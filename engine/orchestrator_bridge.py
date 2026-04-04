"""
engine/orchestrator_bridge.py
==============================
Bridges between the internal Python engine and the provider APIs
(Anthropic, Gemini, OpenAI).  Reads provider config from config.json,
sends context to the active provider, and returns the raw text response.

This does NOT modify any agent .md definitions — it reads them as
system prompts and forwards the context.
"""

import json
import os
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
_CONFIG_PATH = _PROJECT_ROOT / "config.json"


def _load_config() -> Dict[str, Any]:
    try:
        return json.loads(_CONFIG_PATH.read_text())
    except (OSError, json.JSONDecodeError):
        return {}


def _load_agent_prompt(agent_name: str, config: Dict[str, Any]) -> str:
    """Load an agent's system prompt from its .md file."""
    agent_cfg = config.get("agents", {}).get(agent_name, {})
    md_path = _PROJECT_ROOT / agent_cfg.get("file", f"agents/{agent_name}.md")
    if md_path.exists():
        return md_path.read_text()
    return f"You are the {agent_name} agent."


# ---------------------------------------------------------------------------
# Provider adapters
# ---------------------------------------------------------------------------

def _call_anthropic(
    system: str,
    messages: List[Dict[str, str]],
    cfg: Dict[str, Any],
) -> str:
    """Call Anthropic Claude API."""
    try:
        import anthropic

        client = anthropic.Anthropic(api_key=os.environ.get(cfg.get("api_key_env", "ANTHROPIC_API_KEY"), ""))
        response = client.messages.create(
            model=cfg.get("model", "claude-opus-4-5"),
            max_tokens=cfg.get("max_tokens", 8192),
            temperature=cfg.get("temperature", 0.7),
            system=system,
            messages=messages,
        )
        return response.content[0].text if response.content else ""
    except Exception as exc:
        raise RuntimeError(f"Anthropic API error: {exc}") from exc


def _call_gemini(
    system: str,
    messages: List[Dict[str, str]],
    cfg: Dict[str, Any],
) -> str:
    """Call Google Gemini API."""
    try:
        import google.generativeai as genai

        genai.configure(api_key=os.environ.get(cfg.get("api_key_env", "GOOGLE_GEMINI_API_KEY"), ""))
        model = genai.GenerativeModel(
            model_name=cfg.get("model", "gemini-2.5-pro"),
            system_instruction=system,
        )

        if not messages:
            raise RuntimeError("No messages provided to Gemini")

        # Build history from all messages except the final one, then send the
        # final message via chat.send_message.  The Gemini SDK expects history
        # entries with roles "user" or "model".
        history = []
        for msg in messages[:-1]:
            role = "user" if msg["role"] == "user" else "model"
            history.append({"role": role, "parts": [msg["content"]]})

        last_msg = messages[-1]["content"]
        chat = model.start_chat(history=history)
        response = chat.send_message(last_msg)
        return response.text
    except Exception as exc:
        raise RuntimeError(f"Gemini API error: {exc}") from exc


def _call_openai(
    system: str,
    messages: List[Dict[str, str]],
    cfg: Dict[str, Any],
) -> str:
    """Call OpenAI API."""
    try:
        from openai import OpenAI

        client = OpenAI(api_key=os.environ.get(cfg.get("api_key_env", "OPENAI_API_KEY"), ""))
        full_messages = [{"role": "system", "content": system}] + messages
        response = client.chat.completions.create(
            model=cfg.get("model", "gpt-4o"),
            max_tokens=cfg.get("max_tokens", 8192),
            temperature=cfg.get("temperature", 0.7),
            messages=full_messages,
        )
        return response.choices[0].message.content or ""
    except Exception as exc:
        raise RuntimeError(f"OpenAI API error: {exc}") from exc


# ---------------------------------------------------------------------------
# OrchestratorBridge
# ---------------------------------------------------------------------------

_PROVIDER_CALLERS = {
    "anthropic": _call_anthropic,
    "gemini": _call_gemini,
    "openai": _call_openai,
}


class OrchestratorBridge:
    """
    Sends context + system prompt to the configured provider and returns
    the raw text response.  Respects the fallback_provider_order on error.
    """

    def __init__(self, provider_override: Optional[str] = None):
        self._config = _load_config()
        self._provider_override = provider_override

    def _active_provider(self) -> str:
        if self._provider_override:
            return self._provider_override
        return self._config.get("providers", {}).get("active", "anthropic")

    def _fallback_order(self) -> List[str]:
        return self._config.get("orchestration", {}).get(
            "fallback_provider_order", ["anthropic", "gemini", "openai"]
        )

    def _provider_cfg(self, provider: str) -> Dict[str, Any]:
        return self._config.get("providers", {}).get(provider, {})

    def call(
        self,
        agent_name: str,
        messages: List[Dict[str, str]],
        provider: Optional[str] = None,
    ) -> Tuple[str, str]:
        """
        Call the provider with the agent's system prompt + messages.

        Returns (response_text, provider_used).
        Raises RuntimeError if all providers fail.
        """
        system_prompt = _load_agent_prompt(agent_name, self._config)
        active = provider or self._active_provider()
        fallback = self._fallback_order()

        # Build try order: active first, then fallbacks
        try_order = [active] + [p for p in fallback if p != active]

        last_error: Optional[Exception] = None
        for prov in try_order:
            caller = _PROVIDER_CALLERS.get(prov)
            if not caller:
                continue
            cfg = self._provider_cfg(prov)
            try:
                response = caller(system_prompt, messages, cfg)
                return response, prov
            except RuntimeError as exc:
                last_error = exc
                continue

        raise RuntimeError(
            f"All providers failed. Last error: {last_error}"
        ) from last_error

    def get_available_models(self, provider: Optional[str] = None) -> Dict[str, Any]:
        """Return the available_models dict for a provider (from config)."""
        prov = provider or self._active_provider()
        return self._provider_cfg(prov).get("available_models", {})

    def get_provider_status(self) -> Dict[str, str]:
        """
        Quick reachability check for each provider.
        Returns {"anthropic": "green"|"red", ...}
        """
        status: Dict[str, str] = {}
        for prov in _PROVIDER_CALLERS:
            cfg = self._provider_cfg(prov)
            api_key_env = cfg.get("api_key_env", "")
            has_key = bool(os.environ.get(api_key_env, ""))
            status[prov] = "green" if has_key else "red"
        return status
