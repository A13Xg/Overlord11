"""
backend/core/engine_bridge.py
==============================
Async bridge between the FastAPI backend and the internal engine runner.

Runs the blocking EngineRunner.run() in a thread pool so it doesn't
block the asyncio event loop.  Feeds events back through BackendEventBus.
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
from engine.session_manager import SessionManager
from backend.core.session_store import SessionStore, JobRecord
from backend.core.event_stream import event_bus


# Shared session manager (engine-side)
_session_mgr = SessionManager(log_dir=str(_PROJECT_ROOT / "logs" / "sessions"))

# Shared engine runner
_runner = EngineRunner(session_manager=_session_mgr)


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

    # Link session to job
    store.update_job(job.job_id, session_id=session.session_id)

    # Register stream in event bus so SSE clients can subscribe
    event_bus.register(session.session_id, session.stream)

    try:
        # Run blocking engine in thread pool
        result = await asyncio.get_event_loop().run_in_executor(
            None, _runner.run_session, session
        )

        if result["state"] == "completed":
            store.update_job(
                job.job_id,
                state="completed",
                result=result.get("result", ""),
            )
            store.transition(job.job_id, "completed")
        else:
            store.update_job(
                job.job_id,
                state="failed",
                error=result.get("error", "Unknown error"),
            )
            store.transition(job.job_id, "failed")

    except Exception as exc:
        store.update_job(job.job_id, state="failed", error=str(exc))
        store.transition(job.job_id, "failed")
        session.stream.emit_error(error=str(exc))

    finally:
        # Keep stream registered for a short window so late subscribers
        # can still read history, then unregister
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
