"""
Overlord11 - Task Manager
==============================
Manages the standardized TaskingLog.md file within a sandboxed project directory.
Supports adding tasks/subtasks, marking complete, updating status, and querying.

The TaskingLog.md uses a human+AI readable format with:
  - Sequential task IDs (T-001, T-002, ...)
  - Subtask IDs (T-001.1, T-001.2, ...)
  - Checkboxes for completion status
  - Priority tags, assigned agents, timestamps

Usage:
    python task_manager.py --action init --project_dir /path/to/project
    python task_manager.py --action add_task --project_dir /path/to/project \
        --title "Implement login" --priority high --assigned_agent OVR_COD_03
    python task_manager.py --action add_subtask --project_dir /path/to/project \
        --task_id T-001 --title "Create auth middleware"
    python task_manager.py --action complete_task --project_dir /path/to/project --task_id T-001
    python task_manager.py --action query --project_dir /path/to/project
"""

import io
import json
import os
import re
import sys
import time
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from log_manager import log_tool_invocation

TASKING_LOG = "TaskingLog.md"

TEMPLATE = """# TaskingLog

> Standardized task tracking for AI agents and humans.
> **Format**: Tasks are numbered sequentially. Subtasks are indented under their parent.
> **Status Icons**: `[ ]` = pending, `[~]` = in progress, `[x]` = completed, `[!]` = blocked, `[-]` = skipped

---

## Active Tasks

*(No tasks yet)*

---

## Completed Tasks

*(No completed tasks yet)*

---

*Last updated: {timestamp}*
"""


def _get_log_path(project_dir: str) -> Path:
    return Path(project_dir).resolve() / TASKING_LOG


def _read_log(project_dir: str) -> str:
    path = _get_log_path(project_dir)
    if path.exists():
        return path.read_text(encoding="utf-8")
    return ""


def _write_log(project_dir: str, content: str):
    path = _get_log_path(project_dir)
    path.parent.mkdir(parents=True, exist_ok=True)
    # Update the last-updated timestamp
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M")
    content = re.sub(
        r"\*Last updated:.*?\*",
        f"*Last updated: {timestamp}*",
        content
    )
    path.write_text(content, encoding="utf-8")


def _next_task_id(content: str) -> str:
    """Find the highest T-NNN id and return the next one."""
    ids = re.findall(r"T-(\d{3})", content)
    if not ids:
        return "T-001"
    highest = max(int(i) for i in ids)
    return f"T-{highest + 1:03d}"


def _next_subtask_id(content: str, task_id: str) -> str:
    """Find the highest T-NNN.M id under a given task and return the next one."""
    pattern = re.escape(task_id) + r"\.(\d+)"
    ids = re.findall(pattern, content)
    if not ids:
        return f"{task_id}.1"
    highest = max(int(i) for i in ids)
    return f"{task_id}.{highest + 1}"


def _status_icon(status: str) -> str:
    return {
        "pending": "[ ]",
        "in_progress": "[~]",
        "completed": "[x]",
        "blocked": "[!]",
        "skipped": "[-]"
    }.get(status, "[ ]")


def _priority_tag(priority: str) -> str:
    return {
        "critical": "**`CRITICAL`**",
        "high": "**`HIGH`**",
        "medium": "`MEDIUM`",
        "low": "`LOW`"
    }.get(priority, "`MEDIUM`")


def init_log(project_dir: str) -> dict:
    """Initialize TaskingLog.md if it doesn't exist."""
    path = _get_log_path(project_dir)
    if path.exists():
        return {"status": "already_exists", "path": str(path)}
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M")
    content = TEMPLATE.format(timestamp=timestamp)
    _write_log(project_dir, content)
    return {"status": "created", "path": str(path)}


def add_task(project_dir: str, title: str, description: str = "",
             priority: str = "medium", assigned_agent: str = "") -> dict:
    """Add a new top-level task."""
    content = _read_log(project_dir)
    if not content:
        init_log(project_dir)
        content = _read_log(project_dir)

    task_id = _next_task_id(content)
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M")
    agent_str = f" | Agent: `{assigned_agent}`" if assigned_agent else ""

    task_block = (
        f"### {_status_icon('pending')} {task_id}: {title}\n"
        f"- **Priority**: {_priority_tag(priority)}{agent_str}\n"
        f"- **Created**: {timestamp}\n"
        f"- **Status**: pending\n"
    )
    if description:
        task_block += f"- **Details**: {description}\n"
    task_block += "\n"

    # Insert before the completed section or at end of active section
    marker = "## Completed Tasks"
    if marker in content:
        # Remove the "no tasks yet" placeholder if present
        content = content.replace("*(No tasks yet)*\n\n---\n\n## Completed Tasks",
                                  f"---\n\n## Completed Tasks")
        content = content.replace("*(No tasks yet)*", "")
        content = content.replace(marker, f"{task_block}---\n\n{marker}")
    else:
        content += f"\n{task_block}"

    _write_log(project_dir, content)
    return {"status": "added", "task_id": task_id, "title": title}


def add_subtask(project_dir: str, task_id: str, title: str,
                description: str = "") -> dict:
    """Add a subtask under an existing task."""
    content = _read_log(project_dir)
    if task_id not in content:
        return {"status": "error", "error": f"Task {task_id} not found"}

    subtask_id = _next_subtask_id(content, task_id)

    subtask_line = f"  - {_status_icon('pending')} **{subtask_id}**: {title}"
    if description:
        subtask_line += f" — {description}"
    subtask_line += "\n"

    # Find the task block and insert subtask after the last line of metadata/subtasks
    lines = content.split("\n")
    insert_idx = None
    in_task = False
    for i, line in enumerate(lines):
        if f"{task_id}:" in line:
            in_task = True
            continue
        if in_task:
            # Keep going until we hit an empty line or a new task header
            if line.strip() == "" or line.startswith("### ") or line.startswith("## ") or line.startswith("---"):
                insert_idx = i
                break
    if insert_idx is None:
        insert_idx = len(lines)

    lines.insert(insert_idx, subtask_line.rstrip())
    content = "\n".join(lines)
    _write_log(project_dir, content)

    return {"status": "added", "subtask_id": subtask_id, "parent": task_id, "title": title}


def complete_task(project_dir: str, task_id: str, note: str = "") -> dict:
    """Mark a task as completed."""
    content = _read_log(project_dir)
    if task_id not in content:
        return {"status": "error", "error": f"Task {task_id} not found"}

    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M")

    # Replace status icon in the header
    content = content.replace(
        f"[ ] {task_id}:", f"[x] {task_id}:"
    ).replace(
        f"[~] {task_id}:", f"[x] {task_id}:"
    ).replace(
        f"[!] {task_id}:", f"[x] {task_id}:"
    )
    # Update status line
    # Find and update the Status line for this task
    lines = content.split("\n")
    in_task = False
    for i, line in enumerate(lines):
        if f"{task_id}:" in line:
            in_task = True
            continue
        if in_task:
            if line.strip().startswith("- **Status**:"):
                note_str = f" | {note}" if note else ""
                lines[i] = f"- **Status**: completed ({timestamp}){note_str}"
                break
            if line.startswith("### ") or line.startswith("## "):
                break

    content = "\n".join(lines)
    _write_log(project_dir, content)
    return {"status": "completed", "task_id": task_id}


def complete_subtask(project_dir: str, subtask_id: str) -> dict:
    """Mark a subtask as completed."""
    content = _read_log(project_dir)
    if subtask_id not in content:
        return {"status": "error", "error": f"Subtask {subtask_id} not found"}

    content = content.replace(
        f"[ ] **{subtask_id}**:", f"[x] **{subtask_id}**:"
    ).replace(
        f"[~] **{subtask_id}**:", f"[x] **{subtask_id}**:"
    )
    _write_log(project_dir, content)
    return {"status": "completed", "subtask_id": subtask_id}


def update_status(project_dir: str, task_id: str, status: str,
                  note: str = "") -> dict:
    """Update a task's status."""
    content = _read_log(project_dir)
    if task_id not in content:
        return {"status": "error", "error": f"Task {task_id} not found"}

    icon = _status_icon(status)

    # Update the header icon
    for old_icon in ["[ ]", "[~]", "[x]", "[!]", "[-]"]:
        content = content.replace(f"{old_icon} {task_id}:", f"{icon} {task_id}:")

    # Update status metadata line
    lines = content.split("\n")
    in_task = False
    for i, line in enumerate(lines):
        if f"{task_id}:" in line:
            in_task = True
            continue
        if in_task:
            if line.strip().startswith("- **Status**:"):
                timestamp = datetime.now().strftime("%Y-%m-%d %H:%M")
                note_str = f" | {note}" if note else ""
                lines[i] = f"- **Status**: {status} ({timestamp}){note_str}"
                break
            if line.startswith("### ") or line.startswith("## "):
                break

    content = "\n".join(lines)
    _write_log(project_dir, content)
    return {"status": "updated", "task_id": task_id, "new_status": status}


def query_tasks(project_dir: str) -> dict:
    """Query the current state of the task log."""
    content = _read_log(project_dir)
    if not content:
        return {"status": "no_log", "tasks": []}

    tasks = []
    current_task = None

    for line in content.split("\n"):
        # Match task headers: ### [x] T-001: Title
        m = re.match(r"###\s+\[(.)\]\s+(T-\d{3}):\s+(.+)", line)
        if m:
            if current_task:
                tasks.append(current_task)
            status_char = m.group(1)
            status_map = {"x": "completed", "~": "in_progress", "!": "blocked", "-": "skipped", " ": "pending"}
            current_task = {
                "id": m.group(2),
                "title": m.group(3).strip(),
                "status": status_map.get(status_char, "pending"),
                "subtasks": []
            }
            continue

        # Match subtasks:   - [x] **T-001.1**: Title
        m = re.match(r"\s+-\s+\[(.)\]\s+\*\*(T-\d{3}\.\d+)\*\*:\s+(.+)", line)
        if m and current_task:
            status_char = m.group(1)
            status_map = {"x": "completed", "~": "in_progress", "!": "blocked", "-": "skipped", " ": "pending"}
            current_task["subtasks"].append({
                "id": m.group(2),
                "title": m.group(3).strip(),
                "status": status_map.get(status_char, "pending")
            })

    if current_task:
        tasks.append(current_task)

    pending = [t for t in tasks if t["status"] not in ("completed", "skipped")]
    completed = [t for t in tasks if t["status"] in ("completed", "skipped")]

    return {
        "status": "ok",
        "total": len(tasks),
        "pending_count": len(pending),
        "completed_count": len(completed),
        "tasks": tasks
    }


# --- CLI Interface ---

def main():
    import argparse, io

    if sys.platform == "win32":
        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
        sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")

    parser = argparse.ArgumentParser(description="Overlord11 Task Manager")
    parser.add_argument("--action", required=True,
                        choices=["add_task", "add_subtask", "complete_task",
                                 "complete_subtask", "update_status", "query", "init"])
    parser.add_argument("--project_dir", required=True, help="Path to project directory")
    parser.add_argument("--task_id", default=None)
    parser.add_argument("--subtask_id", default=None)
    parser.add_argument("--title", default="")
    parser.add_argument("--description", default="")
    parser.add_argument("--priority", default="medium",
                        choices=["critical", "high", "medium", "low"])
    parser.add_argument("--assigned_agent", default="")
    parser.add_argument("--status", default="pending",
                        choices=["pending", "in_progress", "blocked", "completed", "skipped"])
    parser.add_argument("--note", default="")
    parser.add_argument("--session_id", default=None)

    args = parser.parse_args()
    start = time.time()

    if args.action == "init":
        result = init_log(args.project_dir)
    elif args.action == "add_task":
        result = add_task(args.project_dir, args.title, args.description,
                          args.priority, args.assigned_agent)
    elif args.action == "add_subtask":
        result = add_subtask(args.project_dir, args.task_id, args.title,
                             args.description)
    elif args.action == "complete_task":
        result = complete_task(args.project_dir, args.task_id, args.note)
    elif args.action == "complete_subtask":
        result = complete_subtask(args.project_dir, args.subtask_id)
    elif args.action == "update_status":
        result = update_status(args.project_dir, args.task_id, args.status,
                               args.note)
    elif args.action == "query":
        result = query_tasks(args.project_dir)
    else:
        result = {"error": f"Unknown action: {args.action}"}

    duration_ms = (time.time() - start) * 1000

    if args.session_id:
        log_tool_invocation(
            session_id=args.session_id,
            tool_name="task_manager",
            params={"action": args.action, "project_dir": args.project_dir},
            result={"status": result.get("status", "unknown")},
            duration_ms=duration_ms
        )

    print(json.dumps(result, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
