from __future__ import annotations

import json
from typing import Any

from .errors import ParseError
from .models import ToolCallRequest


def parse_tool_call(payload: dict[str, Any] | str) -> ToolCallRequest:
    if isinstance(payload, str):
        try:
            parsed = json.loads(payload)
        except json.JSONDecodeError as exc:
            raise ParseError(
                code="PARSE_ERROR",
                message="Malformed JSON tool call payload",
                details={"line": exc.lineno, "column": exc.colno},
                recoverable=True,
                retry_hint="Send valid JSON object: {\"tool_name\":\"...\",\"arguments\":{}}",
            ) from exc
    elif isinstance(payload, dict):
        parsed = payload
    else:
        raise ParseError(
            code="PARSE_ERROR",
            message="Tool call payload must be a dict or JSON string",
            details={"received_type": type(payload).__name__},
            recoverable=True,
            retry_hint="Send dict/JSON with tool_name and arguments",
        )

    try:
        return ToolCallRequest.model_validate(parsed)
    except Exception as exc:
        raise ParseError(
            code="PARSE_ERROR",
            message="Tool call envelope is invalid",
            details={"error": str(exc)},
            recoverable=True,
            retry_hint="Ensure payload includes tool_name and arguments object",
        ) from exc
