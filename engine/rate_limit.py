"""
Rate limit exceptions and Retry-After header parsing.

Used by orchestrator_bridge.py to signal HTTP 429 responses, and by
runner.py to implement in-place pause with automatic resume.
"""

import time
import urllib.error

# Default wait when no Retry-After header is present.
_DEFAULT_RETRY_S: float = 60.0


class RateLimitError(Exception):
    """A single provider/model returned HTTP 429."""

    def __init__(self, provider: str, model: str, retry_after_s: float, message: str = ""):
        self.provider = provider
        self.model = model
        self.retry_after_s = max(retry_after_s, 1.0)
        self.message = message
        super().__init__(
            f"Rate limited by {provider}/{model}: retry after {self.retry_after_s:.0f}s"
            + (f" — {message}" if message else "")
        )


class AllProvidersRateLimitedError(Exception):
    """Every configured provider/model combination is currently rate limited."""

    def __init__(self, cooldowns: dict):
        # cooldowns: {provider_name: monotonic_timestamp_when_available}
        self.cooldowns = cooldowns
        super().__init__(
            f"All providers rate limited. Shortest wait: {self.shortest_wait_s():.0f}s. "
            f"Providers: {', '.join(cooldowns)}"
        )

    def shortest_wait_s(self) -> float:
        """Seconds until the earliest provider becomes available again."""
        if not self.cooldowns:
            return _DEFAULT_RETRY_S
        return max(0.0, min(ts - time.monotonic() for ts in self.cooldowns.values()))


def parse_retry_after(exc: urllib.error.HTTPError) -> float:
    """
    Extract wait seconds from an HTTP 429 response.

    Checks the Retry-After header (numeric seconds).
    Falls back to _DEFAULT_RETRY_S if the header is absent or unparseable.
    """
    try:
        header = (
            exc.headers.get("Retry-After")
            or exc.headers.get("retry-after")
            or ""
        )
        if header:
            return float(header)
    except (ValueError, AttributeError):
        pass
    return _DEFAULT_RETRY_S
