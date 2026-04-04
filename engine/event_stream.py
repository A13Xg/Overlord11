"""
engine/event_stream.py
=======================
Async event emission bus.  Consumers subscribe to a queue and receive
typed events as the agent execution loop progresses.

Event schema
------------
Every event is a plain dict with at minimum:
    { "type": str, "session_id": str, "ts": float, ...payload }

Supported types (from spec):
    agent_start, tool_call, tool_result, log, complete, error, healing
"""

import asyncio
import time
from dataclasses import dataclass, field, asdict
from typing import Any, AsyncIterator, Dict, List, Optional


# ---------------------------------------------------------------------------
# Event helpers
# ---------------------------------------------------------------------------

def _now() -> float:
    return time.time()


def make_event(event_type: str, session_id: str, **payload) -> Dict[str, Any]:
    """Build a canonical event dict."""
    return {"type": event_type, "session_id": session_id, "ts": _now(), **payload}


# ---------------------------------------------------------------------------
# EventStream
# ---------------------------------------------------------------------------

class EventStream:
    """
    Per-session async event bus.

    Usage
    -----
    stream = EventStream(session_id="abc123")
    stream.emit("agent_start", agent="orchestrator")

    async for event in stream.subscribe():
        print(event)
    """

    def __init__(self, session_id: str, maxsize: int = 512):
        self.session_id = session_id
        self._queues: List[asyncio.Queue] = []
        self._history: List[Dict[str, Any]] = []
        self._closed = False
        self._maxsize = maxsize

    # ------------------------------------------------------------------
    # Emit (sync-safe — can be called from sync or async context)
    # ------------------------------------------------------------------

    def emit(self, event_type: str, **payload) -> None:
        """Emit an event to all subscribers."""
        event = make_event(event_type, self.session_id, **payload)
        self._history.append(event)
        for q in self._queues:
            if not q.full():
                # Put nowait; drop if queue is full to avoid blocking caller
                try:
                    q.put_nowait(event)
                except asyncio.QueueFull:
                    pass

    def emit_agent_start(self, agent: str, task: str = "") -> None:
        self.emit("agent_start", agent=agent, task=task)

    def emit_tool_call(self, tool: str, args: Dict[str, Any]) -> None:
        self.emit("tool_call", tool=tool, args=args)

    def emit_tool_result(self, tool: str, result: Any) -> None:
        self.emit("tool_result", tool=tool, result=result)

    def emit_log(self, message: str, level: str = "info") -> None:
        self.emit("log", message=message, level=level)

    def emit_complete(self, result: Any = None) -> None:
        self.emit("complete", result=result)
        self._closed = True

    def emit_error(self, error: str, context: Dict[str, Any] = None) -> None:
        self.emit("error", error=error, context=context or {})

    def emit_healing(self, attempt: int, strategy: str, original_error: str) -> None:
        self.emit("healing", attempt=attempt, strategy=strategy, original_error=original_error)

    # ------------------------------------------------------------------
    # Subscribe (async generator)
    # ------------------------------------------------------------------

    async def subscribe(self, replay_history: bool = False) -> AsyncIterator[Dict[str, Any]]:
        """
        Async generator — yields events in real time.
        Set replay_history=True to first receive all buffered events.
        """
        q: asyncio.Queue = asyncio.Queue(maxsize=self._maxsize)
        if replay_history:
            for evt in list(self._history):
                await q.put(evt)
        self._queues.append(q)
        try:
            while True:
                try:
                    event = await asyncio.wait_for(q.get(), timeout=30.0)
                    yield event
                    if event["type"] == "complete" or event["type"] == "error":
                        break
                except asyncio.TimeoutError:
                    if self._closed:
                        break
                    # Send keepalive ping
                    yield make_event("ping", self.session_id)
        finally:
            self._queues.remove(q)

    # ------------------------------------------------------------------
    # History
    # ------------------------------------------------------------------

    def get_history(self, since: float = 0.0) -> List[Dict[str, Any]]:
        """Return all events with ts > since."""
        return [e for e in self._history if e["ts"] > since]

    def __len__(self) -> int:
        return len(self._history)
