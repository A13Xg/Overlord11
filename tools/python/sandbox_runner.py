"""
Overlord11 — Sandbox Runner
============================
Execute arbitrary Python code in a fully isolated, ephemeral virtual environment.

For each invocation:
  1. Creates a fresh temp directory (prefix: ovr11_sandbox_)
  2. Creates a new Python venv inside it
  3. Optionally installs pip packages
  4. Writes the code to script.py and runs it with the venv Python
  5. Captures stdout, stderr, and exit code
  6. Destroys the entire temp directory — nothing persists

No safety restrictions are applied (no AST blocking, no module deny-lists).
The caller is responsible for ensuring code is safe for their environment.

Usage (CLI / Strategy 2):
    python sandbox_runner.py --code "print(1+1)"
    python sandbox_runner.py --code "import numpy as np; print(np.zeros(3))" --packages '["numpy"]'
    python sandbox_runner.py --code "print(input())" --input_data "hello"
    python sandbox_runner.py --code "import time; time.sleep(99)" --timeout 5

Returns JSON:
    {
        "status": "success" | "error",
        "stdout": "...",
        "stderr": "...",
        "returncode": 0,
        "duration_ms": 1234.5,
        "packages_installed": ["numpy"],
        "pip_stderr": "..."   # only on pip install failure
    }
"""

import argparse
import contextlib
import io
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
import traceback
import venv
from pathlib import Path
from typing import List, Optional


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _venv_python(venv_dir: Path) -> Path:
    """Return the platform-correct path to the venv Python executable."""
    if sys.platform == "win32":
        return venv_dir / "Scripts" / "python.exe"
    return venv_dir / "bin" / "python"


def _venv_pip(venv_dir: Path) -> Path:
    """Return the platform-correct path to the venv pip executable."""
    if sys.platform == "win32":
        return venv_dir / "Scripts" / "pip.exe"
    return venv_dir / "bin" / "pip"


# ---------------------------------------------------------------------------
# Core function
# ---------------------------------------------------------------------------

def run_in_sandbox(
    code: str,
    packages: Optional[List[str]] = None,
    timeout: int = 60,
    input_data: str = "",
    session_id: Optional[str] = None,
) -> dict:
    """
    Execute Python code in a temporary virtual environment.

    Args:
        code:        Python source code to execute.
        packages:    pip packages to install before running (e.g. ['numpy']).
        timeout:     Script execution timeout in seconds. pip has its own 120s limit.
        input_data:  String piped to the script's stdin.
        session_id:  If provided, the result is logged via log_manager.

    Returns:
        dict with keys: status, stdout, stderr, returncode, duration_ms,
                        packages_installed, [pip_stderr on failure]
    """
    packages = packages or []
    start = time.monotonic()
    tmp_dir: Optional[str] = None

    try:
        # ── 1. Create temp directory ──────────────────────────────────────
        tmp_dir = tempfile.mkdtemp(prefix="ovr11_sandbox_")
        tmp_path = Path(tmp_dir)
        venv_dir = tmp_path / "venv"

        # ── 2. Create virtual environment ────────────────────────────────
        # Suppress venv's own stdout/stderr (Windows prints 8.3-path warnings
        # to stdout which would corrupt the JSON output of this tool).
        try:
            _devnull = io.StringIO()
            with contextlib.redirect_stdout(_devnull), contextlib.redirect_stderr(_devnull):
                venv.create(str(venv_dir), with_pip=True, clear=True)
        except Exception as exc:
            return {
                "status": "error",
                "error": f"Failed to create virtual environment: {exc}",
                "stdout": "",
                "stderr": traceback.format_exc(),
                "returncode": 1,
                "duration_ms": round((time.monotonic() - start) * 1000, 2),
                "packages_installed": [],
            }

        python_bin = _venv_python(venv_dir)
        pip_bin = _venv_pip(venv_dir)

        # ── 3. Install packages ───────────────────────────────────────────
        if packages:
            pip_cmd = [
                str(pip_bin), "install",
                "--quiet",
                "--no-cache-dir",
                "--disable-pip-version-check",
            ] + packages

            pip_result = subprocess.run(
                pip_cmd,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=120,
                cwd=tmp_dir,
            )

            if pip_result.returncode != 0:
                return {
                    "status": "error",
                    "error": f"pip install failed (exit {pip_result.returncode})",
                    "pip_stderr": pip_result.stderr.strip(),
                    "stdout": "",
                    "stderr": pip_result.stderr.strip(),
                    "returncode": pip_result.returncode,
                    "duration_ms": round((time.monotonic() - start) * 1000, 2),
                    "packages_installed": [],
                }

        # ── 4. Write script ───────────────────────────────────────────────
        script_path = tmp_path / "script.py"
        script_path.write_text(code, encoding="utf-8")

        # ── 5. Run script ─────────────────────────────────────────────────
        run_result = subprocess.run(
            [str(python_bin), str(script_path)],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout,
            cwd=tmp_dir,
            input=input_data if input_data else None,
        )

        duration_ms = round((time.monotonic() - start) * 1000, 2)
        result = {
            "status": "success" if run_result.returncode == 0 else "error",
            "stdout": run_result.stdout,
            "stderr": run_result.stderr,
            "returncode": run_result.returncode,
            "duration_ms": duration_ms,
            "packages_installed": packages,
        }

    except subprocess.TimeoutExpired:
        duration_ms = round((time.monotonic() - start) * 1000, 2)
        result = {
            "status": "error",
            "error": f"Execution timed out after {timeout}s.",
            "stdout": "",
            "stderr": f"Execution timed out after {timeout}s.",
            "returncode": 124,
            "duration_ms": duration_ms,
            "packages_installed": packages,
        }

    except Exception as exc:
        duration_ms = round((time.monotonic() - start) * 1000, 2)
        result = {
            "status": "error",
            "error": str(exc),
            "stdout": "",
            "stderr": traceback.format_exc(),
            "returncode": 1,
            "duration_ms": duration_ms,
            "packages_installed": packages,
        }

    finally:
        # ── 6. Always destroy temp directory ─────────────────────────────
        if tmp_dir and os.path.exists(tmp_dir):
            shutil.rmtree(tmp_dir, ignore_errors=True)

    # ── 7. Log if session_id provided ─────────────────────────────────────
    if session_id:
        try:
            _dir = Path(__file__).resolve().parent
            sys.path.insert(0, str(_dir))
            from log_manager import log_tool_invocation  # type: ignore
            log_tool_invocation(
                session_id=session_id,
                tool_name="sandbox_runner",
                params={
                    "code_length": len(code),
                    "packages": packages,
                    "timeout": timeout,
                },
                result={
                    "status": result["status"],
                    "returncode": result.get("returncode"),
                    "stdout_length": len(result.get("stdout", "")),
                },
                duration_ms=result.get("duration_ms"),
            )
        except Exception:
            pass  # Logging failures must never break the tool result

    return result


# ---------------------------------------------------------------------------
# main() — supports ToolExecutor Strategy 1 (direct kwargs) and Strategy 2 (argparse)
# ---------------------------------------------------------------------------

def main(**kwargs) -> None:
    """
    Entry point for both execution strategies:
      Strategy 1: ToolExecutor calls main(**params) directly.
      Strategy 2: Called as __main__ → falls through to argparse.
    """
    # ── Windows UTF-8 encoding fix ─────────────────────────────────────────
    if sys.platform == "win32":
        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
        sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")

    # ── Strategy 1: Direct call from ToolExecutor ─────────────────────────
    if kwargs:
        code = kwargs.get("code", "")
        if not code:
            out = {"status": "error", "error": "Missing required parameter: code"}
            print(json.dumps(out, indent=2, ensure_ascii=False))
            sys.exit(1)

        packages = kwargs.get("packages", [])
        # ToolExecutor may pass a JSON string when relaying via subprocess
        if isinstance(packages, str):
            packages = json.loads(packages) if packages.strip() else []

        result = run_in_sandbox(
            code=code,
            packages=packages,
            timeout=int(kwargs.get("timeout", 60)),
            input_data=kwargs.get("input_data", "") or "",
            session_id=kwargs.get("session_id"),
        )
        print(json.dumps(result, indent=2, ensure_ascii=False))
        sys.exit(0 if result["status"] == "success" else 1)

    # ── Strategy 2: argparse / CLI ────────────────────────────────────────
    parser = argparse.ArgumentParser(
        description="sandbox_runner: run Python code in an isolated temporary venv",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument(
        "--code", required=True,
        help="Python source code to execute.",
    )
    parser.add_argument(
        "--packages", default="[]",
        help='JSON array of pip package strings, e.g. \'["numpy", "pandas"]\'. Default: []',
    )
    parser.add_argument(
        "--timeout", type=int, default=60,
        help="Script execution timeout in seconds (default: 60).",
    )
    parser.add_argument(
        "--input_data", default="",
        help="String passed as stdin to the script.",
    )
    parser.add_argument(
        "--session_id", default=None,
        help="Session ID for log_manager integration.",
    )

    args = parser.parse_args()

    # Parse packages JSON
    raw = args.packages.strip()
    packages = json.loads(raw) if raw not in ("", "[]") else []

    result = run_in_sandbox(
        code=args.code,
        packages=packages,
        timeout=args.timeout,
        input_data=args.input_data,
        session_id=args.session_id,
    )
    print(json.dumps(result, indent=2, ensure_ascii=False))
    sys.exit(0 if result["status"] == "success" else 1)


if __name__ == "__main__":
    main()
