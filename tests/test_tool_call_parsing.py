import unittest

from engine.tool_executor import extract_tool_calls


class ToolCallParsingTests(unittest.TestCase):
    def test_tool_code_function_style_is_parsed(self):
        text = "TOOL_CODE: list_directory(path='.')"
        calls = extract_tool_calls(text)
        self.assertEqual(len(calls), 1)
        self.assertEqual(calls[0].tool_name, "list_directory")
        self.assertEqual(calls[0].params.get("path"), ".")

    def test_json_array_block_is_parsed_into_multiple_calls(self):
        text = """```json
[
  {"tool":"write_file","params":{"path":"scratch/a.txt","content":"a"}},
  {"tool":"run_shell_command","params":{"command":"echo ok"}}
]
```"""
        calls = extract_tool_calls(text)
        self.assertEqual(len(calls), 2)
        self.assertEqual(calls[0].tool_name, "write_file")
        self.assertEqual(calls[1].tool_name, "run_shell_command")


if __name__ == "__main__":
    unittest.main()

