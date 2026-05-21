"""Overlord11 Engine - Tool Executor (gateway-backed)."""

from __future__ import annotations

import json
import os
import re
import time
from contextlib import contextmanager
from dataclasses import dataclass
from typing import Any, List

from tool_gateway.executor import ToolGateway
from tool_gateway.registry import ToolRegistry
from tool_gateway.tools import ShellExecutionAdapter, WebSearchTool, WriteFileTool


@dataclass
class ToolCall:
    tool_name: str
    params: dict
    raw: str = ""


_JSON_BLOCK_RE = re.compile(r"```json\s*(.*?)\s*```", re.DOTALL | re.IGNORECASE)


def extract_tool_calls(text: str) -> List[ToolCall]:
    calls: List[ToolCall] = []

    def _append_from_obj(obj: Any, raw: str) -> None:
        if isinstance(obj, dict):
            tool_name = obj.get("tool_name") or ""
            params = obj.get("arguments") or {}
            if isinstance(tool_name, str) and tool_name and isinstance(params, dict):
                calls.append(ToolCall(tool_name=tool_name, params=params, raw=raw))
        elif isinstance(obj, list):
            for item in obj:
                if isinstance(item, dict):
                    _append_from_obj(item, raw)

    for m in _JSON_BLOCK_RE.finditer(text):
        raw = m.group(0)
        try:
            obj = json.loads(m.group(1))
            _append_from_obj(obj, raw)
        except (json.JSONDecodeError, TypeError):
            pass

    # Accept canonical bare JSON payloads (single object or array)
    # when the assistant response is top-level JSON without fences.
    stripped = (text or "").strip()
    if stripped.startswith("{") or stripped.startswith("["):
        try:
            obj = json.loads(stripped)
            _append_from_obj(obj, stripped)
        except (json.JSONDecodeError, TypeError):
            pass

    return calls


class ToolExecutor:
    """Compatibility wrapper around the new standardized tool gateway."""

    def __init__(self, tools_dir=None, config=None):
        registry = ToolRegistry()
        registry.register_tool(ShellExecutionAdapter())
        registry.register_tool(WriteFileTool())
        registry.register_tool(WebSearchTool())
        self._gateway = ToolGateway(registry)
        self._runtime_context: dict[str, str] = {}

    def set_runtime_context(self, *, session_id=None, task_dir=None) -> None:
        self._runtime_context = {}
        if session_id:
            self._runtime_context["OVERLORD11_SESSION_ID"] = session_id
        if task_dir:
            self._runtime_context["OVERLORD11_TASK_DIR"] = str(task_dir)

    @contextmanager
    def _runtime_env(self):
        original: dict[str, str | None] = {}
        try:
            for key, value in self._runtime_context.items():
                original[key] = os.environ.get(key)
                os.environ[key] = value
            yield
        finally:
            for key in self._runtime_context:
                prior = original.get(key)
                if prior is None:
                    os.environ.pop(key, None)
                else:
                    os.environ[key] = prior

    def _normalize_params(self, tool_name: str, params: dict) -> None:
        # Canonical schema-only runtime; normalization happens in gateway.
        return

    def execute(self, tool_call: ToolCall) -> dict:
        start = time.monotonic()
        tool_name = tool_call.tool_name
        session_id = self._runtime_context.get("OVERLORD11_SESSION_ID")
        payload = {"tool_name": tool_name, "arguments": dict(tool_call.params or {})}
        with self._runtime_env():
            result = self._gateway.execute_tool_call(payload, session_id=session_id)
        duration_ms = round((time.monotonic() - start) * 1000, 2)

        if result.get("ok"):
            return {
                "status": "success",
                "result": result,
                "tool": tool_name,
                "duration_ms": duration_ms,
            }
        return {
            "status": "error",
            "result": result,
            "tool": tool_name,
            "duration_ms": duration_ms,
            "error": result.get("errors", []),
        }
