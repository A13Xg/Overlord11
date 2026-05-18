"""
Comprehensive loop governor for parent and sub-agent execution budgets.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass
class GovernorDecision:
    allow: bool
    reason: str | None = None
    warn: str | None = None


class LoopGovernor:
    def __init__(self, cfg: dict | None, *, fallback_max_parent_loops: int = 10):
        cfg = cfg or {}
        self.enabled = bool(cfg.get("enabled", True))
        self.max_parent_loops = int(cfg.get("max_parent_loops", fallback_max_parent_loops))
        self.max_subagent_loops_total = int(cfg.get("max_subagent_loops_total", max(2, fallback_max_parent_loops * 3)))
        self.max_subagent_loops_per_agent = int(cfg.get("max_subagent_loops_per_agent", max(1, fallback_max_parent_loops)))
        self.max_retry_loops = int(cfg.get("max_retry_loops", max(1, fallback_max_parent_loops)))
        self.max_effective_loops = int(cfg.get("max_effective_loops", max(2, fallback_max_parent_loops * 2)))
        self.progress_credit_enabled = bool(cfg.get("progress_credit_enabled", True))
        self.max_credit_per_epoch = int(cfg.get("max_credit_per_epoch", 1))
        self.progress_threshold = float(cfg.get("progress_threshold", 2.0))
        self.stall_threshold = float(cfg.get("stall_threshold", 2.0))
        self.stall_consecutive_limit = int(cfg.get("stall_consecutive_limit", 3))

        self.parent_loops_used = 0
        self.subagent_loops_used_total = 0
        self.subagent_loops_by_agent: dict[str, int] = {}
        self.retry_loops_used = 0
        self.effective_loops_used = 0
        self.credits_applied_total = 0
        self._stall_streak = 0
        self._terminal_reason: str | None = None
        self._history: list[dict[str, Any]] = []

    def start(self, run_context: dict[str, Any] | None = None) -> dict[str, Any]:
        return {"enabled": self.enabled, "context": run_context or {}, "snapshot": self.snapshot()}

    def before_parent_loop(self) -> GovernorDecision:
        if not self.enabled:
            return GovernorDecision(True)
        if self.parent_loops_used >= self.max_parent_loops:
            self._terminal_reason = "max_parent_loops_exhausted"
            return GovernorDecision(False, reason=self._terminal_reason)
        if self.effective_loops_used >= self.max_effective_loops:
            self._terminal_reason = "max_effective_loops_exhausted"
            return GovernorDecision(False, reason=self._terminal_reason)
        if self._stall_streak >= self.stall_consecutive_limit:
            self._terminal_reason = "stall_detected_no_progress"
            return GovernorDecision(False, reason=self._terminal_reason)
        return GovernorDecision(True)

    def after_parent_loop(self, metrics: dict[str, Any]) -> GovernorDecision:
        if not self.enabled:
            return GovernorDecision(True)
        self.parent_loops_used += 1
        self.effective_loops_used += 1
        progress_score = self._progress_score(metrics)
        stall_score = self._stall_score(metrics)
        credits = 0
        if (
            self.progress_credit_enabled
            and progress_score >= self.progress_threshold
            and stall_score < self.stall_threshold
        ):
            credits = min(self.max_credit_per_epoch, self.effective_loops_used)
            self.effective_loops_used -= credits
            self.credits_applied_total += credits
            self._stall_streak = 0
        else:
            self._stall_streak += 1 if stall_score >= self.stall_threshold else 0

        self._history.append(
            {
                "parent_loop": self.parent_loops_used,
                "progress_score": round(progress_score, 3),
                "stall_score": round(stall_score, 3),
                "credit_applied": credits,
                "effective_loops_used": self.effective_loops_used,
                "stall_streak": self._stall_streak,
            }
        )
        if len(self._history) > 200:
            self._history = self._history[-200:]
        if self._stall_streak >= self.stall_consecutive_limit:
            self._terminal_reason = "stall_detected_no_progress"
            return GovernorDecision(False, reason=self._terminal_reason)
        return GovernorDecision(True, warn="stall_warning" if self._stall_streak > 0 else None)

    def before_subagent(self, agent_id: str, metadata: dict[str, Any] | None = None) -> GovernorDecision:
        if not self.enabled:
            return GovernorDecision(True)
        used = self.subagent_loops_by_agent.get(agent_id, 0)
        if self.subagent_loops_used_total >= self.max_subagent_loops_total:
            self._terminal_reason = "max_subagent_loops_exhausted"
            return GovernorDecision(False, reason=self._terminal_reason)
        if used >= self.max_subagent_loops_per_agent:
            return GovernorDecision(False, reason="max_subagent_loops_per_agent_exhausted")
        return GovernorDecision(True)

    def after_subagent(self, agent_id: str, metrics: dict[str, Any]) -> GovernorDecision:
        if not self.enabled:
            return GovernorDecision(True)
        child_loops = int(metrics.get("child_loops_used", 1) or 1)
        child_loops = max(1, child_loops)
        self.subagent_loops_used_total += child_loops
        self.subagent_loops_by_agent[agent_id] = self.subagent_loops_by_agent.get(agent_id, 0) + child_loops
        self.effective_loops_used += child_loops
        if self.effective_loops_used >= self.max_effective_loops:
            self._terminal_reason = "max_effective_loops_exhausted"
            return GovernorDecision(False, reason=self._terminal_reason)
        return GovernorDecision(True)

    def increment_retry(self, count: int = 1) -> GovernorDecision:
        if not self.enabled:
            return GovernorDecision(True)
        self.retry_loops_used += max(0, int(count))
        if self.retry_loops_used >= self.max_retry_loops:
            self._terminal_reason = "retry_budget_exhausted"
            return GovernorDecision(False, reason=self._terminal_reason)
        return GovernorDecision(True)

    def snapshot(self) -> dict[str, Any]:
        return {
            "enabled": self.enabled,
            "parent_loops_used": self.parent_loops_used,
            "subagent_loops_used_total": self.subagent_loops_used_total,
            "subagent_loops_by_agent": dict(self.subagent_loops_by_agent),
            "retry_loops_used": self.retry_loops_used,
            "effective_loops_used": self.effective_loops_used,
            "credits_applied_total": self.credits_applied_total,
            "stall_streak": self._stall_streak,
            "limits": {
                "max_parent_loops": self.max_parent_loops,
                "max_subagent_loops_total": self.max_subagent_loops_total,
                "max_subagent_loops_per_agent": self.max_subagent_loops_per_agent,
                "max_retry_loops": self.max_retry_loops,
                "max_effective_loops": self.max_effective_loops,
            },
            "remaining": {
                "parent_loops": max(0, self.max_parent_loops - self.parent_loops_used),
                "subagent_loops_total": max(0, self.max_subagent_loops_total - self.subagent_loops_used_total),
                "retry_loops": max(0, self.max_retry_loops - self.retry_loops_used),
                "effective_loops": max(0, self.max_effective_loops - self.effective_loops_used),
            },
            "terminal_reason": self._terminal_reason,
            "history": list(self._history[-50:]),
        }

    def _progress_score(self, m: dict[str, Any]) -> float:
        score = 0.0
        if int(m.get("effectful_tool_success_count", 0)) > 0:
            score += 2.0
        if int(m.get("artifact_created_count", 0)) > 0:
            score += 1.5
        if int(m.get("delegation_completed_count", 0)) > 0:
            score += 1.5
        if int(m.get("new_state_transition_count", 0)) > 0:
            score += 1.0
        if int(m.get("error_reduction_count", 0)) > 0:
            score += 1.0
        return score

    def _stall_score(self, m: dict[str, Any]) -> float:
        score = 0.0
        if bool(m.get("repeated_tool_pattern", False)):
            score += 1.0
        if bool(m.get("repeated_error_pattern", False)):
            score += 1.0
        if bool(m.get("prose_only_non_trivial", False)):
            score += 1.0
        if bool(m.get("empty_or_invalid_response", False)):
            score += 1.0
        return score
