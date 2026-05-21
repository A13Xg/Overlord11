from __future__ import annotations

from typing import Any


ALIASES_BY_TOOL: dict[str, dict[str, str]] = {
    "run_command": {
        "cmd": "command",
        "timeout": "timeout_seconds",
        "cwd": "working_directory",
        "env": "environment",
    },
    "write_file": {
        "file_path": "path",
    },
    "web_search": {
        "q": "query",
        "limit": "max_results",
        "safesearch": "safe_search",
        "type": "result_type",
        "query_text": "query",
    },
    "web_fetch": {
        "timeout": "timeout_seconds",
    },
    "web_extract_text": {
        "query_text": "raw_text",
    },
    "web_extract_images": {
        "max": "limit",
    },
    "web_image_grabber": {
        "url": "urls",
        "path": "output_directory",
        "max": "max_images",
    },
    "rss_read": {
        "url": "feed_urls",
        "urls": "feed_urls",
        "limit": "max_items",
    },
    "dynamic_browser": {
        "timeout": "timeout_seconds",
        "selector": "wait_selector",
    },
    "intelligent_theme_scraper": {
        "depth": "analysis_depth",
    },
    "web_code_scraper": {
        "include_network": "include_network_analysis",
    },
    "semantic_content_extractor": {
        "query_text": "raw_text",
    },
    "search_and_extract_pipeline": {
        "query": "topics",
        "urls": "seed_urls",
    },
    "calculator": {
        "expr": "expression",
        "calc": "expression",
        "digits": "precision",
    },
    "image_scraper": {
        "page": "url",
        "max": "limit",
        "save": "download",
        "out": "output_directory",
        "timeout": "timeout_seconds",
    },
    "html_report_generator": {
        "heading": "title",
        "body": "content",
        "path": "output_path",
        "file": "output_path",
        "toc": "include_toc",
    },
    "json_transform": {
        "json": "data",
        "input": "data",
        "path": "query",
        "operation": "transform",
        "depth": "max_depth",
    },
}


# Fields that must be lists — if a scalar value arrives after alias normalization, wrap it.
_COERCE_TO_LIST: dict[str, set[str]] = {
    "rss_read": {"feed_urls"},
    "search_and_extract_pipeline": {"topics", "seed_urls"},
}


def normalize_arguments(tool_name: str, arguments: dict[str, Any]) -> tuple[dict[str, Any], list[str], dict[str, Any]]:
    alias_map = ALIASES_BY_TOOL.get(tool_name, {})
    normalized = dict(arguments)
    warnings: list[str] = []
    corrections: list[dict[str, str]] = []

    for source, target in alias_map.items():
        if source in normalized:
            if target in normalized:
                continue
            normalized[target] = normalized.pop(source)
            corrections.append({"from": source, "to": target})
            warnings.append(f"Normalized argument alias '{source}' -> '{target}'")

    # Coerce scalar values to lists where the schema requires a list
    for field in _COERCE_TO_LIST.get(tool_name, set()):
        if field in normalized and isinstance(normalized[field], str):
            normalized[field] = [normalized[field]]
            warnings.append(f"Coerced scalar '{field}' to single-item list")

    return normalized, warnings, {"alias_corrections": corrections}
