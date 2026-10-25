"""Tests for skills/adv/scripts/resolve.py (in-process main(), no network)."""

from __future__ import annotations

import contextlib
import io
import json
import sys
import unittest
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parent.parent / "skills" / "adv" / "scripts"
sys.path.insert(0, str(SCRIPTS))

import resolve  # noqa: E402


def run(*argv, fetch=None):
    out, err = io.StringIO(), io.StringIO()
    code = resolve.main(list(argv), fetch=fetch, stdout=out, stderr=err)
    return code, out.getvalue(), err.getvalue()


def no_network():
    raise AssertionError("fetch must not be called")


class ExitCodeTest(unittest.TestCase):
    def test_valid_pair(self):
        code, out, _ = run("Fable", "Opus")
        self.assertEqual(code, 0)
        self.assertIn("VALID", out)
        self.assertIn("claude --model opus --advisor fable", out)

    def test_invalid_pair(self):
        code, out, _ = run("opus", "fable")
        self.assertEqual(code, 2)
        self.assertIn("INVALID", out)
        self.assertIn("reverse pairing is valid", out)

    def test_unknown_model(self):
        self.assertEqual(run("opus-4.5", "sonnet")[0], 2)
        self.assertEqual(run("gpt-4")[0], 2)

    def test_usage_errors(self):
        self.assertEqual(run()[0], 1)
        self.assertEqual(run("fable", "opus", "extra")[0], 1)
        self.assertEqual(run("fable", "--format", "yaml")[0], 1)
        self.assertEqual(run("fable", "--format", "python")[0], 1)  # snippet needs executor

    def test_help(self):
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            self.assertEqual(run("--help")[0], 0)
        self.assertIn("Exit status", buf.getvalue())

    def test_advisor_only(self):
        code, out, _ = run("fable", "--format", "json")
        self.assertEqual(code, 0)
        data = json.loads(out)
        self.assertIsNone(data["executor"])
        self.assertEqual(data["claude_code"]["commands"], ["/advisor fable"])
        self.assertEqual(data["claude_code"]["launch"], "claude --advisor fable")
        self.assertEqual(run("haiku-4.5")[0], 2)  # Haiku 4.5 cannot advise


class JsonShapeTest(unittest.TestCase):
    def test_fable_opus(self):
        code, out, _ = run("Fable", "Opus", "--format", "json")
        self.assertEqual(code, 0)
        data = json.loads(out)
        self.assertEqual(
            set(data),
            {
                "advisor", "executor", "valid", "reason", "advice_format", "source", "beta",
                "tool", "claude_code", "warnings",
            },
        )  # fmt: skip
        side_keys = {"input", "id", "display", "rank", "advice", "claude_code_arg"}
        self.assertEqual(set(data["advisor"]), side_keys)
        self.assertEqual(set(data["executor"]), side_keys)
        self.assertEqual(data["advisor"]["id"], "claude-fable-5-1")
        self.assertEqual(data["advisor"]["input"], "Fable")
        self.assertEqual(data["executor"]["id"], "claude-opus-5-5")
        self.assertTrue(data["valid"])
        self.assertEqual(data["advice_format"], "encrypted")
        self.assertEqual(data["source"], "baked")
        self.assertEqual(data["beta"], "advisor-tool-2026-03-01")
        self.assertEqual(
            data["tool"],
            {"type": "advisor_20260301", "name": "advisor", "model": "claude-fable-5-1"},
        )
        self.assertEqual(data["claude_code"]["commands"], ["/model opus", "/advisor fable"])
        self.assertTrue(any("not be readable" in w for w in data["warnings"]))

    def test_invalid_json_still_printed(self):
        code, out, _ = run("opus", "fable", "--format", "json")
        self.assertEqual(code, 2)
        self.assertFalse(json.loads(out)["valid"])

    def test_unknown_json(self):
        code, out, _ = run("sonnet-9", "--format", "json")
        self.assertEqual(code, 2)
        data = json.loads(out)
        self.assertFalse(data["valid"])
        self.assertIn("unknown model", data["error"])

    def test_ranks_claude_code(self):
        code, out, _ = run("opus", "fable-5", "--format", "json")
        self.assertEqual(code, 0)
        self.assertTrue(any("Claude Code rejects" in w for w in json.loads(out)["warnings"]))
        code, out, _ = run("opus", "fable-5", "--format", "json", "--ranks", "claude-code")
        self.assertEqual(code, 2)
        data = json.loads(out)
        self.assertEqual(data["executor"]["rank"], 8)
        self.assertTrue(any("Messages API accepts" in w for w in data["warnings"]))

    def test_haiku_and_one_m_args(self):
        code, out, _ = run("haiku", "sonnet-4.6[1m]", "--format", "json")
        self.assertEqual(code, 0)
        data = json.loads(out)
        self.assertEqual(data["advisor"]["claude_code_arg"], "claude-haiku-5-5")
        self.assertEqual(data["executor"]["claude_code_arg"], "claude-sonnet-4-6[1m]")
        self.assertEqual(data["executor"]["id"], "claude-sonnet-4-6")


class LiveTest(unittest.TestCase):
    def test_live_failure_falls_back(self):
        def boom():
            raise RuntimeError("no credentials")

        code, out, err = run("fable", "opus", "--live", "--format", "json", fetch=boom)
        self.assertEqual(code, 0)
        data = json.loads(out)
        self.assertEqual(data["source"], "baked")
        self.assertIn("no credentials", err)
        self.assertIn("--live failed", data["warnings"][0])

    def test_live_newer_model(self):
        rows = [
            {"id": "claude-opus-6", "line": "opus", "lifecycle": "active"},
            {"id": "claude-fable-5-1", "line": "fable", "lifecycle": "active"},
        ]
        code, out, _ = run("fable", "opus", "--live", "--format", "json", fetch=lambda: rows)
        self.assertEqual(code, 0)
        data = json.loads(out)
        self.assertEqual(data["source"], "live")
        self.assertEqual(data["executor"]["id"], "claude-opus-6")
        self.assertIsNone(data["executor"]["rank"])
        self.assertIn("cannot be checked offline", data["reason"])

    def test_no_fetch_without_live(self):
        self.assertEqual(run("fable", "opus", fetch=no_network)[0], 0)


class SnippetTest(unittest.TestCase):
    def test_python(self):
        code, out, _ = run("fable", "opus", "--format", "python")
        self.assertEqual(code, 0)
        self.assertIn("client.beta.messages.create(", out)
        self.assertIn('betas=["advisor-tool-2026-03-01"]', out)
        self.assertIn(
            'tools=[{"type": "advisor_20260301", "name": "advisor", "model": "claude-fable-5-1"}]',
            out,
        )
        self.assertIn('model="claude-opus-5-5"', out)
        self.assertNotIn("tool_choice=", out)
        self.assertIn("pause_turn", out)
        compile(out, "<snippet>", "exec")

    def test_typescript(self):
        code, out, _ = run("opus-4.8", "sonnet-4.6", "--format", "typescript")
        self.assertEqual(code, 0)
        self.assertIn("client.beta.messages.create({", out)
        self.assertIn('betas: ["advisor-tool-2026-03-01"]', out)
        self.assertIn('model: "claude-sonnet-4-6"', out)
        self.assertIn('model: "claude-opus-4-8"', out)
        self.assertNotIn("tool_choice", out)

    def test_curl(self):
        code, out, _ = run("fable", "opus", "--format", "curl")
        self.assertEqual(code, 0)
        self.assertIn('-H "x-api-key: $ANTHROPIC_API_KEY"', out)
        self.assertIn('-H "anthropic-version: 2023-06-01"', out)
        self.assertIn('-H "anthropic-beta: advisor-tool-2026-03-01"', out)
        body = out.split("-d '", 1)[1].rsplit("'", 1)[0]
        data = json.loads(body)
        self.assertEqual(data["model"], "claude-opus-5-5")
        self.assertEqual(data["tools"][0]["model"], "claude-fable-5-1")
        self.assertNotIn("tool_choice", data)

    def test_managed_agents(self):
        code, out, _ = run("opus", "sonnet", "--format", "managed-agents")
        self.assertEqual(code, 0)
        self.assertIn("managed-agents-2026-04-01", out)
        body = "\n".join(line for line in out.splitlines() if not line.startswith("//"))
        self.assertEqual(
            json.loads(body),
            {
                "multiagent": {
                    "type": "multiagent_20261001",
                    "workflows": {"type": "disabled"},
                    "subagents": {"type": "disabled"},
                    "advisor": {"type": "enabled", "model": "claude-opus-5-5"},
                }
            },
        )

    def test_claude_code(self):
        code, out, _ = run("fable", "opus", "--format", "claude-code")
        self.assertEqual(code, 0)
        self.assertEqual(out.splitlines()[:2], ["/model opus", "/advisor fable"])

    def test_invalid_pair_no_snippet(self):
        code, out, err = run("opus", "fable", "--format", "python")
        self.assertEqual(code, 2)
        self.assertEqual(out, "")
        self.assertIn("invalid pairing", err)


if __name__ == "__main__":
    unittest.main()
