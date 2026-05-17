import argparse
import json
import os
import platform
import re
import shutil
import subprocess
from pathlib import Path
from typing import Optional


def _available_shells() -> dict[str, dict]:
    system_name = platform.system().lower()
    shell_env = os.environ.get("SHELL") or os.environ.get("COMSPEC") or ""
    shells: dict[str, dict] = {}

    def _add_shell(shell_name: str, executable: str, args: list[str]) -> None:
        resolved = executable if os.path.isabs(executable) else shutil.which(executable)
        if resolved:
            shells[shell_name] = {
                "name": shell_name,
                "path": resolved,
                "argv_prefix": [resolved, *args],
                "shell_env": shell_env,
                "platform": system_name,
            }

    if system_name == "windows":
        _add_shell("powershell", "powershell.exe", ["-NoProfile", "-Command"])
        _add_shell("pwsh", "pwsh", ["-NoProfile", "-Command"])
        _add_shell("cmd", "cmd.exe", ["/C"])
        # Optional POSIX-style shells on Windows (e.g., Git Bash / MSYS)
        _add_shell("bash", "bash", ["-lc"])
        _add_shell("sh", "sh", ["-lc"])
    else:
        for shell_name in (shell_env, "bash", "zsh", "sh"):
            if not shell_name:
                continue
            executable = shell_name if os.path.isabs(shell_name) else shell_name
            key = Path(executable).name.lower() if os.path.isabs(executable) else shell_name.lower()
            _add_shell(key, executable, ["-lc"])
    return shells


def _detect_shell(shell_preference: str = "auto") -> dict:
    shells = _available_shells()
    preference = (shell_preference or "auto").strip().lower()
    if preference != "auto" and preference in shells:
        return shells[preference]

    # Deterministic default order.
    default_order = (
        ["powershell", "pwsh", "cmd", "bash", "sh"]
        if platform.system().lower() == "windows"
        else ["bash", "zsh", "sh"]
    )
    for name in default_order:
        if name in shells:
            return shells[name]
    if shells:
        return next(iter(shells.values()))

    return {
        "name": "unknown",
        "path": None,
        "argv_prefix": [],
        "shell_env": os.environ.get("SHELL") or os.environ.get("COMSPEC") or "",
        "platform": platform.system().lower(),
    }


def _shell_family(shell_name: str) -> str:
    name = (shell_name or "").lower()
    if name in {"powershell", "pwsh"}:
        return "powershell"
    if name == "cmd":
        return "cmd"
    if name in {"bash", "sh", "zsh"}:
        return "posix"
    return "unknown"


def _detect_command_style(command: str) -> dict:
    cmd = command or ""
    reasons: list[str] = []
    scores = {"powershell": 0, "cmd": 0, "posix": 0}

    patterns = {
        "powershell": [
            r"\$env:[A-Za-z_]\w*",
            r"\b(Get|Set|Remove|Copy|Move|Test)-[A-Za-z]+\b",
            r"\bWhere-Object\b",
            r"\bSelect-String\b",
            r"\bOut-File\b",
            r"-LiteralPath\b",
        ],
        "cmd": [
            r"%[A-Za-z_]\w*%",
            r"(^|\s)dir(\s|$)",
            r"(^|\s)findstr(\s|$)",
            r"(^|\s)copy(\s|$)",
            r"(^|\s)del(\s|$)",
            r"(^|\s)type(\s|$)",
            r"(^|\s)set\s+[A-Za-z_]\w*=",
        ],
        "posix": [
            r"\$\{?[A-Za-z_]\w*\}?",
            r"(^|\s)export\s+[A-Za-z_]\w*=",
            r"(^|\s)(ls|grep|sed|awk|chmod|chown|sudo|pwd|touch)\b",
            r"/[A-Za-z0-9._-]+(/[A-Za-z0-9._-]+)+",
            r"(^|\s)\./[A-Za-z0-9._/-]+",
        ],
    }

    for style, regs in patterns.items():
        for rx in regs:
            if re.search(rx, cmd):
                scores[style] += 1
                reasons.append(f"{style}:{rx}")

    style = "unknown"
    best_score = 0
    for key in ("powershell", "cmd", "posix"):
        if scores[key] > best_score:
            best_score = scores[key]
            style = key

    return {
        "style": style,
        "score": best_score,
        "reasons": reasons[:8],
    }


def _is_style_compatible(command_style: str, shell_name: str) -> bool:
    if command_style == "unknown":
        return True
    family = _shell_family(shell_name)
    if command_style == "powershell":
        return family == "powershell"
    if command_style == "cmd":
        return family == "cmd"
    if command_style == "posix":
        return family == "posix"
    return True


def _find_compatible_shell(command_style: str, preferred: str = "auto") -> Optional[dict]:
    shells = _available_shells()
    preference = (preferred or "auto").strip().lower()
    if preference != "auto" and preference in shells:
        candidate = shells[preference]
        if _is_style_compatible(command_style, candidate.get("name", "")):
            return candidate

    for candidate in shells.values():
        if _is_style_compatible(command_style, candidate.get("name", "")):
            return candidate
    return None


def _shell_mismatch_hint(command_style: str, shell_name: str) -> str:
    if command_style == "posix":
        return (
            f"Detected POSIX-style command but active shell is '{shell_name}'. "
            "Use bash/sh syntax only with bash/sh; otherwise translate command to PowerShell/cmd."
        )
    if command_style == "powershell":
        return (
            f"Detected PowerShell-style command but active shell is '{shell_name}'. "
            "Use cmd/bash syntax only with those shells, or switch shell_preference to powershell/pwsh."
        )
    if command_style == "cmd":
        return (
            f"Detected cmd-style command but active shell is '{shell_name}'. "
            "Use shell_preference='cmd' or translate command to PowerShell."
        )
    return "Command style could not be determined."


def _normalize_bool(value: object, default: bool) -> bool:
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() not in {"0", "false", "no", "off"}
    return bool(value)


def _validate_shell_preference(shell_preference: str) -> Optional[dict]:
    allowed = {"auto", "powershell", "pwsh", "cmd", "bash", "sh", "zsh"}
    pref = (shell_preference or "auto").strip().lower()
    if pref not in allowed:
        return {
            "status": "error",
            "command": "",
            "directory": str(Path(".").resolve()),
            "stdout": "(empty)",
            "stderr": f"Invalid shell_preference: {shell_preference}",
            "error": "InvalidShellPreference",
            "hint": f"Use one of: {', '.join(sorted(allowed))}",
            "exit_code": 2,
            "shell": _detect_shell(),
            "environment": describe_environment(),
        }
    return None


def _select_shell_for_command(
    command: str,
    shell_preference: str,
    auto_switch_shell: bool,
) -> tuple[dict, dict, bool]:
    shell_info = _detect_shell(shell_preference=shell_preference)
    style = _detect_command_style(command)
    switched = False
    if style["style"] != "unknown" and not _is_style_compatible(style["style"], shell_info.get("name", "")):
        if auto_switch_shell:
            compatible = _find_compatible_shell(style["style"], preferred=shell_preference)
            if compatible is not None and compatible.get("name") != shell_info.get("name"):
                shell_info = compatible
                switched = True
    return shell_info, style, switched


def _build_mismatch_response(
    *,
    command: str,
    execution_dir: Path,
    shell_info: dict,
    style: dict,
) -> dict:
    return {
        "status": "error",
        "command": command,
        "directory": str(execution_dir),
        "stdout": "(empty)",
        "stderr": (
            f"Shell/command mismatch: detected '{style.get('style')}' style, "
            f"selected shell '{shell_info.get('name')}'."
        ),
        "error": "ShellStyleMismatch",
        "hint": _shell_mismatch_hint(style.get("style", "unknown"), shell_info.get("name", "unknown")),
        "exit_code": 2,
        "shell": shell_info,
        "environment": describe_environment(),
        "command_style": style,
    }


def describe_environment() -> dict:
    shell_info = _detect_shell(shell_preference="auto")
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
    shell_preference: str = "auto",
    reject_on_shell_mismatch: bool = True,
    auto_switch_shell: bool = True,
) -> dict:
    """Execute a shell command using the best available local shell for the host OS."""
    pref_error = _validate_shell_preference(shell_preference)
    if pref_error is not None:
        return pref_error

    requested_dir = dir_path or working_dir or "."
    execution_dir = Path(requested_dir).resolve()
    reject_mismatch = _normalize_bool(reject_on_shell_mismatch, True)
    auto_switch = _normalize_bool(auto_switch_shell, True)
    shell_info, style, switched = _select_shell_for_command(
        command=command,
        shell_preference=shell_preference,
        auto_switch_shell=auto_switch,
    )

    if not execution_dir.is_dir():
        return {
            "status": "error",
            "command": command,
            "directory": str(execution_dir),
            "stdout": "(empty)",
            "stderr": f"Error: Directory not found: {execution_dir}",
            "error": "DirectoryNotFound",
            "hint": "Verify the working_dir path exists before running the command.",
            "exit_code": 1,
            "shell": shell_info,
            "environment": describe_environment(),
            "command_style": style,
        }

    if not shell_info["path"]:
        return {
            "status": "error",
            "command": command,
            "directory": str(execution_dir),
            "stdout": "(empty)",
            "stderr": "No supported shell executable was found on PATH.",
            "error": "ShellNotFound",
            "hint": "Ensure bash, sh, or cmd.exe is available in PATH.",
            "exit_code": 1,
            "shell": shell_info,
            "environment": describe_environment(),
            "command_style": style,
        }

    style_mismatch = (
        style.get("style") != "unknown"
        and not _is_style_compatible(style.get("style", "unknown"), shell_info.get("name", "unknown"))
    )
    if style_mismatch and reject_mismatch:
        return _build_mismatch_response(
            command=command,
            execution_dir=execution_dir,
            shell_info=shell_info,
            style=style,
        )

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

    succeeded = exit_code == 0 and error_message == "(none)"
    return {
        "status": "success" if succeeded else "error",
        "command": command,
        "directory": str(execution_dir),
        "stdout": stdout_output,
        "stderr": stderr_output,
        "error": error_message,
        "exit_code": exit_code,
        "shell": shell_info,
        "environment": describe_environment(),
        "command_style": style,
        "shell_switched_for_style": switched,
        "style_mismatch_detected": style_mismatch,
        "style_mismatch_hint": _shell_mismatch_hint(style.get("style", "unknown"), shell_info.get("name", "unknown"))
        if style_mismatch else "",
    }


def main(**kwargs):
    # ToolExecutor calls main(**params) directly. Never invoke argparse in this path.
    if kwargs is not None:
        direct_kwargs = dict(kwargs)
        include_env = bool(direct_kwargs.pop("describe_environment", False))
        command = direct_kwargs.get("command")
        if not command:
            return {
                "status": "error",
                "command": "",
                "directory": str(Path(direct_kwargs.get("working_dir", ".")).resolve()),
                "stdout": "(empty)",
                "stderr": "Missing required parameter: command",
                "error": "MissingCommand",
                "hint": "Provide the 'command' parameter with the shell command to execute.",
                "exit_code": 2,
                "shell": _detect_shell(),
                "environment": describe_environment(),
            }
        result = run_shell_command(**direct_kwargs)
        if include_env:
            result["environment"] = describe_environment()
        return result


def cli_main():
    parser = argparse.ArgumentParser(description="Run a shell command")
    parser.add_argument("--command", required=True)
    parser.add_argument("--working_dir", default=".")
    parser.add_argument("--timeout_seconds", type=int, default=60)
    parser.add_argument("--env", default="{}")
    parser.add_argument("--dir_path", default=None)
    parser.add_argument("--describe_environment", action="store_true")
    parser.add_argument("--shell_preference", default="auto")
    parser.add_argument("--reject_on_shell_mismatch", default="false")
    parser.add_argument("--auto_switch_shell", default="true")
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
        shell_preference=args.shell_preference,
        reject_on_shell_mismatch=args.reject_on_shell_mismatch.lower() not in {"0", "false", "no", "off"},
        auto_switch_shell=args.auto_switch_shell.lower() not in {"0", "false", "no", "off"},
    )
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    cli_main()
