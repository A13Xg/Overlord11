"""
SSE broadcaster — publish events to subscribed clients.
"""

import asyncio
import json
from datetime import datetime, timezone
from typing import AsyncGenerator, Dict, List, Optional, Set


class EventBroadcaster:
    """Fan-out events to all registered SSE subscribers."""

    def __init__(self) -> None:
        # Map job_id (or None for "all") → list of subscriber queues
        self._queues: Dict[Optional[str], List[asyncio.Queue]] = {}

    def _get_queues(self, job_id: Optional[str]) -> List[asyncio.Queue]:
        return self._queues.get(job_id, [])

    async def subscribe(self, job_id: Optional[str] = None) -> AsyncGenerator[str, None]:
        """
        Yield SSE-formatted strings.
        Pass job_id=None to receive all events; pass a job_id to filter.
        """
        q: asyncio.Queue = asyncio.Queue(maxsize=256)
        self._queues.setdefault(job_id, []).append(q)
        try:
            # Send a keepalive comment immediately
            yield ": keepalive\n\n"
            while True:
                try:
                    event = await asyncio.wait_for(q.get(), timeout=25)
                    if event is None:
                        break
                    yield event
                except asyncio.TimeoutError:
                    # Send heartbeat to keep connection alive
                    yield ": ping\n\n"
        finally:
            try:
                self._queues[job_id].remove(q)
            except (KeyError, ValueError):
                pass

    def publish(self, job_id: str, event: dict) -> None:
        """Broadcast an event to all relevant subscribers (synchronous)."""
        payload = json.dumps(event, ensure_ascii=False, default=str)
        sse = f"data: {payload}\n\n"

        # Deliver to job-specific subscribers
        for q in list(self._get_queues(job_id)):
            try:
                q.put_nowait(sse)
            except asyncio.QueueFull:
                pass

        # Deliver to "all" subscribers
        for q in list(self._get_queues(None)):
            try:
                q.put_nowait(sse)
            except asyncio.QueueFull:
                pass


# Module-level singleton
broadcaster = EventBroadcaster()
