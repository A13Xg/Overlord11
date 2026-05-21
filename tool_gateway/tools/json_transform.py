"""
JSON Transform tool — parse, query (dot-notation path), and transform JSON data.
Input can be a JSON string or a URL to fetch JSON from.
"""
from __future__ import annotations

import json
import re
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from .base import BaseTool
from .web_fetch import WebFetchTool, WebFetchArgs


class JsonTransformInput(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=False)

    data: str = Field(..., min_length=1, description="JSON string to transform, or a URL starting with http/https to fetch JSON from")
    query: str | None = Field(None, description="Dot-notation path to extract a sub-value, e.g. 'items.0.title' or 'meta.count'")
    transform: Literal["pretty", "minify", "flatten", "keys", "values", "summary"] = Field(
        "pretty",
        description=(
            "pretty — indent with 2 spaces | "
            "minify — compact single-line | "
            "flatten — collapse nested keys into dot-notation dict | "
            "keys — list all top-level keys | "
            "values — list all top-level values | "
            "summary — type and size metadata for each top-level key"
        ),
    )
    max_depth: int = Field(10, ge=1, le=50, description="Maximum depth for flatten operation")


class JsonTransformTool(BaseTool):
    name = "json_transform"
    description = (
        "Parse, query, and transform JSON data. "
        "Supports pretty-printing, minifying, flattening nested structures to dot-notation, "
        "key/value extraction, and structural summaries. "
        "Input can be a raw JSON string or a URL pointing to a JSON API endpoint."
    )
    risk_level = "low"
    destructive = False
    supports_dry_run = False
    input_model = JsonTransformInput
    examples = [
        {"tool_name": "json_transform", "arguments": {"data": '{"name":"Alice","age":30}', "transform": "pretty"}},
        {"tool_name": "json_transform", "arguments": {"data": '{"a":{"b":{"c":1}}}', "transform": "flatten"}},
        {"tool_name": "json_transform", "arguments": {"data": "https://api.github.com/repos/python/cpython", "query": "stargazers_count", "transform": "pretty"}},
    ]

    def execute(self, args: JsonTransformInput) -> dict[str, Any]:
        warnings: list[str] = []
        raw = args.data.strip()

        # Fetch from URL if applicable
        if re.match(r"https?://", raw, re.IGNORECASE):
            fetch = WebFetchTool().execute(WebFetchArgs(url=raw))
            body = fetch.get("body", "")
            if not body:
                raise ValueError(f"URL returned empty body: {raw}")
            raw = str(body)
            warnings.append(f"Fetched JSON from URL: {raw[:80]}")

        # Parse JSON
        try:
            parsed = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise ValueError(f"Invalid JSON: {exc}") from exc

        original_size = len(raw.encode("utf-8"))

        # Apply query (dot-notation path)
        if args.query:
            parsed, query_warning = self._apply_query(parsed, args.query)
            if query_warning:
                warnings.append(query_warning)

        # Apply transform
        result, result_type = self._apply_transform(parsed, args.transform, args.max_depth)
        result_size = len(result.encode("utf-8")) if isinstance(result, str) else None

        # Count top-level keys
        key_count: int | None = None
        if isinstance(parsed, dict):
            key_count = len(parsed)
        elif isinstance(parsed, list):
            key_count = len(parsed)

        return {
            "original_size_bytes": original_size,
            "result": result,
            "result_type": result_type,
            "key_count": key_count,
            "result_size_bytes": result_size,
            "query_applied": args.query,
            "transform_applied": args.transform,
            "_warnings": warnings,
        }

    # ------------------------------------------------------------------

    def _apply_query(self, data: Any, path: str) -> tuple[Any, str | None]:
        """Traverse dot-notation path; return (value, warning_or_None)."""
        parts = path.split(".")
        current = data
        for part in parts:
            if part == "":
                continue
            if isinstance(current, dict):
                if part not in current:
                    return None, f"Key '{part}' not found in object (path: {path})"
                current = current[part]
            elif isinstance(current, list):
                try:
                    idx = int(part)
                except ValueError:
                    return None, f"Cannot index list with non-integer key '{part}' (path: {path})"
                if idx < 0 or idx >= len(current):
                    return None, f"Index {idx} out of range for list of length {len(current)} (path: {path})"
                current = current[idx]
            else:
                return None, f"Cannot traverse into {type(current).__name__} at '{part}' (path: {path})"
        return current, None

    def _apply_transform(self, data: Any, transform: str, max_depth: int) -> tuple[Any, str]:
        if transform == "pretty":
            return json.dumps(data, indent=2, ensure_ascii=False, default=str), "json"
        if transform == "minify":
            return json.dumps(data, separators=(",", ":"), ensure_ascii=False, default=str), "json"
        if transform == "flatten":
            flat = {}
            self._flatten(data, "", flat, max_depth, 0)
            return json.dumps(flat, indent=2, ensure_ascii=False, default=str), "flattened-json"
        if transform == "keys":
            if isinstance(data, dict):
                return json.dumps(list(data.keys()), indent=2), "json-array"
            if isinstance(data, list):
                return json.dumps(list(range(len(data))), indent=2), "json-array"
            return json.dumps([]), "json-array"
        if transform == "values":
            if isinstance(data, dict):
                vals = [json.dumps(v, default=str) if not isinstance(v, (str, int, float, bool)) else v for v in data.values()]
                return json.dumps(vals, indent=2, default=str), "json-array"
            if isinstance(data, list):
                return json.dumps(data, indent=2, default=str), "json-array"
            return json.dumps([data], indent=2, default=str), "json-array"
        if transform == "summary":
            return json.dumps(self._summarize(data), indent=2, default=str), "summary"
        return json.dumps(data, indent=2, ensure_ascii=False, default=str), "json"

    def _flatten(self, obj: Any, prefix: str, result: dict, max_depth: int, depth: int) -> None:
        if depth > max_depth:
            result[prefix] = "...(max depth reached)"
            return
        if isinstance(obj, dict):
            for k, v in obj.items():
                key = f"{prefix}.{k}" if prefix else k
                self._flatten(v, key, result, max_depth, depth + 1)
        elif isinstance(obj, list):
            for i, v in enumerate(obj):
                key = f"{prefix}.{i}" if prefix else str(i)
                self._flatten(v, key, result, max_depth, depth + 1)
        else:
            result[prefix] = obj

    def _summarize(self, data: Any) -> Any:
        if isinstance(data, dict):
            return {
                k: {"type": type(v).__name__, "length": len(v) if isinstance(v, (str, list, dict)) else None}
                for k, v in data.items()
            }
        if isinstance(data, list):
            return {"type": "array", "length": len(data), "item_types": list({type(v).__name__ for v in data})}
        return {"type": type(data).__name__, "value": data}
