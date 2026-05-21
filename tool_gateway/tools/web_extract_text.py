from __future__ import annotations

import re
from typing import Any, Literal

from bs4 import BeautifulSoup
from pydantic import BaseModel, ConfigDict, Field, model_validator

from .base import BaseTool
from .web_common import make_metadata, normalize_url, trim_text
from .web_fetch import WebFetchTool, WebFetchArgs


class WebExtractTextArgs(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    url: str | None = None
    html: str | None = None
    raw_text: str | None = None
    extraction_mode: Literal["auto", "article", "documentation", "blog"] = "auto"
    include_links: bool = False
    include_metadata: bool = True

    @model_validator(mode="after")
    def require_one_source(self) -> "WebExtractTextArgs":
        if not (self.url or self.html or self.raw_text):
            raise ValueError("at least one of url, html, raw_text is required")
        if self.url:
            self.url = normalize_url(self.url)
        return self


class WebExtractTextTool(BaseTool):
    name = "web_extract_text"
    description = "Extract readable text from a webpage, html, or raw text"
    risk_level = "low"
    destructive = False
    supports_dry_run = False
    timeout_behavior = "Uses web_fetch defaults when url is provided"
    examples = [
        {"url": "https://example.com"},
        {"html": "<html><body><article>Hello</article></body></html>", "include_links": True},
    ]
    input_model = WebExtractTextArgs

    def execute(self, args: WebExtractTextArgs) -> dict[str, Any]:
        warnings: list[str] = []
        fallbacks: list[str] = []
        inferred: dict[str, Any] = {}

        html = args.html or ""
        title = ""
        links: list[str] = []

        if not html and args.url:
            fetch = WebFetchTool().execute(WebFetchArgs(url=args.url))
            html = str(fetch.get("body") or "")
            warnings.extend(fetch.get("_warnings", []))
            fallbacks.extend(fetch.get("_metadata", {}).get("fallbacks_used", []))

        if args.raw_text:
            clean_text = trim_text(args.raw_text)
            inferred["content_type"] = "plain_text"
            return {
                "title": "",
                "clean_text": clean_text,
                "metadata": {"word_count": len(clean_text.split())} if args.include_metadata else {},
                "links": [],
                "inferred_content_type": "plain_text",
                "_warnings": warnings,
                "_metadata": make_metadata(partial_success=False, fallbacks_used=fallbacks, inferred_values=inferred),
            }

        soup = BeautifulSoup(html, "html.parser")
        for tag in soup(["script", "style", "noscript", "svg", "iframe", "nav", "footer", "aside"]):
            tag.decompose()

        title_node = soup.find("title")
        title = (title_node.get_text(" ", strip=True) if title_node else "")

        if args.include_links:
            seen: set[str] = set()
            for a in soup.find_all("a", href=True):
                href = (a.get("href") or "").strip()
                if href and href not in seen:
                    seen.add(href)
            links = sorted(seen)

        container = soup.find("article") or soup.find("main") or soup.body or soup
        text = container.get_text("\n", strip=True)
        text = re.sub(r"\n{3,}", "\n\n", text)
        clean_text = trim_text(text)

        inferred_type = args.extraction_mode
        if args.extraction_mode == "auto":
            inferred_type = "documentation" if "docs" in clean_text.lower()[:500] else "article"
            inferred["extraction_mode"] = inferred_type

        return {
            "title": title,
            "clean_text": clean_text,
            "metadata": {"word_count": len(clean_text.split()), "char_count": len(clean_text)} if args.include_metadata else {},
            "links": links,
            "inferred_content_type": inferred_type,
            "_warnings": warnings,
            "_metadata": make_metadata(
                partial_success=(not clean_text),
                fallbacks_used=fallbacks,
                inferred_values=inferred,
            ),
        }
