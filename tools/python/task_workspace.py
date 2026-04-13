"""
Shared helpers for the canonical Overlord11 task workspace layout.

Task layout (naming: {ISO_DATE}_{JOB_ID}):
    workspace/{ISO_DATE}_{JOB_ID}/
      ProjectOverview.md    (auto-created at session start)
      Settings.md           (auto-created at session start)
      TaskingLog.md         (auto-created at session start)
      AInotes.md            (auto-created at session start)
      ErrorLog.md           (auto-created at session start)
      final_output.md       (written by agent on completion)
      output/               (main deliverables - app, code, report, etc)
      artifacts/
        agent/              (system profile, agent traces)
        tools/
          cache/            (tool result cache)
          web/              (web scraper downloads)
          vision/           (vision tool outputs)
        logs/
          agents/           (per-loop agent traces)
          tools/            (per-tool execution traces)
          system/           (system profile JSON)
          session.json      (session manifest)
          events.json       (all events array)
          timeline.jsonl    (trace index)
        app/                (code scaffold output)
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


def task_dir_for(session_id: str, job_id: str = "") -> Path:
    """
    Create task directory path with naming convention: {ISO_DATE}_{JOB_ID}
    Falls back to session_id if job_id not provided (for backward compatibility).
    """
    if job_id:
        # Extract ISO date from session_id (YYYYMMDD_HHMMSS format)
        iso_date = session_id.split("_")[0] if "_" in session_id else session_id[:8]
        task_name = f"{iso_date}_{job_id}"
    else:
        task_name = session_id
    return (WORKSPACE_ROOT / task_name).resolve()


def ensure_task_layout(task_dir: str | Path, include_app: bool = False) -> dict[str, Path]:
    root = Path(task_dir).resolve()
    artifacts = root / "artifacts"
    output = root / "output"
    paths = {
        "root": root,
        "output": output,
        "artifacts": artifacts,
        "agent": artifacts / "agent",
        "tools": artifacts / "tools",
        "tools_cache": artifacts / "tools" / "cache",
        "tools_web": artifacts / "tools" / "web",
        "tools_vision": artifacts / "tools" / "vision",
        "logs": artifacts / "logs",
        "logs_agents": artifacts / "logs" / "agents",
        "logs_tools": artifacts / "logs" / "tools",
        "logs_system": artifacts / "logs" / "system",
        "app": artifacts / "app",
    }
    for path in paths.values():
        path.mkdir(parents=True, exist_ok=True)
    return paths


def ensure_env_task_layout(include_app: bool = False) -> dict[str, Path] | None:
    task_dir = env_task_dir()
    if task_dir is None:
        return None
    return ensure_task_layout(task_dir, include_app=include_app)

