from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from .base import BaseTool


class WriteFileArgs(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    path: str = Field(min_length=1)
    content: str = ""
    overwrite: bool = True


class WriteFileTool(BaseTool):
    name = "write_file"
    description = "Write UTF-8 text content to a file under workspace root"
    risk_level = "medium"
    destructive = True
    supports_dry_run = False
    timeout_behavior = "not_applicable"
    examples = [
        {"path": "answer.md", "content": "# Report\n\nDone."},
        {"path": "output/answer.md", "content": "Result text", "overwrite": True},
    ]
    input_model = WriteFileArgs

    def execute(self, args: WriteFileArgs) -> dict[str, Any]:
        workspace_root = Path(self._resolve_workspace_root()).resolve()
        target = self._resolve_target_path(args.path, workspace_root)
        target.parent.mkdir(parents=True, exist_ok=True)

        if target.exists() and not args.overwrite:
            raise ValueError("Target file already exists and overwrite is false")

        target.write_text(args.content, encoding="utf-8")
        return {
            "path": str(target),
            "workspace_root": str(workspace_root),
            "bytes_written": len(args.content.encode("utf-8")),
            "overwrite": args.overwrite,
        }

    def _resolve_workspace_root(self) -> str:
        base = os.environ.get("OVERLORD11_TASK_DIR") or os.getcwd()
        return str(Path(base).resolve())

    def _resolve_target_path(self, raw_path: str, workspace_root: Path) -> Path:
        p = Path(raw_path)
        resolved = (workspace_root / p).resolve() if not p.is_absolute() else p.resolve()
        try:
            resolved.relative_to(workspace_root)
        except ValueError as exc:
            raise ValueError("write_file path must resolve within workspace root") from exc
        return resolved

