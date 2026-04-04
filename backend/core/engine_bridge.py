"""
backend/core/engine_bridge.py
==============================
Async bridge between the FastAPI backend and the internal engine runner.

Runs the blocking EngineRunner.run() in a thread pool so it doesn't
block the asyncio event loop.  Feeds events back through BackendEventBus.

Pause / Resume / Stop
---------------------
The `_active_sessions` dict maps job_id → engine Session so that the API
layer can propagate pause/resume/stop directly to the running session.
"""

import asyncio
import sys
import os
from pathlib import Path
from typing import Any, Dict, Optional

# Ensure project root is on path so engine/ is importable
_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from engine.runner import EngineRunner
from engine.session_manager import SessionManager, Session
from backend.core.session_store import SessionStore, JobRecord
from backend.core.event_stream import event_bus


# Shared session manager (engine-side)
_session_mgr = SessionManager(log_dir=str(_PROJECT_ROOT / "logs" / "sessions"))

# Shared engine runner
_runner = EngineRunner(session_manager=_session_mgr)

# Map from job_id → running engine Session (so pause/resume/stop can reach it)
_active_sessions: Dict[str, Session] = {}


async def start_job(job: JobRecord, store: SessionStore) -> None:
    """
    Kick off a job asynchronously.
    Updates job state in the store as the engine progresses.
    """
    store.transition(job.job_id, "running")

    # Create an engine session
    session = _session_mgr.create(
        task=job.task,
        provider=job.provider,
        agent=job.agent,
        metadata=job.metadata,
    )

    # Link session to job and register for pause/resume/stop
    store.update_job(job.job_id, session_id=session.session_id)
    _active_sessions[job.job_id] = session

    # Register stream in event bus so SSE clients can subscribe
    event_bus.register(session.session_id, session.stream)

    try:
        # Run blocking engine in thread pool
        loop = asyncio.get_running_loop()
        result = await loop.run_in_executor(None, _runner.run_session, session)

        if result["state"] == "completed":
            store.update_job(job.job_id, result=result.get("result", ""))
            store.transition(job.job_id, "completed")
        else:
            store.update_job(job.job_id, error=result.get("error", "Unknown error"))
            store.transition(job.job_id, "failed")

    except Exception as exc:
        store.update_job(job.job_id, error=str(exc))
        store.transition(job.job_id, "failed")
        session.stream.emit_error(error=str(exc))

    finally:
        _active_sessions.pop(job.job_id, None)

        # Keep stream registered for a brief window so late SSE/WebSocket
        # subscribers can still read the complete event history, then clean up.
        # 60 s is sufficient for any in-flight client reconnect after job end.
        await asyncio.sleep(60)
        event_bus.unregister(session.session_id)


async def auto_start_next(store: SessionStore) -> None:
    """
    If no job is running and a queued job exists, start it.
    Called after each job completes.
    """
    if store.has_running():
        return
    next_job = store.next_queued()
    if next_job:
        asyncio.create_task(start_job(next_job, store))


def pause_job_session(job_id: str) -> bool:
    """
    Pause the engine session for a job.
    Returns True if the session was found and paused.
    """
    session = _active_sessions.get(job_id)
    if session:
        session.pause()
        return True
    return False


def resume_job_session(job_id: str) -> bool:
    """
    Resume a paused engine session.
    Returns True if the session was found and resumed.
    """
    session = _active_sessions.get(job_id)
    if session:
        session.resume()
        return True
    return False


def stop_job_session(job_id: str, reason: str = "Stopped by user") -> bool:
    """
    Stop the engine session for a job immediately.
    Marks the session as failed so the runner loop exits on its next tick.
    Returns True if the session was found.
    """
    session = _active_sessions.get(job_id)
    if session:
        session.fail(reason)
        return True
    return False
