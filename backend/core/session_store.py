"""
backend/core/session_store.py
==============================
Thread-safe in-memory job/session store with optional JSON persistence.

Job states (per spec): queued, running, paused, completed, failed
"""

import json
import os
import threading
import time
import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional

JOB_STATES = ("queued", "running", "paused", "completed", "failed")

_STORE_DIR = Path(os.environ.get("OVR11_STORE_DIR", "logs/jobs"))


class JobRecord:
    """Represents one job in the system."""

    def __init__(
        self,
        task: str,
        agent: str = "orchestrator",
        provider: str = "anthropic",
        metadata: Optional[Dict[str, Any]] = None,
    ):
        self.job_id: str = uuid.uuid4().hex[:12]
        self.task = task
        self.agent = agent
        self.provider = provider
        self.metadata = metadata or {}

        self.state = "queued"
        self.created_at = time.time()
        self.started_at: Optional[float] = None
        self.finished_at: Optional[float] = None
        self.result: Optional[str] = None
        self.error: Optional[str] = None
        self.session_id: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "job_id": self.job_id,
            "task": self.task,
            "agent": self.agent,
            "provider": self.provider,
            "metadata": self.metadata,
            "state": self.state,
            "created_at": self.created_at,
            "started_at": self.started_at,
            "finished_at": self.finished_at,
            "result": self.result,
            "error": self.error,
            "session_id": self.session_id,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "JobRecord":
        job = cls(
            task=data.get("task", ""),
            agent=data.get("agent", "orchestrator"),
            provider=data.get("provider", "anthropic"),
            metadata=data.get("metadata", {}),
        )
        job.job_id = data.get("job_id", job.job_id)
        job.state = data.get("state", "queued")
        job.created_at = data.get("created_at", time.time())
        job.started_at = data.get("started_at")
        job.finished_at = data.get("finished_at")
        job.result = data.get("result")
        job.error = data.get("error")
        job.session_id = data.get("session_id")
        return job


class SessionStore:
    """
    Central registry for all jobs.  Thread-safe via a single RLock.
    """

    def __init__(self, store_dir: Optional[str] = None):
        self._jobs: Dict[str, JobRecord] = {}
        self._lock = threading.RLock()
        self._store_dir = Path(store_dir or str(_STORE_DIR))
        self._store_dir.mkdir(parents=True, exist_ok=True)
        self._load_from_disk()

    # ------------------------------------------------------------------
    # CRUD
    # ------------------------------------------------------------------

    def create_job(
        self,
        task: str,
        agent: str = "orchestrator",
        provider: str = "anthropic",
        metadata: Optional[Dict[str, Any]] = None,
    ) -> JobRecord:
        job = JobRecord(task=task, agent=agent, provider=provider, metadata=metadata)
        with self._lock:
            self._jobs[job.job_id] = job
            self._persist(job)
        return job

    def get_job(self, job_id: str) -> Optional[JobRecord]:
        with self._lock:
            return self._jobs.get(job_id)

    def list_jobs(self, state: Optional[str] = None) -> List[Dict[str, Any]]:
        with self._lock:
            jobs = list(self._jobs.values())
        if state:
            jobs = [j for j in jobs if j.state == state]
        return [j.to_dict() for j in sorted(jobs, key=lambda j: j.created_at)]

    def update_job(self, job_id: str, **kwargs) -> Optional[JobRecord]:
        with self._lock:
            job = self._jobs.get(job_id)
            if not job:
                return None
            for k, v in kwargs.items():
                if hasattr(job, k):
                    setattr(job, k, v)
            self._persist(job)
            return job

    def delete_job(self, job_id: str) -> bool:
        with self._lock:
            if job_id not in self._jobs:
                return False
            del self._jobs[job_id]
            path = self._store_dir / f"{job_id}.json"
            if path.exists():
                path.unlink()
            return True

    # ------------------------------------------------------------------
    # State helpers
    # ------------------------------------------------------------------

    def transition(self, job_id: str, new_state: str) -> bool:
        if new_state not in JOB_STATES:
            return False
        with self._lock:
            job = self._jobs.get(job_id)
            if not job:
                return False
            job.state = new_state
            if new_state == "running" and job.started_at is None:
                job.started_at = time.time()
            elif new_state in ("completed", "failed"):
                job.finished_at = time.time()
            self._persist(job)
        return True

    def next_queued(self) -> Optional[JobRecord]:
        """Return the oldest queued job, or None."""
        with self._lock:
            queued = [j for j in self._jobs.values() if j.state == "queued"]
        if not queued:
            return None
        return min(queued, key=lambda j: j.created_at)

    def has_running(self) -> bool:
        with self._lock:
            return any(j.state == "running" for j in self._jobs.values())

    # ------------------------------------------------------------------
    # Persistence
    # ------------------------------------------------------------------

    def _persist(self, job: JobRecord) -> None:
        path = self._store_dir / f"{job.job_id}.json"
        try:
            path.write_text(json.dumps(job.to_dict(), indent=2))
        except OSError:
            pass

    def _load_from_disk(self) -> None:
        for path in self._store_dir.glob("*.json"):
            try:
                data = json.loads(path.read_text())
                job = JobRecord.from_dict(data)
                # Mark running jobs as failed on restart
                if job.state == "running":
                    job.state = "failed"
                    job.error = "Server restarted while job was running"
                    job.finished_at = time.time()
                self._jobs[job.job_id] = job
            except (OSError, json.JSONDecodeError, KeyError):
                pass
