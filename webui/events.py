"""
webui/events.py — Stable event schema for Overlord11 Tactical WebUI.

Schema version: 0.1

Every event shares a common envelope; payloads are free-form dicts.
See docs/EventSchema.md for the full reference.

Event types (canonical):
    JOB_CREATED        job was persisted for the first time
    JOB_STARTING       runner loop is about to begin
    STATUS             generic status change (job state field updated)
    ITERATION          start/end of a runner iteration
    DIRECTIVES_APPLIED pending directives consumed at iteration start
    VERIFY_START       verify gate is running
    VERIFY_RESULT      verify gate finished (pass/fail + output tail)
    VERIFY_RETRY       verify gate re-run (e.g. after venv install)
    DEP_INSTALL_START  package install beginning
    DEP_INSTALL_RESULT package install finished
    REPAIR_START       repair loop triggered after verify failure
    REPAIR_RESULT      repair attempt finished
    REVIEW_START       reviewer gate running
    REVIEW_RESULT      reviewer gate finished
    LLM_CALL_START     LLM API call initiated
    LLM_CALL_END       LLM API call finished (tokens, latency)
    LLM_UNAVAILABLE    LLM call skipped / no API key (dry-run mode)
    PLAN_CREATED       StepPlan written to artifacts/plans/
    STEP_START         individual plan step beginning
    STEP_END           individual plan step finished
    PATCH_APPLY_START  unified diff being applied
    PATCH_APPLY_RESULT unified diff apply finished
    TOOL_START         tool invocation beginning (generic)
    TOOL_END           tool invocation finished (generic)
    USER_DIRECTIVE     feedback/directive injected by the user mid-run
    ASSUMPTION_LOG     runner logged an assumption instead of asking user
    ARTIFACT_WRITTEN   an artifact file was persisted to disk
    COMPLETE           job finished successfully
    FAILED             job stopped with an error
    STOPPED            job stopped by user request
    PAUSED             job paused by request
    RESUMED            job resumed from PAUSED state
    TIME_BUDGET_EXCEEDED  wall-clock budget exceeded
    ITERATION_BUDGET_EXCEEDED  iteration count budget exceeded
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from enum import Enum
from typing import Any

SCHEMA_VERSION = "0.1"


class EventType(str, Enum):
    JOB_CREATED = "JOB_CREATED"
    JOB_STARTING = "JOB_STARTING"
    STATUS = "STATUS"
    ITERATION = "ITERATION"
    DIRECTIVES_APPLIED = "DIRECTIVES_APPLIED"
    VERIFY_START = "VERIFY_START"
    VERIFY_RESULT = "VERIFY_RESULT"
    VERIFY_RETRY = "VERIFY_RETRY"
    DEP_INSTALL_START = "DEP_INSTALL_START"
    DEP_INSTALL_RESULT = "DEP_INSTALL_RESULT"
    REPAIR_START = "REPAIR_START"
    REPAIR_RESULT = "REPAIR_RESULT"
    REVIEW_START = "REVIEW_START"
    REVIEW_RESULT = "REVIEW_RESULT"
    LLM_CALL_START = "LLM_CALL_START"
    LLM_CALL_END = "LLM_CALL_END"
    LLM_UNAVAILABLE = "LLM_UNAVAILABLE"
    PLAN_CREATED = "PLAN_CREATED"
    STEP_START = "STEP_START"
    STEP_END = "STEP_END"
    PATCH_APPLY_START = "PATCH_APPLY_START"
    PATCH_APPLY_RESULT = "PATCH_APPLY_RESULT"
    TOOL_START = "TOOL_START"
    TOOL_END = "TOOL_END"
    USER_DIRECTIVE = "USER_DIRECTIVE"
    ASSUMPTION_LOG = "ASSUMPTION_LOG"
    ARTIFACT_WRITTEN = "ARTIFACT_WRITTEN"
    COMPLETE = "COMPLETE"
    FAILED = "FAILED"
    STOPPED = "STOPPED"
    PAUSED = "PAUSED"
    RESUMED = "RESUMED"
    TIME_BUDGET_EXCEEDED = "TIME_BUDGET_EXCEEDED"
    ITERATION_BUDGET_EXCEEDED = "ITERATION_BUDGET_EXCEEDED"


class EventLevel(str, Enum):
    INFO = "info"
    WARN = "warn"
    ERROR = "error"


def make_event(
    event_type: EventType | str,
    job_id: str,
    payload: dict[str, Any] | None = None,
    level: EventLevel | str = EventLevel.INFO,
    phase: str | None = None,
    iteration: int | None = None,
) -> dict[str, Any]:
    """
    Build a canonical event dict with schema_version.

    All consumers should treat unknown keys as forward-compatible extensions.
    """
    type_str = event_type.value if isinstance(event_type, EventType) else str(event_type)
    level_str = level.value if isinstance(level, EventLevel) else str(level)
    ev: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "ts": datetime.now(timezone.utc).isoformat(),
        "type": type_str,
        "job_id": job_id,
        "level": level_str,
    }
    if phase is not None:
        ev["phase"] = phase
    if iteration is not None:
        ev["iteration"] = iteration
    if payload:
        ev.update(payload)
    return ev


def emit_event(
    append_fn: Any,
    job_id: str,
    event_type: EventType | str,
    level: EventLevel | str = EventLevel.INFO,
    phase: str | None = None,
    iteration: int | None = None,
    **payload: Any,
) -> dict[str, Any]:
    """
    Canonical event emitter.  Builds the event and calls *append_fn* (which
    may also push to SSE queues).

    Usage::
        emit_event(store.append_event, job_id, EventType.VERIFY_START,
                   phase="verify", iteration=3)

    Returns the emitted event dict.
    """
    ev = make_event(
        event_type,
        job_id,
        payload=payload or None,
        level=level,
        phase=phase,
        iteration=iteration,
    )
    append_fn(ev)
    return ev


def serialize_event(event: dict[str, Any]) -> str:
    """Return a UTF-8 JSON line (no trailing newline)."""
    return json.dumps(event, ensure_ascii=False)
