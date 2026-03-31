"""
webui/app.py — FastAPI application for the Overlord11 Tactical WebUI.

Endpoints
---------
POST   /api/jobs                   Create a new job
GET    /api/jobs                   List all jobs
GET    /api/jobs/{id}              Get job state snapshot
POST   /api/jobs/{id}/start        Start (or restart) a job
POST   /api/jobs/{id}/pause        Pause a running job
POST   /api/jobs/{id}/resume       Resume a paused job
POST   /api/jobs/{id}/stop         Stop a job
POST   /api/jobs/{id}/directive    Inject user feedback mid-run
GET    /api/jobs/{id}/events       SSE stream of job events
GET    /api/jobs/{id}/events/tail  Last N events (JSON array)
GET    /api/jobs/{id}/artifacts    List artifacts
GET    /api/jobs/{id}/artifacts/{name}  Read artifact text

GET    /                           Serve the single-page tactical UI
"""

from __future__ import annotations

import asyncio
import json
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import AsyncGenerator

from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles

from .events import EventType, make_event
from .models import CreateJobRequest, DirectiveRequest, JobState, JobStatus, JobSummary
from . import runner as runner_module
from . import state_store
from .state_store import _safe_artifact_name

# ---------------------------------------------------------------------------
# App factory
# ---------------------------------------------------------------------------

_STATIC_DIR = Path(__file__).resolve().parent / "static"

app = FastAPI(
    title="Overlord11 Tactical WebUI",
    description="Autonomous mission runner with live event streaming",
    version="1.0.0",
)

# Serve static files (frontend)
if _STATIC_DIR.exists():
    app.mount("/static", StaticFiles(directory=str(_STATIC_DIR)), name="static")

# ---------------------------------------------------------------------------
# Root — serve the UI
# ---------------------------------------------------------------------------

@app.get("/", response_class=HTMLResponse, include_in_schema=False)
async def serve_ui():
    index = _STATIC_DIR / "index.html"
    if index.exists():
        return HTMLResponse(content=index.read_text(encoding="utf-8"))
    return HTMLResponse(
        content="<h1>Overlord11 Tactical WebUI</h1><p>Frontend not found.</p>"
    )


# ---------------------------------------------------------------------------
# Jobs — CRUD
# ---------------------------------------------------------------------------

@app.post("/api/jobs", response_model=JobState, status_code=201)
async def create_job(req: CreateJobRequest):
    """Create a new job and persist it to disk."""
    job_id = uuid.uuid4().hex[:12]
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
    )
    state_store.create_job(state)
    return state


@app.get("/api/jobs", response_model=list[JobSummary])
async def list_jobs():
    """Return a summary list of all jobs."""
    summaries = []
    for jid in state_store.list_jobs():
        s = state_store.load_state(jid)
        if s:
            summaries.append(
                JobSummary(
                    job_id=s.job_id,
                    goal=s.goal[:120],
                    status=s.status,
                    created_at=s.created_at,
                    iteration=s.iteration,
                    stop_reason=s.stop_reason,
                )
            )
    return summaries


@app.get("/api/jobs/{job_id}", response_model=JobState)
async def get_job(job_id: str):
    """Return the full state snapshot for a job."""
    state = state_store.load_state(job_id)
    if state is None:
        raise HTTPException(status_code=404, detail=f"Job '{job_id}' not found")
    return state


# ---------------------------------------------------------------------------
# Job control
# ---------------------------------------------------------------------------

@app.post("/api/jobs/{job_id}/start", response_model=JobState)
async def start_job(job_id: str):
    """Start a PENDING job (or restart a FAILED/COMPLETE one)."""
    state = state_store.load_state(job_id)
    if state is None:
        raise HTTPException(status_code=404, detail=f"Job '{job_id}' not found")
    if state.status == JobStatus.RUNNING:
        raise HTTPException(status_code=409, detail="Job is already running")

    # Reset for restart if previously terminal
    if state.status in (JobStatus.COMPLETE, JobStatus.FAILED):
        state.status = JobStatus.PENDING
        state.iteration = 0
        state.last_verify_passed = None
        state.last_verify_output = None
        state.stop_reason = None
        state.started_at = None
        state.finished_at = None
        state_store.save_state(state)

    asyncio.create_task(runner_module.run_job(job_id))
    return state_store.load_state(job_id)


@app.post("/api/jobs/{job_id}/pause")
async def pause_job(job_id: str):
    """Signal a running job to pause at the next iteration boundary."""
    _assert_exists(job_id)
    runner_module.set_control(job_id, "pause")
    return {"status": "pause_requested", "job_id": job_id}


@app.post("/api/jobs/{job_id}/resume")
async def resume_job(job_id: str):
    """Resume a paused job."""
    _assert_exists(job_id)
    runner_module.set_control(job_id, "resume")
    return {"status": "resume_requested", "job_id": job_id}


@app.post("/api/jobs/{job_id}/stop")
async def stop_job(job_id: str):
    """Signal a running/paused job to stop."""
    _assert_exists(job_id)
    runner_module.set_control(job_id, "stop")
    return {"status": "stop_requested", "job_id": job_id}


# ---------------------------------------------------------------------------
# Directives (user feedback injection)
# ---------------------------------------------------------------------------

@app.post("/api/jobs/{job_id}/directive")
async def post_directive(job_id: str, req: DirectiveRequest):
    """
    Inject a user directive mid-run.  The event is recorded and the runner
    picks it up at the next iteration.
    """
    state = state_store.load_state(job_id)
    if state is None:
        raise HTTPException(status_code=404, detail=f"Job '{job_id}' not found")

    directive = {
        "ts": datetime.now(timezone.utc).isoformat(),
        "message": req.message,
    }
    state.directives.append(directive)
    state_store.save_state(state)

    event = make_event(
        EventType.USER_DIRECTIVE,
        job_id,
        {"message": req.message},
    )
    state_store.append_event(event)

    # Broadcast to live SSE clients
    for q in list(runner_module._sse_queues.get(job_id, [])):
        try:
            q.put_nowait(event)
        except asyncio.QueueFull:
            pass

    return {"status": "directive_accepted", "job_id": job_id}


# ---------------------------------------------------------------------------
# SSE event stream
# ---------------------------------------------------------------------------

@app.get("/api/jobs/{job_id}/events")
async def stream_events(
    job_id: str,
    offset: int = Query(0, ge=0, description="Byte offset in events.jsonl to resume from"),
):
    """
    Server-Sent Events stream for a job.

    Sends all historical events (from *offset*) first, then stays open and
    pushes new events as they arrive.  Use `offset` to resume after disconnect.
    """
    _assert_exists(job_id)

    async def _generate() -> AsyncGenerator[str, None]:
        q = runner_module.subscribe_sse(job_id)
        try:
            # 1. Replay historical events
            from . import state_store as ss
            path = Path(ss._events_path(job_id))
            if path.exists():
                with open(path, "r", encoding="utf-8") as fh:
                    if offset:
                        fh.seek(offset)
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
                    # Send keepalive comment
                    yield ": keepalive\n\n"
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
    n: int = Query(50, ge=1, le=500),
):
    """Return the last *n* events as a JSON array."""
    _assert_exists(job_id)
    return JSONResponse(content=state_store.tail_events(job_id, n))


# ---------------------------------------------------------------------------
# Artifacts
# ---------------------------------------------------------------------------

@app.get("/api/jobs/{job_id}/artifacts")
async def list_artifacts(job_id: str):
    """List artifact filenames for a job."""
    _assert_exists(job_id)
    return {"job_id": job_id, "artifacts": state_store.list_artifacts(job_id)}


@app.get("/api/jobs/{job_id}/artifacts/{artifact_name}")
async def get_artifact(job_id: str, artifact_name: str):
    """Return the text content of a named artifact."""
    _assert_exists(job_id)
    try:
        _safe_artifact_name(artifact_name)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid artifact name")
    content = state_store.read_artifact(job_id, artifact_name)
    if content is None:
        raise HTTPException(status_code=404, detail=f"Artifact '{artifact_name}' not found")
    return {"job_id": job_id, "name": artifact_name, "content": content}


# ---------------------------------------------------------------------------
# Health
# ---------------------------------------------------------------------------

@app.get("/api/health")
async def health():
    return {"status": "ok", "service": "overlord11-webui"}


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
