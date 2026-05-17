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


if __name__ == "__main__":
    unittest.main()
