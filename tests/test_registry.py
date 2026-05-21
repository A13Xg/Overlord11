import unittest

from tool_gateway.registry import ToolRegistry
from tool_gateway.tools import ShellExecutionAdapter, WebSearchTool, WriteFileTool


class RegistryTests(unittest.TestCase):
    def test_registration_and_listing(self):
        r = ToolRegistry()
        r.register_tool(ShellExecutionAdapter())
        r.register_tool(WriteFileTool())
        r.register_tool(WebSearchTool())
        tools = r.list_tools()
        names = {t["name"] for t in tools}
        self.assertIn("run_command", names)
        self.assertIn("write_file", names)
        self.assertIn("web_search", names)

    def test_duplicate_registration_rejected(self):
        r = ToolRegistry()
        r.register_tool(ShellExecutionAdapter())
        with self.assertRaises(ValueError):
            r.register_tool(ShellExecutionAdapter())

    def test_unknown_tool_rejected(self):
        r = ToolRegistry()
        r.register_tool(ShellExecutionAdapter())
        with self.assertRaises(Exception):
            r.get_tool("missing_tool")


if __name__ == "__main__":
    unittest.main()
