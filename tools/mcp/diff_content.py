from __future__ import annotations

import difflib
from pathlib import Path
from typing import Literal

from ._common import fail, ok
from .app import mcp


def _read_or_raw(value: str) -> str:
    p = Path(value)
    if p.exists() and p.is_file():
        return p.read_text(encoding="utf-8")
    return value


@mcp.tool(
    name="diff_content",
    description="Diff two content strings (or file paths) and return diff text and change counts in `data`. Prefer this over shell diff for predictable output fields.",
)
def diff_content(
    content_a: str,
    content_b: str,
    label_a: str = "a",
    label_b: str = "b",
    output_format: Literal["unified", "context", "ndiff"] = "unified",
) -> dict:
    """Compare two text inputs.

    Args:
        content_a: First content string or file path.
        content_b: Second content string or file path.
        label_a: Label for the first source.
        label_b: Label for the second source.
        output_format: Diff output style.
    """
    try:
        a = _read_or_raw(content_a).splitlines()
        b = _read_or_raw(content_b).splitlines()
        if output_format == "unified":
            lines = list(difflib.unified_diff(a, b, fromfile=label_a, tofile=label_b, lineterm=""))
        elif output_format == "context":
            lines = list(difflib.context_diff(a, b, fromfile=label_a, tofile=label_b, lineterm=""))
        else:
            lines = list(difflib.ndiff(a, b))
        added = sum(1 for x in lines if x.startswith("+") and not x.startswith("+++"))
        removed = sum(1 for x in lines if x.startswith("-") and not x.startswith("---"))
        return ok(
            {
                "diff": "\n".join(lines),
                "lines_added": added,
                "lines_removed": removed,
                "is_identical": a == b,
            }
        )
    except Exception as exc:
        return fail(f"Diff generation failed: {exc}")

