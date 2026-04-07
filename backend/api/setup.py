"""
Setup Wizard API — first-run detection and configuration.

The wizard runs once on first server start.  Completion is tracked by
writing  workspace/.setup_complete  (a JSON file with metadata).

Endpoints:
  GET  /api/setup/status          — is setup complete? what step?
  POST /api/setup/validate-key    — test connectivity for a provider API key
  POST /api/setup/save-keys       — persist API keys to the OS environment
                                    profile / .env file in project root
  POST /api/setup/complete        — mark wizard as done
  POST /api/setup/reset           — (dev) clear completion flag
"""

import json
import logging
import os
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

router = APIRouter(prefix="/api/setup", tags=["setup"])
log = logging.getLogger("overlord11.setup")

_BASE_DIR = Path(__file__).resolve().parent.parent.parent
_WORKSPACE_DIR = _BASE_DIR / "workspace"
_SETUP_FILE = _WORKSPACE_DIR / ".setup_complete"
_ENV_FILE = _BASE_DIR / ".env"
_CONFIG_PATH = _BASE_DIR / "config.json"

_KEY_TIMEOUT_S = 8


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _load_config() -> dict:
    return json.loads(_CONFIG_PATH.read_text(encoding="utf-8"))


def _is_setup_complete() -> bool:
    return _SETUP_FILE.exists()


def _which_keys_present() -> dict[str, bool]:
    """Check which provider API keys are present in the current environment."""
    cfg = _load_config()
    result = {}
    for name, data in cfg.get("providers", {}).items():
        if name == "active" or not isinstance(data, dict):
            continue
        env_var = data.get("api_key_env", "")
        result[name] = bool(env_var and os.environ.get(env_var, "").strip())
    return result


def _write_env_key(env_var: str, value: str) -> None:
    """Upsert an environment variable in .env file and set it in os.environ."""
    lines: list[str] = []
    if _ENV_FILE.exists():
        lines = _ENV_FILE.read_text(encoding="utf-8").splitlines()

    # Remove existing entry for this key
    lines = [ln for ln in lines if not ln.startswith(f"{env_var}=")]
    lines.append(f"{env_var}={value}")
    _ENV_FILE.write_text("\n".join(lines) + "\n", encoding="utf-8")

    # Also set in current process so health checks immediately pick it up
    os.environ[env_var] = value


# ---------------------------------------------------------------------------
# Key validation (lightweight connectivity test per provider)
# ---------------------------------------------------------------------------

def _validate_key_anthropic(key: str, base_url: str) -> dict:
    url = base_url.rstrip("/") + "/models"
    req = urllib.request.Request(url, headers={
        "x-api-key": key,
        "anthropic-version": "2023-06-01",
    })
    t0 = time.monotonic()
    try:
        with urllib.request.urlopen(req, timeout=_KEY_TIMEOUT_S) as r:
            latency_ms = round((time.monotonic() - t0) * 1000)
            json.loads(r.read())
            return {"valid": True, "latency_ms": latency_ms, "error": None}
    except urllib.error.HTTPError as e:
        latency_ms = round((time.monotonic() - t0) * 1000)
        if e.code == 401:
            return {"valid": False, "latency_ms": latency_ms, "error": "Invalid API key (401)"}
        return {"valid": False, "latency_ms": latency_ms, "error": f"HTTP {e.code}"}
    except Exception as exc:
        return {"valid": False, "latency_ms": None, "error": str(exc)[:120]}


def _validate_key_gemini(key: str, base_url: str) -> dict:
    url = f"{base_url.rstrip('/')}/models?key={key}&pageSize=1"
    t0 = time.monotonic()
    try:
        with urllib.request.urlopen(url, timeout=_KEY_TIMEOUT_S) as r:
            latency_ms = round((time.monotonic() - t0) * 1000)
            json.loads(r.read())
            return {"valid": True, "latency_ms": latency_ms, "error": None}
    except urllib.error.HTTPError as e:
        latency_ms = round((time.monotonic() - t0) * 1000)
        return {"valid": False, "latency_ms": latency_ms, "error": f"HTTP {e.code}"}
    except Exception as exc:
        return {"valid": False, "latency_ms": None, "error": str(exc)[:120]}


def _validate_key_openai(key: str, base_url: str) -> dict:
    url = base_url.rstrip("/") + "/models"
    req = urllib.request.Request(url, headers={"Authorization": f"Bearer {key}"})
    t0 = time.monotonic()
    try:
        with urllib.request.urlopen(req, timeout=_KEY_TIMEOUT_S) as r:
            latency_ms = round((time.monotonic() - t0) * 1000)
            json.loads(r.read())
            return {"valid": True, "latency_ms": latency_ms, "error": None}
    except urllib.error.HTTPError as e:
        latency_ms = round((time.monotonic() - t0) * 1000)
        if e.code == 401:
            return {"valid": False, "latency_ms": latency_ms, "error": "Invalid API key (401)"}
        return {"valid": False, "latency_ms": latency_ms, "error": f"HTTP {e.code}"}
    except Exception as exc:
        return {"valid": False, "latency_ms": None, "error": str(exc)[:120]}


_VALIDATORS = {
    "anthropic": _validate_key_anthropic,
    "gemini": _validate_key_gemini,
    "openai": _validate_key_openai,
}


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@router.get("/status")
async def setup_status():
    """
    Return current setup state.

    Response:
        complete:       whether the wizard has been finished
        keys_present:   dict of provider → bool (key in env)
        any_key:        True if at least one provider key is set
        completed_at:   ISO timestamp when setup was completed (or null)
    """
    keys = _which_keys_present()
    completed_at = None
    if _SETUP_FILE.exists():
        try:
            meta = json.loads(_SETUP_FILE.read_text(encoding="utf-8"))
            completed_at = meta.get("completed_at")
        except Exception:
            completed_at = None

    return {
        "complete": _is_setup_complete(),
        "keys_present": keys,
        "any_key": any(keys.values()),
        "completed_at": completed_at,
    }


class ValidateKeyRequest(BaseModel):
    provider: str
    api_key: str


@router.post("/validate-key")
async def validate_key(req: ValidateKeyRequest):
    """
    Test whether an API key is valid by making a lightweight request to
    the provider's models endpoint.

    Does NOT persist the key — call /save-keys to persist.
    """
    cfg = _load_config()
    provider_cfg = cfg.get("providers", {}).get(req.provider)
    if provider_cfg is None or not isinstance(provider_cfg, dict):
        raise HTTPException(status_code=400, detail=f"Unknown provider: {req.provider}")

    validator = _VALIDATORS.get(req.provider)
    if validator is None:
        raise HTTPException(status_code=400, detail=f"No validator for provider: {req.provider}")

    base_url = provider_cfg.get("api_base", "")
    result = validator(req.api_key.strip(), base_url)
    result["provider"] = req.provider
    return result


class SaveKeysRequest(BaseModel):
    keys: dict[str, str]   # provider_name → api_key_value


@router.post("/save-keys")
async def save_keys(req: SaveKeysRequest):
    """
    Persist one or more API keys.

    Keys are written to the project-root .env file and loaded into the
    current process environment so they take effect immediately without
    a server restart.

    Request body:
        { "keys": { "anthropic": "sk-ant-...", "gemini": "AIza..." } }
    """
    cfg = _load_config()
    saved = []
    errors = []

    for provider_name, key_value in req.keys.items():
        provider_cfg = cfg.get("providers", {}).get(provider_name)
        if not isinstance(provider_cfg, dict):
            errors.append(f"Unknown provider: {provider_name}")
            continue
        env_var = provider_cfg.get("api_key_env", "")
        if not env_var:
            errors.append(f"No env var configured for {provider_name}")
            continue
        if not key_value.strip():
            errors.append(f"Empty key for {provider_name} — skipped")
            continue
        try:
            _write_env_key(env_var, key_value.strip())
            saved.append(provider_name)
        except Exception as exc:
            errors.append(f"Failed to save {provider_name}: {exc}")

    return {"saved": saved, "errors": errors}


class CompleteSetupRequest(BaseModel):
    active_provider: str = ""
    active_model: str = ""


@router.post("/complete")
async def complete_setup(req: CompleteSetupRequest):
    """
    Mark the setup wizard as complete.

    Optionally sets the active provider and model in config.json.
    """
    cfg = _load_config()

    if req.active_provider:
        providers = cfg.get("providers", {})
        if req.active_provider in providers and req.active_provider != "active":
            cfg["providers"]["active"] = req.active_provider
            if req.active_model:
                available = providers[req.active_provider].get("available_models", {})
                if req.active_model in available:
                    cfg["providers"][req.active_provider]["model"] = req.active_model
            _CONFIG_PATH.write_text(
                json.dumps(cfg, indent=2, ensure_ascii=False) + "\n",
                encoding="utf-8",
            )

    _WORKSPACE_DIR.mkdir(parents=True, exist_ok=True)
    meta = {
        "completed_at": datetime.now(timezone.utc).isoformat(),
        "active_provider": req.active_provider or cfg.get("providers", {}).get("active", ""),
    }
    _SETUP_FILE.write_text(json.dumps(meta, indent=2), encoding="utf-8")
    log.info("Setup wizard completed: %s", meta)

    return {"status": "complete", **meta}


@router.post("/reset")
async def reset_setup():
    """Reset setup state (development use only)."""
    if _SETUP_FILE.exists():
        _SETUP_FILE.unlink()
    return {"status": "reset", "message": "Setup state cleared — wizard will reappear on next load"}
