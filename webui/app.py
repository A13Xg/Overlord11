"""
webui/app.py — FastAPI application for the Overlord11 Tactical WebUI.

API contract (per TacticalWebUI_MasterPlan.md):
    POST   /api/jobs                         Create job
    GET    /api/jobs                         List jobs
    GET    /api/jobs/{id}                    Get state snapshot
    POST   /api/jobs/{id}/start              Start job
    POST   /api/jobs/{id}/pause?pause=true   Pause job
    POST   /api/jobs/{id}/pause?pause=false  Resume job
    POST   /api/jobs/{id}/stop               Stop job
    POST   /api/jobs/{id}/directive          Inject directive (text, severity, tags)
    GET    /api/jobs/{id}/events?since=N     SSE stream (byte-offset resume)
    GET    /api/jobs/{id}/events/tail?n=N    Last N events as JSON array
    GET    /api/jobs/{id}/artifacts          List artifacts (path/size/mtime)
    GET    /api/jobs/{id}/artifacts/<path>   Fetch artifact content
    GET    /api/health                       Health check
    GET    /                                 Serve tactical WebUI
"""

from __future__ import annotations

import asyncio
import json
import secrets
import time
import uuid
from asyncio import Queue
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, AsyncGenerator, Optional

from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles

from .events import EventType, make_event
from .models import (
    ArtifactMeta,
    CreateJobRequest,
    DirectiveRequest,
    JobState,
    JobStatus,
    JobSummary,
)
from . import runner as runner_module
from . import state_store
from .state_store import _safe_artifact_path, _safe_job_id

# ---------------------------------------------------------------------------
# App setup
# ---------------------------------------------------------------------------

app = FastAPI(
    title="Overlord11 Tactical WebUI",
    description="Autonomous mission runner with live SSE telemetry.",
    version="0.1.0",
)

_STATIC = Path(__file__).parent / "static"
if _STATIC.exists():
    app.mount("/static", StaticFiles(directory=str(_STATIC)), name="static")

# Length in bytes of generated job IDs (hex chars = 2× this value)
_JOB_ID_BYTES = 6


# ---------------------------------------------------------------------------
# UI
# ---------------------------------------------------------------------------

@app.get("/", include_in_schema=False)
async def serve_ui():
    index = _STATIC / "index.html"
    if index.exists():
        return FileResponse(str(index))
    return HTMLResponse("<h1>Overlord11 WebUI — static files not found</h1>", status_code=503)


# ---------------------------------------------------------------------------
# Jobs — CRUD
# ---------------------------------------------------------------------------

@app.post("/api/jobs", status_code=201)
async def create_job(req: CreateJobRequest):
    """Create and persist a new job."""
    job_id = secrets.token_hex(_JOB_ID_BYTES)
    state = JobState(
        job_id=job_id,
        goal=req.goal,
        status=JobStatus.PENDING,
        created_at=datetime.now(timezone.utc).isoformat(),
        max_iterations=req.max_iterations,
        max_time_seconds=req.max_time_seconds,
        provider=req.provider,
        model=req.model,
        autonomous=req.autonomous,
        verify_command=req.verify_command,
    )
    state_store.create_job(state)
    return state.model_dump()


@app.get("/api/jobs")
async def list_jobs():
    """Return a lightweight summary list of all jobs."""
    result = []
    for jid in state_store.list_jobs():
        s = state_store.load_state(jid)
        if s:
            result.append(
                JobSummary(
                    job_id=s.job_id,
                    goal=s.goal,
                    status=str(s.status),
                    created_at=s.created_at,
                    iteration=s.iteration,
                    stop_reason=s.stop_reason,
                ).model_dump()
            )
    return result


@app.get("/api/jobs/{job_id}")
async def get_job(job_id: str):
    """Return full state snapshot for a job."""
    _assert_exists(job_id)
    state = state_store.load_state(job_id)
    return state.model_dump()


# ---------------------------------------------------------------------------
# Jobs — lifecycle control
# ---------------------------------------------------------------------------

@app.post("/api/jobs/{job_id}/start", status_code=202)
async def start_job(job_id: str):
    """Start (or restart) a job."""
    _assert_exists(job_id)
    state = state_store.load_state(job_id)
    if state.status not in (JobStatus.PENDING, JobStatus.FAILED, JobStatus.STOPPED):
        raise HTTPException(400, f"Job is already {state.status}")
    asyncio.create_task(runner_module.run_job(job_id))
    return {"job_id": job_id, "message": "started"}


@app.post("/api/jobs/{job_id}/pause")
async def pause_or_resume_job(job_id: str, pause: bool = Query(True)):
    """
    Pause (pause=true) or resume (pause=false) a running job.

    Maps to POST /jobs/{id}/pause?pause=true|false per the MasterPlan API contract.
    """
    _assert_exists(job_id)
    state = state_store.load_state(job_id)
    if pause:
        if state.status != JobStatus.RUNNING:
            raise HTTPException(400, f"Job is not running (status={state.status})")
        runner_module.set_control(job_id, "pause")
        return {"job_id": job_id, "message": "pause requested"}
    else:
        if state.status != JobStatus.PAUSED:
            raise HTTPException(400, f"Job is not paused (status={state.status})")
        runner_module.set_control(job_id, "resume")
        return {"job_id": job_id, "message": "resume requested"}


@app.post("/api/jobs/{job_id}/stop")
async def stop_job(job_id: str):
    """Stop a running or paused job."""
    _assert_exists(job_id)
    runner_module.set_control(job_id, "stop")
    return {"job_id": job_id, "message": "stop requested"}


# ---------------------------------------------------------------------------
# Directives
# ---------------------------------------------------------------------------

@app.post("/api/jobs/{job_id}/directive", status_code=202)
async def post_directive(job_id: str, req: DirectiveRequest):
    """
    Inject a user directive mid-run.

    Persists to pending_directives[] in state.json and broadcasts a
    USER_DIRECTIVE event to all live SSE clients immediately.
    """
    _assert_exists(job_id)
    state = state_store.load_state(job_id)

    directive = {
        "text": req.text,
        "severity": req.severity,
        "tags": req.tags,
        "ts": datetime.now(timezone.utc).isoformat(),
    }
    state.pending_directives.append(directive)
    state_store.save_state(state)

    ev = make_event(
        EventType.USER_DIRECTIVE,
        job_id,
        {
            "text": req.text,
            "severity": req.severity,
            "tags": req.tags,
        },
    )
    state_store.append_event(ev)
    # Broadcast to live SSE clients
    for q in list(runner_module._sse_queues.get(job_id, [])):
        try:
            q.put_nowait(ev)
        except asyncio.QueueFull:
            pass

    return {"job_id": job_id, "message": "directive queued"}


# ---------------------------------------------------------------------------
# SSE event stream
# ---------------------------------------------------------------------------

@app.get("/api/jobs/{job_id}/events")
async def stream_events(
    job_id: str,
    since: int = Query(0, ge=0, description="Byte offset to resume from (from events.jsonl)"),
):
    """
    Server-Sent Events stream.

    Replays persisted events from *since* byte offset, then streams live
    events in real time.  Use `since=<last_offset>` to resume after disconnect.
    If *since* exceeds the current file size it is clamped to EOF (no events
    replayed, only live stream).
    """
    _assert_exists(job_id)

    async def _generate() -> AsyncGenerator[str, None]:
        q = runner_module.subscribe_sse(job_id)
        try:
            # 1. Replay historical events from disk
            from . import state_store as ss
            path = Path(ss._events_path(job_id))
            if path.exists():
                file_size = path.stat().st_size
                # Clamp offset to [0, file_size] — prevents seeking past EOF
                safe_offset = min(since, file_size)
                with open(path, "r", encoding="utf-8") as fh:
                    if safe_offset > 0:
                        fh.seek(safe_offset)
                    for line in fh:
                        line = line.strip()
                        if line:
                            yield f"data: {line}\n\n"

            # 2. Stream live events
            while True:
                try:
                    event = await asyncio.wait_for(q.get(), timeout=30.0)
                    yield f"data: {json.dumps(event, ensure_ascii=False)}\n\n"
                except asyncio.TimeoutError:
                    yield ": keepalive\n\n"  # SSE keepalive comment

        finally:
            runner_module.unsubscribe_sse(job_id, q)

    return StreamingResponse(
        _generate(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )


@app.get("/api/jobs/{job_id}/events/tail")
async def tail_events(
    job_id: str,
    n: int = Query(50, ge=1, le=500, description="Number of events to return."),
):
    """Return the last *n* events as a JSON array."""
    _assert_exists(job_id)
    return state_store.tail_events(job_id, n)


# ---------------------------------------------------------------------------
# Artifacts
# ---------------------------------------------------------------------------

@app.get("/api/jobs/{job_id}/artifacts")
async def list_artifacts(job_id: str):
    """List artifact files with path, size, and mtime."""
    _assert_exists(job_id)
    artifacts = state_store.list_artifacts(job_id)
    return {
        "job_id": job_id,
        "artifacts": [a.model_dump() for a in artifacts],
    }


@app.get("/api/jobs/{job_id}/artifacts/{artifact_path:path}")
async def get_artifact(job_id: str, artifact_path: str):
    """Return the text content of a named artifact."""
    _assert_exists(job_id)
    try:
        _safe_artifact_path(artifact_path)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid artifact path")
    content = state_store.read_artifact(job_id, artifact_path)
    if content is None:
        raise HTTPException(status_code=404, detail=f"Artifact '{artifact_path}' not found")
    return {"job_id": job_id, "path": artifact_path, "content": content}


# ---------------------------------------------------------------------------
# Health
# ---------------------------------------------------------------------------

@app.get("/api/health")
async def health():
    return {"status": "ok", "service": "overlord11-webui", "schema_version": "0.1"}


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _assert_exists(job_id: str) -> None:
    try:
        state = state_store.load_state(job_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid job_id format")
    if state is None:
        raise HTTPException(status_code=404, detail=f"Job '{job_id}' not found")
