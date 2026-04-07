"""
Shared helpers for the canonical Overlord11 task workspace layout.

Task layout:
    workspace/<task_id>/
      agent/
      tools/
        cache/
        web/
        vision/
      logs/
        agents/
        tools/
        system/
      app/                  (created only for software-project scaffolds)
      <final deliverables>  (HTML reports, markdown reports, etc.)
"""

from __future__ import annotations

import os
import re
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
WORKSPACE_ROOT = PROJECT_ROOT / "workspace"

_SLUG_RE = re.compile(r"[^A-Za-z0-9._-]+")


def env_task_dir() -> Path | None:
    raw = os.environ.get("OVERLORD11_TASK_DIR", "").strip()
    if not raw:
        return None
    return Path(raw).resolve()


def slugify(value: str, default: str = "artifact") -> str:
    cleaned = _SLUG_RE.sub("_", (value or "").strip()).strip("._-")
    return cleaned or default


def task_dir_for(session_id: str) -> Path:
    return (WORKSPACE_ROOT / session_id).resolve()


def ensure_task_layout(task_dir: str | Path, include_app: bool = False) -> dict[str, Path]:
    root = Path(task_dir).resolve()
    paths = {
        "root": root,
        "agent": root / "agent",
        "tools": root / "tools",
        "tools_cache": root / "tools" / "cache",
        "tools_web": root / "tools" / "web",
        "tools_vision": root / "tools" / "vision",
        "logs": root / "logs",
        "logs_agents": root / "logs" / "agents",
        "logs_tools": root / "logs" / "tools",
        "logs_system": root / "logs" / "system",
        "app": root / "app",
    }
    for key, path in paths.items():
        if key == "app" and not include_app:
            continue
        path.mkdir(parents=True, exist_ok=True)
    return paths


def ensure_env_task_layout(include_app: bool = False) -> dict[str, Path] | None:
    task_dir = env_task_dir()
    if task_dir is None:
        return None
    return ensure_task_layout(task_dir, include_app=include_app)

