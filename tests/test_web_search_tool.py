import unittest
from unittest.mock import patch

from tool_gateway.executor import ToolGateway
from tool_gateway.registry import ToolRegistry
from tool_gateway.tools import WebSearchTool


class _FakeDDGS:
    fail_count = 0

    def __init__(self, timeout=10):
        self.timeout = timeout

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def text(self, **kwargs):
        if _FakeDDGS.fail_count > 0:
            _FakeDDGS.fail_count -= 1
            raise RuntimeError("transient failure")
        return [
            {"title": "B title", "href": "HTTPS://Example.com/a?b=2&a=1#frag", "body": "beta", "date": "2026-05-20"},
            {"title": "A title", "href": "https://example.com/a?a=1&b=2", "body": "alpha", "date": "2026-05-20"},
            {"title": "C title", "href": "https://blocked.com/x", "body": "blocked"},
        ]

    def news(self, **kwargs):
        return self.text(**kwargs)


class WebSearchToolTests(unittest.TestCase):
    def setUp(self):
        reg = ToolRegistry()
        reg.register_tool(WebSearchTool())
        self.gw = ToolGateway(reg)

    @patch("tool_gateway.tools.web_search.DDGS", _FakeDDGS)
    def test_valid_search_succeeds(self):
        res = self.gw.execute_tool_call({"tool_name": "web_search", "arguments": {"query": "python"}})
        self.assertTrue(res["ok"])
        self.assertEqual(res["tool_name"], "web_search")
        self.assertGreaterEqual(len(res["data"]["results"]), 1)

    def test_missing_query_fails(self):
        res = self.gw.execute_tool_call({"tool_name": "web_search", "arguments": {"max_results": 3}})
        self.assertFalse(res["ok"])
        self.assertEqual(res["errors"][0]["code"], "VALIDATION_ERROR")

    def test_unknown_param_fails(self):
        res = self.gw.validate_tool_call("web_search", {"query": "python", "bad_field": True})
        self.assertFalse(res["ok"])
        self.assertEqual(res["errors"][0]["code"], "VALIDATION_ERROR")
        self.assertIn("allowed_keys", res["errors"][0]["details"])

    def test_alias_normalization_works(self):
        res = self.gw.validate_tool_call("web_search", {"q": "python", "limit": 2, "safesearch": "strict", "type": "news"})
        self.assertTrue(res["ok"])
        self.assertGreaterEqual(len(res["warnings"]), 1)

    def test_allow_and_block_overlap_fails(self):
        res = self.gw.validate_tool_call(
            "web_search",
            {"query": "python", "domain_allowlist": ["example.com"], "domain_blocklist": ["example.com"]},
        )
        self.assertFalse(res["ok"])
        self.assertEqual(res["errors"][0]["code"], "VALIDATION_ERROR")

    def test_allowlist_and_blocklist_can_be_null(self):
        res = self.gw.validate_tool_call(
            "web_search",
            {"query": "python", "domain_allowlist": None, "domain_blocklist": None},
        )
        self.assertTrue(res["ok"])

    @patch("tool_gateway.tools.web_search.DDGS", _FakeDDGS)
    def test_dedup_and_normalized_urls(self):
        res = self.gw.execute_tool_call({"tool_name": "web_search", "arguments": {"query": "python", "max_results": 5}})
        self.assertTrue(res["ok"])
        urls = [x["url"] for x in res["data"]["results"]]
        self.assertEqual(len(urls), len(set(urls)))
        self.assertIn("https://example.com/a?a=1&b=2", urls)

    @patch("tool_gateway.tools.web_search.DDGS", _FakeDDGS)
    def test_domain_filtering(self):
        res = self.gw.execute_tool_call(
            {
                "tool_name": "web_search",
                "arguments": {"query": "python", "domain_blocklist": ["blocked.com"], "max_results": 10},
            }
        )
        self.assertTrue(res["ok"])
        domains = [x["source_domain"] for x in res["data"]["results"]]
        self.assertNotIn("blocked.com", domains)

    @patch("tool_gateway.tools.web_search.DDGS", _FakeDDGS)
    def test_retry_then_success(self):
        _FakeDDGS.fail_count = 1
        res = self.gw.execute_tool_call(
            {"tool_name": "web_search", "arguments": {"query": "python", "include_metadata": True}}
        )
        self.assertTrue(res["ok"])
        self.assertGreaterEqual(res["data"]["metadata"]["attempts"], 2)


if __name__ == "__main__":
    unittest.main()
