"""Resolve an `/adv` advisor/executor pairing and print it in a chosen format.

Usage:
    python resolve.py ADVISOR [EXECUTOR] [--ranks api|claude-code] [--live]
                      [--format json|text|claude-code|python|typescript|curl|managed-agents]

Examples:
    python resolve.py fable opus                  # Claude Fable 5.1 advises Claude Opus 5.5
    python resolve.py fable opus --format json
    python resolve.py opus-4.8 sonnet-4.6 --format python

Exit status: 0 valid pairing, 2 invalid pairing or unknown model, 1 usage error.
`--live` lists models with the official `anthropic` SDK (needs ANTHROPIC_API_KEY); on any
failure it warns on stderr and uses the baked catalog. Standard library only otherwise.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Callable, TextIO

sys.path.insert(0, str(Path(__file__).resolve().parent))

import advmodels as am  # noqa: E402

FORMATS = ("text", "json", "claude-code", "python", "typescript", "curl", "managed-agents")
SNIPPET_FORMATS = ("python", "typescript", "curl")


class UsageError(Exception):
    pass


class _Parser(argparse.ArgumentParser):
    def error(self, message: str) -> None:  # type: ignore[override]
        raise UsageError(message)


def build_parser() -> argparse.ArgumentParser:
    p = _Parser(
        prog="resolve.py",
        description="Resolve and validate an advisor/executor pairing for Claude's advisor tool.",
        epilog="Exit status: 0 valid, 2 invalid pairing or unknown model, 1 usage error.",
    )
    p.add_argument("advisor", help="advisor spec, e.g. fable, opus, opus-4.8, claude-sonnet-5-5")
    p.add_argument("executor", nargs="?", help="executor spec, e.g. opus, sonnet, haiku[1m]")
    p.add_argument(
        "--ranks",
        choices=("api", "claude-code", "claude_code"),
        default="api",
        help="rank table to validate with (default: api; claude-code is stricter for Fable 5)",
    )
    p.add_argument(
        "--live",
        action="store_true",
        help="refresh 'latest' from the Models API via the anthropic SDK (falls back to baked)",
    )
    p.add_argument("--format", choices=FORMATS, default="text", help="output format")
    p.add_argument("--catalog", help=argparse.SUPPRESS)
    return p


# --------------------------------------------------------------------------- core


def _side(spec: am.Spec, model: dict, role: str, ranks_key: str) -> dict:
    return {
        "input": spec.raw,
        "id": model["id"],
        "display": model.get("display") or model["id"],
        "rank": model.get(ranks_key),
        "advice": am.advice_format(model),
        "claude_code_arg": am.claude_code_arg(spec, model, role),
    }


def build_result(
    adv_spec: am.Spec,
    exe_spec: am.Spec | None,
    catalog: dict,
    *,
    ranks: str = "api",
    live_ids: list[str] | None = None,
    source: str = "baked",
) -> dict:
    """Resolve both specs and validate. Raises LookupError for an unknown model."""
    ranks = "claude_code" if ranks in ("claude-code", "claude_code") else "api"
    other = "api" if ranks == "claude_code" else "claude_code"
    key = "claude_code_rank" if ranks == "claude_code" else "rank"

    adv = am.resolve(adv_spec, catalog, live_ids)
    exe = am.resolve(exe_spec, catalog, live_ids) if exe_spec is not None else None
    warnings: list[str] = []

    if exe is not None:
        valid, reason = am.check_pair(adv["id"], exe["id"], catalog, ranks)
        other_ok, other_reason = am.check_pair(adv["id"], exe["id"], catalog, other)
        if valid and not other_ok:
            where = "the Messages API" if other == "api" else "Claude Code"
            warnings.append(f"{where} rejects this pairing: {other_reason}")
        elif not valid and other_ok:
            where = "the Messages API" if other == "api" else "Claude Code"
            warnings.append(f"{where} accepts this pairing ({other_reason})")
        if not valid and am.check_pair(exe["id"], adv["id"], catalog, ranks)[0]:
            warnings.append(
                f"the reverse pairing is valid: advisor {exe_spec.raw}, executor {adv_spec.raw}"
            )
    else:
        valid, reason = am.check_advisor(adv["id"], catalog, ranks)

    if adv_spec.one_m:
        warnings.append("[1m] applies only to the executor; it is ignored for the advisor")
    if am.advice_format(adv) == "encrypted":
        warnings.append(am.advice_note(adv))
    for m in (adv, exe):
        if m is not None and m.get("note"):
            warnings.append(f"{am.describe(m)}: {m['note']}")
    if exe is not None and exe.get("forced_tool_choice") is False:
        warnings.append(
            f"{am.describe(exe)} rejects a forced tool_choice; ask for the advisor in the "
            "prompt instead of forcing it"
        )

    adv_side = _side(adv_spec, adv, "advisor", key)
    exe_side = _side(exe_spec, exe, "executor", key) if exe is not None else None
    commands = []
    launch = "claude"
    if exe_side is not None:
        commands.append(f"/model {exe_side['claude_code_arg']}")
        launch += f" --model {exe_side['claude_code_arg']}"
    commands.append(f"/advisor {adv_side['claude_code_arg']}")
    launch += f" --advisor {adv_side['claude_code_arg']}"

    return {
        "advisor": adv_side,
        "executor": exe_side,
        "valid": bool(valid),
        "reason": reason,
        "advice_format": am.advice_format(adv),
        "source": source,
        "beta": am.beta_header(catalog),
        "tool": am.tool_definition(adv["id"], catalog),
        "claude_code": {"commands": commands, "launch": launch},
        "warnings": warnings,
        "_executor_model": exe,
    }


# --------------------------------------------------------------------------- renderers


def render_text(result: dict) -> str:
    adv, exe = result["advisor"], result["executor"]
    lines = [
        f"Advisor:  {adv['display']} ({adv['id']})  rank {adv['rank']}, advice {adv['advice']}"
    ]
    if exe is not None:
        lines.append(f"Executor: {exe['display']} ({exe['id']})  rank {exe['rank']}")
    status = "VALID" if result["valid"] else "INVALID"
    lines.append(f"Pairing:  {status} - {result['reason']}")
    if result["valid"]:
        lines.append("Claude Code: " + " then ".join(result["claude_code"]["commands"]))
        lines.append(f"New session: {result['claude_code']['launch']}")
        lines.append(
            f"API: beta {result['beta']}, tool {json.dumps(result['tool'])}"
            + (f", model {exe['id']}" if exe is not None else "")
        )
    lines.append(f"Source: {result['source']} catalog")
    lines.extend(f"Warning: {w}" for w in result["warnings"])
    return "\n".join(lines)


def render_json(result: dict) -> str:
    public = {k: v for k, v in result.items() if not k.startswith("_")}
    return json.dumps(public, indent=2)


def render_claude_code(result: dict) -> str:
    cmds = list(result["claude_code"]["commands"])
    cmds.append(f"# or start a new session: {result['claude_code']['launch']}")
    return "\n".join(cmds)


def _tool_choice_comment(result: dict, prefix: str) -> str:
    exe = result.get("_executor_model") or {}
    if exe.get("forced_tool_choice") is False:
        return (
            f"{prefix} {exe['id']} rejects a forced tool_choice: ask for the advisor in the "
            "prompt instead.\n"
        )
    return ""


def _advice_comment(result: dict, prefix: str) -> str:
    if result["advice_format"] == "encrypted":
        return (
            f"{prefix} {result['advisor']['id']} returns encrypted advice "
            "(advisor_redacted_result): the executor uses it, you cannot read it.\n"
        )
    return ""


def render_python(result: dict) -> str:
    exe_id = result["executor"]["id"]
    tool = json.dumps(result["tool"])
    beta = json.dumps(result["beta"])
    return (
        "import anthropic\n"
        "\n"
        "client = anthropic.Anthropic()  # reads ANTHROPIC_API_KEY from the environment\n"
        "\n" + _tool_choice_comment(result, "#") + _advice_comment(result, "#") + "\n"
        "def ask(messages):\n"
        "    return client.beta.messages.create(\n"
        f'        model="{exe_id}",  # executor\n'
        "        max_tokens=16000,\n"
        f"        betas=[{beta}],\n"
        f"        tools=[{tool}],\n"
        "        messages=messages,\n"
        "    )\n"
        "\n"
        "\n"
        'messages = [{"role": "user", "content": "Describe your task here."}]\n'
        "response = ask(messages)\n"
        "# A pending advisor call can end the turn with pause_turn: resend the turn unchanged.\n"
        "for _ in range(5):\n"
        '    if response.stop_reason != "pause_turn":\n'
        "        break\n"
        '    messages.append({"role": "assistant", "content": response.content})\n'
        "    response = ask(messages)\n"
        "\n"
        "for block in response.content:\n"
        '    if block.type == "text":\n'
        "        print(block.text)\n"
        '    elif block.type == "advisor_tool_result":\n'
        '        if block.content.type == "advisor_result":\n'
        '            print("[advice]", block.content.text)\n'
        '        elif block.content.type == "advisor_redacted_result":\n'
        '            print("[advice is encrypted]")\n'
        "        else:\n"
        '            print("[advisor error]", block.content.error_code)\n'
    )


def render_typescript(result: dict) -> str:
    exe_id = result["executor"]["id"]
    t = result["tool"]
    tool = f'{{ type: "{t["type"]}", name: "{t["name"]}", model: "{t["model"]}" }}'
    return (
        'import Anthropic from "@anthropic-ai/sdk";\n'
        "\n"
        "const client = new Anthropic(); // reads ANTHROPIC_API_KEY from the environment\n"
        "\n"
        + _tool_choice_comment(result, "//")
        + _advice_comment(result, "//")
        + "function ask(messages: Anthropic.Beta.BetaMessageParam[]) {\n"
        "  return client.beta.messages.create({\n"
        f'    model: "{exe_id}", // executor\n'
        "    max_tokens: 16000,\n"
        f'    betas: ["{result["beta"]}"],\n'
        f"    tools: [{tool}],\n"
        "    messages,\n"
        "  });\n"
        "}\n"
        "\n"
        "const messages: Anthropic.Beta.BetaMessageParam[] = [\n"
        '  { role: "user", content: "Describe your task here." },\n'
        "];\n"
        "let response = await ask(messages);\n"
        "// A pending advisor call can end the turn with pause_turn: resend the turn unchanged.\n"
        'for (let i = 0; i < 5 && response.stop_reason === "pause_turn"; i++) {\n'
        '  messages.push({ role: "assistant", content: response.content });\n'
        "  response = await ask(messages);\n"
        "}\n"
        "\n"
        "for (const block of response.content) {\n"
        '  if (block.type === "text") console.log(block.text);\n'
        "}\n"
    )


def render_curl(result: dict) -> str:
    body = {
        "model": result["executor"]["id"],
        "max_tokens": 16000,
        "tools": [result["tool"]],
        "messages": [{"role": "user", "content": "Describe your task here."}],
    }
    body_text = json.dumps(body, indent=2).replace("'", "'\\''")
    return (
        _tool_choice_comment(result, "#")
        + _advice_comment(result, "#")
        + "# If stop_reason is pause_turn, append the assistant content unchanged and resend.\n"
        "curl https://api.anthropic.com/v1/messages \\\n"
        '  -H "x-api-key: $ANTHROPIC_API_KEY" \\\n'
        '  -H "anthropic-version: 2023-06-01" \\\n'
        f'  -H "anthropic-beta: {result["beta"]}" \\\n'
        '  -H "content-type: application/json" \\\n'
        f"  -d '{body_text}'\n"
    )


def render_managed_agents(result: dict) -> str:
    block = {
        "multiagent": {
            "type": am.MULTIAGENT_TYPE,
            "workflows": {"type": "disabled"},
            "subagents": {"type": "disabled"},
            "advisor": {"type": "enabled", "model": result["advisor"]["id"]},
        }
    }
    exe = result["executor"]
    who = f"an agent whose model is {exe['id']}" if exe else "the agent definition"
    return (
        f"// Claude Managed Agents: add this to {who}; send the beta header "
        f"{am.MANAGED_AGENTS_BETA}.\n"
        "// The advisor block takes only type and model (no max_uses, max_tokens or caching).\n"
        "// On multiagent_20261001 an omitted member takes its default; workflows and\n"
        "// subagents default to enabled, so they are written out as disabled here.\n"
        + json.dumps(block, indent=2)
        + "\n"
    )


RENDERERS: dict[str, Callable[[dict], str]] = {
    "text": render_text,
    "json": render_json,
    "claude-code": render_claude_code,
    "python": render_python,
    "typescript": render_typescript,
    "curl": render_curl,
    "managed-agents": render_managed_agents,
}


# --------------------------------------------------------------------------- live


def load_live(
    fetch: Callable[[], list[Any]], err: TextIO
) -> tuple[list[str] | None, str, str | None]:
    """(live_ids, source, warning). Never raises: any failure falls back to baked."""
    try:
        rows = fetch()
        ids = am.live_ids_from_models(rows)
        if not ids:
            raise RuntimeError("the Models API returned no usable models")
        return ids, "live", None
    except Exception as exc:  # noqa: BLE001 - any failure means "use the baked catalog"
        msg = f"--live failed ({type(exc).__name__}: {exc}); using the baked catalog"
        print(f"warning: {msg}", file=err)
        return None, "baked", msg


# --------------------------------------------------------------------------- main


def main(
    argv: list[str] | None = None,
    *,
    fetch: Callable[[], list[Any]] | None = None,
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

    if args.format in SNIPPET_FORMATS and args.executor is None:
        print(f"error: --format {args.format} needs an EXECUTOR as well as an ADVISOR", file=err)
        return 1

    catalog = am.load_catalog(args.catalog)
    live_ids, source, live_warning = None, "baked", None
    if args.live:
        live_ids, source, live_warning = load_live(fetch or am.fetch_live_models, err)

    try:
        adv_spec = am.parse_spec(args.advisor)
        exe_spec = am.parse_spec(args.executor) if args.executor is not None else None
        result = build_result(
            adv_spec, exe_spec, catalog, ranks=args.ranks, live_ids=live_ids, source=source
        )
    except (ValueError, LookupError) as exc:
        message = str(exc.args[0]) if exc.args else str(exc)
        if args.format == "json":
            print(
                json.dumps({"valid": False, "error": message, "source": source}, indent=2), file=out
            )
        print(f"error: {message}", file=err)
        return 2

    if live_warning:
        result["warnings"].insert(0, live_warning)

    if not result["valid"] and args.format not in ("json", "text"):
        print(f"error: invalid pairing: {result['reason']}", file=err)
        return 2

    print(RENDERERS[args.format](result).rstrip("\n"), file=out)
    return 0 if result["valid"] else 2


if __name__ == "__main__":
    sys.exit(main())
