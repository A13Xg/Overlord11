import unittest
import tempfile
from pathlib import Path

from tool_gateway.executor import ToolGateway
from tool_gateway.registry import ToolRegistry
from tool_gateway.tools import ShellExecutionAdapter


class ShellRunnerTests(unittest.TestCase):
    def setUp(self):
        reg = ToolRegistry()
        reg.register_tool(ShellExecutionAdapter())
        self.gw = ToolGateway(reg)

    def test_dry_run_does_not_execute(self):
        res = self.gw.execute_tool_call({"tool_name": "run_command", "arguments": {"command": "python --version", "dry_run": True}})
        self.assertTrue(res["ok"])
        self.assertTrue(res["data"]["dry_run"])

    def test_auto_shell_detection_metadata_present(self):
        res = self.gw.execute_tool_call({"tool_name": "run_command", "arguments": {"command": "python --version", "timeout_seconds": 30}})
        self.assertTrue(res["ok"])
        self.assertIn("shell_used", res["data"])

    def test_explicit_powershell_string_validates_and_executes(self):
        res = self.gw.execute_tool_call(
            {"tool_name": "run_command", "arguments": {"command": "python --version", "shell": "powershell", "timeout_seconds": 30}}
        )
        self.assertTrue(res["ok"])

    def test_timeout_enforced(self):
        # portable tiny sleep: python one-liner
        cmd = 'python -c "import time; time.sleep(2)"'
        res = self.gw.execute_tool_call({"tool_name": "run_command", "arguments": {"command": cmd, "timeout_seconds": 1}})
        self.assertTrue(res["ok"])
        self.assertTrue(res["data"]["timed_out"])

    def test_empty_command_rejected(self):
        res = self.gw.execute_tool_call({"tool_name": "run_command", "arguments": {"command": ""}})
        self.assertFalse(res["ok"])

    def test_stdout_stderr_exit_code_returned(self):
        cmd = 'python -c "import sys; print(\'out\'); print(\'err\', file=sys.stderr)"'
        res = self.gw.execute_tool_call({"tool_name": "run_command", "arguments": {"command": cmd}})
        self.assertTrue(res["ok"])
        self.assertIn("stdout", res["data"])
        self.assertIn("stderr", res["data"])
        self.assertIn("exit_code", res["data"])

    def test_working_directory_defaults_to_workspace_root(self):
        with tempfile.TemporaryDirectory() as tmp:
            import os
            old = os.environ.get("OVERLORD11_TASK_DIR")
            os.environ["OVERLORD11_TASK_DIR"] = tmp
            try:
                res = self.gw.execute_tool_call({"tool_name": "run_command", "arguments": {"command": "python --version", "dry_run": True}})
                self.assertTrue(res["ok"])
                self.assertEqual(Path(res["data"]["working_directory"]).resolve(), Path(tmp).resolve())
            finally:
                if old is None:
                    os.environ.pop("OVERLORD11_TASK_DIR", None)
                else:
                    os.environ["OVERLORD11_TASK_DIR"] = old

    def test_working_directory_outside_workspace_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            import os
            old = os.environ.get("OVERLORD11_TASK_DIR")
            os.environ["OVERLORD11_TASK_DIR"] = tmp
            try:
                outside = str((Path(tmp).parent).resolve())
                res = self.gw.execute_tool_call(
                    {"tool_name": "run_command", "arguments": {"command": "python --version", "working_directory": outside, "dry_run": True}}
                )
                self.assertFalse(res["ok"])
            finally:
                if old is None:
                    os.environ.pop("OVERLORD11_TASK_DIR", None)
                else:
                    os.environ["OVERLORD11_TASK_DIR"] = old


if __name__ == "__main__":
    unittest.main()
