import tempfile
import unittest
from pathlib import Path

from backend.core.shell_executor import ShellExecutor


class ShellExecutorTests(unittest.TestCase):
    def test_blocks_parent_traversal(self):
        with tempfile.TemporaryDirectory() as td:
            ex = ShellExecutor(Path(td), policy="balanced_limited", shell_type="powershell")
            res = ex.execute("cd ..; Get-ChildItem")
            self.assertTrue(res.blocked)
            self.assertNotEqual(res.exit_code, 0)

    def test_blocks_dangerous_pattern_balanced(self):
        with tempfile.TemporaryDirectory() as td:
            ex = ShellExecutor(Path(td), policy="balanced_limited", shell_type="powershell")
            res = ex.execute("reg delete HKLM\\SOFTWARE\\x /f")
            self.assertTrue(res.blocked)

    def test_allows_simple_command(self):
        with tempfile.TemporaryDirectory() as td:
            ex = ShellExecutor(Path(td), policy="balanced_limited", shell_type="powershell")
            res = ex.execute("Write-Output 'ok'")
            self.assertFalse(res.blocked)
            self.assertEqual(res.exit_code, 0)
            self.assertIn("ok", res.stdout.lower())


if __name__ == "__main__":
    unittest.main()

