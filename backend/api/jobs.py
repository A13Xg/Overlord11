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
from pathlib import Path
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import PlainTextResponse
from pydantic import BaseModel

from ..auth.auth import require_auth
from ..core.conflict_detector import extract_domains, domains_to_dict
from ..core.engine_bridge import bridge
from ..core.event_stream import broadcaster
from ..core.session_store import Job, JobStatus, store

router = APIRouter(prefix="/api/jobs", tags=["jobs"])

_BASE_DIR = Path(__file__).resolve().parent.parent.parent
_WORKSPACE_DIR = _BASE_DIR / "workspace"

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
    rate_limit_action: str = "try_different_model"   # "pause" | "stop" | "try_different_model"
    auto_start: bool = True            # auto-enqueue immediately after creation
    depends_on: List[str] = []         # explicit prerequisite job IDs (optional)
    priority: int = 0                  # 0=normal, -1=high, 1=low
    required_output_ext: Optional[str] = None


# ------------------------------------------------------------------
# List / Create / Queue status
# ------------------------------------------------------------------

@router.get("")
async def list_jobs(
    _session: dict = Depends(require_auth),
    status: Optional[str] = Query(None, description="Filter by status (e.g. completed, running, failed)"),
    q: Optional[str] = Query(None, description="Search by title or prompt (case-insensitive)"),
    limit: Optional[int] = Query(None, ge=1, le=500, description="Max number of results"),
):
    jobs = store.list_jobs()
    if status:
        try:
            status_filter = JobStatus(status.lower())
            jobs = [j for j in jobs if j.status == status_filter]
        except ValueError:
            raise HTTPException(status_code=400, detail=f"Unknown status: {status!r}")
    if q:
        needle = q.lower()
        jobs = [j for j in jobs if needle in j.title.lower() or needle in j.prompt.lower()]
    if limit:
        jobs = jobs[:limit]
    return [j.to_dict() for j in jobs]


@router.get("/queue-status")
async def queue_status(_session: dict = Depends(require_auth)):
    """Return current worker pool and queue depth."""
    return bridge.get_queue_status()


@router.post("", status_code=201)
async def create_job(req: CreateJobRequest, _session: dict = Depends(require_auth)):
    action = req.rate_limit_action if req.rate_limit_action in _VALID_RL_ACTIONS else "try_different_model"
    required_output_ext = _normalize_required_output_ext(req.required_output_ext)

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
        required_output_ext=required_output_ext,
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


def _normalize_required_output_ext(value: Optional[str]) -> Optional[str]:
    if value is None:
        return None
    ext = value.strip().lower()
    if not ext:
        return None
    if "/" in ext or "\\" in ext or len(ext) > 16:
        raise HTTPException(status_code=400, detail="required_output_ext must be a short file extension")
    if not ext.startswith("."):
        ext = f".{ext}"
    if not re.match(r"^\.[a-z0-9]{1,12}$", ext):
        raise HTTPException(status_code=400, detail="required_output_ext must look like .html or .pdf")
    return ext


# ------------------------------------------------------------------
# Single job
# ------------------------------------------------------------------

@router.get("/{job_id}")
async def get_job(job_id: str, _session: dict = Depends(require_auth)):
    return _get_or_404(job_id).to_dict()


@router.delete("/{job_id}", status_code=204)
async def delete_job(job_id: str, _session: dict = Depends(require_auth)):
    _validate_job_id(job_id)
    job = store.get_job(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found")
    archive_result = store.archive_job_workspace(job)
    if archive_result.get("errors"):
        raise HTTPException(
            status_code=500,
            detail={
                "message": "Failed to archive job workspace during delete",
                "archive": archive_result,
            },
        )
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
    if job.status == JobStatus.QUEUED and job.auto_started:
        raise HTTPException(status_code=409, detail="Job is already queued — use STOP then START to re-queue")
    store.update_job(job_id, status=JobStatus.QUEUED)
    bridge.enqueue(job_id)
    # Once manually started, treat the job as actively queued/runnable.
    if not job.auto_started:
        store.update_job(job_id, auto_started=True)
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


# ------------------------------------------------------------------
# Output convenience endpoint
# ------------------------------------------------------------------

@router.get("/{job_id}/output", response_class=PlainTextResponse)
async def get_job_output(job_id: str, _session: dict = Depends(require_auth)):
    """Return the contents of final_output.md (or final_response.md) for a completed job."""
    job = _get_or_404(job_id)
    job_dir = _WORKSPACE_DIR / job_id
    for candidate in ("final_output.md", "final_response.md"):
        output_file = job_dir / candidate
        if output_file.exists():
            return output_file.read_text(encoding="utf-8", errors="replace")
    raise HTTPException(status_code=404, detail="No output file found for this job")


# ------------------------------------------------------------------
# Clone endpoint
# ------------------------------------------------------------------

class CloneJobRequest(BaseModel):
    title: Optional[str] = None
    prompt: Optional[str] = None
    auto_start: bool = True


@router.post("/{job_id}/clone", status_code=201)
async def clone_job(job_id: str, req: CloneJobRequest, _session: dict = Depends(require_auth)):
    """Create a copy of a job, optionally overriding title and/or prompt."""
    job = _get_or_404(job_id)
    new_title = (req.title or job.title).strip() or job.title
    new_prompt = (req.prompt or job.prompt).strip() or job.prompt

    domains = extract_domains(new_prompt, new_title)
    domains_dict = domains_to_dict(domains)

    new_job = store.create_job(
        title=new_title,
        prompt=new_prompt,
        rate_limit_action=job.rate_limit_action,
        resource_domains=domains_dict,
        priority=job.priority,
        auto_started=req.auto_start,
    )

    if req.auto_start:
        conflict_result = bridge.smart_enqueue(new_job, store, broadcaster)
        new_job = store.get_job(new_job.job_id) or new_job
        response = new_job.to_dict()
        if conflict_result is not None:
            response["_conflict"] = {
                "hard": conflict_result.conflicting_job_ids,
                "soft": conflict_result.soft_conflict_job_ids,
                "can_run_parallel": conflict_result.can_run_parallel,
                "sequenced": bool(conflict_result.conflicting_job_ids),
            }
        return response

    return new_job.to_dict()


# ------------------------------------------------------------------
# Retry endpoint
# ------------------------------------------------------------------

class RetryJobRequest(BaseModel):
    prompt: Optional[str] = None  # override prompt for the retry


@router.post("/{job_id}/retry", status_code=201)
async def retry_job(job_id: str, req: RetryJobRequest, _session: dict = Depends(require_auth)):
    """Re-queue a failed or completed job, optionally with a modified prompt."""
    job = _get_or_404(job_id)
    retriable = (JobStatus.FAILED, JobStatus.COMPLETED)
    if job.status not in retriable:
        raise HTTPException(
            status_code=409,
            detail=f"Can only retry failed or completed jobs (current status: {job.status})"
        )

    new_prompt = (req.prompt or job.prompt).strip() or job.prompt
    title = job.title if not req.prompt else job.title + " (retry)"
    domains = extract_domains(new_prompt, title)

    new_job = store.create_job(
        title=title,
        prompt=new_prompt,
        rate_limit_action=job.rate_limit_action,
        resource_domains=domains_to_dict(domains),
        priority=job.priority,
        auto_started=True,
    )
    conflict_result = bridge.smart_enqueue(new_job, store, broadcaster)
    new_job = store.get_job(new_job.job_id) or new_job
    response = new_job.to_dict()
    response["_retried_from"] = job_id
    if conflict_result is not None:
        response["_conflict"] = {
            "hard": conflict_result.conflicting_job_ids,
            "soft": conflict_result.soft_conflict_job_ids,
            "sequenced": bool(conflict_result.conflicting_job_ids),
        }
    return response
