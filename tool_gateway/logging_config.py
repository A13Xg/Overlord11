from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from typing import Any


_LOGGER = logging.getLogger("overlord11.tool_gateway")


def configure_logging() -> None:
    if _LOGGER.handlers:
        return
    handler = logging.StreamHandler()
    formatter = logging.Formatter("%(message)s")
    handler.setFormatter(formatter)
    _LOGGER.addHandler(handler)
    _LOGGER.setLevel(logging.INFO)


def _redact(value: Any) -> Any:
    if isinstance(value, dict):
        redacted = {}
        for k, v in value.items():
            lk = k.lower()
            if any(x in lk for x in ("token", "secret", "password", "key")):
                redacted[k] = "***"
            elif k == "environment" and isinstance(v, dict):
                redacted[k] = {ek: "***" for ek in v}
            else:
                redacted[k] = _redact(v)
        return redacted
    if isinstance(value, list):
        return [_redact(v) for v in value]
    return value


def log_event(event: dict[str, Any]) -> None:
    configure_logging()
    payload = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        **event,
    }
    _LOGGER.info(json.dumps(_redact(payload), ensure_ascii=False, default=str))
