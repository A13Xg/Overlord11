import json
import tempfile
import unittest
from pathlib import Path

from engine.tool_executor import ToolExecutor


class ToolParamNormalizationTests(unittest.TestCase):
    def _executor(self):
        root = Path(__file__).resolve().parent.parent
        cfg = json.loads((root / "config.json").read_text(encoding="utf-8"))
        return ToolExecutor(tools_dir=(root / "tools" / "python"), config=cfg)

    def test_replace_aliases_are_normalized(self):
        ex = self._executor()
        params = {"path": "a.txt", "search": "a", "replace": "b"}
        ex._normalize_params("replace", params)  # noqa: SLF001
        self.assertEqual(params.get("old_str"), "a")
        self.assertEqual(params.get("new_str"), "b")
        self.assertNotIn("search", params)
        self.assertNotIn("replace", params)

    def test_task_manager_action_and_status_are_normalized(self):
        ex = self._executor()
        with tempfile.TemporaryDirectory() as td:
            ex.set_runtime_context(session_id="x", task_dir=Path(td))
            params = {"action": "complete", "status": "started"}
            ex._normalize_params("task_manager", params)  # noqa: SLF001
            self.assertEqual(params.get("action"), "complete_task")
            self.assertEqual(params.get("status"), "in_progress")
            self.assertEqual(params.get("project_dir"), str(Path(td).resolve()))

    def test_run_shell_command_aliases_are_normalized(self):
        ex = self._executor()
        params = {"cmd": "echo ok", "cwd": "scratch"}
        ex._normalize_params("run_shell_command", params)  # noqa: SLF001
        self.assertEqual(params.get("command"), "echo ok")
        self.assertEqual(params.get("working_dir"), "scratch")
        self.assertTrue(params.get("reject_on_shell_mismatch"))
        self.assertTrue(params.get("auto_switch_shell"))
        self.assertIn(params.get("shell_preference"), {"powershell", "bash"})

    def test_session_manager_summary_and_session_id_are_normalized(self):
        ex = self._executor()
        with tempfile.TemporaryDirectory() as td:
            ex.set_runtime_context(session_id="S-123", task_dir=Path(td))
            params = {"action": "close", "summary": "done", "status": "completed"}
            ex._normalize_params("session_manager", params)  # noqa: SLF001
            self.assertEqual(params.get("action"), "close")
            self.assertEqual(params.get("session_id"), "S-123")
            self.assertEqual(params.get("description"), "done")
            self.assertIsInstance(params.get("data"), dict)
            self.assertEqual(params["data"].get("summary"), "done")
            self.assertNotIn("status", params)

    def test_save_memory_aliases_are_normalized(self):
        ex = self._executor()
        with tempfile.TemporaryDirectory() as td:
            ex.set_runtime_context(session_id="abc", task_dir=Path(td))
            params = {"title": "k", "text": "v", "file": "Consciousness.md"}
            ex._normalize_params("save_memory", params)  # noqa: SLF001
            self.assertEqual(params.get("key"), "k")
            self.assertEqual(params.get("value"), "v")
            self.assertEqual(params.get("target_file"), "Consciousness.md")

    def test_task_manager_bulk_subtasks_preflight_fails(self):
        ex = self._executor()
        params = {"action": "add_task", "subtasks": [{"id": "1.1"}]}
        violation, validated = ex._preflight_params("task_manager", params)  # noqa: SLF001
        self.assertIsNone(validated)
        self.assertIsInstance(violation, dict)
        self.assertEqual(violation.get("reason"), "invalid_value")

    def test_zip_tool_aliases_are_normalized(self):
        ex = self._executor()
        params = {"action": "create", "zip_path": "out.zip", "source_path": "output/artifacts"}
        ex._normalize_params("zip_tool", params)  # noqa: SLF001
        self.assertEqual(params.get("file"), "out.zip")
        self.assertEqual(params.get("paths"), ["output/artifacts"])
        self.assertNotIn("zip_path", params)
        self.assertNotIn("source_path", params)

    def test_zip_tool_unknown_params_fail_preflight(self):
        ex = self._executor()
        params = {"action": "list", "zip_path_bad": "x.zip"}
        violation, validated = ex._preflight_params("zip_tool", params)  # noqa: SLF001
        self.assertIsNone(validated)
        self.assertIsInstance(violation, dict)
        self.assertEqual(violation.get("reason"), "unknown_parameters")

    def test_python_only_runtime_mode_is_enabled(self):
        ex = self._executor()
        self.assertEqual(ex._execution_mode, "python_only")  # noqa: SLF001


if __name__ == "__main__":
    unittest.main()
