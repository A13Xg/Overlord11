import unittest
from unittest.mock import patch

from backend.api import health


class ProviderHealthApiTests(unittest.TestCase):
    def test_health_summary_and_shape(self):
        fake_cfg = {
            "providers": {
                "active": "openai",
                "openai": {"model": "gpt-4o", "available_models": {"gpt-4o": "x"}},
                "gemini": {"model": "gemma-4-31b-it", "available_models": {"gemma-4-31b-it": "x"}},
            }
        }
        fake_results = {
            "openai": {"status": "healthy", "latency_ms": 100, "error": None, "model_count": 20},
            "gemini": {"status": "degraded", "latency_ms": 140, "error": "HTTP 500", "model_count": 5},
        }
        fake_checkers = {
            "openai": lambda _cfg: fake_results["openai"],
            "gemini": lambda _cfg: fake_results["gemini"],
        }
        with patch.object(health, "_load_config", return_value=fake_cfg):
            with patch.dict(health._CHECKERS, fake_checkers, clear=False):
                    out = health._run_health_checks(force=True)
        self.assertIn("openai", out)
        self.assertIn("gemini", out)
        self.assertEqual(out["openai"]["status"], "healthy")
        self.assertEqual(out["gemini"]["status"], "degraded")
        self.assertTrue(out["openai"]["active"])
        self.assertEqual(out["openai"]["model"], "gpt-4o")


if __name__ == "__main__":
    unittest.main()
