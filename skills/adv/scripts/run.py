"""Run one task through the Claude Messages API with the advisor tool.

Usage:
    python run.py ADVISOR EXECUTOR [TASK ...] [options]
    echo "task text" | python run.py fable opus -

The EXECUTOR is the request's model and does the work; the ADVISOR is attached as the
server-side advisor tool (beta advisor-tool-2026-03-01). Uses the official `anthropic`
SDK (pip install anthropic) and ANTHROPIC_API_KEY from the environment. API usage is
billed to the Console account that owns the key. --dry-run needs neither.

Exit status: 0 done, 1 usage/setup/API error, 2 invalid pairing or unknown model,
3 the model refused (stop_reason "refusal"), 4 still paused after 5 continuations.
"""

from __future__ import annotations

import argparse
import io
import json
import sys
from pathlib import Path
from typing import Any, Callable, TextIO

sys.path.insert(0, str(Path(__file__).resolve().parent))

import advmodels as am  # noqa: E402

MAX_CONTINUATIONS = 5
EFFORTS = ("low", "medium", "high", "xhigh", "max")
COST_NOTE = (
    "approximate: uncached input and output tokens at catalog list prices only; "
    "cache reads/writes and any fallback model are not priced"
)


class UsageError(Exception):
    pass


class PairingError(Exception):
    pass


class _Parser(argparse.ArgumentParser):
    def error(self, message: str) -> None:  # type: ignore[override]
        raise UsageError(message)


def _positive(text: str) -> int:
    try:
        value = int(text)
    except ValueError as exc:
        raise argparse.ArgumentTypeError(f"not an integer: {text!r}") from exc
    if value < 1:
        raise argparse.ArgumentTypeError("must be at least 1")
    return value


def _advisor_tokens(text: str) -> int:
    value = _positive(text)
    if value < 1024:
        raise argparse.ArgumentTypeError("the advisor's max_tokens must be at least 1024")
    return value


def build_parser() -> argparse.ArgumentParser:
    p = _Parser(
        prog="run.py",
        description=(
            "Run a task on EXECUTOR with ADVISOR attached as Claude's server-side advisor "
            "tool, streaming the answer to stdout and a usage summary to stderr."
        ),
        epilog=(
            "Exit status: 0 done, 1 usage/setup/API error, 2 invalid pairing or unknown "
            "model, 3 refusal, 4 still paused after 5 continuations."
        ),
    )
    p.add_argument("advisor", help="advisor spec, e.g. fable, opus, opus-4.8")
    p.add_argument("executor", help="executor spec, e.g. opus, sonnet, haiku")
    p.add_argument("task", nargs="*", help="task text (words are joined); omit or '-' for stdin")
    p.add_argument("--effort", choices=EFFORTS, help="output_config.effort for the executor")
    p.add_argument("--max-uses", type=_positive, help="cap on advisor calls per request")
    p.add_argument(
        "--advisor-max-tokens",
        type=_advisor_tokens,
        help="cap on the advisor's output per call (minimum 1024)",
    )
    p.add_argument(
        "--caching", choices=("5m", "1h"), help="cache the advisor's prompt with this TTL"
    )
    p.add_argument("--system", metavar="FILE", help="read the system prompt from FILE")
    p.add_argument(
        "--max-tokens", type=_positive, default=64000, help="executor max_tokens (default 64000)"
    )
    p.add_argument(
        "--live",
        action="store_true",
        help="resolve bare family names against the Models API (falls back to baked)",
    )
    p.add_argument(
        "--fallbacks",
        action="store_true",
        help=(
            'opt in to server-side refusal fallbacks (fallbacks: "default", beta '
            f"{am.FALLBACK_BETA}). Off by default: a fallback can swap the executor for a "
            "model this advisor pairing was not validated for. Ignored for Haiku executors, "
            "which have no server-side fallback."
        ),
    )
    p.add_argument("--json", action="store_true", help="print a JSON summary instead of text")
    p.add_argument(
        "--dry-run",
        action="store_true",
        help="print the request as JSON and exit without calling the API",
    )
    p.add_argument("--catalog", help=argparse.SUPPRESS)
    return p


# --------------------------------------------------------------------------- request


def read_task(words: list[str], stdin: TextIO) -> str:
    if not words or words == ["-"]:
        return stdin.read().strip()
    return " ".join(words).strip()


def build_request(
    args: argparse.Namespace,
    catalog: dict,
    task: str,
    *,
    system_text: str | None = None,
    live_ids: list[str] | None = None,
) -> tuple[dict, dict, dict, list[str]]:
    """Return (request kwargs, advisor model, executor model, warnings).

    Raises ValueError/LookupError for a bad spec and PairingError for an invalid pair.
    """
    adv_spec = am.parse_spec(args.advisor)
    exe_spec = am.parse_spec(args.executor)
    adv = am.resolve(adv_spec, catalog, live_ids)
    exe = am.resolve(exe_spec, catalog, live_ids)
    warnings: list[str] = []

    ok, reason = am.check_pair(adv["id"], exe["id"], catalog, "api")
    if not ok:
        raise PairingError(reason)
    if adv.get("rank") is None or exe.get("rank") is None:
        warnings.append(reason)
    if adv_spec.one_m or exe_spec.one_m:
        warnings.append("[1m] is a Claude Code suffix; it is not sent to the API")
    if am.advice_format(adv) == "encrypted":
        warnings.append(am.advice_note(adv))

    tool = am.tool_definition(
        adv["id"],
        catalog,
        max_uses=args.max_uses,
        max_tokens=args.advisor_max_tokens,
        caching=args.caching,
    )
    betas = [am.beta_header(catalog)]
    request: dict[str, Any] = {
        "model": exe["id"],
        "max_tokens": args.max_tokens,
        "betas": betas,
        "tools": [tool],
        "messages": [{"role": "user", "content": task}],
    }
    if system_text:
        request["system"] = system_text
    if exe.get("adaptive_thinking") is not False:
        request["thinking"] = {"type": "adaptive"}
    if args.effort:
        if exe.get("adaptive_thinking") is False:
            # Effort levels error on models without adaptive thinking (Claude Haiku 4.5).
            warnings.append(
                f"{exe['id']} does not support effort; --effort {args.effort} was not sent"
            )
        else:
            request["output_config"] = {"effort": args.effort}
    if args.fallbacks and exe.get("family") == "haiku":
        # The docs say there is no server-side fallback for the Haiku line: "default"
        # leaves a declined request declined, so the parameter would only mislead.
        warnings.append(
            f"server-side fallback has no effect for {exe['id']}; --fallbacks was not sent"
        )
    elif args.fallbacks:
        betas.append(am.FALLBACK_BETA)
        request["fallbacks"] = "default"
        warnings.append(
            "refusal fallbacks are on: a declined turn may be served by a different model "
            "than the validated executor"
        )
    # Never send tool_choice: several executors reject a forced choice, and the advisor
    # is meant to be consulted when the executor decides it needs help.
    return request, adv, exe, warnings


# --------------------------------------------------------------------------- running


def run_task(
    client: Any,
    request: dict,
    out: TextIO,
    err: TextIO,
    max_continuations: int = MAX_CONTINUATIONS,
) -> list[Any]:
    """Stream the request, resuming pause_turn up to ``max_continuations`` times.

    Returns every final message (one per request sent). Text deltas go to ``out``.
    """
    messages = list(request["messages"])
    finals: list[Any] = []
    for attempt in range(max_continuations + 1):
        kwargs = dict(request)
        kwargs["messages"] = list(messages)
        with client.beta.messages.stream(**kwargs) as stream:
            for text in stream.text_stream:
                out.write(text)
                out.flush()
            final = stream.get_final_message()
        finals.append(final)
        if am.get_field(final, "stop_reason") != "pause_turn":
            break
        if attempt < max_continuations:
            # Send the paused assistant turn back unchanged, with the same tools and betas.
            messages.append({"role": "assistant", "content": am.get_field(final, "content")})
    return finals


def execute(
    client: Any, request: dict, out: TextIO, err: TextIO, anthropic_mod: Any = None
) -> tuple[list[Any] | None, int]:
    """run_task with the SDK's typed errors mapped to messages and exit code 1."""
    if anthropic_mod is None:
        try:
            import anthropic as anthropic_mod  # lazily: only needed for a real call
        except ImportError:
            anthropic_mod = None
    if anthropic_mod is None:
        return run_task(client, request, out, err), 0
    try:
        return run_task(client, request, out, err), 0
    except anthropic_mod.BadRequestError as exc:
        print(f"\nerror: the API rejected the request (400): {exc.message}", file=err)
        print(
            "hint: this usually means the advisor/executor pairing is invalid or a beta "
            "header is not enabled for your organization",
            file=err,
        )
    except anthropic_mod.RateLimitError as exc:
        print(f"\nerror: rate limited (429): {exc.message}", file=err)
    except anthropic_mod.APIStatusError as exc:
        print(f"\nerror: API error {exc.status_code}: {exc.message}", file=err)
    except anthropic_mod.APIConnectionError as exc:
        print(f"\nerror: could not reach the API: {exc}", file=err)
    return None, 1


# --------------------------------------------------------------------------- summary


def _empty_usage() -> dict:
    return {"input_tokens": 0, "output_tokens": 0, "cache_read_tokens": 0, "cache_write_tokens": 0}


def _add_usage(total: dict, usage: Any) -> None:
    g = am.get_field
    total["input_tokens"] += g(usage, "input_tokens", 0) or 0
    total["output_tokens"] += g(usage, "output_tokens", 0) or 0
    total["cache_read_tokens"] += g(usage, "cache_read_input_tokens", 0) or 0
    total["cache_write_tokens"] += g(usage, "cache_creation_input_tokens", 0) or 0


def _cost(usage: dict, model: dict | None) -> float | None:
    price = (model or {}).get("price_per_mtok")
    if not price:
        return None
    return round(
        (usage["input_tokens"] * price["input"] + usage["output_tokens"] * price["output"]) / 1e6,
        6,
    )


def advice_entries(finals: list[Any]) -> list[dict]:
    g = am.get_field
    entries = []
    for final in finals:
        for block in g(final, "content", None) or []:
            if g(block, "type") != "advisor_tool_result":
                continue
            content = g(block, "content")
            kind = g(content, "type")
            if kind == "advisor_result":
                entries.append({"type": kind, "text": g(content, "text", "")})
            elif kind == "advisor_redacted_result":
                entries.append({"type": kind, "text": "[encrypted advice]"})
            elif kind == "advisor_tool_result_error":
                entries.append({"type": kind, "error_code": g(content, "error_code")})
            else:
                entries.append({"type": str(kind)})
    return entries


def summarize(finals: list[Any], catalog: dict, advisor_id: str, executor_id: str) -> dict:
    g = am.get_field
    executor = _empty_usage()
    advisor = _empty_usage()
    advisor_model = advisor_id
    other: dict[str, dict] = {}
    for final in finals:
        usage = g(final, "usage")
        if usage is None:
            continue
        iterations = g(usage, "iterations", None)
        if not iterations:
            _add_usage(executor, usage)
            continue
        for it in iterations:
            kind = g(it, "type")
            if kind == "message":
                _add_usage(executor, it)
            elif kind == "advisor_message":
                advisor_model = g(it, "model", None) or advisor_model
                _add_usage(advisor, it)
            else:
                _add_usage(other.setdefault(str(kind), _empty_usage()), it)

    exe_cost = _cost(executor, am.find_model(executor_id, catalog))
    adv_cost = _cost(advisor, am.find_model(advisor_model, catalog))
    total = None
    if exe_cost is not None and adv_cost is not None:
        total = round(exe_cost + adv_cost, 6)
    last = finals[-1] if finals else None
    summary = {
        "executor": executor_id,
        "advisor": advisor_id,
        "stop_reason": g(last, "stop_reason") if last is not None else None,
        "continuations": max(len(finals) - 1, 0),
        "advice": advice_entries(finals),
        "usage": {"executor": executor, "advisor": dict(advisor, model=advisor_model)},
        "approx_cost_usd": {
            "executor": exe_cost,
            "advisor": adv_cost,
            "total": total,
            "note": COST_NOTE,
        },
    }
    if other:
        summary["usage"]["other"] = other
    return summary


def _fmt_usage(u: dict) -> str:
    return (
        f"input {u['input_tokens']}, output {u['output_tokens']}, "
        f"cache read {u['cache_read_tokens']}, cache write {u['cache_write_tokens']}"
    )


def _fmt_cost(value: float | None) -> str:
    return "n/a" if value is None else f"~${value:.4f}"


def format_summary(summary: dict) -> str:
    lines = ["", "--- advisor run summary ---"]
    if summary["advice"]:
        for i, entry in enumerate(summary["advice"], 1):
            if entry["type"] == "advisor_tool_result_error":
                lines.append(f"advice {i}: error {entry.get('error_code')}")
            else:
                lines.append(f"advice {i}: {entry.get('text', '')}")
    else:
        lines.append("advice: the executor did not consult the advisor")
    u = summary["usage"]
    c = summary["approx_cost_usd"]
    lines.append(f"executor {summary['executor']}: {_fmt_usage(u['executor'])}")
    lines.append(f"advisor {u['advisor']['model']}: {_fmt_usage(u['advisor'])}")
    for kind, usage in u.get("other", {}).items():
        lines.append(f"{kind}: {_fmt_usage(usage)}")
    lines.append(
        f"cost: executor {_fmt_cost(c['executor'])}, advisor {_fmt_cost(c['advisor'])}, "
        f"total {_fmt_cost(c['total'])} ({c['note']})"
    )
    if summary["continuations"]:
        lines.append(f"pause_turn continuations: {summary['continuations']}")
    lines.append(f"stop_reason: {summary['stop_reason']}")
    return "\n".join(lines)


# --------------------------------------------------------------------------- main


def _make_client(err: TextIO) -> Any:
    try:
        import anthropic
    except ImportError:
        print(
            "error: the official Anthropic SDK is not installed. Run: pip install anthropic",
            file=err,
        )
        return None
    try:
        return anthropic.Anthropic()
    except Exception as exc:  # noqa: BLE001 - e.g. missing credentials
        print(
            f"error: could not create the API client ({exc}). Set ANTHROPIC_API_KEY.",
            file=err,
        )
        return None


def main(
    argv: list[str] | None = None,
    *,
    client: Any = None,
    anthropic_mod: Any = None,
    fetch: Callable[[], list[Any]] | None = None,
    stdin: TextIO | None = None,
    stdout: TextIO | None = None,
    stderr: TextIO | None = None,
) -> int:
    out = stdout or sys.stdout
    err = stderr or sys.stderr
    parser = build_parser()
    try:
        args = parser.parse_args(argv)
    except UsageError as exc:
        print(parser.format_usage().rstrip(), file=err)
        print(f"error: {exc}", file=err)
        return 1
    except SystemExit as exc:  # --help
        return int(exc.code or 0)

    catalog = am.load_catalog(args.catalog)
    system_text = None
    if args.system:
        try:
            system_text = Path(args.system).read_text(encoding="utf-8")
        except OSError as exc:
            print(f"error: cannot read --system file: {exc}", file=err)
            return 1

    task = read_task(args.task, stdin or sys.stdin)
    if not task:
        print("error: no task given (pass TASK words, or pipe it on stdin)", file=err)
        return 1

    live_ids = None
    if args.live:
        try:
            live_ids = am.live_ids_from_models((fetch or am.fetch_live_models)()) or None
        except Exception as exc:  # noqa: BLE001 - any failure means "use the baked catalog"
            print(f"warning: --live failed ({exc}); using the baked catalog", file=err)

    try:
        request, adv, exe, warnings = build_request(
            args, catalog, task, system_text=system_text, live_ids=live_ids
        )
    except PairingError as exc:
        print(f"error: invalid pairing: {exc}", file=err)
        return 2
    except (ValueError, LookupError) as exc:
        print(f"error: {exc.args[0] if exc.args else exc}", file=err)
        return 2

    if args.dry_run:
        print(json.dumps(request, indent=2), file=out)
        for w in warnings:
            print(f"warning: {w}", file=err)
        return 0

    for w in warnings:
        print(f"warning: {w}", file=err)
    if client is None:
        client = _make_client(err)
        if client is None:
            return 1

    stream_out = io.StringIO() if args.json else out
    finals, code = execute(client, request, stream_out, err, anthropic_mod)
    if finals is None:
        return code
    if not args.json:
        out.write("\n")
        out.flush()

    summary = summarize(finals, catalog, adv["id"], exe["id"])
    last = finals[-1]
    stop = am.get_field(last, "stop_reason")
    exit_code = 0
    if stop == "refusal":
        details = am.get_field(last, "stop_details")
        category = am.get_field(details, "category") if details is not None else None
        explanation = am.get_field(details, "explanation") if details is not None else None
        summary["stop_details"] = {"category": category, "explanation": explanation}
        print(f"refused: category={category} explanation={explanation}", file=err)
        exit_code = 3
    elif stop == "max_tokens":
        print("warning: the executor hit max_tokens; the answer is truncated", file=err)
    elif stop == "pause_turn":
        print(
            f"warning: still paused after {MAX_CONTINUATIONS} continuations; the answer is "
            "incomplete",
            file=err,
        )
        exit_code = 4

    if args.json:
        summary["text"] = stream_out.getvalue()
        summary["warnings"] = warnings
        print(json.dumps(summary, indent=2), file=out)
    else:
        print(format_summary(summary), file=err)
    return exit_code


if __name__ == "__main__":
    sys.exit(main())
