"""
Read File tool — read a file from the job workspace and return its contents.
Companion to write_file. Enforces workspace-root containment.
"""
from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from .base import BaseTool
from .web_common import make_metadata


class ReadFileArgs(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    path: str = Field(min_length=1, description="Path to the file (relative to workspace root)")
    encoding: str = Field("utf-8", description="Text encoding (default utf-8)")
    max_bytes: int = Field(
        1_048_576,
        ge=1,
        le=10_485_760,
        description="Maximum bytes to read (default 1 MiB, max 10 MiB)",
    )
    include_line_count: bool = Field(True, description="Include line count in metadata")


class ReadFileTool(BaseTool):
    name = "read_file"
    description = (
        "Read a file from the job workspace and return its text content. "
        "Enforces workspace containment — cannot read outside the job directory."
    )
    risk_level = "low"
    destructive = False
    supports_dry_run = False
    timeout_behavior = "not_applicable"
    examples = [
        {"tool_name": "read_file", "arguments": {"path": "final_output.md"}},
        {"tool_name": "read_file", "arguments": {"path": "data/results.json", "max_bytes": 65536}},
    ]
    input_model = ReadFileArgs

    def execute(self, args: ReadFileArgs) -> dict[str, Any]:
        workspace_root = Path(os.environ.get("OVERLORD11_TASK_DIR") or os.getcwd()).resolve()
        p = Path(args.path)
        target = (workspace_root / p).resolve() if not p.is_absolute() else p.resolve()

        try:
            target.relative_to(workspace_root)
        except ValueError as exc:
            raise ValueError("read_file path must resolve within workspace root") from exc

        if not target.exists():
            raise FileNotFoundError(f"File not found: {args.path}")
        if not target.is_file():
            raise ValueError(f"Path is not a file: {args.path}")

        size_bytes = target.stat().st_size
        truncated = size_bytes > args.max_bytes

        raw = target.read_bytes()[:args.max_bytes]
        try:
            content = raw.decode(args.encoding, errors="replace")
        except (LookupError, UnicodeDecodeError):
            content = raw.decode("utf-8", errors="replace")

        line_count = content.count("\n") + 1 if args.include_line_count else None

        return {
            "path": str(target.relative_to(workspace_root)),
            "content": content,
            "size_bytes": size_bytes,
            "bytes_read": len(raw),
            "truncated": truncated,
            "line_count": line_count,
            "_warnings": ["File was truncated to max_bytes limit"] if truncated else [],
            "_metadata": make_metadata(
                partial_success=truncated,
                fallbacks_used=[],
                inferred_values={},
                extra={"encoding": args.encoding},
            ),
        }
