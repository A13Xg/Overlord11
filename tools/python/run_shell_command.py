import argparse
import json
import os
import platform
import shutil
import subprocess
from pathlib import Path
from typing import Optional


def _detect_shell() -> dict:
    system_name = platform.system().lower()
    shell_env = os.environ.get("SHELL") or os.environ.get("COMSPEC") or ""

    if system_name == "windows":
        for shell_name, executable, args in (
            ("powershell", "powershell.exe", ["-NoProfile", "-Command"]),
            ("pwsh", "pwsh", ["-NoProfile", "-Command"]),
            ("cmd", "cmd.exe", ["/C"]),
        ):
            resolved = shutil.which(executable)
            if resolved:
                return {
                    "name": shell_name,
                    "path": resolved,
                    "argv_prefix": [resolved, *args],
                    "shell_env": shell_env,
                    "platform": system_name,
                }
    else:
        for shell_name in (shell_env, "bash", "sh"):
            if not shell_name:
                continue
            executable = shell_name if os.path.isabs(shell_name) else shutil.which(shell_name)
            if executable:
                return {
                    "name": Path(executable).name,
                    "path": executable,
                    "argv_prefix": [executable, "-lc"],
                    "shell_env": shell_env,
                    "platform": system_name,
                }

    return {
        "name": "unknown",
        "path": None,
        "argv_prefix": [],
        "shell_env": shell_env,
        "platform": system_name,
    }


def describe_environment() -> dict:
    shell_info = _detect_shell()
    return {
        "platform": platform.platform(),
        "system": platform.system(),
        "release": platform.release(),
        "machine": platform.machine(),
        "python_version": platform.python_version(),
        "cwd": os.getcwd(),
        "shell": shell_info,
        "env": {
            "SHELL": os.environ.get("SHELL", ""),
            "COMSPEC": os.environ.get("COMSPEC", ""),
            "TERM": os.environ.get("TERM", ""),
            "USER": os.environ.get("USER", ""),
        },
    }


def run_shell_command(
    command: str,
    working_dir: str = ".",
    timeout_seconds: int = 60,
    env: Optional[dict] = None,
    dir_path: Optional[str] = None,
) -> dict:
    """Execute a shell command using the best available local shell for the host OS."""
    shell_info = _detect_shell()
    requested_dir = dir_path or working_dir or "."
    execution_dir = Path(requested_dir).resolve()

    if not execution_dir.is_dir():
        return {
            "Command": command,
            "Directory": str(execution_dir),
            "Stdout": "(empty)",
            "Stderr": f"Error: Directory not found: {execution_dir}",
            "Error": "DirectoryNotFound",
            "Exit Code": 1,
            "Shell": shell_info,
            "Environment": describe_environment(),
        }

    if not shell_info["path"]:
        return {
            "Command": command,
            "Directory": str(execution_dir),
            "Stdout": "(empty)",
            "Stderr": "No supported shell executable was found on PATH.",
            "Error": "ShellNotFound",
            "Exit Code": 1,
            "Shell": shell_info,
            "Environment": describe_environment(),
        }

    run_env = os.environ.copy()
    for key, value in (env or {}).items():
        run_env[str(key)] = str(value)

    stdout_output = "(empty)"
    stderr_output = "(empty)"
    error_message = "(none)"
    exit_code = None

    try:
        result = subprocess.run(
            [*shell_info["argv_prefix"], command],
            capture_output=True,
            text=True,
            check=False,
            cwd=str(execution_dir),
            timeout=max(1, int(timeout_seconds)),
            env=run_env,
        )
        stdout_output = result.stdout.strip() if result.stdout else "(empty)"
        stderr_output = result.stderr.strip() if result.stderr else "(empty)"
        exit_code = result.returncode
        if result.returncode != 0 and stderr_output == "(empty)":
            stderr_output = f"Command failed with exit code {result.returncode}."
    except subprocess.TimeoutExpired as exc:
        stdout_output = (exc.stdout or "").strip() or "(empty)"
        stderr_output = (exc.stderr or "").strip() or f"Command timed out after {timeout_seconds} seconds."
        error_message = "TimeoutExpired"
        exit_code = 124
    except Exception as exc:
        error_message = str(exc)
        exit_code = 1

    return {
        "Command": command,
        "Directory": str(execution_dir),
        "Stdout": stdout_output,
        "Stderr": stderr_output,
        "Error": error_message,
        "Exit Code": exit_code,
        "Shell": shell_info,
        "Environment": describe_environment(),
    }


def main(**kwargs):
    # ToolExecutor calls main(**params) directly. Never invoke argparse in this path.
    if kwargs is not None:
        command = kwargs.get("command")
        if not command:
            return {
                "Command": "",
                "Directory": str(Path(kwargs.get("working_dir", ".")).resolve()),
                "Stdout": "(empty)",
                "Stderr": "Missing required parameter: command",
                "Error": "MissingCommand",
                "Exit Code": 2,
                "Shell": _detect_shell(),
                "Environment": describe_environment(),
            }
        return run_shell_command(**kwargs)


def cli_main():
    parser = argparse.ArgumentParser(description="Run a shell command")
    parser.add_argument("--command", required=True)
    parser.add_argument("--working_dir", default=".")
    parser.add_argument("--timeout_seconds", type=int, default=60)
    parser.add_argument("--env", default="{}")
    parser.add_argument("--dir_path", default=None)
    parser.add_argument("--describe_environment", action="store_true")
    args = parser.parse_args()

    if args.describe_environment:
        print(json.dumps(describe_environment(), indent=2))
        return

    env = json.loads(args.env) if args.env else {}
    result = run_shell_command(
        command=args.command,
        working_dir=args.working_dir,
        timeout_seconds=args.timeout_seconds,
        env=env,
        dir_path=args.dir_path,
    )
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    cli_main()
