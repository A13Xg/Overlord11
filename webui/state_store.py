"""
webui/state_store.py — Disk-backed persistence layer.

Layout under workspace/jobs/<job_id>/:
    state.json              current JobState snapshot (atomic overwrite)
    events.jsonl            append-only event log (one JSON per line)
    artifacts/
        verify/             verify gate output logs (iter_<n>.log)
        install/            pip install logs (iter_<n>_<pkg>.log)
        diffs/              unified diff patches (iter_<n>.patch)
        plans/              StepPlan JSON files (step_<n>.json)
        reports/            reviewer/general reports
"""

from __future__ import annotations

import json
import os
import re
import stat
import time
from pathlib import Path
from typing import Any, Iterator

from .events import EventType, make_event, serialize_event
from .models import ArtifactMeta, JobState, JobStatus


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
_WORKSPACE = _PROJECT_ROOT / "workspace" / "jobs"

# Allowlist patterns
_JOB_ID_RE = re.compile(r'^[a-f0-9]{8,64}$')
_ARTIFACT_SUBDIR_RE = re.compile(r'^(verify|install|diffs|plans|reports)$')
_ARTIFACT_FILENAME_RE = re.compile(r'^[A-Za-z0-9_\-\.]{1,128}$')

# Artifact subdirectories to create for every new job
_ARTIFACT_SUBDIRS = ("verify", "install", "diffs", "plans", "reports")


# ---------------------------------------------------------------------------
# Path sanitisation
# ---------------------------------------------------------------------------

def _safe_job_id(job_id: str) -> str:
    """
    Sanitize job_id: basename + hex-only allowlist.
    Raises ValueError on any invalid input.
    """
    safe = os.path.basename(str(job_id))
    if not _JOB_ID_RE.match(safe):
        raise ValueError(f"Invalid job_id: {job_id!r}")
    return safe


def _safe_artifact_path(rel_path: str) -> str:
    """
    Sanitize an artifact relative path such as 'verify/iter_1.log'.

    Accepts:
      - bare filename: 'report.txt'
      - one-level subdir: 'verify/iter_1.log'

    Rejects everything else (traversal, deeper nesting, bad chars).
    Returns the sanitized string.
    """
    # Normalize separators
    rel_path = rel_path.replace("\\", "/").strip("/")
    parts = rel_path.split("/")

    if len(parts) == 1:
        fname = os.path.basename(parts[0])
        if not _ARTIFACT_FILENAME_RE.match(fname) or ".." in fname:
            raise ValueError(f"Invalid artifact name: {rel_path!r}")
        return fname

    if len(parts) == 2:
        subdir = os.path.basename(parts[0])
        fname = os.path.basename(parts[1])
        if not _ARTIFACT_SUBDIR_RE.match(subdir):
            raise ValueError(f"Invalid artifact subdir: {subdir!r}")
        if not _ARTIFACT_FILENAME_RE.match(fname) or ".." in fname:
            raise ValueError(f"Invalid artifact name: {rel_path!r}")
        return f"{subdir}/{fname}"

    raise ValueError(f"Artifact path too deep: {rel_path!r}")


def _is_path_within_workspace(resolved: Path, workspace_resolved: Path) -> bool:
    """Return True if *resolved* is *workspace_resolved* or a child thereof."""
    resolved_str = str(resolved)
    workspace_str = str(workspace_resolved)
    return resolved_str.startswith(workspace_str + os.sep) or resolved_str == workspace_str


def _job_dir(job_id: str) -> Path:
    path = _WORKSPACE / _safe_job_id(job_id)
    if not _is_path_within_workspace(path.resolve(), _WORKSPACE.resolve()):
        raise ValueError(f"Path traversal detected for job_id: {job_id!r}")
    return path


def _state_path(job_id: str) -> Path:
    return _job_dir(job_id) / "state.json"


def _events_path(job_id: str) -> Path:
    return _job_dir(job_id) / "events.jsonl"


def _artifacts_dir(job_id: str) -> Path:
    return _job_dir(job_id) / "artifacts"


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def create_job(state: JobState) -> None:
    """Persist a brand-new job to disk, create artifact subdirs, write first event."""
    d = _job_dir(state.job_id)
    d.mkdir(parents=True, exist_ok=True)
    arts = _artifacts_dir(state.job_id)
    arts.mkdir(exist_ok=True)
    for sub in _ARTIFACT_SUBDIRS:
        (arts / sub).mkdir(exist_ok=True)

    save_state(state)
    append_event(
        make_event(
            EventType.JOB_CREATED,
            state.job_id,
            {"goal": state.goal, "max_iterations": state.max_iterations},
        )
    )


def save_state(state: JobState) -> None:
    """Overwrite state.json atomically (write-to-tmp then rename)."""
    path = _state_path(state.job_id)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(
        json.dumps(state.model_dump(), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    tmp.replace(path)


def load_state(job_id: str) -> JobState | None:
    """Load and return a JobState from disk, or None if not found."""
    path = _state_path(job_id)
    if not path.exists():
        return None
    data = json.loads(path.read_text(encoding="utf-8"))
    return JobState(**data)


def list_jobs() -> list[str]:
    """Return all job_id strings found in the workspace."""
    if not _WORKSPACE.exists():
        return []
    result = []
    for d in _WORKSPACE.iterdir():
        if d.is_dir():
            try:
                if _state_path(d.name).exists():
                    result.append(d.name)
            except ValueError:
                pass  # skip dirs with invalid names
    return sorted(result)


def append_event(event: dict[str, Any]) -> None:
    """Append one event line to the job's events.jsonl."""
    job_id = event.get("job_id", "unknown")
    path = _events_path(job_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "a", encoding="utf-8") as fh:
        fh.write(serialize_event(event) + "\n")


def read_events(job_id: str, byte_offset: int = 0) -> Iterator[dict[str, Any]]:
    """
    Yield parsed event dicts from events.jsonl starting at *byte_offset*.
    Callers can persist the returned file position to resume efficiently.
    """
    path = _events_path(job_id)
    if not path.exists():
        return
    with open(path, "r", encoding="utf-8") as fh:
        if byte_offset:
            fh.seek(byte_offset)
        for line in fh:
            line = line.strip()
            if line:
                try:
                    yield json.loads(line)
                except json.JSONDecodeError:
                    pass  # skip malformed lines


def tail_events(job_id: str, n: int = 50) -> list[dict[str, Any]]:
    """Return the last *n* events for a job."""
    events = list(read_events(job_id))
    return events[-n:]


def write_artifact(job_id: str, rel_path: str, content: str) -> Path:
    """
    Write a text artifact.

    *rel_path* may be a bare filename or a single-level subdirectory path
    such as 'verify/iter_1.log'.  The subdir must be one of:
    verify, install, diffs, plans, reports.
    """
    safe = _safe_artifact_path(rel_path)
    path = _artifacts_dir(job_id) / safe
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    return path


def read_artifact(job_id: str, rel_path: str) -> str | None:
    """Read a text artifact by relative path, or return None if not found."""
    safe = _safe_artifact_path(rel_path)
    path = _artifacts_dir(job_id) / safe
    if not path.exists():
        return None
    return path.read_text(encoding="utf-8")


def list_artifacts(job_id: str) -> list[ArtifactMeta]:
    """
    Return a list of ArtifactMeta objects for all files in the job's
    artifacts/ directory tree (including subdirs).
    """
    d = _artifacts_dir(job_id)
    if not d.exists():
        return []
    result = []
    for p in sorted(d.rglob("*")):
        if p.is_file():
            try:
                rel = p.relative_to(d).as_posix()
                st = p.stat()
                result.append(
                    ArtifactMeta(path=rel, size=st.st_size, mtime=st.st_mtime)
                )
            except (ValueError, OSError):
                pass
    return result
