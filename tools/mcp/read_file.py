from __future__ import annotations

from pathlib import Path

from ._common import fail, ok
from .app import mcp


@mcp.tool(
    name="read_file",
    description="Read a file at the given path and return its text contents in `data` as a string. Use this instead of run_command when you only need safe deterministic file reads.",
)
def read_file(
    path: str,
    encoding: str = "utf-8",
    start_line: int = 1,
    end_line: int = -1,
) -> dict:
    """Read text from a file with optional 1-indexed line slicing.

    Args:
        path: Absolute or relative path to the file to read.
        encoding: File encoding used to decode bytes.
        start_line: First line to return (1-indexed).
        end_line: Last line to return (1-indexed), or -1 for end-of-file.
    """
    try:
        if start_line < 1:
            return fail("start_line must be >= 1.")
        if end_line != -1 and end_line < start_line:
            return fail("end_line must be -1 or greater than or equal to start_line.")
        p = Path(path)
        if not p.exists() or not p.is_file():
            return fail(f"File not found at '{p}'. Check the path with list_directory first.")
        lines = p.read_text(encoding=encoding).splitlines(keepends=True)
        start_idx = start_line - 1
        end_idx = None if end_line == -1 else end_line
        return ok("".join(lines[start_idx:end_idx]))
    except Exception as exc:
        return fail(f"Failed to read file '{path}': {exc}")

