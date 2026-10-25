"""Tests for skills/adv/scripts/run.py with a fake streaming client (no network)."""

from __future__ import annotations

import io
import json
import sys
import unittest
from pathlib import Path
from types import SimpleNamespace as NS

SCRIPTS = Path(__file__).resolve().parent.parent / "skills" / "adv" / "scripts"
sys.path.insert(0, str(SCRIPTS))

import run  # noqa: E402


class FakeStream:
    def __init__(self, texts, final):
        self._texts = texts
        self._final = final

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    @property
    def text_stream(self):
        return iter(self._texts)

    def get_final_message(self):
        return self._final


class FakeMessages:
    def __init__(self, script):
        self.script = list(script)
        self.calls = []

    def stream(self, **kwargs):
        self.calls.append(kwargs)
        texts, final = self.script.pop(0)
        return FakeStream(texts, final)


def fake_client(*script):
    messages = FakeMessages(script)
    return NS(beta=NS(messages=messages)), messages


def it(kind, inp, out, cread=0, cwrite=0, model=None):
    d = NS(
        type=kind,
        input_tokens=inp,
        output_tokens=out,
        cache_read_input_tokens=cread,
        cache_creation_input_tokens=cwrite,
    )
    if model:
        d.model = model
    return d


def message(stop_reason, content, iterations=None, stop_details=None):
    usage = NS(input_tokens=0, output_tokens=0, iterations=iterations)
    return NS(stop_reason=stop_reason, content=content, usage=usage, stop_details=stop_details)


def call(argv, client=None, stdin=""):
    out, err = io.StringIO(), io.StringIO()
    code = run.main(argv, client=client, stdin=io.StringIO(stdin), stdout=out, stderr=err)
    return code, out.getvalue(), err.getvalue()


class DryRunTest(unittest.TestCase):
    def test_request_shape(self):
        code, out, _ = call(["fable", "opus", "Build", "a", "parser", "--dry-run"])
        self.assertEqual(code, 0)
        req = json.loads(out)
        self.assertEqual(req["model"], "claude-opus-5-5")
        self.assertEqual(req["betas"], ["advisor-tool-2026-03-01"])
        self.assertEqual(
            req["tools"],
            [{"type": "advisor_20260301", "name": "advisor", "model": "claude-fable-5-1"}],
        )
        self.assertEqual(req["messages"], [{"role": "user", "content": "Build a parser"}])
        self.assertEqual(req["thinking"], {"type": "adaptive"})
        self.assertEqual(req["max_tokens"], 64000)
        self.assertNotIn("tool_choice", req)
        self.assertNotIn("fallbacks", req)
        self.assertNotIn("system", req)

    def test_haiku_45_omits_thinking(self):
        code, out, _ = call(["sonnet-4.6", "haiku-4.5", "hi", "--dry-run"])
        self.assertEqual(code, 0)
        req = json.loads(out)
        self.assertEqual(req["model"], "claude-haiku-4-5")
        self.assertNotIn("thinking", req)
        self.assertNotIn("tool_choice", req)

    def test_haiku_45_drops_effort(self):
        code, out, err = call(["sonnet", "haiku-4.5", "hi", "--effort", "high", "--dry-run"])
        self.assertEqual(code, 0)
        req = json.loads(out)
        self.assertNotIn("output_config", req)
        self.assertIn("does not support effort", err)

    def test_haiku_skips_fallbacks(self):
        code, out, err = call(["opus", "haiku", "hi", "--fallbacks", "--dry-run"])
        self.assertEqual(code, 0)
        req = json.loads(out)
        self.assertNotIn("fallbacks", req)
        self.assertEqual(req["betas"], ["advisor-tool-2026-03-01"])
        self.assertIn("no effect", err)

    def test_options(self):
        code, out, _ = call(
            [
                "opus", "sonnet", "task", "--dry-run", "--effort", "high", "--max-uses", "3",
                "--advisor-max-tokens", "2048", "--caching", "1h", "--max-tokens", "8000",
                "--fallbacks",
            ]
        )  # fmt: skip
        self.assertEqual(code, 0)
        req = json.loads(out)
        self.assertEqual(
            req["tools"][0],
            {
                "type": "advisor_20260301",
                "name": "advisor",
                "model": "claude-opus-5-5",
                "max_uses": 3,
                "max_tokens": 2048,
                "caching": {"type": "ephemeral", "ttl": "1h"},
            },
        )
        self.assertEqual(req["output_config"], {"effort": "high"})
        self.assertEqual(req["max_tokens"], 8000)
        self.assertEqual(req["fallbacks"], "default")
        self.assertEqual(
            req["betas"], ["advisor-tool-2026-03-01", "server-side-fallback-2026-07-01"]
        )

    def test_stdin_task_and_system(self):
        import tempfile

        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "sys.txt"
            path.write_text("Be terse.", encoding="utf-8")
            code, out, _ = call(
                ["fable", "opus", "-", "--dry-run", "--system", str(path)], stdin="from stdin\n"
            )
        self.assertEqual(code, 0)
        req = json.loads(out)
        self.assertEqual(req["messages"][0]["content"], "from stdin")
        self.assertEqual(req["system"], "Be terse.")

    def test_validation(self):
        self.assertEqual(call(["opus", "fable", "x", "--dry-run"])[0], 2)
        self.assertEqual(call(["haiku-4.5", "haiku-4.5", "x", "--dry-run"])[0], 2)
        self.assertEqual(call(["gpt-4", "opus", "x", "--dry-run"])[0], 2)
        self.assertEqual(call(["fable", "opus", "x", "--advisor-max-tokens", "512"])[0], 1)
        self.assertEqual(call(["fable", "opus", "x", "--max-uses", "0"])[0], 1)
        self.assertEqual(call(["fable"])[0], 1)
        self.assertEqual(call(["fable", "opus", "--dry-run"], stdin="")[0], 1)

    def test_invalid_pair_never_calls_api(self):
        client, messages = fake_client()
        self.assertEqual(call(["opus", "fable", "x"], client=client)[0], 2)
        self.assertEqual(messages.calls, [])


class RunTaskTest(unittest.TestCase):
    def test_pause_turn_continuation(self):
        paused_content = [
            NS(type="text", text="Thinking about it. "),
            NS(type="server_tool_use", id="srvtoolu_1", name="advisor", input={}),
        ]
        done_content = [
            NS(
                type="advisor_tool_result",
                tool_use_id="srvtoolu_1",
                content=NS(type="advisor_result", text="Use a state machine.", stop_reason=None),
            ),
            NS(type="text", text="Done."),
        ]
        client, messages = fake_client(
            (["Thinking about it. "], message("pause_turn", paused_content,
                                              [it("message", 100, 10)])),
            (["Done."], message("end_turn", done_content,
                                [it("advisor_message", 500, 300, model="claude-opus-4-8"),
                                 it("message", 200, 50)])),
        )  # fmt: skip
        code, out, err = call(["opus-4.8", "sonnet-4.6", "write", "it"], client=client)
        self.assertEqual(code, 0)
        self.assertEqual(out, "Thinking about it. Done.\n")
        self.assertEqual(len(messages.calls), 2)
        first, second = messages.calls
        self.assertEqual(first["messages"], [{"role": "user", "content": "write it"}])
        self.assertEqual(
            second["messages"],
            [
                {"role": "user", "content": "write it"},
                {"role": "assistant", "content": paused_content},
            ],
        )
        self.assertIs(second["messages"][1]["content"], paused_content)  # verbatim
        for key in ("tools", "betas", "model", "thinking"):
            self.assertEqual(first[key], second[key])
        self.assertIn("Use a state machine.", err)
        self.assertIn("pause_turn continuations: 1", err)

    def test_continuation_limit(self):
        script = [(["."], message("pause_turn", [NS(type="text", text=".")]))] * 6
        client, messages = fake_client(*script)
        code, _, err = call(["fable", "opus", "x"], client=client)
        self.assertEqual(code, 4)
        self.assertEqual(len(messages.calls), 6)
        self.assertIn("still paused", err)

    def test_refusal_exit_3(self):
        details = NS(category="cyber", explanation="Declined for policy reasons.")
        client, _ = fake_client(([], message("refusal", [], stop_details=details)))
        code, _, err = call(["fable", "opus", "x"], client=client)
        self.assertEqual(code, 3)
        self.assertIn("cyber", err)
        self.assertIn("Declined for policy reasons.", err)

    def test_refusal_json(self):
        details = {"category": "bio", "explanation": "nope"}
        client, _ = fake_client(([], message("refusal", [], stop_details=details)))
        code, out, _ = call(["fable", "opus", "x", "--json"], client=client)
        self.assertEqual(code, 3)
        self.assertEqual(
            json.loads(out)["stop_details"], {"category": "bio", "explanation": "nope"}
        )

    def test_max_tokens_warns(self):
        client, _ = fake_client((["abc"], message("max_tokens", [NS(type="text", text="abc")])))
        code, _, err = call(["fable", "opus", "x"], client=client)
        self.assertEqual(code, 0)
        self.assertIn("max_tokens", err)

    def test_json_mode(self):
        content = [
            NS(type="advisor_tool_result", tool_use_id="a",
               content=NS(type="advisor_redacted_result", encrypted_content="xyz")),
            NS(type="advisor_tool_result", tool_use_id="b",
               content=NS(type="advisor_tool_result_error", error_code="max_uses_exceeded")),
            NS(type="text", text="Answer"),
        ]  # fmt: skip
        client, _ = fake_client((["Answer"], message("end_turn", content)))
        code, out, _ = call(["fable", "opus", "x", "--json"], client=client)
        self.assertEqual(code, 0)
        data = json.loads(out)
        self.assertEqual(data["text"], "Answer")
        self.assertEqual(
            data["advice"],
            [
                {"type": "advisor_redacted_result", "text": "[encrypted advice]"},
                {"type": "advisor_tool_result_error", "error_code": "max_uses_exceeded"},
            ],
        )
        self.assertEqual(data["executor"], "claude-opus-5-5")
        self.assertTrue(any("not be readable" in w for w in data["warnings"]))

    def test_bad_request_error_mapped(self):
        class APIError(Exception):
            def __init__(self, message, status_code=400):
                super().__init__(message)
                self.message = message
                self.status_code = status_code

        class BadRequestError(APIError):
            pass

        class RateLimitError(APIError):
            pass

        class APIConnectionError(Exception):
            pass

        fake_sdk = NS(
            BadRequestError=BadRequestError,
            RateLimitError=RateLimitError,
            APIStatusError=APIError,
            APIConnectionError=APIConnectionError,
        )

        class Boom:
            def stream(self, **kwargs):
                raise BadRequestError("advisor model cannot advise this executor")

        out, err = io.StringIO(), io.StringIO()
        code = run.main(
            ["fable", "opus", "x"],
            client=NS(beta=NS(messages=Boom())),
            anthropic_mod=fake_sdk,
            stdin=io.StringIO(),
            stdout=out,
            stderr=err,
        )
        self.assertEqual(code, 1)
        self.assertIn("advisor model cannot advise this executor", err.getvalue())
        self.assertIn("pairing", err.getvalue())


class SummaryTest(unittest.TestCase):
    def test_usage_arithmetic(self):
        catalog = run.am.load_catalog()
        finals = [
            message("pause_turn", [], [it("message", 1000, 100, cread=50, cwrite=20)]),
            message(
                "end_turn",
                [],
                [
                    it("advisor_message", 2000, 1500, cread=300, model="claude-fable-5-1"),
                    it("message", 3000, 400),
                ],
            ),
        ]
        s = run.summarize(finals, catalog, "claude-fable-5-1", "claude-opus-5-5")
        exe, adv = s["usage"]["executor"], s["usage"]["advisor"]
        self.assertEqual(
            exe,
            {"input_tokens": 4000, "output_tokens": 500, "cache_read_tokens": 50,
             "cache_write_tokens": 20},
        )  # fmt: skip
        self.assertEqual(adv["model"], "claude-fable-5-1")
        self.assertEqual((adv["input_tokens"], adv["output_tokens"]), (2000, 1500))
        self.assertEqual(adv["cache_read_tokens"], 300)
        # Opus 5.5: $4 in / $20 out per MTok; Fable 5.1: $10 in / $50 out per MTok
        cost = s["approx_cost_usd"]
        self.assertAlmostEqual(cost["executor"], (4000 * 4 + 500 * 20) / 1e6)
        self.assertAlmostEqual(cost["advisor"], (2000 * 10 + 1500 * 50) / 1e6)
        self.assertAlmostEqual(cost["total"], cost["executor"] + cost["advisor"])
        self.assertIn("approximate", cost["note"])
        self.assertEqual(s["continuations"], 1)
        self.assertEqual(s["stop_reason"], "end_turn")
        text = run.format_summary(s)
        self.assertIn("approximate", text)
        self.assertIn("advisor claude-fable-5-1", text)

    def test_no_iterations_uses_top_level(self):
        final = NS(
            stop_reason="end_turn",
            content=[],
            usage=NS(input_tokens=10, output_tokens=5, cache_read_input_tokens=None),
        )
        catalog = run.am.load_catalog()
        s = run.summarize([final], catalog, "claude-fable-5-1", "claude-mythos-5")
        self.assertEqual(s["usage"]["executor"]["input_tokens"], 10)
        self.assertIsNone(s["approx_cost_usd"]["executor"])  # Mythos 5 has no list price
        self.assertIsNone(s["approx_cost_usd"]["total"])


if __name__ == "__main__":
    unittest.main()
