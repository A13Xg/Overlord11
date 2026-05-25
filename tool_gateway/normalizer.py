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
        "mode": "result_type",
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
        "action": "capture_screenshot",
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
    "read_file": {
        "file": "path",
        "file_path": "path",
        "filename": "path",
    },
    "csv_processor": {
        "file": "data",
        "csv": "data",
        "input": "data",
        "filter": "filter_value",
        "sort": "sort_column",
        "limit": "max_rows",
    },
    "url_checker": {
        "url": "urls",
        "timeout": "timeout_seconds",
    },
    "text_diff": {
        "original": "text_a",
        "modified": "text_b",
        "a": "text_a",
        "b": "text_b",
        "context": "context_lines",
    },
    "base64_tool": {
        "text": "data",
        "input": "data",
        "action": "operation",
    },
    "json_schema_validator": {
        "json": "data",
        "input": "data",
        "schema": "json_schema",
        "schema_str": "json_schema",
    },
    "scaffold_generator": {
        "project_dir": "output_dir",
        "name": "app_name",
        "type": "app_type",
    },
    "launcher_generator": {
        "command": "app_command",
        "project_path": "project_dir",
    },
}


# Fields that must be lists — if a scalar value arrives after alias normalization, wrap it.
_COERCE_TO_LIST: dict[str, set[str]] = {
    "rss_read": {"feed_urls"},
    "search_and_extract_pipeline": {"topics", "seed_urls"},
    "url_checker": {"urls"},
    "csv_processor": {"columns"},
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

    # Normalize frequent enum/value variants from model output.
    if tool_name == "web_search" and isinstance(normalized.get("result_type"), str):
        raw = str(normalized["result_type"]).strip().lower()
        rt_alias = {
            "web": "text",
            "search": "text",
            "image": "images",
            "img": "images",
        }
        if raw in rt_alias:
            normalized["result_type"] = rt_alias[raw]
            warnings.append(f"Normalized result_type value '{raw}' -> '{rt_alias[raw]}'")

    if tool_name == "dynamic_browser" and isinstance(normalized.get("capture_screenshot"), str):
        raw = str(normalized["capture_screenshot"]).strip().lower()
        shot_alias = {
            "render": False,
            "html": False,
            "fetch": False,
            "screenshot": True,
            "capture": True,
        }
        if raw in shot_alias:
            normalized["capture_screenshot"] = shot_alias[raw]
            warnings.append(
                f"Normalized capture_screenshot value '{raw}' -> '{shot_alias[raw]}'"
            )

    if tool_name == "html_report_generator" and isinstance(normalized.get("theme"), str):
        raw_theme = str(normalized["theme"]).strip()
        if raw_theme.lower() not in {"dark", "light", "auto"}:
            if not normalized.get("style_id"):
                normalized["style_id"] = raw_theme
                warnings.append(f"Moved invalid theme value '{raw_theme}' to style_id")
            normalized["theme"] = "dark"
            warnings.append("Normalized invalid html_report_generator theme to 'dark'")

    return normalized, warnings, {"alias_corrections": corrections}
