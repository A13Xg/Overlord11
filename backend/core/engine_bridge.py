"""
Engine bridge — connects FastAPI to engine/runner.py.

Parallel Job Execution
-----------------------
Jobs are processed by a configurable worker pool rather than a single worker.
The pool size is set via config  orchestration.parallel.max_concurrent_jobs
(default: 2).

Dependency gating
-----------------
A job may declare  depends_on: [job_id, ...]  in its Job record.  The bridge
will hold that job in QUEUED state until every listed prerequisite has
reached COMPLETED status.  If any prerequisite fails, the dependent job is
immediately failed with a clear error message rather than waiting forever.

Dependency checking uses asyncio.Event objects so the wait is non-blocking
and does not consume CPU.  Events are registered when a job is enqueued and
set when the job completes or fails.

Race conditions
---------------
- asyncio.Semaphore caps concurrent job count (one semaphore per bridge).
- N worker coroutines share a single asyncio.Queue; asyncio guarantees only
  one coroutine receives each item from a Queue.get() call.
- SessionStore mutations are protected by its own threading.Lock.
- EngineRunner events are emitted through a thread-safe EventStream.
"""

import asyncio
import logging
import sys
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from engine.runner import EngineRunner

from .event_stream import EventBroadcaster, broadcaster as default_broadcaster
from .session_store import Job, JobStatus, SessionStore, store as default_store

log = logging.getLogger("overlord11.engine_bridge")

# Maximum seconds to wait for all prerequisites before giving up.
_DEPENDENCY_TIMEOUT_S = 3600  # 1 hour


class EngineBridge:
    """Wraps EngineRunner and drives job execution with a parallel worker pool."""

    def __init__(self) -> None:
        self.job_queue: asyncio.Queue = asyncio.Queue()

        # These are initialised in start_worker() once the event loop is running.
        self._semaphore: Optional[asyncio.Semaphore] = None
        self._max_concurrent_jobs: int = 2

        self._worker_tasks: list[asyncio.Task] = []
        self._shutdown_requested = False

        # Maps job_id → asyncio.Event.  Set when the job reaches a terminal
        # state (COMPLETED or FAILED).  Used by dependency gating.
        # Capped at _MAX_COMPLETION_EVENTS entries: oldest are evicted once the
        # limit is reached (they are only needed while dependents are waiting).
        self._completion_events: dict[str, asyncio.Event] = {}
        self._MAX_COMPLETION_EVENTS = 1000

        # Maps job_id → threading.Event passed into the EngineRunner for that
        # job.  Allows external callers (stop/pause API) to interrupt an
        # in-progress rate-limit wait without waiting for it to expire.
        self._job_stop_events: dict[str, threading.Event] = {}

    def signal_stop(self, job_id: str) -> None:
        """Signal the runner for job_id to abort any current wait immediately."""
        event = self._job_stop_events.get(job_id)
        if event is not None:
            event.set()

    # ------------------------------------------------------------------
    # Worker lifecycle
    # ------------------------------------------------------------------

    def start_worker(self, config: Optional[dict] = None) -> None:
        """
        Start the background worker pool that processes jobs.

        Call once from the FastAPI lifespan after the event loop is running.
        Safe to call multiple times — subsequent calls are no-ops if workers
        are already running.
        """
        if self._worker_tasks and not all(t.done() for t in self._worker_tasks):
            return  # already running

        self._shutdown_requested = False
        self._max_concurrent_jobs = (
            (config or {})
            .get("orchestration", {})
            .get("parallel", {})
            .get("max_concurrent_jobs", 2)
        )
        self._semaphore = asyncio.Semaphore(self._max_concurrent_jobs)

        self._worker_tasks = [
            asyncio.create_task(self._worker_loop(worker_id=i))
            for i in range(self._max_concurrent_jobs)
        ]
        log.info(
            "Engine bridge: %d worker(s) started (max_concurrent_jobs=%d)",
            self._max_concurrent_jobs,
            self._max_concurrent_jobs,
        )

    async def stop_worker(self) -> None:
        """Cancel all worker tasks and await clean shutdown."""
        self._shutdown_requested = True
        for task in self._worker_tasks:
            task.cancel()
        await asyncio.gather(*self._worker_tasks, return_exceptions=True)
        self._worker_tasks.clear()
        log.info("Engine bridge: all workers stopped")

    # ------------------------------------------------------------------
    # Worker loop (N instances run concurrently)
    # ------------------------------------------------------------------

    async def _worker_loop(self, worker_id: int) -> None:
        log.debug("Worker %d: started", worker_id)
        try:
            while True:
                job_id = await self.job_queue.get()
                try:
                    async with self._semaphore:  # type: ignore[union-attr]
                        await self._run_job_with_deps(
                            job_id=job_id,
                            store=default_store,
                            broadcaster=default_broadcaster,
                            worker_id=worker_id,
                        )
                except Exception as exc:
                    log.error("Worker %d: unhandled error for job %s: %s", worker_id, job_id, exc)
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
                    self._signal_completion(job_id)
        except asyncio.CancelledError:
            log.debug("Worker %d: cancelled", worker_id)
            return

    # ------------------------------------------------------------------
    # Dependency gating
    # ------------------------------------------------------------------

    def _ensure_completion_event(self, job_id: str) -> asyncio.Event:
        """Return (and register if missing) the completion event for a job.

        Evicts the oldest already-set events when the dict grows beyond the cap
        so that long-running servers do not leak memory.
        """
        if job_id not in self._completion_events:
            # Evict completed (already-set) events if we're at the cap.
            if len(self._completion_events) >= self._MAX_COMPLETION_EVENTS:
                to_remove = [
                    jid for jid, ev in self._completion_events.items() if ev.is_set()
                ]
                for jid in to_remove[:max(1, len(to_remove))]:
                    del self._completion_events[jid]
            self._completion_events[job_id] = asyncio.Event()
        return self._completion_events[job_id]

    def _signal_completion(self, job_id: str) -> None:
        """Mark a job's completion event so dependents can proceed."""
        event = self._completion_events.get(job_id)
        if event is not None:
            event.set()

    async def _wait_for_dependencies(
        self,
        job: Job,
        store: SessionStore,
        broadcaster: EventBroadcaster,
    ) -> bool:
        """
        Block until all jobs listed in job.depends_on reach a terminal state.

        Returns True if all prerequisites completed successfully.
        Returns False if any prerequisite failed, causing this job to be
        failed immediately.
        """
        if not job.depends_on:
            return True

        log.info(
            "Job %s: waiting for %d prerequisite(s): %s",
            job.job_id, len(job.depends_on), job.depends_on,
        )
        broadcaster.publish(job.job_id, {
            "type": "STATUS",
            "job_id": job.job_id,
            "status": "waiting_for_dependencies",
            "depends_on": job.depends_on,
        })

        try:
            await asyncio.wait_for(
                asyncio.gather(*[
                    self._ensure_completion_event(dep_id).wait()
                    for dep_id in job.depends_on
                ]),
                timeout=_DEPENDENCY_TIMEOUT_S,
            )
        except asyncio.TimeoutError:
            msg = (
                f"Timed out after {_DEPENDENCY_TIMEOUT_S}s waiting for "
                f"prerequisites: {job.depends_on}"
            )
            log.warning("Job %s: %s", job.job_id, msg)
            store.update_job(
                job.job_id,
                status=JobStatus.FAILED,
                error=msg,
                completed_at=datetime.now(timezone.utc).isoformat(),
            )
            broadcaster.publish(job.job_id, {
                "type": "ERROR",
                "job_id": job.job_id,
                "message": msg,
            })
            return False

        # Check that all prerequisites actually completed (not failed)
        failed_deps = [
            dep_id
            for dep_id in job.depends_on
            if (j := store.get_job(dep_id)) is not None and j.status == JobStatus.FAILED
        ]
        if failed_deps:
            msg = f"Prerequisite job(s) failed: {failed_deps}"
            log.warning("Job %s: %s", job.job_id, msg)
            store.update_job(
                job.job_id,
                status=JobStatus.FAILED,
                error=msg,
                completed_at=datetime.now(timezone.utc).isoformat(),
            )
            broadcaster.publish(job.job_id, {
                "type": "ERROR",
                "job_id": job.job_id,
                "message": msg,
            })
            return False

        log.info("Job %s: all prerequisites satisfied, starting", job.job_id)
        return True

    # ------------------------------------------------------------------
    # Job execution
    # ------------------------------------------------------------------

    async def _run_job_with_deps(
        self,
        job_id: str,
        store: SessionStore,
        broadcaster: EventBroadcaster,
        worker_id: int,
    ) -> None:
        """Gate on dependencies, then execute the job."""
        job = store.get_job(job_id)
        if job is None:
            log.warning("Worker %d: job %s not found in store", worker_id, job_id)
            return

        # Register completion event before any await so dependents can
        # subscribe immediately.
        self._ensure_completion_event(job_id)

        ok = await self._wait_for_dependencies(job, store, broadcaster)
        if not ok:
            return  # already marked FAILED by _wait_for_dependencies

        await self.run_job(
            job_id=job_id,
            store=store,
            broadcaster=broadcaster,
        )

    async def run_job(
        self,
        job_id: str,
        store: SessionStore,
        broadcaster: EventBroadcaster,
    ) -> None:
        """Execute a single job synchronously in the thread pool."""
        job = store.get_job(job_id)
        if job is None:
            return

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

        # stop_event lets the runner abort a rate-limit wait early when the
        # job is paused, cancelled, or the server is shutting down.
        stop_event = threading.Event()
        self._job_stop_events[job_id] = stop_event

        def _event_callback(event: dict) -> None:
            """Sync callback invoked from EngineRunner (may be on a thread-pool thread)."""
            store.append_event(job_id, event)
            broadcaster.publish(job_id, {**event, "job_id": job_id})

            # Drive job status transitions triggered by engine events.
            event_type = event.get("type", "")
            if event_type == "RATE_LIMITED":
                store.update_job(job_id, status=JobStatus.RATE_LIMITED)
                broadcaster.publish(job_id, {
                    "type": "STATUS",
                    "job_id": job_id,
                    "status": JobStatus.RATE_LIMITED.value,
                    "wait_s": event.get("wait_s"),
                    "resume_at": event.get("resume_at"),
                })
            elif event_type == "AGENT_START":
                j = store.get_job(job_id)
                if j is not None and j.status == JobStatus.RATE_LIMITED:
                    store.update_job(job_id, status=JobStatus.RUNNING)
                    broadcaster.publish(job_id, {
                        "type": "STATUS",
                        "job_id": job_id,
                        "status": JobStatus.RUNNING.value,
                    })

        runner = EngineRunner(
            verbose=False,
            stop_event=stop_event,
            rate_limit_action=job.rate_limit_action,
        )
        runner.events.callbacks.append(_event_callback)

        loop = asyncio.get_running_loop()

        def _check_paused() -> bool:
            j = store.get_job(job_id)
            return j is not None and j.status == JobStatus.PAUSED

        def _run_sync() -> dict:
            import time
            while _check_paused():
                time.sleep(0.5)
            return runner.run(job.prompt)

        try:
            result = await loop.run_in_executor(None, _run_sync)
        except Exception as exc:
            stop_event.set()
            self._job_stop_events.pop(job_id, None)
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
        finally:
            stop_event.set()
            self._job_stop_events.pop(job_id, None)

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
        """Put a job on the queue for the next available worker."""
        self._ensure_completion_event(job_id)
        self.job_queue.put_nowait(job_id)


# Module-level singleton
bridge = EngineBridge()
