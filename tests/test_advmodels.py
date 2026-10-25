"""Tests for skills/adv/scripts/advmodels.py (stdlib unittest, no network)."""

from __future__ import annotations

import sys
import unittest
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace

SCRIPTS = Path(__file__).resolve().parent.parent / "skills" / "adv" / "scripts"
sys.path.insert(0, str(SCRIPTS))

import advmodels as am  # noqa: E402

CATALOG = am.load_catalog()


class ParseSpecTest(unittest.TestCase):
    VALID = {
        "fable": ("fable", None, None, False),
        "Fable": ("fable", None, None, False),
        "OPUS": ("opus", None, None, False),
        "claude-opus": ("opus", None, None, False),
        "mythos": ("mythos", None, None, False),
        "haiku": ("haiku", None, None, False),
        "opus-5.5": ("opus", 5, 5, False),
        "opus5.5": ("opus", 5, 5, False),
        "opus-5-5": ("opus", 5, 5, False),
        "claude-opus-5-5": ("opus", 5, 5, False),
        "Claude-Sonnet-4-6": ("sonnet", 4, 6, False),
        "opus-5": ("opus", 5, None, False),
        "opus5": ("opus", 5, None, False),
        "opus-4.8": ("opus", 4, 8, False),
        "opus_4_8": ("opus", 4, 8, False),
        "sonnet[1m]": ("sonnet", None, None, True),
        "claude-opus-5-5[1m]": ("opus", 5, 5, True),
        "OPUS[1M]": ("opus", None, None, True),
        "haiku-4.5": ("haiku", 4, 5, False),
    }
    INVALID = [
        "",
        "gpt-4",
        "claude",
        "claude-3-7-sonnet",
        "claude-3-7-sonnet-20250219",
        "claude-sonnet-4-20250514",
        "claude-opus-4-1-20250805",
        "opus-",
        "opus 5",
        "opus-5.5.1",
        "opus[2m]",
        "opusx",
        "best",
        "off",
        "status",
        "anthropic.claude-opus-5-5",
    ]

    def test_valid(self):
        for token, (family, major, minor, one_m) in self.VALID.items():
            with self.subTest(token=token):
                spec = am.parse_spec(token)
                self.assertEqual(
                    (spec.family, spec.major, spec.minor, spec.one_m), (family, major, minor, one_m)
                )
                self.assertEqual(spec.raw, token)

    def test_invalid(self):
        for token in self.INVALID:
            with self.subTest(token=token):
                with self.assertRaises(ValueError):
                    am.parse_spec(token)
                self.assertFalse(am.is_model_spec(token))


class ResolveTest(unittest.TestCase):
    def test_family_latest(self):
        for family, model_id in CATALOG["latest"].items():
            with self.subTest(family=family):
                self.assertEqual(am.resolve(am.parse_spec(family), CATALOG)["id"], model_id)

    def test_fable_opus(self):
        self.assertEqual(am.resolve(am.parse_spec("Fable"), CATALOG)["id"], "claude-fable-5-1")
        self.assertEqual(am.resolve(am.parse_spec("Opus"), CATALOG)["id"], "claude-opus-5-5")

    def test_versioned(self):
        cases = {
            "opus-4.8": "claude-opus-4-8",
            "opus-5": "claude-opus-5",
            "opus-5.0": "claude-opus-5",
            "claude-sonnet-4-6": "claude-sonnet-4-6",
            "haiku_4_5": "claude-haiku-4-5",
            "fable-5": "claude-fable-5",
        }
        for token, model_id in cases.items():
            with self.subTest(token=token):
                self.assertEqual(am.resolve(am.parse_spec(token), CATALOG)["id"], model_id)

    def test_every_catalog_id_resolves_to_itself(self):
        for model in CATALOG["models"]:
            with self.subTest(model=model["id"]):
                self.assertIs(am.resolve(am.parse_spec(model["id"]), CATALOG), model)

    def test_unknown(self):
        for token in ("opus-4.5", "sonnet-9", "fable-6.2", "haiku-3"):
            with self.subTest(token=token):
                with self.assertRaises(LookupError):
                    am.resolve(am.parse_spec(token), CATALOG)

    def test_live_versioned_unknown_to_catalog(self):
        model = am.resolve(am.parse_spec("opus-5.7"), CATALOG, live_ids=["claude-opus-5-7"])
        self.assertEqual(model["id"], "claude-opus-5-7")
        self.assertIsNone(model["rank"])
        self.assertEqual(model["display"], "Claude Opus 5.7")

    def test_live_family_newer_wins(self):
        live = ["claude-opus-5-5", "claude-opus-6", "claude-sonnet-5-5"]
        self.assertEqual(am.resolve(am.parse_spec("opus"), CATALOG, live)["id"], "claude-opus-6")
        self.assertEqual(
            am.resolve(am.parse_spec("sonnet"), CATALOG, live)["id"], "claude-sonnet-5-5"
        )

    def test_live_family_older_does_not_win(self):
        live = ["claude-opus-4-8"]
        self.assertEqual(am.resolve(am.parse_spec("opus"), CATALOG, live)["id"], "claude-opus-5-5")


class CheckPairTest(unittest.TestCase):
    def test_api_ranks_reproduce_docs_pairing_table(self):
        table = CATALOG["pairing_table"]
        ids = [m["id"] for m in CATALOG["models"]]
        self.assertEqual(set(table), set(ids))
        for executor in ids:
            for advisor in ids:
                with self.subTest(executor=executor, advisor=advisor):
                    ok, reason = am.check_pair(advisor, executor, CATALOG, "api")
                    self.assertEqual(ok, advisor in table[executor], reason)

    def test_claude_code_ranks_differ_only_for_fable5_mythos5_with_opus5(self):
        ids = [m["id"] for m in CATALOG["models"]]
        expected = {
            (e, a)
            for e in ("claude-fable-5", "claude-mythos-5")
            for a in ("claude-opus-5", "claude-opus-5-5")
        }
        diffs = set()
        for executor in ids:
            for advisor in ids:
                api = am.check_pair(advisor, executor, CATALOG, "api")[0]
                cc = am.check_pair(advisor, executor, CATALOG, "claude_code")[0]
                if api != cc:
                    diffs.add((executor, advisor))
                    self.assertTrue(api)
        self.assertEqual(diffs, expected)

    def test_reasons(self):
        ok, reason = am.check_pair("claude-fable-5-1", "claude-opus-5-5", CATALOG)
        self.assertTrue(ok)
        self.assertIn("can advise", reason)
        ok, reason = am.check_pair("claude-opus-5-5", "claude-fable-5-1", CATALOG)
        self.assertFalse(ok)
        self.assertIn("at least as capable", reason)
        ok, reason = am.check_pair("claude-haiku-4-5", "claude-haiku-4-5", CATALOG)
        self.assertFalse(ok)
        self.assertIn("Sonnet 4.6", reason)

    def test_unknown_rank_is_ok_but_unchecked(self):
        ok, reason = am.check_pair("claude-opus-6", "claude-opus-5-5", CATALOG)
        self.assertTrue(ok)
        self.assertIn("cannot be checked offline", reason)

    def test_claude_code_alias_spelling(self):
        self.assertEqual(
            am.check_pair("claude-opus-5-5", "claude-fable-5", CATALOG, "claude-code")[0], False
        )
        with self.assertRaises(ValueError):
            am.check_pair("claude-opus-5-5", "claude-opus-5-5", CATALOG, "bogus")

    def test_valid_advisors(self):
        self.assertEqual(
            sorted(am.valid_advisors("claude-fable-5-1", CATALOG)),
            ["claude-fable-5-1", "claude-mythos-5-1"],
        )


class ClaudeCodeArgTest(unittest.TestCase):
    def arg(self, token, role):
        spec = am.parse_spec(token)
        return am.claude_code_arg(spec, am.resolve(spec, CATALOG), role)

    def test_cases(self):
        cases = [
            ("fable", "advisor", "fable"),
            ("fable", "executor", "fable"),
            ("Opus", "advisor", "opus"),
            ("sonnet", "executor", "sonnet"),
            ("haiku", "executor", "haiku"),
            ("haiku", "advisor", "claude-haiku-5-5"),
            ("mythos", "advisor", "claude-mythos-5-1"),
            ("mythos", "executor", "claude-mythos-5-1"),
            ("opus-4.8", "advisor", "claude-opus-4-8"),
            ("opus-5.5", "executor", "claude-opus-5-5"),
            ("opus[1m]", "executor", "opus[1m]"),
            ("opus[1m]", "advisor", "opus"),
            ("claude-sonnet-4-6[1m]", "executor", "claude-sonnet-4-6[1m]"),
            ("claude-sonnet-4-6[1m]", "advisor", "claude-sonnet-4-6"),
            ("haiku[1m]", "advisor", "claude-haiku-5-5"),
        ]
        for token, role, expected in cases:
            with self.subTest(token=token, role=role):
                self.assertEqual(self.arg(token, role), expected)

    def test_bad_role(self):
        spec = am.parse_spec("opus")
        with self.assertRaises(ValueError):
            am.claude_code_arg(spec, am.resolve(spec, CATALOG), "main")


class LatestFromLiveTest(unittest.TestCase):
    def rows(self):
        return [
            {"id": "claude-opus-5-5", "line": "opus", "lifecycle": "active",
             "created_at": "2026-09-01T00:00:00Z"},
            {"id": "claude-opus-5", "line": "opus", "lifecycle": "active",
             "created_at": "2026-05-01T00:00:00Z"},
            {"id": "claude-opus-4-8", "line": "opus", "lifecycle": "active",
             "created_at": "2026-03-01T00:00:00Z"},
            {"id": "claude-sonnet-5-5", "line": "sonnet", "lifecycle": "active",
             "created_at": "2026-09-01T00:00:00Z"},
            {"id": "claude-sonnet-4-5-20250929", "line": "sonnet", "lifecycle": "deprecated",
             "created_at": "2025-09-29T00:00:00Z"},
            {"id": "claude-mythos-5-1", "line": "mythos", "lifecycle": "active",
             "created_at": "2026-10-01T00:00:00Z"},
        ]  # fmt: skip

    def test_newer_id_wins(self):
        rows = self.rows() + [
            {"id": "claude-opus-6", "line": "opus", "lifecycle": "active",
             "created_at": "2026-10-20T00:00:00Z"}
        ]  # fmt: skip
        self.assertEqual(am.latest_from_live(rows, "opus"), "claude-opus-6")

    def test_version_beats_created_at(self):
        rows = [
            {"id": "claude-opus-5-5", "line": "opus", "lifecycle": "active",
             "created_at": "2026-01-01T00:00:00Z"},
            {"id": "claude-opus-5", "line": "opus", "lifecycle": "active",
             "created_at": "2026-12-01T00:00:00Z"},
        ]  # fmt: skip
        self.assertEqual(am.latest_from_live(rows, "opus"), "claude-opus-5-5")

    def test_created_at_breaks_ties(self):
        rows = [
            {"id": "claude-haiku-4-5-20251001", "line": "haiku", "lifecycle": "active",
             "created_at": "2025-10-01T00:00:00Z"},
            {"id": "claude-haiku-4-5-20260101", "line": "haiku", "lifecycle": "active",
             "created_at": datetime(2026, 1, 1, tzinfo=timezone.utc)},
        ]  # fmt: skip
        self.assertEqual(am.latest_from_live(rows, "haiku"), "claude-haiku-4-5-20260101")

    def test_deprecated_skipped_when_active_exists(self):
        rows = [
            {"id": "claude-sonnet-5", "line": "sonnet", "lifecycle": "active"},
            {"id": "claude-sonnet-6", "line": "sonnet", "lifecycle": "deprecated"},
            {"id": "claude-sonnet-7", "line": "sonnet", "lifecycle": "retired"},
        ]
        self.assertEqual(am.latest_from_live(rows, "sonnet"), "claude-sonnet-5")

    def test_deprecated_used_only_when_nothing_active(self):
        rows = [
            {"id": "claude-sonnet-4-5-20250929", "line": "sonnet", "lifecycle": "deprecated"},
            {"id": "claude-sonnet-9", "line": "sonnet", "lifecycle": "retired"},
        ]
        self.assertEqual(am.latest_from_live(rows, "sonnet"), "claude-sonnet-4-5-20250929")
        self.assertIsNone(am.latest_from_live(rows[1:], "sonnet"))

    def test_mythos_not_auto_picked(self):
        rows = self.rows() + [
            # a mislabelled row must still never be picked for another family
            {"id": "claude-mythos-9", "line": "fable", "lifecycle": "active"},
            {"id": "claude-fable-5-1", "line": "fable", "lifecycle": "active"},
        ]
        self.assertEqual(am.latest_from_live(rows, "fable"), "claude-fable-5-1")
        self.assertEqual(am.latest_from_live(rows, "mythos"), "claude-mythos-5-1")
        self.assertEqual(am.latest_from_live(rows, "opus"), "claude-opus-5-5")

    def test_line_missing_falls_back_to_id(self):
        rows = [
            SimpleNamespace(id="claude-opus-5-5", line=None, lifecycle="active", created_at=None),
            SimpleNamespace(id="claude-opus-5-7", lifecycle="active", created_at=None),
            SimpleNamespace(id="claude-mythos-preview", line=None, lifecycle="active"),
        ]
        self.assertEqual(am.latest_from_live(rows, "opus"), "claude-opus-5-7")
        self.assertIsNone(am.latest_from_live(rows, "haiku"))

    def test_live_ids_from_models(self):
        ids = am.live_ids_from_models(self.rows())
        self.assertIn("claude-opus-5-5", ids)
        self.assertNotIn("claude-sonnet-4-5-20250929", ids)
        self.assertIn("claude-mythos-5-1", ids)


class DescribeTest(unittest.TestCase):
    def test_describe(self):
        model = am.find_model("claude-opus-5-5", CATALOG)
        self.assertEqual(am.describe(model), "Claude Opus 5.5 (claude-opus-5-5)")

    def test_advice_format(self):
        self.assertEqual(am.advice_format(am.find_model("claude-fable-5-1", CATALOG)), "encrypted")
        self.assertEqual(am.advice_format(am.find_model("claude-opus-4-8", CATALOG)), "plaintext")
        self.assertEqual(am.advice_format(am.find_model("claude-haiku-4-5", CATALOG)), "none")
        self.assertIn("not be readable", am.advice_note(am.find_model("claude-opus-5", CATALOG)))

    def test_tool_definition(self):
        tool = am.tool_definition(
            "claude-opus-5-5", CATALOG, max_uses=3, max_tokens=2048, caching="1h"
        )
        self.assertEqual(
            tool,
            {
                "type": "advisor_20260301",
                "name": "advisor",
                "model": "claude-opus-5-5",
                "max_uses": 3,
                "max_tokens": 2048,
                "caching": {"type": "ephemeral", "ttl": "1h"},
            },
        )

    def test_parse_model_id(self):
        self.assertEqual(am.parse_model_id("claude-3-7-sonnet-20250219"), ("sonnet", 3, 7))
        self.assertEqual(am.parse_model_id("claude-opus-4-20250514"), ("opus", 4, 0))
        self.assertEqual(am.parse_model_id("claude-fable-5-1"), ("fable", 5, 1))
        self.assertIsNone(am.parse_model_id("claude-mythos-preview"))
        self.assertIsNone(am.parse_model_id("claude-2.1"))


if __name__ == "__main__":
    unittest.main()
