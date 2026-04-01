"""
webui/llm_interface.py — High-level LLM call helper.

Delegates to webui/providers/ adapters.  Emits LLM_CALL_START /
LLM_CALL_END (or LLM_UNAVAILABLE in dry-run mode) via *emit*.
"""

from __future__ import annotations

import json
from typing import Any, Callable

from .events import EventLevel, EventType, make_event
from .providers.base import LLMCallError, LLMConfigError
from .providers.router import get_provider, get_provider_config

# Re-export for backwards compatibility
__all__ = ["llm_call", "LLMCallError", "LLMConfigError", "get_provider_config"]


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

    If no API key is available, emits LLM_UNAVAILABLE and returns a stub
    JSON response so the runner can continue demonstrating its structure.

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
    str — raw text content of the LLM response.
    """
    try:
        adapter = get_provider(provider, model)
    except LLMConfigError as exc:
        return _stub_response(job_id, emit, reason=str(exc))

    if not adapter.is_available():
        return _stub_response(
            job_id,
            emit,
            reason=f"No API key for provider '{adapter.name}'",
            provider=adapter.name,
            model=adapter.model,
        )

    if emit:
        emit(
            make_event(
                EventType.LLM_CALL_START,
                job_id,
                {"provider": adapter.name, "model": adapter.model},
            )
        )

    from .providers.base import LLMRequest
    req = LLMRequest(
        messages=messages,
        system=system,
        job_id=job_id,
    )
    try:
        resp = adapter.complete(req)
    except (LLMCallError, LLMConfigError) as exc:
        raise

    if emit:
        emit(
            make_event(
                EventType.LLM_CALL_END,
                job_id,
                {
                    "provider": resp.provider,
                    "model": resp.model,
                    "elapsed_s": resp.elapsed_s,
                    "input_tokens": resp.input_tokens,
                    "output_tokens": resp.output_tokens,
                },
            )
        )
    return resp.text


def _stub_response(
    job_id: str,
    emit: Callable | None,
    reason: str,
    provider: str = "",
    model: str = "",
) -> str:
    """Return a stub complete action and emit LLM_UNAVAILABLE."""
    if emit:
        emit(
            make_event(
                EventType.LLM_UNAVAILABLE,
                job_id,
                {
                    "reason": reason,
                    "provider": provider,
                    "model": model,
                    "mode": "dry_run",
                },
                level=EventLevel.WARN,
            )
        )
    return json.dumps(
        {
            "action": "complete",
            "summary": f"[DRY-RUN] LLM unavailable: {reason}. Runner completed stub iteration.",
        },
        ensure_ascii=False,
    )
