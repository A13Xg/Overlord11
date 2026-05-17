"""
Overlord11 - Read File Tool
=============================
Read the contents of a file, with optional line-range selection and encoding.

Usage:
    python read_file.py --path /path/to/file.py
    python read_file.py --path notes.md --start_line 10 --end_line 50
    python read_file.py --path data.txt --encoding latin-1
"""

import json
import os
import sys
from pathlib import Path


def read_file(
    path: str,
    encoding: str = "utf-8",
    start_line: int = None,
    end_line: int = None,
) -> dict:
    """
    Read the contents of a text file.

    Args:
        path:       Absolute or relative path to the file to read.
        encoding:   File encoding. Defaults to 'utf-8'. Use 'latin-1' for legacy files.
        start_line: Optional 1-based line number to start reading from.
                    If omitted, reads from the beginning of the file.
        end_line:   Optional 1-based line number to stop reading at (inclusive).
                    If omitted, reads to the end of the file.

    Returns:
        dict with keys:
            status      – "success" or "error"
            path        – resolved absolute path to the file
            content     – file content (possibly a subset if start_line/end_line set)
            total_lines – total line count in the file
            lines_read  – number of lines returned in content
            start_line  – actual start line returned (1-based)
            end_line    – actual end line returned (1-based)
            truncated   – true if only a subset of the file was returned
            encoding    – encoding used to read the file
            error       – human-readable error message when status is "error"
            hint        – suggested corrective action when status is "error"
    """
    resolved = os.path.abspath(path)

    if not os.path.exists(resolved):
        return {
            "status": "error",
            "path": resolved,
            "error": f"File not found: {resolved}",
            "hint": "Check that the path is correct and the file exists. Use list_directory to browse available files.",
        }

    if not os.path.isfile(resolved):
        is_dir = os.path.isdir(resolved)
        return {
            "status": "error",
            "path": resolved,
            "error": f"Path is not a file: {resolved}" + (" (it is a directory)" if is_dir else ""),
            "hint": "Use list_directory to list directory contents, or provide a path to a specific file.",
        }

    try:
        with open(resolved, "r", encoding=encoding, errors="replace") as f:
            lines = f.readlines()
    except LookupError:
        return {
            "status": "error",
            "path": resolved,
            "error": f"Unknown encoding: '{encoding}'.",
            "hint": "Common encodings: 'utf-8', 'utf-8-sig', 'latin-1', 'cp1252', 'ascii'.",
        }
    except OSError as exc:
        return {
            "status": "error",
            "path": resolved,
            "error": f"Could not read file: {exc}",
            "hint": "Check file permissions. The file may be locked by another process.",
        }

    total = len(lines)

    # Resolve line range (convert 1-based to 0-based slice)
    sl = (start_line - 1) if start_line is not None else 0
    el = end_line if end_line is not None else total

    # Clamp to valid range
    sl = max(0, min(sl, total))
    el = max(sl, min(el, total))

    selected = lines[sl:el]
    content = "".join(selected)
    truncated = (sl > 0) or (el < total)

    return {
        "status": "success",
        "path": resolved,
        "content": content,
        "total_lines": total,
        "lines_read": len(selected),
        "start_line": sl + 1,
        "end_line": el,
        "truncated": truncated,
        "encoding": encoding,
    }


def main():
    import argparse
    import io

    if sys.platform == "win32":
        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
        sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")

    parser = argparse.ArgumentParser(description="Overlord11 Read File Tool")
    parser.add_argument("--path", required=True, help="Path to the file to read")
    parser.add_argument("--encoding", default="utf-8", help="File encoding (default: utf-8)")
    parser.add_argument("--start_line", type=int, default=None,
                        help="1-based line number to start reading from")
    parser.add_argument("--end_line", type=int, default=None,
                        help="1-based line number to stop reading at (inclusive)")

    args = parser.parse_args()
    result = read_file(
        path=args.path,
        encoding=args.encoding,
        start_line=args.start_line,
        end_line=args.end_line,
    )
    print(json.dumps(result, indent=2, ensure_ascii=False))
    sys.exit(0 if result["status"] == "success" else 1)


if __name__ == "__main__":
    main()
