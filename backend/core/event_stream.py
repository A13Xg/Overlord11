"""
backend/core/event_stream.py
=============================
SSE (Server-Sent Events) and WebSocket event bus for the backend API.

Bridges the engine's per-session EventStream to HTTP clients.
"""

import asyncio
import json
import time
from typing import Any, AsyncIterator, Dict, Optional

from engine.event_stream import EventStream as EngineEventStream


class BackendEventBus:
    """
    Global registry of active engine EventStreams, keyed by session_id.
    The API layer registers streams here so SSE endpoints can subscribe.
    """

    def __init__(self):
        self._streams: Dict[str, EngineEventStream] = {}

    def register(self, session_id: str, stream: EngineEventStream) -> None:
        self._streams[session_id] = stream

    def unregister(self, session_id: str) -> None:
        self._streams.pop(session_id, None)

    def get(self, session_id: str) -> Optional[EngineEventStream]:
        return self._streams.get(session_id)

    def list_active(self):
        return list(self._streams.keys())

    async def sse_generator(
        self, session_id: str, since: float = 0.0
    ) -> AsyncIterator[str]:
        """
        Async generator yielding SSE-formatted strings for a session.
        If the session has already completed, replay history and close.
        """
        stream = self._streams.get(session_id)
        if stream is None:
            yield _sse_event({"type": "error", "error": f"Session {session_id} not found"})
            return

        async for event in stream.subscribe(replay_history=(since == 0.0)):
            if event.get("ts", 0) < since:
                continue
            yield _sse_event(event)


def _sse_event(data: Dict[str, Any]) -> str:
    """Format a dict as an SSE data line."""
    return f"data: {json.dumps(data)}\n\n"


# Singleton instance used by the API
event_bus = BackendEventBus()
