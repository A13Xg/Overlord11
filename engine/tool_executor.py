"""
engine/tool_executor.py
========================
Parses tool-call expressions from agent text output and dispatches them
to the matching tool implementation in tools/python/.

Tool call format (two supported styles)
-----------------------------------------
1. JSON block:
   ```tool_call
   {"tool": "read_file", "args": {"path": "foo.txt"}}
   ```

2. Inline XML-like tags (used by Anthropic-style responses):
   <tool_call>{"tool": "write_file", "args": {...}}</tool_call>

Both styles are detected and parsed.
"""

import importlib.util
import json
import re
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
_TOOLS_DIR = _PROJECT_ROOT / "tools" / "python"
_CONFIG_PATH = _PROJECT_ROOT / "config.json"

# Regex patterns for tool call extraction
_FENCE_PATTERN = re.compile(
    r"```(?:tool_call|json)\s*\n(\{.*?\})\s*\n```",
    re.DOTALL | re.IGNORECASE,
)
_TAG_PATTERN = re.compile(
    r"<tool_call>\s*(\{.*?\})\s*</tool_call>",
    re.DOTALL,
)
_FUNCTION_PATTERN = re.compile(
    r'<function_calls>\s*<invoke name="([^"]+)">(.*?)</invoke>\s*</function_calls>',
    re.DOTALL,
)


# ---------------------------------------------------------------------------
# Tool loader (dynamic import)
# ---------------------------------------------------------------------------

class ToolLoader:
    """Lazy-loads tool Python modules by name."""

    def __init__(self):
        self._cache: Dict[str, Any] = {}
        self._config = self._load_config()

    def _load_config(self) -> Dict[str, Any]:
        try:
            return json.loads(_CONFIG_PATH.read_text())
        except (OSError, json.JSONDecodeError):
            return {}

    def load(self, tool_name: str) -> Optional[Any]:
        """Return the loaded module for tool_name, or None if not found."""
        if tool_name in self._cache:
            return self._cache[tool_name]

        # Resolve implementation path from config
        tool_entry = self._config.get("tools", {}).get(tool_name, {})
        impl_path = tool_entry.get("impl", "")
        if not impl_path:
            # Fallback: guess filename
            impl_path = f"tools/python/{tool_name}.py"

        full_path = _PROJECT_ROOT / impl_path
        if not full_path.exists():
            return None

        spec = importlib.util.spec_from_file_location(tool_name, str(full_path))
        if not spec or not spec.loader:
            return None

        module = importlib.util.module_from_spec(spec)
        try:
            spec.loader.exec_module(module)  # type: ignore[union-attr]
        except Exception:
            return None

        self._cache[tool_name] = module
        return module


# ---------------------------------------------------------------------------
# ToolExecutor
# ---------------------------------------------------------------------------

class ToolExecutor:
    """
    Parses tool calls from agent output and executes the underlying tool.

    Usage
    -----
    executor = ToolExecutor()
    calls = executor.parse(agent_response_text)
    for call in calls:
        result = executor.execute(call["tool"], call["args"])
    """

    def __init__(self):
        self._loader = ToolLoader()

    # ------------------------------------------------------------------
    # Parse
    # ------------------------------------------------------------------

    def parse(self, text: str) -> List[Dict[str, Any]]:
        """
        Extract all tool calls from agent output text.
        Returns list of {"tool": str, "args": dict} dicts.
        """
        calls: List[Dict[str, Any]] = []

        # Try fenced JSON blocks
        for m in _FENCE_PATTERN.finditer(text):
            try:
                data = json.loads(m.group(1))
                if "tool" in data:
                    calls.append({"tool": data["tool"], "args": data.get("args", {})})
            except json.JSONDecodeError:
                pass

        # Try XML-style tags
        for m in _TAG_PATTERN.finditer(text):
            try:
                data = json.loads(m.group(1))
                if "tool" in data:
                    calls.append({"tool": data["tool"], "args": data.get("args", {})})
            except json.JSONDecodeError:
                pass

        # Try Anthropic function_calls format
        for m in _FUNCTION_PATTERN.finditer(text):
            tool_name = m.group(1)
            inner = m.group(2).strip()
            # Extract parameter values
            params = {}
            for param_match in re.finditer(
                r'<parameter name="([^"]+)">(.*?)</parameter>', inner, re.DOTALL
            ):
                params[param_match.group(1)] = param_match.group(2).strip()
            calls.append({"tool": tool_name, "args": params})

        return calls

    def has_tool_calls(self, text: str) -> bool:
        """Quick check — does this text contain any tool call syntax?"""
        return bool(
            _FENCE_PATTERN.search(text)
            or _TAG_PATTERN.search(text)
            or _FUNCTION_PATTERN.search(text)
        )

    # ------------------------------------------------------------------
    # Execute
    # ------------------------------------------------------------------

    def execute(self, tool_name: str, args: Dict[str, Any]) -> Dict[str, Any]:
        """
        Execute a tool and return {"success": bool, "result": Any, "error": str}.
        """
        module = self._loader.load(tool_name)
        if module is None:
            return {
                "success": False,
                "result": None,
                "error": f"Tool '{tool_name}' not found or failed to load",
            }

        # Discover the callable entry point
        entry = getattr(module, tool_name, None)
        if entry is None:
            # Try common naming conventions
            for candidate in ("run", "execute", "main", "call"):
                entry = getattr(module, candidate, None)
                if entry and callable(entry):
                    break

        if entry is None or not callable(entry):
            return {
                "success": False,
                "result": None,
                "error": f"No callable entry point found in tool '{tool_name}'",
            }

        try:
            result = entry(**args)
            return {"success": True, "result": result, "error": None}
        except TypeError as exc:
            return {"success": False, "result": None, "error": f"Argument error: {exc}"}
        except Exception as exc:
            return {"success": False, "result": None, "error": str(exc)}
