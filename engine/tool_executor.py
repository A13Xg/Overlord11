"""
Overlord11 Engine - Tool Executor
====================================
Tool call detection and execution for the engine loop.
"""

import importlib.util
import json
import os
import re
import subprocess
import sys
import threading
import time
from contextlib import contextmanager
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, List, Optional

_BASE_DIR = Path(__file__).resolve().parent.parent
_CANONICAL_CONSCIOUSNESS = (_BASE_DIR / "Consciousness.md").resolve()
_CANONICAL_MEMORY = (_BASE_DIR / "Memory.md").resolve()

try:
    from .tool_cache import ToolCache
except ImportError:
    from tool_cache import ToolCache  # type: ignore[no-redef]


@dataclass
class ToolCall:
    tool_name: str
    params: dict
    raw: str = ""


# ---------------------------------------------------------------------------
# Parsing helpers
# ---------------------------------------------------------------------------

_JSON_BLOCK_RE = re.compile(
    r"```json\s*(.*?)\s*```",
    re.DOTALL | re.IGNORECASE,
)
_XML_CALL_RE = re.compile(
    r"<tool_call>\s*(\{.*?\})\s*</tool_call>",
    re.DOTALL | re.IGNORECASE,
)
_FUNC_CALL_RE = re.compile(
    r"(?:TOOL_CALL|TOOL_CODE)\s*:\s*(\w+)\s*\(([^)]*)\)",
    re.IGNORECASE | re.DOTALL,
)


def _parse_func_params(params_str: str) -> dict:
    """Parse key=value pairs from a function-style call string."""
    params: dict = {}
    for match in re.finditer(r'(\w+)\s*=\s*(?:"([^"]*)"|\'([^\']*)\'|(\S+))', params_str):
        key = match.group(1)
        value = match.group(2) or match.group(3) or match.group(4) or ""
        params[key] = value
    return params


def extract_tool_calls(text: str) -> List[ToolCall]:
    """Parse tool calls from agent output in three supported formats."""
    calls: List[ToolCall] = []

    def _append_from_obj(obj: Any, raw: str) -> None:
        if isinstance(obj, dict):
            tool_name = obj.get("tool") or obj.get("tool_name") or obj.get("name") or ""
            params = obj.get("params") or obj.get("parameters") or obj.get("args") or {}
            if tool_name:
                calls.append(ToolCall(tool_name=tool_name, params=params, raw=raw))
        elif isinstance(obj, list):
            for item in obj:
                if isinstance(item, dict):
                    _append_from_obj(item, raw)

    # 1. JSON block format: ```json\n{"tool": "name", "params": {...}}\n```
    for m in _JSON_BLOCK_RE.finditer(text):
        raw = m.group(0)
        try:
            obj = json.loads(m.group(1))
            _append_from_obj(obj, raw)
        except (json.JSONDecodeError, TypeError):
            pass

    # 2. XML-style: <tool_call>{"tool": "name", "params": {...}}</tool_call>
    for m in _XML_CALL_RE.finditer(text):
        raw = m.group(0)
        try:
            obj = json.loads(m.group(1))
            _append_from_obj(obj, raw)
        except (json.JSONDecodeError, TypeError):
            pass

    # 3. Function call style: TOOL_CALL: tool_name(param1="val", param2="val")
    for m in _FUNC_CALL_RE.finditer(text):
        raw = m.group(0)
        tool_name = m.group(1)
        params = _parse_func_params(m.group(2))
        calls.append(ToolCall(tool_name=tool_name, params=params, raw=raw))

    return calls


# ---------------------------------------------------------------------------
# Executor
# ---------------------------------------------------------------------------

class ToolExecutor:
    """Load and execute tool implementations from tools/python/."""

    # Class-level lock: sys.path is a process-global list.  The brief window
    # where we insert a path, import the module, then remove the path must be
    # atomic across threads so that concurrent tool calls don't accidentally
    # remove each other's path entries.
    _sys_path_lock: threading.Lock = threading.Lock()
    _fs_mutation_lock: threading.Lock = threading.Lock()

    def __init__(self, tools_dir: Path, config: dict):
        self._tools_dir = Path(tools_dir)
        self._config = config
        self._tool_map: dict = {}
        self._runtime_context: dict[str, str] = {}
        self._task_root: Optional[Path] = None
        self._task_output_root: Optional[Path] = None
        self._policy_mode: str = (
            self._config.get("orchestration", {})
            .get("tool_path_policy", {})
            .get("mode", "enforce")
        )
        # Tools with filesystem side effects should not be served from cache.
        self._non_cacheable_tools: set[str] = {
            "run_shell_command",
            "write_file",
            "replace",
            "consciousness_tool",
            "task_manager",
        }
        # Serialize known mutating tools to reduce cross-job filesystem races.
        self._mutation_tools: set[str] = set(self._non_cacheable_tools)
        self._audit_ignored_files: set[Path] = {
            (_BASE_DIR / "workspace" / ".webui_jobs.json").resolve(),
            (_BASE_DIR / "workspace" / ".webui_prefs.json").resolve(),
            (_BASE_DIR / "workspace" / "session_index.json").resolve(),
        }
        self._build_tool_map()
        # Initialise the tool result cache using the orchestration.cache config block
        cache_cfg = config.get("orchestration", {}).get("cache", {})
        self._cache = ToolCache(config=cache_cfg, project_root=_BASE_DIR)

    def set_runtime_context(
        self,
        *,
        session_id: Optional[str] = None,
        task_dir: Optional[Path] = None,
    ) -> None:
        self._runtime_context = {}
        if session_id:
            self._runtime_context["OVERLORD11_SESSION_ID"] = session_id
        if task_dir:
            self._task_root = Path(task_dir).resolve()
            self._task_output_root = (self._task_root / "output").resolve()
            self._runtime_context["OVERLORD11_TASK_DIR"] = str(self._task_root)
            self._runtime_context["OVERLORD11_TASK_OUTPUT_DIR"] = str(self._task_output_root)
            self._runtime_context["OVERLORD11_REPO_ROOT"] = str(_BASE_DIR.resolve())
            self._cache.set_task_root(self._task_root)
        else:
            self._task_root = None
            self._task_output_root = None
            self._cache.set_task_root(None)

    @contextmanager
    def _runtime_env(self):
        original: dict[str, Optional[str]] = {}
        try:
            for key, value in self._runtime_context.items():
                original[key] = os.environ.get(key)
                os.environ[key] = value
            yield
        finally:
            for key in self._runtime_context:
                prior = original.get(key)
                if prior is None:
                    os.environ.pop(key, None)
                else:
                    os.environ[key] = prior

    def _build_tool_map(self) -> None:
        """Index available tools from config, resolving impl paths relative to project root."""
        for name, info in self._config.get("tools", {}).items():
            impl = info.get("impl", "")
            if impl:
                p = Path(impl)
                # If the path is relative, resolve it against the project root
                if not p.is_absolute():
                    p = _BASE_DIR / p
                self._tool_map[name] = p

    def _load_module(self, module_path: Path):
        """Dynamically import a Python module from a file path."""
        spec = importlib.util.spec_from_file_location(module_path.stem, module_path)
        if spec is None or spec.loader is None:
            raise ImportError(f"Cannot load module from {module_path}")
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)  # type: ignore[union-attr]
        return mod

    def execute(self, tool_call: ToolCall) -> dict:
        """
        Execute a tool call, returning a result dict.

        Before running the tool, the cache is consulted.  On a hit the
        stored result is returned immediately with `cached=True` and
        `duration_ms=0`.  On a miss the tool runs normally and a
        successful result is stored in the cache for future calls.
        """
        start = time.monotonic()
        tool_name = tool_call.tool_name
        self._normalize_params(tool_name, tool_call.params)
        policy_outcome = self._apply_path_policy(tool_name, tool_call.params)
        if policy_outcome is not None:
            return {
                "status": "error",
                "result": policy_outcome,
                "tool": tool_name,
                "duration_ms": 0.0,
            }

        # ── Cache lookup ────────────────────────────────────────────────
        if tool_name not in self._non_cacheable_tools:
            cached = self._cache.get(tool_name, tool_call.params)
            if cached is not None:
                return {
                    "status": "success",
                    "result": cached,
                    "tool": tool_name,
                    "duration_ms": 0.0,
                    "cached": True,
                    "cache_age_s": cached.get("cache_age_s"),
                }

        # Resolve the implementation path
        impl_path: Optional[Path] = self._tool_map.get(tool_name)
        if impl_path is None:
            # Try direct lookup in tools/python/
            candidate = self._tools_dir / f"{tool_name}.py"
            if candidate.exists():
                impl_path = candidate

        if impl_path is None or not impl_path.exists():
            return {
                "status": "error",
                "result": f"Tool '{tool_name}' not found",
                "tool": tool_name,
                "duration_ms": 0.0,
            }

        def _invoke() -> dict:
            # Strategy 1: import and call main()
            try:
                result = self._call_python_main(impl_path, tool_call.params)
                duration_ms = (time.monotonic() - start) * 1000
                if isinstance(result, dict):
                    inner_status = str(result.get("status", "")).lower()
                    if inner_status in {"error", "policy_violation"}:
                        return {
                            "status": "error",
                            "result": result,
                            "tool": tool_name,
                            "duration_ms": round(duration_ms, 2),
                        }
                return {
                    "status": "success",
                    "result": result,
                    "tool": tool_name,
                    "duration_ms": round(duration_ms, 2),
                }
            except Exception:
                pass  # Fall through to subprocess strategy

            # Strategy 2: subprocess with JSON params
            try:
                result = self._call_subprocess(impl_path, tool_call.params)
                duration_ms = (time.monotonic() - start) * 1000
                return {
                    "status": "success",
                    "result": result,
                    "tool": tool_name,
                    "duration_ms": round(duration_ms, 2),
                }
            except Exception as sub_err:
                duration_ms = (time.monotonic() - start) * 1000
                return {
                    "status": "error",
                    "result": str(sub_err),
                    "tool": tool_name,
                    "duration_ms": round(duration_ms, 2),
                }

        if tool_name == "run_shell_command" and self._policy_mode == "enforce" and self._task_root is not None:
            with ToolExecutor._fs_mutation_lock:
                before = self._snapshot_filesystem_state()
                outcome = _invoke()
                after = self._snapshot_filesystem_state()
                violation = self._audit_shell_write_violation(before, after)
                if violation is not None:
                    return {
                        "status": "error",
                        "result": {
                            **violation,
                            "shell_result": outcome.get("result"),
                        },
                        "tool": tool_name,
                        "duration_ms": outcome.get("duration_ms", 0.0),
                    }
        elif tool_name in self._mutation_tools:
            with ToolExecutor._fs_mutation_lock:
                outcome = _invoke()
        else:
            outcome = _invoke()

        if outcome.get("status") == "success" and tool_name not in self._non_cacheable_tools:
            self._cache.put(tool_name, tool_call.params, outcome)
        return outcome

    def _normalize_params(self, tool_name: str, params: dict) -> None:
        """Best-effort alias normalization to reduce brittle tool-call failures."""
        if not isinstance(params, dict):
            return

        def _move(src: str, dst: str) -> None:
            if src in params and dst not in params:
                params[dst] = params.pop(src)

        if tool_name == "replace":
            _move("search", "old_str")
            _move("replace", "new_str")
            _move("old", "old_str")
            _move("new", "new_str")

        elif tool_name == "write_file":
            _move("text", "content")
            _move("body", "content")

        elif tool_name == "run_shell_command":
            _move("cmd", "command")
            _move("directory", "working_dir")
            _move("cwd", "working_dir")
            _move("path", "working_dir")
            if "shell_preference" not in params:
                params["shell_preference"] = "powershell" if os.name == "nt" else "bash"
            if "reject_on_shell_mismatch" not in params:
                params["reject_on_shell_mismatch"] = True
            if "auto_switch_shell" not in params:
                params["auto_switch_shell"] = True

        elif tool_name == "task_manager":
            _move("task_dir", "project_dir")
            if "project_dir" not in params and self._task_root is not None:
                params["project_dir"] = str(self._task_root)
            if "action" in params and isinstance(params["action"], str):
                action = params["action"].strip().lower()
                action_alias = {
                    "complete": "complete_task",
                    "add": "add_task",
                    "list": "query",
                    "status": "update_status",
                }
                params["action"] = action_alias.get(action, action)
            if "status" in params and isinstance(params["status"], str):
                status = params["status"].strip().lower()
                status_alias = {
                    "started": "in_progress",
                    "done": "completed",
                    "complete": "completed",
                    "inprogress": "in_progress",
                }
                params["status"] = status_alias.get(status, status)

    def _resolve_under(self, base: Path, target: str) -> Path:
        p = Path(target)
        if p.is_absolute():
            return p.resolve()
        return (base / p).resolve()

    def _ensure_within(self, target: Path, base: Path) -> bool:
        try:
            target.relative_to(base.resolve())
            return True
        except ValueError:
            return False

    def _deny(self, reason: str, **extra: Any) -> dict:
        reason_messages = {
            "memory_path_not_allowlisted": (
                "Memory writes are restricted to canonical persistent memory files.",
                "Use Consciousness.md or Memory.md through consciousness_tool.",
            ),
            "write_outside_task_root": (
                "Write target resolves outside the active task workspace.",
                "Use a relative path under ./output for generated files.",
            ),
            "write_to_blocked_control_plane_path": (
                "Direct writes to control-plane files are blocked in enforce mode.",
                "Persist user deliverables in the task workspace/output directory.",
            ),
            "shell_workdir_outside_task_root": (
                "Shell working directory resolves outside task workspace.",
                "Run shell commands in the task workspace (default) or a subdirectory within it.",
            ),
            "shell_parent_traversal_blocked": (
                "Parent traversal is blocked for shell commands in enforce mode.",
                "Use explicit relative paths that stay inside the task workspace.",
            ),
            "shell_control_plane_target_blocked": (
                "Shell command references blocked control-plane paths.",
                "Avoid touching config/runtime files; operate only inside task workspace output.",
            ),
            "shell_write_outside_task_root": (
                "Shell command changed files outside task workspace (detected by audit).",
                "Restrict command targets to paths under the active task workspace.",
            ),
        }
        message, hint = reason_messages.get(
            reason,
            ("Tool policy enforcement blocked this operation.", "Review tool parameters and workspace-relative paths."),
        )
        out = {
            "status": "policy_violation",
            "reason": reason,
            "message": message,
            "hint": hint,
        }
        out.update(extra)
        return out

    def _snapshot_filesystem_state(self) -> dict[str, tuple[int, int]]:
        """
        Snapshot file size+mtime for the repository tree.

        This powers post-shell write auditing.  We exclude known volatile
        metadata files that may change due to unrelated API activity.
        """
        root = _BASE_DIR.resolve()
        snapshot: dict[str, tuple[int, int]] = {}
        for dirpath, dirnames, filenames in os.walk(root):
            current = Path(dirpath)
            # Prune expensive/irrelevant paths early.
            dirnames[:] = [
                d for d in dirnames
                if d not in {".git", "__pycache__", ".pytest_cache"}
            ]
            for filename in filenames:
                path = (current / filename).resolve()
                if path in self._audit_ignored_files:
                    continue
                try:
                    stat = path.stat()
                except OSError:
                    continue
                snapshot[str(path)] = (stat.st_mtime_ns, stat.st_size)
        return snapshot

    def _audit_shell_write_violation(
        self,
        before: dict[str, tuple[int, int]],
        after: dict[str, tuple[int, int]],
    ) -> Optional[dict]:
        if self._task_root is None:
            return None

        changed_paths: list[Path] = []
        all_keys = set(before.keys()) | set(after.keys())
        for key in all_keys:
            if before.get(key) != after.get(key):
                changed_paths.append(Path(key))

        outside = [
            str(p)
            for p in changed_paths
            if not self._ensure_within(p, self._task_root)
        ]
        if not outside:
            return None

        preview = sorted(outside)[:25]
        return self._deny(
            "shell_write_outside_task_root",
            task_root=str(self._task_root),
            changed_path_count=len(outside),
            changed_paths=preview,
        )

    def _apply_path_policy(self, tool_name: str, params: dict) -> Optional[dict]:
        if self._policy_mode != "enforce":
            return None
        if not isinstance(params, dict):
            return None
        if self._task_root is None or self._task_output_root is None:
            return None

        read_tools = {"read_file", "list_directory", "glob", "search_file_content"}
        write_tools = {"write_file", "replace"}
        memory_tools = {"consciousness_tool"}

        if tool_name in memory_tools:
            # Enforce canonical persistent memory path
            if "file" in params and params["file"]:
                resolved = self._resolve_under(self._task_root, str(params["file"]))
                if resolved != _CANONICAL_CONSCIOUSNESS and resolved != _CANONICAL_MEMORY:
                    return self._deny(
                        "memory_path_not_allowlisted",
                        path=str(resolved),
                        allowed=[str(_CANONICAL_CONSCIOUSNESS), str(_CANONICAL_MEMORY)],
                    )
            return None

        if tool_name in read_tools:
            if "path" in params and isinstance(params["path"], str):
                params["path"] = str(self._resolve_under(self._task_root, params["path"]))
            return None

        if tool_name in write_tools:
            key = "path"
            if key in params and isinstance(params[key], str):
                resolved = self._resolve_under(self._task_output_root, params[key])
                if not self._ensure_within(resolved, self._task_root):
                    return self._deny(
                        "write_outside_task_root",
                        path=str(resolved),
                        task_root=str(self._task_root),
                    )
                # Block direct control-plane writes in normal mode
                blocked = {
                    (_BASE_DIR / "config.json").resolve(),
                    (_BASE_DIR / "Consciousness.md").resolve(),
                    (_BASE_DIR / "Memory.md").resolve(),
                }
                if resolved in blocked:
                    return self._deny("write_to_blocked_control_plane_path", path=str(resolved))
                params[key] = str(resolved)
            return None

        if tool_name == "run_shell_command":
            # Force execution in task output dir unless caller requests a dir under task root.
            requested_dir = params.get("dir_path") or params.get("working_dir") or "."
            resolved_dir = self._resolve_under(self._task_output_root, str(requested_dir))
            if not self._ensure_within(resolved_dir, self._task_root):
                return self._deny(
                    "shell_workdir_outside_task_root",
                    directory=str(resolved_dir),
                    task_root=str(self._task_root),
                )
            command = str(params.get("command", ""))
            # Parent traversal + control-plane path references are disallowed in normal mode.
            if re.search(r"(^|[\\/\s])\.\.([\\/\s]|$)", command):
                return self._deny("shell_parent_traversal_blocked", command=command)
            if str((_BASE_DIR / "config.json").resolve()) in command.replace("/", "\\"):
                return self._deny("shell_control_plane_target_blocked", command=command)
            params["working_dir"] = str(resolved_dir)
            params["dir_path"] = str(resolved_dir)
            return None

        return None

    def _call_python_main(self, impl_path: Path, params: dict) -> Any:
        """
        Import the module and call its main() function.

        sys.path mutation is protected by the class-level _sys_path_lock so
        that concurrent parallel tool threads cannot interfere with each
        other's temporary path entries.  The lock is released as soon as the
        module object is loaded; actual main() execution is single-threaded
        per tool call and needs no further synchronization.
        """
        tools_python = str(impl_path.parent)
        with ToolExecutor._sys_path_lock:
            injected = tools_python not in sys.path
            if injected:
                sys.path.insert(0, tools_python)
            try:
                mod = self._load_module(impl_path)
            finally:
                if injected and tools_python in sys.path:
                    sys.path.remove(tools_python)

        if not hasattr(mod, "main"):
            raise AttributeError(f"No main() in {impl_path.name}")
        try:
            with self._runtime_env():
                return mod.main(**params)
        except SystemExit as exc:
            code = exc.code if isinstance(exc.code, int) else 1
            raise RuntimeError(f"Tool exited via SystemExit(code={code})") from exc

    def _call_subprocess(self, impl_path: Path, params: dict) -> str:
        """Run the tool as a subprocess, passing params as --key value args."""
        cmd = [sys.executable, str(impl_path)]
        for key, value in params.items():
            # Always serialize values as JSON strings to prevent injection
            serialized = value if isinstance(value, str) else json.dumps(value, ensure_ascii=False)
            cmd += [f"--{key}", serialized]
        env = os.environ.copy()
        env.update(self._runtime_context)
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            encoding="utf-8",
            timeout=120,
            env=env,
        )
        if result.returncode != 0:
            # Prefer stderr for the error message; fall back to stdout if empty.
            err_msg = result.stderr.strip() or result.stdout.strip() or f"exit code {result.returncode}"
            raise RuntimeError(err_msg)
        return result.stdout.strip()
