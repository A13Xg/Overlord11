"""
Providers API — provider/model management and config selection.
"""

import json
from pathlib import Path

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

router = APIRouter(tags=["providers"])

_BASE_DIR = Path(__file__).resolve().parent.parent.parent
_CONFIG_PATH = _BASE_DIR / "config.json"
_WORKSPACE_DIR = _BASE_DIR / "workspace"
_PREFS_FILE = _WORKSPACE_DIR / ".webui_prefs.json"


def _load_config() -> dict:
    return json.loads(_CONFIG_PATH.read_text(encoding="utf-8"))


def _load_prefs() -> dict:
    if _PREFS_FILE.exists():
        try:
            return json.loads(_PREFS_FILE.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            pass
    cfg = _load_config()
    active = cfg.get("providers", {}).get("active", "anthropic")
    provider_cfg = cfg.get("providers", {}).get(active, {})
    return {
        "provider": active,
        "model": provider_cfg.get("model", ""),
    }


def _save_prefs(prefs: dict) -> None:
    _WORKSPACE_DIR.mkdir(parents=True, exist_ok=True)
    _PREFS_FILE.write_text(
        json.dumps(prefs, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )


# ------------------------------------------------------------------
# Providers list
# ------------------------------------------------------------------

@router.get("/api/providers")
async def list_providers():
    cfg = _load_config()
    providers_cfg = cfg.get("providers", {})
    active = providers_cfg.get("active", "")
    result = []
    for name, data in providers_cfg.items():
        if name == "active":
            continue
        if not isinstance(data, dict):
            continue
        result.append({
            "name": name,
            "active": name == active,
            "model": data.get("model", ""),
            "available_models": data.get("available_models", {}),
            "api_key_env": data.get("api_key_env", ""),
        })
    return result


@router.get("/api/providers/status")
async def providers_status():
    cfg = _load_config()
    providers_cfg = cfg.get("providers", {})
    active = providers_cfg.get("active", "")
    active_cfg = providers_cfg.get(active, {})
    return {
        "active_provider": active,
        "model": active_cfg.get("model", ""),
        "status": "configured",
    }


# ------------------------------------------------------------------
# Config / selection
# ------------------------------------------------------------------

@router.get("/api/config/selection")
async def get_selection():
    return _load_prefs()


class SelectionRequest(BaseModel):
    provider: str
    model: str


@router.put("/api/config/selection")
async def update_selection(req: SelectionRequest):
    cfg = _load_config()
    providers_cfg = cfg.get("providers", {})

    if req.provider not in providers_cfg or req.provider == "active":
        raise HTTPException(status_code=400, detail=f"Unknown provider: {req.provider}")

    provider_cfg = providers_cfg[req.provider]
    available = provider_cfg.get("available_models", {})
    if req.model not in available:
        raise HTTPException(status_code=400, detail=f"Unknown model: {req.model}")

    prefs = {"provider": req.provider, "model": req.model}
    _save_prefs(prefs)
    return prefs
