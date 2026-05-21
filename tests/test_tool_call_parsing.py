import unittest

from engine.tool_executor import extract_tool_calls


class ToolCallParsingTests(unittest.TestCase):
    def test_canonical_json_block_is_parsed(self):
        text = """```json
{"tool_name":"run_command","arguments":{"command":"python --version","timeout_seconds":30}}
```"""
        calls = extract_tool_calls(text)
        self.assertEqual(len(calls), 1)
        self.assertEqual(calls[0].tool_name, "run_command")
        self.assertEqual(calls[0].params.get("command"), "python --version")

    def test_json_array_block_is_parsed_into_multiple_calls(self):
        text = """```json
[
  {"tool_name":"write_file","arguments":{"path":"answer.md","content":"a"}},
  {"tool_name":"run_command","arguments":{"command":"python --version"}}
]
```"""
        calls = extract_tool_calls(text)
        self.assertEqual(len(calls), 2)
        self.assertEqual(calls[0].tool_name, "write_file")
        self.assertEqual(calls[1].tool_name, "run_command")

    def test_legacy_format_is_ignored(self):
        text = "TOOL_CALL: run_command(command='python --version')"
        calls = extract_tool_calls(text)
        self.assertEqual(calls, [])

    def test_bare_canonical_json_object_is_parsed(self):
        text = "{\"tool_name\":\"run_command\",\"arguments\":{\"command\":\"python --version\"}}"
        calls = extract_tool_calls(text)
        self.assertEqual(len(calls), 1)
        self.assertEqual(calls[0].tool_name, "run_command")

    def test_bare_canonical_json_array_is_parsed(self):
        text = (
            "["
            "{\"tool_name\":\"write_file\",\"arguments\":{\"path\":\"answer.md\",\"content\":\"ok\"}},"
            "{\"tool_name\":\"run_command\",\"arguments\":{\"command\":\"python --version\"}}"
            "]"
        )
        calls = extract_tool_calls(text)
        self.assertEqual(len(calls), 2)
        self.assertEqual(calls[0].tool_name, "write_file")
        self.assertEqual(calls[1].tool_name, "run_command")


if __name__ == "__main__":
    unittest.main()

