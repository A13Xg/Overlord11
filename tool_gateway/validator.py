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
                allowed_values = ["text", "news"]
                break
        details = {"issues": issues}
        retry_hint = "Check required fields, types, and unknown arguments"
        if tool_name and tool_name in _ALLOWED_KEYS_BY_TOOL:
            details["allowed_keys"] = _ALLOWED_KEYS_BY_TOOL[tool_name]
            details["example"] = _EXAMPLES_BY_TOOL[tool_name]
            retry_hint = (
                f"Allowed keys for {tool_name}: {', '.join(_ALLOWED_KEYS_BY_TOOL[tool_name])}. "
                f"Example: {_EXAMPLES_BY_TOOL[tool_name]}"
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
