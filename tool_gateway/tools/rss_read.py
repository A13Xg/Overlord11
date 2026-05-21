from __future__ import annotations

import email.utils
import xml.etree.ElementTree as ET
from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from .base import BaseTool
from .web_common import make_metadata, normalize_url, request_with_retries


class RssReadArgs(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    feed_urls: list[str] = Field(min_length=1)
    max_items: int = Field(default=20, ge=1, le=200)
    include_content: bool = False
    since_datetime: str | None = None


class RssReadTool(BaseTool):
    name = "rss_read"
    description = "Read and normalize RSS/Atom feeds"
    risk_level = "low"
    destructive = False
    supports_dry_run = False
    timeout_behavior = "Per-feed request timeout with partial success"
    examples = [
        {"feed_urls": ["https://planetpython.org/rss20.xml"]},
        {"feed_urls": ["https://example.com/feed.xml"], "max_items": 10, "include_content": True},
    ]
    input_model = RssReadArgs

    def execute(self, args: RssReadArgs) -> dict[str, Any]:
        warnings: list[str] = []
        fallbacks: list[str] = []
        all_items: list[dict[str, Any]] = []
        feed_results: list[dict[str, Any]] = []

        since_ts = _safe_parse_date(args.since_datetime) if args.since_datetime else None

        for raw in args.feed_urls:
            try:
                feed_url = normalize_url(raw)
            except ValueError:
                warnings.append(f"skipped invalid feed url: {raw}")
                continue

            response, rw, rf = request_with_retries(
                method="GET",
                url=feed_url,
                timeout_seconds=20,
                follow_redirects=True,
                retries=2,
            )
            warnings.extend(rw)
            fallbacks.extend(rf)
            if response is None:
                feed_results.append({"feed_url": feed_url, "ok": False, "items": []})
                continue

            text = response.text or ""
            items, item_warnings = _parse_feed_xml(text, include_content=args.include_content)
            warnings.extend(item_warnings)

            if since_ts is not None:
                items = [it for it in items if _safe_parse_date(it.get("published")) and _safe_parse_date(it.get("published")) >= since_ts]

            feed_results.append({"feed_url": feed_url, "ok": True, "items": items[: args.max_items]})
            all_items.extend(items)

        all_items = sorted(all_items, key=lambda x: x.get("published") or "", reverse=True)[: args.max_items]
        return {
            "items": all_items,
            "feeds": feed_results,
            "count": len(all_items),
            "_warnings": sorted(dict.fromkeys(warnings)),
            "_metadata": make_metadata(
                partial_success=any(not x.get("ok") for x in feed_results),
                fallbacks_used=sorted(dict.fromkeys(fallbacks)),
                inferred_values={},
            ),
        }


def _parse_feed_xml(xml_text: str, *, include_content: bool) -> tuple[list[dict[str, Any]], list[str]]:
    warnings: list[str] = []
    out: list[dict[str, Any]] = []
    try:
        root = ET.fromstring(xml_text)
    except ET.ParseError:
        warnings.append("feed parse error")
        return out, warnings

    channel_items = root.findall(".//item")
    atom_entries = root.findall("{http://www.w3.org/2005/Atom}entry")

    for item in channel_items:
        rec = {
            "title": _text(item.find("title")),
            "url": _text(item.find("link")),
            "published": _normalize_datetime(_text(item.find("pubDate")) or _text(item.find("date"))),
            "summary": _text(item.find("description")),
            "content": _text(item.find("content")) if include_content else "",
        }
        out.append(rec)

    for entry in atom_entries:
        link_node = entry.find("{http://www.w3.org/2005/Atom}link")
        link = (link_node.attrib.get("href") if link_node is not None else "") or ""
        rec = {
            "title": _text(entry.find("{http://www.w3.org/2005/Atom}title")),
            "url": link,
            "published": _normalize_datetime(_text(entry.find("{http://www.w3.org/2005/Atom}updated"))),
            "summary": _text(entry.find("{http://www.w3.org/2005/Atom}summary")),
            "content": _text(entry.find("{http://www.w3.org/2005/Atom}content")) if include_content else "",
        }
        out.append(rec)

    dedup: dict[str, dict[str, Any]] = {}
    for item in out:
        key = item.get("url") or (item.get("title") or "")
        if key and key not in dedup:
            dedup[key] = item

    return list(dedup.values()), warnings


def _text(node) -> str:
    return (node.text or "").strip() if node is not None and node.text else ""


def _normalize_datetime(value: str) -> str | None:
    if not value:
        return None
    try:
        dt = email.utils.parsedate_to_datetime(value)
        return dt.isoformat()
    except (TypeError, ValueError):
        pass
    return value


def _safe_parse_date(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
