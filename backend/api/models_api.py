"""
backend/api/models_api.py
==========================
Model management endpoints.

GET  /api/models              List models for active provider
GET  /api/models/{provider}   List models for a specific provider
GET  /api/providers/status    Provider reachability status
GET  /api/config              Get current provider config
PUT  /api/config              Update active provider/model
"""

import json
import os
from pathlib import Path
from typing import Any, Dict, Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

router = APIRouter(tags=["models"])

_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
_CONFIG_PATH = _PROJECT_ROOT / "config.json"
_PREFS_PATH = _PROJECT_ROOT / "workspace" / ".webui_prefs.json"


def _load_config() -> Dict[str, Any]:
    try:
        return json.loads(_CONFIG_PATH.read_text())
    except (OSError, json.JSONDecodeError):
        return {}


def _load_prefs() -> Dict[str, Any]:
    try:
        if _PREFS_PATH.exists():
            return json.loads(_PREFS_PATH.read_text())
    except (OSError, json.JSONDecodeError):
        pass
    return {}


def _save_prefs(prefs: Dict[str, Any]) -> None:
    _PREFS_PATH.parent.mkdir(parents=True, exist_ok=True)
    _PREFS_PATH.write_text(json.dumps(prefs, indent=2))


class UpdateConfigRequest(BaseModel):
    provider: Optional[str] = None
    model: Optional[str] = None


@router.get("/api/models")
def list_models_active():
    """List models for the active provider."""
    cfg = _load_config()
    active = cfg.get("providers", {}).get("active", "anthropic")
    models = cfg.get("providers", {}).get(active, {}).get("available_models", {})
    current = cfg.get("providers", {}).get(active, {}).get("model", "")
    # Override with user prefs
    prefs = _load_prefs()
    if prefs.get("provider") == active and prefs.get("model"):
        current = prefs["model"]
    return {
        "provider": active,
        "current_model": current,
        "models": [
            {"id": mid, "description": desc, "active": mid == current}
            for mid, desc in models.items()
        ],
    }


@router.get("/api/models/{provider}")
def list_models_for_provider(provider: str):
    cfg = _load_config()
    prov_cfg = cfg.get("providers", {}).get(provider)
    if not prov_cfg:
        raise HTTPException(404, f"Provider {provider!r} not found")
    models = prov_cfg.get("available_models", {})
    current = prov_cfg.get("model", "")
    return {
        "provider": provider,
        "current_model": current,
        "models": [
            {"id": mid, "description": desc, "active": mid == current}
            for mid, desc in models.items()
        ],
    }


@router.get("/api/providers/status")
def providers_status():
    """Return reachability status for all providers."""
    cfg = _load_config()
    active = cfg.get("providers", {}).get("active", "anthropic")
    status = {}
    for prov, prov_cfg in cfg.get("providers", {}).items():
        if prov == "active" or not isinstance(prov_cfg, dict):
            continue
        api_key_env = prov_cfg.get("api_key_env", "")
        has_key = bool(os.environ.get(api_key_env, ""))
        status[prov] = {
            "status": "green" if has_key else "red",
            "is_active": prov == active,
            "model": prov_cfg.get("model", ""),
        }
    return status


@router.get("/api/config")
def get_config():
    prefs = _load_prefs()
    cfg = _load_config()
    active = prefs.get("provider") or cfg.get("providers", {}).get("active", "anthropic")
    prov_cfg = cfg.get("providers", {}).get(active, {})
    model = prefs.get("model") or prov_cfg.get("model", "")
    return {"provider": active, "model": model}


@router.put("/api/config")
def update_config(body: UpdateConfigRequest):
    cfg = _load_config()
    prefs = _load_prefs()

    if body.provider:
        if body.provider not in cfg.get("providers", {}):
            raise HTTPException(400, f"Unknown provider {body.provider!r}")
        prefs["provider"] = body.provider

    if body.model:
        active = prefs.get("provider") or cfg.get("providers", {}).get("active", "anthropic")
        available = cfg.get("providers", {}).get(active, {}).get("available_models", {})
        if body.model not in available:
            raise HTTPException(400, f"Model {body.model!r} not available for provider {active!r}")
        prefs["model"] = body.model

    _save_prefs(prefs)
    return prefs


@router.delete("/api/config/selection")
def reset_config():
    if _PREFS_PATH.exists():
        _PREFS_PATH.unlink()
    return {"message": "Selection reset to config defaults"}
