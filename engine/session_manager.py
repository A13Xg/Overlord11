"""
engine/session_manager.py
==========================
Manages engine execution sessions.  A session encapsulates all state
needed for one agent run: context messages, tool results, status, and
the associated EventStream.

Session lifecycle
-----------------
  created → running → (paused) → completed | failed
"""

import json
import os
import time
import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional

from engine.event_stream import EventStream

# ---------------------------------------------------------------------------
# Session states (aligned with job system spec)
# ---------------------------------------------------------------------------

class SessionState:
    QUEUED = "queued"
    RUNNING = "running"
    PAUSED = "paused"
    COMPLETED = "completed"
    FAILED = "failed"


# ---------------------------------------------------------------------------
# Session
# ---------------------------------------------------------------------------

class Session:
    """Single execution session."""

    def __init__(
        self,
        session_id: str,
        task: str,
        provider: str = "anthropic",
        agent: str = "orchestrator",
        metadata: Optional[Dict[str, Any]] = None,
    ):
        self.session_id = session_id
        self.task = task
        self.provider = provider
        self.agent = agent
        self.metadata = metadata or {}

        self.state = SessionState.QUEUED
        self.created_at = time.time()
        self.started_at: Optional[float] = None
        self.finished_at: Optional[float] = None

        self.context: List[Dict[str, Any]] = []
        self.result: Optional[str] = None
        self.error: Optional[str] = None
        self.loop_count = 0

        self.stream = EventStream(session_id)

    # ------------------------------------------------------------------

    def start(self) -> None:
        self.state = SessionState.RUNNING
        self.started_at = time.time()
        self.stream.emit_log(f"Session {self.session_id} started")

    def pause(self) -> None:
        self.state = SessionState.PAUSED
        self.stream.emit_log(f"Session {self.session_id} paused")

    def resume(self) -> None:
        self.state = SessionState.RUNNING
        self.stream.emit_log(f"Session {self.session_id} resumed")

    def complete(self, result: str) -> None:
        self.state = SessionState.COMPLETED
        self.finished_at = time.time()
        self.result = result
        self.stream.emit_complete(result=result)

    def fail(self, error: str) -> None:
        self.state = SessionState.FAILED
        self.finished_at = time.time()
        self.error = error
        self.stream.emit_error(error=error)

    def add_context(self, role: str, content: str) -> None:
        """Append a message to the running context."""
        self.context.append({"role": role, "content": content, "ts": time.time()})

    def to_dict(self) -> Dict[str, Any]:
        return {
            "session_id": self.session_id,
            "task": self.task,
            "provider": self.provider,
            "agent": self.agent,
            "state": self.state,
            "created_at": self.created_at,
            "started_at": self.started_at,
            "finished_at": self.finished_at,
            "loop_count": self.loop_count,
            "result": self.result,
            "error": self.error,
            "metadata": self.metadata,
        }


# ---------------------------------------------------------------------------
# SessionManager
# ---------------------------------------------------------------------------

class SessionManager:
    """
    Creates, tracks, and persists sessions.

    All sessions are held in-memory; optionally persisted to disk under
    the configured log_dir for recovery on restart.
    """

    def __init__(self, log_dir: str = "logs/sessions"):
        self._sessions: Dict[str, Session] = {}
        self._log_dir = Path(log_dir)
        self._log_dir.mkdir(parents=True, exist_ok=True)

    # ------------------------------------------------------------------
    # CRUD
    # ------------------------------------------------------------------

    def create(
        self,
        task: str,
        provider: str = "anthropic",
        agent: str = "orchestrator",
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Session:
        """Create and register a new session."""
        session_id = uuid.uuid4().hex[:12]
        session = Session(
            session_id=session_id,
            task=task,
            provider=provider,
            agent=agent,
            metadata=metadata,
        )
        self._sessions[session_id] = session
        self._persist(session)
        return session

    def get(self, session_id: str) -> Optional[Session]:
        return self._sessions.get(session_id)

    def list_all(self) -> List[Dict[str, Any]]:
        return [s.to_dict() for s in self._sessions.values()]

    def list_by_state(self, state: str) -> List[Session]:
        return [s for s in self._sessions.values() if s.state == state]

    def delete(self, session_id: str) -> bool:
        if session_id in self._sessions:
            del self._sessions[session_id]
            manifest = self._log_dir / f"{session_id}.json"
            if manifest.exists():
                manifest.unlink()
            return True
        return False

    # ------------------------------------------------------------------
    # Queue helpers (spec: sequential execution, skip paused/stopped)
    # ------------------------------------------------------------------

    def next_queued(self) -> Optional[Session]:
        """Return the oldest queued session, or None."""
        queued = self.list_by_state(SessionState.QUEUED)
        if not queued:
            return None
        return min(queued, key=lambda s: s.created_at)

    def has_running(self) -> bool:
        return bool(self.list_by_state(SessionState.RUNNING))

    # ------------------------------------------------------------------
    # Persistence
    # ------------------------------------------------------------------

    def _persist(self, session: Session) -> None:
        path = self._log_dir / f"{session.session_id}.json"
        try:
            path.write_text(json.dumps(session.to_dict(), indent=2))
        except OSError:
            pass  # Non-fatal; in-memory state is canonical
