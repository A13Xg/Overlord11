"""webui/providers/anthropic_adapter.py — Anthropic Messages API adapter."""

from __future__ import annotations

import os
import time

from .base import LLMCallError, LLMProvider, LLMRequest, LLMResponse


class AnthropicAdapter(LLMProvider):
    def __init__(self, model: str, api_key_env: str, **kwargs):
        self._model = model
        self._api_key_env = api_key_env
        self._extra = kwargs

    @property
    def name(self) -> str:
        return "anthropic"

    @property
    def model(self) -> str:
        return self._model

    def is_available(self) -> bool:
        return bool(os.environ.get(self._api_key_env, ""))

    def complete(self, req: LLMRequest) -> LLMResponse:
        try:
            import anthropic  # type: ignore
        except ImportError:
            raise LLMCallError("anthropic package not installed. Run: pip install anthropic")

        api_key = os.environ.get(self._api_key_env, "")
        client = anthropic.Anthropic(api_key=api_key)
        t0 = time.monotonic()
        kwargs = {
            "model": self._model,
            "max_tokens": req.max_tokens,
            "messages": req.messages,
        }
        if req.system:
            kwargs["system"] = req.system
        try:
            resp = client.messages.create(**kwargs)
        except Exception as exc:
            raise LLMCallError(str(exc)) from exc

        elapsed = time.monotonic() - t0
        text = resp.content[0].text if resp.content else ""
        return LLMResponse(
            text=text,
            provider="anthropic",
            model=self._model,
            input_tokens=resp.usage.input_tokens if resp.usage else 0,
            output_tokens=resp.usage.output_tokens if resp.usage else 0,
            elapsed_s=round(elapsed, 3),
            raw=resp,
        )
