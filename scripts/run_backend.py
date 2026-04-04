#!/usr/bin/env python3
"""
scripts/run_backend.py
=======================
Launch the Overlord11 FastAPI backend.

Usage
-----
    python scripts/run_backend.py [--port PORT] [--reload]

Default port: 8080
"""

import argparse
import os
import subprocess
import sys
from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parent.parent


def main():
    parser = argparse.ArgumentParser(description="Start the Overlord11 backend API")
    parser.add_argument("--port", type=int, default=int(os.environ.get("PORT", 8080)))
    parser.add_argument("--host", default=os.environ.get("HOST", "0.0.0.0"))
    parser.add_argument("--reload", action="store_true", help="Enable auto-reload (dev mode)")
    parser.add_argument("--no-install", action="store_true", help="Skip pip install")
    args = parser.parse_args()

    # Install dependencies
    if not args.no_install:
        req_file = _PROJECT_ROOT / "requirements-backend.txt"
        if req_file.exists():
            print("[overlord11] Installing backend dependencies...")
            subprocess.check_call(
                [sys.executable, "-m", "pip", "install", "-r", str(req_file), "--quiet"]
            )

    # Set working directory to project root
    os.chdir(_PROJECT_ROOT)

    # Ensure project root is on PYTHONPATH
    env = os.environ.copy()
    existing = env.get("PYTHONPATH", "")
    env["PYTHONPATH"] = f"{_PROJECT_ROOT}{os.pathsep}{existing}" if existing else str(_PROJECT_ROOT)

    cmd = [
        sys.executable, "-m", "uvicorn",
        "backend.main:app",
        "--host", args.host,
        "--port", str(args.port),
    ]
    if args.reload:
        cmd.append("--reload")

    print(f"[overlord11] Backend starting at http://{args.host}:{args.port}")
    print(f"[overlord11] API docs: http://{args.host}:{args.port}/api/docs")

    os.execve(sys.executable, cmd, env)


if __name__ == "__main__":
    main()
