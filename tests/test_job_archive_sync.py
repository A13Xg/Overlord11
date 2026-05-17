import tempfile
import unittest
from pathlib import Path

import backend.core.session_store as ss
from backend.core.session_store import JobStatus, SessionStore


class JobArchiveSyncTests(unittest.TestCase):
    def test_archive_job_workspace_moves_session_dir(self):
        orig_workspace = ss._WORKSPACE_DIR
        orig_jobs_file = ss._JOBS_FILE
        orig_archive_dir = ss._ARCHIVE_DIR
        try:
            with tempfile.TemporaryDirectory() as td:
                ws = Path(td) / "workspace"
                ss._WORKSPACE_DIR = ws
                ss._JOBS_FILE = ws / ".webui_jobs.json"
                ss._ARCHIVE_DIR = ws / "archive"
                store = SessionStore()
                job = store.create_job(title="t", prompt="p")
                session_id = "20260517_010101_abcd1234"
                store.update_job(job.job_id, session_id=session_id, status=JobStatus.COMPLETED)
                src = ws / session_id
                src.mkdir(parents=True, exist_ok=True)
                (src / "artifact.txt").write_text("x", encoding="utf-8")

                job = store.get_job(job.job_id)
                assert job is not None
                result = store.archive_job_workspace(job)

                self.assertFalse(src.exists())
                self.assertGreaterEqual(len(result["moved"]), 1)
                moved_path = Path(result["moved"][0])
                self.assertTrue(moved_path.exists())
                self.assertEqual(moved_path.parent.resolve(), ss._ARCHIVE_DIR.resolve())
                self.assertTrue((moved_path / "artifact.txt").exists())
                self.assertEqual(result["errors"], [])
        finally:
            ss._WORKSPACE_DIR = orig_workspace
            ss._JOBS_FILE = orig_jobs_file
            ss._ARCHIVE_DIR = orig_archive_dir

    def test_archive_job_workspace_falls_back_to_jobid_pattern(self):
        orig_workspace = ss._WORKSPACE_DIR
        orig_jobs_file = ss._JOBS_FILE
        orig_archive_dir = ss._ARCHIVE_DIR
        try:
            with tempfile.TemporaryDirectory() as td:
                ws = Path(td) / "workspace"
                ss._WORKSPACE_DIR = ws
                ss._JOBS_FILE = ws / ".webui_jobs.json"
                ss._ARCHIVE_DIR = ws / "archive"
                store = SessionStore()
                job = store.create_job(title="t", prompt="p")
                src = ws / f"20260517_010101_{job.job_id}"
                src.mkdir(parents=True, exist_ok=True)
                (src / "artifact.txt").write_text("x", encoding="utf-8")

                result = store.archive_job_workspace(job)
                self.assertFalse(src.exists())
                self.assertGreaterEqual(len(result["moved"]), 1)
                self.assertEqual(result["errors"], [])
        finally:
            ss._WORKSPACE_DIR = orig_workspace
            ss._JOBS_FILE = orig_jobs_file
            ss._ARCHIVE_DIR = orig_archive_dir


if __name__ == "__main__":
    unittest.main()
