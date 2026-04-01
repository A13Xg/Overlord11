"""
webui/providers/base.py — Abstract LLM provider interface.

All adapters must implement LLMProvider.complete().
"""

from __future__ import annotations

import abc
from dataclasses import dataclass, field
from typing import Any


class LLMConfigError(Exception):
    """Provider misconfiguration (unknown provider, missing key, etc.)."""


class LLMCallError(Exception):
    """HTTP-level or API-level error from the LLM provider."""


@dataclass
class LLMRequest:
    """Structured request to the LLM."""

    messages: list[dict[str, str]]
    system: str = ""
    max_tokens: int = 4096
    temperature: float = 0.7
    # Optional metadata (not sent to provider)
    job_id: str = ""
    task_profile: str = "default"  # used for routing / model selection


@dataclass
class LLMResponse:
    """Structured response from the LLM."""

    text: str
    provider: str
    model: str
    input_tokens: int = 0
    output_tokens: int = 0
    elapsed_s: float = 0.0
    raw: Any = field(default=None, repr=False)


class LLMProvider(abc.ABC):
    """Abstract base for all LLM provider adapters."""

    @property
    @abc.abstractmethod
    def name(self) -> str:
        """Provider identifier (e.g. 'anthropic')."""

    @property
    @abc.abstractmethod
    def model(self) -> str:
        """Currently configured model name."""

    @abc.abstractmethod
    def is_available(self) -> bool:
        """Return True if the API key is set and the provider is ready."""

    @abc.abstractmethod
    def complete(self, req: LLMRequest) -> LLMResponse:
        """
        Execute a blocking completion call.

        Raises
        ------
        LLMCallError
            On any API or HTTP error.
        LLMConfigError
            On misconfiguration (missing key, unknown model, etc.).
        """
