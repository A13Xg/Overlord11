from __future__ import annotations

from typing import Any, Dict, List

from pydantic import BaseModel, ConfigDict, Field


class ToolCallRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    tool_name: str = Field(min_length=1)
    arguments: Dict[str, Any]


class ErrorItem(BaseModel):
    code: str
    message: str
    details: Dict[str, Any] = Field(default_factory=dict)


class ResultEnvelope(BaseModel):
    ok: bool
    tool_name: str
    data: Dict[str, Any] = Field(default_factory=dict)
    warnings: List[str] = Field(default_factory=list)
    errors: List[ErrorItem] = Field(default_factory=list)
    metadata: Dict[str, Any] = Field(default_factory=dict)
