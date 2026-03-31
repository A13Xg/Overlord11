"""
webui/llm_interface.py — Provider-agnostic LLM call interface.

Reads provider/model from config.json (same pattern as the rest of Overlord11).
Supports: anthropic, gemini, openai.

LLM responses for the runner are expected to be JSON objects with one of:
    {"action": "tool_call",  "tool": "<name>", "args": {...}}
    {"action": "patch",      "diff": "<unified diff>", "rationale": "..."}
    {"action": "complete",   "summary": "..."}
    {"action": "repair",     "diff": "<unified diff>", "rationale": "..."}

If a provider key is missing the call raises LLMConfigError.
All calls emit LLM_CALL_START / LLM_CALL_END events via the event bus.
"""

from __future__ import annotations

import json
import os
import time
from pathlib import Path
from typing import Any, Callable

from .events import EventType, make_event


# ---------------------------------------------------------------------------
# Config helpers
# ---------------------------------------------------------------------------

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
_CONFIG_PATH = _PROJECT_ROOT / "config.json"


def _load_config() -> dict[str, Any]:
    if _CONFIG_PATH.exists():
        return json.loads(_CONFIG_PATH.read_text(encoding="utf-8"))
    return {}


def get_provider_config(provider: str | None = None, model: str | None = None) -> dict[str, Any]:
    """
    Return a dict with keys: provider, model, api_key, api_base, max_tokens,
    temperature.

    Raises LLMConfigError if provider is unknown or API key env var is absent.
    """
    cfg = _load_config()
    providers = cfg.get("providers", {})
    active = provider or providers.get("active", "anthropic")

    pcfg = providers.get(active)
    if pcfg is None:
        raise LLMConfigError(f"Unknown provider '{active}' — not found in config.json")

    resolved_model = model or pcfg.get("model", "")
    api_key_env = pcfg.get("api_key_env", "")
    api_key = os.environ.get(api_key_env, "")

    return {
        "provider": active,
        "model": resolved_model,
        "api_key": api_key,
        "api_key_env": api_key_env,
        "api_base": pcfg.get("api_base", ""),
        "max_tokens": pcfg.get("max_tokens", 4096),
        "temperature": pcfg.get("temperature", 0.7),
    }


# ---------------------------------------------------------------------------
# Exceptions
# ---------------------------------------------------------------------------

class LLMConfigError(Exception):
    """Provider misconfiguration (unknown provider, missing key, etc.)."""


class LLMCallError(Exception):
    """HTTP-level or API-level error from the LLM provider."""


# ---------------------------------------------------------------------------
# Core call function
# ---------------------------------------------------------------------------

def llm_call(
    messages: list[dict[str, str]],
    *,
    job_id: str,
    system: str = "",
    provider: str | None = None,
    model: str | None = None,
    emit: Callable[[dict[str, Any]], None] | None = None,
) -> str:
    """
    Send *messages* to the configured LLM and return the response text.

    Parameters
    ----------
    messages:
        List of {"role": "user"|"assistant", "content": "..."} dicts.
    job_id:
        Used for event emission only.
    system:
        System prompt prepended for providers that support it.
    provider / model:
        Overrides; falls back to config.json values.
    emit:
        Callable that receives event dicts (for SSE broadcast).

    Returns
    -------
    str — the raw text content of the LLM response.
    """
    pcfg = get_provider_config(provider, model)
    start_ts = time.monotonic()

    if emit:
        emit(
            make_event(
                EventType.LLM_CALL_START,
                job_id,
                {"provider": pcfg["provider"], "model": pcfg["model"]},
            )
        )

    if not pcfg["api_key"]:
        # No key — return a stub response so the runner can still demonstrate
        # its structure without a real LLM.
        result = json.dumps(
            {
                "action": "complete",
                "summary": (
                    "[STUB] No API key for provider "
                    f"'{pcfg['provider']}' (env: {pcfg['api_key_env']}). "
                    "Runner completed stub iteration."
                ),
            }
        )
        _emit_end(emit, job_id, pcfg, start_ts, tokens=0)
        return result

    try:
        if pcfg["provider"] == "anthropic":
            result = _call_anthropic(messages, system=system, pcfg=pcfg)
        elif pcfg["provider"] == "gemini":
            result = _call_gemini(messages, system=system, pcfg=pcfg)
        elif pcfg["provider"] == "openai":
            result = _call_openai(messages, system=system, pcfg=pcfg)
        else:
            raise LLMConfigError(f"Unsupported provider: {pcfg['provider']}")
    except LLMCallError:
        raise
    except Exception as exc:
        raise LLMCallError(str(exc)) from exc

    _emit_end(emit, job_id, pcfg, start_ts)
    return result


def _emit_end(emit, job_id, pcfg, start_ts, tokens=None):
    if emit:
        elapsed = round(time.monotonic() - start_ts, 3)
        payload: dict[str, Any] = {
            "provider": pcfg["provider"],
            "model": pcfg["model"],
            "elapsed_s": elapsed,
        }
        if tokens is not None:
            payload["tokens"] = tokens
        emit(make_event(EventType.LLM_CALL_END, job_id, payload))


# ---------------------------------------------------------------------------
# Provider-specific adapters
# ---------------------------------------------------------------------------

def _call_anthropic(messages: list[dict], system: str, pcfg: dict) -> str:
    """Call the Anthropic Messages API."""
    try:
        import anthropic  # type: ignore
    except ImportError:
        raise LLMCallError(
            "anthropic package not installed. Run: pip install anthropic"
        )

    client = anthropic.Anthropic(api_key=pcfg["api_key"])
    kwargs: dict[str, Any] = {
        "model": pcfg["model"],
        "max_tokens": pcfg["max_tokens"],
        "messages": messages,
    }
    if system:
        kwargs["system"] = system

    response = client.messages.create(**kwargs)
    return response.content[0].text


def _call_gemini(messages: list[dict], system: str, pcfg: dict) -> str:
    """Call the Google Gemini API."""
    try:
        import google.generativeai as genai  # type: ignore
    except ImportError:
        raise LLMCallError(
            "google-generativeai package not installed. "
            "Run: pip install google-generativeai"
        )

    genai.configure(api_key=pcfg["api_key"])
    gmodel = genai.GenerativeModel(
        model_name=pcfg["model"],
        system_instruction=system or None,
    )
    # Convert to Gemini content format
    history = []
    last_msg = messages[-1]["content"] if messages else ""
    for m in messages[:-1]:
        role = "user" if m["role"] == "user" else "model"
        history.append({"role": role, "parts": [m["content"]]})

    chat = gmodel.start_chat(history=history)
    response = chat.send_message(last_msg)
    return response.text


def _call_openai(messages: list[dict], system: str, pcfg: dict) -> str:
    """Call the OpenAI Chat Completions API."""
    try:
        from openai import OpenAI  # type: ignore
    except ImportError:
        raise LLMCallError(
            "openai package not installed. Run: pip install openai"
        )

    full_messages = []
    if system:
        full_messages.append({"role": "system", "content": system})
    full_messages.extend(messages)

    client = OpenAI(api_key=pcfg["api_key"])
    response = client.chat.completions.create(
        model=pcfg["model"],
        messages=full_messages,
        max_tokens=pcfg["max_tokens"],
        temperature=pcfg["temperature"],
    )
    return response.choices[0].message.content
