"""
Overlord11 Engine - Event Stream
==================================
Structured event emission for the engine execution loop.
"""

import json
from datetime import datetime, timezone
from enum import Enum
from typing import Callable, List, Optional


class EventType(str, Enum):
    AGENT_START = "AGENT_START"
    AGENT_COMPLETE = "AGENT_COMPLETE"
    TOOL_CALL = "TOOL_CALL"
    TOOL_RESULT = "TOOL_RESULT"
    TOOL_ERROR = "TOOL_ERROR"
    SESSION_START = "SESSION_START"
    SESSION_END = "SESSION_END"
    ERROR = "ERROR"
    STATUS = "STATUS"


class EventStream:
    """Collects and emits structured events during engine execution."""

    def __init__(self, verbose: bool = False, callbacks: Optional[List[Callable]] = None):
        self.verbose = verbose
        self.callbacks: List[Callable] = callbacks or []
        self._events: List[dict] = []

    def emit(self, event_type: EventType, **kwargs) -> dict:
        """Create and store an event, invoke callbacks, optionally print."""
        event = {
            "type": event_type.value if isinstance(event_type, EventType) else str(event_type),
            "timestamp": datetime.now(timezone.utc).isoformat(),
            **kwargs,
        }
        self._events.append(event)

        for cb in self.callbacks:
            try:
                cb(event)
            except Exception:
                pass

        if self.verbose:
            print(json.dumps(event, ensure_ascii=False))

        return event

    def get_events(self, since: Optional[str] = None) -> List[dict]:
        """Return all events, optionally filtered to those after an ISO timestamp."""
        if since is None:
            return list(self._events)
        return [e for e in self._events if e.get("timestamp", "") >= since]
