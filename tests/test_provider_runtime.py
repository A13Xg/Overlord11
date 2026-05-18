import json
import unittest
from unittest.mock import patch

from backend.core.provider_runtime import ProviderRuntime


class ProviderRuntimeTests(unittest.TestCase):
    def test_unsupported_provider_raises(self):
        runtime = ProviderRuntime({"providers": {"active": "unknown", "unknown": {"model": "x"}}})
        with self.assertRaises(RuntimeError):
            runtime.execute_prompt("hello")

    @patch("backend.core.provider_runtime.ProviderRuntime._request_json")
    def test_openai_response_parsing(self, mock_request_json):
        mock_request_json.return_value = {
            "choices": [{"message": {"content": "Hello world"}}]
        }
        cfg = {
            "providers": {
                "active": "openai",
                "openai": {
                    "model": "gpt-4o",
                    "api_key_env": "OPENAI_API_KEY",
                    "api_base": "https://api.openai.com/v1",
                },
            }
        }
        with patch.dict("os.environ", {"OPENAI_API_KEY": "test-key"}):
            runtime = ProviderRuntime(cfg)
            result = runtime.execute_prompt("say hi")
        self.assertEqual(result.provider, "openai")
        self.assertEqual(result.model, "gpt-4o")
        self.assertEqual(result.output, "Hello world")


if __name__ == "__main__":
    unittest.main()

