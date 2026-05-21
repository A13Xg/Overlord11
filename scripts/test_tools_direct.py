"""
Direct tool-gateway smoke test for all 13 registered tools.
Run: python scripts/test_tools_direct.py

Exits with code 0 if all tests pass, 1 if any fail.
Does NOT go through the LLM — calls ToolGateway directly.
"""
from __future__ import annotations

import json
import os
import sys
import tempfile
import traceback
from pathlib import Path

# Ensure project root is on path
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

# Point workspace to a temp dir so tests don't pollute the real workspace
TEMP_WS = tempfile.mkdtemp(prefix="overlord11_tooltest_")
os.environ["OVERLORD11_TASK_DIR"] = TEMP_WS

from tool_gateway.executor import ToolGateway
from tool_gateway.registry import ToolRegistry
from tool_gateway.tools import (
    CalculatorTool,
    DynamicBrowserTool,
    HtmlReportGeneratorTool,
    ImageScraperTool,
    IntelligentThemeScraperTool,
    JsonTransformTool,
    RssReadTool,
    SearchAndExtractPipelineTool,
    SemanticContentExtractorTool,
    ShellExecutionAdapter,
    WebCodeScraperTool,
    WebExtractImagesTool,
    WebExtractTextTool,
    WebFetchTool,
    WebImageGrabberTool,
    WebSearchTool,
    WriteFileTool,
)

# ---------------------------------------------------------------------------
# Setup
# ---------------------------------------------------------------------------

registry = ToolRegistry()
for tool in [
    ShellExecutionAdapter(),
    WriteFileTool(),
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
    CalculatorTool(),
    ImageScraperTool(),
    HtmlReportGeneratorTool(),
    JsonTransformTool(),
]:
    registry.register_tool(tool)

gw = ToolGateway(registry)

passed: list[str] = []
failed: list[tuple[str, str]] = []

RESET = "\033[0m"
GREEN = "\033[92m"
RED   = "\033[91m"
YELLOW = "\033[93m"
BOLD  = "\033[1m"


def run_test(name: str, payload: dict, checks: list[tuple[str, object]] | None = None, allow_partial: bool = False):
    """Run one tool call and check assertions. checks is [(jsonpath_str, expected_value)]."""
    try:
        result = gw.execute_tool_call(payload)
    except Exception as exc:
        failed.append((name, f"execute_tool_call raised: {exc}\n{traceback.format_exc()}"))
        print(f"  {RED}FAIL{RESET} {name}: exception: {exc}")
        return result if "result" in dir() else {}

    ok = result.get("ok", False)
    if not ok and not allow_partial:
        errs = result.get("errors", [])
        err_str = "; ".join(e.get("message", str(e)) for e in errs) if errs else str(result)
        failed.append((name, err_str))
        print(f"  {RED}FAIL{RESET} {name}: ok=False — {err_str}")
        return result

    for path, expected in (checks or []):
        parts = path.split(".")
        val = result
        for p in parts:
            if isinstance(val, dict):
                val = val.get(p)
            else:
                val = None
                break
        if expected == "_nonempty_":
            if not val:
                msg = f"field '{path}' expected non-empty, got {val!r}"
                if allow_partial:
                    print(f"  {YELLOW}WARN{RESET} {name}: {msg}")
                else:
                    failed.append((name, msg))
                    print(f"  {RED}FAIL{RESET} {name}: {msg}")
                    return result
        elif expected == "_exists_":
            if val is None:
                msg = f"field '{path}' expected to exist"
                failed.append((name, msg))
                print(f"  {RED}FAIL{RESET} {name}: {msg}")
                return result
        elif val != expected:
            msg = f"field '{path}' expected {expected!r}, got {val!r}"
            if allow_partial:
                print(f"  {YELLOW}WARN{RESET} {name}: {msg}")
            else:
                failed.append((name, msg))
                print(f"  {RED}FAIL{RESET} {name}: {msg}")
                return result

    warns = result.get("warnings", [])
    warn_str = f" [{YELLOW}{len(warns)} warn(s){RESET}]" if warns else ""
    print(f"  {GREEN}PASS{RESET} {name}{warn_str}")
    passed.append(name)
    return result


# ---------------------------------------------------------------------------
# PHASE 1 — Offline / minimal-network tests (fast)
# ---------------------------------------------------------------------------

print(f"\n{BOLD}Phase 1 — Offline / internal tests{RESET}")

# --- run_command ---
run_test(
    "run_command::echo",
    {"tool_name": "run_command", "arguments": {"command": "echo hello_from_overlord11", "shell": "auto"}},
    [("data.exit_code", 0), ("data.stdout", "_nonempty_")],
)

run_test(
    "run_command::dry_run",
    {"tool_name": "run_command", "arguments": {"command": "python --version", "dry_run": True}},
    [("data.dry_run", True)],
)

# --- write_file ---
run_test(
    "write_file::simple",
    {"tool_name": "write_file", "arguments": {"path": "test_output.txt", "content": "Hello from tool test!\nLine 2"}},
    [("data.bytes_written", "_nonempty_"), ("ok", True)],
)
# Verify file actually exists in workspace
_written = Path(TEMP_WS) / "test_output.txt"
if _written.exists():
    print(f"  {GREEN}PASS{RESET} write_file::file_exists_on_disk ({_written})")
    passed.append("write_file::file_exists_on_disk")
else:
    failed.append(("write_file::file_exists_on_disk", "file not found at expected path"))
    print(f"  {RED}FAIL{RESET} write_file::file_exists_on_disk — not at {_written}")

# --- write_file alias ---
run_test(
    "write_file::alias_file_path",
    {"tool_name": "write_file", "arguments": {"file_path": "alias_test.txt", "content": "alias works"}},
    [("ok", True)],
)

# --- semantic_content_extractor (offline — raw_text mode) ---
run_test(
    "semantic_content_extractor::raw_text",
    {"tool_name": "semantic_content_extractor", "arguments": {
        "raw_text": "Contact us at support@example.com or call +1-555-123-4567. Price: $29.99."
    }},
    [("data.entities.emails", ["support@example.com"]), ("data.entities.prices", ["$29.99"])],
)

# --- run_command alias ---
run_test(
    "run_command::alias_cmd",
    {"tool_name": "run_command", "arguments": {"cmd": "python -c \"print('alias ok')\""}},
    [("ok", True)],
)

# ---------------------------------------------------------------------------
# PHASE 2 — Network tests (may be slow; partial failures are warned, not hard-failed)
# ---------------------------------------------------------------------------

print(f"\n{BOLD}Phase 2 — Network tests{RESET}")

# --- web_fetch ---
r = run_test(
    "web_fetch::example_com",
    {"tool_name": "web_fetch", "arguments": {"url": "https://example.com"}},
    [("data.status_code", 200), ("data.body", "_nonempty_")],
)

# --- web_extract_text via URL ---
run_test(
    "web_extract_text::url",
    {"tool_name": "web_extract_text", "arguments": {"url": "https://example.com", "include_metadata": True}},
    [("data.clean_text", "_nonempty_"), ("data.title", "_nonempty_")],
)

# --- web_extract_text via raw HTML ---
run_test(
    "web_extract_text::html",
    {"tool_name": "web_extract_text", "arguments": {
        "html": "<html><body><h1>Test</h1><p>Hello world from extract_text test.</p></body></html>"
    }},
    [("data.clean_text", "_nonempty_")],
)

# --- web_extract_images ---
run_test(
    "web_extract_images::example_com",
    {"tool_name": "web_extract_images", "arguments": {"url": "https://example.com"}},
    [("ok", True)],  # example.com has no images; just verify no crash
)

# --- rss_read ---
run_test(
    "rss_read::planetpython",
    {"tool_name": "rss_read", "arguments": {"feed_urls": ["https://planetpython.org/rss20.xml"], "max_items": 5}},
    [("data.count", "_nonempty_"), ("ok", True)],
    allow_partial=True,
)

# --- intelligent_theme_scraper ---
run_test(
    "intelligent_theme_scraper::example_com",
    {"tool_name": "intelligent_theme_scraper", "arguments": {"url": "https://example.com"}},
    [("data.color_palette", "_exists_"), ("ok", True)],
)

# --- web_code_scraper ---
run_test(
    "web_code_scraper::example_com",
    {"tool_name": "web_code_scraper", "arguments": {"url": "https://example.com"}},
    [("data.url", "https://example.com/"), ("ok", True)],
)

# --- dynamic_browser (Playwright fallback to raw_fetch) ---
run_test(
    "dynamic_browser::example_com",
    {"tool_name": "dynamic_browser", "arguments": {"url": "https://example.com"}},
    [("data.title", "_nonempty_"), ("ok", True)],
)

# --- semantic_content_extractor via URL ---
run_test(
    "semantic_content_extractor::url",
    {"tool_name": "semantic_content_extractor", "arguments": {
        "url": "https://example.com",
        "extraction_targets": ["emails", "links"]
    }},
    [("ok", True)],
)

# --- web_search::text mode ---
run_test(
    "web_search::text",
    {"tool_name": "web_search", "arguments": {"query": "python programming language", "result_type": "text", "max_results": 3}},
    [("ok", True)],
    allow_partial=True,
)

# --- web_search::news mode ---
run_test(
    "web_search::news",
    {"tool_name": "web_search", "arguments": {"query": "python 3.14", "result_type": "news", "time_range": "month", "max_results": 3}},
    [("ok", True)],
    allow_partial=True,
)

# --- web_image_grabber (dry_run, no actual downloads) ---
run_test(
    "web_image_grabber::dry_run",
    {"tool_name": "web_image_grabber", "arguments": {
        "source_mode": "direct_urls",
        "urls": ["https://www.python.org/static/img/python-logo.png"],
        "dry_run": True,
        "require_https": True,
    }},
    [("ok", True)],
)

# --- search_and_extract_pipeline via seed_urls ---
run_test(
    "search_and_extract_pipeline::seed_urls",
    {"tool_name": "search_and_extract_pipeline", "arguments": {
        "seed_urls": ["https://example.com"],
        "max_results": 1,
        "deduplicate": True,
    }},
    [("ok", True)],
)

# ---------------------------------------------------------------------------
# PHASE 3 — New tools tests
# ---------------------------------------------------------------------------

print(f"\n{BOLD}Phase 3 — New tools tests{RESET}")

# --- calculator: basic arithmetic ---
run_test(
    "calculator::basic_add",
    {"tool_name": "calculator", "arguments": {"expression": "2 + 2"}},
    [("data.result", 4), ("data.formatted_result", "4"), ("ok", True)],
)

run_test(
    "calculator::sqrt_pi",
    {"tool_name": "calculator", "arguments": {"expression": "sqrt(144) * pi", "precision": 4}},
    [("data.expression", "sqrt(144) * pi"), ("ok", True)],
)

run_test(
    "calculator::scientific",
    {"tool_name": "calculator", "arguments": {"expression": "2 ** 32", "scientific_notation": True}},
    [("data.result", 4294967296.0), ("ok", True)],
)

run_test(
    "calculator::division",
    {"tool_name": "calculator", "arguments": {"expression": "10 / 3", "precision": 3}},
    [("ok", True)],
)

run_test(
    "calculator::alias_expr",
    {"tool_name": "calculator", "arguments": {"expr": "sin(pi / 2)", "precision": 6}},
    [("ok", True)],
)

# --- image_scraper ---
run_test(
    "image_scraper::example_com",
    {"tool_name": "image_scraper", "arguments": {"url": "https://example.com", "limit": 10}},
    [("ok", True), ("data.url", "_nonempty_")],
)

run_test(
    "image_scraper::python_org",
    {"tool_name": "image_scraper", "arguments": {"url": "https://www.python.org", "limit": 5, "require_https": True}},
    [("ok", True), ("data.count", "_exists_")],
    allow_partial=True,
)

# --- html_report_generator ---
r_html = run_test(
    "html_report_generator::basic",
    {"tool_name": "html_report_generator", "arguments": {
        "title": "Tool Test Report",
        "content": "## Overview\n\nThis is a **test** report.\n\n## Details\n\n- Item 1\n- Item 2\n\n```python\nprint('hello')\n```",
        "theme": "dark",
        "include_toc": True,
    }},
    [("ok", True), ("data.html", "_nonempty_"), ("data.size_bytes", "_nonempty_")],
)

run_test(
    "html_report_generator::with_file",
    {"tool_name": "html_report_generator", "arguments": {
        "title": "Saved Report",
        "content": "## Section 1\n\nContent here.\n\n| Col A | Col B |\n|-------|-------|\n| val1  | val2  |",
        "output_path": "test_report.html",
        "theme": "light",
        "include_toc": True,
    }},
    [("ok", True), ("data.output_path", "test_report.html")],
)
# Verify file written to workspace
_html_out = Path(TEMP_WS) / "test_report.html"
if _html_out.exists():
    print(f"  {GREEN}PASS{RESET} html_report_generator::file_exists ({_html_out.stat().st_size} bytes)")
    passed.append("html_report_generator::file_exists")
else:
    failed.append(("html_report_generator::file_exists", f"file not found at {_html_out}"))
    print(f"  {RED}FAIL{RESET} html_report_generator::file_exists — not at {_html_out}")

run_test(
    "html_report_generator::sections",
    {"tool_name": "html_report_generator", "arguments": {
        "title": "Multi-Section Report",
        "content": "## Introduction\n\nOpening content.",
        "sections": [{"title": "Appendix", "content": "Extra data here."}],
        "include_toc": True,
    }},
    [("ok", True), ("data.toc_entries", "_nonempty_")],
)

# --- json_transform ---
run_test(
    "json_transform::pretty",
    {"tool_name": "json_transform", "arguments": {"data": '{"name":"Alice","age":30,"city":"NYC"}', "transform": "pretty"}},
    [("ok", True), ("data.result", "_nonempty_"), ("data.key_count", 3)],
)

run_test(
    "json_transform::minify",
    {"tool_name": "json_transform", "arguments": {"data": '{"a": 1, "b": 2}', "transform": "minify"}},
    [("ok", True), ("data.result", '{"a":1,"b":2}')],
)

run_test(
    "json_transform::flatten",
    {"tool_name": "json_transform", "arguments": {"data": '{"a":{"b":{"c":42}}}', "transform": "flatten"}},
    [("ok", True)],
)

run_test(
    "json_transform::keys",
    {"tool_name": "json_transform", "arguments": {"data": '{"x":1,"y":2,"z":3}', "transform": "keys"}},
    [("ok", True), ("data.key_count", 3)],
)

run_test(
    "json_transform::query_path",
    {"tool_name": "json_transform", "arguments": {"data": '{"items":[{"title":"first"},{"title":"second"}]}', "query": "items.1.title"}},
    [("ok", True)],
)

run_test(
    "json_transform::summary",
    {"tool_name": "json_transform", "arguments": {"data": '{"name":"Alice","scores":[1,2,3],"meta":{"active":true}}', "transform": "summary"}},
    [("ok", True)],
)

run_test(
    "json_transform::alias_input",
    {"tool_name": "json_transform", "arguments": {"input": '{"hello":"world"}', "operation": "pretty"}},
    [("ok", True)],
)

# ---------------------------------------------------------------------------
# Summary
# ---------------------------------------------------------------------------

total = len(passed) + len(failed)
print(f"\n{BOLD}{'='*55}{RESET}")
print(f"{BOLD}Results: {GREEN}{len(passed)} passed{RESET}, {RED}{len(failed)} failed{RESET} / {total} total{RESET}")
if failed:
    print(f"\n{RED}Failed tests:{RESET}")
    for name, reason in failed:
        print(f"  ✗ {name}: {reason[:200]}")

# Write JSON report to temp workspace
report_path = Path(TEMP_WS) / "test_report.json"
report_path.write_text(json.dumps({
    "passed": passed,
    "failed": [{"name": n, "reason": r} for n, r in failed],
    "total": total,
    "workspace": TEMP_WS,
}, indent=2))
print(f"\nReport saved to: {report_path}")

sys.exit(0 if not failed else 1)
