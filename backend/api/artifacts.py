"""
Artifacts API — list and download job artifacts.
"""

import os
import re
from pathlib import Path
from typing import Optional

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
    if session_id and _JOB_ID_RE.match(str(session_id)):
        candidate = _WORKSPACE_DIR / session_id / "output"
        if candidate.is_dir():
            return candidate
        candidate2 = _WORKSPACE_DIR / session_id / "outputs"
        if candidate2.is_dir():
            return candidate2
    fallback = _WORKSPACE_DIR / job.job_id  # job_id already validated upstream
    fallback.mkdir(parents=True, exist_ok=True)
    return fallback


def _find_file_in_dir(art_dir: Path, target_name: str) -> Optional[Path]:
    """
    Walk the directory and return the Path of a file whose name exactly
    matches target_name.  Uses filesystem-originated paths only so no
    user-supplied value ever flows directly into a file operation.
    """
    try:
        for entry in art_dir.iterdir():
            if entry.is_file() and entry.name == target_name:
                return entry
    except OSError:
        pass
    return None


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

    # Derive safe_name from os.path.basename to strip any stray separators,
    # then locate the file by iterating the directory so that the Path used
    # for serving always originates from the filesystem, not from user input.
    safe_name = os.path.basename(name)
    matched: Optional[Path] = _find_file_in_dir(art_dir, safe_name)

    if matched is None:
        raise HTTPException(status_code=404, detail="Artifact not found")

    # Paranoia: confirm the filesystem-derived path is still inside art_dir
    try:
        matched.resolve().relative_to(art_dir)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid artifact path")

    return FileResponse(str(matched), filename=matched.name)
