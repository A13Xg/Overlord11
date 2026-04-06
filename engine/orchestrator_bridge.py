"""
Overlord11 Engine - Orchestrator Bridge
==========================================
Agent context management and LLM provider calls.
"""

import json
import logging
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
        self._provider_diagnostics_done = False
        self._provider_availability: dict[str, bool] = {}
        self._provider_status_detail: dict[str, str] = {}
        self._sticky_provider: str = ""
        self._sticky_model_by_provider: dict[str, str] = {}
        self._logger = logging.getLogger("overlord11.providers")

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

    def call_provider(self, messages: List[dict], system: str, event_callback=None) -> str:
        """Call the active provider, falling back as configured."""
        active = self._providers.get("active", "anthropic")
        order = [active] + [p for p in self._fallback_order if p != active]
        configured = [p for p in self._providers.keys() if p != "active"]
        for provider_name in configured:
            if provider_name not in order:
                order.append(provider_name)

        # Keep using the last successful provider for this task before trying defaults.
        if self._sticky_provider and self._sticky_provider in order:
            order = [self._sticky_provider] + [p for p in order if p != self._sticky_provider]

        if not self._provider_diagnostics_done:
            self._diagnose_providers(order, event_callback=event_callback)

        last_err: Optional[Exception] = None
        for provider_name in order:
            provider_cfg = self._providers.get(provider_name, {})
            if not provider_cfg:
                self._logger.warning("Provider '%s' not configured; skipping", provider_name)
                self._provider_status_detail[provider_name] = "not configured"
                self._emit_provider_trace(event_callback, "provider_skipped", provider=provider_name, reason="not configured")
                continue

            # Skip providers already marked unavailable during diagnostics.
            if not self._provider_availability.get(provider_name, True):
                self._logger.warning("Provider '%s' unavailable; falling back", provider_name)
                if provider_name not in self._provider_status_detail:
                    self._provider_status_detail[provider_name] = "unavailable"
                self._emit_provider_trace(event_callback, "provider_skipped", provider=provider_name, reason=self._provider_status_detail[provider_name])
                continue

            api_key = os.environ.get(provider_cfg.get("api_key_env", ""), "")
            if not api_key:
                self._logger.warning("Provider '%s' missing API key env '%s'; falling back", provider_name, provider_cfg.get("api_key_env", ""))
                self._provider_availability[provider_name] = False
                self._provider_status_detail[provider_name] = f"missing env {provider_cfg.get('api_key_env', '')}"
                self._emit_provider_trace(event_callback, "provider_skipped", provider=provider_name, reason=self._provider_status_detail[provider_name])
                continue
            try:
                self._provider_status_detail[provider_name] = "request in progress"
                response = self._dispatch_with_model_fallback(
                    provider_name,
                    provider_cfg,
                    messages,
                    system,
                    api_key,
                    event_callback=event_callback,
                )
                self._sticky_provider = provider_name
                return response
            except Exception as exc:
                last_err = exc
                self._provider_status_detail[provider_name] = f"all models failed: {exc}"
                self._logger.warning("Provider '%s' failed across models (%s); falling back", provider_name, exc)
                self._emit_provider_trace(event_callback, "provider_failed", provider=provider_name, error=str(exc))
                continue

        raise RuntimeError(self._format_provider_failure(order, last_err)) from last_err

    def _dispatch(
        self,
        provider: str,
        cfg: dict,
        messages: List[dict],
        system: str,
        api_key: str,
        model: Optional[str] = None,
    ) -> str:
        if provider == "anthropic":
            return self._call_anthropic(cfg, messages, system, api_key, model=model)
        if provider == "gemini":
            return self._call_gemini(cfg, messages, system, api_key, model=model)
        if provider == "openai":
            return self._call_openai(cfg, messages, system, api_key, model=model)
        raise ValueError(f"Unknown provider: {provider}")

    def _dispatch_with_model_fallback(
        self,
        provider: str,
        cfg: dict,
        messages: List[dict],
        system: str,
        api_key: str,
        event_callback=None,
    ) -> str:
        """Try primary model first, then remaining available models for this provider."""
        model_order = self._get_model_fallback_order(provider, cfg)
        if not model_order:
            raise RuntimeError("no models configured")

        model_errors: List[str] = []
        last_exc: Optional[Exception] = None

        for model_name in model_order:
            try:
                self._logger.warning("Provider '%s' trying model '%s'", provider, model_name)
                self._provider_status_detail[provider] = f"trying model {model_name}"
                self._emit_provider_trace(event_callback, "model_attempt", provider=provider, model=model_name)
                response = self._dispatch(
                    provider,
                    cfg,
                    messages,
                    system,
                    api_key,
                    model=model_name,
                )
                self._sticky_model_by_provider[provider] = model_name
                self._provider_status_detail[provider] = f"success model {model_name}"
                self._emit_provider_trace(event_callback, "model_success", provider=provider, model=model_name)
                return response
            except Exception as exc:
                last_exc = exc
                model_errors.append(f"{model_name}: {exc}")
                self._logger.warning("Provider '%s' model '%s' failed (%s)", provider, model_name, exc)
                self._emit_provider_trace(event_callback, "model_failed", provider=provider, model=model_name, error=str(exc))

        joined = "; ".join(model_errors)
        raise RuntimeError(joined or "all model attempts failed") from last_exc

    def _get_model_fallback_order(self, provider: str, cfg: dict) -> List[str]:
        """Return model order: sticky-success model first, then configured primary, then others."""
        primary_model = cfg.get("model", "")
        available_models = list(cfg.get("available_models", {}).keys())
        sticky_model = self._sticky_model_by_provider.get(provider, "")

        order: List[str] = []
        if sticky_model:
            order.append(sticky_model)
        if primary_model:
            order.append(primary_model)

        for model_name in available_models:
            if model_name and model_name not in order:
                order.append(model_name)

        return order

    # ------------------------------------------------------------------
    # Anthropic
    # ------------------------------------------------------------------

    def _call_anthropic(
        self,
        cfg: dict,
        messages: List[dict],
        system: str,
        api_key: str,
        model: Optional[str] = None,
    ) -> str:
        url = f"{cfg.get('api_base', 'https://api.anthropic.com/v1')}/messages"
        payload = {
            "model": model or cfg.get("model", "claude-opus-4-5"),
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

    def _call_gemini(
        self,
        cfg: dict,
        messages: List[dict],
        system: str,
        api_key: str,
        model: Optional[str] = None,
    ) -> str:
        selected_model = model or cfg.get("model", "gemini-2.5-pro")
        api_base = cfg.get("api_base", "https://generativelanguage.googleapis.com/v1beta")
        url = f"{api_base}/models/{selected_model}:generateContent?key={api_key}"

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

    def _call_openai(
        self,
        cfg: dict,
        messages: List[dict],
        system: str,
        api_key: str,
        model: Optional[str] = None,
    ) -> str:
        url = f"{cfg.get('api_base', 'https://api.openai.com/v1')}/chat/completions"
        all_messages = [{"role": "system", "content": system}] + messages
        payload = {
            "model": model or cfg.get("model", "gpt-4o"),
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

    def _diagnose_providers(self, order: List[str], event_callback=None) -> None:
        """Check keys and probe providers once so fallback can happen immediately."""
        self._logger.warning("Provider diagnostics started")
        self._emit_provider_trace(event_callback, "diagnostics_started", order=order)
        for provider_name in order:
            provider_cfg = self._providers.get(provider_name, {})
            if not provider_cfg:
                self._provider_availability[provider_name] = False
                self._provider_status_detail[provider_name] = "not configured"
                self._logger.warning("Provider '%s': not configured", provider_name)
                self._emit_provider_trace(event_callback, "diagnostic_result", provider=provider_name, status="not configured")
                continue

            key_env = provider_cfg.get("api_key_env", "")
            api_key = os.environ.get(key_env, "")
            if not api_key:
                self._provider_availability[provider_name] = False
                self._provider_status_detail[provider_name] = f"missing env {key_env}"
                self._logger.warning("Provider '%s': API key env '%s' not set", provider_name, key_env)
                self._emit_provider_trace(event_callback, "diagnostic_result", provider=provider_name, status=self._provider_status_detail[provider_name])
                continue

            ok, detail = self._test_provider_health(provider_name, provider_cfg, api_key)
            self._provider_availability[provider_name] = ok
            self._provider_status_detail[provider_name] = detail
            if ok:
                self._logger.warning("Provider '%s': available (%s)", provider_name, detail)
            else:
                self._logger.warning("Provider '%s': unavailable (%s)", provider_name, detail)
            self._emit_provider_trace(event_callback, "diagnostic_result", provider=provider_name, status=detail, available=ok)

        self._provider_diagnostics_done = True
        self._logger.warning("Provider diagnostics complete")
        self._emit_provider_trace(event_callback, "diagnostics_complete", availability=self._provider_availability)

    def _test_provider_health(self, provider: str, cfg: dict, api_key: str) -> tuple[bool, str]:
        """Probe provider API with a lightweight endpoint to verify key + reachability."""
        try:
            if provider == "anthropic":
                url = f"{cfg.get('api_base', 'https://api.anthropic.com/v1')}/models"
                headers = {
                    "x-api-key": api_key,
                    "anthropic-version": "2023-06-01",
                }
                self._http_get(url, headers)
                return True, "models endpoint ok"

            if provider == "gemini":
                api_base = cfg.get("api_base", "https://generativelanguage.googleapis.com/v1beta")
                url = f"{api_base}/models?key={api_key}"
                self._http_get(url, {})
                return True, "models endpoint ok"

            if provider == "openai":
                url = f"{cfg.get('api_base', 'https://api.openai.com/v1')}/models"
                headers = {
                    "Authorization": f"Bearer {api_key}",
                }
                self._http_get(url, headers)
                return True, "models endpoint ok"

            return False, "unsupported provider"
        except Exception as exc:
            return False, str(exc)

    def _http_post(self, url: str, payload: dict, headers: dict) -> dict:
        data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        req = urllib.request.Request(url, data=data, headers=headers, method="POST")
        with urllib.request.urlopen(req, timeout=120) as resp:
            body = resp.read().decode("utf-8")
        return json.loads(body)

    def _http_get(self, url: str, headers: dict) -> dict:
        req = urllib.request.Request(url, headers=headers, method="GET")
        with urllib.request.urlopen(req, timeout=30) as resp:
            body = resp.read().decode("utf-8")
        return json.loads(body)

    def _format_provider_failure(self, order: List[str], last_err: Optional[Exception]) -> str:
        """Build a concise provider summary for UI event logs when all providers fail."""
        parts: List[str] = []
        for provider_name in order:
            detail = self._provider_status_detail.get(provider_name, "no details")
            parts.append(f"{provider_name}: {detail}")
        summary = " | ".join(parts)
        return f"All providers failed. Last error: {last_err}. Provider diagnostics: {summary}"

    def _emit_provider_trace(self, event_callback, phase: str, **payload) -> None:
        if event_callback is None:
            return
        try:
            event_callback(phase, payload)
        except Exception:
            pass

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _find_agent_by_id(self, agent_id: str) -> Optional[dict]:
        for agent_cfg in self._agents.values():
            if agent_cfg.get("id") == agent_id:
                return agent_cfg
        return None
