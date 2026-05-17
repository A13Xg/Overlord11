"""
Overlord11 - Write File Tool
==============================
Write content to a file, creating the file and any intermediate directories
if they do not exist. Supports overwrite and append modes.

Usage:
    python write_file.py --path output/report.md --content "# Report"
    python write_file.py --path log.txt --content "entry\n" --mode append
    python write_file.py --path data.txt --content "text" --encoding latin-1
"""

import argparse
import json
import os
import sys


def write_file(
    path: str,
    content: str,
    mode: str = "overwrite",
    encoding: str = "utf-8",
) -> dict:
    """
    Write content to a file at the given path.

    Args:
        path:     Absolute or relative path to the file to write.
                  Intermediate directories are created automatically.
        content:  The content to write to the file.
        mode:     'overwrite' (default) replaces any existing content.
                  'append' adds content to the end of the file.
        encoding: File encoding to use when writing. Defaults to 'utf-8'.

    Returns:
        dict with keys:
            status       – "success" or "error"
            path         – resolved absolute path that was written
            mode         – write mode used ('overwrite' or 'append')
            bytes_written – number of bytes written
            encoding     – encoding used
            error        – human-readable error message when status is "error"
            hint         – suggested corrective action when status is "error"
    """
    if mode not in ("overwrite", "append"):
        return {
            "status": "error",
            "path": path,
            "error": f"Invalid mode: '{mode}'. Must be 'overwrite' or 'append'.",
            "hint": "Use mode='overwrite' to replace file contents, or mode='append' to add to the end.",
        }

    try:
        resolved = os.path.abspath(path)
    except (TypeError, ValueError) as exc:
        return {
            "status": "error",
            "path": str(path),
            "error": f"Invalid path: {exc}",
            "hint": "Provide a valid file path string.",
        }

    # Create parent directories
    dir_name = os.path.dirname(resolved)
    if dir_name:
        try:
            os.makedirs(dir_name, exist_ok=True)
        except OSError as exc:
            return {
                "status": "error",
                "path": resolved,
                "error": f"Could not create directory '{dir_name}': {exc}",
                "hint": "Check that you have write permission in the parent directory.",
            }

    try:
        open_mode = "a" if mode == "append" else "w"
        encoded = content.encode(encoding)
        with open(resolved, open_mode, encoding=encoding) as f:
            f.write(content)
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
            "error": f"Could not write to file: {exc}",
            "hint": "Check file permissions. The file may be locked by another process or the disk may be full.",
        }

    return {
        "status": "success",
        "path": resolved,
        "mode": mode,
        "bytes_written": len(encoded),
        "encoding": encoding,
    }


def main(**kwargs):
    """Strategy 1 entry point called by ToolExecutor with schema params as kwargs."""
    if kwargs:
        result = write_file(
            path=kwargs["path"],
            content=kwargs["content"],
            mode=kwargs.get("mode", "overwrite"),
            encoding=kwargs.get("encoding", "utf-8"),
        )
        print(json.dumps(result, indent=2, ensure_ascii=False))
        sys.exit(0 if result["status"] == "success" else 1)

    # Strategy 2 / CLI fallback
    p = argparse.ArgumentParser(description="Write content to a file")
    p.add_argument("--path", required=True, help="Path to the file to write")
    p.add_argument("--content", required=True, help="Content to write")
    p.add_argument("--mode", default="overwrite", choices=["overwrite", "append"],
                   help="Write mode: overwrite (default) or append")
    p.add_argument("--encoding", default="utf-8", help="File encoding (default: utf-8)")
    p.add_argument("--session_id", default=None, help="Session ID for logging")
    args = p.parse_args()
    result = write_file(args.path, args.content, args.mode, args.encoding)
    print(json.dumps(result, indent=2, ensure_ascii=False))
    sys.exit(0 if result["status"] == "success" else 1)


if __name__ == "__main__":
    main()
