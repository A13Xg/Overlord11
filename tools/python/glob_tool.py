"""
Overlord11 - Glob Tool
==========================
Find files matching a glob pattern. Returns a list of matching absolute paths
sorted by modification time (newest first).

Usage:
    python glob_tool.py --pattern "**/*.py"
    python glob_tool.py --pattern "src/**/*.ts" --base_dir /path/to/project
    python glob_tool.py --pattern "*.json" --include_hidden --max_results 20
"""

import glob as _glob  # aliased to avoid name collision with this module
import json
import os
import sys


def glob_tool(
    pattern: str,
    base_dir: str = ".",
    include_hidden: bool = False,
    max_results: int = 500,
) -> dict:
    """
    Find files matching a glob pattern.

    Args:
        pattern:        Glob pattern to match against. Supports *, **, ?, {a,b}.
                        Examples: '**/*.py', 'src/**/*.ts', '*.{json,yaml}'.
        base_dir:       Base directory to search from. Defaults to current
                        working directory.
        include_hidden: Whether to include hidden files and directories
                        (those starting with '.'). Defaults to False.
        max_results:    Maximum number of results to return. Defaults to 500.

    Returns:
        dict with keys:
            status      – "success" or "error"
            paths       – list of absolute paths matching the pattern (on success)
            count       – number of results returned
            truncated   – true if more matches exist beyond max_results
            pattern     – the glob pattern used
            base_dir    – the resolved base directory searched
            error       – human-readable error message when status is "error"
            hint        – suggested corrective action when status is "error"
    """
    search_root = os.path.abspath(base_dir)

    if not os.path.exists(search_root):
        return {
            "status": "error",
            "pattern": pattern,
            "base_dir": search_root,
            "error": f"base_dir not found: {search_root}",
            "hint": "Check the path spelling. Use list_directory to browse available directories.",
        }

    if not os.path.isdir(search_root):
        return {
            "status": "error",
            "pattern": pattern,
            "base_dir": search_root,
            "error": f"base_dir is not a directory: {search_root}",
            "hint": "Provide a path to a directory, not a file.",
        }

    full_pattern = os.path.join(search_root, pattern)

    try:
        matched = _glob.glob(full_pattern, recursive=True)
    except Exception as exc:
        return {
            "status": "error",
            "pattern": pattern,
            "base_dir": search_root,
            "error": f"Glob pattern error: {exc}",
            "hint": "Check that the pattern uses valid glob syntax (*, **, ?, {a,b}).",
        }

    results = []
    for path in matched:
        # Filter hidden files/dirs if requested
        if not include_hidden:
            parts = os.path.relpath(path, search_root).replace("\\", "/").split("/")
            if any(part.startswith(".") for part in parts):
                continue
        try:
            mtime = os.path.getmtime(path)
            results.append((path, mtime))
        except OSError:
            continue

    results.sort(key=lambda x: x[1], reverse=True)

    truncated = len(results) > max_results
    paths = [p for p, _ in results[:max_results]]

    return {
        "status": "success",
        "paths": paths,
        "count": len(paths),
        "truncated": truncated,
        "pattern": pattern,
        "base_dir": search_root,
    }


def main():
    import argparse
    import io

    if sys.platform == "win32":
        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
        sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")

    parser = argparse.ArgumentParser(description="Overlord11 Glob Tool")
    parser.add_argument("--pattern", required=True, help="Glob pattern to match")
    parser.add_argument("--base_dir", default=".", help="Base directory to search from")
    parser.add_argument("--include_hidden", action="store_true",
                        help="Include hidden files and directories")
    parser.add_argument("--max_results", type=int, default=500,
                        help="Maximum number of results (default 500)")

    args = parser.parse_args()

    result = glob_tool(
        pattern=args.pattern,
        base_dir=args.base_dir,
        include_hidden=args.include_hidden,
        max_results=args.max_results,
    )
    print(json.dumps(result, indent=2, ensure_ascii=False))
    sys.exit(0 if result.get("status") == "success" else 1)


if __name__ == "__main__":
    main()
