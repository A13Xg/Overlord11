import platform
import tempfile
import unittest
from pathlib import Path

from backend.core.shell_executor import ShellExecutor, _get_native_shell


class ShellExecutorTests(unittest.TestCase):
    def test_auto_detection(self):
        """Test that auto-detection returns the correct shell for the OS."""
        native_shell = _get_native_shell()
        if platform.system().lower() == "windows":
            self.assertEqual(native_shell, "powershell")
        else:
            self.assertEqual(native_shell, "bash")

    def test_auto_shell_creation(self):
        """Test that ShellExecutor with 'auto' shell_type auto-detects."""
        with tempfile.TemporaryDirectory() as td:
            ex = ShellExecutor(Path(td), policy="balanced_limited", shell_type="auto")
            expected_shell = _get_native_shell()
            self.assertEqual(ex.shell_type, expected_shell)

    def test_blocks_parent_traversal_powershell(self):
        with tempfile.TemporaryDirectory() as td:
            ex = ShellExecutor(Path(td), policy="balanced_limited", shell_type="powershell")
            res = ex.execute("cd ..; Get-ChildItem")
            self.assertTrue(res.blocked)
            self.assertNotEqual(res.exit_code, 0)

    def test_blocks_parent_traversal_bash(self):
        with tempfile.TemporaryDirectory() as td:
            ex = ShellExecutor(Path(td), policy="balanced_limited", shell_type="bash")
            res = ex.execute("cd ..; ls")
            self.assertTrue(res.blocked)
            self.assertNotEqual(res.exit_code, 0)

    def test_blocks_dangerous_pattern_powershell(self):
        with tempfile.TemporaryDirectory() as td:
            ex = ShellExecutor(Path(td), policy="balanced_limited", shell_type="powershell")
            res = ex.execute("reg delete HKLM\\SOFTWARE\\x /f")
            self.assertTrue(res.blocked)

    def test_blocks_dangerous_pattern_bash(self):
        with tempfile.TemporaryDirectory() as td:
            ex = ShellExecutor(Path(td), policy="balanced_limited", shell_type="bash")
            res = ex.execute("rm -rf /")
            self.assertTrue(res.blocked)

    def test_allows_simple_command_powershell(self):
        with tempfile.TemporaryDirectory() as td:
            ex = ShellExecutor(Path(td), policy="balanced_limited", shell_type="powershell")
            res = ex.execute("Write-Output 'ok'")
            self.assertFalse(res.blocked)
            self.assertEqual(res.exit_code, 0)
            self.assertIn("ok", res.stdout.lower())

    def test_allows_simple_command_bash(self):
        with tempfile.TemporaryDirectory() as td:
            ex = ShellExecutor(Path(td), policy="balanced_limited", shell_type="bash")
            res = ex.execute("echo 'ok'")
            self.assertFalse(res.blocked)
            self.assertEqual(res.exit_code, 0)
            self.assertIn("ok", res.stdout.lower())


if __name__ == "__main__":
    unittest.main()

