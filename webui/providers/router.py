"""
webui/providers/router.py — Provider selection and routing.

Reads config.json to build the appropriate provider adapter.
Falls back through the configured fallback order.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from .base import LLMConfigError, LLMProvider
from .anthropic_adapter import AnthropicAdapter
from .gemini_adapter import GeminiAdapter
from .openai_adapter import OpenAIAdapter

_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
_CONFIG_PATH = _PROJECT_ROOT / "config.json"

_ADAPTER_MAP = {
    "anthropic": AnthropicAdapter,
    "gemini": GeminiAdapter,
    "openai": OpenAIAdapter,
}


def _load_config() -> dict[str, Any]:
    if _CONFIG_PATH.exists():
        return json.loads(_CONFIG_PATH.read_text(encoding="utf-8"))
    return {}


def get_provider(provider_name: str | None = None, model: str | None = None) -> LLMProvider:
    """
    Build and return a provider adapter.

    Parameters
    ----------
    provider_name:
        Override; defaults to config.json providers.active.
    model:
        Override; defaults to the provider's configured model.

    Raises
    ------
    LLMConfigError
        If provider_name is unknown.
    """
    cfg = _load_config()
    providers_cfg = cfg.get("providers", {})
    active = provider_name or providers_cfg.get("active", "anthropic")

    pcfg = providers_cfg.get(active)
    if pcfg is None:
        raise LLMConfigError(f"Unknown provider '{active}' — not found in config.json")

    cls = _ADAPTER_MAP.get(active)
    if cls is None:
        raise LLMConfigError(f"No adapter implemented for provider '{active}'")

    resolved_model = model or pcfg.get("model", "")
    return cls(
        model=resolved_model,
        api_key_env=pcfg.get("api_key_env", ""),
        max_tokens=pcfg.get("max_tokens", 4096),
        temperature=pcfg.get("temperature", 0.7),
        api_base=pcfg.get("api_base", ""),
    )


def get_provider_config(provider_name: str | None = None, model: str | None = None) -> dict:
    """Return a plain config dict (for backwards compatibility with llm_interface)."""
    cfg = _load_config()
    providers_cfg = cfg.get("providers", {})
    active = provider_name or providers_cfg.get("active", "anthropic")
    pcfg = providers_cfg.get(active)
    if pcfg is None:
        raise LLMConfigError(f"Unknown provider '{active}' — not found in config.json")
    api_key_env = pcfg.get("api_key_env", "")
    return {
        "provider": active,
        "model": model or pcfg.get("model", ""),
        "api_key": os.environ.get(api_key_env, ""),
        "api_key_env": api_key_env,
        "api_base": pcfg.get("api_base", ""),
        "max_tokens": pcfg.get("max_tokens", 4096),
        "temperature": pcfg.get("temperature", 0.7),
    }
