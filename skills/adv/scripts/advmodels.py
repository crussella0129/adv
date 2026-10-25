"""Model catalog and pairing rules for the `adv` advisor plugin.

Standard library only. This module is the single Python implementation of the
`/adv` resolution rules described in skills/adv/assets/models.json:

* parse a model spec such as ``fable``, ``Opus-5.5``, ``claude-sonnet-4-6`` or
  ``opus[1m]`` (:func:`parse_spec`);
* resolve it to a catalog model, "latest of the family" for a bare family name
  (:func:`resolve`);
* check an advisor/executor pair with the Messages API ranks or Claude Code's
  ranks (:func:`check_pair`);
* produce the argument Claude Code's ``/model`` and ``/advisor`` expect
  (:func:`claude_code_arg`);
* pick the newest model of a family from Models API rows (:func:`latest_from_live`).

The optional :func:`fetch_live_models` imports the official ``anthropic`` SDK
lazily; nothing outside the standard library is imported at module import time.
"""

from __future__ import annotations

import json
import re
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

FAMILIES = ("fable", "mythos", "opus", "sonnet", "haiku")
DEFAULT_CATALOG = Path(__file__).resolve().parent.parent / "assets" / "models.json"

BETA_HEADER = "advisor-tool-2026-03-01"
TOOL_TYPE = "advisor_20260301"
TOOL_NAME = "advisor"
MANAGED_AGENTS_BETA = "managed-agents-2026-04-01"
MULTIAGENT_TYPE = "multiagent_20261001"
FALLBACK_BETA = "server-side-fallback-2026-07-01"

# One user-typed token: optional claude- prefix, family, optional version, optional [1m].
_SPEC_RE = re.compile(
    r"""^(?:claude-)?
        (?P<family>fable|mythos|opus|sonnet|haiku)
        (?:[-_]?(?P<major>\d{1,2})(?:[._-](?P<minor>\d{1,2}))?)?
        (?P<one_m>\[1m\])?$""",
    re.IGNORECASE | re.VERBOSE,
)

# A model id as the Models API (or a provider) reports it, including dated ids.
_ID_RE = re.compile(
    r"""^(?:(?:us|eu|apac|global|jp|au)\.)?(?:anthropic\.)?claude-
        (?:(?P<fam>[a-z]+)-(?P<maj>\d+)(?:-(?P<min>\d{1,2}))?
          |(?P<maj3>\d+)(?:-(?P<min3>\d{1,2}))?-(?P<fam3>[a-z]+))
        (?:[-@](?P<date>\d{8}|latest))?(?:-v\d+(?::\d+)?)?(?:\[1m\])?$""",
    re.IGNORECASE | re.VERBOSE,
)


@dataclass(frozen=True)
class Spec:
    """A parsed model spec. ``major`` is None for a bare family ("latest")."""

    family: str
    major: int | None
    minor: int | None
    one_m: bool
    raw: str

    @property
    def versioned(self) -> bool:
        return self.major is not None

    def candidate_ids(self) -> list[str]:
        """Catalog ids this versioned spec may name (``5.0`` also tries ``-5``)."""
        if self.major is None:
            return []
        base = f"claude-{self.family}-{self.major}"
        if self.minor is None:
            return [base]
        ids = [f"{base}-{self.minor}"]
        if self.minor == 0:
            ids.append(base)
        return ids


# --------------------------------------------------------------------------- catalog


def load_catalog(path: str | Path | None = None) -> dict:
    """Load models.json (default: ../assets/models.json next to this script)."""
    p = Path(path) if path is not None else DEFAULT_CATALOG
    with open(p, encoding="utf-8") as fh:
        return json.load(fh)


def find_model(model_id: str, catalog: dict) -> dict | None:
    for m in catalog.get("models", []):
        if m["id"] == model_id:
            return m
    return None


def _rules(catalog: dict) -> dict:
    return catalog.get("rules", {})


def beta_header(catalog: dict) -> str:
    return _rules(catalog).get("beta_header", BETA_HEADER)


def tool_definition(
    advisor_id: str,
    catalog: dict | None = None,
    *,
    max_uses: int | None = None,
    max_tokens: int | None = None,
    caching: str | None = None,
) -> dict:
    """The Messages API advisor tool definition for ``advisor_id``."""
    rules = _rules(catalog or {})
    tool: dict[str, Any] = {
        "type": rules.get("tool_type", TOOL_TYPE),
        "name": rules.get("tool_name", TOOL_NAME),
        "model": advisor_id,
    }
    if max_uses is not None:
        tool["max_uses"] = max_uses
    if max_tokens is not None:
        tool["max_tokens"] = max_tokens
    if caching is not None:
        tool["caching"] = {"type": "ephemeral", "ttl": caching}
    return tool


# --------------------------------------------------------------------------- parsing


def parse_spec(token: str) -> Spec:
    """Parse one model-spec token. Raises ValueError when it is not a spec."""
    if not isinstance(token, str):
        raise ValueError(f"not a model spec: {token!r}")
    raw = token
    m = _SPEC_RE.match(token.strip())
    if not m:
        raise ValueError(
            f"not a model spec: {raw!r} (expected fable|mythos|opus|sonnet|haiku, "
            "optionally with a version such as opus-4.8, and an optional [1m])"
        )
    major = m.group("major")
    minor = m.group("minor")
    return Spec(
        family=m.group("family").lower(),
        major=int(major) if major is not None else None,
        minor=int(minor) if minor is not None else None,
        one_m=m.group("one_m") is not None,
        raw=raw,
    )


def is_model_spec(token: str) -> bool:
    try:
        parse_spec(token)
    except ValueError:
        return False
    return True


def parse_model_id(model_id: str) -> tuple[str, int, int] | None:
    """(family, major, minor) for an API model id, or None if it has no version."""
    m = _ID_RE.match(model_id or "")
    if not m:
        return None
    fam = (m.group("fam") or m.group("fam3") or "").lower()
    maj = m.group("maj") or m.group("maj3")
    mnr = m.group("min") or m.group("min3")
    if fam not in FAMILIES or maj is None:
        return None
    return fam, int(maj), int(mnr) if mnr is not None else 0


def _version_of(model_id: str) -> tuple[int, int]:
    parsed = parse_model_id(model_id)
    return (parsed[1], parsed[2]) if parsed else (-1, -1)


# --------------------------------------------------------------------------- resolution


def _minimal_model(model_id: str) -> dict:
    """A catalog-shaped dict for an id known only from the live Models API."""
    parsed = parse_model_id(model_id)
    family = parsed[0] if parsed else None
    version = None
    if parsed:
        version = str(parsed[1]) if parsed[2] == 0 else f"{parsed[1]}.{parsed[2]}"
    display = model_id
    if family and version:
        display = f"Claude {family.capitalize()} {version}"
    return {
        "id": model_id,
        "family": family,
        "version": version,
        "display": display,
        "rank": None,
        "claude_code_rank": None,
        "advice": None,
        "forced_tool_choice": None,
        "adaptive_thinking": None,
        "price_per_mtok": None,
        "note": "Not in the baked catalog (seen in the live Models API); pairing not checked.",
    }


def resolve(spec: Spec, catalog: dict, live_ids: Iterable[str] | None = None) -> dict:
    """Resolve a spec to a model dict. Raises LookupError for unknown models."""
    live = list(live_ids) if live_ids is not None else None

    if not spec.versioned:
        latest_id = catalog["latest"][spec.family]
        model = find_model(latest_id, catalog) or _minimal_model(latest_id)
        if live:
            fam_ids = [i for i in live if (parse_model_id(i) or (None,))[0] == spec.family]
            if fam_ids:
                best = max(
                    fam_ids, key=lambda i: (_version_of(i), find_model(i, catalog) is not None)
                )
                if _version_of(best) > _version_of(latest_id):
                    return find_model(best, catalog) or _minimal_model(best)
        return model

    for cid in spec.candidate_ids():
        model = find_model(cid, catalog)
        if model is not None:
            return model
    if live:
        for cid in spec.candidate_ids():
            for lid in live:
                if lid == cid or (
                    lid.startswith(cid + "-") and re.fullmatch(r"\d{8}", lid[len(cid) + 1 :])
                ):
                    return find_model(lid, catalog) or _minimal_model(cid)
    raise LookupError(
        f"unknown model: {spec.raw!r} (looked for {', '.join(spec.candidate_ids())}); "
        "known: " + ", ".join(m["id"] for m in catalog.get("models", []))
    )


def _rank_key(ranks: str) -> str:
    if ranks in ("api", None):
        return "rank"
    if ranks in ("claude_code", "claude-code"):
        return "claude_code_rank"
    raise ValueError(f"ranks must be 'api' or 'claude_code', not {ranks!r}")


def check_advisor(advisor_id: str, catalog: dict, ranks: str = "api") -> tuple[bool, str]:
    """Can ``advisor_id`` be an advisor at all (rank >= advisor_min_rank)?"""
    key = _rank_key(ranks)
    adv = find_model(advisor_id, catalog)
    min_rank = _rules(catalog).get("advisor_min_rank", 2)
    if adv is None or adv.get(key) is None:
        return True, f"{advisor_id} is not in the baked catalog, so it cannot be checked offline"
    if adv[key] < min_rank:
        return False, (
            f"{describe(adv)} cannot be an advisor: an advisor must be Claude Sonnet 4.6 "
            "or more capable"
        )
    return True, f"{describe(adv)} can be an advisor"


def check_pair(
    advisor_id: str, executor_id: str, catalog: dict, ranks: str = "api"
) -> tuple[bool, str]:
    """Apply the rank rule: advisor rank >= min rank and executor rank <= advisor rank."""
    key = _rank_key(ranks)
    label = "Claude Code" if key == "claude_code_rank" else "Messages API"
    adv = find_model(advisor_id, catalog)
    exe = find_model(executor_id, catalog)
    unknown = [
        mid for mid, m in ((advisor_id, adv), (executor_id, exe)) if m is None or m.get(key) is None
    ]
    if unknown:
        return True, (
            f"{' and '.join(unknown)} not in the baked catalog, so the pairing cannot be "
            "checked offline; the API rejects an invalid pair with a 400"
        )
    ok, reason = check_advisor(advisor_id, catalog, ranks)
    if not ok:
        return False, reason
    if exe[key] > adv[key]:
        return False, (
            f"{describe(adv)} cannot advise {describe(exe)} ({label} rules): the advisor "
            "must be at least as capable as the executor"
        )
    return True, f"{describe(adv)} can advise {describe(exe)} ({label} rules)"


def valid_advisors(executor_id: str, catalog: dict, ranks: str = "api") -> list[str]:
    """Catalog ids that may advise ``executor_id``, most capable first."""
    key = _rank_key(ranks)
    out = [
        m for m in catalog.get("models", []) if check_pair(m["id"], executor_id, catalog, ranks)[0]
    ]
    out.sort(key=lambda m: -(m.get(key) or 0))
    return [m["id"] for m in out]


# --------------------------------------------------------------------------- Claude Code


def claude_code_arg(spec: Spec, model: dict, role: str) -> str:
    """The argument for ``/model`` (role "executor") or ``/advisor`` (role "advisor").

    Bare fable/opus/sonnet become Claude Code aliases so the choice keeps tracking the
    latest model; ``haiku`` is a /model alias but not an /advisor alias, so an advisor
    gets the full id. Mythos and versioned specs always use the full id. Only the
    executor keeps a ``[1m]`` suffix.
    """
    if role not in ("advisor", "executor"):
        raise ValueError("role must be 'advisor' or 'executor'")
    aliases = (
        ("fable", "opus", "sonnet") if role == "advisor" else ("fable", "opus", "sonnet", "haiku")
    )
    if not spec.versioned and spec.family in aliases:
        arg = spec.family
    else:
        arg = model["id"]
    if role == "executor" and spec.one_m:
        arg += "[1m]"
    return arg


# --------------------------------------------------------------------------- live data


def _get(obj: Any, key: str, default: Any = None) -> Any:
    if isinstance(obj, dict):
        return obj.get(key, default)
    return getattr(obj, key, default)


get_field = _get  # public name: read a field from an SDK object or a plain dict


def _created_key(value: Any) -> float:
    if value is None:
        return 0.0
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, datetime):
        try:
            return value.timestamp()
        except (OverflowError, OSError, ValueError):
            return 0.0
    if isinstance(value, str):
        text = value.strip()
        if text.endswith("Z"):
            text = text[:-1] + "+00:00"
        try:
            return datetime.fromisoformat(text).timestamp()
        except ValueError:
            try:
                return float(text)
            except ValueError:
                return 0.0
    return 0.0


def _row_family(row: Any) -> str | None:
    line = _get(row, "line")
    if isinstance(line, str) and line:
        return line.lower()
    parsed = parse_model_id(str(_get(row, "id", "")))
    return parsed[0] if parsed else None


def _eligible_rows(models: Iterable[Any], family: str) -> list[Any]:
    rows = []
    for row in models:
        mid = str(_get(row, "id", "") or "")
        if not mid or _row_family(row) != family:
            continue
        if family != "mythos" and "mythos" in mid.lower():
            continue  # never auto-pick a Glasswing-only model
        rows.append(row)
    active = [r for r in rows if (_get(r, "lifecycle") or "active") == "active"]
    if active:
        return active
    return [r for r in rows if _get(r, "lifecycle") == "deprecated"]


def latest_from_live(models: Iterable[Any], family: str) -> str | None:
    """Newest model id of ``family`` among Models API rows (objects or dicts).

    Rows are filtered by ``line`` (falling back to the family parsed from the id),
    restricted to ``lifecycle == "active"`` (deprecated only when nothing is active,
    retired never), then sorted by parsed (major, minor) and ``created_at``.
    """
    family = family.lower()
    rows = _eligible_rows(list(models), family)
    if not rows:
        return None
    best = max(
        rows,
        key=lambda r: (_version_of(str(_get(r, "id"))), _created_key(_get(r, "created_at"))),
    )
    return str(_get(best, "id"))


def live_ids_from_models(models: Iterable[Any]) -> list[str]:
    """Ids :func:`resolve` may use: per family, active rows (deprecated if none)."""
    rows = list(models)
    ids: list[str] = []
    for fam in FAMILIES:
        ids.extend(str(_get(r, "id")) for r in _eligible_rows(rows, fam))
    return ids


def fetch_live_models() -> list[Any]:
    """List models with the official SDK (auto-paginating). Raises on any failure.

    Needs ``pip install anthropic`` and ANTHROPIC_API_KEY (or ANTHROPIC_AUTH_TOKEN).
    """
    try:
        import anthropic  # optional dependency, imported lazily
    except ImportError as exc:  # pragma: no cover - depends on the environment
        raise RuntimeError("the anthropic SDK is not installed (pip install anthropic)") from exc
    client = anthropic.Anthropic()
    return list(client.models.list())


# --------------------------------------------------------------------------- formatting


def describe(model: dict) -> str:
    """``Claude Opus 5.5 (claude-opus-5-5)``."""
    display = model.get("display") or model["id"]
    if display == model["id"]:
        return model["id"]
    return f"{display} ({model['id']})"


def advice_format(model: dict) -> str:
    """``encrypted``, ``plaintext``, ``none`` (cannot advise) or ``unknown``."""
    advice = model.get("advice")
    if advice in ("encrypted", "plaintext"):
        return advice
    if model.get("rank") is not None:
        return "none"
    return "unknown"


def advice_note(model: dict) -> str:
    fmt = advice_format(model)
    if fmt == "encrypted":
        return (
            f"{describe(model)} returns encrypted advice (advisor_redacted_result): the "
            "executor reads it, but the advice text will not be readable in responses"
        )
    if fmt == "plaintext":
        return f"{describe(model)} returns plaintext advice (advisor_result.text)"
    if fmt == "none":
        return f"{describe(model)} cannot be an advisor"
    return f"advice format of {model['id']} is unknown"
