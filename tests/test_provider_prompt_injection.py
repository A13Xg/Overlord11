import json
import unittest

from backend.core.provider_runtime import ProviderRuntime


class _CaptureRuntime(ProviderRuntime):
    def __init__(self, config):
        super().__init__(config)
        self.last_payload = None

    def _request_json(self, req):  # type: ignore[override]
        self.last_payload = json.loads(req.data.decode("utf-8"))
        # Minimal compatible response shape for openai call path.
        return {"choices": [{"message": {"content": "ok"}}]}


class ProviderPromptInjectionTests(unittest.TestCase):
    def test_openai_system_prompt_is_injected(self):
        cfg = {
            "providers": {
                "active": "openai",
                "openai": {
                    "model": "gpt-4o-mini",
                    "api_key_env": "OPENAI_API_KEY",
                    "api_base": "https://api.openai.com/v1",
                },
            }
        }
        import os
        os.environ["OPENAI_API_KEY"] = "fake"
        rt = _CaptureRuntime(cfg)
        rt.execute_prompt_with_selection("openai", "gpt-4o-mini", "user-msg", system_prompt="sys-msg")
        self.assertIsNotNone(rt.last_payload)
        messages = rt.last_payload.get("messages", [])
        self.assertGreaterEqual(len(messages), 2)
        self.assertEqual(messages[0]["role"], "system")
        self.assertEqual(messages[0]["content"], "sys-msg")


if __name__ == "__main__":
    unittest.main()

