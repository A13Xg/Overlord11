from __future__ import annotations

import re
from typing import Any
from urllib.parse import urljoin

from bs4 import BeautifulSoup
from pydantic import BaseModel, ConfigDict, Field, field_validator

from .base import BaseTool
from .web_common import make_metadata, normalize_url
from .web_fetch import WebFetchTool, WebFetchArgs


class WebCodeScraperArgs(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    url: str = Field(min_length=3)
    include_js: bool = True
    include_css: bool = True
    include_network_analysis: bool = False

    @field_validator("url")
    @classmethod
    def validate_url(cls, value: str) -> str:
        return normalize_url(value)


class WebCodeScraperTool(BaseTool):
    name = "web_code_scraper"
    description = "Analyze frontend source assets for reusable implementation patterns"
    risk_level = "low"
    destructive = False
    supports_dry_run = False
    timeout_behavior = "Uses web_fetch timeouts"
    examples = [
        {"url": "https://example.com"},
        {"url": "https://example.com", "include_network_analysis": True},
    ]
    input_model = WebCodeScraperArgs

    def execute(self, args: WebCodeScraperArgs) -> dict[str, Any]:
        fetched = WebFetchTool().execute(WebFetchArgs(url=args.url, timeout_seconds=25))
        html = str(fetched.get("body") or "")
        warnings = list(fetched.get("_warnings", []))

        soup = BeautifulSoup(html, "html.parser")
        js_bundles: list[str] = []
        css_assets: list[str] = []

        if args.include_js:
            for script in soup.find_all("script", src=True):
                js_bundles.append(normalize_url(urljoin(args.url, script.get("src") or "")))

        if args.include_css:
            for link in soup.find_all("link", href=True):
                rel = " ".join(link.get("rel") or []).lower()
                if "stylesheet" in rel:
                    css_assets.append(normalize_url(urljoin(args.url, link.get("href") or "")))

        lower = html.lower()
        frameworks = []
        if "__next" in lower:
            frameworks.append("nextjs")
        if "react" in lower or "data-reactroot" in lower:
            frameworks.append("react")
        if "nuxt" in lower or "vue" in lower:
            frameworks.append("vue")
        if "angular" in lower or "ng-version" in lower:
            frameworks.append("angular")

        endpoints = sorted(set(re.findall(r"https?://[^\"'\s)]+/api/[^\"'\s)]+", html)))[:100]
        routes = sorted(set(re.findall(r"/(?:[a-zA-Z0-9_-]+/){0,4}[a-zA-Z0-9_-]+", html)))[:120]

        return {
            "url": args.url,
            "js_bundles": sorted(set(js_bundles)),
            "css_assets": sorted(set(css_assets)),
            "framework_detection": sorted(set(frameworks)),
            "discovered_routes": routes,
            "api_endpoints": endpoints,
            "component_inference": {
                "has_forms": "<form" in lower,
                "has_tables": "<table" in lower,
                "has_modals": "modal" in lower,
            },
            "network_analysis": {"enabled": args.include_network_analysis, "note": "static html inference only"},
            "_warnings": warnings,
            "_metadata": make_metadata(partial_success=bool(warnings), fallbacks_used=[], inferred_values={}),
        }
