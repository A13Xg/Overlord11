"""
Overlord11 - Consciousness Tool
================================
Provides structured read, search, and write access to the Consciousness.md
shared-memory file.  All agents with memory duties should use this tool
instead of reading/writing the file directly, so that the memory format
stays consistent across sessions.

Actions:
  read_all       - Return the entire Consciousness.md file.
  read_section   - Return a named section (e.g. "Cross-Agent Signals").
  search         - Full-text or keyword search returning matching entries.
  commit         - Append a properly-formatted memory entry.
  search_index   - Return a numbered index of all section headings.
  cleanup        - Remove entries marked [RESOLVED] or with expired TTLs.

Usage (CLI):
    python consciousness_tool.py --action read_all
    python consciousness_tool.py --action read_section --section "Cross-Agent Signals"
    python consciousness_tool.py --action search --query "API endpoint"
    python consciousness_tool.py --action search_index
    python consciousness_tool.py --action commit \
        --key "auth_endpoint" \
        --value "POST /api/v2/auth, requires Bearer header" \
        --priority HIGH --ttl 7d --category context
    python consciousness_tool.py --action cleanup
"""

import argparse
import json
import os
import re
import sys
import time
from datetime import datetime, timedelta
from pathlib import Path

# ---------------------------------------------------------------------------
# Path resolution — Consciousness.md lives at the project root
# ---------------------------------------------------------------------------
SCRIPT_DIR = Path(__file__).resolve().parent          # tools/python/
PROJECT_ROOT = SCRIPT_DIR.parent.parent               # project root
DEFAULT_CONSCIOUSNESS_FILE = PROJECT_ROOT / "Consciousness.md"

# Attempt to import log helpers; degrade gracefully if unavailable
try:
    sys.path.insert(0, str(SCRIPT_DIR))
    from log_manager import log_tool_invocation, log_error
    HAS_LOG = True
except ImportError:
    HAS_LOG = False
    def log_tool_invocation(*a, **kw): pass
    def log_error(*a, **kw): pass


# ---------------------------------------------------------------------------
# TTL helpers
# ---------------------------------------------------------------------------

def _parse_ttl(ttl_str: str) -> timedelta | None:
    """Parse a TTL string into a timedelta.  Returns None for 'persistent'."""
    ttl_str = (ttl_str or "7d").strip().lower()
    if ttl_str in ("persistent", "never", "∞"):
        return None
    match = re.match(r"^(\d+)(h|d|w)$", ttl_str)
    if not match:
        return timedelta(days=7)  # fallback
    val, unit = int(match.group(1)), match.group(2)
    if unit == "h":
        return timedelta(hours=val)
    if unit == "w":
        return timedelta(weeks=val)
    return timedelta(days=val)


def _is_expired(created_str: str, ttl_str: str) -> bool:
    """Return True if the entry has passed its TTL."""
    delta = _parse_ttl(ttl_str)
    if delta is None:
        return False
    try:
        created = datetime.fromisoformat(created_str)
        return datetime.now() > created + delta
    except (ValueError, TypeError):
        return False


# ---------------------------------------------------------------------------
# File I/O helpers
# ---------------------------------------------------------------------------

def _read_file(path: Path) -> str:
    """Read Consciousness.md; return empty string if missing."""
    if not path.exists():
        return ""
    return path.read_text(encoding="utf-8", errors="replace")


def _write_file(path: Path, content: str) -> None:
    """Write content to Consciousness.md; create parents if needed."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


# ---------------------------------------------------------------------------
# Actions
# ---------------------------------------------------------------------------

def read_all(file_path: Path = None) -> dict:
    """Return the entire Consciousness.md file."""
    path = file_path or DEFAULT_CONSCIOUSNESS_FILE
    content = _read_file(path)
    if not content:
        return {"status": "empty", "content": "", "char_count": 0}
    return {
        "status": "ok",
        "content": content,
        "char_count": len(content),
        "line_count": content.count("\n") + 1,
    }


def read_section(section_name: str, file_path: Path = None) -> dict:
    """Return the content of a named section heading.

    Matching is case-insensitive substring match on Markdown headings (##, ###).
    Returns all text from the matched heading until the next heading of equal
    or higher level.
    """
    path = file_path or DEFAULT_CONSCIOUSNESS_FILE
    content = _read_file(path)
    if not content:
        return {"status": "empty", "section": section_name, "content": ""}

    lines = content.splitlines()
    target = section_name.lower().strip()

    # Locate start line
    start_idx = None
    start_level = 0
    for i, line in enumerate(lines):
        m = re.match(r"^(#{1,6})\s+(.*)", line)
        if m and target in m.group(2).lower():
            start_idx = i
            start_level = len(m.group(1))
            break

    if start_idx is None:
        return {
            "status": "not_found",
            "section": section_name,
            "available_sections": _extract_section_headings(content),
        }

    # Collect until next heading of same or higher level
    section_lines = [lines[start_idx]]
    for line in lines[start_idx + 1:]:
        m = re.match(r"^(#{1,6})\s+", line)
        if m and len(m.group(1)) <= start_level:
            break
        section_lines.append(line)

    section_text = "\n".join(section_lines)
    return {
        "status": "ok",
        "section": section_name,
        "content": section_text,
        "line_count": len(section_lines),
    }


def search(query: str, file_path: Path = None, max_results: int = 20) -> dict:
    """Full-text keyword search returning matching paragraph blocks."""
    path = file_path or DEFAULT_CONSCIOUSNESS_FILE
    content = _read_file(path)
    if not content:
        return {"status": "empty", "query": query, "matches": []}

    query_lower = query.lower()
    # Split into paragraphs / entry blocks separated by blank lines
    blocks = re.split(r"\n{2,}", content)
    matches = []
    for idx, block in enumerate(blocks):
        if query_lower in block.lower():
            matches.append({
                "index": idx,
                "snippet": block[:500].strip(),
                "char_offset": content.lower().find(query_lower),
            })
            if len(matches) >= max_results:
                break

    return {
        "status": "ok",
        "query": query,
        "match_count": len(matches),
        "matches": matches,
    }


def search_index(file_path: Path = None) -> dict:
    """Return a numbered index of all section headings in the file."""
    path = file_path or DEFAULT_CONSCIOUSNESS_FILE
    content = _read_file(path)
    if not content:
        return {"status": "empty", "headings": []}

    headings = _extract_section_headings(content)
    return {
        "status": "ok",
        "heading_count": len(headings),
        "headings": headings,
    }


def _extract_section_headings(content: str) -> list:
    """Extract all Markdown headings with their level and index."""
    headings = []
    for i, line in enumerate(content.splitlines()):
        m = re.match(r"^(#{1,6})\s+(.*)", line)
        if m:
            headings.append({
                "index": len(headings),
                "line": i + 1,
                "level": len(m.group(1)),
                "heading": m.group(2).strip(),
            })
    return headings


def commit(
    key: str,
    value: str,
    priority: str = "NORMAL",
    ttl: str = "7d",
    category: str = "context",
    source: str = "AGENT",
    file_path: Path = None,
) -> dict:
    """Append a properly-formatted memory entry to Consciousness.md.

    The entry is appended inside the "Active Memory" section when it exists,
    otherwise at the end of the file.
    """
    path = file_path or DEFAULT_CONSCIOUSNESS_FILE
    content = _read_file(path)

    # Validate priority
    valid_priorities = {"CRITICAL", "HIGH", "NORMAL", "LOW", "PERSISTENT"}
    priority = priority.upper()
    if priority not in valid_priorities:
        priority = "NORMAL"

    # Validate category
    valid_categories = {"context", "finding", "decision", "error", "config", "wip", "handoff"}
    category = category.lower()
    if category not in valid_categories:
        category = "context"

    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M")
    entry = (
        f"\n### [{priority}] {key}\n"
        f"- **Source**: {source}\n"
        f"- **Created**: {timestamp}\n"
        f"- **TTL**: {ttl}\n"
        f"- **Status**: ACTIVE\n"
        f"- **Category**: {category}\n"
        f"- **Context**: {value}\n"
        f"- **Action**: Review and act on this entry as relevant to current task.\n"
    )

    # Try to insert inside the "Active Memory" section
    active_marker = "## Active Memory"
    if active_marker in content:
        # Find next top-level section after Active Memory
        after_active = content.split(active_marker, 1)[1]
        # Find next ## heading
        next_section = re.search(r"\n## ", after_active)
        if next_section:
            insert_pos = content.index(active_marker) + len(active_marker) + next_section.start()
            new_content = content[:insert_pos] + entry + "\n" + content[insert_pos:]
        else:
            new_content = content + entry
    else:
        new_content = content + entry

    _write_file(path, new_content)

    return {
        "status": "committed",
        "key": key,
        "priority": priority,
        "ttl": ttl,
        "category": category,
        "timestamp": timestamp,
        "file": str(path),
    }


def cleanup(file_path: Path = None, dry_run: bool = False) -> dict:
    """Remove entries marked [RESOLVED] or with expired TTLs.

    Parses each ### heading block, checks TTL and Status, and removes
    expired/resolved entries.  Archives them to an ## Archive section instead
    of deleting, preserving history.
    """
    path = file_path or DEFAULT_CONSCIOUSNESS_FILE
    content = _read_file(path)
    if not content:
        return {"status": "empty", "removed": 0, "archived": []}

    lines = content.splitlines(keepends=True)
    archived = []
    result_lines = []
    i = 0

    while i < len(lines):
        line = lines[i]
        m = re.match(r"^(###\s+\[([A-Z]+)\]\s+(.+))", line)
        if m:
            # Collect full block
            block = [line]
            j = i + 1
            while j < len(lines) and not re.match(r"^#{1,3}\s+", lines[j]):
                block.append(lines[j])
                j += 1

            block_text = "".join(block)
            # Extract status and created/TTL
            status_m = re.search(r"\*\*Status\*\*:\s*(\w+)", block_text)
            created_m = re.search(r"\*\*Created\*\*:\s*([^\n]+)", block_text)
            ttl_m = re.search(r"\*\*TTL\*\*:\s*([^\n]+)", block_text)

            status = (status_m.group(1) if status_m else "ACTIVE").strip()
            created_str = (created_m.group(1) if created_m else "").strip()
            ttl_str = (ttl_m.group(1) if ttl_m else "7d").strip()

            is_resolved = status.upper() in ("RESOLVED", "DONE", "CLOSED")
            is_expired = _is_expired(created_str, ttl_str)

            if is_resolved or is_expired:
                reason = "resolved" if is_resolved else "expired"
                archived.append({"heading": m.group(3), "reason": reason})
                if not dry_run:
                    # Don't add to result_lines — effectively removing it
                    pass
                i = j
                continue

            result_lines.extend(block)
            i = j
        else:
            result_lines.append(line)
            i += 1

    if not dry_run and archived:
        new_content = "".join(result_lines)
        # Append archived entries to Archive section
        archive_section = "\n## Archive\n\n"
        if "## Archive" not in new_content:
            new_content += archive_section
        _write_file(path, new_content)

    return {
        "status": "ok",
        "dry_run": dry_run,
        "archived_count": len(archived),
        "archived": archived,
    }


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="Overlord11 Consciousness Tool")
    parser.add_argument("--action", required=True,
                        choices=["read_all", "read_section", "search", "search_index",
                                 "commit", "cleanup"],
                        help="Action to perform on Consciousness.md")
    parser.add_argument("--section", default="", help="Section name for read_section")
    parser.add_argument("--query", default="", help="Search query for search action")
    parser.add_argument("--key", default="", help="Memory key for commit")
    parser.add_argument("--value", default="", help="Memory value/content for commit")
    parser.add_argument("--priority", default="NORMAL",
                        choices=["CRITICAL", "HIGH", "NORMAL", "LOW", "PERSISTENT"],
                        help="Entry priority level")
    parser.add_argument("--ttl", default="7d",
                        help="Time-to-live: 24h, 7d, 30d, persistent, etc.")
    parser.add_argument("--category", default="context",
                        choices=["context", "finding", "decision", "error",
                                 "config", "wip", "handoff"],
                        help="Memory category")
    parser.add_argument("--source", default="AGENT", help="Source agent ID")
    parser.add_argument("--max_results", type=int, default=20,
                        help="Max results for search")
    parser.add_argument("--dry_run", action="store_true",
                        help="Dry-run for cleanup (show what would be removed)")
    parser.add_argument("--file", default=None,
                        help="Path to Consciousness file (default: project root Consciousness.md)")

    args = parser.parse_args()
    file_path = Path(args.file) if args.file else None

    start = time.time()

    try:
        if args.action == "read_all":
            result = read_all(file_path)
        elif args.action == "read_section":
            if not args.section:
                result = {"error": "--section is required for read_section"}
            else:
                result = read_section(args.section, file_path)
        elif args.action == "search":
            if not args.query:
                result = {"error": "--query is required for search"}
            else:
                result = search(args.query, file_path, args.max_results)
        elif args.action == "search_index":
            result = search_index(file_path)
        elif args.action == "commit":
            if not args.key or not args.value:
                result = {"error": "--key and --value are required for commit"}
            else:
                result = commit(
                    key=args.key,
                    value=args.value,
                    priority=args.priority,
                    ttl=args.ttl,
                    category=args.category,
                    source=args.source,
                    file_path=file_path,
                )
        elif args.action == "cleanup":
            result = cleanup(file_path, dry_run=args.dry_run)
        else:
            result = {"error": f"Unknown action: {args.action}"}

    except Exception as exc:
        result = {"error": str(exc), "action": args.action}
        if HAS_LOG:
            log_error("system", "consciousness_tool", str(exc))

    duration_ms = (time.time() - start) * 1000

    if HAS_LOG:
        log_tool_invocation(
            session_id="system",
            tool_name="consciousness_tool",
            params={"action": args.action},
            result={"status": result.get("status", "error")},
            duration_ms=duration_ms,
        )

    print(json.dumps(result, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
