from __future__ import annotations

import os
import time
from datetime import datetime
from typing import Any, Literal
from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from .base import BaseTool

try:
    from ddgs import DDGS
except Exception:  # pragma: no cover - optional dependency in some test envs
    DDGS = None


class WebSearchArgs(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    query: str | None = Field(default=None, max_length=500)
    max_results: int = Field(default=10, ge=1, le=50)
    region: str = Field(default="us-en", min_length=2, max_length=16)
    safe_search: Literal["off", "moderate", "strict"] = "moderate"
    time_range: Literal["any", "day", "week", "month", "year"] = "any"
    result_type: Literal["auto", "text", "news", "images"] = "auto"
    include_snippets: bool = True
    include_metadata: bool = True
    include_rank: bool = True
    include_dates: bool = True
    domain_allowlist: list[str] = Field(default_factory=list)
    domain_blocklist: list[str] = Field(default_factory=list)

    @field_validator("query")
    @classmethod
    def normalize_query(cls, value: str | None) -> str | None:
        if value is None:
            return None
        q = " ".join(value.split()).strip()
        return q or None

    @field_validator("domain_allowlist", "domain_blocklist", mode="before")
    @classmethod
    def normalize_domains(cls, value: list[str] | None) -> list[str]:
        if value is None:
            return []
        out: list[str] = []
        for raw in value:
            d = str(raw or "").strip().lower()
            if not d:
                continue
            if "://" in d:
                d = urlparse(d).hostname or ""
            if d.startswith("www."):
                d = d[4:]
            if d and d not in out:
                out.append(d)
        return out

    @model_validator(mode="after")
    def validate_domain_lists(self) -> "WebSearchArgs":
        overlap = sorted(set(self.domain_allowlist).intersection(self.domain_blocklist))
        if overlap:
            raise ValueError(f"domain_allowlist and domain_blocklist overlap: {', '.join(overlap)}")
        return self


class WebSearchTool(BaseTool):
    name = "web_search"
    description = "Search the web via DuckDuckGo (DDGS) and return normalized, deduplicated structured results"
    risk_level = "low"
    destructive = False
    supports_dry_run = False
    timeout_behavior = "Per-attempt timeout with bounded retries"
    examples = [
        {"query": "latest python release notes", "max_results": 5, "result_type": "auto"},
        {
            "query": "agentic workflows",
            "result_type": "news",
            "time_range": "week",
            "domain_allowlist": ["openai.com", "anthropic.com"],
            "include_metadata": True,
        },
    ]
    input_model = WebSearchArgs

    def execute(self, args: WebSearchArgs) -> dict[str, Any]:
        started = time.monotonic()
        retries = 3
        timeout_seconds = 10
        last_error: str | None = None
        raw_results: list[dict[str, Any]] = []
        attempts = 0
        warnings: list[str] = []
        inferred_values: dict[str, Any] = {}

        query = args.query or "latest updates"
        if not args.query:
            inferred_values["query"] = query

        result_type = args.result_type
        if result_type == "auto":
            result_type = "news" if any(k in query.lower() for k in ("today", "latest", "breaking", "news")) else "text"
            inferred_values["result_type"] = result_type

        # DDGS >=8 uses single-letter timelimit codes: d/w/m/y
        _TIMELIMIT_MAP = {"day": "d", "week": "w", "month": "m", "year": "y"}

        for i in range(1, retries + 1):
            attempts = i
            try:
                if DDGS is None:
                    raise RuntimeError("ddgs dependency is not installed")
                with DDGS(timeout=timeout_seconds) as ddgs:
                    raw_limit = args.time_range
                    time_limit = None if raw_limit == "any" else _TIMELIMIT_MAP.get(raw_limit, raw_limit)
                    if result_type == "news":
                        results = ddgs.news(
                            query=query,
                            region=args.region,
                            safesearch=args.safe_search,
                            timelimit=time_limit,
                            max_results=args.max_results * 3,
                        )
                    elif result_type == "images":
                        results = ddgs.images(
                            query=query,
                            region=args.region,
                            safesearch=args.safe_search,
                            timelimit=time_limit,
                            max_results=args.max_results * 3,
                        )
                    else:
                        results = ddgs.text(
                            query=query,
                            region=args.region,
                            safesearch=args.safe_search,
                            timelimit=time_limit,
                            max_results=args.max_results * 3,
                        )
                    raw_results = list(results or [])
                    break
            except Exception as exc:
                last_error = str(exc)
                if i >= retries:
                    warnings.append(f"web search failed after {retries} attempts: {last_error}")
                    break
                time.sleep(0.3 * i)

        filtered = self._filter_domains(raw_results, args.domain_allowlist, args.domain_blocklist)
        deduped = self._dedupe(filtered)
        ranked = self._rank(deduped)
        top = ranked[: args.max_results]

        results: list[dict[str, Any]] = []
        for idx, item in enumerate(top, start=1):
            rec = {
                "title": item.get("title") or "",
                "url": item.get("url") or "",
                "snippet": (item.get("snippet") or "") if args.include_snippets else "",
                "domain": item.get("source_domain") or "",
                "source_domain": item.get("source_domain") or "",
                "rank": idx if args.include_rank else None,
                "published_date": item.get("published_date") if args.include_dates else None,
            }
            results.append(rec)

        out: dict[str, Any] = {
            "query": query,
            "result_type": result_type,
            "results": results,
            "_warnings": warnings,
        }
        if args.include_metadata:
            out["metadata"] = {
                "attempts": attempts,
                "provider": "ddgs",
                "timeout_seconds": timeout_seconds,
                "raw_count": len(raw_results),
                "after_domain_filter": len(filtered),
                "after_dedup": len(deduped),
                "returned": len(results),
                "duration_seconds": round(time.monotonic() - started, 4),
            }
            if last_error:
                out["metadata"]["last_error"] = last_error
        out["_metadata"] = {
            "workspace": str(os.environ.get("OVERLORD11_TASK_DIR") or os.getcwd()),
            "partial_success": bool(warnings),
            "fallbacks_used": ["retry"] if attempts > 1 else [],
            "inferred_values": inferred_values,
        }
        return out

    def _filter_domains(self, results: list[dict[str, Any]], allow: list[str], block: list[str]) -> list[dict[str, Any]]:
        allow_set = set(allow)
        block_set = set(block)
        out: list[dict[str, Any]] = []
        for item in results:
            normalized = self._normalize_result(item)
            domain = normalized.get("source_domain") or ""
            if allow_set and domain not in allow_set:
                continue
            if block_set and domain in block_set:
                continue
            out.append(normalized)
        return out

    def _dedupe(self, results: list[dict[str, Any]]) -> list[dict[str, Any]]:
        seen: set[str] = set()
        out: list[dict[str, Any]] = []
        for item in results:
            key = item.get("url") or f"{item.get('title','')}|{item.get('source_domain','')}"
            if key in seen:
                continue
            seen.add(key)
            out.append(item)
        return out

    def _rank(self, results: list[dict[str, Any]]) -> list[dict[str, Any]]:
        scored: list[dict[str, Any]] = []
        for idx, item in enumerate(results, start=1):
            title = item.get("title") or ""
            snippet = item.get("snippet") or ""
            domain = item.get("source_domain") or ""
            score = 1000 - idx
            score += min(len(title), 120) * 0.5
            score += min(len(snippet), 240) * 0.15
            if domain in {"wikipedia.org", "openai.com", "docs.python.org"}:
                score += 10
            item2 = dict(item)
            item2["_score"] = round(score, 3)
            scored.append(item2)
        scored.sort(key=lambda x: (-float(x.get("_score", 0.0)), str(x.get("url", ""))))
        return scored

    def _normalize_result(self, raw: dict[str, Any]) -> dict[str, Any]:
        title = str(raw.get("title") or "").strip()
        url = self._normalize_url(str(raw.get("href") or raw.get("url") or "").strip())
        snippet = str(raw.get("body") or raw.get("snippet") or "").strip()
        source_domain = (urlparse(url).hostname or "").lower()
        if source_domain.startswith("www."):
            source_domain = source_domain[4:]
        published_date = self._normalize_date(raw.get("date") or raw.get("published") or raw.get("published_date"))
        return {
            "title": title,
            "url": url,
            "snippet": snippet,
            "source_domain": source_domain,
            "published_date": published_date,
        }

    def _normalize_url(self, url: str) -> str:
        if not url:
            return ""
        parsed = urlparse(url)
        scheme = (parsed.scheme or "https").lower()
        netloc = (parsed.netloc or "").lower()
        path = parsed.path or "/"
        query_items = sorted(parse_qsl(parsed.query, keep_blank_values=False))
        query = urlencode(query_items)
        return urlunparse((scheme, netloc, path, "", query, ""))

    def _normalize_date(self, value: Any) -> str | None:
        if value is None:
            return None
        s = str(value).strip()
        if not s:
            return None
        for fmt in ("%Y-%m-%d", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%dT%H:%M:%SZ"):
            try:
                dt = datetime.strptime(s, fmt)
                return dt.date().isoformat()
            except ValueError:
                continue
        return s
