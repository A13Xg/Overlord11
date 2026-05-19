"""
Constrained shell executor for per-session command execution.
"""

from __future__ import annotations

import os
import re
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Optional


class ShellExecutionError(RuntimeError):
    pass


@dataclass
class ShellExecutionResult:
    shell: str
    command: str
    exit_code: int
    stdout: str
    stderr: str
    timed_out: bool
    blocked: bool = False
    block_reason: str = ""


_ABS_PATH_RE = re.compile(r"(?i)([a-z]:\\|\\\\|/)")
_PARENT_TRAVERSAL_RE = re.compile(r"(^|[\s;|&])cd\s+\.\.([\\/\s;|&]|$)", re.IGNORECASE)
_DESTRUCTIVE_PATTERNS = [
    r"(?i)\bformat\s+[a-z]:",
    r"(?i)\bshutdown\b",
    r"(?i)\breboot\b",
    r"(?i)\breg\s+(add|delete)\b",
    r"(?i)\bbcdedit\b",
    r"(?i)\bmountvol\b",
    r"(?i)\bdel\s+/f\s+/s\s+/q\s+[a-z]:\\",
    r"(?i)\brd\s+/s\s+/q\s+[a-z]:\\",
    r"(?i)\bRemove-Item\b.*-Recurse\b.*[a-z]:\\",
]


def _truncate_text(text: str, max_bytes: int) -> str:
    if max_bytes <= 0:
        return ""
    b = text.encode("utf-8", errors="replace")
    if len(b) <= max_bytes:
        return text
    return b[:max_bytes].decode("utf-8", errors="replace") + "\n...[truncated]"


class ShellExecutor:
    def __init__(self, session_root: Path, policy: str = "balanced_limited", shell_type: str = "powershell"):
        self.session_root = session_root.resolve()
        self.policy = (policy or "balanced_limited").strip().lower()
        self.shell_type = (shell_type or "powershell").strip().lower()

    def _validate_command(self, command: str) -> Optional[str]:
        cmd = (command or "").strip()
        if not cmd:
            return "Empty command"

        # Always enforce no obvious directory escapes.
        if _PARENT_TRAVERSAL_RE.search(cmd):
            return "Parent directory traversal is not allowed"

        # Block obvious absolute path usage outside the session root in balanced mode.
        if self.policy == "balanced_limited":
            if _ABS_PATH_RE.search(cmd):
                # Allow only when command references session root explicitly.
                root_str = str(self.session_root).lower().replace("/", "\\")
                if root_str not in cmd.lower().replace("/", "\\"):
                    return "Absolute paths outside session root are not allowed"
            for pattern in _DESTRUCTIVE_PATTERNS:
                if re.search(pattern, cmd):
                    return "Command blocked by balanced_limited safety policy"
        return None

    def execute(self, command: str, timeout_s: int = 120, max_output_bytes: int = 200_000) -> ShellExecutionResult:
        reason = self._validate_command(command)
        if reason:
            return ShellExecutionResult(
                shell=self.shell_type,
                command=command,
                exit_code=126,
                stdout="",
                stderr=reason,
                timed_out=False,
                blocked=True,
                block_reason=reason,
            )

        if self.shell_type not in {"powershell", "pwsh"}:
            raise ShellExecutionError(f"Unsupported shell type: {self.shell_type}")

        exe = "powershell" if self.shell_type == "powershell" else "pwsh"
        # Always run in session root and avoid profile side effects.
        args = [exe, "-NoProfile", "-NonInteractive", "-Command", command]
        env = os.environ.copy()
        proc = None
        try:
            proc = subprocess.run(
                args,
                cwd=str(self.session_root),
                env=env,
                capture_output=True,
                text=True,
                timeout=max(1, int(timeout_s)),
            )
            stdout = _truncate_text(proc.stdout or "", max_output_bytes)
            stderr = _truncate_text(proc.stderr or "", max_output_bytes)
            return ShellExecutionResult(
                shell=self.shell_type,
                command=command,
                exit_code=int(proc.returncode),
                stdout=stdout,
                stderr=stderr,
                timed_out=False,
            )
        except subprocess.TimeoutExpired as exc:
            stdout = _truncate_text((exc.stdout or ""), max_output_bytes)
            stderr = _truncate_text((exc.stderr or ""), max_output_bytes)
            return ShellExecutionResult(
                shell=self.shell_type,
                command=command,
                exit_code=124,
                stdout=stdout,
                stderr=stderr + ("\nCommand timed out." if stderr else "Command timed out."),
                timed_out=True,
            )

