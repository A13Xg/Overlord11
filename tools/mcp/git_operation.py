
import subprocess
from pathlib import Path
from typing import Literal, List, Dict, Any

from ._common import fail, ok
from .app import mcp


@mcp.tool(
    name="git_operation",
    description="Execute a git subcommand and return output plus changed_files, branch, and commit_hash in `data`. Use this over run_command for normalized git metadata.",
)
def git_operation(
    repo_path: str,
    operation: Literal["status", "diff", "add", "commit", "log", "branch", "checkout", "pull", "push"],
    args: List[str] = [],
) -> Dict[str, Any]:
    """Run a git operation in a repository.

    Args:
        repo_path: Absolute path to repository root.
        operation: Git operation to execute.
        args: Extra arguments for the git subcommand.
    """
    try:
        repo = Path(repo_path)
        if not (repo / ".git").exists():
            return fail(f"'{repo}' is not a git repository root.")
        cmd = ["git", operation] + args
        proc = subprocess.run(cmd, cwd=str(repo), capture_output=True, text=True)
        if proc.returncode != 0:
            return fail(f"Git command failed: {' '.join(cmd)}\n{proc.stderr.strip()}")

        changed = subprocess.run(["git", "status", "--porcelain"], cwd=str(repo), capture_output=True, text=True)
        changed_files = [line[3:] for line in changed.stdout.splitlines() if len(line) > 3]
        branch_proc = subprocess.run(["git", "rev-parse", "--abbrev-ref", "HEAD"], cwd=str(repo), capture_output=True, text=True)
        head_proc = subprocess.run(["git", "rev-parse", "HEAD"], cwd=str(repo), capture_output=True, text=True)
        return ok(
            {
                "output": proc.stdout or proc.stderr,
                "changed_files": changed_files,
                "branch": branch_proc.stdout.strip() if branch_proc.returncode == 0 else "",
                "commit_hash": head_proc.stdout.strip() if head_proc.returncode == 0 else None,
            }
        )
    except Exception as exc:
        return fail(f"Git operation failed: {exc}")

