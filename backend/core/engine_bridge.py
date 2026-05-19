"""
Engine bridge — connects FastAPI to direct provider runtime.

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
- Provider runtime events are emitted through a thread-safe EventStream.
"""

import asyncio
import json
import logging
import re
import sys
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional, Set

_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from .conflict_detector import (
    ConflictResult,
    DomainSet,
    detect_conflicts,
    domains_from_dict,
    domains_to_dict,
    extract_domains,
)
from .event_stream import EventBroadcaster, broadcaster as default_broadcaster
from .mcp_runtime import mcp_runtime
from .provider_runtime import ProviderHTTPError, ProviderRuntime
from .shell_executor import ShellExecutor
from .session_store import Job, JobStatus, SessionStore, store as default_store

log = logging.getLogger("overlord11.engine_bridge")

# Maximum seconds to wait for all prerequisites before giving up.
_DEPENDENCY_TIMEOUT_S = 3600  # 1 hour
_MODEL_STATE_PATH = _PROJECT_ROOT / "workspace" / ".webui_model_state.json"
_DEFAULT_ORCH_PROMPT_PATH = _PROJECT_ROOT / "Orchestrator_systemPrompt.md"


class EngineBridge:
    """Wraps provider runtime and drives job execution with a parallel worker pool."""

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

        # Maps job_id → threading.Event passed into the runtime loop for that
        # job. Allows stop/pause API to interrupt queued/running work.
        self._job_stop_events: dict[str, threading.Event] = {}

        # Maps job_id → DomainSet for jobs that are currently RUNNING or QUEUED.
        # Used by smart_enqueue() to detect resource conflicts.
        self._active_domains: Dict[str, DomainSet] = {}
        self._active_domains_lock = threading.Lock()

    def signal_stop(self, job_id: str) -> None:
        """Signal the runner for job_id to abort any current wait immediately."""
        event = self._job_stop_events.get(job_id)
        if event is not None:
            event.set()

    @staticmethod
    def _build_model_candidates(
        selected_model: str,
        available_models: dict,
        fallback_models: list,
        last_working_model: str = "",
    ) -> list[str]:
        candidates: list[str] = []

        def _push_model(name: str) -> None:
            if name and name not in candidates and name in available_models:
                candidates.append(name)

        _push_model(selected_model)
        _push_model(last_working_model)
        for m in fallback_models or []:
            _push_model(str(m))
        for m in (available_models or {}).keys():
            _push_model(str(m))
        if not candidates and selected_model:
            candidates = [selected_model]
        return candidates

    # ------------------------------------------------------------------
    # Smart enqueue with conflict detection
    # ------------------------------------------------------------------

    def smart_enqueue(
        self,
        job: Job,
        store: SessionStore,
        broadcaster: EventBroadcaster,
    ) -> ConflictResult:
        """
        Analyse job for resource conflicts against all active/queued jobs,
        automatically chain `depends_on` for hard conflicts, then enqueue.

        Returns a ConflictResult so the API can inform the caller.
        """
        # Extract or reuse stored domains
        if job.resource_domains:
            new_domains = domains_from_dict(job.resource_domains)
        else:
            new_domains = extract_domains(job.prompt, job.title)
            domains_dict = domains_to_dict(new_domains)
            store.update_job(job.job_id, resource_domains=domains_dict)

        # Snapshot active domains under lock
        with self._active_domains_lock:
            active_snapshot = dict(self._active_domains)

        # Detect conflicts
        conflict = detect_conflicts(new_domains, active_snapshot)

        if conflict.conflicting_job_ids:
            # Hard conflicts: sequence this job after all conflicting jobs
            existing_deps = set(job.depends_on)
            new_deps = existing_deps | set(conflict.conflicting_job_ids)
            conflict_info = {
                "sequenced_after": conflict.conflicting_job_ids,
                "overlap": conflict.overlap_details,
                "reason": "resource_conflict",
            }
            store.update_job(
                job.job_id,
                depends_on=sorted(new_deps),
                conflict_info=conflict_info,
            )
            broadcaster.publish(job.job_id, {
                "type": "STATUS",
                "job_id": job.job_id,
                "status": "queued",
                "conflict": conflict_info,
                "message": (
                    f"Sequenced after {len(conflict.conflicting_job_ids)} conflicting "
                    f"job(s): {conflict.conflicting_job_ids}"
                ),
            })
            log.info(
                "Job %s: sequenced after %s due to resource conflicts: %s",
                job.job_id, conflict.conflicting_job_ids, conflict.overlap_details,
            )
        elif conflict.soft_conflict_job_ids:
            log.info(
                "Job %s: soft conflict with %s — allowing parallel execution",
                job.job_id, conflict.soft_conflict_job_ids,
            )

        # Register this job's domains as active
        with self._active_domains_lock:
            self._active_domains[job.job_id] = new_domains

        self.enqueue(job.job_id)
        return conflict

    def _release_job_domains(self, job_id: str) -> None:
        """Remove a job from the active domains registry when it finishes."""
        with self._active_domains_lock:
            self._active_domains.pop(job_id, None)

    def get_queue_status(self) -> dict:
        """Return current queue depth and active job count."""
        with self._active_domains_lock:
            active_count = len(self._active_domains)
        return {
            "queue_depth": self.job_queue.qsize(),
            "active_jobs": active_count,
            "max_concurrent": self._max_concurrent_jobs,
            "workers": len([t for t in self._worker_tasks if not t.done()]),
        }

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
        """Mark a job's completion event so dependents can proceed, and release domains."""
        event = self._completion_events.get(job_id)
        if event is not None:
            event.set()
        self._release_job_domains(job_id)

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

        # Pre-populate completion events for dependencies that are already in a
        # terminal state (e.g. completed in a previous server run).  Without
        # this, a freshly-created asyncio.Event would never be set and the
        # dependent job would block until the 1-hour timeout fires.
        for dep_id in job.depends_on:
            dep_job = store.get_job(dep_id)
            if dep_job is not None and dep_job.status in (JobStatus.COMPLETED, JobStatus.FAILED):
                ev = self._ensure_completion_event(dep_id)
                ev.set()  # already finished — unblock immediately

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

        # Skip jobs that were stopped/cancelled while still waiting in queue.
        if job.status in (JobStatus.FAILED, JobStatus.COMPLETED):
            log.info(
                "Job %s: skipping execution — already in terminal state %s",
                job_id, job.status,
            )
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

        stop_event = threading.Event()
        self._job_stop_events[job_id] = stop_event

        def _session_id() -> str:
            now = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
            return f"{now}_{job_id}"

        def _prepare_workspace(session_id: str) -> Path:
            root = _PROJECT_ROOT / "workspace" / session_id
            (root / "output").mkdir(parents=True, exist_ok=True)
            (root / "artifacts" / "logs").mkdir(parents=True, exist_ok=True)
            return root

        loop = asyncio.get_running_loop()

        def _check_blocked() -> bool:
            j = store.get_job(job_id)
            return j is not None and j.status == JobStatus.PAUSED and not stop_event.is_set()

        def _run_sync() -> dict:
            import time
            while _check_blocked():
                time.sleep(0.5)
            if stop_event.is_set():
                return {"status": "failed", "error": "Stopped by user", "output": ""}
            session_id = _session_id()
            workspace = _prepare_workspace(session_id)
            started_at = datetime.now(timezone.utc).isoformat()
            _event = {
                "type": "SESSION_START",
                "job_id": job_id,
                "session_id": session_id,
                "started_at": started_at,
            }
            store.append_event(job_id, _event)
            broadcaster.publish(job_id, _event)

            cfg = json.loads((_PROJECT_ROOT / "config.json").read_text(encoding="utf-8"))
            runtime = ProviderRuntime(cfg)
            runtime_cfg = cfg.get("runtime", {}) or {}
            runtime_mode = str(runtime_cfg.get("mode", "shell_only") or "shell_only").strip().lower()
            shell_cfg = runtime_cfg.get("shell", {}) or {}
            mcp_cfg = cfg.get("mcp", {}) or {}
            prompts_cfg = runtime_cfg.get("prompts", {}) or {}
            providers_cfg = cfg.get("providers", {})
            active_provider = str(providers_cfg.get("active", "openai")).strip()
            provider_cfg = providers_cfg.get(active_provider, {}) or {}
            selected_model = str(provider_cfg.get("model", "")).strip()
            available_models = provider_cfg.get("available_models", {}) or {}
            fallback_models = provider_cfg.get("fallback_models", []) or []

            if not selected_model:
                raise RuntimeError(f"Provider '{active_provider}' has no selected model")

            def _load_model_state() -> dict:
                try:
                    if _MODEL_STATE_PATH.exists():
                        return json.loads(_MODEL_STATE_PATH.read_text(encoding="utf-8"))
                except Exception:
                    pass
                return {}

            def _save_model_state(state: dict) -> None:
                _MODEL_STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
                _MODEL_STATE_PATH.write_text(
                    json.dumps(state, indent=2, ensure_ascii=False) + "\n",
                    encoding="utf-8",
                )

            model_state = _load_model_state()
            last_working = str(model_state.get(active_provider, {}).get("last_working_model", "")).strip()

            # One-time candidate chain build per job.
            candidates = self._build_model_candidates(
                selected_model=selected_model,
                available_models=available_models,
                fallback_models=fallback_models,
                last_working_model=last_working,
            )

            output_parts: list[str] = []
            retry_after_values: list[int] = []

            def _load_orchestrator_system_prompt() -> str:
                if not bool(prompts_cfg.get("inject_orchestrator_system_prompt", True)):
                    return ""
                path_str = str(prompts_cfg.get("orchestrator_system_prompt_path", str(_DEFAULT_ORCH_PROMPT_PATH)))
                p = Path(path_str)
                if not p.is_absolute():
                    p = (_PROJECT_ROOT / p).resolve()
                try:
                    if p.exists():
                        return p.read_text(encoding="utf-8")
                except Exception:
                    return ""
                return ""

            def _on_chunk(text: str) -> None:
                if not text:
                    return
                output_parts.append(text)
                token_event = {
                    "type": "TOKEN",
                    "job_id": job_id,
                    "session_id": session_id,
                    "text": text,
                }
                store.append_event(job_id, token_event)
                broadcaster.publish(job_id, token_event)

            def _provider_call_with_fallback(prompt_text: str, system_prompt_text: str, stream: bool = False):
                provider_result_local = None
                chosen_model_local = None
                for idx, model_name in enumerate(candidates):
                    chosen_model_local = model_name
                    attempt_event = {
                        "type": "PROVIDER_ATTEMPT",
                        "job_id": job_id,
                        "session_id": session_id,
                        "provider": active_provider,
                        "model": model_name,
                        "attempt": idx + 1,
                        "total_candidates": len(candidates),
                    }
                    store.append_event(job_id, attempt_event)
                    broadcaster.publish(job_id, attempt_event)
                    try:
                        if stream:
                            provider_result_local = runtime.execute_prompt_streaming_with_selection(
                                active_provider,
                                model_name,
                                prompt_text,
                                system_prompt=system_prompt_text,
                                on_chunk=_on_chunk,
                            )
                        else:
                            provider_result_local = runtime.execute_prompt_with_selection(
                                active_provider,
                                model_name,
                                prompt_text,
                                system_prompt=system_prompt_text,
                            )
                        return provider_result_local, model_name
                    except ProviderHTTPError as exc:
                        if exc.status_code == 429:
                            if exc.retry_after_s is not None:
                                retry_after_values.append(int(exc.retry_after_s))
                            rl_event = {
                                "type": "RATE_LIMITED",
                                "job_id": job_id,
                                "session_id": session_id,
                                "provider": active_provider,
                                "model": model_name,
                                "retry_num": idx + 1,
                                "wait_s": int(exc.retry_after_s or 0),
                                "action": "try_different_model",
                            }
                            store.append_event(job_id, rl_event)
                            broadcaster.publish(job_id, rl_event)
                            continue
                        if exc.status_code >= 500:
                            err_event = {
                                "type": "PROVIDER_ERROR",
                                "job_id": job_id,
                                "session_id": session_id,
                                "provider": active_provider,
                                "model": model_name,
                                "status_code": exc.status_code,
                                "message": str(exc),
                                "retry_num": idx + 1,
                                "action": "try_next_model",
                            }
                            store.append_event(job_id, err_event)
                            broadcaster.publish(job_id, err_event)
                            continue
                        raise
                return None, chosen_model_local

            def _update_failure_counters(
                signature: str,
                previous_signature: str,
                total_failures: int,
                consecutive_failures: int,
                same_failure_streak: int,
            ) -> tuple[str, int, int, int]:
                total_failures += 1
                consecutive_failures += 1
                if signature == previous_signature and signature:
                    same_failure_streak += 1
                else:
                    same_failure_streak = 1
                return signature, total_failures, consecutive_failures, same_failure_streak

            mcp_enabled = bool(mcp_cfg.get("enabled", False))
            if runtime_mode == "mcp_orchestrated" and mcp_enabled:
                max_steps = int((mcp_cfg.get("max_steps", 10) or 10))
                tool_timeout_s = int((mcp_cfg.get("tool_call_timeout_s", 30) or 30))
                mcp_heal_cfg = mcp_cfg.get("self_heal", {}) or {}
                mcp_heal_enabled = bool(mcp_heal_cfg.get("enabled", True))
                mcp_max_consecutive_failures = max(1, int(mcp_heal_cfg.get("max_consecutive_failures", 3) or 3))
                mcp_max_total_failures = max(1, int(mcp_heal_cfg.get("max_total_failures", 6) or 6))
                mcp_max_same_failure_streak = max(1, int(mcp_heal_cfg.get("max_same_failure_streak", 3) or 3))
                trace: list[dict] = []
                history_lines: list[str] = []
                final_message = ""
                orchestrator_prompt = _load_orchestrator_system_prompt()
                tool_calls = 0
                mcp_total_failures = 0
                mcp_consecutive_failures = 0
                mcp_same_failure_streak = 0
                mcp_last_failure_signature = ""
                max_tool_calls = int((mcp_cfg.get("policy", {}) or {}).get("max_calls_per_job", 20) or 20)
                discovery = mcp_runtime.refresh_tools()
                discovery_ev = {
                    "type": "MCP_DISCOVERY",
                    "job_id": job_id,
                    "session_id": session_id,
                    "discovered_tool_count": int(discovery.get("discovered_tool_count", 0) or 0),
                }
                store.append_event(job_id, discovery_ev)
                broadcaster.publish(job_id, discovery_ev)

                for step in range(1, max_steps + 1):
                    if stop_event.is_set():
                        return {"status": "failed", "error": "Stopped by user", "output": ""}
                    tools = mcp_runtime.tool_catalog()
                    if step == 1 and not tools:
                        final_message = "No MCP tools available from configured local servers."
                        trace.append({"step": step, "action": "mcp_no_tools"})
                        break
                    tools_prompt = json.dumps([
                        {
                            "tool": t.get("full_name"),
                            "description": t.get("description", ""),
                            "input_schema": t.get("inputSchema", {}),
                        }
                        for t in tools
                    ], ensure_ascii=False, indent=2)
                    planner_prompt = (
                        f"Task:\n{job.prompt}\n\n"
                        f"Session workspace:\n{workspace}\n\n"
                        "Decide next action and reply in strict JSON only:\n"
                        "{\"action\":\"tool\",\"tool\":\"<server.tool>\",\"arguments\":{}}\n"
                        "or\n"
                        "{\"action\":\"final\",\"message\":\"<final user-facing answer>\"}\n\n"
                        f"Max tool calls allowed: {max_tool_calls}\n"
                        f"Tool calls used: {tool_calls}\n\n"
                        "Available tools:\n"
                        f"{tools_prompt}\n\n"
                        "Prior execution history:\n"
                        + ("\n".join(history_lines[-20:]) if history_lines else "(none)")
                    )
                    decision_result, chosen_model = _provider_call_with_fallback(planner_prompt, orchestrator_prompt, stream=False)
                    if decision_result is None:
                        break
                    if decision_result.model:
                        state_obj = model_state.get(active_provider, {})
                        state_obj["last_working_model"] = decision_result.model
                        state_obj["updated_at"] = datetime.now(timezone.utc).isoformat()
                        model_state[active_provider] = state_obj
                        _save_model_state(model_state)

                    raw_text = (decision_result.output or "").strip()
                    match = re.search(r"\{[\s\S]*\}", raw_text)
                    payload = {}
                    if match:
                        try:
                            payload = json.loads(match.group(0))
                        except Exception:
                            payload = {}
                    action = str(payload.get("action", "")).strip().lower()
                    if action == "final":
                        final_message = str(payload.get("message", "")).strip() or raw_text
                        trace.append({"step": step, "action": "final", "model": chosen_model, "message": final_message[:5000]})
                        break
                    if action == "tool":
                        if tool_calls >= max_tool_calls:
                            final_message = f"Tool call budget exceeded ({tool_calls}/{max_tool_calls})."
                            trace.append({"step": step, "action": "budget_exhausted"})
                            break
                        tool_name = str(payload.get("tool", "")).strip()
                        arguments = payload.get("arguments", {})
                        if not isinstance(arguments, dict):
                            arguments = {}
                        call_ev = {
                            "type": "MCP_TOOL_CALL",
                            "job_id": job_id,
                            "session_id": session_id,
                            "step": step,
                            "tool": tool_name,
                            "arguments": arguments,
                        }
                        store.append_event(job_id, call_ev)
                        broadcaster.publish(job_id, call_ev)
                        result = mcp_runtime.call_tool(tool_name, arguments, timeout_s=tool_timeout_s)
                        tool_calls += 1
                        result_ev = {
                            "type": "MCP_TOOL_RESULT",
                            "job_id": job_id,
                            "session_id": session_id,
                            "step": step,
                            "tool": tool_name,
                            "result": result,
                        }
                        store.append_event(job_id, result_ev)
                        broadcaster.publish(job_id, result_ev)
                        if bool(result.get("success", False)):
                            mcp_consecutive_failures = 0
                            mcp_same_failure_streak = 0
                            mcp_last_failure_signature = ""
                        else:
                            failure_sig = f"{tool_name}|{str(result.get('error', ''))[:240]}"
                            (
                                mcp_last_failure_signature,
                                mcp_total_failures,
                                mcp_consecutive_failures,
                                mcp_same_failure_streak,
                            ) = _update_failure_counters(
                                failure_sig,
                                mcp_last_failure_signature,
                                mcp_total_failures,
                                mcp_consecutive_failures,
                                mcp_same_failure_streak,
                            )
                            err_ev = {
                                "type": "MCP_ERROR",
                                "job_id": job_id,
                                "session_id": session_id,
                                "step": step,
                                "tool": tool_name,
                                "error": result.get("error"),
                                "self_heal": {
                                    "enabled": mcp_heal_enabled,
                                    "total_failures": mcp_total_failures,
                                    "max_total_failures": mcp_max_total_failures,
                                    "consecutive_failures": mcp_consecutive_failures,
                                    "max_consecutive_failures": mcp_max_consecutive_failures,
                                    "same_failure_streak": mcp_same_failure_streak,
                                    "max_same_failure_streak": mcp_max_same_failure_streak,
                                },
                            }
                            store.append_event(job_id, err_ev)
                            broadcaster.publish(job_id, err_ev)
                            if mcp_heal_enabled and (
                                mcp_total_failures >= mcp_max_total_failures
                                or mcp_consecutive_failures >= mcp_max_consecutive_failures
                                or mcp_same_failure_streak >= mcp_max_same_failure_streak
                            ):
                                final_message = (
                                    "MCP self-heal loop guard triggered: repeated tool failures reached the configured limit. "
                                    f"total={mcp_total_failures}/{mcp_max_total_failures}, "
                                    f"consecutive={mcp_consecutive_failures}/{mcp_max_consecutive_failures}, "
                                    f"same_failure={mcp_same_failure_streak}/{mcp_max_same_failure_streak}."
                                )
                                trace.append({
                                    "step": step,
                                    "action": "self_heal_loop_guard_stop",
                                    "mode": "mcp",
                                    "tool": tool_name,
                                    "error": result.get("error"),
                                    "total_failures": mcp_total_failures,
                                    "consecutive_failures": mcp_consecutive_failures,
                                    "same_failure_streak": mcp_same_failure_streak,
                                })
                                break
                        trace.append({
                            "step": step,
                            "action": "tool",
                            "tool": tool_name,
                            "arguments": arguments,
                            "result": result,
                        })
                        history_lines.append(
                            f"[step {step}] tool={tool_name!r}\nargs={json.dumps(arguments, ensure_ascii=False)}\nresult={json.dumps(result, ensure_ascii=False)}"
                        )
                        continue
                    final_message = raw_text
                    trace.append({"step": step, "action": "final_fallback", "model": chosen_model, "message": final_message[:5000]})
                    break

                if not final_message:
                    final_message = "Job ended without a final response."
                output = final_message.strip()
                (workspace / "output" / "answer.md").write_text(output, encoding="utf-8")
                (workspace / "artifacts" / "logs" / "mcp_trace.json").write_text(
                    json.dumps(trace, indent=2, ensure_ascii=False),
                    encoding="utf-8",
                )
                meta = {
                    "provider": active_provider,
                    "model": model_state.get(active_provider, {}).get("last_working_model", selected_model),
                    "job_id": job_id,
                    "session_id": session_id,
                    "started_at": started_at,
                    "completed_at": datetime.now(timezone.utc).isoformat(),
                    "mode": "mcp_orchestrated",
                }
                (workspace / "artifacts" / "logs" / "provider_response.json").write_text(
                    json.dumps({"meta": meta, "raw": {"mode": "mcp_orchestrated"}}, indent=2, ensure_ascii=False),
                    encoding="utf-8",
                )
                _done_event = {"type": "SESSION_END", "job_id": job_id, "session_id": session_id, "status": "complete"}
                store.append_event(job_id, _done_event)
                broadcaster.publish(job_id, _done_event)
                return {
                    "status": "complete",
                    "session_id": session_id,
                    "output": output,
                    "completion_mode": "mcp_orchestrated",
                    "tool_call_count": tool_calls,
                    "artifact_count": 3,
                }

            shell_enabled = bool(shell_cfg.get("enabled", False))
            if shell_enabled:
                shell_policy = (job.shell_policy or shell_cfg.get("default_policy", "balanced_limited") or "balanced_limited")
                shell_type = (job.shell_type or shell_cfg.get("default_shell", "powershell") or "powershell")
                timeout_s = int(shell_cfg.get("command_timeout_s", 120) or 120)
                max_output_bytes = int(shell_cfg.get("max_output_bytes", 200000) or 200000)
                max_steps = int(shell_cfg.get("max_steps", 10) or 10)
                self_heal_cfg = shell_cfg.get("self_heal", {}) or {}
                self_heal_enabled = bool(self_heal_cfg.get("enabled", True))
                self_heal_max_retries = max(0, int(self_heal_cfg.get("max_retries_per_step", 2) or 0))
                self_heal_max_total_failures = max(1, int(self_heal_cfg.get("max_total_failures", 6) or 6))
                self_heal_max_same_failure_streak = max(1, int(self_heal_cfg.get("max_same_failure_streak", 3) or 3))
                stop_on_blocked = bool(self_heal_cfg.get("stop_on_blocked_command", True))
                orchestrator_prompt = _load_orchestrator_system_prompt()
                shell_executor = ShellExecutor(workspace, policy=shell_policy, shell_type=shell_type)
                trace: list[dict] = []
                history_lines: list[str] = []
                final_message = ""
                consecutive_heal_retries = 0
                total_failures = 0
                same_failure_streak = 0
                last_failure_signature = ""

                for step in range(1, max_steps + 1):
                    if stop_event.is_set():
                        return {"status": "failed", "error": "Stopped by user", "output": ""}
                    planner_prompt = (
                        f"Task:\n{job.prompt}\n\n"
                        f"Session workspace:\n{workspace}\n\n"
                        "Decide next action and reply in strict JSON only:\n"
                        "{\"action\":\"run\",\"command\":\"<shell command>\"}\n"
                        "or\n"
                        "{\"action\":\"final\",\"message\":\"<final user-facing answer>\"}\n\n"
                        f"Self-heal mode: {'enabled' if self_heal_enabled else 'disabled'}\n"
                        f"Current heal retries on latest failure: {consecutive_heal_retries}/{self_heal_max_retries}\n\n"
                        "Prior execution history:\n"
                        + ("\n".join(history_lines[-25:]) if history_lines else "(none)")
                    )
                    decision_result, chosen_model = _provider_call_with_fallback(planner_prompt, orchestrator_prompt, stream=False)
                    if decision_result is None:
                        break
                    if decision_result.model:
                        state_obj = model_state.get(active_provider, {})
                        state_obj["last_working_model"] = decision_result.model
                        state_obj["updated_at"] = datetime.now(timezone.utc).isoformat()
                        model_state[active_provider] = state_obj
                        _save_model_state(model_state)

                    raw_text = (decision_result.output or "").strip()
                    match = re.search(r"\{[\s\S]*\}", raw_text)
                    payload = {}
                    if match:
                        try:
                            payload = json.loads(match.group(0))
                        except Exception:
                            payload = {}
                    action = str(payload.get("action", "")).strip().lower()
                    if action == "final":
                        final_message = str(payload.get("message", "")).strip() or raw_text
                        trace.append({"step": step, "action": "final", "model": chosen_model, "message": final_message[:5000]})
                        break
                    if action == "run":
                        cmd = str(payload.get("command", "")).strip()
                        cmd_ev = {
                            "type": "SHELL_COMMAND",
                            "job_id": job_id,
                            "session_id": session_id,
                            "step": step,
                            "shell": shell_type,
                            "shell_policy": shell_policy,
                            "command": cmd,
                        }
                        store.append_event(job_id, cmd_ev)
                        broadcaster.publish(job_id, cmd_ev)
                        res = shell_executor.execute(cmd, timeout_s=timeout_s, max_output_bytes=max_output_bytes)
                        res_ev = {
                            "type": "SHELL_RESULT",
                            "job_id": job_id,
                            "session_id": session_id,
                            "step": step,
                            "shell": res.shell,
                            "exit_code": res.exit_code,
                            "timed_out": res.timed_out,
                            "blocked": res.blocked,
                            "stdout": res.stdout,
                            "stderr": res.stderr,
                        }
                        store.append_event(job_id, res_ev)
                        broadcaster.publish(job_id, res_ev)
                        trace.append({
                            "step": step,
                            "action": "run",
                            "command": cmd,
                            "exit_code": res.exit_code,
                            "timed_out": res.timed_out,
                            "blocked": res.blocked,
                            "stdout": res.stdout,
                            "stderr": res.stderr,
                        })
                        history_lines.append(
                            f"[step {step}] cmd={cmd!r} exit={res.exit_code} blocked={res.blocked} timed_out={res.timed_out}\n"
                            f"stdout:\n{res.stdout}\n\nstderr:\n{res.stderr}"
                        )
                        if res.exit_code == 0 and not res.blocked and not res.timed_out:
                            consecutive_heal_retries = 0
                            same_failure_streak = 0
                            last_failure_signature = ""
                            continue

                        # Failure path
                        if res.blocked and stop_on_blocked:
                            final_message = (
                                "Command blocked by shell safety policy. "
                                "Job stopped to avoid unsafe host impact."
                            )
                            trace.append({
                                "step": step,
                                "action": "self_heal_stop",
                                "reason": "blocked_command",
                                "shell_policy": shell_policy,
                            })
                            break

                        if not self_heal_enabled:
                            final_message = (
                                f"Command failed (exit={res.exit_code}) and self-heal is disabled."
                            )
                            trace.append({
                                "step": step,
                                "action": "self_heal_disabled_stop",
                                "exit_code": res.exit_code,
                                "blocked": res.blocked,
                                "timed_out": res.timed_out,
                            })
                            break

                        consecutive_heal_retries += 1
                        failure_sig = f"{res.exit_code}|{res.blocked}|{res.timed_out}|{(res.stderr or '')[:240]}"
                        (
                            last_failure_signature,
                            total_failures,
                            _,
                            same_failure_streak,
                        ) = _update_failure_counters(
                            failure_sig,
                            last_failure_signature,
                            total_failures,
                            0,
                            same_failure_streak,
                        )
                        heal_ev = {
                            "type": "SELF_HEAL",
                            "job_id": job_id,
                            "session_id": session_id,
                            "step": step,
                            "retry_num": consecutive_heal_retries,
                            "max_retries": self_heal_max_retries,
                            "total_failures": total_failures,
                            "max_total_failures": self_heal_max_total_failures,
                            "same_failure_streak": same_failure_streak,
                            "max_same_failure_streak": self_heal_max_same_failure_streak,
                            "reason": "blocked" if res.blocked else ("timeout" if res.timed_out else "nonzero_exit"),
                        }
                        store.append_event(job_id, heal_ev)
                        broadcaster.publish(job_id, heal_ev)

                        if consecutive_heal_retries > self_heal_max_retries:
                            final_message = (
                                f"Self-heal retry budget exhausted ({self_heal_max_retries}). "
                                f"Last command exit={res.exit_code}."
                            )
                            trace.append({
                                "step": step,
                                "action": "self_heal_exhausted",
                                "exit_code": res.exit_code,
                                "retries": consecutive_heal_retries,
                            })
                            break
                        if total_failures >= self_heal_max_total_failures:
                            final_message = (
                                "Self-heal loop guard triggered: total command failures reached "
                                f"{total_failures}/{self_heal_max_total_failures}."
                            )
                            trace.append({
                                "step": step,
                                "action": "self_heal_total_failure_limit",
                                "total_failures": total_failures,
                                "max_total_failures": self_heal_max_total_failures,
                                "exit_code": res.exit_code,
                            })
                            break
                        if same_failure_streak >= self_heal_max_same_failure_streak:
                            final_message = (
                                "Self-heal loop guard triggered: same failure repeated "
                                f"{same_failure_streak}/{self_heal_max_same_failure_streak} times."
                            )
                            trace.append({
                                "step": step,
                                "action": "self_heal_same_failure_limit",
                                "same_failure_streak": same_failure_streak,
                                "max_same_failure_streak": self_heal_max_same_failure_streak,
                                "exit_code": res.exit_code,
                            })
                            break
                        continue
                    # Non-JSON/invalid action: treat as final answer to avoid loops.
                    final_message = raw_text
                    trace.append({"step": step, "action": "final_fallback", "model": chosen_model, "message": final_message[:5000]})
                    break

                if not final_message:
                    final_message = "Job ended without a final response."
                output = final_message.strip()
                (workspace / "output" / "answer.md").write_text(output, encoding="utf-8")
                (workspace / "artifacts" / "logs" / "shell_trace.json").write_text(
                    json.dumps(trace, indent=2, ensure_ascii=False),
                    encoding="utf-8",
                )
                meta = {
                    "provider": active_provider,
                    "model": model_state.get(active_provider, {}).get("last_working_model", selected_model),
                    "job_id": job_id,
                    "session_id": session_id,
                    "started_at": started_at,
                    "completed_at": datetime.now(timezone.utc).isoformat(),
                    "shell_policy": shell_policy,
                    "shell_type": shell_type,
                }
                (workspace / "artifacts" / "logs" / "provider_response.json").write_text(
                    json.dumps({"meta": meta, "raw": {"mode": "shell_orchestrated"}}, indent=2, ensure_ascii=False),
                    encoding="utf-8",
                )
                _done_event = {"type": "SESSION_END", "job_id": job_id, "session_id": session_id, "status": "complete"}
                store.append_event(job_id, _done_event)
                broadcaster.publish(job_id, _done_event)
                return {
                    "status": "complete",
                    "session_id": session_id,
                    "output": output,
                    "completion_mode": "shell_orchestrated",
                    "tool_call_count": len([t for t in trace if t.get("action") == "run"]),
                    "artifact_count": 3,
                }

            provider_result, chosen_model = _provider_call_with_fallback(job.prompt, _load_orchestrator_system_prompt(), stream=True)

            if provider_result is None:
                # All candidate models were exhausted, typically due to 429.
                action = (job.rate_limit_action or "try_different_model").strip()
                wait_s = min(retry_after_values) if retry_after_values else 300
                if action == "pause":
                    resume_at = datetime.now(timezone.utc).timestamp() + wait_s
                    resume_iso = datetime.fromtimestamp(resume_at, tz=timezone.utc).isoformat()
                    store.update_job(job_id, status=JobStatus.RATE_LIMITED)
                    pause_ev = {
                        "type": "RATE_LIMITED",
                        "job_id": job_id,
                        "session_id": session_id,
                        "provider": active_provider,
                        "model": chosen_model,
                        "retry_num": len(candidates),
                        "wait_s": wait_s,
                        "resume_at": resume_iso,
                        "action": "pause",
                    }
                    store.append_event(job_id, pause_ev)
                    broadcaster.publish(job_id, pause_ev)
                    slept = 0
                    while slept < wait_s and not stop_event.is_set():
                        if _check_blocked():
                            return {"status": "rate_limited", "error": "Paused by user during rate-limit wait", "output": ""}
                        time.sleep(1.0)
                        slept += 1
                    return {"status": "rate_limited", "error": f"Rate limited across models; paused wait elapsed ({wait_s}s). Use resume/start to retry.", "output": ""}
                if action == "stop":
                    raise RuntimeError("Rate limited across all candidate models; configured action=stop")
                raise RuntimeError("Rate limited across all candidate models; no successful fallback model available")

            # Persist sticky last-known-working model per provider.
            if provider_result.model:
                state_obj = model_state.get(active_provider, {})
                state_obj["last_working_model"] = provider_result.model
                state_obj["updated_at"] = datetime.now(timezone.utc).isoformat()
                model_state[active_provider] = state_obj
                _save_model_state(model_state)

            streamed_output = "".join(output_parts)
            output = (streamed_output or provider_result.output or "").strip()
            if not output:
                raise RuntimeError("Provider returned empty response")

            # Canonical shell-runtime fallback deliverable.
            # Rich deliverables (answer.html/csv/py/...) may also be produced by
            # future tool/orchestrator flows and should take priority in selection.
            (workspace / "output" / "answer.md").write_text(output, encoding="utf-8")
            meta = {
                "provider": provider_result.provider,
                "model": provider_result.model,
                "job_id": job_id,
                "session_id": session_id,
                "started_at": started_at,
                "completed_at": datetime.now(timezone.utc).isoformat(),
            }
            (workspace / "artifacts" / "logs" / "provider_response.json").write_text(
                json.dumps({"meta": meta, "raw": provider_result.raw}, indent=2, ensure_ascii=False),
                encoding="utf-8",
            )
            _done_event = {
                "type": "SESSION_END",
                "job_id": job_id,
                "session_id": session_id,
                "status": "complete",
            }
            store.append_event(job_id, _done_event)
            broadcaster.publish(job_id, _done_event)
            return {
                "status": "complete",
                "session_id": session_id,
                "output": output,
                "completion_mode": "direct_provider",
                "tool_call_count": 0,
                "artifact_count": 2,
            }

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

        result_status = str(result.get("status", "") or "").lower()
        is_complete = result_status == "complete"
        is_rate_limited = result_status == "rate_limited"
        if is_complete:
            job_status = JobStatus.COMPLETED
        elif is_rate_limited:
            job_status = JobStatus.RATE_LIMITED
        else:
            job_status = JobStatus.FAILED
        completion_mode = result.get("completion_mode")
        tool_call_count = int(result.get("tool_call_count", 0) or 0)
        artifact_count = int(result.get("artifact_count", 0) or 0)
        error_msg = result.get("error") if not is_complete else None

        store.update_job(
            job_id,
            status=job_status,
            output=result.get("output", ""),
            session_id=result.get("session_id"),
            error=error_msg,
            completion_mode=completion_mode,
            tool_call_count=tool_call_count,
            artifact_count=artifact_count,
            completed_at=None if is_rate_limited else datetime.now(timezone.utc).isoformat(),
        )
        broadcaster.publish(job_id, {
            "type": "JOB_COMPLETE",
            "job_id": job_id,
            "status": job_status.value,
            "session_id": result.get("session_id"),
            "completion_mode": completion_mode,
            "tool_call_count": tool_call_count,
            "artifact_count": artifact_count,
            "error": error_msg,
        })

    def enqueue(self, job_id: str) -> None:
        """Put a job on the queue for the next available worker."""
        self._ensure_completion_event(job_id)
        self.job_queue.put_nowait(job_id)


# Module-level singleton
bridge = EngineBridge()
