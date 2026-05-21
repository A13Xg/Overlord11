from pathlib import Path
from typing import Any, Dict

from ._common import fail, ok
from .app import mcp


@mcp.tool(
    name="write_markdown_summary",
    description="Write a clean markdown summary file for downstream agents. Returns write metadata in `data`.",
)
def write_markdown_summary(
    filename: str,
    markdown: str,
    title: str = "",
    make_dirs: bool = True,
    encoding: str = "utf-8",
) -> Dict[str, Any]:
    """Write markdown content with optional title preface."""
    try:
        p = Path(filename)
        if p.suffix.lower() not in {".md", ".markdown"}:
            return fail("filename must end with .md or .markdown")
        if make_dirs:
            p.parent.mkdir(parents=True, exist_ok=True)
        elif not p.parent.exists():
            return fail(f"Parent directory '{p.parent}' does not exist. Set make_dirs=true.")
        content = markdown
        if title.strip():
            content = f"# {title.strip()}\n\n{markdown}"
        p.write_text(content, encoding=encoding)
        return ok(
            {
                "path": str(p),
                "bytes_written": len(content.encode(encoding)),
                "lines_written": len(content.splitlines()),
                "kind": "markdown_summary",
            }
        )
    except Exception as exc:
        return fail(f"Failed to write markdown summary '{filename}': {exc}")
