"""webui/providers/openai_adapter.py — OpenAI Chat Completions adapter."""

from __future__ import annotations

import os
import time

from .base import LLMCallError, LLMProvider, LLMRequest, LLMResponse


class OpenAIAdapter(LLMProvider):
    def __init__(self, model: str, api_key_env: str, **kwargs):
        self._model = model
        self._api_key_env = api_key_env
        self._extra = kwargs

    @property
    def name(self) -> str:
        return "openai"

    @property
    def model(self) -> str:
        return self._model

    def is_available(self) -> bool:
        return bool(os.environ.get(self._api_key_env, ""))

    def complete(self, req: LLMRequest) -> LLMResponse:
        try:
            from openai import OpenAI  # type: ignore
        except ImportError:
            raise LLMCallError("openai package not installed. Run: pip install openai")

        api_key = os.environ.get(self._api_key_env, "")
        full_messages = []
        if req.system:
            full_messages.append({"role": "system", "content": req.system})
        full_messages.extend(req.messages)

        t0 = time.monotonic()
        try:
            client = OpenAI(api_key=api_key)
            response = client.chat.completions.create(
                model=self._model,
                messages=full_messages,
                max_tokens=req.max_tokens,
                temperature=req.temperature,
            )
        except Exception as exc:
            raise LLMCallError(str(exc)) from exc

        elapsed = time.monotonic() - t0
        text = response.choices[0].message.content or ""
        usage = response.usage
        return LLMResponse(
            text=text,
            provider="openai",
            model=self._model,
            input_tokens=usage.prompt_tokens if usage else 0,
            output_tokens=usage.completion_tokens if usage else 0,
            elapsed_s=round(elapsed, 3),
            raw=response,
        )
