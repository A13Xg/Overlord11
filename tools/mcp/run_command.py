
import os
import subprocess
from pathlib import Path
from typing import Any, Dict

from ._common import fail, ok
from .app import mcp


@mcp.tool(
    name="run_command",
    description="Execute a shell command and return stdout/stderr/exit_code/timed_out in `data`. The shell used depends on the platform: bash on Unix/Linux/macOS, PowerShell on Windows. Use platform-appropriate syntax for the target environment. Prefer this only when dedicated tools are insufficient.",
)
def run_command(
    command: str,
    working_dir: str = "",
    timeout_seconds: int = 30,
    env_vars: Dict[str, str] = {},
    shell: bool = True,
) -> Dict[str, Any]:
    """Run a shell command string.

    Args:
        command: Command string to execute.
        working_dir: Directory to execute from; empty uses current directory.
        timeout_seconds: Timeout in seconds before process termination.
        env_vars: Additional environment variables.
        shell: Whether to run through shell for pipes/redirection support.
    """
    try:
        cwd = Path(working_dir).resolve() if working_dir else Path.cwd()
        if not cwd.exists() or not cwd.is_dir():
            return fail(f"working_dir '{cwd}' does not exist or is not a directory.")
        env = os.environ.copy()
        env.update(env_vars or {})
        try:
            proc = subprocess.run(
                command,
                cwd=str(cwd),
                capture_output=True,
                text=True,
                timeout=timeout_seconds,
                shell=shell,
                env=env,
            )
            data = {
                "stdout": proc.stdout,
                "stderr": proc.stderr,
                "exit_code": proc.returncode,
                "timed_out": False,
            }
        except subprocess.TimeoutExpired as exc:
            data = {
                "stdout": exc.stdout or "",
                "stderr": (exc.stderr or "") + "\nProcess timed out.",
                "exit_code": -1,
                "timed_out": True,
            }
        return ok(data)
    except Exception as exc:
        return fail(f"Failed to run command: {exc}")

