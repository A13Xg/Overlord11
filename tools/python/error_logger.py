"""
Overlord11 - Error Logger
==============================
Manages the ErrorLog.md file within a sandboxed project directory.
Logs errors with severity, context, attempted solutions, and resolution status.

Usage:
    python error_logger.py --action init --project_dir /path/to/project
    python error_logger.py --action log_error --project_dir /path/to/project \
        --title "ImportError in auth module" --severity major \
        --source "src/auth.py" --details "ModuleNotFoundError: bcrypt"
    python error_logger.py --action add_attempt --project_dir /path/to/project \
        --error_id E-001 --attempted_fix "pip install bcrypt"
    python error_logger.py --action resolve_error --project_dir /path/to/project \
        --error_id E-001 --resolution "Added bcrypt to requirements.txt and installed"
"""

import io
import json
import os
import re
import sys
import time
from datetime import datetime
from pathlib import Path

if sys.platform == "win32":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")

sys.path.insert(0, str(Path(__file__).parent))
from log_manager import log_tool_invocation

ERROR_LOG = "ErrorLog.md"

TEMPLATE = """# ErrorLog

> Standardized error tracking for AI agents and humans.
> Errors are logged with severity, context, attempted fixes, and resolution.
> **Severity**: `CRITICAL` = blocks all work | `MAJOR` = blocks current task | `MINOR` = workaround exists | `WARNING` = potential issue

---

## Open Errors

*(No open errors)*

---

## Resolved Errors

*(No resolved errors)*

---

*Last updated: {timestamp}*
"""


def _get_log_path(project_dir: str) -> Path:
    return Path(project_dir).resolve() / ERROR_LOG


def _read_log(project_dir: str) -> str:
    path = _get_log_path(project_dir)
    if path.exists():
        return path.read_text(encoding="utf-8")
    return ""


def _write_log(project_dir: str, content: str):
    path = _get_log_path(project_dir)
    path.parent.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M")
    content = re.sub(r"\*Last updated:.*?\*", f"*Last updated: {timestamp}*", content)
    path.write_text(content, encoding="utf-8")


def _next_error_id(content: str) -> str:
    ids = re.findall(r"E-(\d{3})", content)
    if not ids:
        return "E-001"
    highest = max(int(i) for i in ids)
    return f"E-{highest + 1:03d}"


def _severity_tag(severity: str) -> str:
    return {
        "critical": "**`CRITICAL`**",
        "major": "**`MAJOR`**",
        "minor": "`MINOR`",
        "warning": "`WARNING`"
    }.get(severity, "`MAJOR`")


def init_log(project_dir: str) -> dict:
    path = _get_log_path(project_dir)
    if path.exists():
        return {"status": "already_exists", "path": str(path)}
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M")
    _write_log(project_dir, TEMPLATE.format(timestamp=timestamp))
    return {"status": "created", "path": str(path)}


def log_error(project_dir: str, title: str, severity: str = "major",
              source: str = "", details: str = "") -> dict:
    content = _read_log(project_dir)
    if not content:
        init_log(project_dir)
        content = _read_log(project_dir)

    error_id = _next_error_id(content)
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M")

    error_block = (
        f"### {error_id}: {title}\n"
        f"- **Severity**: {_severity_tag(severity)}\n"
        f"- **Logged**: {timestamp}\n"
        f"- **Source**: `{source}`\n" if source else ""
    )
    # Rebuild properly if source was empty
    if not source:
        error_block = (
            f"### {error_id}: {title}\n"
            f"- **Severity**: {_severity_tag(severity)}\n"
            f"- **Logged**: {timestamp}\n"
        )
    else:
        error_block = (
            f"### {error_id}: {title}\n"
            f"- **Severity**: {_severity_tag(severity)}\n"
            f"- **Logged**: {timestamp}\n"
            f"- **Source**: `{source}`\n"
        )

    error_block += f"- **Status**: OPEN\n"
    if details:
        error_block += f"- **Details**: {details}\n"
    error_block += f"- **Attempted Fixes**:\n  *(none yet)*\n\n"

    # Insert into Open Errors section
    content = content.replace("*(No open errors)*\n\n---\n\n## Resolved",
                              f"---\n\n## Resolved")
    content = content.replace("*(No open errors)*", "")

    marker = "## Resolved Errors"
    if marker in content:
        content = content.replace(marker, f"{error_block}---\n\n{marker}")

    _write_log(project_dir, content)
    return {"status": "logged", "error_id": error_id, "title": title, "severity": severity}


def add_attempt(project_dir: str, error_id: str, attempted_fix: str) -> dict:
    content = _read_log(project_dir)
    if error_id not in content:
        return {"status": "error", "error": f"Error {error_id} not found"}

    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M")
    attempt_line = f"  - [{timestamp}] {attempted_fix}"

    # Replace the "none yet" placeholder or append to attempts list
    if f"### {error_id}:" in content:
        # Find the Attempted Fixes section for this error
        content = content.replace(
            f"  *(none yet)*",
            f"  {attempt_line.strip()}",
            1  # Only replace the first occurrence (closest to current error)
        )
        if attempt_line.strip() not in content:
            # Fallback: insert after the last attempt line
            lines = content.split("\n")
            in_error = False
            in_attempts = False
            insert_idx = None
            for i, line in enumerate(lines):
                if f"{error_id}:" in line:
                    in_error = True
                    continue
                if in_error and "**Attempted Fixes**" in line:
                    in_attempts = True
                    continue
                if in_attempts:
                    if line.strip().startswith("- [") or line.strip().startswith("*("):
                        insert_idx = i + 1
                    elif line.startswith("### ") or line.startswith("## ") or line.startswith("---"):
                        if insert_idx is None:
                            insert_idx = i
                        break
            if insert_idx:
                lines.insert(insert_idx, f"  {attempt_line.strip()}")
                content = "\n".join(lines)

    _write_log(project_dir, content)
    return {"status": "attempt_logged", "error_id": error_id}


def resolve_error(project_dir: str, error_id: str, resolution: str) -> dict:
    content = _read_log(project_dir)
    if error_id not in content:
        return {"status": "error", "error": f"Error {error_id} not found"}

    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M")

    # Update status to RESOLVED
    lines = content.split("\n")
    in_error = False
    for i, line in enumerate(lines):
        if f"{error_id}:" in line:
            in_error = True
            continue
        if in_error and line.strip().startswith("- **Status**:"):
            lines[i] = f"- **Status**: RESOLVED ({timestamp})"
            break
        if in_error and (line.startswith("### ") or line.startswith("## ")):
            break

    # Add resolution line
    for i, line in enumerate(lines):
        if f"{error_id}:" in line:
            in_error = True
            continue
        if in_error and "**Attempted Fixes**" in line:
            lines.insert(i, f"- **Resolution**: {resolution}")
            break
        if in_error and (line.startswith("### ") or line.startswith("## ")):
            lines.insert(i, f"- **Resolution**: {resolution}")
            break

    content = "\n".join(lines)
    _write_log(project_dir, content)
    return {"status": "resolved", "error_id": error_id, "resolution": resolution}


def query_errors(project_dir: str) -> dict:
    content = _read_log(project_dir)
    if not content:
        return {"status": "no_log", "errors": []}

    errors = []
    current = None

    for line in content.split("\n"):
        m = re.match(r"###\s+(E-\d{3}):\s+(.+)", line)
        if m:
            if current:
                errors.append(current)
            current = {
                "id": m.group(1),
                "title": m.group(2).strip(),
                "status": "OPEN",
                "severity": "unknown"
            }
            continue
        if current:
            if "**Status**:" in line:
                if "RESOLVED" in line:
                    current["status"] = "RESOLVED"
            if "**Severity**:" in line:
                if "CRITICAL" in line:
                    current["severity"] = "critical"
                elif "MAJOR" in line:
                    current["severity"] = "major"
                elif "MINOR" in line:
                    current["severity"] = "minor"
                elif "WARNING" in line:
                    current["severity"] = "warning"

    if current:
        errors.append(current)

    open_errors = [e for e in errors if e["status"] == "OPEN"]
    resolved = [e for e in errors if e["status"] == "RESOLVED"]

    return {
        "status": "ok",
        "total": len(errors),
        "open_count": len(open_errors),
        "resolved_count": len(resolved),
        "errors": errors
    }


# --- CLI Interface ---

def main():
    import argparse

    parser = argparse.ArgumentParser(description="Overlord11 Error Logger")
    parser.add_argument("--action", required=True,
                        choices=["log_error", "resolve_error", "add_attempt", "query", "init"])
    parser.add_argument("--project_dir", required=True)
    parser.add_argument("--error_id", default=None)
    parser.add_argument("--title", default="")
    parser.add_argument("--severity", default="major",
                        choices=["critical", "major", "minor", "warning"])
    parser.add_argument("--source", default="")
    parser.add_argument("--details", default="")
    parser.add_argument("--attempted_fix", default="")
    parser.add_argument("--resolution", default="")
    parser.add_argument("--session_id", default=None)

    args = parser.parse_args()
    start = time.time()

    if args.action == "init":
        result = init_log(args.project_dir)
    elif args.action == "log_error":
        result = log_error(args.project_dir, args.title, args.severity,
                           args.source, args.details)
    elif args.action == "add_attempt":
        result = add_attempt(args.project_dir, args.error_id, args.attempted_fix)
    elif args.action == "resolve_error":
        result = resolve_error(args.project_dir, args.error_id, args.resolution)
    elif args.action == "query":
        result = query_errors(args.project_dir)
    else:
        result = {"error": f"Unknown action: {args.action}"}

    duration_ms = (time.time() - start) * 1000

    if args.session_id:
        log_tool_invocation(
            session_id=args.session_id,
            tool_name="error_logger",
            params={"action": args.action, "project_dir": args.project_dir},
            result={"status": result.get("status", "unknown")},
            duration_ms=duration_ms
        )

    print(json.dumps(result, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
