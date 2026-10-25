"""hooks/catalog.ts must be in sync with skills/adv/assets/models.json."""

from __future__ import annotations

import contextlib
import importlib.util
import io
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SCRIPT = ROOT / "tools" / "sync_catalog.py"


def load_module():
    spec = importlib.util.spec_from_file_location("sync_catalog", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class SyncCatalogTest(unittest.TestCase):
    def test_check_passes(self):
        module = load_module()
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            code = module.main(["--check"])
        self.assertEqual(code, 0, buf.getvalue())

    def test_render_is_deterministic(self):
        module = load_module()
        import json

        catalog = json.loads(module.SOURCE.read_text(encoding="utf-8"))
        self.assertEqual(module.render(catalog), module.render(catalog))
        self.assertIn("export const CATALOG", module.render(catalog))


if __name__ == "__main__":
    unittest.main()
