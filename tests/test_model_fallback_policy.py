import unittest
import os

from engine.orchestrator_bridge import OrchestratorBridge


class ModelFallbackPolicyTests(unittest.TestCase):
    def _bridge(self):
        OrchestratorBridge._GLOBAL_STICKY_PROVIDER = ""
        OrchestratorBridge._GLOBAL_STICKY_MODEL_BY_PROVIDER = {}
        OrchestratorBridge._GLOBAL_SUPPORTED_MODELS_BY_PROVIDER = {}
        cfg = {
            "providers": {
                "active": "gemini",
                "gemini": {
                    "model": "gemini-2.5-flash",
                    "api_key_env": "GOOGLE_GEMINI_API_KEY",
                    "available_models": {
                        "gemini-2.5-flash": "selected",
                        "gemini-2.5-pro": "high capability",
                        "gemini-2.5-flash-lite": "cheaper",
                        "gemma-3-27b-it": "high RPD lower TPM",
                    },
                },
            },
            "orchestration": {
                "model_fallback_policy": {
                    "competency_weight": 0.6,
                    "quota_weight": 0.3,
                    "health_weight": 0.1,
                }
            },
        }
        return OrchestratorBridge(cfg)

    def test_selected_model_is_always_first(self):
        bridge = self._bridge()
        order = bridge._get_model_fallback_order(
            "gemini",
            bridge._providers["gemini"],
            messages=[{"role": "user", "content": "hello"}],
            system="",
        )
        self.assertGreaterEqual(len(order), 1)
        self.assertEqual(order[0], "gemini-2.5-flash")

    def test_long_prompt_penalizes_low_tpm_models(self):
        bridge = self._bridge()
        very_long = "token " * 60000  # large enough to pressure low TPM options
        order = bridge._get_model_fallback_order(
            "gemini",
            bridge._providers["gemini"],
            messages=[{"role": "user", "content": very_long}],
            system="",
        )
        # Selected model remains first by contract.
        self.assertEqual(order[0], "gemini-2.5-flash")
        # For long prompts, gemma (15k TPM heuristic) should rank after flash-lite/pro.
        self.assertGreater(order.index("gemma-3-27b-it"), order.index("gemini-2.5-flash-lite"))
        self.assertGreater(order.index("gemma-3-27b-it"), order.index("gemini-2.5-pro"))

    def test_competency_drives_order_for_short_prompts(self):
        bridge = self._bridge()
        order = bridge._get_model_fallback_order(
            "gemini",
            bridge._providers["gemini"],
            messages=[{"role": "user", "content": "small ask"}],
            system="",
        )
        # With low token pressure, higher competency model should lead remaining list.
        self.assertLess(order.index("gemini-2.5-pro"), order.index("gemini-2.5-flash-lite"))

    def test_sticky_model_is_used_first_on_subsequent_runs(self):
        bridge = self._bridge()
        bridge._sticky_model_by_provider["gemini"] = "gemini-2.5-pro"
        order = bridge._get_model_fallback_order(
            "gemini",
            bridge._providers["gemini"],
            messages=[{"role": "user", "content": "small ask"}],
            system="",
        )
        self.assertEqual(order[0], "gemini-2.5-pro")
        self.assertEqual(order[1], "gemini-2.5-flash")

    def test_streaming_uses_same_order_policy(self):
        bridge = self._bridge()
        bridge._provider_diagnostics_done = True
        bridge._provider_availability["gemini"] = True
        os.environ["GOOGLE_GEMINI_API_KEY"] = "fake"

        attempts = []

        def fake_dispatch_streaming(provider, cfg, messages, system, api_key, model, token_cb):
            attempts.append(model)
            raise RuntimeError("forced failure")

        bridge._dispatch_streaming = fake_dispatch_streaming  # type: ignore[method-assign]
        bridge.call_provider = lambda *args, **kwargs: (_ for _ in ()).throw(RuntimeError("forced fallback failure"))  # type: ignore[method-assign]

        with self.assertRaises(RuntimeError):
            bridge.call_provider_streaming(
                messages=[{"role": "user", "content": "x"}],
                system="",
                token_callback=lambda _t: None,
            )
        self.assertGreaterEqual(len(attempts), 1)
        self.assertEqual(attempts[0], "gemini-2.5-flash")


if __name__ == "__main__":
    unittest.main()
