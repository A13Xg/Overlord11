"""
backend/api/jobs.py
====================
Job management REST endpoints.

POST   /api/jobs               Create + enqueue a new job
GET    /api/jobs               List all jobs (optional ?state= filter)
GET    /api/jobs/{job_id}      Get one job
PATCH  /api/jobs/{job_id}      Update state (start/pause/stop)
DELETE /api/jobs/{job_id}      Delete a job

State machine
-------------
  queued → running → completed
                   → failed
  running → paused → running
  any     → failed
"""

import asyncio
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from backend.core.session_store import JOB_STATES, SessionStore
from backend.core.engine_bridge import auto_start_next, start_job

router = APIRouter(prefix="/api/jobs", tags=["jobs"])


# ---------------------------------------------------------------------------
# Request / Response models
# ---------------------------------------------------------------------------

class CreateJobRequest(BaseModel):
    task: str = Field(..., min_length=1, description="Task description / prompt")
    agent: str = Field("orchestrator", description="Agent to run (default: orchestrator)")
    provider: str = Field("anthropic", description="Provider override")
    metadata: dict = Field(default_factory=dict)
    autostart: bool = Field(True, description="Auto-start if no job is currently running")


class PatchJobRequest(BaseModel):
    action: str = Field(..., description="One of: start, pause, resume, stop, restart")


# ---------------------------------------------------------------------------
# Dependency: store
# ---------------------------------------------------------------------------

def get_store() -> SessionStore:
    from backend.main import store  # late import to avoid circular
    return store


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@router.post("", status_code=201)
async def create_job(
    body: CreateJobRequest,
    store: SessionStore = Depends(get_store),
):
    job = store.create_job(
        task=body.task,
        agent=body.agent,
        provider=body.provider,
        metadata=body.metadata,
    )

    if body.autostart and not store.has_running():
        asyncio.create_task(start_job(job, store))

    return job.to_dict()


@router.get("")
def list_jobs(
    state: Optional[str] = Query(None, description="Filter by state"),
    store: SessionStore = Depends(get_store),
):
    return store.list_jobs(state=state)


@router.get("/{job_id}")
def get_job(job_id: str, store: SessionStore = Depends(get_store)):
    job = store.get_job(job_id)
    if not job:
        raise HTTPException(404, f"Job {job_id!r} not found")
    return job.to_dict()


@router.patch("/{job_id}")
async def update_job(
    job_id: str,
    body: PatchJobRequest,
    store: SessionStore = Depends(get_store),
):
    job = store.get_job(job_id)
    if not job:
        raise HTTPException(404, f"Job {job_id!r} not found")

    action = body.action.lower()

    if action == "start":
        if job.state not in ("queued", "paused"):
            raise HTTPException(400, f"Cannot start a job in state {job.state!r}")
        if store.has_running():
            raise HTTPException(409, "Another job is already running")
        asyncio.create_task(start_job(job, store))

    elif action == "pause":
        if job.state != "running":
            raise HTTPException(400, "Can only pause a running job")
        store.transition(job_id, "paused")

    elif action == "resume":
        if job.state != "paused":
            raise HTTPException(400, "Can only resume a paused job")
        store.transition(job_id, "running")

    elif action == "stop":
        if job.state in ("completed", "failed"):
            raise HTTPException(400, f"Job already in terminal state {job.state!r}")
        store.update_job(job_id, state="failed", error="Stopped by user")
        store.transition(job_id, "failed")
        asyncio.create_task(auto_start_next(store))

    elif action == "restart":
        # Create a new job with same params
        new_job = store.create_job(
            task=job.task,
            agent=job.agent,
            provider=job.provider,
            metadata={**job.metadata, "restarted_from": job_id},
        )
        if not store.has_running():
            asyncio.create_task(start_job(new_job, store))
        return {"message": "New job created", "job": new_job.to_dict()}

    else:
        raise HTTPException(400, f"Unknown action {action!r}")

    job = store.get_job(job_id)
    return job.to_dict() if job else {"job_id": job_id}


@router.delete("/{job_id}", status_code=204)
def delete_job(job_id: str, store: SessionStore = Depends(get_store)):
    if not store.delete_job(job_id):
        raise HTTPException(404, f"Job {job_id!r} not found")


# ---------------------------------------------------------------------------
# Bulk control endpoints (start all / pause all / stop all)
# ---------------------------------------------------------------------------

@router.post("/control/start-all")
async def start_all(store: SessionStore = Depends(get_store)):
    """Auto-start next queued job if nothing is running."""
    await auto_start_next(store)
    return {"message": "Auto-start triggered"}


@router.post("/control/pause-all")
def pause_all(store: SessionStore = Depends(get_store)):
    running = [j for j in store.list_jobs(state="running")]
    for job_dict in running:
        store.transition(job_dict["job_id"], "paused")
    return {"paused": len(running)}


@router.post("/control/stop-all")
async def stop_all(store: SessionStore = Depends(get_store)):
    affected = 0
    for state in ("running", "queued", "paused"):
        for job_dict in store.list_jobs(state=state):
            store.update_job(job_dict["job_id"], error="Stopped by user")
            store.transition(job_dict["job_id"], "failed")
            affected += 1
    return {"stopped": affected}
