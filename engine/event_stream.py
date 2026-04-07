"""
Overlord11 Engine - Event Stream
==================================
Structured event emission for the engine execution loop.
"""

import json
import threading
from datetime import datetime, timezone
from enum import Enum
from typing import Callable, List, Optional


class EventType(str, Enum):
    AGENT_START = "AGENT_START"
    AGENT_COMPLETE = "AGENT_COMPLETE"
    AGENT_MESSAGE = "AGENT_MESSAGE"
    TOOL_CALL = "TOOL_CALL"
    TOOL_RESULT = "TOOL_RESULT"
    TOOL_ERROR = "TOOL_ERROR"
    PROVIDER_TRACE = "PROVIDER_TRACE"
    SYSTEM_PROFILE = "SYSTEM_PROFILE"
    ARTIFACT_CREATED = "ARTIFACT_CREATED"
    SESSION_START = "SESSION_START"
    SESSION_END = "SESSION_END"
    ERROR = "ERROR"
    STATUS = "STATUS"
    # Streaming: emitted for each batch of tokens during LLM generation.
    # Payload: {text: str, agent_id: str, loop: int, session_id: str}
    TOKEN = "TOKEN"
    # Cache: emitted when a tool result is served from cache instead of executing.
    # Payload: {tool: str, cache_age_s: float, loop: int}
    TOOL_CACHE_HIT = "TOOL_CACHE_HIT"
    # Notifications: emitted by notification_tool to push browser toasts to the operator.
    # Payload: {title: str, message: str, severity: str, session_id: str|None}
    NOTIFICATION = "NOTIFICATION"


class EventStream:
    """Collects and emits structured events during engine execution."""

    def __init__(self, verbose: bool = False, callbacks: Optional[List[Callable]] = None):
        self.verbose = verbose
        self.callbacks: List[Callable] = callbacks or []
        self._events: List[dict] = []
        # Guards _events mutations and callbacks snapshot so that parallel
        # tool threads never corrupt the event list or miss a callback.
        self._lock = threading.Lock()

    def emit(self, event_type: EventType, **kwargs) -> dict:
        """
        Create and store an event, invoke callbacks, optionally print.

        Thread-safe: multiple threads (parallel tool workers) may call this
        simultaneously.  The lock is held only for the append and callbacks
        snapshot; actual callback invocation happens outside the lock to
        prevent deadlocks when a callback itself calls emit().
        """
        event = {
            "type": event_type.value if isinstance(event_type, EventType) else str(event_type),
            "timestamp": datetime.now(timezone.utc).isoformat(),
            **kwargs,
        }
        with self._lock:
            self._events.append(event)
            # Snapshot the callback list so we can release the lock before
            # calling each one (callbacks may re-enter emit()).
            cbs = list(self.callbacks)

        for cb in cbs:
            try:
                cb(event)
            except Exception:
                pass

        if self.verbose:
            print(json.dumps(event, ensure_ascii=False))

        return event

    def get_events(self, since: Optional[str] = None) -> List[dict]:
        """Return all events, optionally filtered to those after an ISO timestamp."""
        with self._lock:
            snapshot = list(self._events)
        if since is None:
            return snapshot
        return [e for e in snapshot if e.get("timestamp", "") >= since]
