"""
backend/api/artifacts.py
=========================
Artifact file management endpoints.

GET    /api/artifacts/{job_id}             List artifacts for a job
GET    /api/artifacts/{job_id}/{filename}  Download / preview a file
DELETE /api/artifacts/{job_id}/{filename}  Delete a file
"""

import mimetypes
import os
import re
from pathlib import Path
from typing import Any, Dict, List

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse

router = APIRouter(prefix="/api/artifacts", tags=["artifacts"])

_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
_WORKSPACE_ROOT = (_PROJECT_ROOT / "workspace").resolve()

# Strict allowlist patterns (security: prevent path traversal)
_JOB_ID_RE = re.compile(r"^([a-f0-9]{8,64})$")
_FILENAME_RE = re.compile(r"^([A-Za-z0-9_\-\.]{1,256})$")


def _safe_job_dir(job_id: str) -> Path:
    """
    Return a validated job directory path.
    Uses the regex match group (not the original input) to build the path
    so tainted data never reaches a file operation.
    """
    match = _JOB_ID_RE.match(job_id)
    if not match:
        raise HTTPException(400, "Invalid job_id format")
    # Use only the allowlisted match group — not the original user input
    safe_id = match.group(1)
    candidate = (_WORKSPACE_ROOT / safe_id).resolve()
    # Verify the resolved path is strictly inside _WORKSPACE_ROOT
    if not str(candidate).startswith(str(_WORKSPACE_ROOT) + os.sep):
        raise HTTPException(400, "Invalid job_id: path traversal detected")
    return candidate


def _safe_artifact_path(job_id: str, filename: str) -> Path:
    """
    Return a validated artifact path.
    Both job_id and filename are regex-matched and only the match groups
    are used to construct the path.
    """
    job_dir = _safe_job_dir(job_id)
    match = _FILENAME_RE.match(os.path.basename(filename))
    if not match:
        raise HTTPException(400, "Invalid filename")
    # Use only the allowlisted match group — not the original user input
    safe_name = match.group(1)
    candidate = (job_dir / safe_name).resolve()
    # Verify the resolved path is strictly inside job_dir
    if not str(candidate).startswith(str(job_dir) + os.sep):
        raise HTTPException(400, "Invalid filename: path traversal detected")
    return candidate


@router.get("/{job_id}")
def list_artifacts(job_id: str) -> List[Dict[str, Any]]:
    job_dir = _safe_job_dir(job_id)
    if not job_dir.exists():
        return []
    result = []
    for p in sorted(job_dir.iterdir()):
        if p.is_file():
            stat = p.stat()
            result.append(
                {
                    "path": p.name,
                    "size": stat.st_size,
                    "mtime": stat.st_mtime,
                    "mime": mimetypes.guess_type(p.name)[0] or "application/octet-stream",
                }
            )
    return result


@router.get("/{job_id}/{filename}")
def download_artifact(job_id: str, filename: str):
    path = _safe_artifact_path(job_id, filename)
    if not path.exists() or not path.is_file():
        raise HTTPException(404, "Artifact not found")
    return FileResponse(str(path), filename=path.name)


@router.delete("/{job_id}/{filename}", status_code=204)
def delete_artifact(job_id: str, filename: str):
    path = _safe_artifact_path(job_id, filename)
    if not path.exists():
        raise HTTPException(404, "Artifact not found")
    path.unlink()
