import re
import unittest
from pathlib import Path

from tool_gateway.tools import ShellExecutionAdapter, WriteFileTool


class ToolThemeContractTests(unittest.TestCase):
    def test_tool_theme_file_exists_and_has_required_sections(self):
        theme = Path(__file__).resolve().parent.parent / "tool_gateway" / "tools" / "TOOL_THEME.md"
        self.assertTrue(theme.exists())
        text = theme.read_text(encoding="utf-8")
        for section in (
            "## Naming",
            "## Input Schema",
            "## Result Contract",
            "## Error And Warning Style",
            "## Workspace Safety",
            "## Examples",
        ):
            self.assertIn(section, text)

    def test_tool_names_follow_snake_case(self):
        for tool in (ShellExecutionAdapter(), WriteFileTool()):
            self.assertRegex(tool.name, r"^[a-z][a-z0-9_]*$")


if __name__ == "__main__":
    unittest.main()
