"""
Tools API — list registered tools and their schemas.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends

from ..auth.auth import require_auth
from ..core.engine_bridge import bridge

router = APIRouter(prefix="/api/tools", tags=["tools"])


@router.get("")
async def list_tools(_session: dict = Depends(require_auth)):
    """Return all registered tools with names, descriptions, risk levels, and input schemas."""
    tools = bridge.list_tools()
    return {"count": len(tools), "tools": tools}


@router.get("/{tool_name}")
async def get_tool(tool_name: str, _session: dict = Depends(require_auth)):
    """Return schema for a specific tool."""
    tools = bridge.list_tools()
    for tool in tools:
        if tool["name"] == tool_name:
            return tool
    from fastapi import HTTPException
    raise HTTPException(status_code=404, detail=f"Tool not found: {tool_name!r}")
