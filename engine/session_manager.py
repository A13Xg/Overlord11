"""
Overlord11 Engine - Session Manager
======================================
Engine-level session management wrapping tools/python/session_manager.py.
"""

import importlib.util as _ilu
import json
import os
import platform
import shutil
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
_CONSCIOUSNESS_PATH = _BASE_DIR / "Consciousness.md"

if str(_TOOLS_DIR) not in sys.path:
    sys.path.insert(0, str(_TOOLS_DIR))

from log_manager import log_event as _log_event_entry
from log_manager import log_llm_decision as _log_llm_decision
from log_manager import log_tool_invocation as _log_tool_invocation
from task_workspace import ensure_task_layout


class EngineSession:
    """Wraps the existing session functions with an engine-friendly interface."""

    def __init__(self, session_id: Optional[str] = None, job_id: Optional[str] = None, description: str = ""):
        self._session_id: Optional[str] = session_id
        self._job_id: Optional[str] = job_id
        self._description = description
        self._session_dir: Optional[Path] = None
        self._logs: list = []
        self._closed = False
        self._trace_counter = 0

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def create(self) -> str:
        """Create a new session, scaffold the workspace, and return the session_id.

        The workspace is named with the format {ISO_DATE}_{JOB_ID} if job_id is provided,
        otherwise uses just the ISO timestamp.
        """
        result = create_session(description=self._description, job_id=self._job_id)
        self._session_id = result["session_id"]
        self._session_dir = Path(result["workspace"])
        self._ensure_runtime_dirs()
        self._init_project_docs()
        self._persist_logs()
        return self._session_id

    def load(self) -> bool:
        """Restore session state from an existing session_id. Returns True on success."""
        if not self._session_id:
            return False
        try:
            data = get_session(self._session_id)
            if "error" in data:
                return False
            workspace = data.get("workspace")
            if workspace:
                self._session_dir = Path(workspace)
                self._ensure_runtime_dirs()
                # Load existing logs if present — check new artifacts/logs/ path first, then legacy
                logs_path = self._session_dir / "artifacts" / "logs" / "events.json"
                if not logs_path.exists():
                    logs_path = self._session_dir / "logs" / "events.json"
                if not logs_path.exists():
                    logs_path = self._session_dir / "logs.json"
                if logs_path.exists():
                    try:
                        self._logs = json.loads(logs_path.read_text(encoding="utf-8"))
                    except (json.JSONDecodeError, OSError):
                        pass
            return True
        except Exception:
            return False

    def close(self, status: str = "complete") -> dict:
        """Close the session."""
        if self._closed or not self._session_id:
            return {}
        self._closed = True
        self._persist_logs()
        return close_session(self._session_id, summary=status)

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
        if self._session_id:
            _log_event_entry(self._session_id, event_type, {"data": data})

    def log_tool_call(self, tool_name: str, params: dict, result: Any = None) -> dict:
        """Log a tool invocation."""
        trace_path = self.write_trace(
            category="tools",
            payload={
                "tool": tool_name,
                "params": params,
                "result": result,
            },
            stem=f"tool_{tool_name.lower()}",
        )
        entry = {
            "type": "tool_call",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "tool": tool_name,
            "params": params,
            "result": result,
            "trace_path": trace_path,
        }
        self._logs.append(entry)
        self._persist_logs()
        # Also register in the underlying session
        if self._session_id:
            try:
                log_change(
                    self._session_id,
                    tool_name,         # file_path
                    "tool_call",       # action
                    summary=str(result)[:200],
                )
            except Exception:
                pass
            _log_tool_invocation(
                session_id=self._session_id,
                tool_name=tool_name,
                params=params,
                result=result if isinstance(result, dict) else {"value": result},
                duration_ms=(result or {}).get("duration_ms") if isinstance(result, dict) else None,
            )
        return entry

    def log_agent(self, agent_id: str, input_text: str, output_text: str) -> dict:
        """Log an agent invocation."""
        trace_path = self.write_trace(
            category="agents",
            payload={
                "agent_id": agent_id,
                "input_text": input_text,
                "output_text": output_text,
            },
            stem=f"agent_{agent_id.lower()}",
        )
        entry = {
            "type": "agent",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "agent_id": agent_id,
            "input_len": len(input_text),
            "output_len": len(output_text),
            "output_preview": output_text[:300],
            "trace_path": trace_path,
        }
        self._logs.append(entry)
        self._persist_logs()
        if self._session_id:
            _log_llm_decision(
                session_id=self._session_id,
                agent_id=agent_id,
                decision=output_text[:1000],
                reasoning=input_text[:1000],
                context={"trace_path": trace_path},
            )
        return entry

    def record_system_profile(self, agent_id: str = "SYSTEM") -> dict:
        """Capture OS and shell profile, persist it as artifacts, and update memory."""
        shell_path = os.environ.get("SHELL") or os.environ.get("COMSPEC") or ""
        is_windows = platform.system() == "Windows"

        # Detect shell type more precisely
        shell_name = Path(shell_path).name.lower() if shell_path else ""
        if "powershell" in shell_name or "pwsh" in shell_name:
            shell_type = "powershell"
        elif "bash" in shell_name or os.environ.get("BASH_VERSION"):
            shell_type = "bash"
        elif "zsh" in shell_name:
            shell_type = "zsh"
        elif "cmd.exe" in shell_name or shell_name == "cmd":
            shell_type = "cmd"
        else:
            shell_type = "bash" if not is_windows else "cmd"

        # Check availability of common tools
        _tools_check = ["git", "python", "python3", "pip", "pip3", "node", "npm", "rg", "curl", "wget"]
        available_tools = [t for t in _tools_check if shutil.which(t)]

        profile = {
            "captured_at": datetime.now(timezone.utc).isoformat(),
            "agent_id": agent_id,
            "platform": platform.platform(),
            "system": platform.system(),
            "release": platform.release(),
            "machine": platform.machine(),
            "python_version": platform.python_version(),
            "cwd": str(_BASE_DIR),
            "shell": {
                "env": shell_path,
                "type": shell_type,
                "resolved": shutil.which(Path(shell_path).name) if shell_path else None,
                "use_unix_syntax": shell_type in ("bash", "zsh") or not is_windows,
            },
            "available_tools": available_tools,
            "env": {
                "USER": os.environ.get("USER") or os.environ.get("USERNAME", ""),
                "TERM": os.environ.get("TERM", ""),
                "PATH_HEAD": os.environ.get("PATH", "").split(os.pathsep)[:8],
            },
        }
        self.write_trace(category="system", payload=profile, stem="system_profile")
        self.write_artifact("artifacts/agent/system_profile.json", json.dumps(profile, indent=2, ensure_ascii=False))
        self._update_consciousness_environment(profile)
        self.log_event("system_profile", profile)
        return profile

    def log_agent_cycle(
        self,
        agent_id: str,
        loop: int,
        system_prompt: str,
        messages: list[dict],
        response: str,
        tool_calls: list[dict],
    ) -> dict:
        payload = {
            "agent_id": agent_id,
            "loop": loop,
            "system_prompt": system_prompt,
            "messages": messages,
            "response": response,
            "tool_calls": tool_calls,
        }
        trace_path = self.write_trace(category="agents", payload=payload, stem=f"loop_{loop:02d}_{agent_id.lower()}")
        return {"trace_path": trace_path, "payload": payload}

    def log_product_output(self, output_text: str) -> Optional[str]:
        if not output_text:
            return None
        extension = ".html" if "<html" in output_text.lower() else ".md"
        relative_path = f"final_output{extension}"
        self.write_artifact(relative_path, output_text)
        return relative_path

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
            return self._session_dir
        return None

    @property
    def session_dir(self) -> Optional[Path]:
        return self._session_dir

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _persist_logs(self) -> None:
        """Write events.json into artifacts/logs/."""
        if not self._session_dir:
            return
        logs_path = self._session_dir / "artifacts" / "logs" / "events.json"
        try:
            logs_path.write_text(
                json.dumps(self._logs, indent=2, ensure_ascii=False, default=str),
                encoding="utf-8",
            )
        except OSError:
            pass

    def write_trace(self, category: str, payload: Any, stem: str) -> str:
        """Write a structured trace file and append a JSONL timeline entry."""
        self._ensure_runtime_dirs()
        self._trace_counter += 1
        if category == "agents":
            relative_path = f"artifacts/logs/agents/{self._trace_counter:03d}_{stem}.json"
        elif category == "tools":
            relative_path = f"artifacts/logs/tools/{self._trace_counter:03d}_{stem}.json"
        else:
            relative_path = f"artifacts/logs/system/{self._trace_counter:03d}_{stem}.json"
        self.write_artifact(relative_path, json.dumps(payload, indent=2, ensure_ascii=False, default=str))
        timeline_entry = {
            "index": self._trace_counter,
            "category": category,
            "path": relative_path,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "summary": stem,
        }
        timeline_path = self._session_dir / "artifacts" / "logs" / "timeline.jsonl" if self._session_dir else None
        if timeline_path:
            with timeline_path.open("a", encoding="utf-8") as handle:
                handle.write(json.dumps(timeline_entry, ensure_ascii=False) + "\n")
        return relative_path

    def write_artifact(self, relative_path: str, content: str) -> str:
        self._ensure_runtime_dirs()
        if not self._session_dir:
            raise RuntimeError("Session directory is not initialized")
        target = self._session_dir / relative_path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")
        return relative_path

    def _ensure_runtime_dirs(self) -> None:
        if not self._session_dir:
            return
        ensure_task_layout(self._session_dir)

    def _init_project_docs(self) -> None:
        """Auto-create the 5 agent context files at the workspace root."""
        if not self._session_dir:
            return
        try:
            _pdi_path = _TOOLS_DIR / "project_docs_init.py"
            _pdi_spec = _ilu.spec_from_file_location("_project_docs_init", _pdi_path)
            _pdi_mod = _ilu.module_from_spec(_pdi_spec)  # type: ignore[arg-type]
            _pdi_spec.loader.exec_module(_pdi_mod)  # type: ignore[union-attr]
            _pdi_mod.init_all(
                project_dir=str(self._session_dir),
                project_name=self._description[:60] or "Session",
                description=self._description,
            )
        except Exception:
            pass  # Non-fatal: agent can still call project_docs_init manually if needed

    def _update_consciousness_environment(self, profile: dict) -> None:
        """Persist the latest execution environment into shared memory."""
        title = "### [PERSISTENT] Execution Environment Profile"
        block = (
            f"{title}\n"
            f"- **Source**: SYSTEM\n"
            f"- **Created**: {datetime.now().strftime('%Y-%m-%d %H:%M')}\n"
            f"- **TTL**: persistent\n"
            f"- **Status**: ACTIVE\n"
            f"- **Context**: Runtime host is {profile['system']} {profile['release']} on {profile['machine']}. Shell type: {profile['shell'].get('type', 'auto')}; Python {profile['python_version']}. Available tools: {', '.join(profile.get('available_tools', [])) or 'unknown'}.\n"
            f"- **Action**: {'Use Unix/bash shell syntax (forward slashes, $VAR, etc.).' if profile['shell'].get('use_unix_syntax') else 'Use Windows shell syntax (backslashes, %VAR%, etc.).'} Check available_tools list before calling run_shell_command with tools that may not be installed.\n"
        )
        if not _CONSCIOUSNESS_PATH.exists():
            return
        text = _CONSCIOUSNESS_PATH.read_text(encoding="utf-8")
        if title in text:
            start = text.index(title)
            end = text.find("\n### [", start + len(title))
            if end == -1:
                end = len(text)
            text = text[:start] + block + text[end:]
        else:
            marker = "### Shared Context\n\n<!-- Persistent context that all agents should be aware of -->\n\n"
            if marker in text:
                text = text.replace(marker, marker + block + "\n", 1)
            else:
                text += "\n\n" + block
        _CONSCIOUSNESS_PATH.write_text(text, encoding="utf-8")
