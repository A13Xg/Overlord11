"""Async provider health probes with TTL cache and Gemini rate-limit fallback.

Gemini 429 / RESOURCE_EXHAUSTED handling
-----------------------------------------
When Gemini returns HTTP 429, the response body contains:
  {"error": {"code": 429, "status": "RESOURCE_EXHAUSTED", "details": [
      {"@type": "...RetryInfo", "retryDelay": "15s"},
      {"@type": "...QuotaFailure", "violations": [{"quotaMetric": "..."}]}
  ]}}

We detect this and walk the GEMINI_FALLBACK_CHAIN (best → worst) until a model
succeeds, capping retry_after from the RetryInfo detail if present.
"""
from __future__ import annotations

import asyncio
import json
import os
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional

try:
    import httpx
    _HTTPX_AVAILABLE = True
except ImportError:
    _HTTPX_AVAILABLE = False

from .logging_config import get_webui_logger

log = get_webui_logger()
CONFIG_FILE = Path(__file__).resolve().parent.parent / "config.json"

# How long to probe before giving up (seconds)
PROBE_TIMEOUT = 10.0
# How long cached results are valid
CACHE_TTL = 300.0

# Progressive Gemini fallback chain: preferred → fallback models in order.
# When a rate limit (429 RESOURCE_EXHAUSTED) is hit, we try the next entry.
GEMINI_FALLBACK_CHAIN: List[str] = [
    "gemini-2.5-pro",
    "gemini-2.5-flash",
    "gemini-2.5-flash-lite",
    "gemini-2.0-flash",
    "gemini-1.5-flash",
    "gemini-1.5-pro",
]


@dataclass
class ProviderResult:
    name: str
    status: str          # "ok" | "no_key" | "error" | "checking" | "no_config"
    models: List[str] = field(default_factory=list)
    error: Optional[str] = None
    checked_at: Optional[float] = None
    latency_ms: Optional[int] = None
    # Gemini-specific: which model is currently active after rate-limit fallback
    active_model_override: Optional[str] = None
    # Seconds until rate-limit clears (from RetryInfo detail)
    rate_limit_retry_after: Optional[float] = None


# Module-level result cache — plain dict, GIL-safe for simple read/write
_cache: Dict[str, ProviderResult] = {}


# ── Helpers ───────────────────────────────────────────────────────────────────

def _load_provider_cfg() -> dict:
    try:
        return json.loads(CONFIG_FILE.read_text(encoding="utf-8")).get("providers", {})
    except Exception as exc:
        log.warning("provider_health: failed to load config", extra={"exc": str(exc)})
        return {}


def _parse_gemini_429(body: str) -> Optional[float]:
    """Return retry_after seconds from a Gemini 429 body, or None."""
    try:
        data = json.loads(body)
        for detail in data.get("error", {}).get("details", []):
            if "retryDelay" in detail:
                delay_str: str = detail["retryDelay"]  # e.g. "15.002s"
                return float(delay_str.rstrip("s"))
    except Exception:
        pass
    return None


def _is_rate_limited(status_code: int, body: str) -> bool:
    if status_code != 429:
        return False
    try:
        data = json.loads(body)
        return data.get("error", {}).get("status") == "RESOURCE_EXHAUSTED"
    except Exception:
        return True  # 429 is always a rate limit regardless of body


# ── Per-provider probers ──────────────────────────────────────────────────────

async def _probe_gemini(name: str, pcfg: dict) -> ProviderResult:
    if not _HTTPX_AVAILABLE:
        return ProviderResult(name, "error", error="httpx not installed")
    key_env = pcfg.get("api_key_env", "GOOGLE_GEMINI_API_KEY")
    api_key = os.environ.get(key_env, "")
    if not api_key:
        return ProviderResult(name, "no_key",
                              error=f"Env var {key_env} not set. "
                                    f"Copy .env.example → .env and add your key.")
    base = pcfg.get("api_base", "https://generativelanguage.googleapis.com/v1beta")
    t0 = time.monotonic()
    try:
        async with httpx.AsyncClient(timeout=PROBE_TIMEOUT) as client:
            r = await client.get(f"{base}/models", params={"key": api_key})
        ms = int((time.monotonic() - t0) * 1000)
        if r.status_code == 200:
            models = [
                m.get("name", "").split("/")[-1]
                for m in r.json().get("models", [])
                if m.get("name")
            ]
            log.info("Gemini probe OK", extra={
                "provider": name, "model_count": len(models), "latency_ms": ms,
            })
            return ProviderResult(name, "ok", models=sorted(models),
                                  checked_at=time.time(), latency_ms=ms)
        body = r.text
        if _is_rate_limited(r.status_code, body):
            retry_after = _parse_gemini_429(body)
            log.warning("Gemini probe: rate limited",
                        extra={"provider": name, "retry_after": retry_after})
            return ProviderResult(name, "error",
                                  error=f"Rate limited (429 RESOURCE_EXHAUSTED). "
                                        f"Retry after: {retry_after}s",
                                  checked_at=time.time(), latency_ms=ms,
                                  rate_limit_retry_after=retry_after)
        log.warning("Gemini probe: non-200", extra={"provider": name, "status": r.status_code})
        return ProviderResult(name, "error",
                              error=f"HTTP {r.status_code}: {body[:300]}",
                              checked_at=time.time(), latency_ms=ms)
    except Exception as exc:
        log.error("Gemini probe: exception", extra={"provider": name, "exc": str(exc)})
        return ProviderResult(name, "error", error=str(exc), checked_at=time.time())


async def _probe_openai(name: str, pcfg: dict) -> ProviderResult:
    if not _HTTPX_AVAILABLE:
        return ProviderResult(name, "error", error="httpx not installed")
    key_env = pcfg.get("api_key_env", "OPENAI_API_KEY")
    api_key = os.environ.get(key_env, "")
    if not api_key:
        return ProviderResult(name, "no_key",
                              error=f"Env var {key_env} not set. "
                                    f"Copy .env.example → .env and add your key.")
    base = pcfg.get("api_base", "https://api.openai.com/v1")
    t0 = time.monotonic()
    try:
        async with httpx.AsyncClient(timeout=PROBE_TIMEOUT) as client:
            r = await client.get(f"{base}/models",
                                 headers={"Authorization": f"Bearer {api_key}"})
        ms = int((time.monotonic() - t0) * 1000)
        if r.status_code == 200:
            models = sorted(m["id"] for m in r.json().get("data", []) if m.get("id"))
            log.info("OpenAI probe OK", extra={
                "provider": name, "model_count": len(models), "latency_ms": ms,
            })
            return ProviderResult(name, "ok", models=models,
                                  checked_at=time.time(), latency_ms=ms)
        log.warning("OpenAI probe: non-200",
                    extra={"provider": name, "status": r.status_code})
        return ProviderResult(name, "error",
                              error=f"HTTP {r.status_code}: {r.text[:300]}",
                              checked_at=time.time(), latency_ms=ms)
    except Exception as exc:
        log.error("OpenAI probe: exception", extra={"provider": name, "exc": str(exc)})
        return ProviderResult(name, "error", error=str(exc), checked_at=time.time())


async def _probe_anthropic(name: str, pcfg: dict) -> ProviderResult:
    if not _HTTPX_AVAILABLE:
        return ProviderResult(name, "error", error="httpx not installed")
    key_env = pcfg.get("api_key_env", "ANTHROPIC_API_KEY")
    api_key = os.environ.get(key_env, "")
    if not api_key:
        return ProviderResult(name, "no_key",
                              error=f"Env var {key_env} not set. "
                                    f"Copy .env.example → .env and add your key.")
    base = pcfg.get("api_base", "https://api.anthropic.com/v1")
    t0 = time.monotonic()
    try:
        async with httpx.AsyncClient(timeout=PROBE_TIMEOUT) as client:
            r = await client.get(
                f"{base}/models",
                headers={"x-api-key": api_key, "anthropic-version": "2023-06-01"},
            )
        ms = int((time.monotonic() - t0) * 1000)
        if r.status_code == 200:
            models = [m["id"] for m in r.json().get("data", []) if m.get("id")]
            log.info("Anthropic probe OK", extra={
                "provider": name, "model_count": len(models), "latency_ms": ms,
            })
            return ProviderResult(name, "ok", models=models,
                                  checked_at=time.time(), latency_ms=ms)
        log.warning("Anthropic probe: non-200",
                    extra={"provider": name, "status": r.status_code})
        return ProviderResult(name, "error",
                              error=f"HTTP {r.status_code}: {r.text[:300]}",
                              checked_at=time.time(), latency_ms=ms)
    except Exception as exc:
        log.error("Anthropic probe: exception", extra={"provider": name, "exc": str(exc)})
        return ProviderResult(name, "error", error=str(exc), checked_at=time.time())


_PROBERS = {
    "gemini": _probe_gemini,
    "openai": _probe_openai,
    "anthropic": _probe_anthropic,
}


# ── Public API ────────────────────────────────────────────────────────────────

async def probe_all(force: bool = False) -> Dict[str, dict]:
    """Probe all configured providers concurrently; return serialisable status dict."""
    providers_cfg = _load_provider_cfg()
    now = time.time()
    tasks: Dict[str, asyncio.Task] = {}

    for name, prober in _PROBERS.items():
        cached = _cache.get(name)
        stale = not cached or not cached.checked_at or (now - cached.checked_at) >= CACHE_TTL
        if force or stale:
            if name in providers_cfg:
                tasks[name] = asyncio.ensure_future(prober(name, providers_cfg[name]))
            else:
                _cache[name] = ProviderResult(name, "no_config",
                                              error="Provider not in config.json")

    if tasks:
        results = await asyncio.gather(*tasks.values(), return_exceptions=True)
        for name, result in zip(tasks.keys(), results):
            if isinstance(result, Exception):
                _cache[name] = ProviderResult(name, "error", error=str(result),
                                              checked_at=now)
                log.error("Provider probe raised exception",
                           extra={"provider": name, "exc": str(result)})
            else:
                _cache[name] = result

    return _serialise()


def get_cached() -> Dict[str, dict]:
    """Return current cached status without re-probing."""
    return _serialise()


def get_gemini_fallback_model(preferred_model: str) -> Optional[str]:
    """Return the next model to try when preferred_model is rate-limited.

    Walks GEMINI_FALLBACK_CHAIN from the position of preferred_model downward.
    Returns None if already at the end of the chain.
    """
    try:
        idx = GEMINI_FALLBACK_CHAIN.index(preferred_model)
    except ValueError:
        # Preferred model not in chain — start from the beginning
        idx = -1
    next_idx = idx + 1
    if next_idx < len(GEMINI_FALLBACK_CHAIN):
        fallback = GEMINI_FALLBACK_CHAIN[next_idx]
        log.warning(
            f"Gemini rate limit on {preferred_model!r} — falling back to {fallback!r}",
            extra={"event": "gemini_fallback", "from": preferred_model, "to": fallback},
        )
        return fallback
    log.error(
        f"Gemini rate limit on {preferred_model!r} — no more fallback models available",
        extra={"event": "gemini_fallback_exhausted", "model": preferred_model},
    )
    return None


def get_rate_limit_retry_after(provider: str) -> Optional[float]:
    """Return seconds until rate limit clears for a provider, or None."""
    ps = _cache.get(provider)
    if ps and ps.rate_limit_retry_after is not None:
        elapsed = time.time() - (ps.checked_at or 0)
        remaining = ps.rate_limit_retry_after - elapsed
        return max(0.0, remaining) if remaining > 0 else None
    return None


def _serialise() -> Dict[str, dict]:
    out: Dict[str, dict] = {}
    for name in _PROBERS:
        ps = _cache.get(name)
        if ps:
            out[name] = {
                "status": ps.status,
                "models": ps.models,
                "error": ps.error,
                "checked_at": ps.checked_at,
                "latency_ms": ps.latency_ms,
                "active_model_override": ps.active_model_override,
                "rate_limit_retry_after": ps.rate_limit_retry_after,
            }
        else:
            out[name] = {
                "status": "checking",
                "models": [],
                "error": None,
                "checked_at": None,
                "latency_ms": None,
                "active_model_override": None,
                "rate_limit_retry_after": None,
            }
    return out
