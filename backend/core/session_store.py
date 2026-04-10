"""
Session store — in-memory + file-backed job/session state.
"""

import json
import os
import secrets
import threading
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
    RATE_LIMITED = "rate_limited"
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
    # Optional list of job_ids that must reach COMPLETED before this job starts.
    # Enforced by EngineBridge._wait_for_dependencies().
    depends_on: List[str] = field(default_factory=list)
    # What to do when all providers return 429: "pause" | "stop" | "try_different_model"
    # "pause" (default): exponential backoff starting at initial_wait_s, doubling each hit, max 8 hours
    # "stop": fail the job immediately
    # "try_different_model": wait only as long as the shortest provider Retry-After, then retry
    rate_limit_action: str = "pause"
    # Resource domains extracted by conflict_detector; used for smart sequencing.
    resource_domains: dict = field(default_factory=dict)
    # Execution priority: lower = higher priority (0 = normal, -1 = high, 1 = low)
    priority: int = 0
    # Whether this job was auto-started (vs manually started)
    auto_started: bool = True
    # Conflict info: which jobs this was sequenced behind and why
    conflict_info: dict = field(default_factory=dict)

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
            depends_on=d.get("depends_on", []),
            rate_limit_action=d.get("rate_limit_action", "pause"),
            resource_domains=d.get("resource_domains", {}),
            priority=d.get("priority", 0),
            auto_started=d.get("auto_started", True),
            conflict_info=d.get("conflict_info", {}),
        )


class SessionStore:
    """Thread-safe in-memory store with file persistence."""

    def __init__(self) -> None:
        self._jobs: dict[str, Job] = {}
        # Guards all mutations: the event_callback in EngineBridge fires from
        # thread-pool workers (parallel tool execution), so append_event and
        # persist must be atomic.
        self._lock = threading.Lock()

    # ------------------------------------------------------------------
    # CRUD
    # ------------------------------------------------------------------

    def create_job(
        self,
        title: str,
        prompt: str,
        depends_on: Optional[List[str]] = None,
        rate_limit_action: str = "pause",
        resource_domains: Optional[dict] = None,
        priority: int = 0,
        auto_started: bool = True,
        conflict_info: Optional[dict] = None,
    ) -> Job:
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
            depends_on=list(depends_on) if depends_on else [],
            rate_limit_action=rate_limit_action,
            resource_domains=resource_domains or {},
            priority=priority,
            auto_started=auto_started,
            conflict_info=conflict_info or {},
        )
        with self._lock:
            self._jobs[job_id] = job
        self.persist()
        return job

    def get_job(self, job_id: str) -> Optional[Job]:
        with self._lock:
            return self._jobs.get(job_id)

    def list_jobs(self) -> List[Job]:
        with self._lock:
            jobs = list(self._jobs.values())
        return sorted(jobs, key=lambda j: j.created_at, reverse=True)

    def update_job(self, job_id: str, **kwargs) -> Optional[Job]:
        with self._lock:
            job = self._jobs.get(job_id)
            if job is None:
                return None
            for key, value in kwargs.items():
                if hasattr(job, key):
                    setattr(job, key, value)
        self.persist()
        return job

    def delete_job(self, job_id: str) -> bool:
        with self._lock:
            if job_id not in self._jobs:
                return False
            del self._jobs[job_id]
        self.persist()
        return True

    def append_event(self, job_id: str, event: dict) -> Optional[Job]:
        with self._lock:
            job = self._jobs.get(job_id)
            if job is None:
                return None
            job.events.append(event)
        self.persist()
        return job

    # ------------------------------------------------------------------
    # Persistence
    # ------------------------------------------------------------------

    def persist(self) -> None:
        _WORKSPACE_DIR.mkdir(parents=True, exist_ok=True)
        with self._lock:
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
            with self._lock:
                for item in data:
                    job = Job.from_dict(item)
                    # Jobs that were in-flight when the server last died → failed.
                    # Includes RATE_LIMITED (runner was sleeping) and PAUSED
                    # (no worker will ever resume them after restart).
                    _interrupted = (
                        JobStatus.RUNNING,
                        JobStatus.QUEUED,
                        JobStatus.RATE_LIMITED,
                        JobStatus.PAUSED,
                    )
                    if job.status in _interrupted:
                        job.status = JobStatus.FAILED
                        job.error = "Server restarted — job interrupted"
                    self._jobs[job.job_id] = job
        except (json.JSONDecodeError, KeyError, OSError):
            pass


# Module-level singleton
store = SessionStore()
