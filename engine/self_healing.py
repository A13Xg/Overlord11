"""
engine/self_healing.py
=======================
Self-healing and autonomous retry system.

When a tool call or agent response results in an error, this module:
  1. Detects and classifies the error
  2. Builds a remediation strategy
  3. Injects an error-context message back into the agent context
  4. Signals the runner to retry (up to max_retries)

Error classes
-------------
  TOOL_ERROR      — tool raised an exception or returned success=False
  API_ERROR       — provider API returned an error / timed out
  PARSE_ERROR     — could not parse tool call from agent output
  RUNTIME_ERROR   — unexpected Python exception in the engine itself
  LOOP_LIMIT      — agent exceeded max loop count without completing
"""

import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


# ---------------------------------------------------------------------------
# Error classification
# ---------------------------------------------------------------------------

class ErrorClass:
    TOOL_ERROR = "tool_error"
    API_ERROR = "api_error"
    PARSE_ERROR = "parse_error"
    RUNTIME_ERROR = "runtime_error"
    LOOP_LIMIT = "loop_limit"


def classify_error(error: str, context: Optional[Dict[str, Any]] = None) -> str:
    """Heuristically classify an error string into an ErrorClass."""
    lower = error.lower()
    if any(k in lower for k in ("api", "rate limit", "status 4", "status 5", "timeout", "connection")):
        return ErrorClass.API_ERROR
    if any(k in lower for k in ("parse", "json", "syntax", "decode")):
        return ErrorClass.PARSE_ERROR
    if any(k in lower for k in ("tool", "not found", "argument", "missing")):
        return ErrorClass.TOOL_ERROR
    if "loop" in lower or "max_loops" in lower:
        return ErrorClass.LOOP_LIMIT
    return ErrorClass.RUNTIME_ERROR


# ---------------------------------------------------------------------------
# Healing strategies
# ---------------------------------------------------------------------------

_STRATEGY_TEMPLATES: Dict[str, str] = {
    ErrorClass.TOOL_ERROR: (
        "The tool call you made returned an error: {error}\n"
        "Please review the tool's expected arguments and try again with corrected parameters. "
        "If the tool is unavailable, use an alternative approach."
    ),
    ErrorClass.API_ERROR: (
        "The provider API returned an error: {error}\n"
        "This may be a temporary issue. Please wait a moment, then retry your last request. "
        "If the problem persists, simplify your request."
    ),
    ErrorClass.PARSE_ERROR: (
        "Your last response could not be parsed as a valid tool call: {error}\n"
        "Please ensure tool calls use the correct JSON format:\n"
        '```tool_call\n{{"tool": "tool_name", "args": {{"key": "value"}}}}\n```'
    ),
    ErrorClass.RUNTIME_ERROR: (
        "An unexpected runtime error occurred: {error}\n"
        "Please re-examine your approach and try a different strategy."
    ),
    ErrorClass.LOOP_LIMIT: (
        "You have reached the maximum execution loop limit.\n"
        "Please provide a concise final answer with what you have accomplished so far."
    ),
}


def build_healing_message(error_class: str, error: str) -> str:
    """Build a remediation message to inject into agent context."""
    template = _STRATEGY_TEMPLATES.get(error_class, _STRATEGY_TEMPLATES[ErrorClass.RUNTIME_ERROR])
    return template.format(error=error)


# ---------------------------------------------------------------------------
# SelfHealingSystem
# ---------------------------------------------------------------------------

@dataclass
class HealingAttempt:
    attempt: int
    error: str
    error_class: str
    strategy: str
    ts: float = field(default_factory=time.time)


class SelfHealingSystem:
    """
    Manages retry + error-feed-back loop for a single session.

    Usage
    -----
    healer = SelfHealingSystem(max_retries=3)

    if healer.should_retry(error):
        message = healer.heal(error)
        context.append({"role": "user", "content": message})
        # → re-enter agent loop
    else:
        # give up
    """

    def __init__(self, max_retries: int = 3, retry_delay: float = 1.0):
        self.max_retries = max_retries
        self.retry_delay = retry_delay
        self.attempts: List[HealingAttempt] = []
        self._total_retries = 0

    @property
    def retry_count(self) -> int:
        return self._total_retries

    def should_retry(self, error: str) -> bool:
        """True if another retry is allowed."""
        # Never retry loop-limit errors
        if classify_error(error) == ErrorClass.LOOP_LIMIT:
            return False
        return self._total_retries < self.max_retries

    def heal(
        self,
        error: str,
        context: Optional[Dict[str, Any]] = None,
        delay: Optional[float] = None,
    ) -> str:
        """
        Record the error, apply retry delay, and return the remediation
        message to inject into the agent context.
        """
        error_class = classify_error(error, context)
        strategy = build_healing_message(error_class, error)

        attempt = HealingAttempt(
            attempt=self._total_retries + 1,
            error=error,
            error_class=error_class,
            strategy=strategy,
        )
        self.attempts.append(attempt)
        self._total_retries += 1

        # Apply delay (longer for API errors)
        wait = delay if delay is not None else self._backoff_delay(error_class)
        if wait > 0:
            time.sleep(wait)

        return strategy

    def _backoff_delay(self, error_class: str) -> float:
        """Exponential backoff; API errors get longer delays."""
        base = self.retry_delay
        multiplier = 2 ** (self._total_retries - 1)
        if error_class == ErrorClass.API_ERROR:
            return min(base * multiplier * 2, 30.0)
        return min(base * multiplier, 10.0)

    def summary(self) -> Dict[str, Any]:
        return {
            "total_retries": self._total_retries,
            "max_retries": self.max_retries,
            "attempts": [
                {
                    "attempt": a.attempt,
                    "error_class": a.error_class,
                    "ts": a.ts,
                }
                for a in self.attempts
            ],
        }
