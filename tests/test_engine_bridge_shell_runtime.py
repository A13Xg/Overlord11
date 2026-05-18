import asyncio
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from backend.core.engine_bridge import EngineBridge
from backend.core.session_store import JobStatus, SessionStore


class _DummyBroadcaster:
    def publish(self, _job_id: str, _event: dict) -> None:
        return


class EngineBridgeShellRuntimeTests(unittest.IsolatedAsyncioTestCase):
    async def test_run_job_shell_mode_writes_outputs(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            (root / "workspace").mkdir(parents=True, exist_ok=True)
            (root / "config.json").write_text(
                json.dumps(
                    {
                        "providers": {
                            "active": "openai",
                            "openai": {"model": "gpt-4o", "api_key_env": "OPENAI_API_KEY"},
                        }
                    }
                ),
                encoding="utf-8",
            )

            store = SessionStore()
            job = store.create_job(title="t", prompt="p")
            bridge = EngineBridge()

            with patch("backend.core.engine_bridge._PROJECT_ROOT", root):
                with patch("backend.core.provider_runtime.ProviderRuntime.execute_prompt") as run_mock:
                    run_mock.return_value = type(
                        "R",
                        (),
                        {
                            "provider": "openai",
                            "model": "gpt-4o",
                            "output": "answer",
                            "raw": {"ok": True},
                        },
                    )()
                    await bridge.run_job(job.job_id, store, _DummyBroadcaster())

            updated = store.get_job(job.job_id)
            self.assertIsNotNone(updated)
            assert updated is not None
            self.assertEqual(updated.status, JobStatus.COMPLETED)
            self.assertEqual(updated.completion_mode, "direct_provider")
            self.assertEqual(updated.tool_call_count, 0)
            self.assertTrue(updated.session_id)
            session_root = root / "workspace" / str(updated.session_id)
            self.assertTrue((session_root / "final_output.md").exists())
            self.assertTrue((session_root / "output" / "answer.md").exists())
            self.assertTrue((session_root / "artifacts" / "logs" / "provider_response.json").exists())


if __name__ == "__main__":
    unittest.main()

