"""
AgenticToolset - Master Log Manager
===================================
Central logging system for all tool invocations, LLM decisions, and agent activity.
All logs written as structured JSONL to the master log and per-session log files.

Usage:
    python log_manager.py --action log_tool --session_id 20260215_120000 \
        --data '{"tool": "project_scanner", "params": {"path": "."}, "result": "success"}'

    python log_manager.py --action log_decision --session_id 20260215_120000 \
        --data '{"agent": "AGNT_ARC_02", "decision": "Use FastAPI for REST layer", "reasoning": "..."}'

    python log_manager.py --action query --session_id 20260215_120000

    python log_manager.py --action summary --session_id 20260215_120000
"""

import json
import os
import sys
import time
from datetime import datetime
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent.parent
LOGS_DIR = BASE_DIR / "logs"
MASTER_LOG = LOGS_DIR / "master.jsonl"
SESSION_LOG_DIR = LOGS_DIR / "sessions"

# Ensure directories exist
LOGS_DIR.mkdir(parents=True, exist_ok=True)
SESSION_LOG_DIR.mkdir(parents=True, exist_ok=True)


def _rotate_log(log_path: Path, max_size_mb: int = 50, rotation_count: int = 5):
    """Rotate log file if it exceeds max size."""
    if not log_path.exists():
        return
    size_mb = log_path.stat().st_size / (1024 * 1024)
    if size_mb < max_size_mb:
        return
    # Shift existing rotations
    for i in range(rotation_count - 1, 0, -1):
        older = log_path.with_suffix(f".{i}.jsonl")
        newer = log_path.with_suffix(f".{i-1}.jsonl") if i > 1 else log_path
        if newer.exists():
            newer.rename(older)
    # Current becomes .1
    if log_path.exists():
        log_path.rename(log_path.with_suffix(".1.jsonl"))


def _write_entry(entry: dict, session_id: str = None):
    """Write a log entry to master log and optional session log."""
    entry["timestamp"] = datetime.now().isoformat()
    entry["epoch"] = time.time()
    line = json.dumps(entry, default=str) + "\n"

    # Rotate and write to master log
    _rotate_log(MASTER_LOG)
    with open(MASTER_LOG, "a", encoding="utf-8") as f:
        f.write(line)

    # Write to session log if session_id provided
    if session_id:
        session_log = SESSION_LOG_DIR / f"{session_id}.jsonl"
        with open(session_log, "a", encoding="utf-8") as f:
            f.write(line)


def log_tool_invocation(session_id: str, tool_name: str, params: dict,
                        result: dict, duration_ms: float = None):
    """Log a tool invocation with its parameters and result."""
    entry = {
        "type": "tool_invocation",
        "session_id": session_id,
        "tool": tool_name,
        "params": params,
        "result": result,
        "duration_ms": duration_ms
    }
    _write_entry(entry, session_id)
    return entry


def log_llm_decision(session_id: str, agent_id: str, decision: str,
                     reasoning: str = None, context: dict = None):
    """Log an LLM decision or output."""
    entry = {
        "type": "llm_decision",
        "session_id": session_id,
        "agent_id": agent_id,
        "decision": decision,
        "reasoning": reasoning,
        "context": context
    }
    _write_entry(entry, session_id)
    return entry


def log_agent_switch(session_id: str, from_agent: str, to_agent: str, reason: str):
    """Log when the active agent role switches."""
    entry = {
        "type": "agent_switch",
        "session_id": session_id,
        "from_agent": from_agent,
        "to_agent": to_agent,
        "reason": reason
    }
    _write_entry(entry, session_id)
    return entry


def log_error(session_id: str, source: str, error: str, traceback: str = None):
    """Log an error event."""
    entry = {
        "type": "error",
        "session_id": session_id,
        "source": source,
        "error": error,
        "traceback": traceback
    }
    _write_entry(entry, session_id)
    return entry


def log_event(session_id: str, event_type: str, data: dict):
    """Log a generic event."""
    entry = {
        "type": event_type,
        "session_id": session_id,
        **data
    }
    _write_entry(entry, session_id)
    return entry


def query_logs(session_id: str = None, log_type: str = None,
               last_n: int = 50) -> list:
    """Query log entries with optional filters."""
    source = (SESSION_LOG_DIR / f"{session_id}.jsonl") if session_id else MASTER_LOG
    if not source.exists():
        return []

    entries = []
    with open(source, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                entry = json.loads(line)
                if log_type and entry.get("type") != log_type:
                    continue
                entries.append(entry)
            except json.JSONDecodeError:
                continue

    return entries[-last_n:]


def session_summary(session_id: str) -> dict:
    """Generate a summary of a session's activity."""
    entries = query_logs(session_id=session_id, last_n=10000)
    if not entries:
        return {"session_id": session_id, "status": "no_entries"}

    summary = {
        "session_id": session_id,
        "total_entries": len(entries),
        "tool_invocations": 0,
        "llm_decisions": 0,
        "agent_switches": 0,
        "errors": 0,
        "tools_used": [],
        "agents_active": [],
        "first_entry": entries[0].get("timestamp"),
        "last_entry": entries[-1].get("timestamp"),
    }

    tools_seen = set()
    agents_seen = set()

    for entry in entries:
        t = entry.get("type")
        if t == "tool_invocation":
            summary["tool_invocations"] += 1
            tools_seen.add(entry.get("tool", "unknown"))
        elif t == "llm_decision":
            summary["llm_decisions"] += 1
            agents_seen.add(entry.get("agent_id", "unknown"))
        elif t == "agent_switch":
            summary["agent_switches"] += 1
            agents_seen.add(entry.get("to_agent", "unknown"))
        elif t == "error":
            summary["errors"] += 1

    summary["tools_used"] = sorted(tools_seen)
    summary["agents_active"] = sorted(agents_seen)
    return summary


def list_sessions() -> list:
    """List all session log files."""
    if not SESSION_LOG_DIR.exists():
        return []
    sessions = []
    for f in sorted(SESSION_LOG_DIR.glob("*.jsonl")):
        stat = f.stat()
        sessions.append({
            "session_id": f.stem,
            "size_bytes": stat.st_size,
            "modified": datetime.fromtimestamp(stat.st_mtime).isoformat()
        })
    return sessions


# --- CLI Interface ---

def main():
    import argparse
    parser = argparse.ArgumentParser(description="AgenticToolset Log Manager")
    parser.add_argument("--action", required=True,
                        choices=["log_tool", "log_decision", "log_agent_switch",
                                 "log_error", "log_event", "query", "summary",
                                 "list_sessions"],
                        help="Action to perform")
    parser.add_argument("--session_id", default=None, help="Session identifier")
    parser.add_argument("--data", default="{}", help="JSON data for the log entry")
    parser.add_argument("--type_filter", default=None, help="Filter logs by type")
    parser.add_argument("--last_n", type=int, default=50, help="Number of recent entries")

    args = parser.parse_args()
    data = json.loads(args.data)

    if args.action == "log_tool":
        result = log_tool_invocation(
            session_id=args.session_id or "unset",
            tool_name=data.get("tool", "unknown"),
            params=data.get("params", {}),
            result=data.get("result", {}),
            duration_ms=data.get("duration_ms")
        )
        print(json.dumps(result, indent=2))

    elif args.action == "log_decision":
        result = log_llm_decision(
            session_id=args.session_id or "unset",
            agent_id=data.get("agent", "unknown"),
            decision=data.get("decision", ""),
            reasoning=data.get("reasoning"),
            context=data.get("context")
        )
        print(json.dumps(result, indent=2))

    elif args.action == "log_agent_switch":
        result = log_agent_switch(
            session_id=args.session_id or "unset",
            from_agent=data.get("from", "none"),
            to_agent=data.get("to", "unknown"),
            reason=data.get("reason", "")
        )
        print(json.dumps(result, indent=2))

    elif args.action == "log_error":
        result = log_error(
            session_id=args.session_id or "unset",
            source=data.get("source", "unknown"),
            error=data.get("error", ""),
            traceback=data.get("traceback")
        )
        print(json.dumps(result, indent=2))

    elif args.action == "log_event":
        result = log_event(
            session_id=args.session_id or "unset",
            event_type=data.get("event_type", "generic"),
            data=data
        )
        print(json.dumps(result, indent=2))

    elif args.action == "query":
        entries = query_logs(
            session_id=args.session_id,
            log_type=args.type_filter,
            last_n=args.last_n
        )
        print(json.dumps(entries, indent=2))

    elif args.action == "summary":
        result = session_summary(args.session_id or "")
        print(json.dumps(result, indent=2))

    elif args.action == "list_sessions":
        result = list_sessions()
        print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
