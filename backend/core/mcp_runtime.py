"""
MCP runtime subsystem for local stdio servers.
"""

from __future__ import annotations

import json
import logging
import os
import queue
import subprocess
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

log = logging.getLogger("overlord11.mcp_runtime")


@dataclass
class McpServerConfig:
    name: str
    command: str
    args: list[str] = field(default_factory=list)
    env: dict[str, str] = field(default_factory=dict)
    cwd: str = ""
    auto_start: bool = True


@dataclass
class McpServerState:
    name: str
    running: bool = False
    pid: Optional[int] = None
    last_heartbeat: Optional[str] = None
    last_error: Optional[str] = None
    tool_count: int = 0


class _JsonRpcStdIoClient:
    def __init__(self, cfg: McpServerConfig, project_root: Path) -> None:
        self.cfg = cfg
        self.project_root = project_root
        self.proc: Optional[subprocess.Popen] = None
        self._seq = 0
        self._lock = threading.Lock()
        self._pending: dict[int, queue.Queue] = {}
        self._reader_thread: Optional[threading.Thread] = None
        self._closed = False
        self._last_error = ""

    @property
    def last_error(self) -> str:
        return self._last_error

    def start(self) -> None:
        if self.proc and self.proc.poll() is None:
            return
        cwd = Path(self.cfg.cwd).resolve() if self.cfg.cwd else self.project_root
        env = dict(**self.cfg.env) if self.cfg.env else {}
        merged_env = dict(**env)
        for k, v in env.items():
            merged_env[str(k)] = str(v)
        runtime_env = dict(**os.environ)
        runtime_env.update(merged_env)
        self.proc = subprocess.Popen(
            [self.cfg.command] + list(self.cfg.args or []),
            cwd=str(cwd),
            env=runtime_env,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            bufsize=0,
        )
        self._closed = False
        self._reader_thread = threading.Thread(target=self._reader_loop, daemon=True)
        self._reader_thread.start()
        self._initialize_session()

    def stop(self) -> None:
        self._closed = True
        p = self.proc
        if p is None:
            return
        try:
            if p.poll() is None:
                p.terminate()
                p.wait(timeout=5)
        except Exception:
            try:
                p.kill()
            except Exception:
                pass
        self.proc = None

    def is_running(self) -> bool:
        return self.proc is not None and self.proc.poll() is None

    def pid(self) -> Optional[int]:
        return self.proc.pid if self.proc else None

    def _next_id(self) -> int:
        with self._lock:
            self._seq += 1
            return self._seq

    def _write_message(self, payload: dict[str, Any]) -> None:
        if self.proc is None or self.proc.stdin is None:
            raise RuntimeError("MCP server is not running")
        raw = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        header = f"Content-Length: {len(raw)}\r\n\r\n".encode("ascii")
        self.proc.stdin.write(header + raw)
        self.proc.stdin.flush()

    def _read_message(self) -> Optional[dict[str, Any]]:
        if self.proc is None or self.proc.stdout is None:
            return None
        stream = self.proc.stdout
        content_length = None
        while True:
            line = stream.readline()
            if not line:
                return None
            if line in (b"\r\n", b"\n"):
                break
            parts = line.decode("utf-8", errors="replace").strip().split(":", 1)
            if len(parts) == 2 and parts[0].lower() == "content-length":
                try:
                    content_length = int(parts[1].strip())
                except ValueError:
                    content_length = None
        if content_length is None:
            return None
        body = stream.read(content_length)
        if not body:
            return None
        try:
            return json.loads(body.decode("utf-8", errors="replace"))
        except json.JSONDecodeError:
            return None

    def _reader_loop(self) -> None:
        while not self._closed:
            msg = self._read_message()
            if msg is None:
                break
            msg_id = msg.get("id")
            if isinstance(msg_id, int):
                with self._lock:
                    q = self._pending.get(msg_id)
                if q is not None:
                    q.put(msg)

    def request(self, method: str, params: Optional[dict[str, Any]] = None, timeout_s: int = 20) -> dict[str, Any]:
        if not self.is_running():
            raise RuntimeError("MCP server is not running")
        rid = self._next_id()
        q: queue.Queue = queue.Queue(maxsize=1)
        with self._lock:
            self._pending[rid] = q
        try:
            payload = {"jsonrpc": "2.0", "id": rid, "method": method, "params": params or {}}
            self._write_message(payload)
            try:
                response = q.get(timeout=max(1, timeout_s))
            except queue.Empty:
                raise TimeoutError(f"MCP request timed out for method '{method}'")
            if "error" in response:
                err = response.get("error") or {}
                message = err.get("message", "unknown MCP error")
                raise RuntimeError(f"MCP error: {message}")
            return response.get("result") or {}
        finally:
            with self._lock:
                self._pending.pop(rid, None)

    def notify(self, method: str, params: Optional[dict[str, Any]] = None) -> None:
        if not self.is_running():
            raise RuntimeError("MCP server is not running")
        payload = {"jsonrpc": "2.0", "method": method, "params": params or {}}
        self._write_message(payload)

    def _initialize_session(self) -> None:
        try:
            self.request(
                "initialize",
                {
                    "protocolVersion": "2024-11-05",
                    "capabilities": {"tools": {}},
                    "clientInfo": {"name": "overlord11", "version": "2.3.0"},
                },
                timeout_s=20,
            )
            self.notify("notifications/initialized", {})
        except Exception as exc:
            self._last_error = str(exc)
            raise


class McpToolRegistry:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._tools: dict[str, dict[str, Any]] = {}

    def replace_for_server(self, server_name: str, tools: list[dict[str, Any]]) -> None:
        with self._lock:
            next_tools = {k: v for k, v in self._tools.items() if v.get("server") != server_name}
            for item in tools:
                raw_name = str(item.get("name", "")).strip()
                if not raw_name:
                    continue
                full_name = f"{server_name}.{raw_name}"
                next_tools[full_name] = {
                    "full_name": full_name,
                    "server": server_name,
                    "name": raw_name,
                    "description": str(item.get("description", "")),
                    "inputSchema": item.get("inputSchema") or {"type": "object", "properties": {}},
                }
            self._tools = next_tools

    def all_tools(self) -> list[dict[str, Any]]:
        with self._lock:
            return [self._tools[k] for k in sorted(self._tools.keys())]

    def get(self, full_name: str) -> Optional[dict[str, Any]]:
        with self._lock:
            return self._tools.get(full_name)


class ToolPolicy:
    def __init__(self, max_calls_per_job: int = 20, per_call_timeout_s: int = 30, max_argument_chars: int = 20000) -> None:
        self.max_calls_per_job = max(1, int(max_calls_per_job))
        self.per_call_timeout_s = max(1, int(per_call_timeout_s))
        self.max_argument_chars = max(500, int(max_argument_chars))

    def validate_call_budget(self, current_calls: int) -> Optional[str]:
        if current_calls >= self.max_calls_per_job:
            return f"Tool call budget exceeded ({current_calls}/{self.max_calls_per_job})."
        return None

    def validate_arguments(self, arguments: dict[str, Any]) -> Optional[str]:
        size = len(json.dumps(arguments, ensure_ascii=False, default=str))
        if size > self.max_argument_chars:
            return f"Tool arguments too large ({size} chars). Limit is {self.max_argument_chars}."
        return None


class McpRuntime:
    def __init__(self, project_root: Path) -> None:
        self.project_root = project_root
        self.registry = McpToolRegistry()
        self._clients: dict[str, _JsonRpcStdIoClient] = {}
        self._states: dict[str, McpServerState] = {}
        self._configs: dict[str, McpServerConfig] = {}
        self._lock = threading.Lock()
        self._running = False
        self._refresh_thread: Optional[threading.Thread] = None
        self._refresh_interval_s = 60
        self.policy = ToolPolicy()

    def configure(self, cfg: dict[str, Any]) -> None:
        mcp_cfg = cfg.get("mcp", {}) or {}
        self._refresh_interval_s = max(5, int(mcp_cfg.get("discovery_interval_s", 60) or 60))
        policy_cfg = mcp_cfg.get("policy", {}) or {}
        self.policy = ToolPolicy(
            max_calls_per_job=int(policy_cfg.get("max_calls_per_job", 20) or 20),
            per_call_timeout_s=int(policy_cfg.get("per_call_timeout_s", 30) or 30),
            max_argument_chars=int(policy_cfg.get("max_argument_chars", 20000) or 20000),
        )
        next_configs: dict[str, McpServerConfig] = {}
        for raw in mcp_cfg.get("servers", []) or []:
            name = str((raw or {}).get("name", "")).strip()
            command = str((raw or {}).get("command", "")).strip()
            if not name or not command:
                continue
            next_configs[name] = McpServerConfig(
                name=name,
                command=command,
                args=list((raw or {}).get("args", []) or []),
                env=dict((raw or {}).get("env", {}) or {}),
                cwd=str((raw or {}).get("cwd", "") or ""),
                auto_start=bool((raw or {}).get("auto_start", True)),
            )
        with self._lock:
            self._configs = next_configs
            for name in next_configs:
                self._states.setdefault(name, McpServerState(name=name))

    def start(self, cfg: dict[str, Any]) -> None:
        self.configure(cfg)
        mcp_cfg = cfg.get("mcp", {}) or {}
        if not bool(mcp_cfg.get("enabled", False)):
            self.stop()
            return
        self._running = True
        self._ensure_servers_started()
        self.refresh_tools()
        if self._refresh_thread is None or not self._refresh_thread.is_alive():
            self._refresh_thread = threading.Thread(target=self._refresh_loop, daemon=True)
            self._refresh_thread.start()

    def stop(self) -> None:
        self._running = False
        with self._lock:
            clients = list(self._clients.values())
            self._clients = {}
        for client in clients:
            client.stop()

    def _refresh_loop(self) -> None:
        while self._running:
            try:
                self._ensure_servers_started()
                self.refresh_tools()
            except Exception as exc:
                log.warning("MCP periodic refresh failed: %s", exc)
            time.sleep(self._refresh_interval_s)

    def _ensure_servers_started(self) -> None:
        with self._lock:
            configs = dict(self._configs)
        for name, cfg in configs.items():
            if not cfg.auto_start:
                continue
            with self._lock:
                client = self._clients.get(name)
                if client is None:
                    client = _JsonRpcStdIoClient(cfg, self.project_root)
                    self._clients[name] = client
            state = self._states.setdefault(name, McpServerState(name=name))
            try:
                if not client.is_running():
                    client.start()
                state.running = client.is_running()
                state.pid = client.pid()
                state.last_error = None
            except Exception as exc:
                state.running = False
                state.last_error = str(exc)

    def refresh_tools(self) -> dict[str, Any]:
        discovered = 0
        with self._lock:
            clients = dict(self._clients)
        for name, client in clients.items():
            state = self._states.setdefault(name, McpServerState(name=name))
            try:
                if not client.is_running():
                    state.running = False
                    continue
                result = client.request("tools/list", {}, timeout_s=self.policy.per_call_timeout_s)
                tools = result.get("tools", []) if isinstance(result, dict) else []
                if not isinstance(tools, list):
                    tools = []
                self.registry.replace_for_server(name, tools)
                state.tool_count = len(tools)
                state.running = True
                state.pid = client.pid()
                state.last_error = None
                state.last_heartbeat = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
                discovered += len(tools)
            except Exception as exc:
                state.last_error = str(exc)
                state.running = client.is_running()
        snapshot = {
            "discovered_tool_count": discovered,
            "servers": self.server_status(),
            "tools": self.registry.all_tools(),
        }
        self._write_snapshot(snapshot)
        return snapshot

    def _write_snapshot(self, snapshot: dict[str, Any]) -> None:
        out = self.project_root / "workspace" / ".mcp_tools_snapshot.json"
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(snapshot, indent=2, ensure_ascii=False), encoding="utf-8")

    def server_status(self) -> list[dict[str, Any]]:
        with self._lock:
            names = sorted(self._states.keys())
            return [
                {
                    "name": self._states[n].name,
                    "running": self._states[n].running,
                    "pid": self._states[n].pid,
                    "last_heartbeat": self._states[n].last_heartbeat,
                    "last_error": self._states[n].last_error,
                    "tool_count": self._states[n].tool_count,
                }
                for n in names
            ]

    def tool_catalog(self) -> list[dict[str, Any]]:
        return self.registry.all_tools()

    def _validate_against_schema(self, schema: dict[str, Any], arguments: dict[str, Any]) -> Optional[str]:
        required = list((schema or {}).get("required", []) or [])
        properties = dict((schema or {}).get("properties", {}) or {})
        for key in required:
            if key not in arguments:
                return f"Missing required argument '{key}'."
        for key, value in arguments.items():
            spec = properties.get(key) or {}
            expected = spec.get("type")
            if expected == "string" and not isinstance(value, str):
                return f"Argument '{key}' must be a string."
            if expected == "integer" and not isinstance(value, int):
                return f"Argument '{key}' must be an integer."
            if expected == "number" and not isinstance(value, (int, float)):
                return f"Argument '{key}' must be a number."
            if expected == "boolean" and not isinstance(value, bool):
                return f"Argument '{key}' must be a boolean."
            if expected == "array" and not isinstance(value, list):
                return f"Argument '{key}' must be an array."
            if expected == "object" and not isinstance(value, dict):
                return f"Argument '{key}' must be an object."
        return None

    def call_tool(self, full_name: str, arguments: dict[str, Any], timeout_s: Optional[int] = None) -> dict[str, Any]:
        meta = self.registry.get(full_name)
        if meta is None:
            return {"success": False, "data": None, "error": f"Unknown MCP tool '{full_name}'."}
        arg_error = self.policy.validate_arguments(arguments)
        if arg_error:
            return {"success": False, "data": None, "error": arg_error}
        schema_error = self._validate_against_schema(meta.get("inputSchema") or {}, arguments)
        if schema_error:
            return {"success": False, "data": None, "error": schema_error}
        server_name = str(meta.get("server"))
        tool_name = str(meta.get("name"))
        with self._lock:
            client = self._clients.get(server_name)
        if client is None or not client.is_running():
            return {"success": False, "data": None, "error": f"Server '{server_name}' is not running."}
        try:
            result = client.request(
                "tools/call",
                {"name": tool_name, "arguments": arguments},
                timeout_s=int(timeout_s or self.policy.per_call_timeout_s),
            )
            data = result
            if isinstance(result, dict) and "structuredContent" in result:
                data = result.get("structuredContent")
            if isinstance(data, dict) and {"success", "data", "error"}.issubset(set(data.keys())):
                return data
            return {"success": True, "data": data, "error": None}
        except Exception as exc:
            return {"success": False, "data": None, "error": f"Tool call failed: {exc}"}


_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
mcp_runtime = McpRuntime(_PROJECT_ROOT)
