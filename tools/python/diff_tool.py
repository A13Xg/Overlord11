"""
Overlord11 - Diff Tool
=======================
Compare two strings or files and produce human-readable unified diffs or
structured line-by-line comparison results. Useful for reviewing changes,
auditing edits, and verifying that rewrites preserved intended content.

Actions:
  diff_strings  – Compare two string values.
  diff_files    – Compare two files line by line.
  patch_apply   – Apply a unified diff patch to a string or file.

Usage (CLI):
    python diff_tool.py --action diff_strings --a "Hello World" --b "Hello Claude"
    python diff_tool.py --action diff_files --file_a old.py --file_b new.py
    python diff_tool.py --action diff_files --file_a original.txt --file_b modified.txt --context 5
"""

import argparse
import difflib
import json
import sys
from pathlib import Path
from typing import Optional


def diff_tool(
    action: str,
    a: Optional[str] = None,
    b: Optional[str] = None,
    file_a: Optional[str] = None,
    file_b: Optional[str] = None,
    context: int = 3,
    output_format: str = "unified",
    encoding: str = "utf-8",
) -> dict:
    """
    Compare strings or files and produce diffs.

    Args:
        action:        Operation: diff_strings, diff_files, patch_apply.
        a:             First string (for diff_strings or patch_apply source).
        b:             Second string (for diff_strings) or patch content (for patch_apply).
        file_a:        First file path (for diff_files).
        file_b:        Second file path (for diff_files).
        context:       Lines of context around each change. Defaults to 3.
        output_format: 'unified' (default) or 'side_by_side' (structured list).
        encoding:      File encoding. Defaults to utf-8.

    Returns:
        dict with keys:
            status          – "success" or "error"
            action          – action performed
            identical       – bool, no differences found
            diff            – unified diff string or structured list (output_format='side_by_side')
            added_lines     – count of added lines
            removed_lines   – count of removed lines
            changed_blocks  – count of distinct change hunks
            error           – error message (on failure)
            hint            – corrective action (on failure)
    """
    if action not in ("diff_strings", "diff_files", "patch_apply"):
        return {
            "status": "error",
            "action": action,
            "error": f"Unknown action: '{action}'",
            "hint": "Use one of: diff_strings, diff_files, patch_apply",
        }

    # ── diff_strings ───────────────────────────────────────────────────────
    if action == "diff_strings":
        if a is None or b is None:
            return {
                "status": "error",
                "action": action,
                "error": "Both 'a' and 'b' parameters are required for diff_strings",
                "hint": "Provide both strings to compare.",
            }
        lines_a = a.splitlines(keepends=True)
        lines_b = b.splitlines(keepends=True)
        return _compute_diff(lines_a, lines_b, label_a="string_a", label_b="string_b",
                             context=context, output_format=output_format, action=action)

    # ── diff_files ─────────────────────────────────────────────────────────
    if action == "diff_files":
        if not file_a or not file_b:
            return {
                "status": "error",
                "action": action,
                "error": "Both 'file_a' and 'file_b' are required for diff_files",
                "hint": "Provide paths to both files to compare.",
            }
        pa, pb = Path(file_a), Path(file_b)
        for label, p in (("file_a", pa), ("file_b", pb)):
            if not p.exists():
                return {
                    "status": "error",
                    "action": action,
                    "error": f"File not found ({label}): {p}",
                    "hint": "Check the file path with list_directory or glob_tool.",
                }
        try:
            content_a = pa.read_text(encoding=encoding, errors="replace").splitlines(keepends=True)
            content_b = pb.read_text(encoding=encoding, errors="replace").splitlines(keepends=True)
        except OSError as exc:
            return {
                "status": "error",
                "action": action,
                "error": f"Cannot read file: {exc}",
                "hint": "Check file permissions.",
            }
        return _compute_diff(content_a, content_b, label_a=file_a, label_b=file_b,
                             context=context, output_format=output_format, action=action)

    # ── patch_apply ────────────────────────────────────────────────────────
    if action == "patch_apply":
        if a is None or b is None:
            return {
                "status": "error",
                "action": action,
                "error": "Both 'a' (source text) and 'b' (unified diff patch) are required",
                "hint": "Provide the original text in 'a' and the unified diff in 'b'.",
            }
        try:
            result = _apply_patch(a, b)
            return {
                "status": "success",
                "action": "patch_apply",
                "result": result,
            }
        except Exception as exc:
            return {
                "status": "error",
                "action": action,
                "error": f"Patch application failed: {exc}",
                "hint": "Ensure the patch was generated from the same source text.",
            }

    return {"status": "error", "action": action, "error": "Internal error"}


def _compute_diff(lines_a, lines_b, label_a, label_b, context, output_format, action):
    """Compute the diff and return a result dict."""
    added = 0
    removed = 0

    if output_format == "side_by_side":
        opcodes = difflib.SequenceMatcher(None, lines_a, lines_b).get_opcodes()
        side_by_side = []
        for tag, i1, i2, j1, j2 in opcodes:
            block = {
                "operation": tag,
                "a_lines": [l.rstrip("\n") for l in lines_a[i1:i2]],
                "b_lines": [l.rstrip("\n") for l in lines_b[j1:j2]],
                "a_range": [i1 + 1, i2],
                "b_range": [j1 + 1, j2],
            }
            if tag in ("replace", "delete"):
                removed += len(lines_a[i1:i2])
            if tag in ("replace", "insert"):
                added += len(lines_b[j1:j2])
            if tag != "equal":
                side_by_side.append(block)
        return {
            "status": "success",
            "action": action,
            "label_a": label_a,
            "label_b": label_b,
            "output_format": "side_by_side",
            "identical": not side_by_side,
            "added_lines": added,
            "removed_lines": removed,
            "changed_blocks": len(side_by_side),
            "diff": side_by_side,
        }

    # unified diff
    unified = list(difflib.unified_diff(
        lines_a, lines_b,
        fromfile=label_a, tofile=label_b,
        n=context,
    ))
    for line in unified:
        if line.startswith("+") and not line.startswith("+++"):
            added += 1
        elif line.startswith("-") and not line.startswith("---"):
            removed += 1

    # Count hunks
    hunks = sum(1 for l in unified if l.startswith("@@"))

    return {
        "status": "success",
        "action": action,
        "label_a": label_a,
        "label_b": label_b,
        "output_format": "unified",
        "identical": not unified,
        "added_lines": added,
        "removed_lines": removed,
        "changed_blocks": hunks,
        "diff": "".join(unified) if unified else "(no differences)",
    }


def _apply_patch(source: str, patch: str) -> str:
    """
    Apply a unified diff patch to source text.
    Basic implementation supporting standard unified diff format.
    """
    import re as _re

    source_lines = source.splitlines(keepends=True)
    result_lines = list(source_lines)
    patch_lines = patch.splitlines(keepends=True)

    # Parse hunks
    hunk_header = _re.compile(r"^@@ -(\d+)(?:,(\d+))? \+(\d+)(?:,(\d+))? @@")
    i = 0
    offset = 0
    while i < len(patch_lines):
        m = hunk_header.match(patch_lines[i])
        if m:
            src_start = int(m.group(1)) - 1  # 0-based
            hunk_lines = []
            i += 1
            while i < len(patch_lines) and not hunk_header.match(patch_lines[i]):
                if not patch_lines[i].startswith(("---", "+++")):
                    hunk_lines.append(patch_lines[i])
                i += 1
            # Apply hunk
            pos = src_start + offset
            removes = [l[1:] for l in hunk_lines if l.startswith("-")]
            adds = [l[1:] for l in hunk_lines if l.startswith("+")]
            del result_lines[pos:pos + len(removes)]
            result_lines[pos:pos] = adds
            offset += len(adds) - len(removes)
        else:
            i += 1

    return "".join(result_lines)


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="Overlord11 Diff Tool")
    parser.add_argument("--action", required=True,
                        choices=["diff_strings", "diff_files", "patch_apply"])
    parser.add_argument("--a", default=None, help="First string or source text")
    parser.add_argument("--b", default=None, help="Second string or patch content")
    parser.add_argument("--file_a", default=None, help="First file path")
    parser.add_argument("--file_b", default=None, help="Second file path")
    parser.add_argument("--context", type=int, default=3, help="Lines of context")
    parser.add_argument("--output_format", default="unified",
                        choices=["unified", "side_by_side"])
    parser.add_argument("--encoding", default="utf-8")

    args = parser.parse_args()
    result = diff_tool(
        action=args.action,
        a=args.a,
        b=args.b,
        file_a=args.file_a,
        file_b=args.file_b,
        context=args.context,
        output_format=args.output_format,
        encoding=args.encoding,
    )
    print(json.dumps(result, indent=2, ensure_ascii=False))
    sys.exit(0 if result.get("status") == "success" else 1)


if __name__ == "__main__":
    main()
