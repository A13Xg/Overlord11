from __future__ import annotations

from pydantic import BaseModel, ValidationError as PydanticValidationError

from .errors import ValidationError

_ALLOWED_SHELL_VALUES = ["auto", "powershell", "cmd", "bash", "sh"]
_ALLOWED_KEYS_BY_TOOL: dict[str, list[str]] = {
    "run_command": [
        "command",
        "working_directory",
        "timeout_seconds",
        "shell",
        "environment",
        "capture_output",
        "dry_run",
    ],
    "write_file": ["path", "content", "overwrite"],
    "web_search": [
        "query",
        "max_results",
        "region",
        "safe_search",
        "time_range",
        "result_type",
        "include_snippets",
        "include_metadata",
        "include_rank",
        "include_dates",
        "domain_allowlist",
        "domain_blocklist",
    ],
    "web_fetch": ["url", "timeout_seconds", "follow_redirects", "headers", "user_agent"],
    "web_extract_text": [
        "url",
        "html",
        "raw_text",
        "extraction_mode",
        "include_links",
        "include_metadata",
    ],
    "web_extract_images": ["url", "limit", "include_alt_text", "min_width", "min_height", "image_type"],
    "web_image_grabber": [
        "source_mode",
        "query",
        "urls",
        "output_directory",
        "max_images",
        "matching_mode",
        "allowed_extensions",
        "require_https",
        "deduplicate",
        "overwrite_existing",
        "create_manifest",
        "dry_run",
    ],
    "rss_read": ["feed_urls", "max_items", "include_content", "since_datetime"],
    "dynamic_browser": [
        "url",
        "timeout_seconds",
        "wait_selector",
        "viewport",
        "user_agent",
        "capture_screenshot",
    ],
    "intelligent_theme_scraper": [
        "url",
        "analysis_depth",
        "extract_css_variables",
        "detect_frameworks",
        "include_component_summary",
    ],
    "web_code_scraper": ["url", "include_js", "include_css", "include_network_analysis"],
    "semantic_content_extractor": ["url", "html", "raw_text", "extraction_targets"],
    "search_and_extract_pipeline": ["topics", "seed_urls", "max_results", "deduplicate", "freshness"],
    "calculator": ["expression", "precision", "scientific_notation"],
    "image_scraper": ["url", "limit", "download", "output_directory", "min_size_kb", "require_https", "timeout_seconds"],
    "html_report_generator": ["title", "content", "output_path", "theme", "palette_id", "style_id", "include_toc", "sections"],
    "json_transform": ["data", "query", "transform", "max_depth"],
    "read_file": ["path", "encoding", "max_bytes", "include_line_count"],
    "csv_processor": [
        "data",
        "filter_column",
        "filter_value",
        "sort_column",
        "sort_order",
        "columns",
        "max_rows",
        "operation",
    ],
    "url_checker": ["urls", "timeout_seconds", "follow_redirects", "check_ssl", "method"],
    "text_diff": ["text_a", "text_b", "label_a", "label_b", "context_lines", "format"],
    "base64_tool": ["operation", "data", "variant", "encoding"],
    "json_schema_validator": ["data", "json_schema", "stop_on_first_error"],
}
_EXAMPLES_BY_TOOL: dict[str, dict] = {
    "run_command": {
        "tool_name": "run_command",
        "arguments": {"command": "python --version", "timeout_seconds": 30},
    },
    "write_file": {
        "tool_name": "write_file",
        "arguments": {"path": "output/answer.md", "content": "hello", "overwrite": True},
    },
    "web_search": {
        "tool_name": "web_search",
        "arguments": {
            "query": "python release notes",
            "max_results": 5,
            "safe_search": "moderate",
            "time_range": "month",
            "result_type": "text",
            "include_snippets": True,
        },
    },
    "web_fetch": {
        "tool_name": "web_fetch",
        "arguments": {"url": "https://example.com", "timeout_seconds": 20, "follow_redirects": True},
    },
    "web_extract_text": {
        "tool_name": "web_extract_text",
        "arguments": {"url": "https://example.com", "extraction_mode": "auto", "include_metadata": True},
    },
    "web_extract_images": {
        "tool_name": "web_extract_images",
        "arguments": {"url": "https://example.com", "limit": 20, "image_type": "auto"},
    },
    "web_image_grabber": {
        "tool_name": "web_image_grabber",
        "arguments": {"query": "mountain landscape", "max_images": 10, "source_mode": "search_query"},
    },
    "rss_read": {
        "tool_name": "rss_read",
        "arguments": {"feed_urls": ["https://planetpython.org/rss20.xml"], "max_items": 20},
    },
    "dynamic_browser": {
        "tool_name": "dynamic_browser",
        "arguments": {"url": "https://example.com", "timeout_seconds": 30, "capture_screenshot": False},
    },
    "intelligent_theme_scraper": {
        "tool_name": "intelligent_theme_scraper",
        "arguments": {"url": "https://example.com", "analysis_depth": "balanced"},
    },
    "web_code_scraper": {
        "tool_name": "web_code_scraper",
        "arguments": {"url": "https://example.com", "include_js": True, "include_css": True},
    },
    "semantic_content_extractor": {
        "tool_name": "semantic_content_extractor",
        "arguments": {"url": "https://example.com", "extraction_targets": []},
    },
    "search_and_extract_pipeline": {
        "tool_name": "search_and_extract_pipeline",
        "arguments": {"topics": ["python packaging"], "max_results": 10, "freshness": "recent"},
    },
    "calculator": {
        "tool_name": "calculator",
        "arguments": {"expression": "sqrt(16) * pi", "precision": 4},
    },
    "image_scraper": {
        "tool_name": "image_scraper",
        "arguments": {"url": "https://example.com", "limit": 20},
    },
    "html_report_generator": {
        "tool_name": "html_report_generator",
        "arguments": {"title": "My Report", "content": "## Overview\nContent here.", "theme": "dark"},
    },
    "json_transform": {
        "tool_name": "json_transform",
        "arguments": {"data": "{\"key\": \"value\"}", "transform": "pretty"},
    },
    "read_file": {
        "tool_name": "read_file",
        "arguments": {"path": "final_output.md"},
    },
    "csv_processor": {
        "tool_name": "csv_processor",
        "arguments": {"data": "data/results.csv", "operation": "summary"},
    },
    "url_checker": {
        "tool_name": "url_checker",
        "arguments": {"urls": ["https://example.com", "https://python.org"]},
    },
    "text_diff": {
        "tool_name": "text_diff",
        "arguments": {
            "text_a": "Hello world\nLine two",
            "text_b": "Hello world\nLine 2",
        },
    },
    "base64_tool": {
        "tool_name": "base64_tool",
        "arguments": {"operation": "encode", "data": "Hello, Overlord11!"},
    },
    "json_schema_validator": {
        "tool_name": "json_schema_validator",
        "arguments": {
            "data": "{\"name\": \"Alice\", \"age\": 30}",
            "json_schema": "{\"type\": \"object\", \"required\": [\"name\"], \"properties\": {\"name\": {\"type\": \"string\"}}}",
        },
    },
}


def validate_arguments(model: type[BaseModel], arguments: dict, tool_name: str | None = None) -> BaseModel:
    try:
        return model.model_validate(arguments)
    except PydanticValidationError as exc:
        issues = exc.errors()
        allowed_values = None
        for issue in issues:
            loc = issue.get("loc") or ()
            if "shell" in loc:
                allowed_values = _ALLOWED_SHELL_VALUES
                break
            if "safe_search" in loc:
                allowed_values = ["off", "moderate", "strict"]
                break
            if "time_range" in loc:
                allowed_values = ["any", "day", "week", "month", "year"]
                break
            if "result_type" in loc:
                allowed_values = ["auto", "text", "news", "images"]
                break
        details = {"issues": issues}
        retry_hint = "Check required fields, types, and unknown arguments"
        if tool_name and tool_name in _ALLOWED_KEYS_BY_TOOL:
            details["allowed_keys"] = _ALLOWED_KEYS_BY_TOOL[tool_name]
            example = _EXAMPLES_BY_TOOL.get(tool_name)
            if example:
                details["example"] = example
                retry_hint = (
                    f"Allowed keys for {tool_name}: {', '.join(_ALLOWED_KEYS_BY_TOOL[tool_name])}. "
                    f"Example: {example}"
                )
        if allowed_values:
            details["allowed_values"] = allowed_values
            if tool_name == "run_command":
                retry_hint = "Use shell one of: auto, powershell, cmd, bash, sh, or omit shell to use default auto"
            elif tool_name == "web_search":
                retry_hint = "Use allowed enum values for web_search fields shown in allowed_values"
        raise ValidationError(
            code="VALIDATION_ERROR",
            message="Tool arguments failed schema validation",
            details=details,
            recoverable=True,
            retry_hint=retry_hint,
        ) from exc
