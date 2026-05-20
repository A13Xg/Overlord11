
from pathlib import Path
from typing import Literal, Dict, Any

from ._common import fail, ok
from .app import mcp


@mcp.tool(
    name="write_file",
    description="Write text content to a file and return write metadata in `data` (`path`, `bytes_written`, `lines_written`). Use this over run_command for predictable file writes with explicit modes.",
)
def write_file(
    path: str,
    content: str,
    mode: Literal["overwrite", "append", "create_only"] = "overwrite",
    encoding: str = "utf-8",
    make_dirs: bool = True,
) -> Dict[str, Any]:
    """Write full text content to a file.

    Args:
        path: Absolute or relative file path to write.
        content: Full text content to write.
        mode: Write mode: overwrite, append, or create_only.
        encoding: File encoding used to encode text.
        make_dirs: Whether to create missing parent directories.
    """
    try:
        p = Path(path)
        if make_dirs:
            p.parent.mkdir(parents=True, exist_ok=True)
        elif not p.parent.exists():
            return fail(f"Parent directory '{p.parent}' does not exist. Set make_dirs=true.")
        if mode == "create_only" and p.exists():
            return fail(f"File '{p}' already exists. Use mode='overwrite' or mode='append'.")
        file_mode = "a" if mode == "append" else "w"
        with p.open(file_mode, encoding=encoding) as handle:
            handle.write(content)
        return ok(
            {
                "path": str(p),
                "bytes_written": len(content.encode(encoding)),
                "lines_written": len(content.splitlines()),
            }
        )
    except Exception as exc:
        return fail(f"Failed to write file '{path}': {exc}")

