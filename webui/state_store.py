import json
import os
import re
import time
from pathlib import Path
from typing import List, Optional, Dict, Any

from .models import JobSummary, JobDetail, ArtifactInfo, JobStatus

WORKSPACE_ROOT = Path(__file__).resolve().parent.parent / "workspace"
JOBS_DIR = WORKSPACE_ROOT / "jobs"

FINISHED_PRODUCT_PATHS = [
    "artifacts/reports/debrief.md",
    "artifacts/final_report.md",
    "artifacts/output.md",
]
FINISHED_PRODUCT_PREFIXES = ["artifacts/deliverables/", "artifacts/reports/", "artifacts/"]


def get_jobs_dir() -> Path:
    return JOBS_DIR


def _read_state(job_dir: Path) -> Optional[Dict[str, Any]]:
    state_file = job_dir / "state.json"
    if state_file.exists():
        try:
            return json.loads(state_file.read_text(encoding="utf-8"))
        except Exception:
            pass
    return None


def _read_events(job_dir: Path) -> List[Dict[str, Any]]:
    events_file = job_dir / "events.jsonl"
    if not events_file.exists():
        return []
    events = []
    try:
        for line in events_file.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line:
                try:
                    events.append(json.loads(line))
                except Exception:
                    pass
    except Exception:
        pass
    return events


def _list_artifacts(job_dir: Path) -> List[ArtifactInfo]:
    artifacts = []
    for root, _, files in os.walk(job_dir):
        for fname in files:
            fpath = Path(root) / fname
            rel = fpath.relative_to(job_dir).as_posix()
            if rel in ("state.json", "events.jsonl"):
                continue
            try:
                stat = fpath.stat()
                is_fp = any(
                    rel == fp or rel.startswith(pfx)
                    for fp in FINISHED_PRODUCT_PATHS
                    for pfx in FINISHED_PRODUCT_PREFIXES
                )
                artifacts.append(ArtifactInfo(
                    path=rel,
                    size=stat.st_size,
                    mtime=stat.st_mtime,
                    is_finished_product=is_fp,
                ))
            except Exception:
                pass
    return sorted(artifacts, key=lambda a: a.path)


def _make_summary(job_id: str, job_dir: Path) -> JobSummary:
    state = _read_state(job_dir)
    if state:
        status_val = state.get("status", "pending")
        try:
            status = JobStatus(status_val)
        except ValueError:
            status = JobStatus.pending
        return JobSummary(
            job_id=job_id,
            goal=state.get("goal"),
            status=status,
            created=state.get("created"),
            updated=state.get("updated"),
            verify_summary=state.get("verify_summary"),
            provider=state.get("provider"),
            model=state.get("model"),
        )
    mtime = job_dir.stat().st_mtime
    return JobSummary(
        job_id=job_id,
        status=JobStatus.pending,
        created=mtime,
        updated=mtime,
    )


def list_jobs() -> List[JobSummary]:
    if not JOBS_DIR.exists():
        return []
    jobs = []
    for entry in sorted(JOBS_DIR.iterdir()):
        if entry.is_dir():
            jobs.append(_make_summary(entry.name, entry))
    return sorted(jobs, key=lambda j: j.created or 0, reverse=True)


def get_job(job_id: str) -> Optional[JobDetail]:
    if not re.match(r'^[a-zA-Z0-9_\-]{1,128}$', job_id):
        return None
    job_dir = JOBS_DIR / job_id
    if not job_dir.is_dir():
        return None
    summary = _make_summary(job_id, job_dir)
    state = _read_state(job_dir)
    events = _read_events(job_dir)
    artifacts = _list_artifacts(job_dir)
    return JobDetail(
        **summary.model_dump(),
        state=state,
        events=events,
        artifacts=artifacts,
    )


def list_artifacts(job_id: str) -> Optional[List[ArtifactInfo]]:
    if not re.match(r'^[a-zA-Z0-9_\-]{1,128}$', job_id):
        return None
    job_dir = JOBS_DIR / job_id
    if not job_dir.is_dir():
        return None
    return _list_artifacts(job_dir)


def read_artifact(job_id: str, artifact_path: str) -> Optional[bytes]:
    if not re.match(r'^[a-zA-Z0-9_\-]{1,128}$', job_id):
        return None
    clean_path = os.path.normpath(artifact_path).lstrip("/").lstrip("\\")
    if ".." in clean_path:
        return None
    job_dir = JOBS_DIR / job_id
    if not job_dir.is_dir():
        return None
    full_path = job_dir / clean_path
    try:
        full_path.resolve().relative_to(job_dir.resolve())
    except ValueError:
        return None
    if not full_path.is_file():
        return None
    return full_path.read_bytes()
