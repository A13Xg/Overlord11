"""
Engine bridge — connects FastAPI to engine/runner.py.
"""

import asyncio
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

# Ensure project root is on sys.path so engine package is importable
_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from engine.runner import EngineRunner

from .event_stream import EventBroadcaster, broadcaster as default_broadcaster
from .session_store import Job, JobStatus, SessionStore, store as default_store


class EngineBridge:
    """Wraps EngineRunner and drives job execution with status tracking."""

    def __init__(self) -> None:
        self.job_queue: asyncio.Queue = asyncio.Queue()
        self._current_job_id: Optional[str] = None
        self._worker_task: Optional[asyncio.Task] = None

    # ------------------------------------------------------------------
    # Worker lifecycle
    # ------------------------------------------------------------------

    def start_worker(self) -> asyncio.Task:
        """Start the background worker that processes jobs sequentially."""
        self._worker_task = asyncio.create_task(self._worker_loop())
        return self._worker_task

    async def _worker_loop(self) -> None:
        while True:
            job_id = await self.job_queue.get()
            try:
                await self.run_job(
                    job_id=job_id,
                    store=default_store,
                    broadcaster=default_broadcaster,
                )
            except Exception as exc:
                default_store.update_job(
                    job_id,
                    status=JobStatus.FAILED,
                    error=str(exc),
                    completed_at=datetime.now(timezone.utc).isoformat(),
                )
                default_broadcaster.publish(job_id, {
                    "type": "ERROR",
                    "job_id": job_id,
                    "message": str(exc),
                })
            finally:
                self.job_queue.task_done()
                self._current_job_id = None

    # ------------------------------------------------------------------
    # Job execution
    # ------------------------------------------------------------------

    async def run_job(
        self,
        job_id: str,
        store: SessionStore,
        broadcaster: EventBroadcaster,
    ) -> None:
        job = store.get_job(job_id)
        if job is None:
            return

        self._current_job_id = job_id

        store.update_job(
            job_id,
            status=JobStatus.RUNNING,
            started_at=datetime.now(timezone.utc).isoformat(),
            error=None,
        )
        broadcaster.publish(job_id, {
            "type": "STATUS",
            "job_id": job_id,
            "status": JobStatus.RUNNING.value,
        })

        def _event_callback(event: dict) -> None:
            """Sync callback — called from within EngineRunner.run()."""
            # Append to job event list
            job_obj = store.get_job(job_id)
            if job_obj is not None:
                job_obj.events.append(event)
            broadcaster.publish(job_id, {**event, "job_id": job_id})

        runner = EngineRunner(verbose=False)
        runner.events.callbacks.append(_event_callback)

        loop = asyncio.get_running_loop()

        def _check_paused() -> bool:
            j = store.get_job(job_id)
            return j is not None and j.status == JobStatus.PAUSED

        def _run_sync() -> dict:
            """Execute the engine synchronously (runs in thread-pool)."""
            import time
            # Honour paused state by busy-waiting before starting
            while _check_paused():
                time.sleep(0.5)
            return runner.run(job.prompt)

        try:
            result = await loop.run_in_executor(None, _run_sync)
        except Exception as exc:
            store.update_job(
                job_id,
                status=JobStatus.FAILED,
                error=str(exc),
                completed_at=datetime.now(timezone.utc).isoformat(),
            )
            broadcaster.publish(job_id, {
                "type": "ERROR",
                "job_id": job_id,
                "message": str(exc),
            })
            return

        store.update_job(
            job_id,
            status=JobStatus.COMPLETED,
            output=result.get("output", ""),
            session_id=result.get("session_id"),
            completed_at=datetime.now(timezone.utc).isoformat(),
        )
        broadcaster.publish(job_id, {
            "type": "JOB_COMPLETE",
            "job_id": job_id,
            "status": JobStatus.COMPLETED.value,
            "session_id": result.get("session_id"),
        })

    def enqueue(self, job_id: str) -> None:
        self.job_queue.put_nowait(job_id)


# Module-level singleton
bridge = EngineBridge()
