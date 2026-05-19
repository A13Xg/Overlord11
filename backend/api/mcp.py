"""
MCP runtime API endpoints.
"""

from __future__ import annotations

from fastapi import APIRouter

from ..core.mcp_runtime import mcp_runtime

router = APIRouter(tags=["mcp"])


@router.get("/api/mcp/servers")
async def list_mcp_servers():
    return {"servers": mcp_runtime.server_status()}


@router.get("/api/mcp/tools")
async def list_mcp_tools():
    return {"tools": mcp_runtime.tool_catalog()}


@router.post("/api/mcp/refresh")
async def refresh_mcp_tools():
    return mcp_runtime.refresh_tools()

