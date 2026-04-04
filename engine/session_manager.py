"""
Overlord11 Engine - Session Manager
======================================
Engine-level session management wrapping tools/python/session_manager.py.
"""

import importlib.util as _ilu
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

_TOOLS_DIR = Path(__file__).resolve().parent.parent / "tools" / "python"

# Load tools/python/session_manager.py by absolute path to avoid name collision
_TOOLS_SESSION_MANAGER_PATH = _TOOLS_DIR / "session_manager.py"
try:
    _spec = _ilu.spec_from_file_location("_tools_session_manager", _TOOLS_SESSION_MANAGER_PATH)
    _tools_sm = _ilu.module_from_spec(_spec)  # type: ignore[arg-type]
    _spec.loader.exec_module(_tools_sm)  # type: ignore[union-attr]
    create_session = _tools_sm.create_session
    close_session = _tools_sm.close_session
    log_change = _tools_sm.log_change
    get_session = _tools_sm.get_session
except Exception as _e:
    raise ImportError(
        f"Failed to load tools/python/session_manager.py — ensure the file exists at "
        f"{_TOOLS_SESSION_MANAGER_PATH}. Original error: {_e}"
    ) from _e

_BASE_DIR = Path(__file__).resolve().parent.parent
_WORKSPACE_DIR = _BASE_DIR / "workspace"


class EngineSession:
    """Wraps the existing session functions with an engine-friendly interface."""

    def __init__(self, session_id: Optional[str] = None, description: str = ""):
        self._session_id: Optional[str] = session_id
        self._description = description
        self._session_dir: Optional[Path] = None
        self._logs: list = []
        self._closed = False

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def create(self) -> str:
        """Create a new session and return the session_id."""
        result = create_session(description=self._description)
        self._session_id = result["session_id"]
        self._session_dir = Path(result["workspace"])
        (self._session_dir / "outputs").mkdir(exist_ok=True)
        self._persist_logs()
        return self._session_id

    def close(self, status: str = "complete") -> dict:
        """Close the session."""
        if self._closed or not self._session_id:
            return {}
        self._closed = True
        self._persist_logs()
        return close_session(self._session_id, status=status)

    # ------------------------------------------------------------------
    # Logging helpers
    # ------------------------------------------------------------------

    def log_event(self, event_type: str, data: Any = None) -> None:
        """Append a generic event to logs.json."""
        entry = {
            "type": event_type,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "data": data,
        }
        self._logs.append(entry)
        self._persist_logs()

    def log_tool_call(self, tool_name: str, params: dict, result: Any = None) -> None:
        """Log a tool invocation."""
        entry = {
            "type": "tool_call",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "tool": tool_name,
            "params": params,
            "result": result,
        }
        self._logs.append(entry)
        self._persist_logs()
        # Also register in the underlying session
        if self._session_id:
            try:
                log_change(
                    self._session_id,
                    {"file": tool_name, "action": "tool_call", "summary": str(result)[:200]},
                )
            except Exception:
                pass

    def log_agent(self, agent_id: str, input_text: str, output_text: str) -> None:
        """Log an agent invocation."""
        entry = {
            "type": "agent",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "agent_id": agent_id,
            "input_len": len(input_text),
            "output_len": len(output_text),
            "output_preview": output_text[:300],
        }
        self._logs.append(entry)
        self._persist_logs()

    # ------------------------------------------------------------------
    # Introspection
    # ------------------------------------------------------------------

    def to_dict(self) -> dict:
        """Return a serialisable representation of the session."""
        base = {}
        if self._session_id:
            try:
                base = get_session(self._session_id) or {}
            except Exception:
                pass
        base.update(
            {
                "session_id": self._session_id,
                "description": self._description,
                "session_dir": str(self._session_dir) if self._session_dir else None,
                "log_count": len(self._logs),
                "closed": self._closed,
            }
        )
        return base

    # ------------------------------------------------------------------
    # Properties
    # ------------------------------------------------------------------

    @property
    def session_id(self) -> Optional[str]:
        return self._session_id

    @property
    def outputs_dir(self) -> Optional[Path]:
        if self._session_dir:
            return self._session_dir / "outputs"
        return None

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _persist_logs(self) -> None:
        """Write logs.json into the session directory."""
        if not self._session_dir:
            return
        logs_path = self._session_dir / "logs.json"
        try:
            logs_path.write_text(
                json.dumps(self._logs, indent=2, ensure_ascii=False, default=str),
                encoding="utf-8",
            )
        except OSError:
            pass
