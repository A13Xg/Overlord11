"""
Overlord11 - Execute Python Tool
===================================
Sandboxed Python code execution with timeout enforcement and output capture.

Usage:
    python execute_python.py --code "print(1+1)" --timeout 30
    python execute_python.py --code "x = 2+2; print(x)" --allow_network false
"""

import argparse
import io
import json
import sys
import time
import traceback
from concurrent.futures import ProcessPoolExecutor, TimeoutError as FuturesTimeoutError
from pathlib import Path

# ---------------------------------------------------------------------------
# Restricted execution globals
# ---------------------------------------------------------------------------

_BLOCKED_NAMES = frozenset([
    "open",
    "exec",
    "eval",
    "compile",
    "__import__",
    "breakpoint",
    "input",
])

_SAFE_BUILTINS = {
    name: getattr(__builtins__ if isinstance(__builtins__, dict) else __builtins__, name, None)
    for name in [
        "abs", "all", "any", "bin", "bool", "bytes", "callable", "chr",
        "dict", "dir", "divmod", "enumerate", "filter", "float", "format",
        "frozenset", "getattr", "hasattr", "hash", "hex", "id", "int",
        "isinstance", "issubclass", "iter", "len", "list", "map", "max",
        "min", "next", "object", "oct", "ord", "pow", "print", "range",
        "repr", "reversed", "round", "set", "setattr", "slice", "sorted",
        "staticmethod", "str", "sum", "super", "tuple", "type", "vars", "zip",
        "Exception", "ValueError", "TypeError", "KeyError", "IndexError",
        "RuntimeError", "StopIteration", "NotImplementedError",
        "True", "False", "None",
    ]
    if getattr(__builtins__ if isinstance(__builtins__, dict) else __builtins__, name, None) is not None
    or name in ("True", "False", "None")
}


def _worker(code: str, allow_network: bool) -> dict:
    """Worker function executed in a subprocess for isolation."""
    import ast as _ast
    import io as _io
    import sys as _sys
    import time as _time
    import traceback as _tb

    stdout_buf = _io.StringIO()
    stderr_buf = _io.StringIO()
    old_stdout, old_stderr = _sys.stdout, _sys.stderr
    _sys.stdout = stdout_buf
    _sys.stderr = stderr_buf

    restricted_globals: dict = {
        "__builtins__": _SAFE_BUILTINS,
        "__name__": "__sandbox__",
    }

    # Selectively allow safe stdlib modules
    import math
    import json as _json
    import re
    import datetime
    import collections
    import itertools
    import functools
    import string
    restricted_globals.update({
        "math": math,
        "json": _json,
        "re": re,
        "datetime": datetime,
        "collections": collections,
        "itertools": itertools,
        "functools": functools,
        "string": string,
    })

    start = _time.monotonic()
    returncode = 0
    try:
        exec(compile(code, "<sandbox>", "exec"), restricted_globals)  # noqa: S102
    except Exception:
        stderr_buf.write(_tb.format_exc())
        returncode = 1
    finally:
        _sys.stdout = old_stdout
        _sys.stderr = old_stderr

    duration_ms = (_time.monotonic() - start) * 1000
    return {
        "status": "success" if returncode == 0 else "error",
        "stdout": stdout_buf.getvalue(),
        "stderr": stderr_buf.getvalue(),
        "returncode": returncode,
        "duration_ms": round(duration_ms, 2),
    }


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def _ast_check(code: str, allow_network: bool) -> str:
    """
    Use AST analysis to detect dangerous imports and attribute accesses.
    Returns an error message string if blocked, or empty string if clean.
    """
    import ast

    _blocked_imports = {
        "os", "sys", "subprocess", "importlib", "shutil", "socket",
        "pty", "ctypes", "multiprocessing", "threading", "signal",
        "builtins", "inspect", "gc",
    }
    if not allow_network:
        _blocked_imports.update({"urllib", "requests", "http", "ftplib", "smtplib", "ssl"})

    try:
        tree = ast.parse(code)
    except SyntaxError as exc:
        return f"SyntaxError: {exc}"

    for node in ast.walk(tree):
        # Block any import of restricted modules
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            module = getattr(node, "module", None) or ""
            names = [alias.name for alias in getattr(node, "names", [])]
            for name in ([module] if module else []) + names:
                top = name.split(".")[0]
                if top in _blocked_imports:
                    return f"Blocked: import of '{top}' is not permitted in sandboxed execution."
        # Block __import__() calls
        if isinstance(node, ast.Call):
            func = node.func
            if isinstance(func, ast.Name) and func.id == "__import__":
                return "Blocked: __import__() is not permitted in sandboxed execution."
            # Block getattr tricks like getattr(os, 'system')
            if isinstance(func, ast.Name) and func.id in ("getattr", "setattr", "delattr"):
                if node.args and isinstance(node.args[0], ast.Name):
                    if node.args[0].id in _blocked_imports:
                        return f"Blocked: attribute access on '{node.args[0].id}' is not permitted."
    return ""


def run_python(code: str, timeout: int = 30, allow_network: bool = False) -> dict:
    """
    Execute arbitrary Python code in a sandboxed environment.

    Args:
        code: Python source code to execute.
        timeout: Maximum execution time in seconds.
        allow_network: If False (default), network modules are blocked.

    Returns:
        dict with keys: status, stdout, stderr, returncode, duration_ms
    """
    start = time.monotonic()

    # AST-based static safety check before spawning
    error_msg = _ast_check(code, allow_network)
    if error_msg:
        return {
            "status": "error",
            "stdout": "",
            "stderr": error_msg,
            "returncode": 1,
            "duration_ms": round((time.monotonic() - start) * 1000, 2),
        }

    try:
        with ProcessPoolExecutor(max_workers=1) as executor:
            future = executor.submit(_worker, code, allow_network)
            result = future.result(timeout=timeout)
        return result
    except FuturesTimeoutError:
        duration_ms = round((time.monotonic() - start) * 1000, 2)
        return {
            "status": "error",
            "stdout": "",
            "stderr": f"Execution timed out after {timeout}s.",
            "returncode": 124,
            "duration_ms": duration_ms,
        }
    except Exception as exc:
        duration_ms = round((time.monotonic() - start) * 1000, 2)
        return {
            "status": "error",
            "stdout": "",
            "stderr": traceback.format_exc(),
            "returncode": 1,
            "duration_ms": duration_ms,
        }


# ---------------------------------------------------------------------------
# main() for tool executor compatibility
# ---------------------------------------------------------------------------

def main(code: str, timeout: int = 30, allow_network: bool = False) -> dict:
    """Entry point called by ToolExecutor.main()."""
    return run_python(code=code, timeout=int(timeout), allow_network=bool(allow_network))


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def _cli() -> None:
    parser = argparse.ArgumentParser(description="Sandboxed Python execution tool")
    parser.add_argument("--code", required=True, help="Python code to execute")
    parser.add_argument("--timeout", type=int, default=30, help="Timeout in seconds")
    parser.add_argument("--allow_network", type=lambda v: v.lower() == "true", default=False)
    args = parser.parse_args()

    result = run_python(code=args.code, timeout=args.timeout, allow_network=args.allow_network)
    print(json.dumps(result, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    _cli()
