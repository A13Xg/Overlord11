"""
Events API — SSE endpoints for real-time event streaming.
"""

import asyncio
import re

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import StreamingResponse

from ..core.event_stream import broadcaster

router = APIRouter(prefix="/api/events", tags=["events"])

_JOB_ID_RE = re.compile(r"^[a-f0-9]{8,64}$")


class QuietStreamingResponse(StreamingResponse):
    """Suppress cancellation raised when an SSE client disconnects."""

    async def __call__(self, scope, receive, send):
        try:
            await super().__call__(scope, receive, send)
        except asyncio.CancelledError:
            return


async def _safe_event_stream(request: Request, job_id: str | None):
    """Exit quietly when the SSE client disconnects or the task is cancelled."""
    try:
        async for chunk in broadcaster.subscribe(job_id=job_id):
            if await request.is_disconnected():
                break
            yield chunk
    except asyncio.CancelledError:
        return


@router.get("")
async def stream_all_events(request: Request):
    """SSE stream — all events from all jobs."""
    return QuietStreamingResponse(
        _safe_event_stream(request, job_id=None),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
            "Connection": "keep-alive",
        },
    )


@router.get("/{job_id}")
async def stream_job_events(job_id: str, request: Request):
    """SSE stream — events for a specific job."""
    if not _JOB_ID_RE.match(job_id):
        raise HTTPException(status_code=400, detail="Invalid job_id format")

    return QuietStreamingResponse(
        _safe_event_stream(request, job_id=job_id),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
            "Connection": "keep-alive",
        },
    )
