"""Smoke test for optional FastAPI example (skipped without fastapi)."""
from __future__ import annotations

import importlib.util
import sys
import unittest
from pathlib import Path


def _load_fastapi_module():
    root = Path(__file__).resolve().parents[1]
    path = root / "examples" / "fastapi_telemetry.py"
    spec = importlib.util.spec_from_file_location("fastapi_telemetry", path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load {path}")
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    return mod


class TestFastAPIExample(unittest.TestCase):
    def test_app_exists_when_fastapi_installed(self):
        try:
            import fastapi  # noqa: F401
        except ImportError:
            self.skipTest("fastapi not installed")
        mod = _load_fastapi_module()
        self.assertTrue(hasattr(mod, "app"))
        self.assertEqual(mod.app.title, "MSFS Telemetry")
        routes = {getattr(r, "path", None) for r in mod.app.routes}
        self.assertIn("/health", routes)
        self.assertIn("/snapshot", routes)
        self.assertIn("/stream", routes)


if __name__ == "__main__":
    unittest.main()
