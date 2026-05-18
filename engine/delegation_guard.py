"""
Delegation retry guardrails.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

_BASE_DIR = Path(__file__).resolve().parent.parent


def validate_retry_strategy(
    previous_attempt: dict[str, Any],
    next_attempt: dict[str, Any],
    immutable_rules: list[str],
    known_agent_ids: set[str],
) -> tuple[bool, dict[str, Any]]:
    """
    Validate that retry changes only invocation strategy, not privileged intent.
    """
    prev_agent = str(previous_attempt.get("agent_id") or "").strip()
    next_agent = str(next_attempt.get("agent_id") or "").strip()
    if prev_agent != next_agent:
        return False, {"retry_block_reason": "agent_id_change_disallowed", "strategy_diff": {"from": prev_agent, "to": next_agent}}
    if next_agent not in known_agent_ids:
        return False, {"retry_block_reason": "unknown_agent_id", "strategy_diff": {"agent_id": next_agent}}

    # Immutable core strings must not appear in retry mutating intent.
    serialized = json.dumps(next_attempt, ensure_ascii=False).replace("\\", "/").lower()
    normalized_rules = [r.replace("\\", "/").lower().strip().rstrip("/") for r in immutable_rules if str(r).strip()]
    for rule in normalized_rules:
        if rule and rule in serialized:
            return False, {"retry_block_reason": "immutable_core_reference_detected", "strategy_diff": {"rule": rule}}

    allowed_delta_keys = {
        "task",
        "inputs",
        "expected_outputs",
        "timeout_s",
        "allow_parallel",
        "depends_on",
        "retry_policy",
        "step_id",
    }
    diff: dict[str, Any] = {}
    keys = set(previous_attempt.keys()) | set(next_attempt.keys())
    for key in sorted(keys):
        if previous_attempt.get(key) != next_attempt.get(key):
            diff[key] = {"from": previous_attempt.get(key), "to": next_attempt.get(key)}
            if key not in allowed_delta_keys and key != "agent_id":
                return False, {"retry_block_reason": "non_strategy_field_changed", "strategy_diff": diff}

    return True, {"retry_block_reason": None, "strategy_diff": diff}
