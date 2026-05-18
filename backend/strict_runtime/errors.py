from dataclasses import dataclass, field
from typing import Any


@dataclass
class RuntimeErrorEnvelope:
    code: str
    tool: str
    message: str
    retryable: bool
    details: dict[str, Any] = field(default_factory=dict)
    correction_hint: str = ""
    suggested_params: dict[str, Any] = field(default_factory=dict)
    trace_id: str = ""

