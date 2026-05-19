from __future__ import annotations

import csv
import io
import json
from typing import Any, Literal

import tomli_w
import tomllib
import yaml

from ._common import fail, ok
from .app import mcp


def _parse(content: str, fmt: str) -> Any:
    if fmt == "json":
        return json.loads(content)
    if fmt == "yaml":
        return yaml.safe_load(content)
    if fmt == "toml":
        return tomllib.loads(content)
    if fmt == "csv":
        return list(csv.DictReader(io.StringIO(content)))
    if fmt == "markdown":
        return {"markdown": content}
    raise ValueError(f"Unsupported format: {fmt}")


def _dump(value: Any, fmt: str, indent: int) -> str:
    if fmt == "json":
        return json.dumps(value, indent=indent, ensure_ascii=False)
    if fmt == "yaml":
        return yaml.safe_dump(value, indent=indent, sort_keys=False)
    if fmt == "toml":
        if not isinstance(value, dict):
            raise ValueError("TOML output requires object-like input.")
        return tomli_w.dumps(value)
    if fmt == "csv":
        if not isinstance(value, list) or (value and not isinstance(value[0], dict)):
            raise ValueError("CSV output requires a list of objects.")
        out = io.StringIO()
        fieldnames = list(value[0].keys()) if value else []
        writer = csv.DictWriter(out, fieldnames=fieldnames)
        if fieldnames:
            writer.writeheader()
            writer.writerows(value)
        return out.getvalue()
    if fmt == "markdown":
        if isinstance(value, dict) and "markdown" in value:
            return str(value["markdown"])
        return "```json\n" + json.dumps(value, indent=indent, ensure_ascii=False) + "\n```"
    raise ValueError(f"Unsupported format: {fmt}")


@mcp.tool(
    name="convert_format",
    description="Convert content between json/yaml/toml/csv/markdown and return the converted text in `data`. Use this when an agent needs deterministic format translation.",
)
def convert_format(
    content: str,
    from_format: Literal["json", "yaml", "toml", "csv", "markdown"],
    to_format: Literal["json", "yaml", "toml", "csv", "markdown"],
    indent: int = 2,
) -> dict:
    """Convert serialized text from one format to another.

    Args:
        content: Input serialized content.
        from_format: Source format.
        to_format: Target format.
        indent: Indentation size for pretty JSON/YAML output.
    """
    try:
        if indent < 0:
            return fail("indent must be >= 0.")
        parsed = _parse(content, from_format)
        return ok(_dump(parsed, to_format, indent))
    except Exception as exc:
        return fail(f"Format conversion failed ({from_format} -> {to_format}): {exc}")

