#!/usr/bin/env python3
"""Launch the Overlord11 Tactical WebUI backend."""
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def main():
    host = "127.0.0.1"
    port = 8844
    print(f"🎯 Overlord11 Tactical WebUI → http://{host}:{port}")
    print(f"   API docs: http://{host}:{port}/docs")
    print(f"   Press Ctrl+C to stop\n")
    subprocess.run([
        sys.executable, "-m", "uvicorn",
        "webui.app:app",
        "--host", host,
        "--port", str(port),
        "--reload",
    ], cwd=str(ROOT), check=True)


if __name__ == "__main__":
    main()
