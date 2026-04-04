"""
backend/api/events.py
======================
SSE and WebSocket endpoints for real-time event streaming.

GET  /api/events/{session_id}          SSE stream
GET  /api/events/{session_id}/history  Event history
WS   /ws/{session_id}                  WebSocket stream
"""

import asyncio
import json
from typing import Optional

from fastapi import APIRouter, Query, WebSocket, WebSocketDisconnect
from fastapi.responses import StreamingResponse

from backend.core.event_stream import event_bus

router = APIRouter(tags=["events"])


@router.get("/api/events/{session_id}")
async def sse_stream(
    session_id: str,
    since: float = Query(0.0, description="Return events with ts > since"),
):
    """Server-Sent Events stream for a session."""

    async def generator():
        async for chunk in event_bus.sse_generator(session_id, since=since):
            yield chunk

    return StreamingResponse(
        generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )


@router.get("/api/events/{session_id}/history")
def event_history(
    session_id: str,
    since: float = Query(0.0),
):
    """Return buffered event history for a session."""
    stream = event_bus.get(session_id)
    if not stream:
        return {"session_id": session_id, "events": []}
    return {"session_id": session_id, "events": stream.get_history(since=since)}


@router.websocket("/ws/{session_id}")
async def websocket_stream(websocket: WebSocket, session_id: str):
    """WebSocket stream — mirrors the SSE events."""
    await websocket.accept()
    stream = event_bus.get(session_id)
    if not stream:
        await websocket.send_json({"type": "error", "error": f"Session {session_id} not found"})
        await websocket.close()
        return

    try:
        async for event in stream.subscribe(replay_history=True):
            await websocket.send_json(event)
            if event.get("type") in ("complete", "error"):
                break
    except WebSocketDisconnect:
        pass
    except Exception:
        pass
    finally:
        try:
            await websocket.close()
        except Exception:
            pass
