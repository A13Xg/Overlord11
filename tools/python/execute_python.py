"""
tools/python/execute_python.py
================================
Execute arbitrary Python code safely in a subprocess sandbox.
Returns stdout, stderr, and exit code.

Used by the self-healing system and agent loops for dynamic problem solving.
"""

import subprocess
import sys
import tempfile
import os
from pathlib import Path
from typing import Any, Dict, Optional


def execute_python(
    code: str,
    timeout: int = 30,
    working_dir: Optional[str] = None,
    env_vars: Optional[Dict[str, str]] = None,
) -> Dict[str, Any]:
    """
    Execute Python code in a subprocess and return the results.

    Parameters
    ----------
    code        : Python source code to execute
    timeout     : Maximum execution time in seconds (default 30)
    working_dir : Working directory for the subprocess (default: temp dir)
    env_vars    : Additional environment variables to pass to the subprocess

    Returns
    -------
    {
        "success": bool,
        "stdout":  str,
        "stderr":  str,
        "exit_code": int,
        "timed_out": bool
    }
    """
    if not isinstance(code, str) or not code.strip():
        return {
            "success": False,
            "stdout": "",
            "stderr": "No code provided",
            "exit_code": 1,
            "timed_out": False,
        }

    # Cap timeout to prevent runaway executions
    timeout = min(int(timeout), 120)

    # Build subprocess environment
    proc_env = os.environ.copy()
    if env_vars and isinstance(env_vars, dict):
        for k, v in env_vars.items():
            if isinstance(k, str) and isinstance(v, str):
                proc_env[k] = v

    # Resolve working directory
    _created_tmpdir = None
    if working_dir:
        work_path = Path(working_dir)
        if not work_path.is_dir():
            return {
                "success": False,
                "stdout": "",
                "stderr": f"Working directory does not exist: {working_dir}",
                "exit_code": 1,
                "timed_out": False,
            }
        cwd = str(work_path.resolve())
    else:
        _created_tmpdir = tempfile.mkdtemp(prefix="ovr11_exec_")
        cwd = _created_tmpdir

    # Write code to a temp file and execute it
    with tempfile.NamedTemporaryFile(
        mode="w",
        suffix=".py",
        dir=cwd,
        delete=False,
        encoding="utf-8",
    ) as f:
        f.write(code)
        script_path = f.name

    try:
        result = subprocess.run(
            [sys.executable, script_path],
            capture_output=True,
            text=True,
            timeout=timeout,
            cwd=cwd,
            env=proc_env,
        )
        return {
            "success": result.returncode == 0,
            "stdout": result.stdout,
            "stderr": result.stderr,
            "exit_code": result.returncode,
            "timed_out": False,
        }
    except subprocess.TimeoutExpired:
        return {
            "success": False,
            "stdout": "",
            "stderr": f"Execution timed out after {timeout} seconds",
            "exit_code": -1,
            "timed_out": True,
        }
    except Exception as exc:
        return {
            "success": False,
            "stdout": "",
            "stderr": str(exc),
            "exit_code": -1,
            "timed_out": False,
        }
    finally:
        # Clean up temp script
        try:
            os.unlink(script_path)
        except OSError:
            pass
        # Clean up temp directory created by this invocation (not caller-supplied dirs)
        if _created_tmpdir:
            import shutil
            try:
                shutil.rmtree(_created_tmpdir, ignore_errors=True)
            except OSError:
                pass
