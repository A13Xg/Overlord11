"""
backend/api/artifacts.py
=========================
Artifact file management endpoints.

GET    /api/artifacts/{job_id}             List artifacts for a job
GET    /api/artifacts/{job_id}/{filename}  Download / preview a file
DELETE /api/artifacts/{job_id}/{filename}  Delete a file

Security
--------
All user-supplied path components are validated through a strict allowlist
regex BEFORE any file-system operation.  The regex match group (not the raw
input) is used to build every path.  After construction, Path.resolve() is
called and the result is bounds-checked against the known root directory.
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

# Strict character-level allowlist patterns (prevent path traversal)
_JOB_ID_RE = re.compile(r"^([a-f0-9]{8,64})$")
_FILENAME_RE = re.compile(r"^([A-Za-z0-9_\-\.]{1,256})$")


def _validate_within(candidate: Path, root: Path, label: str) -> None:
    """Raise HTTPException if candidate is not strictly inside root."""
    try:
        candidate.relative_to(root)
    except ValueError:
        raise HTTPException(400, f"Invalid {label}: path traversal detected")


def _safe_job_dir(job_id: str) -> Path:
    """
    Return a validated job directory path.
    Only the allowlisted regex match group is used to construct the path;
    a resolve() + relative_to() bounds-check follows.
    """
    m = _JOB_ID_RE.match(job_id)
    if not m:
        raise HTTPException(400, "Invalid job_id format")
    safe_id = m.group(1)  # only hex chars, 8-64 len — no traversal possible
    candidate = (_WORKSPACE_ROOT / safe_id).resolve()
    _validate_within(candidate, _WORKSPACE_ROOT, "job_id")
    return candidate


def _safe_artifact_path(job_id: str, filename: str) -> Path:
    """
    Return a validated artifact path.
    Both job_id and filename pass the allowlist check; paths are resolved
    and bounds-checked before being returned.
    """
    job_dir = _safe_job_dir(job_id)
    base = os.path.basename(filename)  # strip any directory component first
    m = _FILENAME_RE.match(base)
    if not m:
        raise HTTPException(400, "Invalid filename")
    safe_name = m.group(1)  # only alphanum + _ - . — no traversal possible
    candidate = (job_dir / safe_name).resolve()
    _validate_within(candidate, job_dir, "filename")
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
