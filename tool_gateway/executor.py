from __future__ import annotations

import time
import uuid
from typing import Any

from .errors import ExecutionError, ParseError, UnknownToolError, ValidationError
from .logging_config import log_event
from .normalizer import normalize_arguments
from .parser import parse_tool_call
from .registry import ToolRegistry
from .results import error_result, success_result
from .validator import validate_arguments


class ToolGateway:
    def __init__(self, registry: ToolRegistry):
        self.registry = registry
        self._session_validation_retry_counts: dict[str, int] = {}
        self._session_validation_retry_counts_by_field: dict[str, dict[str, int]] = {}

    def register_tool(self, tool) -> None:
        self.registry.register_tool(tool)

    def list_tools(self) -> list[dict[str, Any]]:
        return self.registry.list_tools()

    def get_tool_schema(self, tool_name: str) -> dict[str, Any]:
        return self.registry.get_tool_schema(tool_name)

    def validate_tool_call(self, tool_name: str, arguments: dict[str, Any]) -> dict[str, Any]:
        try:
            tool = self.registry.get_tool(tool_name)
            normalized, warnings, normalization_meta = normalize_arguments(tool_name, arguments)
            validated = validate_arguments(tool.input_model, normalized, tool_name=tool_name)
            return success_result(
                tool_name,
                {"validated_arguments": validated.model_dump()},
                warnings=warnings,
                metadata={"normalization": normalization_meta},
            )
        except UnknownToolError as exc:
            return error_result(
                tool_name,
                code=exc.code,
                message=exc.message,
                details=exc.details,
                recoverable=exc.recoverable,
                retry_hint=exc.retry_hint,
            )
        except ValidationError as exc:
            return error_result(
                tool_name,
                code=exc.code,
                message=exc.message,
                details=exc.details,
                recoverable=exc.recoverable,
                retry_hint=exc.retry_hint,
            )

    def execute_tool_call(self, payload: dict[str, Any] | str, session_id: str | None = None) -> dict[str, Any]:
        request_id = str(uuid.uuid4())
        start = time.monotonic()
        raw_arguments: dict[str, Any] = {}
        tool_name = "unknown"

        try:
            call = parse_tool_call(payload)
            tool_name = call.tool_name
            raw_arguments = call.arguments
            tool = self.registry.get_tool(tool_name)
            normalized_arguments, warnings, normalization_meta = normalize_arguments(tool_name, call.arguments)
            validated = validate_arguments(tool.input_model, normalized_arguments, tool_name=tool_name)

            data = tool.execute(validated)
            metadata = {
                "request_id": request_id,
                "normalization": normalization_meta,
                "duration_seconds": round(time.monotonic() - start, 4),
            }
            if isinstance(data, dict):
                metadata.setdefault("shell_used", data.get("shell_used"))
                metadata.setdefault("shell_path", data.get("shell_path"))

            result = success_result(tool_name, data if isinstance(data, dict) else {"value": data}, warnings=warnings, metadata=metadata)
            log_event({
                "request_id": request_id,
                "session_id": session_id,
                "tool_name": tool_name,
                "raw_arguments": raw_arguments,
                "normalized_arguments": normalized_arguments,
                "validation_status": "ok",
                "execution_status": "ok",
                "duration_seconds": metadata["duration_seconds"],
                "provider": self._provider_from_session_id(session_id),
            })
            return result

        except (ParseError, UnknownToolError, ValidationError) as exc:
            duration = round(time.monotonic() - start, 4)
            validation_fields = self._extract_validation_fields(exc.details if isinstance(exc.details, dict) else {})
            retry_count = self._increment_validation_retry_count(session_id, validation_fields)
            retry_counts_by_field = self._get_validation_retry_counts_by_field(session_id, validation_fields)
            result = error_result(
                tool_name,
                code=exc.code,
                message=exc.message,
                details=exc.details,
                recoverable=exc.recoverable,
                retry_hint=exc.retry_hint,
                metadata={
                    "request_id": request_id,
                    "duration_seconds": duration,
                    "validation_error_fields": validation_fields,
                    "validation_error_field": validation_fields[0] if validation_fields else None,
                    "retry_validation_error_count": retry_count,
                    "retry_validation_error_count_by_field": retry_counts_by_field,
                },
            )
            log_event({
                "request_id": request_id,
                "session_id": session_id,
                "tool_name": tool_name,
                "raw_arguments": raw_arguments,
                "validation_status": "failed",
                "execution_status": "not_executed",
                "duration_seconds": duration,
                "error_code": exc.code,
                "validation_error_fields": validation_fields,
                "validation_error_field": validation_fields[0] if validation_fields else None,
                "retry_validation_error_count": retry_count,
                "retry_validation_error_count_by_field": retry_counts_by_field,
                "provider": self._provider_from_session_id(session_id),
            })
            return result
        except Exception as exc:
            duration = round(time.monotonic() - start, 4)
            err = ExecutionError(
                code="EXECUTION_ERROR",
                message="Tool execution failed",
                details={"error": str(exc)},
                recoverable=True,
                retry_hint="Review arguments and retry",
            )
            result = error_result(
                tool_name,
                code=err.code,
                message=err.message,
                details=err.details,
                recoverable=err.recoverable,
                retry_hint=err.retry_hint,
                metadata={"request_id": request_id, "duration_seconds": duration},
            )
            log_event({
                "request_id": request_id,
                "session_id": session_id,
                "tool_name": tool_name,
                "raw_arguments": raw_arguments,
                "validation_status": "ok",
                "execution_status": "failed",
                "duration_seconds": duration,
                "error_code": err.code,
                "provider": self._provider_from_session_id(session_id),
            })
            return result

    def _extract_validation_fields(self, details: dict[str, Any]) -> list[str]:
        fields: list[str] = []
        for issue in details.get("issues", []):
            loc = issue.get("loc") or []
            if isinstance(loc, (list, tuple)) and loc:
                fields.append(str(loc[0]))
        # stable de-dupe
        deduped: list[str] = []
        for field in fields:
            if field not in deduped:
                deduped.append(field)
        return deduped

    def _provider_from_session_id(self, session_id: str | None) -> str | None:
        # Placeholder hook for future session/provider binding.
        return None

    def _increment_validation_retry_count(self, session_id: str | None, validation_fields: list[str]) -> int:
        if not session_id or not validation_fields:
            return 0
        count = self._session_validation_retry_counts.get(session_id, 0) + 1
        self._session_validation_retry_counts[session_id] = count
        by_field = self._session_validation_retry_counts_by_field.setdefault(session_id, {})
        for field in validation_fields:
            key = str(field)
            by_field[key] = by_field.get(key, 0) + 1
        return count

    def _get_validation_retry_counts_by_field(self, session_id: str | None, validation_fields: list[str]) -> dict[str, int]:
        if not session_id or not validation_fields:
            return {}
        by_field = self._session_validation_retry_counts_by_field.get(session_id, {})
        return {field: int(by_field.get(field, 0)) for field in validation_fields}
