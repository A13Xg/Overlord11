"""
MCP runtime subsystem for local stdio servers.
"""

from __future__ import annotations

import json
import logging
import os
import threading
import time
import asyncio
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

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
        self.blocked_tools: set[str] = {"run_command", "execute_python"}

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
            normalized_command = self._normalize_command(command)
            normalized_cwd = self._normalize_cwd(str((raw or {}).get("cwd", "") or ""))
            normalized_args = self._normalize_args(list((raw or {}).get("args", []) or []))
            next_configs[name] = McpServerConfig(
                name=name,
                command=normalized_command,
                args=normalized_args,
                env=dict((raw or {}).get("env", {}) or {}),
                cwd=normalized_cwd,
                auto_start=bool((raw or {}).get("auto_start", True)),
            )
        with self._lock:
            self._configs = next_configs
            for name in next_configs:
                self._states.setdefault(name, McpServerState(name=name))

    def _normalize_command(self, command: str) -> str:
        cmd = (command or "").strip()
        if cmd.lower() in {"python", "python3", "py"}:
            return sys.executable
        p = Path(cmd)
        if not p.is_absolute() and p.exists():
            return str(p.resolve())
        return cmd

    def _normalize_cwd(self, cwd_value: str) -> str:
        cwd = (cwd_value or "").strip()
        if not cwd:
            return str(self.project_root)
        p = Path(cwd)
        if not p.is_absolute():
            p = (self.project_root / p).resolve()
        return str(p)

    def _normalize_args(self, args: list[str]) -> list[str]:
        out: list[str] = []
        for a in args:
            s = str(a)
            p = Path(s)
            if p.suffix.lower() == ".py" and not p.is_absolute():
                candidate = (self.project_root / p).resolve()
                if candidate.exists():
                    out.append(str(candidate))
                    continue
            out.append(s)
        return out

    def start(self, cfg: dict[str, Any]) -> None:
        self.configure(cfg)
        mcp_cfg = cfg.get("mcp", {}) or {}
        if not bool(mcp_cfg.get("enabled", False)):
            self.stop()
            return
        self._running = True
        self.refresh_tools()
        if self._refresh_thread is None or not self._refresh_thread.is_alive():
            self._refresh_thread = threading.Thread(target=self._refresh_loop, daemon=True)
            self._refresh_thread.start()

    def stop(self) -> None:
        self._running = False

    def _refresh_loop(self) -> None:
        while self._running:
            try:
                self.refresh_tools()
            except Exception as exc:
                log.warning("MCP periodic refresh failed: %s", exc)
            time.sleep(self._refresh_interval_s)

    def refresh_tools(self) -> dict[str, Any]:
        discovered = 0
        with self._lock:
            configs = dict(self._configs)
        for name, cfg in configs.items():
            state = self._states.setdefault(name, McpServerState(name=name))
            try:
                tools = self._run_coro_blocking(self._sdk_list_tools(cfg))
                if not isinstance(tools, list):
                    tools = []
                self.registry.replace_for_server(name, tools)
                state.tool_count = len(tools)
                state.running = True
                state.pid = None
                state.last_error = None
                state.last_heartbeat = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
                discovered += len(tools)
            except Exception as exc:
                state.last_error = str(exc)
                state.running = False
                state.pid = None
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

    def call_tool(
        self,
        full_name: str,
        arguments: dict[str, Any],
        timeout_s: Optional[int] = None,
        allowed_root: Optional[str] = None,
    ) -> dict[str, Any]:
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
        if tool_name in self.policy.blocked_tools:
            return {
                "success": False,
                "data": None,
                "error": f"Tool '{tool_name}' is blocked by safety policy in MCP mode.",
            }
        sandboxed_args, sandbox_error = self._sandbox_tool_arguments(
            tool_name=tool_name,
            arguments=arguments,
            allowed_root=allowed_root,
        )
        if sandbox_error:
            return {"success": False, "data": None, "error": sandbox_error}
        with self._lock:
            cfg = self._configs.get(server_name)
        if cfg is None:
            return {"success": False, "data": None, "error": f"Server '{server_name}' is not configured."}
        try:
            result = self._run_coro_blocking(
                self._sdk_call_tool(
                    cfg=cfg,
                    tool_name=tool_name,
                    arguments=sandboxed_args,
                    timeout_s=int(timeout_s or self.policy.per_call_timeout_s),
                )
            )
            data = result
            if isinstance(data, dict) and {"success", "data", "error"}.issubset(set(data.keys())):
                return data
            return {"success": True, "data": data, "error": None}
        except Exception as exc:
            return {"success": False, "data": None, "error": f"Tool call failed: {exc}"}

    def _sandbox_tool_arguments(
        self,
        tool_name: str,
        arguments: dict[str, Any],
        allowed_root: Optional[str],
    ) -> tuple[dict[str, Any], Optional[str]]:
        if not isinstance(arguments, dict):
            return {}, "Tool arguments must be an object."
        if not allowed_root:
            return dict(arguments), None

        root = Path(allowed_root).resolve()
        if not root.exists():
            return {}, f"Allowed workspace root does not exist: '{root}'."

        # tool -> path-like argument keys that must remain inside allowed_root
        sandbox_keys: dict[str, list[str]] = {
            "write_file": ["path"],
            "write_html_page": ["filename"],
            "write_markdown_summary": ["filename"],
            "read_file": ["path"],
            "replace_in_file": ["path"],
            "list_directory": ["path"],
            "search_content": ["directory"],
            "run_command": ["working_dir"],
            "git_operation": ["repo_path"],
        }

        out = dict(arguments)

        def _resolve_within_root(raw: Any, key: str) -> tuple[Optional[str], Optional[str]]:
            if raw is None or raw == "":
                return str(root), None if key == "working_dir" else (None, None)
            if not isinstance(raw, str):
                return None, f"Argument '{key}' must be a string path."
            p = Path(raw)
            target = p.resolve() if p.is_absolute() else (root / p).resolve()
            try:
                target.relative_to(root)
            except ValueError:
                return None, (
                    f"Path '{raw}' resolves outside the job workspace. "
                    f"Use a path under '{root}'."
                )
            return str(target), None

        for key in sandbox_keys.get(tool_name, []):
            if key not in out:
                continue
            resolved, err = _resolve_within_root(out.get(key), key)
            if err:
                return {}, err
            if resolved is not None:
                out[key] = resolved

        # Special cases with conditional file-path semantics
        if tool_name == "query_json":
            val = out.get("input")
            if isinstance(val, str) and val.strip().lower().endswith(".json"):
                resolved, err = _resolve_within_root(val, "input")
                if err:
                    return {}, err
                if resolved is not None:
                    out["input"] = resolved
        if tool_name == "compute_hash" and str(out.get("input_type", "string")) == "file":
            resolved, err = _resolve_within_root(out.get("input"), "input")
            if err:
                return {}, err
            if resolved is not None:
                out["input"] = resolved

        return out, None

    def _run_coro_blocking(self, coro: Any) -> Any:
        """
        Run a coroutine from sync code regardless of whether an event loop
        is already active in the current thread.
        """
        try:
            asyncio.get_running_loop()
            has_running_loop = True
        except RuntimeError:
            has_running_loop = False

        if not has_running_loop:
            return asyncio.run(coro)

        box: dict[str, Any] = {"result": None, "error": None}

        def _worker() -> None:
            try:
                box["result"] = asyncio.run(coro)
            except Exception as exc:
                box["error"] = exc

        t = threading.Thread(target=_worker, daemon=True)
        t.start()
        t.join()
        if box["error"] is not None:
            raise box["error"]
        return box["result"]

    async def _sdk_list_tools(self, cfg: McpServerConfig) -> list[dict[str, Any]]:
        env = dict(os.environ)
        env.update({str(k): str(v) for k, v in (cfg.env or {}).items()})
        server_params = StdioServerParameters(
            command=cfg.command,
            args=list(cfg.args or []),
            env=env,
            cwd=(cfg.cwd or str(self.project_root)),
        )
        async with stdio_client(server_params) as (read, write):
            async with ClientSession(read, write) as session:
                await asyncio.wait_for(session.initialize(), timeout=self.policy.per_call_timeout_s)
                resp = await asyncio.wait_for(session.list_tools(), timeout=self.policy.per_call_timeout_s)
                out: list[dict[str, Any]] = []
                for tool in resp.tools:
                    out.append(
                        {
                            "name": str(getattr(tool, "name", "")),
                            "description": str(getattr(tool, "description", "") or ""),
                            "inputSchema": getattr(tool, "inputSchema", None) or {"type": "object", "properties": {}},
                        }
                    )
                return out

    async def _sdk_call_tool(self, cfg: McpServerConfig, tool_name: str, arguments: dict[str, Any], timeout_s: int) -> Any:
        env = dict(os.environ)
        env.update({str(k): str(v) for k, v in (cfg.env or {}).items()})
        server_params = StdioServerParameters(
            command=cfg.command,
            args=list(cfg.args or []),
            env=env,
            cwd=(cfg.cwd or str(self.project_root)),
        )
        async with stdio_client(server_params) as (read, write):
            async with ClientSession(read, write) as session:
                await asyncio.wait_for(session.initialize(), timeout=timeout_s)
                result = await asyncio.wait_for(session.call_tool(tool_name, arguments=arguments), timeout=timeout_s)
                structured = getattr(result, "structuredContent", None)
                if structured is not None:
                    return structured
                content = getattr(result, "content", None)
                if content and isinstance(content, list):
                    first = content[0]
                    text = getattr(first, "text", None)
                    if text is not None:
                        return text
                return {"raw": str(result)}


_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
mcp_runtime = McpRuntime(_PROJECT_ROOT)
