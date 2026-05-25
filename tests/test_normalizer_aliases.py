import unittest

from tool_gateway.executor import ToolGateway
from tool_gateway.normalizer import normalize_arguments
from tool_gateway.registry import ToolRegistry
from tool_gateway.tools import DynamicBrowserTool, WebSearchTool


class NormalizerAliasTests(unittest.TestCase):
    def setUp(self):
        reg = ToolRegistry()
        reg.register_tool(WebSearchTool())
        reg.register_tool(DynamicBrowserTool())
        self.gw = ToolGateway(reg)

    def test_web_search_mode_alias_normalizes(self):
        res = self.gw.validate_tool_call(
            "web_search",
            {"query": "python", "mode": "text", "max_results": 3},
        )
        self.assertTrue(res["ok"])
        self.assertGreaterEqual(len(res.get("warnings", [])), 1)

    def test_dynamic_browser_action_alias_normalizes(self):
        res = self.gw.validate_tool_call(
            "dynamic_browser",
            {"url": "https://example.com", "action": "render"},
        )
        self.assertTrue(res["ok"])
        self.assertGreaterEqual(len(res.get("warnings", [])), 1)

    def test_html_report_style_value_in_theme_moves_to_style_id(self):
        args, warnings, _meta = normalize_arguments(
            "html_report_generator",
            {"title": "T", "content": "C", "theme": "minimal-zen"},
        )
        self.assertEqual(args["theme"], "dark")
        self.assertEqual(args["style_id"], "minimal-zen")
        self.assertGreaterEqual(len(warnings), 1)


if __name__ == "__main__":
    unittest.main()
