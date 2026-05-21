#!/usr/bin/env python3
"""Launch the Overlord11 Tactical WebUI."""
import sys
import os

# Add project root to path
_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, _PROJECT_ROOT)

# ── Load .env before any imports ────────────────────────────────────────────
_env_file = os.path.join(_PROJECT_ROOT, ".env")
if os.path.exists(_env_file):
    try:
        with open(_env_file, encoding="utf-8") as _f:
            for _line in _f:
                _line = _line.strip()
                if not _line or _line.startswith("#") or "=" not in _line:
                    continue
                _k, _, _v = _line.partition("=")
                _k = _k.strip()
                _v = _v.strip().strip('"').strip("'")
                if _k and _k not in os.environ:
                    os.environ[_k] = _v
    except OSError:
        pass
# ─────────────────────────────────────────────────────────────────────────────

import uvicorn


def _check_env() -> None:
    """Warn if no API keys are configured."""
    _KEY_VARS = [
        ("ANTHROPIC_API_KEY", "Anthropic / Claude"),
        ("GEMINI_API_KEY", "Google Gemini"),
        ("OPENAI_API_KEY", "OpenAI / GPT"),
    ]
    configured = [name for var, name in _KEY_VARS if os.environ.get(var, "").strip()]
    if not configured:
        print(
            "[OVERLORD11] ⚠ WARNING: No API keys found in environment or .env file.\n"
            "             At least one of ANTHROPIC_API_KEY, GEMINI_API_KEY, or OPENAI_API_KEY\n"
            "             must be set for agents to run. Use the setup wizard at http://localhost:{port}\n"
            "             or edit .env in the project root."
        )
    else:
        print(f"[OVERLORD11] API keys configured: {', '.join(configured)}")


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 7900))
    _check_env()
    print(f"[OVERLORD11] WebUI starting on http://localhost:{port}")
    uvicorn.run("backend.main:app", host="0.0.0.0", port=port, reload=False)
