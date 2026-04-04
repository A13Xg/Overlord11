"""
Jobs API — CRUD + control endpoints.
"""

import re
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

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


class CreateJobRequest(BaseModel):
    title: str
    prompt: str


# ------------------------------------------------------------------
# List / Create
# ------------------------------------------------------------------

@router.get("")
async def list_jobs():
    return [j.to_dict() for j in store.list_jobs()]


@router.post("", status_code=201)
async def create_job(req: CreateJobRequest):
    job = store.create_job(title=req.title.strip(), prompt=req.prompt.strip())
    return job.to_dict()


# ------------------------------------------------------------------
# Single job
# ------------------------------------------------------------------

@router.get("/{job_id}")
async def get_job(job_id: str):
    return _get_or_404(job_id).to_dict()


@router.delete("/{job_id}", status_code=204)
async def delete_job(job_id: str):
    _validate_job_id(job_id)
    if not store.delete_job(job_id):
        raise HTTPException(status_code=404, detail="Job not found")


# ------------------------------------------------------------------
# Control
# ------------------------------------------------------------------

@router.post("/{job_id}/start")
async def start_job(job_id: str):
    job = _get_or_404(job_id)
    if job.status == JobStatus.RUNNING:
        raise HTTPException(status_code=409, detail="Job is already running")
    if job.status == JobStatus.COMPLETED:
        raise HTTPException(status_code=409, detail="Job already completed")
    store.update_job(job_id, status=JobStatus.QUEUED)
    bridge.enqueue(job_id)
    broadcaster.publish(job_id, {
        "type": "STATUS",
        "job_id": job_id,
        "status": JobStatus.QUEUED.value,
    })
    return {"status": "queued", "job_id": job_id}


@router.post("/{job_id}/stop")
async def stop_job(job_id: str):
    job = _get_or_404(job_id)
    if job.status not in (JobStatus.RUNNING, JobStatus.QUEUED, JobStatus.PAUSED):
        raise HTTPException(status_code=409, detail=f"Cannot stop job in state: {job.status}")
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
async def pause_job(job_id: str):
    job = _get_or_404(job_id)
    if job.status != JobStatus.RUNNING:
        raise HTTPException(status_code=409, detail="Can only pause a running job")
    store.update_job(job_id, status=JobStatus.PAUSED)
    broadcaster.publish(job_id, {
        "type": "STATUS",
        "job_id": job_id,
        "status": JobStatus.PAUSED.value,
    })
    return {"status": "paused", "job_id": job_id}


@router.post("/{job_id}/resume")
async def resume_job(job_id: str):
    job = _get_or_404(job_id)
    if job.status != JobStatus.PAUSED:
        raise HTTPException(status_code=409, detail="Job is not paused")
    store.update_job(job_id, status=JobStatus.RUNNING)
    broadcaster.publish(job_id, {
        "type": "STATUS",
        "job_id": job_id,
        "status": JobStatus.RUNNING.value,
    })
    return {"status": "resumed", "job_id": job_id}


@router.post("/{job_id}/restart")
async def restart_job(job_id: str):
    job = _get_or_404(job_id)
    new_title = job.title + " (2)"
    new_job = store.create_job(title=new_title, prompt=job.prompt)
    bridge.enqueue(new_job.job_id)
    store.update_job(new_job.job_id, status=JobStatus.QUEUED)
    broadcaster.publish(new_job.job_id, {
        "type": "STATUS",
        "job_id": new_job.job_id,
        "status": JobStatus.QUEUED.value,
    })
    return new_job.to_dict()
