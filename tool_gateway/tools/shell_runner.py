from __future__ import annotations

import os
import re
import shutil
import signal
import subprocess
import time
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from .base import BaseTool

_MAX_OUTPUT_CHARS = 12000
_DANGEROUS_PATTERNS = [
    r"\brm\s+-rf\b",
    r"\bdel\s+/f\b",
    r"\bformat\b",
    r"\bshutdown\b",
    r">\s*/dev/sd",
]
_SECRET_KEY_RE = re.compile(r"(key|token|secret|password)", re.IGNORECASE)


class RunCommandArgs(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    command: str = Field(min_length=1)
    working_directory: str | None = None
    timeout_seconds: int = Field(default=30, ge=1, le=300)
    shell: Literal["auto", "powershell", "cmd", "bash", "sh"] = "auto"
    environment: dict[str, str] = Field(default_factory=dict)
    capture_output: bool = True
    dry_run: bool = False

    @field_validator("shell", mode="before")
    @classmethod
    def normalize_shell(cls, value):
        if isinstance(value, str):
            return value.lower()
        return value


class ShellExecutionAdapter(BaseTool):
    name = "run_command"
    description = "Run shell commands through a controlled structured interface"
    risk_level = "high"
    destructive = True
    supports_dry_run = True
    timeout_behavior = "Kills execution and returns TIMEOUT error envelope"
    examples = [
        {"command": "python --version", "timeout_seconds": 30, "shell": "auto"},
        {"command": "npm test", "working_directory": ".", "dry_run": True},
    ]
    input_model = RunCommandArgs

    def execute(self, args: RunCommandArgs) -> dict[str, Any]:
        command = args.command.strip()
        if not command:
            raise ValueError("command cannot be empty")

        shell_used, shell_path = self._resolve_shell(args.shell)
        workspace_root = self._resolve_workspace_root()
        working_dir = self._resolve_working_directory(args.working_directory, workspace_root)
        warnings: list[str] = []

        for pat in _DANGEROUS_PATTERNS:
            if re.search(pat, command, re.IGNORECASE):
                warnings.append("Command appears high-risk; review carefully before execution")
                break

        if args.dry_run:
            return {
                "command": command,
                "shell_requested": args.shell,
                "shell_used": shell_used,
                "shell_path": shell_path,
                "workspace_root": workspace_root,
                "working_directory": working_dir,
                "exit_code": None,
                "stdout": "",
                "stderr": "",
                "duration_seconds": 0.0,
                "timed_out": False,
                "dry_run": True,
                "warnings": warnings,
            }

        cmd = self._build_command(shell_used, command)
        env = os.environ.copy()
        env.update(args.environment)
        redacted_environment = {k: ("***" if _SECRET_KEY_RE.search(k) else v) for k, v in args.environment.items()}

        t0 = time.monotonic()
        try:
            proc = subprocess.Popen(
                cmd,
                cwd=working_dir,
                env=env,
                stdout=subprocess.PIPE if args.capture_output else None,
                stderr=subprocess.PIPE if args.capture_output else None,
                text=True,
                shell=False,
                start_new_session=(os.name != "nt"),
            )

            stdout, stderr, timed_out, cancelled = self._wait_for_process(
                proc=proc,
                timeout_seconds=args.timeout_seconds,
            )
            duration = time.monotonic() - t0
            return {
                "command": command,
                "shell_requested": args.shell,
                "shell_used": shell_used,
                "shell_path": shell_path,
                "workspace_root": workspace_root,
                "working_directory": working_dir,
                "exit_code": proc.returncode,
                "stdout": (stdout or "")[:_MAX_OUTPUT_CHARS],
                "stderr": (stderr or "")[:_MAX_OUTPUT_CHARS],
                "duration_seconds": round(duration, 4),
                "timed_out": timed_out,
                "cancelled": cancelled,
                "dry_run": False,
                "warnings": warnings,
                "environment": redacted_environment,
            }
        except subprocess.TimeoutExpired as exc:
            duration = time.monotonic() - t0
            stdout = ((exc.stdout or "") if isinstance(exc.stdout, str) else "")[:_MAX_OUTPUT_CHARS]
            stderr = ((exc.stderr or "") if isinstance(exc.stderr, str) else "")[:_MAX_OUTPUT_CHARS]
            return {
                "command": command,
                "shell_requested": args.shell,
                "shell_used": shell_used,
                "shell_path": shell_path,
                "workspace_root": workspace_root,
                "working_directory": working_dir,
                "exit_code": None,
                "stdout": stdout,
                "stderr": stderr,
                "duration_seconds": round(duration, 4),
                "timed_out": True,
                "dry_run": False,
                "warnings": warnings,
                "environment": redacted_environment,
            }

    def _wait_for_process(self, proc: subprocess.Popen, timeout_seconds: int) -> tuple[str, str, bool, bool]:
        start = time.monotonic()
        timed_out = False
        cancelled = False
        while True:
            if self._is_stop_requested():
                cancelled = True
                self._terminate_process_tree(proc)
                break

            elapsed = time.monotonic() - start
            if elapsed >= timeout_seconds:
                timed_out = True
                self._terminate_process_tree(proc)
                break

            try:
                stdout, stderr = proc.communicate(timeout=0.2)
                return stdout or "", stderr or "", timed_out, cancelled
            except subprocess.TimeoutExpired:
                continue

        # Process was cancelled or timed out; collect whatever output remains.
        try:
            stdout, stderr = proc.communicate(timeout=1.0)
        except subprocess.TimeoutExpired:
            self._terminate_process_tree(proc, force=True)
            try:
                stdout, stderr = proc.communicate(timeout=1.0)
            except subprocess.TimeoutExpired:
                stdout, stderr = "", ""
        return stdout or "", stderr or "", timed_out, cancelled

    def _is_stop_requested(self) -> bool:
        # Cancellation is job-scoped and only valid when runtime context is set.
        if not os.environ.get("OVERLORD11_SESSION_ID", "").strip():
            return False
        stop_file = os.environ.get("OVERLORD11_STOP_FILE", "").strip()
        if not stop_file:
            return False
        return Path(stop_file).exists()

    def _terminate_process_tree(self, proc: subprocess.Popen, force: bool = False) -> None:
        if proc.poll() is not None:
            return
        try:
            if os.name == "nt":
                # /T kills child tree, /F forces termination if requested.
                taskkill_cmd = ["taskkill", "/PID", str(proc.pid), "/T"]
                if force:
                    taskkill_cmd.append("/F")
                subprocess.run(taskkill_cmd, capture_output=True, text=True, check=False)
            else:
                pgid = os.getpgid(proc.pid)
                sig = signal.SIGKILL if force else signal.SIGTERM
                os.killpg(pgid, sig)
        except OSError:
            try:
                if force:
                    proc.kill()
                else:
                    proc.terminate()
            except OSError:
                pass

    def _resolve_shell(self, requested: str) -> tuple[str, str | None]:
        if requested != "auto":
            return requested, shutil.which(requested)

        if os.name == "nt":
            pwsh = shutil.which("powershell") or shutil.which("pwsh")
            if pwsh:
                return "powershell", pwsh
            return "cmd", shutil.which("cmd")

        bash = shutil.which("bash")
        if bash:
            return "bash", bash
        return "sh", shutil.which("sh")

    def _build_command(self, shell_used: str, command: str) -> list[str]:
        if shell_used == "powershell":
            exe = shutil.which("powershell") or shutil.which("pwsh") or "powershell"
            return [exe, "-NoProfile", "-NonInteractive", "-Command", command]
        if shell_used == "cmd":
            exe = shutil.which("cmd") or "cmd"
            return [exe, "/d", "/s", "/c", command]
        if shell_used == "bash":
            exe = shutil.which("bash") or "bash"
            return [exe, "-lc", command]
        exe = shutil.which("sh") or "sh"
        return [exe, "-lc", command]

    def _resolve_workspace_root(self) -> str:
        base = os.environ.get("OVERLORD11_TASK_DIR") or os.getcwd()
        return str(Path(base).resolve())

    def _resolve_working_directory(self, requested: str | None, workspace_root: str) -> str:
        workspace_path = Path(workspace_root).resolve()
        if requested:
            candidate = Path(requested)
            resolved = (workspace_path / candidate).resolve() if not candidate.is_absolute() else candidate.resolve()
        else:
            resolved = workspace_path

        try:
            resolved.relative_to(workspace_path)
        except ValueError as exc:
            raise ValueError("working_directory must resolve within workspace root") from exc
        return str(resolved)
