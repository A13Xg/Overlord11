from __future__ import annotations

from typing import Any

from bs4 import BeautifulSoup
from pydantic import BaseModel, ConfigDict, Field, field_validator

from .base import BaseTool
from .web_common import make_metadata, normalize_url
from .web_fetch import WebFetchTool, WebFetchArgs


class DynamicBrowserArgs(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    url: str = Field(min_length=3)
    timeout_seconds: int = Field(default=30, ge=1, le=120)
    wait_selector: str | None = None
    viewport: dict[str, int] | None = None
    user_agent: str | None = None
    capture_screenshot: bool = False

    @field_validator("url")
    @classmethod
    def validate_url(cls, value: str) -> str:
        return normalize_url(value)


class DynamicBrowserTool(BaseTool):
    name = "dynamic_browser"
    description = "Render javascript-heavy pages with Playwright and fallback to raw fetch"
    risk_level = "medium"
    destructive = False
    supports_dry_run = False
    timeout_behavior = "Playwright timeout then fallback to web_fetch"
    examples = [
        {"url": "https://example.com"},
        {"url": "https://example.com", "wait_selector": "main", "capture_screenshot": False},
    ]
    input_model = DynamicBrowserArgs

    def execute(self, args: DynamicBrowserArgs) -> dict[str, Any]:
        warnings: list[str] = []
        fallbacks: list[str] = []
        html = ""
        final_url = args.url
        console_errors: list[str] = []

        try:
            from playwright.sync_api import sync_playwright

            with sync_playwright() as p:
                browser = p.chromium.launch(headless=True)
                page = browser.new_page(
                    viewport=args.viewport or {"width": 1366, "height": 768},
                    user_agent=args.user_agent,
                )
                page.on("console", lambda msg: console_errors.append(msg.text) if msg.type == "error" else None)
                page.goto(args.url, timeout=args.timeout_seconds * 1000, wait_until="networkidle")
                if args.wait_selector:
                    page.wait_for_selector(args.wait_selector, timeout=args.timeout_seconds * 1000)
                html = page.content()
                final_url = page.url
                browser.close()
        except Exception as exc:
            warnings.append(f"playwright render unavailable: {exc}")
            fallbacks.append("raw_fetch")
            fetched = WebFetchTool().execute(WebFetchArgs(url=args.url, timeout_seconds=min(args.timeout_seconds, 30)))
            html = str(fetched.get("body") or "")
            final_url = str(fetched.get("final_url") or args.url)
            warnings.extend(fetched.get("_warnings", []))

        soup = BeautifulSoup(html, "html.parser")
        title = (soup.title.get_text(" ", strip=True) if soup.title else "")
        text = (soup.get_text("\n", strip=True) or "")[:12000]

        return {
            "url": args.url,
            "final_url": final_url,
            "title": title,
            "dom_length": len(html),
            "text_preview": text,
            "console_errors": console_errors[:25],
            "screenshot_path": "",
            "_warnings": warnings,
            "_metadata": make_metadata(
                partial_success=bool(fallbacks or warnings),
                fallbacks_used=fallbacks,
                inferred_values={},
                extra={"rendered_with": "playwright" if not fallbacks else "web_fetch"},
            ),
        }
