"""
Overlord11 - JSON Tool
=======================
Parse, validate, query, transform, and format JSON data.

Actions:
  parse      - Parse a JSON string into a structured object.
  validate   - Validate JSON syntax and optionally check against a schema.
  query      - Extract values using a dot-notation path (e.g., 'users.0.name').
  format     - Pretty-print or minify a JSON string.
  merge      - Deep-merge two JSON objects.
  diff       - Show differences between two JSON objects.
  keys       - List all keys at a given path (flat or recursive).
  set        - Set a value at a dot-notation path in a JSON object.
  delete     - Remove a key at a dot-notation path from a JSON object.

Usage (CLI):
    python json_tool.py --action parse --input '{"key": "value"}'
    python json_tool.py --action query --input '{"users": [{"name": "Alice"}]}' --path 'users.0.name'
    python json_tool.py --action format --input '{"a":1}' --indent 4
    python json_tool.py --action validate --input '{"a": 1}'
"""

import argparse
import json
import sys
from copy import deepcopy
from typing import Any, Optional


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _parse_path(path: str) -> list:
    """Split a dot-notation path into key/index segments.
    Supports:  users.0.name  →  ['users', 0, 'name']
    """
    if not path:
        return []
    parts = []
    for p in path.split("."):
        try:
            parts.append(int(p))
        except ValueError:
            parts.append(p)
    return parts


def _get_at(obj: Any, parts: list) -> Any:
    """Traverse obj following parts; raises KeyError/IndexError on miss."""
    current = obj
    for part in parts:
        if isinstance(current, dict):
            current = current[part]
        elif isinstance(current, list):
            current = current[int(part)]
        else:
            raise KeyError(f"Cannot traverse into {type(current).__name__} with key '{part}'")
    return current


def _set_at(obj: Any, parts: list, value: Any) -> Any:
    """Return a deep-copy of obj with value set at parts path."""
    obj = deepcopy(obj)
    if not parts:
        return value
    parent = _get_at(obj, parts[:-1])
    key = parts[-1]
    if isinstance(parent, dict):
        parent[key] = value
    elif isinstance(parent, list):
        parent[int(key)] = value
    else:
        raise KeyError(f"Cannot set key '{key}' on {type(parent).__name__}")
    return obj


def _delete_at(obj: Any, parts: list) -> Any:
    """Return a deep-copy of obj with the key at parts path removed."""
    obj = deepcopy(obj)
    parent = _get_at(obj, parts[:-1])
    key = parts[-1]
    if isinstance(parent, dict):
        del parent[key]
    elif isinstance(parent, list):
        del parent[int(key)]
    else:
        raise KeyError(f"Cannot delete key '{key}' from {type(parent).__name__}")
    return obj


def _deep_merge(base: dict, override: dict) -> dict:
    """Recursively merge override into base. Override wins on conflicts."""
    result = deepcopy(base)
    for k, v in override.items():
        if k in result and isinstance(result[k], dict) and isinstance(v, dict):
            result[k] = _deep_merge(result[k], v)
        else:
            result[k] = deepcopy(v)
    return result


def _collect_keys(obj: Any, prefix: str = "", recursive: bool = True) -> list:
    """Collect all key paths in an object."""
    keys = []
    if isinstance(obj, dict):
        for k, v in obj.items():
            full_key = f"{prefix}.{k}" if prefix else str(k)
            keys.append(full_key)
            if recursive:
                keys.extend(_collect_keys(v, full_key, recursive=True))
    elif isinstance(obj, list):
        for i, v in enumerate(obj):
            full_key = f"{prefix}.{i}" if prefix else str(i)
            keys.append(full_key)
            if recursive:
                keys.extend(_collect_keys(v, full_key, recursive=True))
    return keys


def _diff_objects(a: Any, b: Any, path: str = "") -> list:
    """Return a list of diff entries between two JSON-serializable objects."""
    diffs = []
    if type(a) != type(b):
        diffs.append({"path": path or "(root)", "type": "type_changed",
                      "from": type(a).__name__, "to": type(b).__name__,
                      "from_value": a, "to_value": b})
        return diffs

    if isinstance(a, dict):
        all_keys = set(a) | set(b)
        for k in sorted(all_keys):
            child_path = f"{path}.{k}" if path else str(k)
            if k not in a:
                diffs.append({"path": child_path, "type": "added", "value": b[k]})
            elif k not in b:
                diffs.append({"path": child_path, "type": "removed", "value": a[k]})
            else:
                diffs.extend(_diff_objects(a[k], b[k], child_path))
    elif isinstance(a, list):
        max_len = max(len(a), len(b))
        for i in range(max_len):
            child_path = f"{path}.{i}" if path else str(i)
            if i >= len(a):
                diffs.append({"path": child_path, "type": "added", "value": b[i]})
            elif i >= len(b):
                diffs.append({"path": child_path, "type": "removed", "value": a[i]})
            else:
                diffs.extend(_diff_objects(a[i], b[i], child_path))
    elif a != b:
        diffs.append({"path": path or "(root)", "type": "changed",
                      "from": a, "to": b})
    return diffs


# ---------------------------------------------------------------------------
# Public action functions
# ---------------------------------------------------------------------------

def json_tool(
    action: str,
    input: Optional[str] = None,
    input_b: Optional[str] = None,
    path: Optional[str] = None,
    value: Optional[str] = None,
    indent: int = 2,
    recursive: bool = True,
    file: Optional[str] = None,
    file_b: Optional[str] = None,
) -> dict:
    """
    Parse, validate, query, transform, and format JSON.

    Args:
        action:    One of: parse, validate, query, format, merge, diff, keys, set, delete.
        input:     JSON string to operate on. Alternative to file.
        input_b:   Second JSON string for merge/diff actions. Alternative to file_b.
        path:      Dot-notation key path for query/set/delete/keys actions (e.g., 'users.0.name').
        value:     JSON string value to set (for 'set' action).
        indent:    Indentation spaces for 'format' action. 0 = minify. Defaults to 2.
        recursive: For 'keys' action: include nested keys. Defaults to True.
        file:      Path to a JSON file (alternative to input).
        file_b:    Path to a second JSON file (alternative to input_b for merge/diff).

    Returns:
        dict with keys:
            status  – "success" or "error"
            action  – action performed
            result  – the output value (parsed object, formatted string, list of diffs, etc.)
            error   – error message (on failure)
            hint    – corrective action (on failure)
    """
    if action not in ("parse", "validate", "query", "format", "merge", "diff", "keys", "set", "delete"):
        return {
            "status": "error",
            "action": action,
            "error": f"Unknown action: '{action}'",
            "hint": "Use one of: parse, validate, query, format, merge, diff, keys, set, delete",
        }

    # Load primary input
    def _load_json_source(src: Optional[str], src_file: Optional[str], label: str):
        if src_file:
            try:
                from pathlib import Path
                content = Path(src_file).read_text(encoding="utf-8")
                return json.loads(content), None
            except FileNotFoundError:
                return None, f"{label} file not found: {src_file}"
            except json.JSONDecodeError as exc:
                return None, f"{label} file contains invalid JSON: {exc}"
            except OSError as exc:
                return None, f"Cannot read {label} file: {exc}"
        if src is None:
            return None, f"Either '{label}' string or '{label}_file' path is required"
        try:
            return json.loads(src), None
        except json.JSONDecodeError as exc:
            return None, f"Invalid JSON in {label}: {exc}"

    data, err = _load_json_source(input, file, "input")
    if err:
        return {"status": "error", "action": action, "error": err,
                "hint": "Provide valid JSON in the 'input' parameter or a path in 'file'."}

    # ── parse ──────────────────────────────────────────────────────────────
    if action == "parse":
        return {
            "status": "success",
            "action": "parse",
            "result": data,
            "type": type(data).__name__,
        }

    # ── validate ───────────────────────────────────────────────────────────
    if action == "validate":
        return {
            "status": "success",
            "action": "validate",
            "valid": True,
            "type": type(data).__name__,
            "result": "JSON is valid",
        }

    # ── format ─────────────────────────────────────────────────────────────
    if action == "format":
        ind = None if indent == 0 else int(indent)
        formatted = json.dumps(data, indent=ind, ensure_ascii=False)
        return {
            "status": "success",
            "action": "format",
            "result": formatted,
            "indent": indent,
            "minified": indent == 0,
        }

    # ── query ──────────────────────────────────────────────────────────────
    if action == "query":
        if not path:
            return {
                "status": "error",
                "action": "query",
                "error": "The 'path' parameter is required for the query action",
                "hint": "Provide a dot-notation path, e.g., 'users.0.name'",
            }
        try:
            parts = _parse_path(path)
            found = _get_at(data, parts)
            return {
                "status": "success",
                "action": "query",
                "path": path,
                "result": found,
                "type": type(found).__name__,
            }
        except (KeyError, IndexError, TypeError) as exc:
            return {
                "status": "error",
                "action": "query",
                "path": path,
                "error": f"Path not found: {exc}",
                "hint": "Use the 'keys' action to list available paths in the document.",
            }

    # ── keys ───────────────────────────────────────────────────────────────
    if action == "keys":
        root = data
        if path:
            try:
                root = _get_at(data, _parse_path(path))
            except (KeyError, IndexError, TypeError) as exc:
                return {
                    "status": "error",
                    "action": "keys",
                    "path": path,
                    "error": f"Path not found: {exc}",
                    "hint": "Check the path spelling with the query action first.",
                }
        keys_list = _collect_keys(root, recursive=recursive)
        return {
            "status": "success",
            "action": "keys",
            "path": path or "(root)",
            "recursive": recursive,
            "count": len(keys_list),
            "result": keys_list,
        }

    # ── set ────────────────────────────────────────────────────────────────
    if action == "set":
        if not path:
            return {
                "status": "error",
                "action": "set",
                "error": "The 'path' parameter is required for the set action",
                "hint": "Provide a dot-notation path, e.g., 'users.0.name'",
            }
        if value is None:
            return {
                "status": "error",
                "action": "set",
                "error": "The 'value' parameter is required for the set action",
                "hint": "Provide a JSON value string, e.g., '\"Alice\"' or '42'",
            }
        try:
            parsed_value = json.loads(value)
        except json.JSONDecodeError as exc:
            return {
                "status": "error",
                "action": "set",
                "error": f"'value' is not valid JSON: {exc}",
                "hint": "Provide value as a JSON string: e.g., '\"text\"', '42', 'true', '[1,2]'",
            }
        try:
            updated = _set_at(data, _parse_path(path), parsed_value)
            return {
                "status": "success",
                "action": "set",
                "path": path,
                "value": parsed_value,
                "result": updated,
            }
        except (KeyError, IndexError, TypeError) as exc:
            return {
                "status": "error",
                "action": "set",
                "path": path,
                "error": f"Cannot set at path: {exc}",
                "hint": "Check the path exists using the query or keys action.",
            }

    # ── delete ─────────────────────────────────────────────────────────────
    if action == "delete":
        if not path:
            return {
                "status": "error",
                "action": "delete",
                "error": "The 'path' parameter is required for the delete action",
                "hint": "Provide a dot-notation path, e.g., 'users.0'",
            }
        try:
            updated = _delete_at(data, _parse_path(path))
            return {
                "status": "success",
                "action": "delete",
                "path": path,
                "result": updated,
            }
        except (KeyError, IndexError, TypeError) as exc:
            return {
                "status": "error",
                "action": "delete",
                "path": path,
                "error": f"Cannot delete at path: {exc}",
                "hint": "Verify the path exists using the keys action.",
            }

    # ── merge / diff: need second input ────────────────────────────────────
    data_b, err_b = _load_json_source(input_b, file_b, "input_b")
    if err_b:
        return {
            "status": "error",
            "action": action,
            "error": err_b,
            "hint": "Provide the second JSON value in 'input_b' or 'file_b'.",
        }

    if action == "merge":
        if not isinstance(data, dict) or not isinstance(data_b, dict):
            return {
                "status": "error",
                "action": "merge",
                "error": "Both inputs must be JSON objects (dicts) for merge",
                "hint": "Use inputs that are JSON objects: {...}",
            }
        merged = _deep_merge(data, data_b)
        return {
            "status": "success",
            "action": "merge",
            "result": merged,
            "keys_in_base": len(data),
            "keys_in_override": len(data_b),
            "keys_in_result": len(merged),
        }

    if action == "diff":
        diffs = _diff_objects(data, data_b)
        return {
            "status": "success",
            "action": "diff",
            "identical": len(diffs) == 0,
            "diff_count": len(diffs),
            "result": diffs,
        }

    # Should not reach here
    return {"status": "error", "action": action, "error": "Internal error"}


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="Overlord11 JSON Tool")
    parser.add_argument("--action", required=True,
                        choices=["parse", "validate", "query", "format", "merge",
                                 "diff", "keys", "set", "delete"])
    parser.add_argument("--input", default=None, help="JSON string input")
    parser.add_argument("--input_b", default=None, help="Second JSON string (for merge/diff)")
    parser.add_argument("--path", default=None, help="Dot-notation path (e.g., users.0.name)")
    parser.add_argument("--value", default=None, help="JSON value string (for set action)")
    parser.add_argument("--indent", type=int, default=2, help="Indentation for format (0=minify)")
    parser.add_argument("--no_recursive", action="store_true", help="Shallow keys only")
    parser.add_argument("--file", default=None, help="Path to JSON file (alternative to --input)")
    parser.add_argument("--file_b", default=None, help="Path to second JSON file")

    args = parser.parse_args()
    result = json_tool(
        action=args.action,
        input=args.input,
        input_b=args.input_b,
        path=args.path,
        value=args.value,
        indent=args.indent,
        recursive=not args.no_recursive,
        file=args.file,
        file_b=args.file_b,
    )
    print(json.dumps(result, indent=2, ensure_ascii=False, default=str))
    sys.exit(0 if result.get("status") == "success" else 1)


if __name__ == "__main__":
    main()
