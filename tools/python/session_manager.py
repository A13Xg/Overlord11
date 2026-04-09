"""
Overlord11 - Session Manager
================================
Manages task sessions with unique IDs, tracks changes, and preserves a single
canonical task directory per task under workspace/<task_id>/.

Usage:
    python session_manager.py --action create --description "Implement user auth"
    python session_manager.py --action status --session_id 20260215_120000
    python session_manager.py --action list
    python session_manager.py --action log_change --session_id 20260215_120000 \
        --data '{"file": "src/auth.py", "action": "created", "summary": "Added JWT handler"}'
    python session_manager.py --action close --session_id 20260215_120000
"""

import json
import os
import sys
import time
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from log_manager import log_tool_invocation, log_event
from task_workspace import WORKSPACE_ROOT, ensure_task_layout

BASE_DIR = Path(__file__).resolve().parent.parent.parent
WORKSPACE_DIR = WORKSPACE_ROOT
SESSION_INDEX = WORKSPACE_DIR / "session_index.json"


def _session_manifest_path(session_dir: Path) -> Path:
    # Check new artifacts/logs/ path first, then legacy paths
    artifacts_modern = session_dir / "artifacts" / "logs" / "session.json"
    if artifacts_modern.exists():
        return artifacts_modern
    legacy_modern = session_dir / "logs" / "session.json"
    if legacy_modern.exists():
        return legacy_modern
    return session_dir / "session.json"


def _load_index() -> dict:
    """Load the session index."""
    if SESSION_INDEX.exists():
        try:
            return json.loads(SESSION_INDEX.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            pass
    return {"sessions": {}}


def _save_index(index: dict):
    """Save the session index."""
    WORKSPACE_DIR.mkdir(parents=True, exist_ok=True)
    SESSION_INDEX.write_text(json.dumps(index, indent=2, default=str), encoding="utf-8")


def create_session(description: str = "", tags: list = None) -> dict:
    """Create a new work session with a single canonical task directory."""
    session_id = datetime.now().strftime("%Y%m%d_%H%M%S")
    session_dir = WORKSPACE_DIR / session_id
    suffix = 1
    while session_dir.exists():
        suffix += 1
        session_id = f"{datetime.now().strftime('%Y%m%d_%H%M%S')}_{suffix:02d}"
        session_dir = WORKSPACE_DIR / session_id

    layout = ensure_task_layout(session_dir)

    session = {
        "session_id": session_id,
        "created_at": datetime.now().isoformat(),
        "description": description,
        "tags": tags or [],
        "status": "active",
        "workspace": str(layout["root"]),
        "task_dir": str(layout["root"]),
        "agent_dir": str(layout["agent"]),
        "tools_dir": str(layout["tools"]),
        "logs_dir": str(layout["logs"]),
        "app_dir": str(layout["app"]),
        "changes": [],
        "agents_used": [],
        "tools_used": [],
        "notes": [],
    }

    # Save session manifest in artifacts/logs/
    manifest_path = layout["logs"] / "session.json"
    manifest_path.write_text(json.dumps(session, indent=2, default=str), encoding="utf-8")

    # Update index
    index = _load_index()
    index["sessions"][session_id] = {
        "description": description,
        "status": "active",
        "created_at": session["created_at"],
        "workspace": str(layout["root"]),
        "task_dir": str(layout["root"]),
    }
    _save_index(index)

    log_event(session_id, "session_created", {"description": description})

    return session


def get_session(session_id: str) -> dict:
    """Get full session details."""
    session_dir = WORKSPACE_DIR / session_id
    manifest = _session_manifest_path(session_dir)
    if not manifest.exists():
        return {"error": f"Session not found: {session_id}"}
    try:
        return json.loads(manifest.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as e:
        return {"error": f"Could not read session: {e}"}


def _save_session(session_id: str, session: dict):
    """Save session manifest."""
    session_dir = WORKSPACE_DIR / session_id
    layout = ensure_task_layout(session_dir)
    manifest = layout["logs"] / "session.json"
    manifest.write_text(json.dumps(session, indent=2, default=str), encoding="utf-8")


def log_change(session_id: str, file_path: str, action: str,
               summary: str = "", diff_preview: str = None) -> dict:
    """Log a file change within a session."""
    session = get_session(session_id)
    if "error" in session:
        return session

    change = {
        "timestamp": datetime.now().isoformat(),
        "file": file_path,
        "action": action,  # created, modified, deleted, renamed
        "summary": summary,
    }
    if diff_preview:
        change["diff_preview"] = diff_preview[:500]

    session["changes"].append(change)
    _save_session(session_id, session)

    return {"status": "logged", "change": change}


def log_agent_usage(session_id: str, agent_id: str):
    """Record that an agent was used in this session."""
    session = get_session(session_id)
    if "error" in session:
        return session

    if agent_id not in session["agents_used"]:
        session["agents_used"].append(agent_id)
        _save_session(session_id, session)

    return {"status": "recorded", "agent": agent_id}


def log_tool_usage(session_id: str, tool_name: str):
    """Record that a tool was used in this session."""
    session = get_session(session_id)
    if "error" in session:
        return session

    if tool_name not in session["tools_used"]:
        session["tools_used"].append(tool_name)
        _save_session(session_id, session)

    return {"status": "recorded", "tool": tool_name}


def add_note(session_id: str, note: str) -> dict:
    """Add a note to the session."""
    session = get_session(session_id)
    if "error" in session:
        return session

    session["notes"].append({
        "timestamp": datetime.now().isoformat(),
        "text": note,
    })
    _save_session(session_id, session)

    return {"status": "noted"}


def close_session(session_id: str, summary: str = "") -> dict:
    """Close a session and generate its final summary."""
    session = get_session(session_id)
    if "error" in session:
        return session

    session["status"] = "closed"
    session["closed_at"] = datetime.now().isoformat()
    session["close_summary"] = summary
    session["stats"] = {
        "total_changes": len(session["changes"]),
        "agents_used": len(session["agents_used"]),
        "tools_used": len(session["tools_used"]),
        "notes_count": len(session["notes"]),
        "files_touched": list(set(c["file"] for c in session["changes"])),
    }

    _save_session(session_id, session)

    # Update index
    index = _load_index()
    if session_id in index["sessions"]:
        index["sessions"][session_id]["status"] = "closed"
        index["sessions"][session_id]["closed_at"] = session["closed_at"]
    _save_index(index)

    log_event(session_id, "session_closed", {
        "summary": summary,
        "stats": session["stats"]
    })

    return session


def list_sessions(status: str = None) -> list:
    """List all sessions, optionally filtered by status."""
    index = _load_index()
    sessions = []
    for sid, info in index.get("sessions", {}).items():
        if status and info.get("status") != status:
            continue
        sessions.append({"session_id": sid, **info})
    return sorted(sessions, key=lambda s: s.get("created_at", ""), reverse=True)


def get_active_session() -> dict:
    """Get the most recent active session, if any."""
    active = list_sessions(status="active")
    if active:
        return get_session(active[0]["session_id"])
    return {"status": "no_active_session"}


# --- CLI Interface ---

def main():
    import argparse
    parser = argparse.ArgumentParser(description="Overlord11 Session Manager")
    parser.add_argument("--action", required=True,
                        choices=["create", "status", "log_change", "log_agent",
                                 "log_tool", "add_note", "close", "list", "active"],
                        help="Action to perform")
    parser.add_argument("--session_id", default=None, help="Session ID")
    parser.add_argument("--description", default="", help="Session description")
    parser.add_argument("--data", default="{}", help="JSON data for the action")
    parser.add_argument("--status_filter", default=None, help="Filter sessions by status")

    args = parser.parse_args()
    data = json.loads(args.data)

    start = time.time()

    if args.action == "create":
        result = create_session(
            description=args.description or data.get("description", ""),
            tags=data.get("tags", [])
        )
    elif args.action == "status":
        result = get_session(args.session_id)
    elif args.action == "log_change":
        result = log_change(
            session_id=args.session_id,
            file_path=data.get("file", ""),
            action=data.get("action", "modified"),
            summary=data.get("summary", ""),
            diff_preview=data.get("diff_preview")
        )
    elif args.action == "log_agent":
        result = log_agent_usage(args.session_id, data.get("agent_id", ""))
    elif args.action == "log_tool":
        result = log_tool_usage(args.session_id, data.get("tool_name", ""))
    elif args.action == "add_note":
        result = add_note(args.session_id, data.get("note", ""))
    elif args.action == "close":
        result = close_session(
            session_id=args.session_id,
            summary=data.get("summary", args.description)
        )
    elif args.action == "list":
        result = list_sessions(status=args.status_filter)
    elif args.action == "active":
        result = get_active_session()
    else:
        result = {"error": f"Unknown action: {args.action}"}

    duration_ms = (time.time() - start) * 1000

    log_tool_invocation(
        session_id=args.session_id or "system",
        tool_name="session_manager",
        params={"action": args.action, "session_id": args.session_id},
        result={"status": "success" if "error" not in (result if isinstance(result, dict) else {}) else "error"},
        duration_ms=duration_ms
    )

    print(json.dumps(result, indent=2, default=str))


if __name__ == "__main__":
    main()
