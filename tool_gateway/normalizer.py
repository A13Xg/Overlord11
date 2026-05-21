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
    },
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

    return normalized, warnings, {"alias_corrections": corrections}
