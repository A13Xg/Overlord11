"""
Overlord11 - List Directory Tool
=====================================
List the contents of a directory with metadata (size, type, modification time).
Optionally recurse into subdirectories.

Usage:
    python list_directory.py --path /some/dir
    python list_directory.py --path ./src --recursive --filter_extension .py
    python list_directory.py --path . --include_hidden
"""

import json
import os
import sys
from datetime import datetime
from typing import List, Optional


def list_directory(
    path: str,
    recursive: bool = False,
    include_hidden: bool = False,
    filter_extension: Optional[str] = None,
) -> dict:
    """
    List the contents of a directory.

    Args:
        path:             Absolute or relative path to the directory to list.
        recursive:        Whether to recursively list subdirectories.
                          Defaults to False.
        include_hidden:   Whether to include hidden files and directories
                          (those starting with '.'). Defaults to False.
        filter_extension: Optional file extension filter (e.g., '.py', '.json').
                          Only files with this extension are returned.
                          Directories are always included when recursive=True.

    Returns:
        dict with keys:
            status   – "success" or "error"
            path     – the resolved directory path
            entries  – list of entry dicts (name, type, size, modified, path)
            error    – error message if status is "error"
    """
    resolved = os.path.abspath(path)

    if not os.path.exists(resolved):
        return {"status": "error", "error": f"Path not found: {path}"}
    if not os.path.isdir(resolved):
        return {"status": "error", "error": f"Not a directory: {path}"}

    # Normalise extension filter
    ext_filter = filter_extension.lower() if filter_extension else None
    if ext_filter and not ext_filter.startswith("."):
        ext_filter = "." + ext_filter

    entries: List[dict] = []

    def _scan(dir_path: str):
        try:
            names = sorted(os.listdir(dir_path))
        except PermissionError:
            return

        for name in names:
            if not include_hidden and name.startswith("."):
                continue

            full = os.path.join(dir_path, name)
            is_dir = os.path.isdir(full)

            # Apply extension filter to files only
            if ext_filter and not is_dir:
                if not name.lower().endswith(ext_filter):
                    continue

            try:
                stat = os.stat(full)
                size = stat.st_size if not is_dir else None
                modified = datetime.fromtimestamp(stat.st_mtime).isoformat()
            except OSError:
                size = None
                modified = None

            entries.append({
                "name": name,
                "type": "directory" if is_dir else "file",
                "size": size,
                "modified": modified,
                "path": full,
            })

            if recursive and is_dir:
                _scan(full)

    _scan(resolved)

    return {
        "status": "success",
        "path": resolved,
        "entries": entries,
        "count": len(entries),
    }


def main():
    import argparse
    import io

    if sys.platform == "win32":
        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
        sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")

    parser = argparse.ArgumentParser(description="Overlord11 List Directory Tool")
    parser.add_argument("--path", required=True, help="Directory path to list")
    parser.add_argument("--recursive", action="store_true",
                        help="Recursively list subdirectories")
    parser.add_argument("--include_hidden", action="store_true",
                        help="Include hidden files and directories")
    parser.add_argument("--filter_extension", default=None,
                        help="Only show files with this extension (e.g. .py)")

    args = parser.parse_args()

    result = list_directory(
        path=args.path,
        recursive=args.recursive,
        include_hidden=args.include_hidden,
        filter_extension=args.filter_extension,
    )
    print(json.dumps(result, indent=2, ensure_ascii=False))
    sys.exit(0 if result["status"] == "success" else 1)


if __name__ == "__main__":
    main()
