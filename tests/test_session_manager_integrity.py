import importlib.util
import tempfile
import unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path


def _load_session_manager_module():
    root = Path(__file__).resolve().parent.parent
    module_path = root / "tools" / "python" / "session_manager.py"
    spec = importlib.util.spec_from_file_location("tools_session_manager_for_test", module_path)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)  # type: ignore[union-attr]
    return mod


class SessionManagerIntegrityTests(unittest.TestCase):
    def test_parallel_log_change_keeps_session_manifest_parseable(self):
        sm = _load_session_manager_module()
        original_workspace_dir = sm.WORKSPACE_DIR
        original_session_index = sm.SESSION_INDEX
        with tempfile.TemporaryDirectory() as td:
            temp_workspace = Path(td) / "workspace"
            temp_workspace.mkdir(parents=True, exist_ok=True)
            sm.WORKSPACE_DIR = temp_workspace
            sm.SESSION_INDEX = temp_workspace / "session_index.json"
            try:
                created = sm.create_session(description="integrity-test")
                sid = created["session_id"]

                def _worker(i: int):
                    return sm.log_change(
                        session_id=sid,
                        file_path=f"file_{i}.txt",
                        action="modified",
                        summary="parallel update",
                    )

                with ThreadPoolExecutor(max_workers=8) as pool:
                    list(pool.map(_worker, range(40)))

                loaded = sm.get_session(sid)
                self.assertIsInstance(loaded, dict)
                self.assertNotIn("error", loaded)
                self.assertIsInstance(loaded.get("changes"), list)
            finally:
                sm.WORKSPACE_DIR = original_workspace_dir
                sm.SESSION_INDEX = original_session_index


if __name__ == "__main__":
    unittest.main()
