"""
Overlord11 Engine - Orchestrator Bridge
==========================================
Agent context management and LLM provider calls.
"""

import json
import logging
import os
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any, List, Optional

try:
    from .rate_limit import AllProvidersRateLimitedError, RateLimitError, parse_retry_after
except ImportError:
    from rate_limit import AllProvidersRateLimitedError, RateLimitError, parse_retry_after  # type: ignore[no-redef]


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
        attempted_providers: set = set()
        provider_cooldowns: dict = {}  # provider_name → monotonic timestamp when available

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

            attempted_providers.add(provider_name)
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
            except RateLimitError as exc:
                last_err = exc
                provider_cooldowns[provider_name] = time.monotonic() + exc.retry_after_s
                self._provider_status_detail[provider_name] = f"rate limited ({exc.retry_after_s:.0f}s)"
                self._logger.warning("Provider '%s' rate limited (%.0fs); falling back", provider_name, exc.retry_after_s)
                self._emit_provider_trace(event_callback, "provider_rate_limited", provider=provider_name, retry_after_s=exc.retry_after_s)
                continue
            except Exception as exc:
                last_err = exc
                self._provider_status_detail[provider_name] = f"all models failed: {exc}"
                self._logger.warning("Provider '%s' failed across models (%s); falling back", provider_name, exc)
                self._emit_provider_trace(event_callback, "provider_failed", provider=provider_name, error=str(exc))
                continue

        # If every attempted provider was rate limited (and none had hard errors), surface that
        # so the caller can pause and retry instead of treating this as a permanent failure.
        if provider_cooldowns and provider_cooldowns.keys() == attempted_providers:
            raise AllProvidersRateLimitedError(provider_cooldowns)

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
        # model_name → monotonic timestamp when this model becomes available again.
        rate_limited_models: dict = {}

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
            except urllib.error.HTTPError as exc:
                if exc.code == 429:
                    retry_s = parse_retry_after(exc)
                    rate_limited_models[model_name] = time.monotonic() + retry_s
                    model_errors.append(f"{model_name}: rate limited ({retry_s:.0f}s)")
                    self._logger.warning("Provider '%s' model '%s' rate limited (%.0fs)", provider, model_name, retry_s)
                    self._emit_provider_trace(event_callback, "model_rate_limited", provider=provider, model=model_name, retry_after_s=retry_s)
                    last_exc = exc
                else:
                    last_exc = exc
                    model_errors.append(f"{model_name}: HTTP {exc.code}")
                    self._logger.warning("Provider '%s' model '%s' failed (HTTP %d)", provider, model_name, exc.code)
                    self._emit_provider_trace(event_callback, "model_failed", provider=provider, model=model_name, error=str(exc))
            except Exception as exc:
                last_exc = exc
                model_errors.append(f"{model_name}: {exc}")
                self._logger.warning("Provider '%s' model '%s' failed (%s)", provider, model_name, exc)
                self._emit_provider_trace(event_callback, "model_failed", provider=provider, model=model_name, error=str(exc))

        # If every model failure was a rate limit, surface a RateLimitError so
        # call_provider() can accumulate per-provider cooldowns.
        if rate_limited_models and len(rate_limited_models) == len(model_errors):
            max_ts = max(rate_limited_models.values())
            raise RateLimitError(provider, "all-models", max_ts - time.monotonic(), "all models rate limited")

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
    # Streaming provider calls
    # ------------------------------------------------------------------

    def call_provider_streaming(
        self,
        messages: List[dict],
        system: str,
        token_callback,
        event_callback=None,
    ) -> str:
        """
        Like call_provider() but streams tokens as they arrive.

        token_callback(text: str) is invoked for each chunk of text received
        from the provider.  Falls back to non-streaming if the provider does
        not support it or if streaming fails.

        Returns the full accumulated response string.
        """
        active = self._providers.get("active", "anthropic")
        order = [active] + [p for p in self._fallback_order if p != active]
        configured = [p for p in self._providers.keys() if p != "active"]
        for p in configured:
            if p not in order:
                order.append(p)
        if self._sticky_provider and self._sticky_provider in order:
            order = [self._sticky_provider] + [p for p in order if p != self._sticky_provider]

        if not self._provider_diagnostics_done:
            self._diagnose_providers(order, event_callback=event_callback)

        last_err: Optional[Exception] = None
        attempted_providers: set = set()
        provider_cooldowns: dict = {}  # provider_name → monotonic timestamp when available

        for provider_name in order:
            provider_cfg = self._providers.get(provider_name, {})
            if not provider_cfg:
                continue
            if not self._provider_availability.get(provider_name, True):
                continue
            api_key = os.environ.get(provider_cfg.get("api_key_env", ""), "")
            if not api_key:
                self._provider_availability[provider_name] = False
                continue

            attempted_providers.add(provider_name)
            try:
                model_order = self._get_model_fallback_order(provider_name, provider_cfg)
                rate_limited_models: dict = {}

                for model_name in model_order:
                    try:
                        self._emit_provider_trace(
                            event_callback, "model_attempt_stream",
                            provider=provider_name, model=model_name,
                        )
                        result = self._dispatch_streaming(
                            provider_name, provider_cfg, messages, system,
                            api_key, model_name, token_callback,
                        )
                        self._sticky_provider = provider_name
                        self._sticky_model_by_provider[provider_name] = model_name
                        return result
                    except urllib.error.HTTPError as exc:
                        if exc.code == 429:
                            retry_s = parse_retry_after(exc)
                            rate_limited_models[model_name] = time.monotonic() + retry_s
                            self._logger.warning(
                                "Streaming rate limited for %s/%s (%.0fs)", provider_name, model_name, retry_s
                            )
                            self._emit_provider_trace(
                                event_callback, "model_rate_limited",
                                provider=provider_name, model=model_name, retry_after_s=retry_s,
                            )
                            last_err = exc
                        else:
                            self._logger.warning(
                                "Streaming failed for %s/%s (HTTP %d); trying next", provider_name, model_name, exc.code
                            )
                            last_err = exc
                        continue
                    except Exception as exc:
                        self._logger.warning(
                            "Streaming failed for %s/%s (%s); trying next", provider_name, model_name, exc
                        )
                        last_err = exc
                        continue

                # All models for this provider were rate limited
                if rate_limited_models and len(rate_limited_models) == len(model_order):
                    max_ts = max(rate_limited_models.values())
                    provider_cooldowns[provider_name] = max_ts
                    continue

            except Exception as exc:
                last_err = exc
                continue

        # All streaming attempts failed — check if everything was rate limited.
        if provider_cooldowns and provider_cooldowns.keys() == attempted_providers:
            raise AllProvidersRateLimitedError(provider_cooldowns)

        # Fall back to non-streaming
        self._logger.warning("All streaming attempts failed (%s); falling back to non-streaming", last_err)
        return self.call_provider(messages=messages, system=system, event_callback=event_callback)

    def _dispatch_streaming(
        self,
        provider: str,
        cfg: dict,
        messages: List[dict],
        system: str,
        api_key: str,
        model: str,
        token_callback,
    ) -> str:
        if provider == "anthropic":
            return self._call_anthropic_streaming(cfg, messages, system, api_key, model, token_callback)
        if provider == "gemini":
            return self._call_gemini_streaming(cfg, messages, system, api_key, model, token_callback)
        if provider == "openai":
            return self._call_openai_streaming(cfg, messages, system, api_key, model, token_callback)
        raise ValueError(f"Unknown provider for streaming: {provider}")

    def _call_anthropic_streaming(
        self,
        cfg: dict,
        messages: List[dict],
        system: str,
        api_key: str,
        model: str,
        token_callback,
    ) -> str:
        """
        Stream from Anthropic Messages API using server-sent events.
        SSE format: event: content_block_delta → data: {delta: {type: text_delta, text: "..."}}
        """
        url = f"{cfg.get('api_base', 'https://api.anthropic.com/v1')}/messages"
        payload = {
            "model": model or cfg.get("model", "claude-opus-4-5"),
            "max_tokens": cfg.get("max_tokens", 8192),
            "temperature": cfg.get("temperature", 0.7),
            "system": system,
            "messages": messages,
            "stream": True,
        }
        headers = {
            "Content-Type": "application/json",
            "x-api-key": api_key,
            "anthropic-version": "2023-06-01",
        }

        accumulated = ""
        for line in self._stream_lines(url, payload, headers):
            if not line.startswith("data: "):
                continue
            json_str = line[6:].strip()
            if not json_str or json_str == "[DONE]":
                continue
            try:
                chunk = json.loads(json_str)
            except json.JSONDecodeError:
                continue
            if chunk.get("type") == "content_block_delta":
                delta = chunk.get("delta", {})
                if delta.get("type") == "text_delta":
                    text = delta.get("text", "")
                    if text:
                        accumulated += text
                        token_callback(text)
        return accumulated

    def _call_openai_streaming(
        self,
        cfg: dict,
        messages: List[dict],
        system: str,
        api_key: str,
        model: str,
        token_callback,
    ) -> str:
        """
        Stream from OpenAI Chat Completions API using server-sent events.
        SSE format: data: {choices: [{delta: {content: "..."}}]}  →  data: [DONE]
        """
        url = f"{cfg.get('api_base', 'https://api.openai.com/v1')}/chat/completions"
        all_messages = [{"role": "system", "content": system}] + messages
        payload = {
            "model": model or cfg.get("model", "gpt-4o"),
            "max_tokens": cfg.get("max_tokens", 8192),
            "temperature": cfg.get("temperature", 0.7),
            "messages": all_messages,
            "stream": True,
        }
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {api_key}",
        }

        accumulated = ""
        for line in self._stream_lines(url, payload, headers):
            if not line.startswith("data: "):
                continue
            json_str = line[6:].strip()
            if not json_str or json_str == "[DONE]":
                continue
            try:
                chunk = json.loads(json_str)
                text = chunk["choices"][0]["delta"].get("content") or ""
                if text:
                    accumulated += text
                    token_callback(text)
            except (json.JSONDecodeError, KeyError, IndexError):
                continue
        return accumulated

    def _call_gemini_streaming(
        self,
        cfg: dict,
        messages: List[dict],
        system: str,
        api_key: str,
        model: str,
        token_callback,
    ) -> str:
        """
        Stream from Gemini streamGenerateContent endpoint.
        Response body is a JSON array of candidate objects delivered incrementally.
        We parse complete JSON objects as brace depth reaches zero.
        """
        selected_model = model or cfg.get("model", "gemini-2.5-pro")
        api_base = cfg.get("api_base", "https://generativelanguage.googleapis.com/v1beta")
        url = f"{api_base}/models/{selected_model}:streamGenerateContent?key={api_key}&alt=sse"

        contents = []
        for msg in messages:
            role = "user" if msg.get("role") == "user" else "model"
            contents.append({"role": role, "parts": [{"text": msg.get("content", "")}]})

        payload: dict = {
            "contents": contents,
            "generationConfig": {
                "maxOutputTokens": cfg.get("max_tokens", 8192),
                "temperature": cfg.get("temperature", 0.7),
            },
        }
        if system:
            payload["systemInstruction"] = {"parts": [{"text": system}]}

        headers = {"Content-Type": "application/json"}
        accumulated = ""

        # Gemini with alt=sse returns SSE format like Anthropic/OpenAI
        for line in self._stream_lines(url, payload, headers):
            if not line.startswith("data: "):
                continue
            json_str = line[6:].strip()
            if not json_str:
                continue
            try:
                chunk = json.loads(json_str)
                text = chunk["candidates"][0]["content"]["parts"][0]["text"]
                if text:
                    accumulated += text
                    token_callback(text)
            except (json.JSONDecodeError, KeyError, IndexError):
                continue
        return accumulated

    def _stream_lines(self, url: str, payload: dict, headers: dict, timeout: int = 300):
        """
        Open an HTTP POST connection and yield decoded lines as they arrive
        from the socket.  Used by all three streaming provider methods.
        """
        import urllib.request
        data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        req = urllib.request.Request(url, data=data, headers=headers, method="POST")
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            for raw_line in resp:
                yield raw_line.decode("utf-8", errors="replace").rstrip("\r\n")

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
