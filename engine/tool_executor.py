"""
Overlord11 Engine - Tool Executor
====================================
Tool call detection and execution for the engine loop.
"""

import importlib.util
import fnmatch
import inspect
import json
import os
import re
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from contextlib import contextmanager
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, List, Optional

from pydantic import BaseModel, ConfigDict, ValidationError, create_model

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


@dataclass
class ToolContract:
    """Resolved runtime contract for one tool."""

    tool_name: str
    params_model: type[BaseModel]
    invoke: Callable[[dict, dict], Any]
    source: str = "module"


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
    _FUNCTION_ADAPTERS: dict[str, str] = {
        "calculator": "calculator",
        "cleanup_tool": "full_scan",
        "code_analyzer": "analyze_code",
        "computer_control": "mouse_move",
        "consciousness_tool": "read_all",
        "data_visualizer": "data_visualizer",
        "database_tool": "database_tool",
        "datetime_tool": "datetime_tool",
        "delegate_task": "main",
        "diff_tool": "diff_tool",
        "env_tool": "env_tool",
        "error_handler": "analyze",
        "error_logger": "query_errors",
        "execute_python": "main",
        "file_converter": "convert",
        "git_tool": "git_tool",
        "glob": "glob_tool",
        "hash_tool": "hash_tool",
        "http_request": "http_request",
        "json_tool": "json_tool",
        "launcher_generator": "generate_launcher",
        "list_directory": "list_directory",
        "log_manager": "query_logs",
        "notification_tool": "main",
        "project_docs_init": "init_all",
        "project_scanner": "scan_project",
        "publisher_tool": "generate_report",
        "read_file": "read_file",
        "regex_tool": "regex_tool",
        "replace": "replace_in_file",
        "response_formatter": "auto",
        "run_shell_command": "main",
        "sandbox_runner": "main",
        "save_memory": "save_memory",
        "scaffold_generator": "generate_scaffold",
        "search_file_content": "main",
        "session_clean": "main",
        "session_manager": "main",
        "task_manager": "main",
        "ui_design_system": "main",
        "vision_tool": "analyze_image",
        "web_fetch": "web_fetch",
        "web_scraper": "fetch_page",
        "write_file": "write_file",
        "zip_tool": "zip_tool",
    }
    _CURATED_ALIAS_MAP: dict[str, dict[str, str]] = {
        "replace": {"search": "old_str", "replace": "new_str", "old": "old_str", "new": "new_str"},
        "write_file": {"text": "content", "body": "content"},
        "run_shell_command": {"cmd": "command", "directory": "working_dir", "cwd": "working_dir", "path": "working_dir"},
        "task_manager": {"task_dir": "project_dir"},
        "session_manager": {"summary": "description"},
        "save_memory": {"content": "value", "text": "value", "body": "value", "name": "key", "title": "key", "file": "target_file", "path": "target_file"},
        "zip_tool": {"zip_path": "file", "archive_path": "file", "output_path": "output", "source_path": "paths"},
    }
    _FORBIDDEN_ALIASES: dict[str, set[str]] = {
        "zip_tool": {"src", "source", "zip", "archive"},
        "task_manager": {"subtasks"},
    }

    def __init__(self, tools_dir: Path, config: dict):
        self._tools_dir = Path(tools_dir)
        self._config = config
        self._tool_map: dict = {}
        self._tool_contracts: dict[str, ToolContract] = {}
        self._runtime_context: dict[str, str] = {}
        self._task_root: Optional[Path] = None
        self._task_output_root: Optional[Path] = None
        tools_cfg = self._config.get("orchestration", {}).get("tools", {})
        self._execution_mode = str(tools_cfg.get("execution_mode", "python_only")).strip().lower()
        self._require_execute_contract = bool(tools_cfg.get("require_execute_contract", True))
        self._strict_param_validation = bool(tools_cfg.get("strict_param_validation", True))
        self._alias_policy = str(tools_cfg.get("alias_policy", "curated_strict")).strip().lower()
        self._policy_mode: str = (
            self._config.get("orchestration", {})
            .get("tool_path_policy", {})
            .get("mode", "enforce")
        )
        shell_policy_cfg = self._config.get("orchestration", {}).get("shell_policy", {})
        self._verification_outside_write_allowlist: list[str] = [
            str(p).replace("\\", "/").strip().lstrip("./")
            for p in shell_policy_cfg.get("verification_outside_write_allowlist", ["workspace/**", "logs/**"])
            if str(p).strip()
        ]
        self._shell_block_tracked_repo_writes: bool = bool(
            shell_policy_cfg.get("block_tracked_repo_writes", True)
        )
        # Tools with filesystem side effects should not be served from cache.
        self._non_cacheable_tools: set[str] = {
            "run_shell_command",
            "write_file",
            "replace",
            "consciousness_tool",
            "task_manager",
            "session_manager",
            "save_memory",
            "log_manager",
            # Conservative disable for workspace/filesystem-sensitive reads/artifacts.
            "zip_tool",
            "publisher_tool",
            "read_file",
            "list_directory",
            "glob",
            "search_file_content",
        }
        # Serialize known mutating tools to reduce cross-job filesystem races.
        self._mutation_tools: set[str] = set(self._non_cacheable_tools)
        self._audit_ignored_files: set[Path] = {
            (_BASE_DIR / "workspace" / ".webui_jobs.json").resolve(),
            (_BASE_DIR / "workspace" / ".webui_prefs.json").resolve(),
            (_BASE_DIR / "workspace" / "session_index.json").resolve(),
        }
        self._protected_control_plane_paths: set[Path] = {
            (_BASE_DIR / "config.json").resolve(),
            (_BASE_DIR / "Consciousness.md").resolve(),
            (_BASE_DIR / "Memory.md").resolve(),
        }
        self._immutable_patterns_default: list[str] = [
            str(p).replace("\\", "/").lower().strip()
            for p in (
                self._config.get("orchestration", {})
                .get("delegation", {})
                .get("immutable_core_paths", [])
            )
            if str(p).strip()
        ]
        self._build_tool_map()
        self._build_tool_contracts()
        self._delegation_handler: Optional[Callable[..., dict]] = None
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

    def set_delegation_handler(self, handler: Optional[Callable[..., dict]]) -> None:
        self._delegation_handler = handler

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

    def _build_tool_contracts(self) -> None:
        """Resolve runtime execute contracts for all configured tools."""
        errors: list[str] = []
        self._tool_contracts = {}
        for tool_name in sorted(self._tool_map.keys()):
            impl_path = self._tool_map.get(tool_name)
            if impl_path is None or not impl_path.exists():
                errors.append(f"{tool_name}: implementation file missing")
                continue
            try:
                contract = self._resolve_contract(tool_name, impl_path)
                self._tool_contracts[tool_name] = contract
            except Exception as exc:
                errors.append(f"{tool_name}: {exc}")
        if self._require_execute_contract and errors:
            msg = "Tool contract validation failed:\n- " + "\n- ".join(errors)
            raise RuntimeError(msg)

    def _resolve_contract(self, tool_name: str, impl_path: Path) -> ToolContract:
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

        params_model: Optional[type[BaseModel]] = None
        model_candidate = getattr(mod, "ParamsModel", None)
        if inspect.isclass(model_candidate) and issubclass(model_candidate, BaseModel):
            params_model = model_candidate
        if params_model is None:
            params_model = self._build_params_model_from_def(tool_name)

        execute_fn = getattr(mod, "execute", None)
        if callable(execute_fn):
            def _invoke(params: dict, context: dict) -> Any:
                return self._invoke_execute_fn(execute_fn, params, context)

            return ToolContract(tool_name=tool_name, params_model=params_model, invoke=_invoke, source="module.execute")

        adapter = self._build_adapter_for_module(tool_name, mod)
        if adapter is None:
            raise RuntimeError("missing execute() and no supported adapter")
        return ToolContract(tool_name=tool_name, params_model=params_model, invoke=adapter, source="executor.adapter")

    def _build_params_model_from_def(self, tool_name: str) -> type[BaseModel]:
        info = (self._config.get("tools", {}) or {}).get(tool_name, {})
        def_rel = info.get("def")
        if not def_rel:
            raise RuntimeError("missing def path for ParamsModel synthesis")
        def_path = Path(def_rel)
        if not def_path.is_absolute():
            def_path = (_BASE_DIR / def_path).resolve()
        if not def_path.exists():
            raise RuntimeError(f"def file not found: {def_path}")
        schema = json.loads(def_path.read_text(encoding="utf-8"))
        params = (schema.get("parameters") or {})
        props = params.get("properties") or {}
        required = set(params.get("required") or [])
        fields: dict[str, tuple[Any, Any]] = {}
        for key, meta in props.items():
            typ = self._json_schema_type_to_python(meta or {})
            default: Any = ... if key in required else None
            fields[str(key)] = (typ, default)
        model = create_model(  # type: ignore[call-overload]
            f"{tool_name.title().replace('_', '')}ParamsModel",
            __config__=ConfigDict(extra="forbid"),
            **fields,
        )
        return model

    def _json_schema_type_to_python(self, meta: dict) -> Any:
        t = meta.get("type")
        enum_vals = meta.get("enum")
        if isinstance(enum_vals, list) and enum_vals:
            return str
        if t == "string":
            return str
        if t == "boolean":
            return bool
        if t == "integer":
            return int
        if t == "number":
            return float
        if t == "array":
            return list[Any]
        if t == "object":
            return dict[str, Any]
        return Any

    def _invoke_execute_fn(self, execute_fn: Callable[..., Any], params: dict, context: dict) -> Any:
        sig = inspect.signature(execute_fn)
        kw = {name: p for name, p in sig.parameters.items() if p.kind in {inspect.Parameter.POSITIONAL_OR_KEYWORD, inspect.Parameter.KEYWORD_ONLY}}
        if any(p.kind == inspect.Parameter.VAR_KEYWORD for p in sig.parameters.values()):
            return execute_fn(params=params, context=context)
        if "params" in kw and "context" in kw:
            return execute_fn(params=params, context=context)
        if "params" in kw:
            return execute_fn(params=params)
        if "context" in kw:
            return execute_fn(context=context)
        if len(kw) == 2:
            names = list(kw.keys())
            return execute_fn(**{names[0]: params, names[1]: context})
        if len(kw) == 1:
            only = next(iter(kw))
            return execute_fn(**{only: params})
        return execute_fn(params, context)

    def _load_module(self, module_path: Path):
        """Dynamically import a Python module from a file path."""
        spec = importlib.util.spec_from_file_location(module_path.stem, module_path)
        if spec is None or spec.loader is None:
            raise ImportError(f"Cannot load module from {module_path}")
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)  # type: ignore[union-attr]
        return mod

    def _build_adapter_for_module(self, tool_name: str, mod: Any) -> Optional[Callable[[dict, dict], Any]]:
        # Special action dispatchers where module functions are not kwargs-friendly.
        if tool_name == "task_manager":
            return lambda params, _ctx: self._invoke_task_manager_module(mod, params)
        if tool_name == "session_manager":
            return lambda params, _ctx: self._invoke_session_manager_module(mod, params)
        if tool_name == "computer_control":
            return lambda params, _ctx: self._invoke_computer_control_module(mod, params)
        if tool_name == "consciousness_tool":
            return lambda params, _ctx: self._invoke_consciousness_module(mod, params)
        if tool_name == "error_handler":
            return lambda params, _ctx: self._invoke_error_handler_module(mod, params)
        if tool_name == "error_logger":
            return lambda params, _ctx: self._invoke_error_logger_module(mod, params)
        if tool_name == "file_converter":
            return lambda params, _ctx: self._invoke_file_converter_module(mod, params)
        if tool_name == "log_manager":
            return lambda params, _ctx: self._invoke_log_manager_module(mod, params)
        if tool_name == "response_formatter":
            return lambda params, _ctx: self._invoke_response_formatter_module(mod, params)
        if tool_name == "vision_tool":
            return lambda params, _ctx: self._invoke_vision_module(mod, params)
        if tool_name == "web_scraper":
            return lambda params, _ctx: self._invoke_web_scraper_module(mod, params)

        fn_name = self._FUNCTION_ADAPTERS.get(tool_name, tool_name)
        fn = getattr(mod, fn_name, None)
        if not callable(fn):
            return None
        return lambda params, _ctx: self._invoke_callable_with_params(fn, params, tool_name=tool_name)

    def _invoke_callable_with_params(self, fn: Callable[..., Any], params: dict, *, tool_name: str) -> Any:
        if not callable(fn):
            raise RuntimeError(f"{tool_name}: adapter target is not callable")
        try:
            sig = inspect.signature(fn)
        except Exception:
            with self._runtime_env():
                return fn(**params)
        if any(p.kind == inspect.Parameter.VAR_KEYWORD for p in sig.parameters.values()):
            with self._runtime_env():
                return fn(**params)
        accepted = {
            p.name
            for p in sig.parameters.values()
            if p.kind in {inspect.Parameter.POSITIONAL_OR_KEYWORD, inspect.Parameter.KEYWORD_ONLY}
        }
        filtered = {k: v for k, v in params.items() if k in accepted}
        missing_required = [
            p.name for p in sig.parameters.values()
            if p.kind in {inspect.Parameter.POSITIONAL_OR_KEYWORD, inspect.Parameter.KEYWORD_ONLY}
            and p.default is inspect._empty
            and p.name not in filtered
        ]
        if missing_required:
            raise RuntimeError(
                f"{tool_name}: missing required adapter parameters: {', '.join(sorted(missing_required))}"
            )
        with self._runtime_env():
            result = fn(**filtered)
        # Normalize historical wrappers that return no explicit status.
        if isinstance(result, dict) and "status" not in result:
            result = {"status": "success", **result}
        return result

    def _invoke_task_manager_module(self, mod: Any, params: dict) -> Any:
        action = str(params.get("action", "")).strip().lower()
        project_dir = (
            params.get("project_dir")
            or params.get("task_dir")
            or (str(self._task_root) if self._task_root is not None else "")
        )
        if not project_dir:
            raise RuntimeError("task_manager: project_dir is required")
        if action == "init":
            return mod.init_log(project_dir)
        if action == "add_task":
            return mod.add_task(project_dir, params.get("title", ""), params.get("description", ""), params.get("priority", "medium"), params.get("assigned_agent", ""))
        if action == "add_subtask":
            return mod.add_subtask(project_dir, params.get("task_id"), params.get("title", ""), params.get("description", ""))
        if action == "complete_task":
            return mod.complete_task(project_dir, params.get("task_id"), params.get("note", ""))
        if action == "complete_subtask":
            return mod.complete_subtask(project_dir, params.get("subtask_id"))
        if action == "update_status":
            return mod.update_status(project_dir, params.get("task_id"), params.get("status", "pending"), params.get("note", ""))
        if action == "query":
            return mod.query_tasks(project_dir)
        raise RuntimeError(f"task_manager: unsupported action '{action}'")

    def _invoke_session_manager_module(self, mod: Any, params: dict) -> Any:
        action = str(params.get("action", "")).strip().lower()
        session_id = params.get("session_id")
        data = params.get("data") if isinstance(params.get("data"), dict) else {}
        if action == "create":
            return mod.create_session(
                description=params.get("description", "") or data.get("description", ""),
                tags=data.get("tags", []),
                job_id=params.get("job_id", "") or data.get("job_id", ""),
            )
        if action == "status":
            return mod.get_session(session_id)
        if action == "log_change":
            return mod.log_change(
                session_id=session_id,
                file_path=data.get("file", ""),
                action=data.get("action", "modified"),
                summary=data.get("summary", ""),
                diff_preview=data.get("diff_preview"),
            )
        if action == "log_agent":
            return mod.log_agent_usage(session_id, data.get("agent_id", ""))
        if action == "log_tool":
            return mod.log_tool_usage(session_id, data.get("tool_name", ""))
        if action == "add_note":
            return mod.add_note(session_id, data.get("note", ""))
        if action == "close":
            return mod.close_session(session_id=session_id, summary=data.get("summary", params.get("description", "")))
        if action == "list":
            return mod.list_sessions(status=params.get("status_filter"))
        if action == "active":
            return mod.get_active_session()
        raise RuntimeError(f"session_manager: unsupported action '{action}'")

    def _invoke_computer_control_module(self, mod: Any, params: dict) -> Any:
        action = str(params.get("action", "")).strip().lower()
        if action == "get_screen_size":
            return mod.get_screen_size()
        if action == "get_mouse_pos":
            return mod.get_mouse_pos()
        if action == "mouse_move":
            return mod.mouse_move(params.get("x"), params.get("y"), params.get("duration", 0.2), bool(params.get("relative", False)))
        if action == "mouse_click":
            return mod.mouse_click(params.get("x"), params.get("y"), params.get("button", "left"), int(params.get("clicks", 1)), float(params.get("interval", 0.05)))
        if action == "mouse_scroll":
            return mod.mouse_scroll(int(params.get("amount", 3)), params.get("direction", "up"), params.get("x"), params.get("y"))
        if action == "key_press":
            return mod.key_press(params.get("keys", ""), int(params.get("presses", 1)), float(params.get("interval", 0.05)))
        if action == "hotkey":
            keys = params.get("keys", "")
            if isinstance(keys, str):
                return mod.hotkey(*[k.strip() for k in keys.split(",") if k.strip()])
            if isinstance(keys, list):
                return mod.hotkey(*[str(k) for k in keys if str(k).strip()])
        if action == "type_text":
            return mod.type_text(params.get("text", ""), float(params.get("interval", 0.05)))
        if action == "clipboard_get":
            return mod.clipboard_get()
        if action == "clipboard_set":
            return mod.clipboard_set(params.get("text", ""))
        raise RuntimeError(f"computer_control: unsupported action '{action}'")

    def _invoke_consciousness_module(self, mod: Any, params: dict) -> Any:
        action = str(params.get("action", "")).strip().lower()
        file_path = Path(params["file"]) if isinstance(params.get("file"), str) and params.get("file") else None
        if action == "read_all":
            return mod.read_all(file_path)
        if action == "read_section":
            return mod.read_section(params.get("section", ""), file_path)
        if action == "search":
            return mod.search(params.get("query", ""), file_path, int(params.get("max_results", 20)))
        if action == "search_index":
            return mod.search_index(file_path)
        if action == "commit":
            return mod.commit(
                key=params.get("key", ""),
                value=params.get("value", ""),
                priority=params.get("priority", "NORMAL"),
                ttl=params.get("ttl", "7d"),
                category=params.get("category", "context"),
                source=params.get("source", "AGENT"),
                file_path=file_path,
            )
        if action == "cleanup":
            return mod.cleanup(file_path, dry_run=bool(params.get("dry_run", False)))
        if action == "ttl_stats":
            return mod.ttl_stats(file_path)
        raise RuntimeError(f"consciousness_tool: unsupported action '{action}'")

    def _invoke_error_handler_module(self, mod: Any, params: dict) -> Any:
        action = str(params.get("action", "")).strip().lower()
        if action == "analyze":
            return mod.analyze(params.get("error_text", ""), params.get("context", ""), params.get("session_id"))
        if action == "search_error":
            return mod.search_error(params.get("error_text", ""), params.get("language", "python"))
        if action == "self_correct":
            return mod.self_correct(params.get("error_text", ""), params.get("attempted_fix", ""), params.get("session_id"))
        if action == "summarize":
            return mod.summarize(params.get("error_text", ""), params.get("context", ""))
        raise RuntimeError(f"error_handler: unsupported action '{action}'")

    def _invoke_error_logger_module(self, mod: Any, params: dict) -> Any:
        action = str(params.get("action", "")).strip().lower()
        project_dir = params.get("project_dir") or (str(self._task_root) if self._task_root is not None else ".")
        if action == "init":
            return mod.init_log(project_dir)
        if action == "log_error":
            return mod.log_error(project_dir, params.get("title", ""), params.get("description", ""), params.get("severity", "medium"), params.get("source", "agent"))
        if action == "add_attempt":
            return mod.add_attempt(project_dir, params.get("error_id", ""), params.get("attempt", ""))
        if action == "resolve_error":
            return mod.resolve_error(project_dir, params.get("error_id", ""), params.get("resolution", ""))
        if action == "query":
            return mod.query_errors(project_dir, params.get("status"), params.get("severity"))
        raise RuntimeError(f"error_logger: unsupported action '{action}'")

    def _invoke_file_converter_module(self, mod: Any, params: dict) -> Any:
        action = str(params.get("action", "")).strip().lower()
        if action == "list_formats":
            return mod.list_formats()
        if action == "detect":
            return mod.detect_format(params.get("input"))
        if action == "convert":
            return mod.convert(
                input_path=params.get("input"),
                output_path=params.get("output"),
                from_format=params.get("from_format"),
                to_format=params.get("to_format"),
                title=params.get("title", "Document"),
            )
        raise RuntimeError(f"file_converter: unsupported action '{action}'")

    def _invoke_log_manager_module(self, mod: Any, params: dict) -> Any:
        action = str(params.get("action", "")).strip().lower()
        data = params.get("data") if isinstance(params.get("data"), dict) else {}
        session_id = params.get("session_id") or "unset"
        if action == "log_tool":
            return mod.log_tool_invocation(session_id, data.get("tool", "unknown"), data.get("params", {}), data.get("result", {}), data.get("duration_ms"))
        if action == "log_decision":
            return mod.log_llm_decision(session_id, data.get("agent", "unknown"), data.get("decision", ""), data.get("reasoning"), data.get("context"))
        if action == "log_agent_switch":
            return mod.log_agent_switch(session_id, data.get("from", "none"), data.get("to", "unknown"), data.get("reason", ""))
        if action == "log_error":
            return mod.log_error(session_id, data.get("source", "unknown"), data.get("error", ""), data.get("traceback"))
        if action == "log_event":
            return mod.log_event(session_id, data.get("event_type", "generic"), data)
        if action == "query":
            return mod.query_logs(session_id=params.get("session_id"), log_type=params.get("type_filter"), last_n=int(params.get("last_n", 50)))
        if action == "summary":
            return mod.session_summary(params.get("session_id", ""))
        if action == "list_sessions":
            return mod.list_sessions()
        raise RuntimeError(f"log_manager: unsupported action '{action}'")

    def _invoke_response_formatter_module(self, mod: Any, params: dict) -> Any:
        action = str(params.get("action", "")).strip().lower()
        if action == "decide":
            return mod.decide(params.get("request", ""), params.get("content", ""), params.get("context", ""))
        if action == "format":
            return mod.format_content(params.get("content", ""), params.get("format_type", "markdown"), params.get("title", "Report"))
        if action == "auto":
            return mod.auto(params.get("request", ""), params.get("content", ""), params.get("context", ""), params.get("title", "Report"))
        raise RuntimeError(f"response_formatter: unsupported action '{action}'")

    def _invoke_vision_module(self, mod: Any, params: dict) -> Any:
        action = str(params.get("action", "")).strip().lower()
        if action == "screenshot":
            return mod.screenshot(output=params.get("output"), region=params.get("region"), format=params.get("format", "png"))
        if action == "analyze_image":
            return mod.analyze_image(params.get("image"), include_b64=not bool(params.get("no_b64", False)))
        if action == "ocr":
            return mod.ocr(params.get("image"))
        if action == "list_images":
            return mod.list_images(params.get("directory"), recursive=bool(params.get("recursive", False)))
        if action == "compare_images":
            return mod.compare_images(params.get("image"), params.get("image2"))
        raise RuntimeError(f"vision_tool: unsupported action '{action}'")

    def _invoke_web_scraper_module(self, mod: Any, params: dict) -> Any:
        action = str(params.get("action", "")).strip().lower()
        dispatch = getattr(mod, "ACTION_DISPATCH", {})
        if action not in dispatch:
            raise RuntimeError(f"web_scraper: unsupported action '{action}'")
        fn = dispatch[action]
        kwargs = {
            "url": params.get("url"),
            "query": params.get("query"),
            "output_dir": params.get("output_dir"),
            "extract_mode": params.get("extract_mode"),
            "wait_for_js": bool(params.get("wait_for_js", True)),
            "wait_timeout": int(params.get("wait_timeout", 15)),
            "download_imgs": bool(params.get("download_images", True)),
            "max_images": int(params.get("max_images", 20)),
            "max_results": int(params.get("max_results", 10)),
            "max_entries": int(params.get("max_entries", 20)),
            "clean_text": bool(params.get("clean_text", True)),
            "do_summarize": bool(params.get("summarize", True)),
            "max_summary_length": int(params.get("max_summary_length", 220)),
            "min_size": int(params.get("min_image_size", 5120)),
            "smart": bool(params.get("smart_images", False)),
            "min_score": float(params.get("min_image_score", 0.4)),
            "analysis_goal": params.get("analysis_goal", ""),
        }
        kwargs = {k: v for k, v in kwargs.items() if v is not None}
        return fn(**kwargs)

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
        if self._execution_mode != "python_only":
            return {
                "status": "error",
                "result": {
                    "status": "error",
                    "error": "invalid_execution_mode",
                    "hint": "Only orchestration.tools.execution_mode=python_only is supported.",
                },
                "tool": tool_name,
                "duration_ms": 0.0,
                "validation_stage": "rejected",
                "param_error_code": "invalid_execution_mode",
            }
        normalized_params = dict(tool_call.params) if isinstance(tool_call.params, dict) else tool_call.params
        corrections = self._normalize_params(tool_name, normalized_params if isinstance(normalized_params, dict) else {})
        preflight_error, validated_params = self._preflight_params(tool_name, normalized_params, corrections)
        if preflight_error is not None:
            return {
                "status": "error",
                "result": preflight_error,
                "tool": tool_name,
                "duration_ms": 0.0,
                "validation_stage": "rejected",
                "param_error_code": preflight_error.get("reason", "param_preflight_failed"),
                "corrections": preflight_error.get("corrections", []),
                "suggested_payload": preflight_error.get("suggested_payload"),
                "failure_signature": f"{tool_name}:{preflight_error.get('reason', 'param_preflight_failed')}",
                "invocation_mode": "direct_python",
                "serialization_mode": "python_only_contract",
            }
        if isinstance(validated_params, dict):
            tool_call.params = validated_params
        if tool_name in {"delegate_task", "run_subagent"}:
            return self._execute_delegation(tool_call)
        policy_outcome = self._apply_path_policy(tool_name, tool_call.params if isinstance(tool_call.params, dict) else {})
        if policy_outcome is not None:
            return {
                "status": "error",
                "result": policy_outcome,
                "tool": tool_name,
                "duration_ms": 0.0,
                "validation_stage": "validated",
                "param_error_code": policy_outcome.get("reason", "policy_violation"),
                "failure_signature": f"{tool_name}:{policy_outcome.get('reason', 'policy_violation')}",
                "invocation_mode": "direct_python",
                "serialization_mode": "python_only_contract",
            }

        # ── Cache lookup ────────────────────────────────────────────────
        if tool_name not in self._non_cacheable_tools:
            cached = self._cache.get(tool_name, tool_call.params)
            if cached is not None:
                return {
                    "status": "success",
                    "result": cached.get("payload"),
                    "tool": tool_name,
                    "duration_ms": 0.0,
                    "cached": True,
                    "cache_age_s": cached.get("cache_age_s", 0),
                    "validation_stage": "validated",
                    "invocation_mode": "direct_python",
                    "serialization_mode": "python_only_contract",
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
            try:
                result = self._call_python_main(impl_path, tool_name, tool_call.params if isinstance(tool_call.params, dict) else {})
                duration_ms = (time.monotonic() - start) * 1000
                if isinstance(result, dict):
                    inner_status = str(result.get("status", "")).lower()
                    if inner_status in {"error", "policy_violation"}:
                        reason = self._canonical_error_code(result)
                        return {
                            "status": "error",
                            "result": result,
                            "tool": tool_name,
                            "duration_ms": round(duration_ms, 2),
                            "validation_stage": "validated",
                            "param_error_code": reason,
                            "failure_signature": f"{tool_name}:{reason}",
                            "invocation_mode": "direct_python",
                            "serialization_mode": "python_only_contract",
                        }
                return {
                    "status": "success",
                    "result": result,
                    "tool": tool_name,
                    "duration_ms": round(duration_ms, 2),
                    "validation_stage": "validated",
                    "corrections": corrections,
                    "invocation_mode": "direct_python",
                    "serialization_mode": "python_only_contract",
                }
            except Exception as exc:
                duration_ms = (time.monotonic() - start) * 1000
                return {
                    "status": "error",
                    "result": str(exc),
                    "tool": tool_name,
                    "duration_ms": round(duration_ms, 2),
                    "validation_stage": "validated",
                    "param_error_code": "runtime_exception",
                    "failure_signature": f"{tool_name}:runtime_exception",
                    "invocation_mode": "direct_python",
                    "serialization_mode": "python_only_contract",
                }

        if tool_name == "run_shell_command" and self._policy_mode == "enforce" and self._task_root is not None:
            with ToolExecutor._fs_mutation_lock:
                before = self._snapshot_filesystem_state()
                outcome = _invoke()
                after = self._snapshot_filesystem_state()
                violation, diagnostic = self._audit_shell_write_violation(
                    before,
                    after,
                    command=str(tool_call.params.get("command", "")),
                )
                if diagnostic is not None and outcome.get("status") == "success":
                    payload = outcome.get("result")
                    if isinstance(payload, dict):
                        payload["policy_diagnostics"] = diagnostic
                    else:
                        outcome["result"] = {"value": payload, "policy_diagnostics": diagnostic}
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

    def _canonical_error_code(self, payload: dict) -> str:
        reason = str(
            payload.get("reason")
            or payload.get("error")
            or payload.get("policy_reason")
            or ""
        ).strip()
        if not reason or reason.lower() == "(none)":
            if payload.get("policy_reason"):
                reason = str(payload.get("policy_reason"))
            elif str(payload.get("status", "")).lower() == "error":
                reason = "tool_error"
            else:
                reason = "runtime_failure"
        reason = reason.replace("\n", " ").strip()
        if len(reason) > 120:
            reason = reason[:120]
        return reason

    def _normalize_params(self, tool_name: str, params: dict) -> list[dict]:
        """Curated alias normalization only (no fuzzy inference)."""
        corrections: list[dict] = []
        if not isinstance(params, dict):
            return corrections
        alias_map = self._CURATED_ALIAS_MAP.get(tool_name, {})
        if self._alias_policy == "curated_strict" and alias_map:
            for src, dst in alias_map.items():
                if src in params and dst not in params:
                    value = params.pop(src)
                    if tool_name == "zip_tool" and src == "source_path":
                        if isinstance(value, list):
                            params[dst] = [str(x) for x in value]
                        else:
                            params[dst] = [str(value)]
                    else:
                        params[dst] = value
                    corrections.append({"from": src, "to": dst, "kind": "alias"})

        if tool_name == "run_shell_command":
            if "shell_preference" not in params:
                params["shell_preference"] = "powershell" if os.name == "nt" else "bash"
            if "reject_on_shell_mismatch" not in params:
                params["reject_on_shell_mismatch"] = True
            if "auto_switch_shell" not in params:
                params["auto_switch_shell"] = True

        elif tool_name == "task_manager":
            if "project_dir" not in params and self._task_root is not None:
                params["project_dir"] = str(self._task_root)
            if "action" in params and isinstance(params["action"], str):
                action_alias = {"complete": "complete_task", "add": "add_task", "list": "query", "status": "update_status"}
                fixed = action_alias.get(params["action"].strip().lower(), params["action"].strip().lower())
                if fixed != params["action"]:
                    corrections.append({"from": params["action"], "to": fixed, "kind": "action_alias"})
                params["action"] = fixed
            if "status" in params and isinstance(params["status"], str):
                status_alias = {"started": "in_progress", "done": "completed", "complete": "completed", "inprogress": "in_progress"}
                fixed = status_alias.get(params["status"].strip().lower(), params["status"].strip().lower())
                if fixed != params["status"]:
                    corrections.append({"from": params["status"], "to": fixed, "kind": "status_alias"})
                params["status"] = fixed

        elif tool_name == "session_manager":
            if "action" in params and isinstance(params["action"], str):
                params["action"] = params["action"].strip().lower()
            if "description" in params and isinstance(params["description"], str):
                data = params.get("data")
                if not isinstance(data, dict):
                    data = {}
                data.setdefault("summary", params["description"])
                params["data"] = data
            params.pop("status", None)
            action = str(params.get("action", "")).lower()
            if action in {"close", "status", "log_change", "log_agent", "log_tool", "add_note"} and not params.get("session_id"):
                sid = self._runtime_context.get("OVERLORD11_SESSION_ID")
                if sid:
                    params["session_id"] = sid
                    corrections.append({"from": "(runtime)", "to": "session_id", "kind": "injected"})

        elif tool_name == "save_memory":
            if "key" not in params and isinstance(params.get("value"), str) and params.get("value", "").strip():
                sid = self._runtime_context.get("OVERLORD11_SESSION_ID", "session")
                params["key"] = f"auto_memory_{sid}"
                corrections.append({"from": "(generated)", "to": "key", "kind": "injected"})

        elif tool_name == "zip_tool":
            if isinstance(params.get("paths"), str):
                raw = str(params["paths"])
                try:
                    parsed = json.loads(raw)
                    if isinstance(parsed, list):
                        params["paths"] = [str(x) for x in parsed]
                    else:
                        params["paths"] = [raw]
                except Exception:
                    params["paths"] = [raw]
                corrections.append({"from": "paths", "to": "paths", "kind": "normalized_list"})
        return corrections

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
            "write_outside_task_output_root": (
                "Write target resolves outside the active task output directory.",
                "Write files under ./output (or paths prefixed with output/).",
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
            "shell_write_outside_task_root_verification_blocked": (
                "Verification command wrote outside allowlisted operational directories.",
                "Allow only external writes under configured shell_policy allowlist.",
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
        *,
        command: str,
    ) -> tuple[Optional[dict], Optional[dict]]:
        if self._task_root is None:
            return None, None

        changed_paths: list[Path] = []
        all_keys = set(before.keys()) | set(after.keys())
        for key in all_keys:
            if before.get(key) != after.get(key):
                changed_paths.append(Path(key))

        outside_paths = [p for p in changed_paths if not self._ensure_within(p, self._task_root)]
        outside = [str(p) for p in outside_paths]
        if not outside:
            return None, None

        intent = self._classify_shell_command_intent(command)
        immutable_patterns = self._effective_immutable_patterns()
        blocked_paths: list[str] = []
        allowlisted_paths: list[str] = []
        for path in outside_paths:
            if self._is_protected_or_immutable_path(path, immutable_patterns):
                blocked_paths.append(str(path))
                continue
            if not self._is_path_allowlisted_for_verification(path):
                blocked_paths.append(str(path))
                continue
            allowlisted_paths.append(str(path))

        if intent == "verification" and not blocked_paths:
            return None, {
                "status": "allowed_external_artifact_write",
                "intent": intent,
                "changed_path_count": len(outside_paths),
                "allowlisted_changed_paths": sorted(allowlisted_paths)[:25],
                "allowlist": list(self._verification_outside_write_allowlist),
            }

        reason = (
            "shell_write_outside_task_root_verification_blocked"
            if intent == "verification"
            else "shell_write_outside_task_root"
        )
        preview = sorted(blocked_paths or outside)[:25]
        return self._deny(
            reason,
            task_root=str(self._task_root),
            changed_path_count=len(outside),
            changed_paths=preview,
            command_intent=intent,
            allowlist=self._verification_outside_write_allowlist,
        ), None

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
                params["path"] = str(self._resolve_path_for_task(params["path"], prefer_output=False))
            return None

        if tool_name in write_tools:
            key = "path"
            if key in params and isinstance(params[key], str):
                resolved = self._resolve_path_for_task(params[key], prefer_output=True)
                if not self._ensure_within(resolved, self._task_root):
                    return self._deny(
                        "write_outside_task_root",
                        path=str(resolved),
                        task_root=str(self._task_root),
                    )
                if not self._ensure_within(resolved, self._task_output_root):
                    return self._deny(
                        "write_outside_task_output_root",
                        path=str(resolved),
                        task_output_root=str(self._task_output_root),
                    )
                # Block direct control-plane writes in normal mode
                if resolved in self._protected_control_plane_paths:
                    return self._deny("write_to_blocked_control_plane_path", path=str(resolved))
                if self._matches_immutable_pattern(resolved, self._effective_immutable_patterns()):
                    return self._deny("write_to_immutable_core_path_blocked", path=str(resolved))
                params[key] = str(resolved)
            return None

        if tool_name == "run_shell_command":
            # Force execution in task output dir unless caller requests a dir under task root.
            requested_dir = params.get("dir_path") or params.get("working_dir") or "."
            resolved_dir = self._resolve_path_for_task(str(requested_dir), prefer_output=True)
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
            if self._shell_targets_immutable(command, self._effective_immutable_patterns()):
                return self._deny("shell_immutable_core_target_blocked", command=command)
            params["working_dir"] = str(resolved_dir)
            params["dir_path"] = str(resolved_dir)
            return None

        return None

    def _resolve_path_for_task(self, raw_path: str, *, prefer_output: bool) -> Path:
        """Resolve a user path into canonical task-root/output-root space."""
        if self._task_root is None:
            return Path(raw_path).resolve()
        if self._task_output_root is None:
            return self._resolve_under(self._task_root, raw_path)
        text = str(raw_path or "").strip()
        if not text:
            return self._task_output_root.resolve() if prefer_output else self._task_root.resolve()
        p = Path(text)
        if p.is_absolute():
            return p.resolve()
        rel_norm = text.replace("\\", "/").lstrip("./")
        if rel_norm.startswith("output/"):
            return (self._task_root / rel_norm).resolve()
        base = self._task_output_root if prefer_output else self._task_root
        return (base / rel_norm).resolve()

    def execute_delegation_graph(
        self,
        delegation_calls: list[ToolCall],
        *,
        loop: int,
        emit_event: Optional[Callable[..., None]] = None,
    ) -> list[tuple[ToolCall, dict]]:
        if not delegation_calls:
            return []
        nodes, by_step, errs = self._prepare_delegation_nodes(delegation_calls)
        if emit_event:
            emit_event("SUBAGENT_GRAPH_START", loop=loop, total=len(delegation_calls), valid=len(nodes), errors=len(errs))
        ordered_results: list[tuple[ToolCall, dict]] = []
        for tc, err in errs:
            ordered_results.append((tc, err))
        if not nodes:
            return ordered_results

        remaining = {n["step_id"]: n for n in nodes}
        completed: set[str] = set()
        while remaining:
            ready = [
                n for sid, n in remaining.items()
                if set(n["depends_on"]).issubset(completed)
            ]
            if not ready:
                for sid in sorted(remaining.keys()):
                    tc = remaining[sid]["tool_call"]
                    ordered_results.append((tc, {"status": "error", "tool": tc.tool_name, "duration_ms": 0.0, "error": "delegation_cycle_or_unresolved_dependency", "result": {"status": "error"}}))
                break
            ready_sorted = sorted(ready, key=lambda n: n["order"])
            run_parallel = len(ready_sorted) > 1 and all(n["allow_parallel"] for n in ready_sorted)
            if emit_event:
                emit_event("SUBAGENT_WAVE_START", loop=loop, wave_size=len(ready_sorted), parallel=run_parallel, step_ids=[n["step_id"] for n in ready_sorted])
            wave_out: dict[str, tuple[ToolCall, dict]] = {}
            if run_parallel:
                with ThreadPoolExecutor(max_workers=min(4, len(ready_sorted))) as pool:
                    futs = {
                        pool.submit(self._execute_delegation, n["tool_call"]): n["step_id"]
                        for n in ready_sorted
                    }
                    for fut in as_completed(futs):
                        sid = futs[fut]
                        n = remaining[sid]
                        wave_out[sid] = (n["tool_call"], fut.result())
            else:
                for n in ready_sorted:
                    wave_out[n["step_id"]] = (n["tool_call"], self._execute_delegation(n["tool_call"]))
            for n in ready_sorted:
                sid = n["step_id"]
                ordered_results.append(wave_out[sid])
                completed.add(sid)
                del remaining[sid]
        if emit_event:
            emit_event("SUBAGENT_GRAPH_COMPLETE", loop=loop, total=len(delegation_calls), completed=len(ordered_results))
        by_id = {id(tc): (tc, res) for tc, res in ordered_results}
        return [by_id[id(tc)] for tc in delegation_calls if id(tc) in by_id]

    def _prepare_delegation_nodes(self, calls: list[ToolCall]) -> tuple[list[dict], dict[str, dict], list[tuple[ToolCall, dict]]]:
        nodes: list[dict] = []
        by_step: dict[str, dict] = {}
        errs: list[tuple[ToolCall, dict]] = []
        seen: set[str] = set()
        for i, tc in enumerate(calls):
            params = tc.params if isinstance(tc.params, dict) else {}
            step_id = str(params.get("step_id") or f"step_{i+1}")
            if step_id in seen:
                errs.append((tc, {"status": "error", "tool": tc.tool_name, "duration_ms": 0.0, "error": f"duplicate_step_id:{step_id}", "result": {"status": "error"}}))
                continue
            seen.add(step_id)
            depends_on = params.get("depends_on") or []
            if isinstance(depends_on, str):
                depends_on = [depends_on]
            if not isinstance(depends_on, list):
                errs.append((tc, {"status": "error", "tool": tc.tool_name, "duration_ms": 0.0, "error": "depends_on_must_be_list", "result": {"status": "error"}}))
                continue
            node = {
                "tool_call": tc,
                "step_id": step_id,
                "depends_on": [str(x) for x in depends_on],
                "allow_parallel": bool(params.get("allow_parallel", False)),
                "order": i,
            }
            nodes.append(node)
            by_step[step_id] = node
        for node in nodes:
            bad = [d for d in node["depends_on"] if d not in by_step]
            if bad:
                tc = node["tool_call"]
                errs.append((tc, {"status": "error", "tool": tc.tool_name, "duration_ms": 0.0, "error": f"unknown_dependencies:{bad}", "result": {"status": "error"}}))
        bad_ids = {id(tc) for tc, _ in errs}
        nodes = [n for n in nodes if id(n["tool_call"]) not in bad_ids]
        return nodes, by_step, errs

    def _execute_delegation(self, tool_call: ToolCall) -> dict:
        if self._delegation_handler is None:
            return {
                "status": "error",
                "result": {"status": "error", "errors": "delegation_handler_not_registered"},
                "tool": tool_call.tool_name,
                "duration_ms": 0.0,
                "error": "delegation_handler_not_registered",
            }
        started = time.monotonic()
        try:
            payload = self._delegation_handler(tool_name=tool_call.tool_name, params=tool_call.params)
            duration_ms = round((time.monotonic() - started) * 1000, 2)
            status = "success" if str(payload.get("status", "")).lower() == "success" else "error"
            out = {
                "status": status,
                "result": payload,
                "tool": tool_call.tool_name,
                "duration_ms": duration_ms,
            }
            if status != "success":
                out["error"] = payload.get("errors") or payload.get("error") or "delegation_failed"
            return out
        except Exception as exc:
            return {
                "status": "error",
                "result": {"status": "error", "errors": str(exc)},
                "tool": tool_call.tool_name,
                "duration_ms": round((time.monotonic() - started) * 1000, 2),
                "error": str(exc),
            }

    def _load_immutable_patterns(self) -> list[str]:
        raw = os.environ.get("OVERLORD11_IMMUTABLE_CORE_PATHS", "").strip()
        if not raw:
            return []
        try:
            items = json.loads(raw)
            if isinstance(items, list):
                return [str(x).replace("\\", "/").lower().strip() for x in items if str(x).strip()]
        except Exception:
            pass
        return []

    def _effective_immutable_patterns(self) -> list[str]:
        env_patterns = self._load_immutable_patterns()
        if env_patterns:
            return env_patterns
        return list(self._immutable_patterns_default)

    def _classify_shell_command_intent(self, command: str) -> str:
        lowered = (command or "").lower()
        mutating_markers = (
            "set-content", "add-content", "out-file", "copy-item", "move-item",
            "remove-item", "new-item", "rename-item", "del ", "rm ", "mv ",
            "cp ", "touch ", "tee ", "sed -i", ">>", "1>", "2>",
        )
        if any(marker in lowered for marker in mutating_markers):
            return "mutating"
        verification_markers = (
            "python -m unittest",
            "python -m py_compile",
            "pytest",
            "ruff check",
            "flake8",
            "mypy",
        )
        if any(marker in lowered for marker in verification_markers):
            return "verification"
        return "unknown"

    def _repo_relative_posix(self, path: Path) -> Optional[str]:
        try:
            rel = path.resolve().relative_to(_BASE_DIR.resolve())
        except ValueError:
            return None
        return str(rel).replace("\\", "/")

    def _is_path_allowlisted_for_verification(self, path: Path) -> bool:
        rel = self._repo_relative_posix(path)
        if rel is None:
            return False
        rel_norm = rel.lstrip("./")
        for pattern in self._verification_outside_write_allowlist:
            pat = pattern.replace("\\", "/").lstrip("./")
            if fnmatch.fnmatch(rel_norm, pat):
                return True
        return False

    def _is_protected_or_immutable_path(self, path: Path, immutable_patterns: list[str]) -> bool:
        resolved = path.resolve()
        if resolved in self._protected_control_plane_paths:
            return True
        if self._matches_immutable_pattern(resolved, immutable_patterns):
            return True
        if self._shell_block_tracked_repo_writes:
            rel = self._repo_relative_posix(resolved)
            if rel is not None and not self._is_path_allowlisted_for_verification(resolved):
                return True
        return False

    def _matches_immutable_pattern(self, path: Path, patterns: list[str]) -> bool:
        if not patterns:
            return False
        normalized = str(path.resolve()).replace("\\", "/").lower()
        base = str(_BASE_DIR.resolve()).replace("\\", "/").lower().rstrip("/")
        rel = normalized
        if normalized.startswith(base + "/"):
            rel = normalized[len(base) + 1 :]
        for pat in patterns:
            p = pat.rstrip("/")
            if rel == p or rel.startswith(p + "/"):
                return True
        return False

    def _shell_targets_immutable(self, command: str, patterns: list[str]) -> bool:
        if not command or not patterns:
            return False
        cmd = command.replace("\\", "/").lower()
        return any(pat.rstrip("/").lower() in cmd for pat in patterns)

    def _preflight_params(self, tool_name: str, params: Any, corrections: Optional[list[dict]] = None) -> tuple[Optional[dict], Optional[dict]]:
        corrections = corrections or []
        if not isinstance(params, dict):
            return ({
                "status": "error",
                "error": "param_preflight_failed",
                "reason": "params_must_be_object",
                "hint": f"Tool '{tool_name}' expects params to be a JSON object.",
                "suggested_payload": {},
                "corrections": corrections,
            }, None)

        forbidden = sorted(
            [k for k in self._FORBIDDEN_ALIASES.get(tool_name, set()) if k in params]
        )
        if forbidden:
            return ({
                "status": "error",
                "error": "param_preflight_failed",
                "reason": "invalid_value",
                "tool": tool_name,
                "hint": f"Forbidden alias parameter(s): {', '.join(forbidden)}",
                "corrections": corrections,
                "suggested_payload": self._build_suggested_payload(tool_name, params, forbidden),
            }, None)

        contract = self._tool_contracts.get(tool_name)
        if contract is None:
            return ({
                "status": "error",
                "error": "param_preflight_failed",
                "reason": "tool_contract_missing",
                "tool": tool_name,
                "hint": "No runtime contract registered for this tool.",
                "corrections": corrections,
                "suggested_payload": params,
            }, None)

        try:
            parsed = contract.params_model.model_validate(params)
            validated = parsed.model_dump(exclude_none=True)
        except ValidationError as exc:
            return (self._build_validation_error(tool_name, params, exc, corrections), None)

        semantic = self._semantic_preflight(tool_name, validated)
        if semantic is not None:
            semantic.setdefault("status", "error")
            semantic.setdefault("error", "param_preflight_failed")
            semantic.setdefault("tool", tool_name)
            semantic.setdefault("corrections", corrections)
            semantic.setdefault("suggested_payload", self._build_suggested_payload(tool_name, validated, []))
            return (semantic, None)
        return (None, validated)

    def _build_validation_error(self, tool_name: str, original: dict, exc: ValidationError, corrections: list[dict]) -> dict:
        unknown: list[str] = []
        missing: list[str] = []
        invalid_type: list[dict[str, Any]] = []
        invalid_value: list[dict[str, Any]] = []
        for err in exc.errors():
            loc = [str(x) for x in err.get("loc", [])]
            field = loc[-1] if loc else ""
            etype = str(err.get("type", ""))
            msg = str(err.get("msg", ""))
            if etype == "extra_forbidden":
                unknown.append(field)
            elif etype == "missing":
                missing.append(field)
            elif "literal" in etype or "enum" in etype:
                invalid_value.append({"field": field, "message": msg})
            else:
                invalid_type.append({"field": field, "message": msg})
        reason = "invalid_type"
        if unknown:
            reason = "unknown_parameters"
        elif missing:
            reason = "missing_required"
        elif invalid_value:
            reason = "invalid_value"
        return {
            "status": "error",
            "error": "param_preflight_failed",
            "reason": reason,
            "tool": tool_name,
            "unknown_parameters": sorted([u for u in unknown if u]),
            "missing_required": sorted([m for m in missing if m]),
            "invalid_type": invalid_type,
            "invalid_value": invalid_value,
            "hint": self._build_validation_hint(tool_name, reason, unknown, missing),
            "corrections": corrections,
            "suggested_payload": self._build_suggested_payload(tool_name, original, unknown),
        }

    def _build_validation_hint(self, tool_name: str, reason: str, unknown: list[str], missing: list[str]) -> str:
        if reason == "unknown_parameters":
            return f"Remove unsupported parameter(s): {', '.join(sorted([u for u in unknown if u]))}."
        if reason == "missing_required":
            return f"Add required parameter(s): {', '.join(sorted([m for m in missing if m]))}."
        return f"Adjust parameter types/values to match tools/defs/{tool_name}.json."

    def _build_suggested_payload(self, tool_name: str, params: dict, unknown: list[str]) -> dict:
        candidate = {k: v for k, v in params.items() if k not in set(unknown)}
        if tool_name == "session_manager":
            action = str(candidate.get("action", "")).strip().lower()
            if action in {"close", "status", "log_change", "log_agent", "log_tool", "add_note"} and not candidate.get("session_id"):
                sid = self._runtime_context.get("OVERLORD11_SESSION_ID")
                if sid:
                    candidate["session_id"] = sid
        return candidate

    def _semantic_preflight(self, tool_name: str, params: dict) -> Optional[dict]:
        if tool_name == "task_manager":
            action = str(params.get("action", "")).strip().lower()
            if action == "add_subtask" and not str(params.get("task_id", "")).strip():
                return {"reason": "missing_required", "hint": "task_manager add_subtask requires task_id."}
            if action == "update_status" and not str(params.get("task_id", "")).strip():
                return {"reason": "missing_required", "hint": "task_manager update_status requires task_id."}
            if action == "complete_subtask" and not str(params.get("subtask_id", "")).strip():
                return {"reason": "missing_required", "hint": "task_manager complete_subtask requires subtask_id."}
        if tool_name == "session_manager":
            action = str(params.get("action", "")).strip().lower()
            if action in {"status", "log_change", "log_agent", "log_tool", "add_note", "close"} and not str(params.get("session_id", "")).strip():
                return {"reason": "missing_required", "hint": f"session_manager action '{action}' requires session_id."}
        if tool_name == "save_memory":
            key = str(params.get("key", "")).strip()
            value = str(params.get("value", "")).strip()
            if not key or not value:
                return {"reason": "missing_required", "hint": "save_memory requires both key and value."}
        if tool_name == "zip_tool":
            action = str(params.get("action", "")).strip().lower()
            if action == "create":
                if not str(params.get("output", "")).strip():
                    return {"reason": "missing_required", "hint": "zip_tool create requires output."}
                paths = params.get("paths")
                if not isinstance(paths, list) or len(paths) == 0:
                    return {"reason": "missing_required", "hint": "zip_tool create requires non-empty paths list."}
            if action in {"extract", "list", "add", "remove", "info"} and not str(params.get("file", "")).strip():
                return {"reason": "missing_required", "hint": f"zip_tool action '{action}' requires file."}
        if tool_name == "publisher_tool":
            if not str(params.get("title", "")).strip():
                return {"reason": "missing_required", "hint": "publisher_tool requires title."}
            if not str(params.get("content", "")).strip():
                return {"reason": "missing_required", "hint": "publisher_tool requires content."}
        if tool_name == "run_shell_command":
            if not str(params.get("command", "")).strip():
                return {"reason": "missing_required", "hint": "run_shell_command requires command."}
        return None

    def _call_python_main(self, impl_path: Path, tool_name: str, params: dict) -> Any:
        contract = self._tool_contracts.get(tool_name)
        if contract is None:
            raise RuntimeError(f"tool_contract_missing:{tool_name}")
        context = {
            "session_id": self._runtime_context.get("OVERLORD11_SESSION_ID", ""),
            "task_root": str(self._task_root) if self._task_root is not None else "",
            "output_root": str(self._task_output_root) if self._task_output_root is not None else "",
            "repo_root": str(_BASE_DIR.resolve()),
        }
        try:
            with self._runtime_env():
                return contract.invoke(params, context)
        except SystemExit as exc:
            code = exc.code if isinstance(exc.code, int) else 1
            raise RuntimeError(f"Tool exited via SystemExit(code={code})") from exc

    def _supports_direct_kwargs(self, fn: Callable[..., Any], params: dict) -> bool:
        try:
            sig = inspect.signature(fn)
        except Exception:
            return True
        parameters = sig.parameters.values()
        if any(p.kind == inspect.Parameter.VAR_KEYWORD for p in parameters):
            return True
        accepted = {
            p.name
            for p in parameters
            if p.kind in {inspect.Parameter.POSITIONAL_OR_KEYWORD, inspect.Parameter.KEYWORD_ONLY}
        }
        if not params:
            return True
        return set(params.keys()).issubset(accepted)
