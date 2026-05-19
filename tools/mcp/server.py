from __future__ import annotations

from tools.mcp.app import mcp

# Import all tool modules so decorators register with the shared FastMCP instance.
from tools.mcp import compute_hash  # noqa: F401
from tools.mcp import convert_format  # noqa: F401
from tools.mcp import diff_content  # noqa: F401
from tools.mcp import execute_python  # noqa: F401
from tools.mcp import fetch_url  # noqa: F401
from tools.mcp import get_datetime  # noqa: F401
from tools.mcp import git_operation  # noqa: F401
from tools.mcp import list_directory  # noqa: F401
from tools.mcp import query_json  # noqa: F401
from tools.mcp import read_file  # noqa: F401
from tools.mcp import regex_operation  # noqa: F401
from tools.mcp import replace_in_file  # noqa: F401
from tools.mcp import run_command  # noqa: F401
from tools.mcp import search_content  # noqa: F401
from tools.mcp import store_memory  # noqa: F401
from tools.mcp import write_file  # noqa: F401


if __name__ == "__main__":
    mcp.run()

