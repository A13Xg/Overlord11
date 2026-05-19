"""
Direct provider runtime for shell-only WebUI execution.
"""

import json
import os
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Any, Callable, Optional


@dataclass
class ProviderResult:
    provider: str
    model: str
    output: str
    raw: dict[str, Any]


class ProviderHTTPError(RuntimeError):
    def __init__(self, status_code: int, message: str, retry_after_s: Optional[int] = None):
        super().__init__(message)
        self.status_code = int(status_code)
        self.retry_after_s = retry_after_s


class ProviderRuntime:
    def __init__(self, config: dict):
        self._config = config or {}

    def execute_prompt(self, prompt: str, system_prompt: str = "") -> ProviderResult:
        providers_cfg = self._config.get("providers", {})
        active = providers_cfg.get("active", "openai")
        provider_cfg = providers_cfg.get(active, {})
        model = str(provider_cfg.get("model", "")).strip()
        if not model:
            raise RuntimeError(f"Provider '{active}' has no model configured")
        return self.execute_prompt_with_selection(active, model, prompt, system_prompt=system_prompt)

    def execute_prompt_with_selection(self, provider: str, model: str, prompt: str, system_prompt: str = "") -> ProviderResult:
        providers_cfg = self._config.get("providers", {})
        provider_cfg = providers_cfg.get(provider, {})
        if not provider_cfg:
            raise RuntimeError(f"Unknown provider: {provider}")

        if provider == "openai":
            return self._call_openai(provider_cfg, model, prompt, system_prompt=system_prompt)
        if provider == "anthropic":
            return self._call_anthropic(provider_cfg, model, prompt, system_prompt=system_prompt)
        if provider == "gemini":
            return self._call_gemini(provider_cfg, model, prompt, system_prompt=system_prompt)
        raise RuntimeError(f"Unsupported provider: {provider}")

    def execute_prompt_streaming(
        self,
        prompt: str,
        system_prompt: str = "",
        on_chunk: Optional[Callable[[str], None]] = None,
    ) -> ProviderResult:
        providers_cfg = self._config.get("providers", {})
        active = providers_cfg.get("active", "openai")
        provider_cfg = providers_cfg.get(active, {})
        model = str(provider_cfg.get("model", "")).strip()
        if not model:
            raise RuntimeError(f"Provider '{active}' has no model configured")
        return self.execute_prompt_streaming_with_selection(active, model, prompt, system_prompt=system_prompt, on_chunk=on_chunk)

    def execute_prompt_streaming_with_selection(
        self,
        provider: str,
        model: str,
        prompt: str,
        system_prompt: str = "",
        on_chunk: Optional[Callable[[str], None]] = None,
    ) -> ProviderResult:
        providers_cfg = self._config.get("providers", {})
        provider_cfg = providers_cfg.get(provider, {})
        if not provider_cfg:
            raise RuntimeError(f"Unknown provider: {provider}")

        if provider == "openai":
            try:
                return self._call_openai_streaming(provider_cfg, model, prompt, system_prompt=system_prompt, on_chunk=on_chunk)
            except ProviderHTTPError as exc:
                if exc.status_code == 429:
                    raise
                return self._call_openai(provider_cfg, model, prompt, system_prompt=system_prompt)
            except RuntimeError:
                return self._call_openai(provider_cfg, model, prompt, system_prompt=system_prompt)
        return self.execute_prompt_with_selection(provider, model, prompt, system_prompt=system_prompt)

    def _call_openai(self, cfg: dict, model: str, prompt: str, system_prompt: str = "") -> ProviderResult:
        key = os.environ.get(cfg.get("api_key_env", ""), "")
        if not key:
            raise RuntimeError("OpenAI API key not configured")
        url = cfg.get("api_base", "https://api.openai.com/v1").rstrip("/") + "/chat/completions"
        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": prompt})
        payload = {
            "model": model,
            "messages": messages,
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

    def _call_openai_streaming(
        self,
        cfg: dict,
        model: str,
        prompt: str,
        system_prompt: str = "",
        on_chunk: Optional[Callable[[str], None]] = None,
    ) -> ProviderResult:
        key = os.environ.get(cfg.get("api_key_env", ""), "")
        if not key:
            raise RuntimeError("OpenAI API key not configured")
        url = cfg.get("api_base", "https://api.openai.com/v1").rstrip("/") + "/chat/completions"
        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": prompt})
        payload = {
            "model": model,
            "messages": messages,
            "temperature": float(cfg.get("temperature", 0.7)),
            "max_tokens": int(cfg.get("max_tokens", 4096)),
            "top_p": float(cfg.get("top_p", 1.0)),
            "stream": True,
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
        try:
            with urllib.request.urlopen(req, timeout=180) as resp:
                parts: list[str] = []
                event_count = 0
                while True:
                    raw_line = resp.readline()
                    if not raw_line:
                        break
                    line = raw_line.decode("utf-8").strip()
                    if not line.startswith("data:"):
                        continue
                    data = line[5:].strip()
                    if data == "[DONE]":
                        break
                    if not data:
                        continue
                    event_count += 1
                    try:
                        obj = json.loads(data)
                    except json.JSONDecodeError:
                        continue
                    choices = obj.get("choices") or []
                    if not choices or not isinstance(choices[0], dict):
                        continue
                    delta = choices[0].get("delta") or {}
                    text = str(delta.get("content") or "")
                    if text:
                        parts.append(text)
                        if on_chunk is not None:
                            on_chunk(text)
                output = "".join(parts)
                raw = {"streamed": True, "events": event_count}
                return ProviderResult(provider="openai", model=model, output=output, raw=raw)
        except urllib.error.HTTPError as exc:
            detail = ""
            try:
                detail = exc.read().decode("utf-8")
            except Exception:
                detail = str(exc)
            retry_after = self._retry_after_from_headers(exc.headers)
            raise ProviderHTTPError(
                status_code=exc.code,
                retry_after_s=retry_after,
                message=f"Provider HTTP {exc.code}: {detail[:500]}",
            ) from exc
        except urllib.error.URLError as exc:
            raise RuntimeError(f"Provider network error: {exc}") from exc

    def _call_anthropic(self, cfg: dict, model: str, prompt: str, system_prompt: str = "") -> ProviderResult:
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
        if system_prompt:
            payload["system"] = system_prompt
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

    def _call_gemini(self, cfg: dict, model: str, prompt: str, system_prompt: str = "") -> ProviderResult:
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
        if system_prompt:
            payload["systemInstruction"] = {"parts": [{"text": system_prompt}]}
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
        attempts = 3
        for attempt in range(1, attempts + 1):
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
                if exc.code >= 500 and attempt < attempts:
                    time.sleep(0.6 * attempt)
                    continue
                retry_after = self._retry_after_from_headers(exc.headers)
                raise ProviderHTTPError(
                    status_code=exc.code,
                    retry_after_s=retry_after,
                    message=f"Provider HTTP {exc.code}: {detail[:500]}",
                ) from exc
            except urllib.error.URLError as exc:
                if attempt < attempts:
                    time.sleep(0.6 * attempt)
                    continue
                raise RuntimeError(f"Provider network error: {exc}") from exc
        raise RuntimeError("Provider request failed after retries")

    @staticmethod
    def _retry_after_from_headers(headers: Any) -> Optional[int]:
        if headers is None:
            return None
        try:
            raw = headers.get("retry-after")
        except Exception:
            raw = None
        if raw is None:
            return None
        try:
            return max(0, int(float(str(raw).strip())))
        except Exception:
            return None
