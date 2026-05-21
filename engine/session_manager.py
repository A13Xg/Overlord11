"""Overlord11 Engine - Session Manager (tool-gateway baseline)."""

from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

_BASE_DIR = Path(__file__).resolve().parent.parent
_WORKSPACE_DIR = _BASE_DIR / "workspace"


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class EngineSession:
    def __init__(self, session_id: Optional[str] = None, job_id: Optional[str] = None, description: str = ""):
        self._session_id = session_id
        self._job_id = job_id
        self._description = description
        self._session_dir: Optional[Path] = None
        self._logs: list[dict[str, Any]] = []
        self._closed = False
        self._trace_counter = 0

    def create(self) -> str:
        if not self._session_id:
            self._session_id = self._job_id or str(uuid.uuid4())
        self._session_dir = _WORKSPACE_DIR / self._session_id
        (self._session_dir / "artifacts" / "logs" / "agents").mkdir(parents=True, exist_ok=True)
        (self._session_dir / "artifacts" / "logs" / "tools").mkdir(parents=True, exist_ok=True)
        (self._session_dir / "artifacts" / "logs" / "system").mkdir(parents=True, exist_ok=True)
        self._persist_logs()
        return self._session_id

    def load(self) -> bool:
        if not self._session_id:
            return False
        self._session_dir = _WORKSPACE_DIR / self._session_id
        if not self._session_dir.exists():
            return False
        logs_path = self._session_dir / "artifacts" / "logs" / "events.json"
        if logs_path.exists():
            try:
                self._logs = json.loads(logs_path.read_text(encoding="utf-8"))
            except Exception:
                self._logs = []
        return True

    def close(self, status: str = "complete") -> dict:
        self._closed = True
        self.log_event("session_closed", {"status": status})
        self._persist_logs()
        return {"status": status, "session_id": self._session_id}

    def log_event(self, event_type: str, data: Any = None) -> None:
        self._logs.append({"type": event_type, "timestamp": _now_iso(), "data": data})
        self._persist_logs()

    def log_tool_call(self, tool_name: str, params: dict, result: Any = None) -> dict:
        trace_path = self.write_trace("tools", {"tool": tool_name, "params": params, "result": result}, f"tool_{tool_name}")
        entry = {"type": "tool_call", "timestamp": _now_iso(), "tool": tool_name, "params": params, "result": result, "trace_path": trace_path}
        self._logs.append(entry)
        self._persist_logs()
        return entry

    def log_agent(self, agent_id: str, input_text: str, output_text: str) -> dict:
        trace_path = self.write_trace("agents", {"agent_id": agent_id, "input_text": input_text, "output_text": output_text}, f"agent_{agent_id}")
        entry = {
            "type": "agent",
            "timestamp": _now_iso(),
            "agent_id": agent_id,
            "input_len": len(input_text),
            "output_len": len(output_text),
            "output_preview": output_text[:300],
            "trace_path": trace_path,
        }
        self._logs.append(entry)
        self._persist_logs()
        return entry

    def record_system_profile(self, agent_id: str = "SYSTEM") -> dict:
        profile = {
            "captured_at": _now_iso(),
            "agent_id": agent_id,
            "system": "Windows" if __import__("os").name == "nt" else "POSIX",
            "release": "unknown",
            "shell": {"type": "powershell" if __import__("os").name == "nt" else "bash", "env": "auto"},
            "cwd": str(_BASE_DIR),
        }
        self.write_trace("system", profile, "system_profile")
        return profile

    def log_agent_cycle(self, agent_id: str, loop: int, system_prompt: str, messages: list[dict], response: str, tool_calls: list[dict]) -> dict:
        payload = {
            "agent_id": agent_id,
            "loop": loop,
            "system_prompt": system_prompt,
            "messages": messages,
            "response": response,
            "tool_calls": tool_calls,
        }
        trace_path = self.write_trace("agents", payload, f"loop_{loop:02d}_{agent_id}")
        return {"trace_path": trace_path, "payload": payload}

    def log_product_output(self, output_text: str) -> Optional[str]:
        if not output_text:
            return None
        ext = ".html" if "<html" in output_text.lower() else ".md"
        path = f"final_output{ext}"
        self.write_artifact(path, output_text)
        return path

    def write_job_summary(self, summary: dict) -> str:
        return self.write_artifact("artifacts/logs/job_summary.json", json.dumps(summary, indent=2, ensure_ascii=False))

    def write_trace(self, category: str, payload: Any, stem: str) -> str:
        self._trace_counter += 1
        relative_path = f"artifacts/logs/{category}/{self._trace_counter:03d}_{stem}.json"
        self.write_artifact(relative_path, json.dumps(payload, indent=2, ensure_ascii=False, default=str))
        timeline = self._session_dir / "artifacts" / "logs" / "timeline.jsonl" if self._session_dir else None
        if timeline:
            timeline.parent.mkdir(parents=True, exist_ok=True)
            with timeline.open("a", encoding="utf-8") as fh:
                fh.write(json.dumps({"index": self._trace_counter, "category": category, "path": relative_path, "timestamp": _now_iso(), "summary": stem}, ensure_ascii=False) + "\n")
        return relative_path

    def write_artifact(self, relative_path: str, content: str) -> str:
        if not self._session_dir:
            raise RuntimeError("Session directory is not initialized")
        target = self._session_dir / relative_path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")
        return relative_path

    def _persist_logs(self) -> None:
        if not self._session_dir:
            return
        p = self._session_dir / "artifacts" / "logs" / "events.json"
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps(self._logs, indent=2, ensure_ascii=False, default=str), encoding="utf-8")

    @property
    def session_id(self) -> Optional[str]:
        return self._session_id

    @property
    def session_dir(self) -> Optional[Path]:
        return self._session_dir
