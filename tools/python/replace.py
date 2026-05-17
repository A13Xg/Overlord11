"""
Overlord11 - Replace Tool
==============================
Find-and-replace text within a file. Replaces the first occurrence by default,
or all occurrences with --replace_all. Returns the number of replacements made.

Usage:
    python replace.py --path src/main.py --old_str "foo" --new_str "bar"
    python replace.py --path config.json --old_str "localhost" --new_str "0.0.0.0" --replace_all
    python replace.py --session_id 20260322_120000 --path file.py --old_str "x" --new_str "y"
"""

import json
import os
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from log_manager import log_tool_invocation


def safe_str(val, max_len: int = 200) -> str:
    """Encoding-safe string conversion."""
    if val is None:
        return "(none)"
    s = str(val)
    if len(s) > max_len:
        s = s[:max_len] + "..."
    try:
        s.encode(sys.stdout.encoding or "utf-8")
        return s
    except (UnicodeEncodeError, LookupError):
        return s.encode("ascii", errors="backslashreplace").decode("ascii")


def replace_in_file(path: str, old_str: str, new_str: str,
                    replace_all: bool = False) -> dict:
    """Perform find-and-replace on a file."""
    file_path = Path(path).resolve()

    if not file_path.exists():
        return {"status": "error", "error": f"File not found: {path}"}

    if not file_path.is_file():
        return {"status": "error", "error": f"Not a file: {path}"}

    try:
        content = file_path.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        content = file_path.read_text(encoding="utf-8", errors="replace")

    if old_str not in content:
        return {
            "status": "no_match",
            "message": f"String not found in {file_path.name}",
            "replacements": 0
        }

    if replace_all:
        count = content.count(old_str)
        new_content = content.replace(old_str, new_str)
    else:
        count = 1
        new_content = content.replace(old_str, new_str, 1)

    file_path.write_text(new_content, encoding="utf-8")

    return {
        "status": "success",
        "file": str(file_path),
        "replacements": count,
        "replace_all": replace_all,
        "old_str_preview": safe_str(old_str, 80),
        "new_str_preview": safe_str(new_str, 80)
    }


def main():
    import argparse
    import io

    if sys.platform == "win32":
        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
        sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")

    parser = argparse.ArgumentParser(description="Overlord11 Replace Tool")
    parser.add_argument("--path", required=True, help="Path to the file to modify")
    parser.add_argument("--old_str", required=True, help="Exact string to find")
    parser.add_argument("--new_str", required=True, help="Replacement string")
    parser.add_argument("--replace_all", action="store_true",
                        help="Replace all occurrences (default: first only)")
    parser.add_argument("--session_id", default=None, help="Session ID for logging")

    args = parser.parse_args()
    start = time.time()

    result = replace_in_file(
        path=args.path,
        old_str=args.old_str,
        new_str=args.new_str,
        replace_all=args.replace_all
    )

    duration_ms = (time.time() - start) * 1000

    if args.session_id:
        log_tool_invocation(
            session_id=args.session_id,
            tool_name="replace",
            params={"path": args.path, "replace_all": args.replace_all},
            result=result,
            duration_ms=duration_ms
        )

    print(json.dumps(result, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
