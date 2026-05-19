from __future__ import annotations

from pathlib import Path

from ._common import fail, ok
from .app import mcp


@mcp.tool(
    name="replace_in_file",
    description="Replace literal text in a file and return replacement count plus preview in `data`. Use this for deterministic non-regex edits.",
)
def replace_in_file(
    path: str,
    old_text: str,
    new_text: str,
    replace_all: bool = False,
) -> dict:
    """Replace literal text in a file.

    Args:
        path: Path to the file to modify.
        old_text: Exact text to find.
        new_text: Replacement text.
        replace_all: Whether to replace all occurrences.
    """
    try:
        if old_text == "":
            return fail("old_text cannot be empty.")
        p = Path(path)
        if not p.exists() or not p.is_file():
            return fail(f"File not found at '{p}'.")
        content = p.read_text(encoding="utf-8")
        total = content.count(old_text)
        if total == 0:
            return ok({"replacements_made": 0, "preview": content[:500]})
        if replace_all:
            result = content.replace(old_text, new_text)
            made = total
        else:
            result = content.replace(old_text, new_text, 1)
            made = 1
        p.write_text(result, encoding="utf-8")
        return ok({"replacements_made": made, "preview": result[:500]})
    except Exception as exc:
        return fail(f"Failed to replace text in '{path}': {exc}")

