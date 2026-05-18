import json
import os
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

    def test_write_file_output_prefix_not_duplicated(self):
        ex = self._executor()
        with tempfile.TemporaryDirectory() as td:
            ex.set_runtime_context(session_id="test", task_dir=Path(td))
            params = {"path": "output/artifacts/hello.txt", "content": "hello"}
            violation = ex._apply_path_policy("write_file", params)  # noqa: SLF001
            self.assertIsNone(violation)
            resolved = Path(params["path"]).resolve()
            self.assertTrue(str(resolved).endswith("output\\artifacts\\hello.txt"))
            self.assertNotIn("output\\output\\", str(resolved).lower())

    def test_write_file_execute_does_not_false_fail_on_system_exit_zero(self):
        ex = self._executor()
        with tempfile.TemporaryDirectory() as td:
            ex.set_runtime_context(session_id="test", task_dir=Path(td))
            result = ex.execute(ToolCall(tool_name="write_file", params={"path": "output/ok.txt", "content": "ok"}))
            self.assertEqual(result.get("status"), "success")
            payload = result.get("result")
            self.assertIsInstance(payload, dict)
            self.assertEqual(str(payload.get("status", "")).lower(), "success")

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

    def test_cmd_del_flags_do_not_trigger_false_outside_targets(self):
        ex = self._executor()
        with tempfile.TemporaryDirectory() as td:
            ex.set_runtime_context(session_id="test", task_dir=Path(td))
            out = Path(td) / "output"
            out.mkdir(parents=True, exist_ok=True)
            target = out / "local_tmp.txt"
            target.write_text("x", encoding="utf-8")
            result = ex.execute(
                ToolCall(
                    tool_name="run_shell_command",
                    params={"command": "del /f /q local_tmp.txt", "shell_preference": "cmd"},
                )
            )
            self.assertEqual(result.get("status"), "success")
            self.assertFalse(target.exists())

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

    def test_shell_targeting_immutable_core_is_blocked(self):
        ex = self._executor()
        prior = os.environ.get("OVERLORD11_IMMUTABLE_CORE_PATHS")
        os.environ["OVERLORD11_IMMUTABLE_CORE_PATHS"] = json.dumps(["engine/"])
        try:
            with tempfile.TemporaryDirectory() as td:
                ex.set_runtime_context(session_id="test", task_dir=Path(td))
                params = {"command": 'Set-Content -LiteralPath "engine/runner.py" -Value "x"'}
                violation = ex._apply_path_policy("run_shell_command", params)  # noqa: SLF001
                self.assertIsInstance(violation, dict)
                self.assertEqual(violation.get("reason"), "shell_immutable_core_target_blocked")
        finally:
            if prior is None:
                os.environ.pop("OVERLORD11_IMMUTABLE_CORE_PATHS", None)
            else:
                os.environ["OVERLORD11_IMMUTABLE_CORE_PATHS"] = prior

    def test_verification_outside_writes_allowlisted_are_diagnostic_not_violation(self):
        ex = self._executor()
        repo_root = Path(__file__).resolve().parent.parent
        with tempfile.TemporaryDirectory() as td:
            ex.set_runtime_context(session_id="test", task_dir=Path(td))
            before = {}
            after = {
                str((repo_root / "logs" / "master.jsonl").resolve()): (1, 1),
                str((repo_root / "workspace" / "S1" / "artifacts" / "logs" / "events.json").resolve()): (1, 1),
            }
            violation, diagnostic = ex._audit_shell_write_violation(  # noqa: SLF001
                before,
                after,
                command="python -m unittest discover tests",
            )
            self.assertIsNone(violation)
            self.assertIsInstance(diagnostic, dict)
            self.assertEqual(diagnostic.get("status"), "allowed_external_artifact_write")

    def test_verification_outside_writes_to_protected_path_are_blocked(self):
        ex = self._executor()
        repo_root = Path(__file__).resolve().parent.parent
        with tempfile.TemporaryDirectory() as td:
            ex.set_runtime_context(session_id="test", task_dir=Path(td))
            before = {}
            after = {
                str((repo_root / "Consciousness.md").resolve()): (1, 1),
            }
            violation, diagnostic = ex._audit_shell_write_violation(  # noqa: SLF001
                before,
                after,
                command="python -m unittest discover tests",
            )
            self.assertIsNone(diagnostic)
            self.assertIsInstance(violation, dict)
            self.assertEqual(violation.get("status"), "policy_violation")
            self.assertEqual(violation.get("reason"), "shell_write_outside_task_root_verification_blocked")


if __name__ == "__main__":
    unittest.main()
