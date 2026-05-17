"""
Provider Health API — lightweight connectivity checks for all configured providers.

Each provider is tested with a minimal HTTP request (models list or a 1-token
generation).  Results are cached for 5 minutes to avoid hammering APIs on every
page load.  Failed providers are tracked with a timestamp so the engine's
fallback logic can skip them and retry after a cooldown.
"""

import json
import logging
import os
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from fastapi import APIRouter

router = APIRouter(tags=["health"])
log = logging.getLogger("overlord11.health")

_BASE_DIR = Path(__file__).resolve().parent.parent.parent
_CONFIG_PATH = _BASE_DIR / "config.json"

_CACHE_TTL_S = 300  # 5 minutes
_CHECK_TIMEOUT_S = 8

# In-process cache: provider_name → {status, latency_ms, checked_at, error}
_health_cache: dict[str, dict] = {}
_cache_ts: float = 0.0


def _load_config() -> dict:
    return json.loads(_CONFIG_PATH.read_text(encoding="utf-8"))


def _check_anthropic(cfg: dict) -> dict:
    """Check Anthropic: GET /v1/models with API key."""
    key = os.environ.get(cfg.get("api_key_env", ""), "")
    if not key:
        return {"status": "no_key", "latency_ms": None, "error": "API key not configured"}
    url = cfg.get("api_base", "https://api.anthropic.com/v1") + "/models"
    req = urllib.request.Request(url, headers={
        "x-api-key": key,
        "anthropic-version": "2023-06-01",
    })
    t0 = time.monotonic()
    try:
        with urllib.request.urlopen(req, timeout=_CHECK_TIMEOUT_S) as r:
            latency_ms = round((time.monotonic() - t0) * 1000)
            data = json.loads(r.read())
            model_count = len(data.get("data", []))
            return {"status": "healthy", "latency_ms": latency_ms, "error": None,
                    "model_count": model_count}
    except urllib.error.HTTPError as e:
        latency_ms = round((time.monotonic() - t0) * 1000)
        if e.code == 401:
            return {"status": "auth_error", "latency_ms": latency_ms, "error": "Invalid API key"}
        return {"status": "degraded", "latency_ms": latency_ms, "error": f"HTTP {e.code}"}
    except Exception as exc:
        latency_ms = round((time.monotonic() - t0) * 1000)
        return {"status": "unreachable", "latency_ms": latency_ms, "error": str(exc)[:120]}


def _check_gemini(cfg: dict) -> dict:
    """Check Gemini: GET /v1beta/models with API key."""
    key = os.environ.get(cfg.get("api_key_env", ""), "")
    if not key:
        return {"status": "no_key", "latency_ms": None, "error": "API key not configured"}
    base = cfg.get("api_base", "https://generativelanguage.googleapis.com/v1beta")
    url = f"{base}/models?key={key}&pageSize=5"
    t0 = time.monotonic()
    try:
        with urllib.request.urlopen(url, timeout=_CHECK_TIMEOUT_S) as r:
            latency_ms = round((time.monotonic() - t0) * 1000)
            data = json.loads(r.read())
            model_count = len(data.get("models", []))
            return {"status": "healthy", "latency_ms": latency_ms, "error": None,
                    "model_count": model_count}
    except urllib.error.HTTPError as e:
        latency_ms = round((time.monotonic() - t0) * 1000)
        if e.code in (400, 401, 403):
            return {"status": "auth_error", "latency_ms": latency_ms, "error": f"HTTP {e.code}: key invalid or quota exceeded"}
        return {"status": "degraded", "latency_ms": latency_ms, "error": f"HTTP {e.code}"}
    except Exception as exc:
        latency_ms = round((time.monotonic() - t0) * 1000)
        return {"status": "unreachable", "latency_ms": latency_ms, "error": str(exc)[:120]}


def _check_openai(cfg: dict) -> dict:
    """Check OpenAI: GET /v1/models with Bearer key."""
    key = os.environ.get(cfg.get("api_key_env", ""), "")
    if not key:
        return {"status": "no_key", "latency_ms": None, "error": "API key not configured"}
    url = cfg.get("api_base", "https://api.openai.com/v1") + "/models"
    req = urllib.request.Request(url, headers={"Authorization": f"Bearer {key}"})
    t0 = time.monotonic()
    try:
        with urllib.request.urlopen(req, timeout=_CHECK_TIMEOUT_S) as r:
            latency_ms = round((time.monotonic() - t0) * 1000)
            data = json.loads(r.read())
            model_count = len(data.get("data", []))
            return {"status": "healthy", "latency_ms": latency_ms, "error": None,
                    "model_count": model_count}
    except urllib.error.HTTPError as e:
        latency_ms = round((time.monotonic() - t0) * 1000)
        if e.code == 401:
            return {"status": "auth_error", "latency_ms": latency_ms, "error": "Invalid API key"}
        return {"status": "degraded", "latency_ms": latency_ms, "error": f"HTTP {e.code}"}
    except Exception as exc:
        latency_ms = round((time.monotonic() - t0) * 1000)
        return {"status": "unreachable", "latency_ms": latency_ms, "error": str(exc)[:120]}


_CHECKERS = {
    "anthropic": _check_anthropic,
    "gemini": _check_gemini,
    "openai": _check_openai,
}


def _run_health_checks(force: bool = False) -> dict:
    global _health_cache, _cache_ts
    now = time.monotonic()
    if not force and _health_cache and (now - _cache_ts) < _CACHE_TTL_S:
        return _health_cache

    cfg = _load_config()
    providers_cfg = cfg.get("providers", {})
    active = providers_cfg.get("active", "")
    results = {}

    for name, provider_cfg in providers_cfg.items():
        if name == "active" or not isinstance(provider_cfg, dict):
            continue
        checker = _CHECKERS.get(name)
        if checker is None:
            results[name] = {"status": "unknown", "latency_ms": None, "error": "No checker"}
            continue
        try:
            result = checker(provider_cfg)
        except Exception as exc:
            result = {"status": "error", "latency_ms": None, "error": str(exc)[:120]}

        result["active"] = (name == active)
        result["checked_at"] = datetime.now(timezone.utc).isoformat()
        result["model"] = provider_cfg.get("model", "")
        result["model_count"] = result.get("model_count", len(provider_cfg.get("available_models", {})))
        results[name] = result

    _health_cache = results
    _cache_ts = now
    return results


@router.get("/api/providers/health")
async def provider_health(force: bool = False):
    """
    Return health status for all configured providers.

    Query params:
        force=true  — bypass 5-minute cache and run live checks immediately.

    Response per provider:
        status:      healthy | degraded | auth_error | no_key | unreachable | unknown
        latency_ms:  round-trip time in milliseconds (null if not reached)
        model_count: number of models available on this provider
        model:       currently selected model
        active:      whether this is the active provider
        checked_at:  ISO timestamp of this check
        error:       error message if status != healthy
    """
    results = _run_health_checks(force=force)
    summary_status = "healthy"
    for r in results.values():
        if r.get("status") != "healthy":
            summary_status = "degraded"
            break
    return {
        "summary": summary_status,
        "cached": not force and bool(_health_cache),
        "cache_age_s": round(time.monotonic() - _cache_ts) if _cache_ts else None,
        "providers": results,
    }
