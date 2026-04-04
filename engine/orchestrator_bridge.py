"""
Overlord11 Engine - Orchestrator Bridge
==========================================
Agent context management and LLM provider calls.
"""

import json
import os
import sys
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any, List, Optional


_BASE_DIR = Path(__file__).resolve().parent.parent


class OrchestratorBridge:
    """Manages agent prompts and provider API calls."""

    def __init__(self, config: dict):
        self._config = config
        self._providers = config.get("providers", {})
        self._agents = config.get("agents", {})
        self._fallback_order: List[str] = (
            config.get("orchestration", {}).get("fallback_provider_order", ["anthropic", "gemini", "openai"])
        )

    # ------------------------------------------------------------------
    # Prompt building
    # ------------------------------------------------------------------

    def build_system_prompt(self, agent_id: str) -> str:
        """Build system prompt from agent markdown file + ONBOARDING.md."""
        parts: List[str] = []

        # Read ONBOARDING.md
        onboarding_path = _BASE_DIR / "ONBOARDING.md"
        if onboarding_path.exists():
            parts.append(onboarding_path.read_text(encoding="utf-8"))

        # Find the agent config by id
        agent_cfg = self._find_agent_by_id(agent_id)
        if agent_cfg:
            agent_file = _BASE_DIR / agent_cfg.get("file", "")
            if agent_file.exists():
                parts.append(agent_file.read_text(encoding="utf-8"))

        return "\n\n---\n\n".join(parts)

    def build_context(self, messages: List[dict], tool_results: Optional[List[dict]] = None) -> List[dict]:
        """Format message history, optionally appending tool results."""
        context = list(messages)
        if tool_results:
            for tr in tool_results:
                content = json.dumps(tr, ensure_ascii=False)
                context.append({"role": "user", "content": f"Tool result:\n{content}"})
        return context

    # ------------------------------------------------------------------
    # Provider calls
    # ------------------------------------------------------------------

    def call_provider(self, messages: List[dict], system: str) -> str:
        """Call the active provider, falling back as configured."""
        active = self._providers.get("active", "anthropic")
        order = [active] + [p for p in self._fallback_order if p != active]

        last_err: Optional[Exception] = None
        for provider_name in order:
            provider_cfg = self._providers.get(provider_name, {})
            if not provider_cfg:
                continue
            api_key = os.environ.get(provider_cfg.get("api_key_env", ""), "")
            if not api_key:
                continue
            try:
                return self._dispatch(provider_name, provider_cfg, messages, system, api_key)
            except Exception as exc:
                last_err = exc
                continue

        raise RuntimeError(
            f"All providers failed. Last error: {last_err}"
        ) from last_err

    def _dispatch(
        self,
        provider: str,
        cfg: dict,
        messages: List[dict],
        system: str,
        api_key: str,
    ) -> str:
        if provider == "anthropic":
            return self._call_anthropic(cfg, messages, system, api_key)
        if provider == "gemini":
            return self._call_gemini(cfg, messages, system, api_key)
        if provider == "openai":
            return self._call_openai(cfg, messages, system, api_key)
        raise ValueError(f"Unknown provider: {provider}")

    # ------------------------------------------------------------------
    # Anthropic
    # ------------------------------------------------------------------

    def _call_anthropic(self, cfg: dict, messages: List[dict], system: str, api_key: str) -> str:
        url = f"{cfg.get('api_base', 'https://api.anthropic.com/v1')}/messages"
        payload = {
            "model": cfg.get("model", "claude-opus-4-5"),
            "max_tokens": cfg.get("max_tokens", 8192),
            "temperature": cfg.get("temperature", 0.7),
            "system": system,
            "messages": messages,
        }
        headers = {
            "Content-Type": "application/json",
            "x-api-key": api_key,
            "anthropic-version": "2023-06-01",
        }
        response = self._http_post(url, payload, headers)
        return response["content"][0]["text"]

    # ------------------------------------------------------------------
    # Gemini
    # ------------------------------------------------------------------

    def _call_gemini(self, cfg: dict, messages: List[dict], system: str, api_key: str) -> str:
        model = cfg.get("model", "gemini-2.5-pro")
        api_base = cfg.get("api_base", "https://generativelanguage.googleapis.com/v1beta")
        url = f"{api_base}/models/{model}:generateContent?key={api_key}"

        # Convert messages to Gemini format
        contents = []
        for msg in messages:
            role = "user" if msg.get("role") == "user" else "model"
            contents.append({"role": role, "parts": [{"text": msg.get("content", "")}]})

        payload: dict[str, Any] = {
            "contents": contents,
            "generationConfig": {
                "maxOutputTokens": cfg.get("max_tokens", 8192),
                "temperature": cfg.get("temperature", 0.7),
            },
        }
        if system:
            payload["systemInstruction"] = {"parts": [{"text": system}]}

        headers = {"Content-Type": "application/json"}
        response = self._http_post(url, payload, headers)
        return response["candidates"][0]["content"]["parts"][0]["text"]

    # ------------------------------------------------------------------
    # OpenAI
    # ------------------------------------------------------------------

    def _call_openai(self, cfg: dict, messages: List[dict], system: str, api_key: str) -> str:
        url = f"{cfg.get('api_base', 'https://api.openai.com/v1')}/chat/completions"
        all_messages = [{"role": "system", "content": system}] + messages
        payload = {
            "model": cfg.get("model", "gpt-4o"),
            "max_tokens": cfg.get("max_tokens", 8192),
            "temperature": cfg.get("temperature", 0.7),
            "messages": all_messages,
        }
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {api_key}",
        }
        response = self._http_post(url, payload, headers)
        return response["choices"][0]["message"]["content"]

    # ------------------------------------------------------------------
    # HTTP helper
    # ------------------------------------------------------------------

    def _http_post(self, url: str, payload: dict, headers: dict) -> dict:
        data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        req = urllib.request.Request(url, data=data, headers=headers, method="POST")
        with urllib.request.urlopen(req, timeout=120) as resp:
            body = resp.read().decode("utf-8")
        return json.loads(body)

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _find_agent_by_id(self, agent_id: str) -> Optional[dict]:
        for agent_cfg in self._agents.values():
            if agent_cfg.get("id") == agent_id:
                return agent_cfg
        return None
