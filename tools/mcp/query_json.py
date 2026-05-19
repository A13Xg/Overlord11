from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, Literal

from ._common import fail, ok
from .app import mcp


def _query_path(obj: Any, json_path: str) -> Any:
    if json_path == "":
        return obj
    tokens = re.finditer(r"([^.\\[\\]]+)|\\[(\\d+)\\]", json_path)
    current = obj
    for token in tokens:
        key = token.group(1)
        index = token.group(2)
        if key is not None:
            current = current[key]
        else:
            current = current[int(index)]
    return current


@mcp.tool(
    name="query_json",
    description="Query JSON input by dot/bracket path and return the selected value in `data`. Use this for structured extraction instead of ad-hoc string parsing.",
)
def query_json(
    input: str,
    json_path: str,
    output_format: Literal["value", "pretty", "compact"] = "value",
) -> dict:
    """Query a value from JSON string or .json file.

    Args:
        input: JSON string or file path ending in .json.
        json_path: Dot/bracket path such as users[0].name; empty returns whole object.
        output_format: Output style for returned data.
    """
    try:
        candidate = Path(input)
        source = (
            candidate.read_text(encoding="utf-8")
            if candidate.suffix == ".json" and candidate.exists() and candidate.is_file()
            else input
        )
        parsed = json.loads(source)
        value = _query_path(parsed, json_path)
        if output_format == "value":
            return ok(value)
        if output_format == "pretty":
            return ok(json.dumps(value, indent=2, ensure_ascii=False))
        return ok(json.dumps(value, separators=(",", ":"), ensure_ascii=False))
    except Exception as exc:
        return fail(f"JSON query failed: {exc}. Verify valid JSON and json_path syntax.")

