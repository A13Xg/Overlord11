"""
Stats API — system-level statistics.
"""
from __future__ import annotations

import time
from datetime import datetime, timezone

from fastapi import APIRouter, Depends

from ..auth.auth import require_auth
from ..core.engine_bridge import bridge
from ..core.session_store import JobStatus, store

router = APIRouter(prefix="/api/stats", tags=["stats"])

_SERVER_START_TIME = time.monotonic()
_SERVER_START_WALL = datetime.now(timezone.utc).isoformat()


@router.get("")
async def get_stats(_session: dict = Depends(require_auth)):
    """Return system-level statistics: job counts, success rate, tool counts, uptime."""
    jobs = store.list_jobs()

    status_counts: dict[str, int] = {s.value: 0 for s in JobStatus}
    for job in jobs:
        status_counts[job.status.value] = status_counts.get(job.status.value, 0) + 1

    completed = status_counts.get("completed", 0)
    failed = status_counts.get("failed", 0)
    terminal = completed + failed
    success_rate = round(completed / terminal, 4) if terminal > 0 else None

    # Aggregate tool_call_count across all jobs
    total_tool_calls = sum(getattr(j, "tool_call_count", 0) for j in jobs)
    total_artifacts = sum(getattr(j, "artifact_count", 0) for j in jobs)

    uptime_seconds = round(time.monotonic() - _SERVER_START_TIME)

    return {
        "server_started_at": _SERVER_START_WALL,
        "uptime_seconds": uptime_seconds,
        "jobs": {
            "total": len(jobs),
            "by_status": status_counts,
            "success_rate": success_rate,
            "total_tool_calls": total_tool_calls,
            "total_artifacts": total_artifacts,
        },
        "tools": {
            "registered": len(bridge.list_tools()),
        },
        "queue": bridge.get_queue_status(),
    }
