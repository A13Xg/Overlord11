"""
webui/reviewer.py — Reviewer gate for the Tactical WebUI runner.

Performs pre-delivery checks before a job is marked COMPLETE:
  1. Secrets scan (re-uses cleanup_tool.py patterns if available, else built-in)
  2. Checks diff coverage against goal keywords
  3. Ensures no hardcoded provider/model names leaked into artifacts

Returns ReviewResult with pass/fail and a list of findings.
"""

from __future__ import annotations

import re
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

# ---------------------------------------------------------------------------
# Patterns for secrets scanning (mirrors cleanup_tool.py approach)
# ---------------------------------------------------------------------------

_SECRET_PATTERNS = [
    # Generic API key shapes
    re.compile(r"(api[_-]?key|apikey|secret|password|passwd|token|auth)[\"']?\s*[:=]\s*[\"'][A-Za-z0-9+/=_\-]{8,}", re.IGNORECASE),
    # AWS
    re.compile(r"AKIA[0-9A-Z]{16}"),
    # Anthropic
    re.compile(r"sk-ant-[A-Za-z0-9\-_]{20,}"),
    # OpenAI
    re.compile(r"sk-[A-Za-z0-9]{20,}"),
    # Google API key
    re.compile(r"AIza[0-9A-Za-z\-_]{35}"),
    # GitHub token
    re.compile(r"ghp_[A-Za-z0-9]{36}"),
]

_HARDCODED_PROVIDER_NAMES = re.compile(
    r'(?<![a-zA-Z])(claude-opus|claude-sonnet|claude-haiku|gpt-4o|gpt-3\.5|gemini-\d)',
    re.IGNORECASE,
)


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------

@dataclass
class ReviewFinding:
    severity: str  # "error" | "warning" | "info"
    rule: str
    detail: str
    file: str = ""


@dataclass
class ReviewResult:
    passed: bool
    findings: list[ReviewFinding] = field(default_factory=list)

    def summary(self) -> str:
        if self.passed:
            return "Reviewer gate PASSED"
        errors = [f for f in self.findings if f.severity == "error"]
        return f"Reviewer gate FAILED — {len(errors)} error(s), {len(self.findings)} total finding(s)"


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def run_review(
    job_id: str,
    goal: str,
    artifact_texts: dict[str, str],  # filename -> content
) -> ReviewResult:
    """
    Run all reviewer checks over the provided artifacts.

    Parameters
    ----------
    job_id:
        Used for logging / context only.
    goal:
        The original mission goal text.
    artifact_texts:
        Dict mapping artifact filenames to their text content.

    Returns
    -------
    ReviewResult with pass/fail and findings.
    """
    findings: list[ReviewFinding] = []

    for fname, content in artifact_texts.items():
        _check_secrets(fname, content, findings)
        _check_hardcoded_models(fname, content, findings)

    # Diff coverage: at least one artifact should exist if goal mentions "fix" or "change"
    _check_diff_coverage(goal, artifact_texts, findings)

    errors = [f for f in findings if f.severity == "error"]
    passed = len(errors) == 0
    return ReviewResult(passed=passed, findings=findings)


# ---------------------------------------------------------------------------
# Individual checks
# ---------------------------------------------------------------------------

def _check_secrets(fname: str, content: str, findings: list[ReviewFinding]) -> None:
    for pattern in _SECRET_PATTERNS:
        for match in pattern.finditer(content):
            findings.append(
                ReviewFinding(
                    severity="error",
                    rule="secrets_scan",
                    detail=f"Potential secret matched pattern {pattern.pattern[:40]}…",
                    file=fname,
                )
            )
            break  # one finding per pattern per file is enough


def _check_hardcoded_models(fname: str, content: str, findings: list[ReviewFinding]) -> None:
    matches = _HARDCODED_PROVIDER_NAMES.findall(content)
    for m in matches:
        findings.append(
            ReviewFinding(
                severity="warning",
                rule="no_hardcoded_model",
                detail=f"Hardcoded model name '{m}' found — use config.json instead",
                file=fname,
            )
        )


def _check_diff_coverage(
    goal: str,
    artifact_texts: dict[str, str],
    findings: list[ReviewFinding],
) -> None:
    """
    Very lightweight coverage check: if goal mentions 'fix'/'patch'/'change'
    then at least one patch artifact should exist.
    """
    trigger_words = {"fix", "patch", "change", "repair", "update", "refactor"}
    goal_lower = goal.lower()
    triggered = any(w in goal_lower for w in trigger_words)
    has_diff = any("patch" in k or "diff" in k or k.endswith(".patch") for k in artifact_texts)

    if triggered and not has_diff and artifact_texts:
        findings.append(
            ReviewFinding(
                severity="warning",
                rule="diff_coverage",
                detail="Goal implies code changes but no diff/patch artifact was recorded",
            )
        )
