"""webui/providers/gemini_adapter.py — Google Gemini API adapter."""

from __future__ import annotations

import os
import time

from .base import LLMCallError, LLMProvider, LLMRequest, LLMResponse


class GeminiAdapter(LLMProvider):
    def __init__(self, model: str, api_key_env: str, **kwargs):
        self._model = model
        self._api_key_env = api_key_env
        self._extra = kwargs

    @property
    def name(self) -> str:
        return "gemini"

    @property
    def model(self) -> str:
        return self._model

    def is_available(self) -> bool:
        return bool(os.environ.get(self._api_key_env, ""))

    def complete(self, req: LLMRequest) -> LLMResponse:
        try:
            import google.generativeai as genai  # type: ignore
        except ImportError:
            raise LLMCallError(
                "google-generativeai package not installed. "
                "Run: pip install google-generativeai"
            )

        api_key = os.environ.get(self._api_key_env, "")
        genai.configure(api_key=api_key)
        gmodel = genai.GenerativeModel(
            model_name=self._model,
            system_instruction=req.system or None,
        )
        history = []
        last_msg = req.messages[-1]["content"] if req.messages else ""
        for m in req.messages[:-1]:
            role = "user" if m["role"] == "user" else "model"
            history.append({"role": role, "parts": [m["content"]]})

        t0 = time.monotonic()
        try:
            chat = gmodel.start_chat(history=history)
            response = chat.send_message(last_msg)
        except Exception as exc:
            raise LLMCallError(str(exc)) from exc

        elapsed = time.monotonic() - t0
        return LLMResponse(
            text=response.text,
            provider="gemini",
            model=self._model,
            elapsed_s=round(elapsed, 3),
            raw=response,
        )
