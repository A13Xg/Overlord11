"""
Purge Overlord11 workspace artifacts on demand.

Usage:
  python scripts/cleanup_workspace.py
  python scripts/cleanup_workspace.py --dry-run
"""

from __future__ import annotations

import argparse
import shutil
from pathlib import Path


TRACKING_FILES = [
    ".webui_jobs.json",
    ".webui_model_state.json",
    ".webui_prefs.json",
    ".mcp_tools_snapshot.json",
    ".setup_complete",
]


def _is_session_dir(path: Path) -> bool:
    name = path.name
    if len(name) < 18:
        return False
    # Matches: YYYYMMDD_HHMMSS_<jobid>
    return name[:8].isdigit() and name[8] == "_" and name[9:15].isdigit() and "_" in name[15:]


def purge_workspace(project_root: Path, dry_run: bool = False) -> dict[str, list[str]]:
    workspace = (project_root / "workspace").resolve()
    if not workspace.exists():
        return {"removed_dirs": [], "removed_files": []}

    removed_dirs: list[str] = []
    removed_files: list[str] = []

    # Purge all session directories
    for child in workspace.iterdir():
        if child.is_dir() and _is_session_dir(child):
            removed_dirs.append(str(child))
            if not dry_run:
                shutil.rmtree(child, ignore_errors=False)

    # Purge all archive contents (keep archive directory itself)
    archive = workspace / "archive"
    if archive.exists() and archive.is_dir():
        for child in archive.iterdir():
            removed_dirs.append(str(child))
            if not dry_run:
                if child.is_dir():
                    shutil.rmtree(child, ignore_errors=False)
                else:
                    child.unlink(missing_ok=True)

    # Remove tracking json/marker files
    for file_name in TRACKING_FILES:
        path = workspace / file_name
        if path.exists():
            removed_files.append(str(path))
            if not dry_run:
                path.unlink(missing_ok=True)

    # Ensure expected directories exist
    if not dry_run:
        (workspace / "archive").mkdir(parents=True, exist_ok=True)
        (workspace / "users").mkdir(parents=True, exist_ok=True)

    return {"removed_dirs": removed_dirs, "removed_files": removed_files}


def main() -> int:
    parser = argparse.ArgumentParser(description="Purge workspace sessions, archive contents, and tracking files.")
    parser.add_argument("--dry-run", action="store_true", help="Show what would be removed without deleting.")
    args = parser.parse_args()

    project_root = Path(__file__).resolve().parent.parent
    result = purge_workspace(project_root=project_root, dry_run=args.dry_run)

    print("Workspace cleanup complete.")
    print(f"Removed directories: {len(result['removed_dirs'])}")
    print(f"Removed tracking files: {len(result['removed_files'])}")
    if args.dry_run:
        print("Dry run only; no changes applied.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

