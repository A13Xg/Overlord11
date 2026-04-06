"""
session_clean — Overlord11 session reset tool.

Purges workspace session folders and clears Consciousness.md active entries
while preserving Memory.md (permanent preferences/rules) and logs/ (audit trail).

Usage:
    python tools/python/session_clean.py --action clean
    python tools/python/session_clean.py --action status
    python tools/python/session_clean.py --action purge_workspace --older_than_days 7 --archive true
    python tools/python/session_clean.py --action reset_consciousness --dry_run true
"""

import argparse
import io
import json
import re
import shutil
import sys
from datetime import datetime, timezone, timedelta
from pathlib import Path

_BASE_DIR = Path(__file__).resolve().parent.parent.parent
_WORKSPACE_DIR = _BASE_DIR / "workspace"
_CONSCIOUSNESS_FILE = _BASE_DIR / "Consciousness.md"
_MEMORY_FILE = _BASE_DIR / "Memory.md"
_LOGS_DIR = _BASE_DIR / "logs"

# Sections in Consciousness.md that contain ephemeral entries (cleared on reset)
_EPHEMERAL_SECTIONS = [
    "Cross-Agent Signals",
    "Work In Progress",
    "Pending Handoffs",
    "Error States",
]

# Sections preserved during reset (permanent config and context)
_PRESERVED_SECTIONS = [
    "Shared Context",
    "Agent Registry",
    "Communication Protocols",
    "Archive",
    "Anti-Bloat Measures",
    "Quick Reference",
    "Memory Management Rules",
    "Purpose",
    "Overlord11 Integration",
]

# Session folder pattern: YYYYMMDD_HHMMSS
_SESSION_DIR_RE = re.compile(r"^\d{8}_\d{6}$")


def _is_session_dir(path: Path) -> bool:
    return path.is_dir() and _SESSION_DIR_RE.match(path.name) is not None


def _session_age_days(session_dir: Path) -> float:
    """Return age in days based on directory modification time."""
    mtime = session_dir.stat().st_mtime
    age = datetime.now(timezone.utc) - datetime.fromtimestamp(mtime, tz=timezone.utc)
    return age.total_seconds() / 86400


def _list_workspace_sessions(older_than_days: int = 0) -> list[Path]:
    """Return list of session directories to purge."""
    if not _WORKSPACE_DIR.exists():
        return []
    sessions = []
    for entry in _WORKSPACE_DIR.iterdir():
        if entry.name == "archive":
            continue
        if _is_session_dir(entry):
            if older_than_days == 0 or _session_age_days(entry) > older_than_days:
                sessions.append(entry)
    return sorted(sessions)


def _purge_workspace(sessions: list[Path], archive: bool, dry_run: bool) -> dict:
    """Remove or archive workspace session directories."""
    removed = []
    archived = []
    errors = []

    archive_dir = _WORKSPACE_DIR / "archive"

    for session_dir in sessions:
        try:
            if dry_run:
                if archive:
                    archived.append(str(session_dir))
                else:
                    removed.append(str(session_dir))
                continue

            if archive:
                archive_dir.mkdir(parents=True, exist_ok=True)
                dest = archive_dir / session_dir.name
                shutil.move(str(session_dir), str(dest))
                archived.append(str(session_dir))
            else:
                shutil.rmtree(session_dir)
                removed.append(str(session_dir))
        except Exception as exc:
            errors.append({"path": str(session_dir), "error": str(exc)})

    return {"removed": removed, "archived": archived, "errors": errors}


def _reset_consciousness(dry_run: bool) -> dict:
    """Clear active entries from ephemeral sections of Consciousness.md."""
    if not _CONSCIOUSNESS_FILE.exists():
        return {"status": "skipped", "reason": "Consciousness.md not found"}

    content = _CONSCIOUSNESS_FILE.read_text(encoding="utf-8")
    original_len = len(content.splitlines())

    # For each ephemeral section, replace its content with a cleared placeholder
    # We detect sections by H3 heading and replace until the next H2/H3/HR
    cleared_sections = []

    for section_name in _EPHEMERAL_SECTIONS:
        # Pattern: the section heading followed by its content block
        pattern = re.compile(
            r"(### " + re.escape(section_name) + r"\n)"   # heading
            r"(.*?)"                                       # content (lazy)
            r"(?=\n---|\n##|\Z)",                          # until hr, h2, or EOF
            re.DOTALL,
        )

        def _replace_section(m: re.Match) -> str:
            heading = m.group(1)
            old_content = m.group(2)
            # Check if there are any non-comment, non-empty, non-placeholder lines
            real_entries = [
                ln for ln in old_content.splitlines()
                if ln.strip() and not ln.strip().startswith("<!--") and ln.strip() != "_No active signals._"
                and not ln.strip().startswith("_No ")
            ]
            if real_entries:
                cleared_sections.append(section_name)
            # Replace with empty placeholder, preserve comment examples
            # Find the comment block (<!-- ... -->) and keep it
            comment_match = re.search(r"(<!-- Example:.*?-->)", old_content, re.DOTALL)
            placeholder = f"\n_No active entries._\n\n"
            if comment_match:
                placeholder = f"\n_No active entries._\n\n{comment_match.group(1)}\n"
            return heading + placeholder

        new_content, count = pattern.subn(_replace_section, content)
        if count:
            content = new_content

    new_len = len(content.splitlines())

    if not dry_run and cleared_sections:
        _CONSCIOUSNESS_FILE.write_text(content, encoding="utf-8")

    return {
        "status": "dry_run" if dry_run else "cleared",
        "sections_cleared": cleared_sections,
        "lines_before": original_len,
        "lines_after": new_len,
    }


def _get_status() -> dict:
    """Report current state without making changes."""
    sessions = _list_workspace_sessions(older_than_days=0)
    total_size = 0
    for s in sessions:
        for f in s.rglob("*"):
            if f.is_file():
                total_size += f.stat().st_size

    consciousness_status = "not found"
    active_entry_count = 0
    if _CONSCIOUSNESS_FILE.exists():
        text = _CONSCIOUSNESS_FILE.read_text(encoding="utf-8")
        # Count non-placeholder, non-comment H3 entries in ephemeral sections
        for section in _EPHEMERAL_SECTIONS:
            sec_match = re.search(
                r"### " + re.escape(section) + r"\n(.*?)(?=\n---|\n##|\Z)",
                text,
                re.DOTALL,
            )
            if sec_match:
                block = sec_match.group(1)
                entries = [ln for ln in block.splitlines()
                           if ln.startswith("### [") and not ln.startswith("<!-- ")]
                active_entry_count += len(entries)
        consciousness_status = f"{active_entry_count} active entries"

    logs_size = 0
    log_files = 0
    if _LOGS_DIR.exists():
        for f in _LOGS_DIR.rglob("*"):
            if f.is_file():
                logs_size += f.stat().st_size
                log_files += 1

    return {
        "workspace_sessions": len(sessions),
        "workspace_size_bytes": total_size,
        "workspace_size_mb": round(total_size / 1024 / 1024, 2),
        "consciousness_active_entries": active_entry_count,
        "consciousness_status": consciousness_status,
        "memory_file_exists": _MEMORY_FILE.exists(),
        "logs_files": log_files,
        "logs_size_bytes": logs_size,
        "logs_preserved": True,
        "memory_preserved": True,
    }


def _log_to_master(session_id: str, result: dict) -> None:
    """Append a log entry to logs/master.jsonl."""
    try:
        _LOGS_DIR.mkdir(parents=True, exist_ok=True)
        log_file = _LOGS_DIR / "master.jsonl"
        entry = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "session_id": session_id or "manual",
            "agent_id": "TOOL",
            "tool": "session_clean",
            "result": result,
        }
        with open(log_file, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")
    except Exception:
        pass


def main(
    action: str = "clean",
    archive: bool = False,
    older_than_days: int = 0,
    dry_run: bool = False,
    session_id: str = "",
) -> dict:
    # Normalize bool args that may arrive as strings from CLI
    if isinstance(archive, str):
        archive = archive.lower() in ("true", "1", "yes")
    if isinstance(dry_run, str):
        dry_run = dry_run.lower() in ("true", "1", "yes")
    if isinstance(older_than_days, str):
        older_than_days = int(older_than_days)

    result: dict = {"action": action, "dry_run": dry_run}

    if action == "status":
        result.update(_get_status())

    elif action == "purge_workspace":
        sessions = _list_workspace_sessions(older_than_days=older_than_days)
        result["sessions_found"] = len(sessions)
        result.update(_purge_workspace(sessions, archive=archive, dry_run=dry_run))

    elif action == "reset_consciousness":
        result.update(_reset_consciousness(dry_run=dry_run))

    elif action == "clean":
        # Full clean: purge workspace + reset consciousness
        sessions = _list_workspace_sessions(older_than_days=older_than_days)
        result["sessions_found"] = len(sessions)
        workspace_result = _purge_workspace(sessions, archive=archive, dry_run=dry_run)
        consciousness_result = _reset_consciousness(dry_run=dry_run)
        result["workspace"] = workspace_result
        result["consciousness"] = consciousness_result
        result["preserved"] = ["Memory.md", "logs/"]

    else:
        result["error"] = f"Unknown action: {action}"

    if session_id and not dry_run:
        _log_to_master(session_id, result)

    return result


if __name__ == "__main__":
    if sys.platform == "win32":
        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
        sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")
    parser = argparse.ArgumentParser(description="Overlord11 session cleanup tool")
    parser.add_argument("--action", default="clean",
                        choices=["clean", "purge_workspace", "reset_consciousness", "status"])
    parser.add_argument("--archive", default="false")
    parser.add_argument("--older_than_days", type=int, default=0)
    parser.add_argument("--dry_run", default="false")
    parser.add_argument("--session_id", default="")
    args = parser.parse_args()

    output = main(
        action=args.action,
        archive=args.archive,
        older_than_days=args.older_than_days,
        dry_run=args.dry_run,
        session_id=args.session_id,
    )
    print(json.dumps(output, indent=2, ensure_ascii=False))
