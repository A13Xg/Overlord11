from __future__ import annotations

import os
import uuid
from datetime import datetime, timezone
from enum import Enum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from .base import BaseTool


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class SessionAction(str, Enum):
    create_session = "create_session"
    get_session = "get_session"
    update_session = "update_session"
    list_sessions = "list_sessions"
    close_session = "close_session"
    record_note = "record_note"
    get_recent_events = "get_recent_events"


class SessionManagerArgs(BaseModel):
    model_config = ConfigDict(extra="forbid")

    action: SessionAction
    session_id: str | None = None
    data: dict[str, Any] = Field(default_factory=dict)
    limit: int = Field(default=20, ge=1, le=100)


class SessionStore:
    def __init__(self) -> None:
        self._sessions: dict[str, dict[str, Any]] = {}

    def create(self, data: dict[str, Any]) -> dict[str, Any]:
        sid = str(uuid.uuid4())
        now = _now_iso()
        session = {
            "session_id": sid,
            "created_at": now,
            "updated_at": now,
            "status": "active",
            "working_directory": os.environ.get("OVERLORD11_TASK_DIR", os.getcwd()),
            "notes": [],
            "metadata": data.copy(),
            "recent_events": [{"type": "session_created", "at": now}],
        }
        self._sessions[sid] = session
        return session

    def get(self, sid: str) -> dict[str, Any] | None:
        return self._sessions.get(sid)

    def list(self, limit: int) -> list[dict[str, Any]]:
        sessions = list(self._sessions.values())
        sessions.sort(key=lambda x: x["updated_at"], reverse=True)
        return sessions[:limit]


_STORE = SessionStore()


class SessionManagerTool(BaseTool):
    name = "session_manager"
    description = "Manage in-memory execution sessions and events"
    risk_level = "low"
    destructive = False
    supports_dry_run = False
    timeout_behavior = "not_applicable"
    examples = [
        {"action": "create_session", "data": {"purpose": "tool gateway test"}},
        {"action": "record_note", "session_id": "<id>", "data": {"note": "started"}},
    ]
    input_model = SessionManagerArgs

    def execute(self, args: SessionManagerArgs) -> dict[str, Any]:
        action = args.action
        if action == SessionAction.create_session:
            return {"session": _STORE.create(args.data)}

        if action == SessionAction.list_sessions:
            return {"sessions": _STORE.list(args.limit)}

        if not args.session_id:
            raise ValueError("session_id is required for this action")

        session = _STORE.get(args.session_id)
        if not session:
            raise ValueError("session not found")

        now = _now_iso()

        if action == SessionAction.get_session:
            return {"session": session}

        if action == SessionAction.update_session:
            metadata = session.get("metadata", {})
            if isinstance(args.data, dict):
                metadata.update(args.data)
            session["metadata"] = metadata
            session["updated_at"] = now
            session["recent_events"].append({"type": "session_updated", "at": now, "data": args.data})
            return {"session": session}

        if action == SessionAction.record_note:
            note = str(args.data.get("note", "")).strip()
            if not note:
                raise ValueError("data.note is required")
            session["notes"].append({"at": now, "note": note})
            session["updated_at"] = now
            session["recent_events"].append({"type": "note", "at": now, "note": note})
            return {"session": session}

        if action == SessionAction.get_recent_events:
            events = session.get("recent_events", [])
            return {"events": events[-args.limit:]}

        if action == SessionAction.close_session:
            session["status"] = "closed"
            session["updated_at"] = now
            session["recent_events"].append({"type": "session_closed", "at": now})
            return {"session": session}

        raise ValueError("Unsupported action")
