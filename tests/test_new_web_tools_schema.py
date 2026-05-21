import unittest

from tool_gateway.executor import ToolGateway
from tool_gateway.registry import ToolRegistry
from tool_gateway.tools import (
    DynamicBrowserTool,
    IntelligentThemeScraperTool,
    RssReadTool,
    SearchAndExtractPipelineTool,
    SemanticContentExtractorTool,
    WebCodeScraperTool,
    WebExtractImagesTool,
    WebExtractTextTool,
    WebFetchTool,
    WebImageGrabberTool,
    WebSearchTool,
)


class NewWebToolsSchemaTests(unittest.TestCase):
    def setUp(self):
        reg = ToolRegistry()
        for tool in (
            WebSearchTool(),
            WebFetchTool(),
            WebExtractTextTool(),
            WebExtractImagesTool(),
            WebImageGrabberTool(),
            RssReadTool(),
            DynamicBrowserTool(),
            IntelligentThemeScraperTool(),
            WebCodeScraperTool(),
            SemanticContentExtractorTool(),
            SearchAndExtractPipelineTool(),
        ):
            reg.register_tool(tool)
        self.gw = ToolGateway(reg)

    def test_validate_all_new_tools_minimal_payloads(self):
        payloads = [
            ("web_search", {"query": "python"}),
            ("web_fetch", {"url": "https://example.com"}),
            ("web_extract_text", {"raw_text": "hello"}),
            ("web_extract_images", {"url": "https://example.com"}),
            ("web_image_grabber", {"query": "mountain"}),
            ("rss_read", {"feed_urls": ["https://example.com/feed.xml"]}),
            ("dynamic_browser", {"url": "https://example.com"}),
            ("intelligent_theme_scraper", {"url": "https://example.com"}),
            ("web_code_scraper", {"url": "https://example.com"}),
            ("semantic_content_extractor", {"raw_text": "Contact us at support@example.com"}),
            ("search_and_extract_pipeline", {"topics": ["python packaging"]}),
        ]
        for tool_name, arguments in payloads:
            res = self.gw.validate_tool_call(tool_name, arguments)
            self.assertTrue(res["ok"], f"validation failed for {tool_name}: {res}")

    def test_alias_normalization_for_new_tools(self):
        res = self.gw.validate_tool_call("dynamic_browser", {"url": "https://example.com", "selector": "main", "timeout": 15})
        self.assertTrue(res["ok"])
        self.assertGreaterEqual(len(res["warnings"]), 1)

        res = self.gw.validate_tool_call("rss_read", {"url": ["https://example.com/feed.xml"], "limit": 5})
        self.assertTrue(res["ok"])
        self.assertGreaterEqual(len(res["warnings"]), 1)


if __name__ == "__main__":
    unittest.main()
