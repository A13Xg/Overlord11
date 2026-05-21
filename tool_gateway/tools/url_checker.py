"""
URL Checker tool — bulk URL availability checker with response times and status codes.
"""
from __future__ import annotations

import time
from typing import Any
from urllib.parse import urlparse

import requests
from pydantic import BaseModel, ConfigDict, Field

from .base import BaseTool
from .web_common import make_metadata

_DEFAULT_UA = "Overlord11-ToolGateway/1.0"


class UrlCheckerArgs(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    urls: list[str] = Field(min_length=1, description="List of URLs to check (max 50)")
    timeout_seconds: float = Field(10.0, ge=1.0, le=60.0, description="Per-URL timeout")
    follow_redirects: bool = Field(True, description="Follow HTTP redirects")
    check_ssl: bool = Field(True, description="Verify SSL certificates")
    method: str = Field("HEAD", description="HTTP method: HEAD (fast) or GET (full response)")


class UrlCheckerTool(BaseTool):
    name = "url_checker"
    description = (
        "Check availability, status codes, and response times for a list of URLs. "
        "Uses HEAD requests by default for speed. Returns status, latency, redirect chain, and content type."
    )
    risk_level = "low"
    destructive = False
    supports_dry_run = False
    timeout_behavior = f"timeout_seconds per URL"
    examples = [
        {
            "tool_name": "url_checker",
            "arguments": {"urls": ["https://example.com", "https://python.org"]},
        },
        {
            "tool_name": "url_checker",
            "arguments": {
                "urls": ["https://example.com/page1", "https://example.com/page2"],
                "method": "GET",
                "timeout_seconds": 5.0,
            },
        },
    ]
    input_model = UrlCheckerArgs

    def execute(self, args: UrlCheckerArgs) -> dict[str, Any]:
        if len(args.urls) > 50:
            raise ValueError("url_checker accepts at most 50 URLs per call")

        warnings: list[str] = []
        results: list[dict[str, Any]] = []
        method = args.method.upper() if args.method.upper() in {"HEAD", "GET"} else "HEAD"

        for url in args.urls:
            result = self._check_url(
                url=url,
                timeout=args.timeout_seconds,
                follow_redirects=args.follow_redirects,
                check_ssl=args.check_ssl,
                method=method,
            )
            results.append(result)
            if not result["ok"]:
                warnings.append(f"{url}: {result['error']}")

        reachable = sum(1 for r in results if r["ok"])
        return {
            "checked": len(results),
            "reachable": reachable,
            "unreachable": len(results) - reachable,
            "results": results,
            "_warnings": warnings,
            "_metadata": make_metadata(
                partial_success=bool(warnings),
                fallbacks_used=[],
                inferred_values={},
                extra={"method": method},
            ),
        }

    @staticmethod
    def _check_url(
        *,
        url: str,
        timeout: float,
        follow_redirects: bool,
        check_ssl: bool,
        method: str,
    ) -> dict[str, Any]:
        # Validate URL scheme
        parsed = urlparse(url)
        if parsed.scheme not in {"http", "https"}:
            return {
                "url": url,
                "ok": False,
                "status_code": None,
                "latency_ms": None,
                "final_url": None,
                "content_type": None,
                "error": f"Unsupported URL scheme: {parsed.scheme!r}",
            }

        t0 = time.monotonic()
        try:
            resp = requests.request(
                method=method,
                url=url,
                timeout=timeout,
                allow_redirects=follow_redirects,
                verify=check_ssl,
                headers={"User-Agent": _DEFAULT_UA},
            )
            latency_ms = round((time.monotonic() - t0) * 1000)
            return {
                "url": url,
                "ok": resp.status_code < 400,
                "status_code": resp.status_code,
                "latency_ms": latency_ms,
                "final_url": str(resp.url) if str(resp.url) != url else None,
                "content_type": resp.headers.get("content-type", "").split(";")[0].strip() or None,
                "error": None,
            }
        except requests.exceptions.SSLError as exc:
            latency_ms = round((time.monotonic() - t0) * 1000)
            return {
                "url": url,
                "ok": False,
                "status_code": None,
                "latency_ms": latency_ms,
                "final_url": None,
                "content_type": None,
                "error": f"SSL error: {exc}",
            }
        except requests.exceptions.Timeout:
            latency_ms = round((time.monotonic() - t0) * 1000)
            return {
                "url": url,
                "ok": False,
                "status_code": None,
                "latency_ms": latency_ms,
                "final_url": None,
                "content_type": None,
                "error": "Timeout",
            }
        except Exception as exc:
            latency_ms = round((time.monotonic() - t0) * 1000)
            return {
                "url": url,
                "ok": False,
                "status_code": None,
                "latency_ms": latency_ms,
                "final_url": None,
                "content_type": None,
                "error": str(exc)[:200],
            }
