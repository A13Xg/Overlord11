"""
webui/models.py — Pydantic models for the Tactical WebUI REST API.
"""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any, Optional

from pydantic import BaseModel, ConfigDict, Field


# ---------------------------------------------------------------------------
# Enumerations
# ---------------------------------------------------------------------------

class JobStatus(str, Enum):
    PENDING = "PENDING"
    RUNNING = "RUNNING"
    PAUSED = "PAUSED"
    COMPLETE = "COMPLETE"
    FAILED = "FAILED"


# ---------------------------------------------------------------------------
# Request bodies
# ---------------------------------------------------------------------------

class CreateJobRequest(BaseModel):
    """Payload for POST /jobs."""

    goal: str = Field(..., description="Mission goal / instructions for the runner.")
    max_iterations: int = Field(10, ge=1, le=100, description="Budget: max runner loops.")
    max_time_seconds: int = Field(
        3600, ge=10, le=86400, description="Budget: wall-clock time limit in seconds."
    )
    provider: Optional[str] = Field(
        None,
        description="LLM provider override (anthropic/gemini/openai). Defaults to config.json active provider.",
    )
    model: Optional[str] = Field(
        None,
        description="Model override. Defaults to the provider's configured model.",
    )
    autonomous: bool = Field(
        True,
        description="If True, runner proceeds without permission prompts.",
    )


class DirectiveRequest(BaseModel):
    """Payload for POST /jobs/{job_id}/directive — injects user feedback mid-run."""

    message: str = Field(..., description="Feedback or instruction from the user.")


# ---------------------------------------------------------------------------
# Response / state models
# ---------------------------------------------------------------------------

class JobState(BaseModel):
    """Persisted job state snapshot — written to workspace/jobs/<id>/state.json."""

    job_id: str
    goal: str
    status: JobStatus = JobStatus.PENDING
    created_at: str
    started_at: Optional[str] = None
    finished_at: Optional[str] = None

    # budgets
    max_iterations: int = 10
    max_time_seconds: int = 3600
    iteration: int = 0

    # LLM config
    provider: Optional[str] = None
    model: Optional[str] = None
    autonomous: bool = True

    # outcome
    stop_reason: Optional[str] = None
    last_verify_passed: Optional[bool] = None
    last_verify_output: Optional[str] = None

    # misc
    assumptions: list[str] = Field(default_factory=list)
    directives: list[dict[str, Any]] = Field(default_factory=list)

    model_config = ConfigDict(use_enum_values=True)


class JobSummary(BaseModel):
    """Lightweight job listing row."""

    job_id: str
    goal: str
    status: str
    created_at: str
    iteration: int
    stop_reason: Optional[str] = None
