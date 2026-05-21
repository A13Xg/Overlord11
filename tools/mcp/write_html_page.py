from pathlib import Path
from typing import Any, Dict

from ._common import fail, ok
from .app import mcp


@mcp.tool(
    name="write_html_page",
    description="Write a complete HTML page to a .html/.htm file and return write metadata in `data`. Use this specialized tool for webpage deliverables.",
)
def write_html_page(
    filename: str,
    html: str,
    make_dirs: bool = True,
    encoding: str = "utf-8",
) -> Dict[str, Any]:
    """Write HTML content to a file with extension validation."""
    try:
        p = Path(filename)
        if p.suffix.lower() not in {".html", ".htm"}:
            return fail("filename must end with .html or .htm")
        if make_dirs:
            p.parent.mkdir(parents=True, exist_ok=True)
        elif not p.parent.exists():
            return fail(f"Parent directory '{p.parent}' does not exist. Set make_dirs=true.")
        p.write_text(html, encoding=encoding)
        return ok(
            {
                "path": str(p),
                "bytes_written": len(html.encode(encoding)),
                "lines_written": len(html.splitlines()),
                "kind": "html_page",
            }
        )
    except Exception as exc:
        return fail(f"Failed to write HTML page '{filename}': {exc}")
