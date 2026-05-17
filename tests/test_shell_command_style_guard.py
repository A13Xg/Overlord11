import unittest

from tools.python.run_shell_command import _detect_command_style, run_shell_command


class ShellCommandStyleGuardTests(unittest.TestCase):
    def test_detects_powershell_style(self):
        style = _detect_command_style("Get-ChildItem -LiteralPath . | Select-String -Pattern test")
        self.assertEqual(style["style"], "powershell")

    def test_detects_posix_style(self):
        style = _detect_command_style("ls -la ./src && export FOO=bar && echo $FOO")
        self.assertEqual(style["style"], "posix")

    def test_rejects_style_mismatch_when_requested(self):
        result = run_shell_command(
            command="ls -la ./",
            shell_preference="powershell",
            reject_on_shell_mismatch=True,
            auto_switch_shell=False,
            working_dir=".",
        )
        self.assertEqual(result.get("status"), "error")
        self.assertEqual(result.get("error"), "ShellStyleMismatch")

    def test_invalid_shell_preference_fails_fast(self):
        result = run_shell_command(
            command="echo hello",
            shell_preference="fish",
            working_dir=".",
        )
        self.assertEqual(result.get("status"), "error")
        self.assertEqual(result.get("error"), "InvalidShellPreference")


if __name__ == "__main__":
    unittest.main()

