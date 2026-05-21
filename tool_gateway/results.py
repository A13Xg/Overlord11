from __future__ import annotations

from .models import ErrorItem, ResultEnvelope


def success_result(tool_name: str, data: dict, *, warnings: list[str] | None = None, metadata: dict | None = None) -> dict:
    envelope = ResultEnvelope(
        ok=True,
        tool_name=tool_name,
        data=data or {},
        warnings=warnings or [],
        errors=[],
        metadata=metadata or {},
    )
    return envelope.model_dump()


def error_result(
    tool_name: str,
    *,
    code: str,
    message: str,
    details: dict | None = None,
    warnings: list[str] | None = None,
    recoverable: bool = True,
    retry_hint: str | None = None,
    metadata: dict | None = None,
) -> dict:
    md = dict(metadata or {})
    md.setdefault("recoverable", recoverable)
    if retry_hint:
        md.setdefault("retry_hint", retry_hint)
    envelope = ResultEnvelope(
        ok=False,
        tool_name=tool_name,
        data={},
        warnings=warnings or [],
        errors=[ErrorItem(code=code, message=message, details=details or {})],
        metadata=md,
    )
    return envelope.model_dump()
