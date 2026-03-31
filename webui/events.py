"""
webui/events.py — Stable event schema for Overlord11 Tactical WebUI.

Every significant action emits one of these typed events.  All events share
a common envelope; payloads are free-form dicts.

Event types (canonical):
    JOB_CREATED        job was persisted for the first time
    JOB_STARTING       runner loop is about to begin
    STATUS             generic status change (job state field updated)
    ITERATION          start/end of a runner iteration
    TOOL_START         tool invocation beginning
    TOOL_END           tool invocation finished
    VERIFY_START       verify gate is running
    VERIFY_RESULT      verify gate finished (pass/fail + output tail)
    REPAIR_START       repair loop triggered after verify failure
    REPAIR_RESULT      repair attempt finished
    REVIEW_START       reviewer gate running
    REVIEW_RESULT      reviewer gate finished
    LLM_CALL_START     LLM API call initiated
    LLM_CALL_END       LLM API call finished (tokens, latency)
    USER_DIRECTIVE     feedback/directive injected by the user mid-run
    ASSUMPTION_LOG     runner logged an assumption instead of asking user
    COMPLETE           job finished successfully
    FAILED             job stopped with an error / budget exceeded
    PAUSED             job paused by request
    RESUMED            job resumed from PAUSED state
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from enum import Enum
from typing import Any


class EventType(str, Enum):
    JOB_CREATED = "JOB_CREATED"
    JOB_STARTING = "JOB_STARTING"
    STATUS = "STATUS"
    ITERATION = "ITERATION"
    TOOL_START = "TOOL_START"
    TOOL_END = "TOOL_END"
    VERIFY_START = "VERIFY_START"
    VERIFY_RESULT = "VERIFY_RESULT"
    REPAIR_START = "REPAIR_START"
    REPAIR_RESULT = "REPAIR_RESULT"
    REVIEW_START = "REVIEW_START"
    REVIEW_RESULT = "REVIEW_RESULT"
    LLM_CALL_START = "LLM_CALL_START"
    LLM_CALL_END = "LLM_CALL_END"
    USER_DIRECTIVE = "USER_DIRECTIVE"
    ASSUMPTION_LOG = "ASSUMPTION_LOG"
    COMPLETE = "COMPLETE"
    FAILED = "FAILED"
    PAUSED = "PAUSED"
    RESUMED = "RESUMED"


class EventLevel(str, Enum):
    INFO = "info"
    WARN = "warn"
    ERROR = "error"


def make_event(
    event_type: EventType | str,
    job_id: str,
    payload: dict[str, Any] | None = None,
    level: EventLevel | str = EventLevel.INFO,
) -> dict[str, Any]:
    """
    Build a canonical event dict.

    All consumers should treat unknown keys as forward-compatible extensions.
    """
    # Use .value for enum instances so we get "JOB_CREATED" not "EventType.JOB_CREATED"
    type_str = event_type.value if isinstance(event_type, EventType) else str(event_type)
    level_str = level.value if isinstance(level, EventLevel) else str(level)
    return {
        "ts": datetime.now(timezone.utc).isoformat(),
        "type": type_str,
        "job_id": job_id,
        "level": level_str,
        **(payload or {}),
    }


def serialize_event(event: dict[str, Any]) -> str:
    """Return a UTF-8 JSON line (no trailing newline)."""
    return json.dumps(event, ensure_ascii=False)
