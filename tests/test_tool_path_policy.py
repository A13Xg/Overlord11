import json
import tempfile
import unittest
from pathlib import Path
import uuid

from engine.tool_executor import ToolCall, ToolExecutor


class ToolPathPolicyTests(unittest.TestCase):
    def _executor(self):
        root = Path(__file__).resolve().parent.parent
        cfg = json.loads((root / "config.json").read_text(encoding="utf-8"))
        return ToolExecutor(tools_dir=(root / "tools" / "python"), config=cfg)

    def test_write_file_relative_path_is_sandboxed_to_task_output(self):
        ex = self._executor()
        with tempfile.TemporaryDirectory() as td:
            ex.set_runtime_context(session_id="test", task_dir=Path(td))
            params = {"path": "scratch/hello.txt", "content": "hello"}
            violation = ex._apply_path_policy("write_file", params)  # noqa: SLF001
            self.assertIsNone(violation)
            self.assertIn(str(Path(td).resolve() / "output"), params["path"])

    def test_write_file_absolute_outside_task_root_is_blocked(self):
        ex = self._executor()
        with tempfile.TemporaryDirectory() as td:
            ex.set_runtime_context(session_id="test", task_dir=Path(td))
            params = {"path": str((Path(td).resolve().parent / "outside.txt")), "content": "x"}
            violation = ex._apply_path_policy("write_file", params)  # noqa: SLF001
            self.assertIsInstance(violation, dict)
            self.assertEqual(violation.get("status"), "policy_violation")

    def test_shell_parent_traversal_is_blocked(self):
        ex = self._executor()
        with tempfile.TemporaryDirectory() as td:
            ex.set_runtime_context(session_id="test", task_dir=Path(td))
            params = {"command": "type ..\\config.json"}
            violation = ex._apply_path_policy("run_shell_command", params)  # noqa: SLF001
            self.assertIsInstance(violation, dict)
            self.assertEqual(violation.get("reason"), "shell_parent_traversal_blocked")

    def test_shell_preexec_policy_blocks_write_outside_task_root(self):
        ex = self._executor()
        repo_root = Path(__file__).resolve().parent.parent
        outside_path = repo_root / f"_tmp_shell_audit_{uuid.uuid4().hex}.txt"
        with tempfile.TemporaryDirectory() as td:
            ex.set_runtime_context(session_id="test", task_dir=Path(td))
            (Path(td) / "output").mkdir(parents=True, exist_ok=True)
            cmd = f'Set-Content -LiteralPath "{outside_path}" -Value "audit-test"'
            result = ex.execute(ToolCall(tool_name="run_shell_command", params={"command": cmd}))
            self.assertEqual(result.get("status"), "error")
            payload = result.get("result")
            self.assertIsInstance(payload, dict)
            self.assertEqual(payload.get("error"), "ShellWritePolicyViolation")
            self.assertEqual(payload.get("policy_reason"), "write_target_outside_task_root")
            self.assertIn("allowed task workspace", payload.get("stderr", "").lower())
            self.assertFalse(outside_path.exists())
        if outside_path.exists():
            outside_path.unlink()

    def test_shell_mutation_inside_task_root_is_allowed(self):
        ex = self._executor()
        with tempfile.TemporaryDirectory() as td:
            ex.set_runtime_context(session_id="test", task_dir=Path(td))
            (Path(td) / "output").mkdir(parents=True, exist_ok=True)
            cmd = 'Set-Content -LiteralPath "local_ok.txt" -Value "hello"'
            result = ex.execute(ToolCall(tool_name="run_shell_command", params={"command": cmd}))
            self.assertEqual(result.get("status"), "success")
            target = Path(td).resolve() / "output" / "local_ok.txt"
            self.assertTrue(target.exists())

    def test_shell_dynamic_env_write_target_is_blocked(self):
        ex = self._executor()
        with tempfile.TemporaryDirectory() as td:
            ex.set_runtime_context(session_id="test", task_dir=Path(td))
            (Path(td) / "output").mkdir(parents=True, exist_ok=True)
            cmd = 'Set-Content -Path "$env:TEMP\\outside_guard.txt" -Value "x"'
            result = ex.execute(ToolCall(tool_name="run_shell_command", params={"command": cmd}))
            self.assertEqual(result.get("status"), "error")
            payload = result.get("result")
            self.assertIsInstance(payload, dict)
            self.assertEqual(payload.get("error"), "ShellWritePolicyViolation")
            self.assertEqual(payload.get("policy_reason"), "dynamic_path_not_allowed")

    def test_shell_inner_error_is_propagated_as_error_status(self):
        ex = self._executor()
        with tempfile.TemporaryDirectory() as td:
            ex.set_runtime_context(session_id="test", task_dir=Path(td))
            # output directory intentionally missing -> tool returns DirectoryNotFound
            result = ex.execute(
                ToolCall(
                    tool_name="run_shell_command",
                    params={"command": "echo hello"},
                )
            )
            self.assertEqual(result.get("status"), "error")
            payload = result.get("result")
            self.assertIsInstance(payload, dict)
            self.assertEqual(payload.get("status"), "error")


if __name__ == "__main__":
    unittest.main()
