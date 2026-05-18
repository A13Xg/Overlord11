"""
Direct provider runtime for shell-only WebUI execution.
"""

import json
import os
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Any, Optional


@dataclass
class ProviderResult:
    provider: str
    model: str
    output: str
    raw: dict[str, Any]


class ProviderRuntime:
    def __init__(self, config: dict):
        self._config = config or {}

    def execute_prompt(self, prompt: str) -> ProviderResult:
        providers_cfg = self._config.get("providers", {})
        active = providers_cfg.get("active", "openai")
        provider_cfg = providers_cfg.get(active, {})
        model = str(provider_cfg.get("model", "")).strip()
        if not model:
            raise RuntimeError(f"Provider '{active}' has no model configured")

        if active == "openai":
            return self._call_openai(provider_cfg, model, prompt)
        if active == "anthropic":
            return self._call_anthropic(provider_cfg, model, prompt)
        if active == "gemini":
            return self._call_gemini(provider_cfg, model, prompt)
        raise RuntimeError(f"Unsupported provider: {active}")

    def _call_openai(self, cfg: dict, model: str, prompt: str) -> ProviderResult:
        key = os.environ.get(cfg.get("api_key_env", ""), "")
        if not key:
            raise RuntimeError("OpenAI API key not configured")
        url = cfg.get("api_base", "https://api.openai.com/v1").rstrip("/") + "/chat/completions"
        payload = {
            "model": model,
            "messages": [{"role": "user", "content": prompt}],
            "temperature": float(cfg.get("temperature", 0.7)),
            "max_tokens": int(cfg.get("max_tokens", 4096)),
            "top_p": float(cfg.get("top_p", 1.0)),
        }
        req = urllib.request.Request(
            url,
            data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
            headers={
                "Authorization": f"Bearer {key}",
                "Content-Type": "application/json",
            },
            method="POST",
        )
        raw = self._request_json(req)
        choices = raw.get("choices") or []
        output = ""
        if choices and isinstance(choices[0], dict):
            msg = choices[0].get("message") or {}
            output = str(msg.get("content") or "")
        return ProviderResult(provider="openai", model=model, output=output, raw=raw)

    def _call_anthropic(self, cfg: dict, model: str, prompt: str) -> ProviderResult:
        key = os.environ.get(cfg.get("api_key_env", ""), "")
        if not key:
            raise RuntimeError("Anthropic API key not configured")
        url = cfg.get("api_base", "https://api.anthropic.com/v1").rstrip("/") + "/messages"
        payload = {
            "model": model,
            "max_tokens": int(cfg.get("max_tokens", 4096)),
            "temperature": float(cfg.get("temperature", 0.7)),
            "messages": [{"role": "user", "content": prompt}],
        }
        req = urllib.request.Request(
            url,
            data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
            headers={
                "x-api-key": key,
                "anthropic-version": "2023-06-01",
                "Content-Type": "application/json",
            },
            method="POST",
        )
        raw = self._request_json(req)
        output = ""
        content = raw.get("content") or []
        if isinstance(content, list):
            parts: list[str] = []
            for item in content:
                if isinstance(item, dict) and item.get("type") == "text":
                    parts.append(str(item.get("text") or ""))
            output = "".join(parts)
        return ProviderResult(provider="anthropic", model=model, output=output, raw=raw)

    def _call_gemini(self, cfg: dict, model: str, prompt: str) -> ProviderResult:
        key = os.environ.get(cfg.get("api_key_env", ""), "")
        if not key:
            raise RuntimeError("Gemini API key not configured")
        base = cfg.get("api_base", "https://generativelanguage.googleapis.com/v1beta").rstrip("/")
        url = f"{base}/models/{model}:generateContent?key={key}"
        payload = {
            "contents": [{"parts": [{"text": prompt}]}],
            "generationConfig": {
                "temperature": float(cfg.get("temperature", 0.7)),
                "topP": float(cfg.get("top_p", 1.0)),
                "maxOutputTokens": int(cfg.get("max_tokens", 4096)),
            },
        }
        req = urllib.request.Request(
            url,
            data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        raw = self._request_json(req)
        output = ""
        candidates = raw.get("candidates") or []
        if candidates and isinstance(candidates[0], dict):
            content = candidates[0].get("content") or {}
            parts = content.get("parts") or []
            output = "".join(str(p.get("text") or "") for p in parts if isinstance(p, dict))
        return ProviderResult(provider="gemini", model=model, output=output, raw=raw)

    def _request_json(self, req: urllib.request.Request) -> dict[str, Any]:
        try:
            with urllib.request.urlopen(req, timeout=180) as resp:
                data = resp.read().decode("utf-8")
                return json.loads(data)
        except urllib.error.HTTPError as exc:
            detail = ""
            try:
                detail = exc.read().decode("utf-8")
            except Exception:
                detail = str(exc)
            raise RuntimeError(f"Provider HTTP {exc.code}: {detail[:500]}") from exc
        except urllib.error.URLError as exc:
            raise RuntimeError(f"Provider network error: {exc}") from exc

