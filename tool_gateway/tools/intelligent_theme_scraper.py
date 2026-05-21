from __future__ import annotations

import re
from typing import Any, Literal

from bs4 import BeautifulSoup
from pydantic import BaseModel, ConfigDict, Field, field_validator

from .base import BaseTool
from .web_common import make_metadata, normalize_url
from .web_fetch import WebFetchTool, WebFetchArgs

_COLOR_RE = re.compile(r"#(?:[0-9a-fA-F]{3}|[0-9a-fA-F]{6})\b")


class IntelligentThemeScraperArgs(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    url: str = Field(min_length=3)
    analysis_depth: Literal["quick", "balanced", "deep"] = "balanced"
    extract_css_variables: bool = True
    detect_frameworks: bool = True
    include_component_summary: bool = True

    @field_validator("url")
    @classmethod
    def validate_url(cls, value: str) -> str:
        return normalize_url(value)


class IntelligentThemeScraperTool(BaseTool):
    name = "intelligent_theme_scraper"
    description = "Extract reusable design-system signals from webpage HTML/CSS"
    risk_level = "low"
    destructive = False
    supports_dry_run = False
    timeout_behavior = "Uses web_fetch timeouts"
    examples = [
        {"url": "https://example.com"},
        {"url": "https://example.com", "analysis_depth": "deep", "detect_frameworks": True},
    ]
    input_model = IntelligentThemeScraperArgs

    def execute(self, args: IntelligentThemeScraperArgs) -> dict[str, Any]:
        fetched = WebFetchTool().execute(WebFetchArgs(url=args.url, timeout_seconds=25))
        html = str(fetched.get("body") or "")
        warnings = list(fetched.get("_warnings", []))

        soup = BeautifulSoup(html, "html.parser")
        style_text = "\n".join(tag.get_text("\n", strip=True) for tag in soup.find_all("style"))
        full_text = f"{html}\n{style_text}"

        css_vars = sorted(set(re.findall(r"--[a-zA-Z0-9_-]+", full_text)))[:300]
        colors = sorted(set(_COLOR_RE.findall(full_text)))[:64]
        fonts = sorted(set(re.findall(r"font-family\s*:\s*([^;]+);", full_text, re.IGNORECASE)))[:20]
        spacing = sorted(set(re.findall(r"(?:margin|padding|gap)\s*:\s*([0-9.]+(?:px|rem|em|%)?)", full_text, re.IGNORECASE)))[:32]
        animations = sorted(set(re.findall(r"@keyframes\s+([a-zA-Z0-9_-]+)", full_text)))[:20]
        breakpoints = sorted(set(re.findall(r"@media\s*\([^)]*?(\d+px)", full_text)))[:20]

        framework_hints: list[str] = []
        if args.detect_frameworks:
            lower = full_text.lower()
            if "react" in lower or "data-reactroot" in lower:
                framework_hints.append("react")
            if "__next" in lower:
                framework_hints.append("nextjs")
            if "ng-" in lower or "angular" in lower:
                framework_hints.append("angular")
            if "vue" in lower or "nuxt" in lower:
                framework_hints.append("vue")

        components = []
        if args.include_component_summary:
            for selector, name in (("button", "button"), ("nav", "navigation"), ("form", "form"), ("header", "header"), ("footer", "footer")):
                count = len(soup.select(selector))
                if count:
                    components.append({"component": name, "count": count})

        return {
            "url": args.url,
            "color_palette": colors,
            "typography": {"font_families": fonts},
            "spacing_scale": spacing,
            "component_summaries": components,
            "framework_detection": sorted(set(framework_hints)),
            "reusable_css_patterns": css_vars if args.extract_css_variables else [],
            "animation_summaries": animations,
            "breakpoints": breakpoints,
            "_warnings": warnings,
            "_metadata": make_metadata(partial_success=bool(warnings), fallbacks_used=[], inferred_values={}),
        }
