from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from .base import BaseTool
from .web_extract_text import WebExtractTextTool, WebExtractTextArgs
from .web_search import WebSearchTool, WebSearchArgs
from .web_common import make_metadata


class SearchAndExtractPipelineArgs(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    topics: list[str] = Field(default_factory=list)
    seed_urls: list[str] = Field(default_factory=list)
    max_results: int = Field(default=10, ge=1, le=50)
    deduplicate: bool = True
    freshness: Literal["any", "recent", "day", "week", "month", "year"] = "recent"


class SearchAndExtractPipelineTool(BaseTool):
    name = "search_and_extract_pipeline"
    description = "Run search->extract pipeline with partial-success handling"
    risk_level = "low"
    destructive = False
    supports_dry_run = False
    timeout_behavior = "Delegates to child tools"
    examples = [
        {"topics": ["python packaging"], "max_results": 5},
        {"seed_urls": ["https://docs.python.org/3/"], "deduplicate": True},
    ]
    input_model = SearchAndExtractPipelineArgs

    def execute(self, args: SearchAndExtractPipelineArgs) -> dict[str, Any]:
        warnings: list[str] = []
        fallbacks: list[str] = []
        inferred: dict[str, Any] = {}

        urls: list[str] = list(args.seed_urls)
        if not urls:
            query = " ".join(args.topics).strip()
            if not query:
                query = "latest technology updates"
                inferred["query"] = query
            time_range = "week" if args.freshness == "recent" else args.freshness
            search = WebSearchTool().execute(
                WebSearchArgs(query=query, max_results=args.max_results, time_range=time_range, include_metadata=True)
            )
            warnings.extend(search.get("_warnings", []))
            for rec in search.get("results", []):
                u = rec.get("url")
                if isinstance(u, str) and u:
                    urls.append(u)

        if args.deduplicate:
            urls = sorted(dict.fromkeys(urls))

        extracted: list[dict[str, Any]] = []
        for url in urls[: args.max_results]:
            try:
                item = WebExtractTextTool().execute(WebExtractTextArgs(url=url, include_metadata=True))
                extracted.append({
                    "url": url,
                    "title": item.get("title", ""),
                    "clean_text": item.get("clean_text", ""),
                    "metadata": item.get("metadata", {}),
                })
                warnings.extend(item.get("_warnings", []))
            except Exception as exc:
                warnings.append(f"extract failed for {url}: {exc}")
                fallbacks.append("partial_skip_failed_extract")

        ranked = sorted(extracted, key=lambda x: len(str(x.get("clean_text") or "")), reverse=True)
        return {
            "topics": args.topics,
            "seed_urls": args.seed_urls,
            "sources": urls[: args.max_results],
            "documents": ranked,
            "count": len(ranked),
            "_warnings": sorted(dict.fromkeys(warnings)),
            "_metadata": make_metadata(
                partial_success=(len(ranked) < max(1, len(urls[: args.max_results]))),
                fallbacks_used=sorted(dict.fromkeys(fallbacks)),
                inferred_values=inferred,
            ),
        }
