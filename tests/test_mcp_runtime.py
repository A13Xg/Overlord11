import unittest
from pathlib import Path

from backend.core.mcp_runtime import McpRuntime


class McpRuntimeTests(unittest.TestCase):
    def setUp(self) -> None:
        self.rt = McpRuntime(Path(".").resolve())

    def test_registry_replace_for_server(self):
        self.rt.registry.replace_for_server(
            "s1",
            [
                {
                    "name": "read_file",
                    "description": "Read",
                    "inputSchema": {"type": "object", "properties": {"path": {"type": "string"}}},
                }
            ],
        )
        self.rt.registry.replace_for_server(
            "s2",
            [
                {
                    "name": "search_content",
                    "description": "Search",
                    "inputSchema": {"type": "object", "properties": {"pattern": {"type": "string"}}},
                }
            ],
        )
        tools = self.rt.tool_catalog()
        names = [t["full_name"] for t in tools]
        self.assertIn("s1.read_file", names)
        self.assertIn("s2.search_content", names)

    def test_schema_validation_required_and_type(self):
        schema = {
            "type": "object",
            "required": ["path"],
            "properties": {
                "path": {"type": "string"},
                "start_line": {"type": "integer"},
            },
        }
        err_missing = self.rt._validate_against_schema(schema, {})
        self.assertIsNotNone(err_missing)
        err_type = self.rt._validate_against_schema(schema, {"path": 123})
        self.assertIsNotNone(err_type)
        ok = self.rt._validate_against_schema(schema, {"path": "a.txt", "start_line": 1})
        self.assertIsNone(ok)

    def test_call_unknown_tool(self):
        out = self.rt.call_tool("unknown.server_tool", {})
        self.assertFalse(out["success"])
        self.assertIn("Unknown MCP tool", out["error"])


if __name__ == "__main__":
    unittest.main()

