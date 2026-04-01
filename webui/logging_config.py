"""Structured JSON-line logging for Overlord11 WebUI and Agent subsystems.

Two separate log streams:
  logs/webui.jsonl  — WebUI HTTP activity, provider health, config changes.
  logs/agents.jsonl — Agent orchestration, tool calls, job execution events.

Each line is a JSON object parseable by an AI for diagnostics.
"""
from __future__ import annotations

import json
import logging
import logging.handlers
import time
from pathlib import Path

LOG_DIR = Path(__file__).resolve().parent.parent / "logs"


class JSONLineFormatter(logging.Formatter):
    """Emit each log record as a single UTF-8 JSON line."""

    # Fields that live on every LogRecord but are not interesting extra context.
    _SKIP = frozenset({
        "args", "asctime", "created", "exc_info", "exc_text", "filename",
        "funcName", "id", "levelname", "levelno", "lineno", "message",
        "module", "msecs", "msg", "name", "pathname", "process",
        "processName", "relativeCreated", "stack_info", "thread",
        "threadName", "taskName",
    })

    def format(self, record: logging.LogRecord) -> str:
        obj: dict = {
            "ts": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(record.created)),
            "ms": int(record.msecs),
            "level": record.levelname,
            "logger": record.name,
            "msg": record.getMessage(),
        }
        if record.exc_info:
            obj["exc"] = self.formatException(record.exc_info)
        if record.stack_info:
            obj["stack"] = self.formatStack(record.stack_info)
        # Attach any extra fields passed via Logger.info(..., extra={...})
        for key, val in record.__dict__.items():
            if key not in self._SKIP and not key.startswith("_"):
                obj[key] = val
        return json.dumps(obj, ensure_ascii=False, default=str)


def _build_logger(name: str, filename: str, level: int = logging.DEBUG) -> logging.Logger:
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    logger = logging.getLogger(name)
    if logger.handlers:
        return logger  # already configured; avoid duplicate handlers
    logger.setLevel(level)
    logger.propagate = False

    # Rotating file: 5 MB per file, keep 10 rotations
    fh = logging.handlers.RotatingFileHandler(
        LOG_DIR / filename,
        maxBytes=5 * 1024 * 1024,
        backupCount=10,
        encoding="utf-8",
    )
    fh.setFormatter(JSONLineFormatter())
    fh.setLevel(logging.DEBUG)
    logger.addHandler(fh)

    # Console: INFO+ only, human-readable
    sh = logging.StreamHandler()
    sh.setFormatter(logging.Formatter(
        "%(asctime)s [%(name)-8s] %(levelname)-8s %(message)s",
        datefmt="%H:%M:%S",
    ))
    sh.setLevel(logging.INFO)
    logger.addHandler(sh)
    return logger


def get_webui_logger() -> logging.Logger:
    """Logger for WebUI operations: HTTP requests, config, provider health, UI events."""
    return _build_logger("webui", "webui.jsonl")


def get_agents_logger() -> logging.Logger:
    """Logger for agent/tool operations: tool calls, LLM decisions, job lifecycle."""
    return _build_logger("agents", "agents.jsonl")
