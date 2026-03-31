#!/usr/bin/env python3
"""
scripts/run_webui.py — Entry point for the Overlord11 Tactical WebUI.

Usage:
    python scripts/run_webui.py [--host HOST] [--port PORT] [--reload]

Defaults: host=0.0.0.0, port=7900
"""

import argparse
import os
import sys
from pathlib import Path

# Add project root to path so `webui` package is importable
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))


def main() -> None:
    parser = argparse.ArgumentParser(description="Overlord11 Tactical WebUI server")
    parser.add_argument("--host", default="0.0.0.0", help="Bind host (default: 0.0.0.0)")
    parser.add_argument("--port", type=int, default=7900, help="Bind port (default: 7900)")
    parser.add_argument(
        "--reload",
        action="store_true",
        help="Enable uvicorn hot-reload (development only)",
    )
    args = parser.parse_args()

    # Ensure workspace/jobs exists
    jobs_dir = PROJECT_ROOT / "workspace" / "jobs"
    jobs_dir.mkdir(parents=True, exist_ok=True)

    try:
        import uvicorn  # noqa: F401
    except ImportError:
        print(
            "ERROR: uvicorn not found. Install dependencies first:\n"
            "  pip install -r requirements-webui.txt",
            file=sys.stderr,
        )
        sys.exit(1)

    import uvicorn

    print(f"  Overlord11 Tactical WebUI")
    print(f"  http://{args.host}:{args.port}")
    print(f"  API docs: http://{args.host}:{args.port}/docs")
    print()

    uvicorn.run(
        "webui.app:app",
        host=args.host,
        port=args.port,
        reload=args.reload,
        log_level="info",
    )


if __name__ == "__main__":
    main()
