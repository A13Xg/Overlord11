"""
Artifacts API — list and download job artifacts.
"""

import os
import re
from pathlib import Path

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse

from ..core.session_store import store

router = APIRouter(prefix="/api/artifacts", tags=["artifacts"])

_BASE_DIR = Path(__file__).resolve().parent.parent.parent
_WORKSPACE_DIR = _BASE_DIR / "workspace"

_JOB_ID_RE = re.compile(r"^[a-f0-9]{8,64}$")
_ARTIFACT_NAME_RE = re.compile(r"^[A-Za-z0-9_\-\.]{1,128}$")


def _validate_job_id(job_id: str) -> None:
    if not _JOB_ID_RE.match(job_id):
        raise HTTPException(status_code=400, detail="Invalid job_id format")


def _validate_artifact_name(name: str) -> None:
    if not _ARTIFACT_NAME_RE.match(name):
        raise HTTPException(status_code=400, detail="Invalid artifact name")


def _artifact_dir(job: object) -> Path:
    """
    Locate the artifact directory for a job.
    If the job has a session_id we look in workspace/<session_id>/output;
    otherwise fall back to workspace/<job_id>.
    """
    session_id = getattr(job, "session_id", None)
    if session_id:
        candidate = _WORKSPACE_DIR / session_id / "output"
        if candidate.is_dir():
            return candidate
        candidate2 = _WORKSPACE_DIR / session_id / "outputs"
        if candidate2.is_dir():
            return candidate2
    fallback = _WORKSPACE_DIR / job.job_id
    fallback.mkdir(parents=True, exist_ok=True)
    return fallback


@router.get("/{job_id}")
async def list_artifacts(job_id: str):
    _validate_job_id(job_id)
    job = store.get_job(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found")

    art_dir = _artifact_dir(job)
    if not art_dir.exists():
        return []

    items = []
    for entry in sorted(art_dir.iterdir()):
        if entry.is_file():
            stat = entry.stat()
            items.append({
                "name": entry.name,
                "size": stat.st_size,
                "mtime": stat.st_mtime,
            })
    return items


@router.get("/{job_id}/{name}")
async def download_artifact(job_id: str, name: str):
    _validate_job_id(job_id)
    _validate_artifact_name(name)

    job = store.get_job(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found")

    art_dir = _artifact_dir(job).resolve()

    # Strip any directory components from the user-supplied name, then
    # resolve the full path and confirm it lives inside art_dir.
    safe_name = os.path.basename(name)
    resolved = (art_dir / safe_name).resolve()

    # Strict containment check — rejects symlinks that escape the directory
    try:
        resolved.relative_to(art_dir)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid artifact path")

    if not resolved.exists() or not resolved.is_file():
        raise HTTPException(status_code=404, detail="Artifact not found")

    # Pass the fully-resolved absolute path; safe_name is used only as the
    # download filename and has already been validated by the allowlist regex.
    return FileResponse(str(resolved), filename=safe_name)
