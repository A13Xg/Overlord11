"""
AgenticToolset - Web Researcher
=================================
Web research and scraping tool. Searches the web via DuckDuckGo, discovers and
parses RSS/Atom feeds, fetches and extracts readable content from web pages.

Uses only Python standard library. Optionally leverages the `duckduckgo-search`
package for enhanced search results when installed.

Usage:
    python web_researcher.py --action search --query "python fastapi tutorial"
    python web_researcher.py --action search --query "machine learning" --max_results 5
    python web_researcher.py --action fetch --url https://example.com
    python web_researcher.py --action extract --url https://example.com
    python web_researcher.py --action find_feeds --url https://example.com
    python web_researcher.py --action parse_feed --url https://example.com/rss.xml
"""

import json
import os
import re
import ssl
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime
from html.parser import HTMLParser
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from log_manager import log_tool_invocation, log_error

# --- Constants ---

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
)
DEFAULT_TIMEOUT = 15
MAX_CONTENT_SIZE = 5_000_000  # 5 MB


# --- HTTP Utilities ---

def _create_ssl_context():
    """Create an SSL context that works across platforms."""
    try:
        return ssl.create_default_context()
    except Exception:
        ctx = ssl._create_unverified_context()
        return ctx


def _fetch_url(url: str, timeout: int = DEFAULT_TIMEOUT,
               headers: dict = None, data: bytes = None,
               method: str = None) -> dict:
    """Fetch a URL and return response details."""
    hdrs = {"User-Agent": USER_AGENT, "Accept-Language": "en-US,en;q=0.9"}
    if headers:
        hdrs.update(headers)

    req = urllib.request.Request(url, headers=hdrs, data=data, method=method)
    ctx = _create_ssl_context()

    try:
        with urllib.request.urlopen(req, timeout=timeout, context=ctx) as resp:
            content_type = resp.headers.get("Content-Type", "")
            charset = "utf-8"
            if "charset=" in content_type:
                charset = content_type.split("charset=")[-1].split(";")[0].strip()

            raw = resp.read(MAX_CONTENT_SIZE)
            try:
                text = raw.decode(charset, errors="replace")
            except (LookupError, UnicodeDecodeError):
                text = raw.decode("utf-8", errors="replace")

            return {
                "status": resp.status,
                "url": resp.url,
                "content_type": content_type,
                "content_length": len(raw),
                "text": text,
            }
    except urllib.error.HTTPError as e:
        return {"error": f"HTTP {e.code}: {e.reason}", "status": e.code}
    except urllib.error.URLError as e:
        return {"error": f"URL Error: {e.reason}"}
    except Exception as e:
        return {"error": str(e)}


# --- HTML Text Extraction ---

class _TextExtractor(HTMLParser):
    """Extract readable text from HTML, skipping script/style tags."""

    SKIP_TAGS = {"script", "style", "noscript", "svg", "path", "meta", "link"}
    BLOCK_TAGS = {
        "p", "div", "br", "h1", "h2", "h3", "h4", "h5", "h6",
        "li", "tr", "td", "th", "blockquote", "pre", "hr",
        "section", "article", "header", "footer", "nav", "main",
    }

    def __init__(self):
        super().__init__()
        self._text = []
        self._skip_depth = 0
        self._links = []
        self._current_href = None

    def handle_starttag(self, tag, attrs):
        tag = tag.lower()
        if tag in self.SKIP_TAGS:
            self._skip_depth += 1
        if tag in self.BLOCK_TAGS:
            self._text.append("\n")
        if tag == "a":
            for name, val in attrs:
                if name == "href" and val:
                    self._current_href = val

    def handle_endtag(self, tag):
        tag = tag.lower()
        if tag in self.SKIP_TAGS:
            self._skip_depth = max(0, self._skip_depth - 1)
        if tag in self.BLOCK_TAGS:
            self._text.append("\n")
        if tag == "a":
            self._current_href = None

    def handle_data(self, data):
        if self._skip_depth == 0:
            self._text.append(data)
            if self._current_href:
                self._links.append({
                    "text": data.strip(),
                    "href": self._current_href,
                })

    def get_text(self) -> str:
        raw = "".join(self._text)
        lines = []
        for line in raw.splitlines():
            cleaned = " ".join(line.split())
            if cleaned:
                lines.append(cleaned)
        return "\n".join(lines)

    def get_links(self) -> list:
        return [l for l in self._links if l["text"]]


def extract_text(html: str) -> dict:
    """Extract readable text and links from HTML."""
    parser = _TextExtractor()
    try:
        parser.feed(html)
    except Exception:
        pass
    return {
        "text": parser.get_text(),
        "links": parser.get_links()[:100],
    }


# --- DuckDuckGo Search ---

def _ddg_search_stdlib(query: str, max_results: int = 10) -> list:
    """Search DuckDuckGo using the HTML interface (stdlib only)."""
    results = []

    url = "https://html.duckduckgo.com/html/"
    data = urllib.parse.urlencode({"q": query}).encode("utf-8")
    headers = {"Content-Type": "application/x-www-form-urlencoded"}

    resp = _fetch_url(url, data=data, headers=headers, method="POST")
    if "error" in resp:
        return [{"error": resp["error"]}]

    html = resp["text"]

    # Extract result blocks: links with class "result__a" and snippets
    result_pattern = re.compile(
        r'<a[^>]*class="result__a"[^>]*href="([^"]*)"[^>]*>(.*?)</a>'
        r'.*?'
        r'<a[^>]*class="result__snippet"[^>]*>(.*?)</a>',
        re.DOTALL,
    )

    for match in result_pattern.finditer(html):
        if len(results) >= max_results:
            break

        raw_url = match.group(1)
        title = re.sub(r"<[^>]+>", "", match.group(2)).strip()
        snippet = re.sub(r"<[^>]+>", "", match.group(3)).strip()

        # DDG wraps URLs in a redirect; extract the actual URL
        if "uddg=" in raw_url:
            parsed = urllib.parse.parse_qs(urllib.parse.urlparse(raw_url).query)
            actual_url = parsed.get("uddg", [raw_url])[0]
        else:
            actual_url = raw_url

        if title and actual_url:
            results.append({
                "title": title,
                "url": urllib.parse.unquote(actual_url),
                "snippet": snippet,
            })

    # Simpler fallback pattern if the above didn't match
    if not results:
        link_pattern = re.compile(
            r'<a[^>]*class="result__a"[^>]*href="([^"]*)"[^>]*>(.*?)</a>',
            re.DOTALL,
        )
        for match in link_pattern.finditer(html):
            if len(results) >= max_results:
                break
            raw_url = match.group(1)
            title = re.sub(r"<[^>]+>", "", match.group(2)).strip()
            if "uddg=" in raw_url:
                parsed = urllib.parse.parse_qs(
                    urllib.parse.urlparse(raw_url).query
                )
                actual_url = parsed.get("uddg", [raw_url])[0]
            else:
                actual_url = raw_url
            if title and actual_url:
                results.append({
                    "title": title,
                    "url": urllib.parse.unquote(actual_url),
                    "snippet": "",
                })

    return results


def _ddg_instant_answer(query: str) -> dict:
    """Query DuckDuckGo Instant Answer API for supplemental context."""
    params = urllib.parse.urlencode({
        "q": query, "format": "json", "no_html": "1", "skip_disambig": "1",
    })
    url = f"https://api.duckduckgo.com/?{params}"

    resp = _fetch_url(url)
    if "error" in resp:
        return resp

    try:
        data = json.loads(resp["text"])
        result = {
            "abstract": data.get("Abstract", ""),
            "abstract_source": data.get("AbstractSource", ""),
            "abstract_url": data.get("AbstractURL", ""),
            "answer": data.get("Answer", ""),
            "definition": data.get("Definition", ""),
            "related_topics": [],
        }
        for topic in data.get("RelatedTopics", [])[:10]:
            if "Text" in topic:
                result["related_topics"].append({
                    "text": topic["Text"],
                    "url": topic.get("FirstURL", ""),
                })
        return result
    except (json.JSONDecodeError, KeyError) as e:
        return {"error": f"Failed to parse DDG response: {e}"}


def web_search(query: str, max_results: int = 10) -> dict:
    """Search the web using DuckDuckGo.

    Tries the duckduckgo-search package first for richer results, then
    falls back to stdlib HTML scraping of DuckDuckGo Lite.
    """
    # Try duckduckgo-search package first
    try:
        from duckduckgo_search import DDGS
        with DDGS() as ddgs:
            results = list(ddgs.text(query, max_results=max_results))
            return {
                "provider": "duckduckgo-search",
                "query": query,
                "results": results,
                "count": len(results),
            }
    except ImportError:
        pass
    except Exception:
        pass

    # Fallback to stdlib HTML scraping
    results = _ddg_search_stdlib(query, max_results)

    # Also fetch instant answer for supplemental context
    instant = _ddg_instant_answer(query)

    return {
        "provider": "duckduckgo-html-lite",
        "query": query,
        "results": results,
        "count": len(results),
        "instant_answer": instant if not instant.get("error") else None,
    }


# --- RSS Feed Discovery & Parsing ---

def find_feeds(url: str) -> dict:
    """Discover RSS/Atom feed URLs linked from a web page."""
    resp = _fetch_url(url)
    if "error" in resp:
        return resp

    html = resp["text"]
    feeds = []

    # Look for <link> tags with RSS/Atom types
    link_pattern = re.compile(
        r"<link[^>]*"
        r'type=["\']?(application/rss\+xml|application/atom\+xml|'
        r'application/feed\+json)["\']?'
        r"[^>]*>",
        re.IGNORECASE,
    )

    for match in link_pattern.finditer(html):
        tag = match.group(0)

        href_match = re.search(r'href=["\']?([^"\'\s>]+)', tag)
        if not href_match:
            continue
        href = href_match.group(1)

        title_match = re.search(r'title=["\']([^"\']*)', tag)
        title = title_match.group(1) if title_match else ""

        type_match = re.search(r'type=["\']?([^"\'\s>]+)', tag)
        feed_type = type_match.group(1) if type_match else ""

        # Resolve relative URLs
        if href.startswith("/"):
            parsed = urllib.parse.urlparse(url)
            href = f"{parsed.scheme}://{parsed.netloc}{href}"
        elif not href.startswith("http"):
            href = urllib.parse.urljoin(url, href)

        feeds.append({"url": href, "title": title, "type": feed_type})

    # Probe common feed paths if nothing found in HTML
    if not feeds:
        common_paths = [
            "/feed", "/rss", "/feed.xml", "/rss.xml", "/atom.xml",
            "/feeds/posts/default", "/index.xml", "/?feed=rss2",
        ]
        parsed = urllib.parse.urlparse(url)
        base = f"{parsed.scheme}://{parsed.netloc}"

        for path in common_paths:
            test_url = base + path
            probe = _fetch_url(test_url, timeout=5)
            if "error" not in probe and probe.get("status") == 200:
                ct = probe.get("content_type", "")
                preview = probe.get("text", "")[:500]
                if any(x in ct for x in ("xml", "rss", "atom")) or \
                   "<rss" in preview or "<feed" in preview:
                    feeds.append({
                        "url": test_url,
                        "title": "Auto-discovered",
                        "type": "auto-detected",
                    })

    return {
        "source_url": url,
        "feeds_found": len(feeds),
        "feeds": feeds,
    }


def parse_feed(url: str, max_entries: int = 20) -> dict:
    """Parse an RSS or Atom feed and return structured entries."""
    resp = _fetch_url(url)
    if "error" in resp:
        return resp

    try:
        root = ET.fromstring(resp["text"])
    except ET.ParseError as e:
        return {"error": f"XML parse error: {e}"}

    entries = []
    feed_info = {}

    ns = {
        "atom": "http://www.w3.org/2005/Atom",
        "dc": "http://purl.org/dc/elements/1.1/",
        "content": "http://purl.org/rss/1.0/modules/content/",
    }

    if root.tag.endswith("feed") or \
       root.tag == "{http://www.w3.org/2005/Atom}feed":
        # --- Atom feed ---
        feed_info["type"] = "atom"
        feed_info["title"] = (
            _xml_text(root, "atom:title", ns) or _xml_text(root, "title") or ""
        )
        feed_info["link"] = (
            _xml_attr(root, "atom:link[@rel='alternate']", "href", ns) or ""
        )

        items = root.findall("atom:entry", ns) or root.findall("entry")
        for entry in items[:max_entries]:
            entries.append({
                "title": (
                    _xml_text(entry, "atom:title", ns)
                    or _xml_text(entry, "title") or ""
                ),
                "link": (
                    _xml_attr(entry, "atom:link[@rel='alternate']", "href", ns)
                    or _xml_attr(entry, "atom:link", "href", ns)
                    or _xml_text(entry, "link") or ""
                ),
                "published": (
                    _xml_text(entry, "atom:published", ns)
                    or _xml_text(entry, "atom:updated", ns)
                    or _xml_text(entry, "published") or ""
                ),
                "summary": (
                    _xml_text(entry, "atom:summary", ns)
                    or _xml_text(entry, "summary") or ""
                )[:500],
                "author": (
                    _xml_text(entry, "atom:author/atom:name", ns)
                    or _xml_text(entry, "author/name") or ""
                ),
            })
    else:
        # --- RSS feed ---
        channel = root.find("channel") or root
        feed_info["type"] = "rss"
        feed_info["title"] = _xml_text(channel, "title") or ""
        feed_info["link"] = _xml_text(channel, "link") or ""
        feed_info["description"] = (_xml_text(channel, "description") or "")[:300]

        items = channel.findall("item") or root.findall("item")
        for item in items[:max_entries]:
            entries.append({
                "title": _xml_text(item, "title") or "",
                "link": (
                    _xml_text(item, "link")
                    or _xml_text(item, "guid") or ""
                ),
                "published": (
                    _xml_text(item, "pubDate")
                    or _xml_text(item, "dc:date", ns) or ""
                ),
                "summary": (_xml_text(item, "description") or "")[:500],
                "author": (
                    _xml_text(item, "author")
                    or _xml_text(item, "dc:creator", ns) or ""
                ),
            })

    return {
        "feed_url": url,
        "feed_info": feed_info,
        "entry_count": len(entries),
        "entries": entries,
    }


def _xml_text(el, path, ns=None):
    """Get text content of an XML element by path."""
    child = el.find(path, ns) if ns else el.find(path)
    if child is not None and child.text:
        return child.text.strip()
    return None


def _xml_attr(el, path, attr, ns=None):
    """Get attribute value of an XML element by path."""
    child = el.find(path, ns) if ns else el.find(path)
    if child is not None:
        return child.get(attr, "")
    return None


# --- Page Fetch & Extract ---

def fetch_page(url: str) -> dict:
    """Fetch a web page and return raw content."""
    resp = _fetch_url(url)
    if "error" in resp:
        return resp

    return {
        "url": resp.get("url", url),
        "status": resp["status"],
        "content_type": resp["content_type"],
        "content_length": resp["content_length"],
        "content": resp["text"][:50000],
    }


def extract_page(url: str) -> dict:
    """Fetch a web page and extract readable text content."""
    resp = _fetch_url(url)
    if "error" in resp:
        return resp

    extracted = extract_text(resp["text"])

    title_match = re.search(
        r"<title[^>]*>(.*?)</title>", resp["text"],
        re.IGNORECASE | re.DOTALL,
    )
    title = (
        re.sub(r"<[^>]+>", "", title_match.group(1)).strip()
        if title_match else ""
    )

    desc_match = re.search(
        r'<meta[^>]*name=["\']description["\'][^>]*content=["\']([^"\']*)',
        resp["text"], re.IGNORECASE,
    )
    description = desc_match.group(1).strip() if desc_match else ""

    return {
        "url": resp.get("url", url),
        "title": title,
        "description": description,
        "text": extracted["text"][:30000],
        "links": extracted["links"][:50],
        "content_length": resp["content_length"],
    }


# --- CLI Interface ---

def main():
    import argparse

    parser = argparse.ArgumentParser(
        description="AgenticToolset Web Researcher"
    )
    parser.add_argument(
        "--action", required=True,
        choices=["search", "fetch", "extract", "find_feeds", "parse_feed"],
        help="Action to perform",
    )
    parser.add_argument("--query", default=None, help="Search query (for search action)")
    parser.add_argument("--url", default=None, help="URL to fetch/analyze")
    parser.add_argument(
        "--max_results", type=int, default=10, help="Max search results",
    )
    parser.add_argument(
        "--max_entries", type=int, default=20, help="Max feed entries to return",
    )
    parser.add_argument("--output", default=None, help="Write result to JSON file")
    parser.add_argument("--session_id", default=None, help="Session ID for logging")

    args = parser.parse_args()
    session_id = args.session_id or "unset"

    start = time.time()
    result = {}

    if args.action == "search":
        if not args.query:
            parser.error("--query is required for search action")
        result = web_search(args.query, max_results=args.max_results)

    elif args.action == "fetch":
        if not args.url:
            parser.error("--url is required for fetch action")
        result = fetch_page(args.url)

    elif args.action == "extract":
        if not args.url:
            parser.error("--url is required for extract action")
        result = extract_page(args.url)

    elif args.action == "find_feeds":
        if not args.url:
            parser.error("--url is required for find_feeds action")
        result = find_feeds(args.url)

    elif args.action == "parse_feed":
        if not args.url:
            parser.error("--url is required for parse_feed action")
        result = parse_feed(args.url, max_entries=args.max_entries)

    duration_ms = (time.time() - start) * 1000

    log_tool_invocation(
        session_id=session_id,
        tool_name="web_researcher",
        params={"action": args.action, "query": args.query, "url": args.url},
        result={
            "status": "error"
            if "error" in (result if isinstance(result, dict) else {})
            else "success"
        },
        duration_ms=duration_ms,
    )

    output_str = json.dumps(result, indent=2, default=str, ensure_ascii=False)
    if args.output:
        Path(args.output).parent.mkdir(parents=True, exist_ok=True)
        Path(args.output).write_text(output_str, encoding="utf-8")
        print(f"Result written to {args.output}")
    else:
        print(output_str)


if __name__ == "__main__":
    main()
