"""
webui/state_store.py — Disk-backed persistence layer.

Layout under workspace/jobs/<job_id>/:
    state.json      — current JobState snapshot (overwritten on each update)
    events.jsonl    — append-only event log (one JSON object per line)
    artifacts/      — diffs, test outputs, repair patches, etc.
"""

from __future__ import annotations

import json
import os
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterator

from .events import EventType, make_event, serialize_event
from .models import JobState, JobStatus


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
_WORKSPACE = _PROJECT_ROOT / "workspace" / "jobs"

# Allowlist patterns — enforced on every user-supplied path component
_JOB_ID_RE = re.compile(r'^[a-f0-9]{8,64}$')
_ARTIFACT_NAME_RE = re.compile(r'^[A-Za-z0-9_\-\.]{1,128}$')


def _safe_job_id(job_id: str) -> str:
    """
    Sanitize job_id against path traversal.

    Strips to basename (removes directory separators), then validates
    against a hex-only allowlist.  Raises ValueError for any invalid input.
    """
    safe = os.path.basename(str(job_id))
    if not _JOB_ID_RE.match(safe):
        raise ValueError(f"Invalid job_id: {job_id!r}")
    return safe


def _safe_artifact_name(name: str) -> str:
    """
    Sanitize artifact name against path traversal.

    Strips to basename (removes directory separators), then validates
    against an alphanumeric allowlist.  Raises ValueError for any invalid input.
    """
    safe = os.path.basename(str(name))
    if not _ARTIFACT_NAME_RE.match(safe) or '..' in safe:
        raise ValueError(f"Invalid artifact name: {name!r}")
    return safe


def _job_dir(job_id: str) -> Path:
    path = _WORKSPACE / _safe_job_id(job_id)
    # Resolve and verify it is still under _WORKSPACE (defense-in-depth)
    resolved = path.resolve()
    workspace_resolved = _WORKSPACE.resolve()
    if not str(resolved).startswith(str(workspace_resolved)):
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
    """Persist a brand-new job to disk and write the first event."""
    d = _job_dir(state.job_id)
    d.mkdir(parents=True, exist_ok=True)
    _artifacts_dir(state.job_id).mkdir(exist_ok=True)

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
    return sorted(
        d.name for d in _WORKSPACE.iterdir() if d.is_dir() and (_state_path(d.name)).exists()
    )


def append_event(event: dict[str, Any]) -> None:
    """Append one event line to the job's events.jsonl."""
    job_id = event.get("job_id", "unknown")
    path = _events_path(job_id)
    # Ensure parent dir exists (defensive)
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
    """Return the last *n* events for a job (O(file-size), acceptable for UI)."""
    events = list(read_events(job_id))
    return events[-n:]


def write_artifact(job_id: str, name: str, content: str) -> Path:
    """Write a text artifact to the job's artifacts/ directory."""
    path = _artifacts_dir(job_id) / _safe_artifact_name(name)
    path.write_text(content, encoding="utf-8")
    return path


def read_artifact(job_id: str, name: str) -> str | None:
    """Read a text artifact by name, or return None if it doesn't exist."""
    path = _artifacts_dir(job_id) / _safe_artifact_name(name)
    if not path.exists():
        return None
    return path.read_text(encoding="utf-8")


def list_artifacts(job_id: str) -> list[str]:
    """Return a list of artifact filenames for a job."""
    d = _artifacts_dir(job_id)
    if not d.exists():
        return []
    return sorted(p.name for p in d.iterdir() if p.is_file())
