from __future__ import annotations

import json
import re
from typing import Any

from bs4 import BeautifulSoup
from pydantic import BaseModel, ConfigDict, Field, model_validator

from .base import BaseTool
from .web_common import make_metadata, normalize_url
from .web_fetch import WebFetchTool, WebFetchArgs


class SemanticContentExtractorArgs(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    url: str | None = None
    html: str | None = None
    raw_text: str | None = None
    extraction_targets: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def require_source(self) -> "SemanticContentExtractorArgs":
        if not (self.url or self.html or self.raw_text):
            raise ValueError("at least one of url, html, raw_text is required")
        if self.url:
            self.url = normalize_url(self.url)
        return self


class SemanticContentExtractorTool(BaseTool):
    name = "semantic_content_extractor"
    description = "Extract semantic structures like entities, FAQ, contacts, tables, and JSON-LD"
    risk_level = "low"
    destructive = False
    supports_dry_run = False
    timeout_behavior = "Uses web_fetch when url provided"
    examples = [
        {"url": "https://example.com"},
        {"raw_text": "Contact us at support@example.com. Price: $29."},
    ]
    input_model = SemanticContentExtractorArgs

    def execute(self, args: SemanticContentExtractorArgs) -> dict[str, Any]:
        warnings: list[str] = []
        html = args.html or ""
        text = args.raw_text or ""

        if args.url and not html and not text:
            fetched = WebFetchTool().execute(WebFetchArgs(url=args.url, timeout_seconds=25))
            html = str(fetched.get("body") or "")
            warnings.extend(fetched.get("_warnings", []))

        if html and not text:
            text = BeautifulSoup(html, "html.parser").get_text("\n", strip=True)

        emails = sorted(set(re.findall(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}", text)))
        phones = sorted(set(re.findall(r"\+?[0-9][0-9\- ()]{7,}[0-9]", text)))
        prices = sorted(set(re.findall(r"(?:\$|USD\s?)\d+(?:\.\d{2})?", text, re.IGNORECASE)))

        entities = {
            "emails": emails,
            "phones": phones,
            "prices": prices,
        }

        faq = []
        for q, a in re.findall(r"(Q[:\-].{1,200}?)(?:\n|\r)+(A[:\-].{1,500}?)($|\n\n)", text, re.IGNORECASE | re.DOTALL):
            faq.append({"question": q.strip(), "answer": a.strip()})

        tables = []
        if html:
            soup = BeautifulSoup(html, "html.parser")
            for table in soup.find_all("table")[:10]:
                rows = []
                for tr in table.find_all("tr")[:20]:
                    cells = [td.get_text(" ", strip=True) for td in tr.find_all(["th", "td"])][:12]
                    if cells:
                        rows.append(cells)
                if rows:
                    tables.append({"rows": rows})

        json_ld = []
        opengraph: dict[str, str] = {}
        if html:
            soup = BeautifulSoup(html, "html.parser")
            for script in soup.find_all("script", attrs={"type": "application/ld+json"}):
                raw = script.get_text(" ", strip=True)
                try:
                    json_ld.append(json.loads(raw))
                except json.JSONDecodeError:
                    warnings.append("invalid json-ld block skipped")
            for meta in soup.find_all("meta"):
                key = (meta.get("property") or meta.get("name") or "").strip().lower()
                if key.startswith("og:"):
                    opengraph[key] = (meta.get("content") or "").strip()

        return {
            "entities": entities,
            "faq": faq,
            "contacts": {"emails": emails, "phones": phones},
            "tables": tables,
            "schema_org": json_ld,
            "open_graph": opengraph,
            "json_ld": json_ld,
            "_warnings": sorted(dict.fromkeys(warnings)),
            "_metadata": make_metadata(partial_success=bool(warnings), fallbacks_used=[], inferred_values={}),
        }
