from __future__ import annotations

from typing import Any

from .errors import UnknownToolError
from .tools.base import BaseTool


class ToolRegistry:
    def __init__(self) -> None:
        self._tools: dict[str, BaseTool] = {}

    def register_tool(self, tool: BaseTool) -> None:
        if tool.name in self._tools:
            raise ValueError(f"Duplicate tool registration: {tool.name}")
        self._tools[tool.name] = tool

    def get_tool(self, tool_name: str) -> BaseTool:
        tool = self._tools.get(tool_name)
        if tool is None:
            raise UnknownToolError(
                code="UNKNOWN_TOOL",
                message=f"Unknown tool: {tool_name}",
                details={"tool_name": tool_name},
                recoverable=True,
                retry_hint="Call list_tools() to discover valid names",
            )
        return tool

    def list_tools(self) -> list[dict[str, Any]]:
        return [tool.schema() for tool in self._tools.values()]

    def get_tool_schema(self, tool_name: str) -> dict[str, Any]:
        return self.get_tool(tool_name).schema()
