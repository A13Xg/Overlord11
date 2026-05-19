import unittest

from backend.core.engine_bridge import EngineBridge


class ModelFallbackPolicyTests(unittest.TestCase):
    def test_selected_model_first_then_sticky_then_fallbacks(self):
        available = {
            "gemini-3.1-pro-preview": "pro",
            "gemma-4-31b-it": "gemma",
            "gemini-2.5-flash": "flash",
            "gemma-3-27b-it": "gemma3",
        }
        fallback = [
            "gemma-4-31b-it",
            "gemma-3-27b-it",
            "gemini-2.5-flash",
        ]
        out = EngineBridge._build_model_candidates(
            selected_model="gemini-3.1-pro-preview",
            available_models=available,
            fallback_models=fallback,
            last_working_model="gemini-2.5-flash",
        )
        self.assertEqual(out[0], "gemini-3.1-pro-preview")
        self.assertEqual(out[1], "gemini-2.5-flash")
        self.assertEqual(len(out), len(set(out)))

    def test_invalid_fallback_models_are_ignored(self):
        available = {"gpt-4o": "primary", "gpt-4o-mini": "mini"}
        fallback = ["does-not-exist", "gpt-4o-mini"]
        out = EngineBridge._build_model_candidates(
            selected_model="gpt-4o",
            available_models=available,
            fallback_models=fallback,
            last_working_model="",
        )
        self.assertEqual(out, ["gpt-4o", "gpt-4o-mini"])


if __name__ == "__main__":
    unittest.main()

