"""
Overlord11 - Env Tool
======================
Read, write, and validate .env files. Manage environment variables for projects
without requiring shell access. Safely handles comments, blank lines, quoted values,
and multiline strings.

Actions:
  read     – Load a .env file and return all key-value pairs.
  write    – Write or update key-value pairs in a .env file.
  delete   – Remove a key from a .env file.
  validate – Check that required keys are present (and optionally non-empty).
  get      – Get the value of a single key from a .env file.
  list     – List all keys in a .env file (without values, for safety).

Usage (CLI):
    python env_tool.py --action read --file .env
    python env_tool.py --action write --file .env --key DATABASE_URL --value "postgres://..."
    python env_tool.py --action validate --file .env --required DATABASE_URL,SECRET_KEY
    python env_tool.py --action delete --file .env --key OLD_KEY
"""

import argparse
import json
import os
import re
import sys
from pathlib import Path
from typing import Dict, List, Optional


# ---------------------------------------------------------------------------
# .env parser / serializer
# ---------------------------------------------------------------------------

def _parse_env_file(content: str) -> Dict[str, str]:
    """Parse .env file content into a dict. Handles comments, quotes, and exports."""
    result = {}
    for line in content.splitlines():
        stripped = line.strip()
        # Skip blank lines and comments
        if not stripped or stripped.startswith("#"):
            continue
        # Strip optional 'export ' prefix
        if stripped.startswith("export "):
            stripped = stripped[7:].lstrip()
        # Split on first '='
        if "=" not in stripped:
            continue
        key, _, value = stripped.partition("=")
        key = key.strip()
        value = value.strip()
        # Unquote: double quotes
        if len(value) >= 2 and value[0] == '"' and value[-1] == '"':
            value = value[1:-1].replace('\\"', '"').replace("\\n", "\n").replace("\\t", "\t")
        # Unquote: single quotes
        elif len(value) >= 2 and value[0] == "'" and value[-1] == "'":
            value = value[1:-1]
        # Strip inline comment (only for unquoted values)
        else:
            comment_pos = value.find(" #")
            if comment_pos != -1:
                value = value[:comment_pos].rstrip()
        if key:
            result[key] = value
    return result


def _serialize_env_file(current_content: str, updates: Dict[str, str],
                         deletions: Optional[List[str]] = None) -> str:
    """Merge updates and deletions into existing .env content, preserving comments and order."""
    deletions = set(deletions or [])
    lines = current_content.splitlines(keepends=True)
    updated_keys = set()
    new_lines = []

    for line in lines:
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            new_lines.append(line)
            continue
        bare = stripped[7:].lstrip() if stripped.startswith("export ") else stripped
        if "=" not in bare:
            new_lines.append(line)
            continue
        key = bare.partition("=")[0].strip()
        if key in deletions:
            continue  # Remove this key
        if key in updates:
            new_lines.append(_format_kv(key, updates[key]))
            updated_keys.add(key)
        else:
            new_lines.append(line)

    # Append new keys that weren't already in the file
    for key, value in updates.items():
        if key not in updated_keys:
            new_lines.append(_format_kv(key, value))

    content = "".join(new_lines)
    if content and not content.endswith("\n"):
        content += "\n"
    return content


def _format_kv(key: str, value: str) -> str:
    """Format a key=value line, quoting if value contains spaces or special chars."""
    if not value or re.search(r'[\s#\'"\\]', value):
        escaped = value.replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n").replace("\t", "\\t")
        return f'{key}="{escaped}"\n'
    return f"{key}={value}\n"


# ---------------------------------------------------------------------------
# Core function
# ---------------------------------------------------------------------------

def env_tool(
    action: str,
    file: str = ".env",
    key: Optional[str] = None,
    value: Optional[str] = None,
    pairs: Optional[Dict[str, str]] = None,
    required: Optional[List[str]] = None,
    allow_empty: bool = False,
    create: bool = True,
) -> dict:
    """
    Read, write, and validate .env files.

    Args:
        action:      Operation: read, write, delete, validate, get, list.
        file:        Path to the .env file. Defaults to '.env'.
        key:         Key name for get/write/delete actions.
        value:       Value string for write action.
        pairs:       Dict of key→value pairs for bulk write.
        required:    List of required key names for validate action.
        allow_empty: Whether empty string counts as present for validate. Default False.
        create:      Create the .env file if it doesn't exist (write action). Default True.

    Returns:
        dict with keys:
            status   – "success" or "error"
            action   – action performed
            file     – resolved file path
            data     – key-value dict (read/get)
            keys     – list of key names (list)
            missing  – list of missing required keys (validate)
            valid    – bool, all required keys present (validate)
            error    – error message (on failure)
            hint     – corrective action (on failure)
    """
    if action not in ("read", "write", "delete", "validate", "get", "list"):
        return {
            "status": "error",
            "action": action,
            "error": f"Unknown action: '{action}'",
            "hint": "Use one of: read, write, delete, validate, get, list",
        }

    env_path = Path(file)

    def _load_content() -> tuple:
        if not env_path.exists():
            if create and action == "write":
                return "", {}
            return None, None
        try:
            content = env_path.read_text(encoding="utf-8")
            return content, _parse_env_file(content)
        except OSError as exc:
            return None, {"_error": str(exc)}

    # ── read ───────────────────────────────────────────────────────────────
    if action == "read":
        content, parsed = _load_content()
        if content is None and parsed is None:
            return {
                "status": "error",
                "action": action,
                "file": str(env_path),
                "error": f".env file not found: {file}",
                "hint": "Create the file or use the write action to create it.",
            }
        if "_error" in (parsed or {}):
            return {
                "status": "error",
                "action": action,
                "file": str(env_path),
                "error": f"Cannot read file: {parsed['_error']}",
                "hint": "Check file permissions.",
            }
        return {
            "status": "success",
            "action": "read",
            "file": str(env_path.resolve()),
            "key_count": len(parsed),
            "data": parsed,
        }

    # ── list ───────────────────────────────────────────────────────────────
    if action == "list":
        content, parsed = _load_content()
        if content is None and parsed is None:
            return {
                "status": "error",
                "action": action,
                "file": str(env_path),
                "error": f".env file not found: {file}",
                "hint": "Create the file first.",
            }
        return {
            "status": "success",
            "action": "list",
            "file": str(env_path.resolve()),
            "key_count": len(parsed or {}),
            "keys": list((parsed or {}).keys()),
        }

    # ── get ────────────────────────────────────────────────────────────────
    if action == "get":
        if not key:
            return {
                "status": "error",
                "action": action,
                "error": "The 'key' parameter is required for get",
                "hint": "Provide the environment variable name in 'key'.",
            }
        content, parsed = _load_content()
        if content is None and parsed is None:
            return {
                "status": "error",
                "action": action,
                "file": str(env_path),
                "error": f".env file not found: {file}",
                "hint": "Use the read action to inspect the file.",
            }
        if key not in (parsed or {}):
            return {
                "status": "error",
                "action": action,
                "file": str(env_path.resolve()),
                "key": key,
                "error": f"Key not found: '{key}'",
                "hint": "Use the list action to see available keys.",
            }
        return {
            "status": "success",
            "action": "get",
            "file": str(env_path.resolve()),
            "key": key,
            "value": parsed[key],
        }

    # ── validate ───────────────────────────────────────────────────────────
    if action == "validate":
        if not required:
            return {
                "status": "error",
                "action": action,
                "error": "The 'required' parameter is required for validate",
                "hint": "Provide a list of required key names.",
            }
        content, parsed = _load_content()
        parsed = parsed or {}
        missing = []
        empty = []
        for req_key in required:
            if req_key not in parsed:
                missing.append(req_key)
            elif not allow_empty and not parsed[req_key]:
                empty.append(req_key)
        all_valid = not missing and not empty
        return {
            "status": "success",
            "action": "validate",
            "file": str(env_path.resolve()),
            "valid": all_valid,
            "required": required,
            "missing": missing,
            "empty": empty,
            "verdict": "PASS" if all_valid else "FAIL",
        }

    # ── write ──────────────────────────────────────────────────────────────
    if action == "write":
        updates = dict(pairs or {})
        if key is not None:
            if value is None:
                return {
                    "status": "error",
                    "action": action,
                    "error": "The 'value' parameter is required when 'key' is provided",
                    "hint": "Provide both 'key' and 'value', or use 'pairs' for bulk writes.",
                }
            updates[key] = value
        if not updates:
            return {
                "status": "error",
                "action": action,
                "error": "Nothing to write — provide 'key'+'value' or 'pairs'",
                "hint": "Provide key-value pairs to write.",
            }
        content, _ = _load_content()
        if content is None:
            content = ""
        new_content = _serialize_env_file(content, updates)
        try:
            env_path.parent.mkdir(parents=True, exist_ok=True)
            env_path.write_text(new_content, encoding="utf-8")
        except OSError as exc:
            return {
                "status": "error",
                "action": action,
                "file": str(env_path),
                "error": f"Cannot write file: {exc}",
                "hint": "Check directory write permissions.",
            }
        return {
            "status": "success",
            "action": "write",
            "file": str(env_path.resolve()),
            "written_keys": list(updates.keys()),
            "key_count": len(updates),
        }

    # ── delete ─────────────────────────────────────────────────────────────
    if action == "delete":
        keys_to_delete = []
        if key:
            keys_to_delete = [key]
        if not keys_to_delete:
            return {
                "status": "error",
                "action": action,
                "error": "The 'key' parameter is required for delete",
                "hint": "Provide the key name to delete in 'key'.",
            }
        content, parsed = _load_content()
        if content is None and parsed is None:
            return {
                "status": "error",
                "action": action,
                "file": str(env_path),
                "error": f".env file not found: {file}",
                "hint": "Nothing to delete.",
            }
        not_found = [k for k in keys_to_delete if k not in (parsed or {})]
        new_content = _serialize_env_file(content or "", {}, deletions=keys_to_delete)
        try:
            env_path.write_text(new_content, encoding="utf-8")
        except OSError as exc:
            return {
                "status": "error",
                "action": action,
                "file": str(env_path),
                "error": f"Cannot write file: {exc}",
                "hint": "Check file permissions.",
            }
        return {
            "status": "success",
            "action": "delete",
            "file": str(env_path.resolve()),
            "deleted": [k for k in keys_to_delete if k not in not_found],
            "not_found": not_found,
        }

    return {"status": "error", "action": action, "error": "Internal error"}


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="Overlord11 Env Tool")
    parser.add_argument("--action", required=True,
                        choices=["read", "write", "delete", "validate", "get", "list"])
    parser.add_argument("--file", default=".env", help=".env file path")
    parser.add_argument("--key", default=None, help="Key name")
    parser.add_argument("--value", default=None, help="Value for write action")
    parser.add_argument("--pairs", default=None, help="JSON object of key-value pairs for write")
    parser.add_argument("--required", nargs="+", default=None, help="Required keys for validate")
    parser.add_argument("--allow_empty", action="store_true")
    parser.add_argument("--no_create", action="store_true", help="Don't create file if missing")

    args = parser.parse_args()
    pairs = None
    if args.pairs:
        try:
            pairs = json.loads(args.pairs)
        except json.JSONDecodeError as exc:
            print(json.dumps({"status": "error", "error": f"Invalid JSON for --pairs: {exc}"}))
            sys.exit(1)

    result = env_tool(
        action=args.action,
        file=args.file,
        key=args.key,
        value=args.value,
        pairs=pairs,
        required=args.required,
        allow_empty=args.allow_empty,
        create=not args.no_create,
    )
    print(json.dumps(result, indent=2, ensure_ascii=False))
    sys.exit(0 if result.get("status") == "success" else 1)


if __name__ == "__main__":
    main()
