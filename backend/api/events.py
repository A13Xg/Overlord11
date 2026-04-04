"""
Events API — SSE endpoints for real-time event streaming.
"""

import re

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse

from ..core.event_stream import broadcaster

router = APIRouter(prefix="/api/events", tags=["events"])

_JOB_ID_RE = re.compile(r"^[a-f0-9]{8,64}$")


@router.get("")
async def stream_all_events():
    """SSE stream — all events from all jobs."""
    return StreamingResponse(
        broadcaster.subscribe(job_id=None),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
            "Connection": "keep-alive",
        },
    )


@router.get("/{job_id}")
async def stream_job_events(job_id: str):
    """SSE stream — events for a specific job."""
    if not _JOB_ID_RE.match(job_id):
        raise HTTPException(status_code=400, detail="Invalid job_id format")

    return StreamingResponse(
        broadcaster.subscribe(job_id=job_id),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
            "Connection": "keep-alive",
        },
    )
