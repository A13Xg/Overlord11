from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator

from .base import BaseTool
from .web_common import domain_from_url, make_metadata, normalize_url, request_with_retries


class WebFetchArgs(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    url: str = Field(min_length=3)
    timeout_seconds: int = Field(default=20, ge=1, le=120)
    follow_redirects: bool = True
    headers: dict[str, str] = Field(default_factory=dict)
    user_agent: str | None = None

    @field_validator("url")
    @classmethod
    def validate_url(cls, value: str) -> str:
        return normalize_url(value)


class WebFetchTool(BaseTool):
    name = "web_fetch"
    description = "Safely fetch webpage content with redirect and timeout handling"
    risk_level = "low"
    destructive = False
    supports_dry_run = False
    timeout_behavior = "Request-level timeout with bounded retries"
    examples = [
        {"url": "https://example.com"},
        {"url": "https://docs.python.org/3/", "timeout_seconds": 15, "follow_redirects": True},
    ]
    input_model = WebFetchArgs

    def execute(self, args: WebFetchArgs) -> dict[str, Any]:
        headers = dict(args.headers)
        inferred_values: dict[str, Any] = {}
        if args.user_agent:
            headers["User-Agent"] = args.user_agent
        elif "User-Agent" not in headers:
            inferred_values["user_agent"] = "default"

        response, warnings, fallbacks = request_with_retries(
            method="GET",
            url=args.url,
            timeout_seconds=args.timeout_seconds,
            follow_redirects=args.follow_redirects,
            headers=headers,
            retries=2,
        )

        if response is None:
            return {
                "url": args.url,
                "status_code": None,
                "content_type": None,
                "final_url": None,
                "domain": domain_from_url(args.url),
                "headers": {},
                "body": "",
                "_warnings": warnings,
                "_metadata": make_metadata(partial_success=False, fallbacks_used=fallbacks, inferred_values=inferred_values),
            }

        content_type = response.headers.get("Content-Type", "").split(";")[0].strip().lower()
        text = response.text if response.text is not None else ""
        return {
            "url": args.url,
            "status_code": response.status_code,
            "content_type": content_type,
            "final_url": response.url,
            "domain": domain_from_url(response.url),
            "headers": {k: v for k, v in sorted(response.headers.items())},
            "body": text,
            "_warnings": warnings,
            "_metadata": make_metadata(
                partial_success=(response.status_code >= 400),
                fallbacks_used=fallbacks,
                inferred_values=inferred_values,
                extra={"redirected": response.url != args.url},
            ),
        }
