import asyncio
import tempfile
import time
import unittest
from datetime import datetime, timezone
from pathlib import Path

import backend.core.engine_bridge as eb
import backend.core.session_store as ss
from backend.core.event_stream import EventBroadcaster
from backend.core.session_store import JobStatus, SessionStore


class _DummyEvents:
    def __init__(self):
        self.callbacks = []


class _DummyRunner:
    def __init__(self, verbose=False, stop_event=None, rate_limit_action=None, stop_file_path=None):
        self._stop_event = stop_event
        self._stop_file = Path(stop_file_path) if stop_file_path else None
        self.events = _DummyEvents()

    def run(self, prompt, job_id=None, job_title=None, required_output_ext=None):
        # Simulate moderately long task that can be cancelled.
        for _ in range(60):
            if self._stop_event is not None and self._stop_event.is_set():
                return {
                    "status": "failed",
                    "output": "",
                    "error": "stopped_by_user",
                    "completion_mode": "no_effect_fail",
                    "tool_call_count": 0,
                    "artifact_count": 0,
                    "session_id": f"session_{job_id}",
                }
            if self._stop_file is not None and self._stop_file.exists():
                return {
                    "status": "failed",
                    "output": "",
                    "error": "stopped_by_user",
                    "completion_mode": "no_effect_fail",
                    "tool_call_count": 0,
                    "artifact_count": 0,
                    "session_id": f"session_{job_id}",
                }
            time.sleep(0.02)

        return {
            "status": "complete",
            "output": f"done:{prompt}",
            "error": None,
            "completion_mode": "tool_driven",
            "tool_call_count": 1,
            "artifact_count": 1,
            "session_id": f"session_{job_id}",
        }


class EngineBridgeConcurrencyStopTests(unittest.IsolatedAsyncioTestCase):
    async def test_stop_one_of_three_jobs_does_not_affect_others(self):
        orig_workspace = ss._WORKSPACE_DIR
        orig_jobs_file = ss._JOBS_FILE
        orig_archive_dir = ss._ARCHIVE_DIR
        orig_runner_cls = eb.EngineRunner

        try:
            with tempfile.TemporaryDirectory() as td:
                ws = Path(td) / "workspace"
                ss._WORKSPACE_DIR = ws
                ss._JOBS_FILE = ws / ".webui_jobs.json"
                ss._ARCHIVE_DIR = ws / "archive"

                store = SessionStore()
                broadcaster = EventBroadcaster()
                bridge = eb.EngineBridge()

                eb.EngineRunner = _DummyRunner

                j1 = store.create_job(title="job-1", prompt="alpha")
                j2 = store.create_job(title="job-2", prompt="beta")
                j3 = store.create_job(title="job-3", prompt="gamma")

                store.update_job(j1.job_id, status=JobStatus.QUEUED)
                store.update_job(j2.job_id, status=JobStatus.QUEUED)
                store.update_job(j3.job_id, status=JobStatus.QUEUED)

                t1 = asyncio.create_task(bridge.run_job(j1.job_id, store, broadcaster))
                t2 = asyncio.create_task(bridge.run_job(j2.job_id, store, broadcaster))
                t3 = asyncio.create_task(bridge.run_job(j3.job_id, store, broadcaster))

                await asyncio.sleep(0.2)
                bridge.signal_stop(j2.job_id)
                store.update_job(
                    j2.job_id,
                    status=JobStatus.FAILED,
                    error="Stopped by user",
                    completed_at=datetime.now(timezone.utc).isoformat(),
                )

                await asyncio.gather(t1, t2, t3)

                r1 = store.get_job(j1.job_id)
                r2 = store.get_job(j2.job_id)
                r3 = store.get_job(j3.job_id)

                self.assertIsNotNone(r1)
                self.assertIsNotNone(r2)
                self.assertIsNotNone(r3)
                self.assertEqual(r2.status, JobStatus.FAILED)
                self.assertEqual(r2.error, "Stopped by user")
                self.assertEqual(r1.status, JobStatus.COMPLETED)
                self.assertEqual(r3.status, JobStatus.COMPLETED)

        finally:
            eb.EngineRunner = orig_runner_cls
            ss._WORKSPACE_DIR = orig_workspace
            ss._JOBS_FILE = orig_jobs_file
            ss._ARCHIVE_DIR = orig_archive_dir


if __name__ == "__main__":
    unittest.main()
