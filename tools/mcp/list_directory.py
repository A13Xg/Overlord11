from __future__ import annotations

import datetime as dt
from pathlib import Path

from ._common import fail, ok
from .app import mcp


@mcp.tool(
    name="list_directory",
    description="List files and directories and return entries in `data` with name, type, size, and modified timestamp. Use this to inspect paths before read/write/search operations.",
)
def list_directory(
    path: str,
    recursive: bool = False,
    include_hidden: bool = False,
    filter_ext: str = "",
) -> dict:
    """List directory contents.

    Args:
        path: Directory path to list.
        recursive: Whether to traverse nested subdirectories.
        include_hidden: Whether to include dot-prefixed files and directories.
        filter_ext: Optional extension filter such as '.py'; empty means all files.
    """
    try:
        root = Path(path)
        if not root.exists() or not root.is_dir():
            return fail(f"Directory not found at '{root}'.")
        entries = []
        iterator = root.rglob("*") if recursive else root.iterdir()
        for entry in iterator:
            if not include_hidden and entry.name.startswith("."):
                continue
            if filter_ext and entry.is_file() and entry.suffix != filter_ext:
                continue
            st = entry.stat()
            entries.append(
                {
                    "name": str(entry.relative_to(root)),
                    "type": "dir" if entry.is_dir() else "file",
                    "size_bytes": st.st_size,
                    "modified_iso": dt.datetime.fromtimestamp(
                        st.st_mtime, tz=dt.timezone.utc
                    ).isoformat(),
                }
            )
        return ok(entries)
    except Exception as exc:
        return fail(f"Failed to list directory '{path}': {exc}")

