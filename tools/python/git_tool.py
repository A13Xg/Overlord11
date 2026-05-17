"""
Overlord11 - Git Tool
======================
Structured Git operations: status, diff, add, commit, push, pull, log,
checkout, branch management, stash, reset, and show.

Usage:
    python git_tool.py --operation status
    python git_tool.py --operation add --files src/main.py src/utils.py
    python git_tool.py --operation commit --message "Fix auth bug"
    python git_tool.py --operation log --args "--oneline" "-10"
    python git_tool.py --operation checkout --branch feature/new-api
    python git_tool.py --operation diff --files src/main.py
"""

import json
import os
import subprocess
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
try:
    from log_manager import log_tool_invocation
    HAS_LOG = True
except ImportError:
    HAS_LOG = False
    def log_tool_invocation(*a, **kw): pass


def git_tool(
    operation: str,
    files: list = None,
    message: str = None,
    branch: str = None,
    args: list = None,
) -> dict:
    """
    Perform a Git version control operation.

    Args:
        operation: Git operation to perform. One of:
                   status, diff, add, commit, push, pull, log,
                   checkout, branch, stash, reset, show.
        files:     List of file paths for operations targeting specific files
                   (add, diff, checkout). If omitted for 'add', stages all changes.
        message:   Commit message. Required for the 'commit' operation.
        branch:    Branch name for 'branch' or 'checkout' operations.
        args:      Additional raw git arguments (e.g., ['--stat'] for diff --stat,
                   ['-n', '10'] for log -n 10).

    Returns:
        dict with keys:
            status    – "success" or "error"
            operation – the operation that was run
            command   – the full git command that was executed
            stdout    – captured standard output (stripped)
            stderr    – captured standard error (stripped)
            returncode – process exit code
            error     – human-readable error message when status is "error"
    """
    VALID_OPERATIONS = {
        "status", "diff", "add", "commit", "push", "pull",
        "log", "checkout", "branch", "stash", "reset", "show",
    }

    if not operation:
        return {
            "status": "error",
            "error": "operation is required.",
            "hint": f"Valid operations: {', '.join(sorted(VALID_OPERATIONS))}",
        }

    if operation not in VALID_OPERATIONS:
        return {
            "status": "error",
            "operation": operation,
            "error": f"Unknown operation: '{operation}'.",
            "hint": f"Valid operations: {', '.join(sorted(VALID_OPERATIONS))}",
        }

    # Validate operation-specific requirements
    if operation == "commit" and not message:
        return {
            "status": "error",
            "operation": "commit",
            "error": "The 'commit' operation requires a 'message' argument.",
            "hint": "Provide --message 'your commit message'.",
        }

    # Build the git command
    cmd = ["git"]

    if operation == "status":
        cmd += ["status", "--short", "--branch"]

    elif operation == "diff":
        cmd += ["diff"]
        if files:
            cmd += ["--"] + files

    elif operation == "add":
        cmd += ["add"]
        if files:
            cmd += files
        else:
            cmd += ["."]  # stage all changes when no files specified

    elif operation == "commit":
        cmd += ["commit", "-m", message]

    elif operation == "push":
        cmd += ["push"]
        if branch:
            cmd += ["origin", branch]

    elif operation == "pull":
        cmd += ["pull"]
        if branch:
            cmd += ["origin", branch]

    elif operation == "log":
        cmd += ["log", "--oneline", "-20"]

    elif operation == "checkout":
        cmd += ["checkout"]
        if branch:
            cmd += [branch]
        elif files:
            cmd += ["--"] + files
        else:
            return {
                "status": "error",
                "operation": "checkout",
                "error": "checkout requires either a 'branch' name or 'files' list.",
                "hint": "Provide --branch <name> to switch branches, or --files to restore files.",
            }

    elif operation == "branch":
        cmd += ["branch"]
        if branch:
            cmd += [branch]  # create new branch

    elif operation == "stash":
        cmd += ["stash"]

    elif operation == "reset":
        cmd += ["reset"]
        if files:
            cmd += ["--"] + files

    elif operation == "show":
        cmd += ["show"]

    # Append extra args
    if args:
        cmd += [str(a) for a in args]

    command_str = " ".join(cmd)

    # Check git availability
    try:
        subprocess.run(["git", "--version"], capture_output=True, check=True)
    except FileNotFoundError:
        return {
            "status": "error",
            "operation": operation,
            "command": command_str,
            "error": "git executable not found in PATH.",
            "hint": "Install Git from https://git-scm.com/ and ensure it is in your PATH.",
        }

    # Execute
    try:
        proc = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
    except Exception as exc:
        return {
            "status": "error",
            "operation": operation,
            "command": command_str,
            "error": f"Failed to execute git command: {exc}",
            "hint": "Check that git is installed and the current directory is a git repository.",
        }

    success = proc.returncode == 0
    result = {
        "status": "success" if success else "error",
        "operation": operation,
        "command": command_str,
        "stdout": proc.stdout.strip(),
        "stderr": proc.stderr.strip(),
        "returncode": proc.returncode,
    }

    if not success:
        result["error"] = proc.stderr.strip() or f"git {operation} exited with code {proc.returncode}."
        result["hint"] = "Review the stderr output above. Common causes: not a git repo, merge conflict, authentication failure."

    return result


def main():
    import argparse
    import io

    if sys.platform == "win32":
        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
        sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")

    parser = argparse.ArgumentParser(description="Overlord11 Git Tool")
    parser.add_argument("--operation", required=True,
                        choices=["status", "diff", "add", "commit", "push", "pull",
                                 "log", "checkout", "branch", "stash", "reset", "show"],
                        help="Git operation to perform")
    parser.add_argument("--files", nargs="*", default=None,
                        help="File paths for add/diff/checkout operations")
    parser.add_argument("--message", default=None, help="Commit message (required for commit)")
    parser.add_argument("--branch", default=None, help="Branch name for branch/checkout")
    parser.add_argument("--args", nargs="*", default=None,
                        help="Additional git arguments")
    parser.add_argument("--session_id", default=None, help="Session ID for logging")

    parsed = parser.parse_args()
    start = time.time()

    result = git_tool(
        operation=parsed.operation,
        files=parsed.files,
        message=parsed.message,
        branch=parsed.branch,
        args=parsed.args,
    )

    duration_ms = (time.time() - start) * 1000
    if HAS_LOG and parsed.session_id:
        log_tool_invocation(
            session_id=parsed.session_id,
            tool_name="git_tool",
            params={"operation": parsed.operation},
            result={"status": result.get("status", "error")},
            duration_ms=duration_ms,
        )

    print(json.dumps(result, indent=2, ensure_ascii=False))
    sys.exit(0 if result.get("status") == "success" else 1)


if __name__ == "__main__":
    main()
