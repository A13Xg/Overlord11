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

# Allowlist patterns (security: prevent path traversal)
_JOB_ID_RE = re.compile(r"^[a-f0-9]{8,64}$")
_FILENAME_RE = re.compile(r"^[A-Za-z0-9_\-\.]{1,256}$")


def _safe_job_dir(job_id: str) -> Path:
    if not _JOB_ID_RE.match(job_id):
        raise HTTPException(400, "Invalid job_id format")
    # Resolve to real path and verify it stays inside _WORKSPACE_ROOT
    candidate = (_WORKSPACE_ROOT / job_id).resolve()
    if not str(candidate).startswith(str(_WORKSPACE_ROOT) + os.sep) and candidate != _WORKSPACE_ROOT:
        raise HTTPException(400, "Invalid job_id: path traversal detected")
    return candidate


def _safe_artifact_path(job_id: str, filename: str) -> Path:
    job_dir = _safe_job_dir(job_id)
    safe_name = os.path.basename(filename)
    if not _FILENAME_RE.match(safe_name):
        raise HTTPException(400, "Invalid filename")
    # Resolve and verify path stays inside job_dir
    candidate = (job_dir / safe_name).resolve()
    if not str(candidate).startswith(str(job_dir) + os.sep) and candidate != job_dir:
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
    return FileResponse(str(path), filename=filename)


@router.delete("/{job_id}/{filename}", status_code=204)
def delete_artifact(job_id: str, filename: str):
    path = _safe_artifact_path(job_id, filename)
    if not path.exists():
        raise HTTPException(404, "Artifact not found")
    path.unlink()
