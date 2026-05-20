
import fnmatch
import re
from typing import Dict, Any
from pathlib import Path

from ._common import fail, ok
from .app import mcp


@mcp.tool(
    name="search_content",
    description="Search files under a directory for a regex or literal pattern and return match records in `data` with line and context. Prefer this over run_command grep for schema-stable match output.",
)
def search_content(
    directory: str,
    pattern: str,
    file_glob: str = "*",
    context_lines: int = 2,
    max_results: int = 50,
    case_sensitive: bool = True,
) -> Dict[str, Any]:
    """Search content in files.

    Args:
        directory: Root directory to search in.
        pattern: Regex or literal string to find.
        file_glob: Glob pattern for files to scan.
        context_lines: Number of surrounding lines to include.
        max_results: Maximum matches to return.
        case_sensitive: Whether matching is case-sensitive.
    """
    try:
        root = Path(directory)
        if not root.exists() or not root.is_dir():
            return fail(f"Directory '{root}' not found.")
        if context_lines < 0 or max_results < 1:
            return fail("context_lines must be >= 0 and max_results must be >= 1.")
        flags = 0 if case_sensitive else re.IGNORECASE
        try:
            rx = re.compile(pattern, flags)
        except re.error:
            rx = re.compile(re.escape(pattern), flags)
        results = []
        for file_path in root.rglob("*"):
            if not file_path.is_file() or not fnmatch.fnmatch(file_path.name, file_glob):
                continue
            lines = file_path.read_text(encoding="utf-8", errors="replace").splitlines()
            for idx, line in enumerate(lines):
                if rx.search(line):
                    start = max(0, idx - context_lines)
                    end = min(len(lines), idx + context_lines + 1)
                    results.append(
                        {
                            "file": str(file_path),
                            "line_number": idx + 1,
                            "line": line,
                            "context_before": lines[start:idx],
                            "context_after": lines[idx + 1 : end],
                        }
                    )
                    if len(results) >= max_results:
                        return ok(results)
        return ok(results)
    except Exception as exc:
        return fail(f"Search failed in '{directory}': {exc}")

