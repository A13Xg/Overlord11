"""
Jobs API — CRUD + control endpoints.

Auto-start behaviour
--------------------
Jobs are auto-started by default (auto_start=True in CreateJobRequest).
On creation the engine bridge runs conflict detection and either:
  - enqueues immediately if no hard resource conflicts exist, or
  - chains `depends_on` to the conflicting jobs so it starts after them.
"""

import re
from datetime import datetime, timezone
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from ..auth.auth import require_auth
from ..core.conflict_detector import extract_domains, domains_to_dict
from ..core.engine_bridge import bridge
from ..core.event_stream import broadcaster
from ..core.session_store import Job, JobStatus, store

router = APIRouter(prefix="/api/jobs", tags=["jobs"])

_JOB_ID_RE = re.compile(r"^[a-f0-9]{8,64}$")


def _validate_job_id(job_id: str) -> None:
    if not _JOB_ID_RE.match(job_id):
        raise HTTPException(status_code=400, detail="Invalid job_id format")


def _get_or_404(job_id: str) -> Job:
    _validate_job_id(job_id)
    job = store.get_job(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found")
    return job


_VALID_RL_ACTIONS = {"pause", "stop", "try_different_model"}


class CreateJobRequest(BaseModel):
    title: str
    prompt: str
    rate_limit_action: str = "pause"   # "pause" | "stop" | "try_different_model"
    auto_start: bool = True            # auto-enqueue immediately after creation
    depends_on: List[str] = []         # explicit prerequisite job IDs (optional)
    priority: int = 0                  # 0=normal, -1=high, 1=low


# ------------------------------------------------------------------
# List / Create / Queue status
# ------------------------------------------------------------------

@router.get("")
async def list_jobs(_session: dict = Depends(require_auth)):
    return [j.to_dict() for j in store.list_jobs()]


@router.get("/queue-status")
async def queue_status(_session: dict = Depends(require_auth)):
    """Return current worker pool and queue depth."""
    return bridge.get_queue_status()


@router.post("", status_code=201)
async def create_job(req: CreateJobRequest, _session: dict = Depends(require_auth)):
    action = req.rate_limit_action if req.rate_limit_action in _VALID_RL_ACTIONS else "pause"

    # Pre-extract resource domains so conflict detection happens before creation
    domains = extract_domains(req.prompt.strip(), req.title.strip())
    domains_dict = domains_to_dict(domains)

    job = store.create_job(
        title=req.title.strip(),
        prompt=req.prompt.strip(),
        depends_on=req.depends_on,
        rate_limit_action=action,
        resource_domains=domains_dict,
        priority=req.priority,
        auto_started=req.auto_start,
    )

    conflict_result = None
    if req.auto_start:
        # smart_enqueue: detect conflicts, auto-chain depends_on, then enqueue
        conflict_result = bridge.smart_enqueue(job, store, broadcaster)
        # Re-fetch job after smart_enqueue may have updated depends_on
        job = store.get_job(job.job_id) or job

    response = job.to_dict()
    if conflict_result is not None:
        response["_conflict"] = {
            "hard": conflict_result.conflicting_job_ids,
            "soft": conflict_result.soft_conflict_job_ids,
            "can_run_parallel": conflict_result.can_run_parallel,
            "sequenced": bool(conflict_result.conflicting_job_ids),
        }
    return response


# ------------------------------------------------------------------
# Single job
# ------------------------------------------------------------------

@router.get("/{job_id}")
async def get_job(job_id: str, _session: dict = Depends(require_auth)):
    return _get_or_404(job_id).to_dict()


@router.delete("/{job_id}", status_code=204)
async def delete_job(job_id: str, _session: dict = Depends(require_auth)):
    _validate_job_id(job_id)
    if not store.delete_job(job_id):
        raise HTTPException(status_code=404, detail="Job not found")


# ------------------------------------------------------------------
# Control
# ------------------------------------------------------------------

@router.post("/{job_id}/start")
async def start_job(job_id: str, _session: dict = Depends(require_auth)):
    job = _get_or_404(job_id)
    if job.status == JobStatus.RUNNING:
        raise HTTPException(status_code=409, detail="Job is already running")
    if job.status == JobStatus.COMPLETED:
        raise HTTPException(status_code=409, detail="Job already completed")
    if job.status == JobStatus.QUEUED:
        raise HTTPException(status_code=409, detail="Job is already queued — use STOP then START to re-queue")
    store.update_job(job_id, status=JobStatus.QUEUED)
    bridge.enqueue(job_id)
    broadcaster.publish(job_id, {
        "type": "STATUS",
        "job_id": job_id,
        "status": JobStatus.QUEUED.value,
    })
    return {"status": "queued", "job_id": job_id}


@router.post("/{job_id}/stop")
async def stop_job(job_id: str, _session: dict = Depends(require_auth)):
    job = _get_or_404(job_id)
    stoppable = (JobStatus.RUNNING, JobStatus.QUEUED, JobStatus.PAUSED, JobStatus.RATE_LIMITED)
    if job.status not in stoppable:
        raise HTTPException(status_code=409, detail=f"Cannot stop job in state: {job.status}")
    # Signal the runner's stop_event so any in-progress rate-limit wait exits immediately.
    bridge.signal_stop(job_id)
    store.update_job(
        job_id,
        status=JobStatus.FAILED,
        error="Stopped by user",
        completed_at=datetime.now(timezone.utc).isoformat(),
    )
    broadcaster.publish(job_id, {
        "type": "STATUS",
        "job_id": job_id,
        "status": JobStatus.FAILED.value,
        "error": "Stopped by user",
    })
    return {"status": "stopped", "job_id": job_id}


@router.post("/{job_id}/pause")
async def pause_job(job_id: str, _session: dict = Depends(require_auth)):
    job = _get_or_404(job_id)
    pausable = (JobStatus.RUNNING, JobStatus.RATE_LIMITED)
    if job.status not in pausable:
        raise HTTPException(status_code=409, detail="Can only pause a running or rate-limited job")
    # Signal the runner so a rate-limit wait exits and the job parks in PAUSED state.
    bridge.signal_stop(job_id)
    store.update_job(job_id, status=JobStatus.PAUSED)
    broadcaster.publish(job_id, {
        "type": "STATUS",
        "job_id": job_id,
        "status": JobStatus.PAUSED.value,
    })
    return {"status": "paused", "job_id": job_id}


@router.post("/{job_id}/resume")
async def resume_job(job_id: str, _session: dict = Depends(require_auth)):
    job = _get_or_404(job_id)
    resumable = (JobStatus.PAUSED, JobStatus.RATE_LIMITED)
    if job.status not in resumable:
        raise HTTPException(status_code=409, detail="Job is not paused or rate-limited")
    store.update_job(job_id, status=JobStatus.RUNNING)
    broadcaster.publish(job_id, {
        "type": "STATUS",
        "job_id": job_id,
        "status": JobStatus.RUNNING.value,
    })
    return {"status": "resumed", "job_id": job_id}


@router.post("/{job_id}/restart")
async def restart_job(job_id: str, _session: dict = Depends(require_auth)):
    job = _get_or_404(job_id)
    new_title = job.title + " (2)"
    new_job = store.create_job(
        title=new_title,
        prompt=job.prompt,
        rate_limit_action=job.rate_limit_action,
    )
    bridge.enqueue(new_job.job_id)
    store.update_job(new_job.job_id, status=JobStatus.QUEUED)
    broadcaster.publish(new_job.job_id, {
        "type": "STATUS",
        "job_id": new_job.job_id,
        "status": JobStatus.QUEUED.value,
    })
    return new_job.to_dict()
