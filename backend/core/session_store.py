"""
Session store — in-memory + file-backed job/session state.
"""

import json
import os
import secrets
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import List, Optional

_BASE_DIR = Path(__file__).resolve().parent.parent.parent
_WORKSPACE_DIR = _BASE_DIR / "workspace"
_JOBS_FILE = _WORKSPACE_DIR / ".webui_jobs.json"


class JobStatus(str, Enum):
    QUEUED = "queued"
    RUNNING = "running"
    PAUSED = "paused"
    COMPLETED = "completed"
    FAILED = "failed"


@dataclass
class Job:
    job_id: str
    title: str
    prompt: str
    status: JobStatus
    created_at: str
    started_at: Optional[str]
    completed_at: Optional[str]
    session_id: Optional[str]
    output: Optional[str]
    error: Optional[str]
    artifacts: List[str] = field(default_factory=list)
    events: List[dict] = field(default_factory=list)

    def to_dict(self) -> dict:
        d = asdict(self)
        d["status"] = self.status.value
        return d

    @classmethod
    def from_dict(cls, d: dict) -> "Job":
        return cls(
            job_id=d["job_id"],
            title=d["title"],
            prompt=d["prompt"],
            status=JobStatus(d["status"]),
            created_at=d["created_at"],
            started_at=d.get("started_at"),
            completed_at=d.get("completed_at"),
            session_id=d.get("session_id"),
            output=d.get("output"),
            error=d.get("error"),
            artifacts=d.get("artifacts", []),
            events=d.get("events", []),
        )


class SessionStore:
    """Thread-safe in-memory store with file persistence."""

    def __init__(self) -> None:
        self._jobs: dict[str, Job] = {}

    # ------------------------------------------------------------------
    # CRUD
    # ------------------------------------------------------------------

    def create_job(self, title: str, prompt: str) -> Job:
        job_id = secrets.token_hex(4)  # 8-char hex
        job = Job(
            job_id=job_id,
            title=title,
            prompt=prompt,
            status=JobStatus.QUEUED,
            created_at=datetime.now(timezone.utc).isoformat(),
            started_at=None,
            completed_at=None,
            session_id=None,
            output=None,
            error=None,
            artifacts=[],
            events=[],
        )
        self._jobs[job_id] = job
        self.persist()
        return job

    def get_job(self, job_id: str) -> Optional[Job]:
        return self._jobs.get(job_id)

    def list_jobs(self) -> List[Job]:
        return sorted(self._jobs.values(), key=lambda j: j.created_at, reverse=True)

    def update_job(self, job_id: str, **kwargs) -> Optional[Job]:
        job = self._jobs.get(job_id)
        if job is None:
            return None
        for key, value in kwargs.items():
            if hasattr(job, key):
                setattr(job, key, value)
        self.persist()
        return job

    def delete_job(self, job_id: str) -> bool:
        if job_id in self._jobs:
            del self._jobs[job_id]
            self.persist()
            return True
        return False

    # ------------------------------------------------------------------
    # Persistence
    # ------------------------------------------------------------------

    def persist(self) -> None:
        _WORKSPACE_DIR.mkdir(parents=True, exist_ok=True)
        data = [j.to_dict() for j in self._jobs.values()]
        try:
            _JOBS_FILE.write_text(
                json.dumps(data, indent=2, ensure_ascii=False, default=str),
                encoding="utf-8",
            )
        except OSError:
            pass

    def load(self) -> None:
        if not _JOBS_FILE.exists():
            return
        try:
            data = json.loads(_JOBS_FILE.read_text(encoding="utf-8"))
            for item in data:
                job = Job.from_dict(item)
                # Jobs that were running/queued when server last died → failed
                if job.status in (JobStatus.RUNNING, JobStatus.QUEUED):
                    job.status = JobStatus.FAILED
                    job.error = "Server restarted — job interrupted"
                self._jobs[job.job_id] = job
        except (json.JSONDecodeError, KeyError, OSError):
            pass


# Module-level singleton
store = SessionStore()
