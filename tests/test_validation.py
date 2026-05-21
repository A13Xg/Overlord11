import unittest

from tool_gateway.executor import ToolGateway
from tool_gateway.registry import ToolRegistry
from tool_gateway.tools import ShellExecutionAdapter, WriteFileTool


class ValidationTests(unittest.TestCase):
    def setUp(self):
        reg = ToolRegistry()
        reg.register_tool(ShellExecutionAdapter())
        reg.register_tool(WriteFileTool())
        self.gw = ToolGateway(reg)

    def test_valid_call_succeeds(self):
        res = self.gw.validate_tool_call("run_command", {"command": "python --version"})
        self.assertTrue(res["ok"])

    def test_missing_required_fails(self):
        res = self.gw.validate_tool_call("run_command", {"timeout_seconds": 10})
        self.assertFalse(res["ok"])
        self.assertEqual(res["errors"][0]["code"], "VALIDATION_ERROR")

    def test_unknown_param_fails(self):
        res = self.gw.validate_tool_call("run_command", {"command": "echo ok", "bad_field": True})
        self.assertFalse(res["ok"])

    def test_wrong_type_fails(self):
        res = self.gw.validate_tool_call("run_command", {"command": "echo ok", "timeout_seconds": "30"})
        self.assertFalse(res["ok"])

    def test_alias_normalization_works(self):
        res = self.gw.validate_tool_call("run_command", {"cmd": "echo ok", "timeout": 1})
        self.assertTrue(res["ok"])
        self.assertGreaterEqual(len(res["warnings"]), 1)

    def test_ambiguous_alias_not_guessed(self):
        res = self.gw.validate_tool_call("run_command", {"commandx": "echo ok"})
        self.assertFalse(res["ok"])

    def test_json_parse_error(self):
        res = self.gw.execute_tool_call('{"tool_name": "run_command", "arguments": }')
        self.assertFalse(res["ok"])
        self.assertEqual(res["errors"][0]["code"], "PARSE_ERROR")

    def test_shell_auto_string_validates(self):
        res = self.gw.validate_tool_call("run_command", {"command": "python --version", "shell": "auto"})
        self.assertTrue(res["ok"])

    def test_shell_uppercase_normalizes(self):
        res = self.gw.validate_tool_call("run_command", {"command": "python --version", "shell": "AUTO"})
        self.assertTrue(res["ok"])

    def test_invalid_shell_has_allowed_values_and_retry_hint(self):
        res = self.gw.execute_tool_call(
            {"tool_name": "run_command", "arguments": {"command": "python --version", "shell": "pwsh"}},
            session_id="sess-1",
        )
        self.assertFalse(res["ok"])
        self.assertEqual(res["errors"][0]["code"], "VALIDATION_ERROR")
        self.assertIn("allowed_values", res["errors"][0]["details"])
        self.assertIn("omit shell", res["metadata"].get("retry_hint", ""))
        self.assertEqual(res["metadata"].get("validation_error_field"), "shell")

    def test_write_file_file_path_alias_normalizes(self):
        res = self.gw.validate_tool_call("write_file", {"file_path": "answer.md", "content": "ok"})
        self.assertTrue(res["ok"])
        self.assertGreaterEqual(len(res["warnings"]), 1)

    def test_write_file_unknown_encoding_field_fails_with_allowed_keys(self):
        res = self.gw.validate_tool_call("write_file", {"path": "answer.md", "content": "ok", "encoding": "utf-8"})
        self.assertFalse(res["ok"])
        self.assertEqual(res["errors"][0]["code"], "VALIDATION_ERROR")
        self.assertIn("allowed_keys", res["errors"][0]["details"])

    def test_validation_retry_count_by_field_is_reported(self):
        res1 = self.gw.execute_tool_call(
            {"tool_name": "write_file", "arguments": {"content": "missing-path"}},
            session_id="sess-2",
        )
        res2 = self.gw.execute_tool_call(
            {"tool_name": "write_file", "arguments": {"content": "missing-path-again"}},
            session_id="sess-2",
        )
        self.assertFalse(res1["ok"])
        self.assertFalse(res2["ok"])
        self.assertEqual(res2["metadata"].get("validation_error_field"), "path")
        by_field = res2["metadata"].get("retry_validation_error_count_by_field", {})
        self.assertGreaterEqual(int(by_field.get("path", 0)), 2)


if __name__ == "__main__":
    unittest.main()
