"""
Overlord11 Engine - Tool Executor
====================================
Tool call detection and execution for the engine loop.
"""

import importlib.util
import json
import re
import subprocess
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, List, Optional

_BASE_DIR = Path(__file__).resolve().parent.parent

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
    r"```json\s*(\{.*?\"tool\"\s*:.*?\})\s*```",
    re.DOTALL | re.IGNORECASE,
)
_XML_CALL_RE = re.compile(
    r"<tool_call>\s*(\{.*?\})\s*</tool_call>",
    re.DOTALL | re.IGNORECASE,
)
_FUNC_CALL_RE = re.compile(
    r"TOOL_CALL:\s*(\w+)\s*\(([^)]*)\)",
    re.IGNORECASE,
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

    # 1. JSON block format: ```json\n{"tool": "name", "params": {...}}\n```
    for m in _JSON_BLOCK_RE.finditer(text):
        raw = m.group(0)
        try:
            obj = json.loads(m.group(1))
            tool_name = obj.get("tool") or obj.get("tool_name") or obj.get("name") or ""
            params = obj.get("params") or obj.get("parameters") or obj.get("args") or {}
            if tool_name:
                calls.append(ToolCall(tool_name=tool_name, params=params, raw=raw))
        except (json.JSONDecodeError, TypeError):
            pass

    # 2. XML-style: <tool_call>{"tool": "name", "params": {...}}</tool_call>
    for m in _XML_CALL_RE.finditer(text):
        raw = m.group(0)
        try:
            obj = json.loads(m.group(1))
            tool_name = obj.get("tool") or obj.get("tool_name") or obj.get("name") or ""
            params = obj.get("params") or obj.get("parameters") or obj.get("args") or {}
            if tool_name:
                calls.append(ToolCall(tool_name=tool_name, params=params, raw=raw))
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

    def __init__(self, tools_dir: Path, config: dict):
        self._tools_dir = Path(tools_dir)
        self._config = config
        self._tool_map: dict = {}
        self._build_tool_map()
        # Initialise the tool result cache using the orchestration.cache config block
        cache_cfg = config.get("orchestration", {}).get("cache", {})
        self._cache = ToolCache(config=cache_cfg, project_root=_BASE_DIR)

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

        # ── Cache lookup ────────────────────────────────────────────────
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

        # Strategy 1: import and call main()
        try:
            result = self._call_python_main(impl_path, tool_call.params)
            duration_ms = (time.monotonic() - start) * 1000
            outcome = {
                "status": "success",
                "result": result,
                "tool": tool_name,
                "duration_ms": round(duration_ms, 2),
            }
            self._cache.put(tool_name, tool_call.params, outcome)
            return outcome
        except Exception:
            pass  # Fall through to subprocess strategy

        # Strategy 2: subprocess with JSON params
        try:
            result = self._call_subprocess(impl_path, tool_call.params)
            duration_ms = (time.monotonic() - start) * 1000
            outcome = {
                "status": "success",
                "result": result,
                "tool": tool_name,
                "duration_ms": round(duration_ms, 2),
            }
            self._cache.put(tool_name, tool_call.params, outcome)
            return outcome
        except Exception as sub_err:
            duration_ms = (time.monotonic() - start) * 1000
            return {
                "status": "error",
                "result": str(sub_err),
                "tool": tool_name,
                "duration_ms": round(duration_ms, 2),
            }

    def _call_python_main(self, impl_path: Path, params: dict) -> Any:
        """Import the module and call its main() function."""
        # Temporarily add the tools/python dir to sys.path
        tools_python = str(impl_path.parent)
        injected = tools_python not in sys.path
        if injected:
            sys.path.insert(0, tools_python)
        try:
            mod = self._load_module(impl_path)
            if not hasattr(mod, "main"):
                raise AttributeError(f"No main() in {impl_path.name}")
            try:
                return mod.main(**params)
            except SystemExit as exc:
                code = exc.code if isinstance(exc.code, int) else 1
                raise RuntimeError(f"Tool exited via SystemExit(code={code})") from exc
        finally:
            if injected:
                try:
                    sys.path.remove(tools_python)
                except ValueError:
                    pass

    def _call_subprocess(self, impl_path: Path, params: dict) -> str:
        """Run the tool as a subprocess, passing params as --key value args."""
        cmd = [sys.executable, str(impl_path)]
        for key, value in params.items():
            # Always serialize values as JSON strings to prevent injection
            serialized = value if isinstance(value, str) else json.dumps(value, ensure_ascii=False)
            cmd += [f"--{key}", serialized]
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            encoding="utf-8",
            timeout=120,
        )
        if result.returncode != 0 and result.stderr:
            raise RuntimeError(result.stderr.strip())
        return result.stdout.strip()
