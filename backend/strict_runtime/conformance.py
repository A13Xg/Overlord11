"""
Report-only conformance gate for future strict runtime tooling.
"""

from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass
class ConformanceIssue:
    tool: str
    code: str
    message: str


def check_tools_report_only(tools_config: dict[str, Any]) -> list[ConformanceIssue]:
    issues: list[ConformanceIssue] = []
    for tool_name, cfg in sorted((tools_config or {}).items()):
        impl = str((cfg or {}).get("impl", "")).strip()
        if not impl:
            issues.append(ConformanceIssue(tool=tool_name, code="E_RUNTIME_CONFORMANCE", message="missing impl path"))
            continue
        p = Path(impl)
        if not p.exists():
            issues.append(ConformanceIssue(tool=tool_name, code="E_RUNTIME_CONFORMANCE", message="impl path missing on disk"))
    return issues

