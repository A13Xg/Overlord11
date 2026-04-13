"""
Overlord11 - Web Fetch Tool
============================
Perform an HTTP GET request to a URL. Supports custom headers, configurable
timeout, and optional response body conversion (text, JSON, Markdown).

Usage (CLI):
    python web_fetch.py --url https://example.com
    python web_fetch.py --url https://api.example.com/data --return_format json
    python web_fetch.py --url https://example.com --headers '{"Accept": "text/html"}' --return_format markdown
"""

import argparse
import json
import re
import sys
from typing import Optional


try:
    import requests
    HAS_REQUESTS = True
except ImportError:
    HAS_REQUESTS = False

try:
    from urllib.request import urlopen, Request as _UrllibRequest
    from urllib.error import URLError, HTTPError as _HTTPError
    HAS_URLLIB = True
except ImportError:
    HAS_URLLIB = False


# ---------------------------------------------------------------------------
# HTML → Markdown converter (no third-party deps required)
# ---------------------------------------------------------------------------

def _html_to_markdown(html: str) -> str:
    """Convert basic HTML to Markdown. Best-effort; handles common tags."""
    text = html

    # Remove <script> and <style> blocks
    text = re.sub(r"<script[^>]*>.*?</script>", "", text, flags=re.DOTALL | re.IGNORECASE)
    text = re.sub(r"<style[^>]*>.*?</style>", "", text, flags=re.DOTALL | re.IGNORECASE)

    # Headings
    for i in range(6, 0, -1):
        text = re.sub(rf"<h{i}[^>]*>(.*?)</h{i}>",
                      lambda m, level=i: "\n" + "#" * level + " " + m.group(1).strip() + "\n",
                      text, flags=re.DOTALL | re.IGNORECASE)

    # Bold / italic
    text = re.sub(r"<(strong|b)[^>]*>(.*?)</\1>", r"**\2**", text, flags=re.DOTALL | re.IGNORECASE)
    text = re.sub(r"<(em|i)[^>]*>(.*?)</\1>", r"_\2_", text, flags=re.DOTALL | re.IGNORECASE)

    # Links
    text = re.sub(r'<a[^>]+href=["\']([^"\']+)["\'][^>]*>(.*?)</a>',
                  r"[\2](\1)", text, flags=re.DOTALL | re.IGNORECASE)

    # Images
    text = re.sub(r'<img[^>]+alt=["\']([^"\']*)["\'][^>]*src=["\']([^"\']+)["\'][^>]*/?>',
                  r"![\1](\2)", text, flags=re.IGNORECASE)
    text = re.sub(r'<img[^>]+src=["\']([^"\']+)["\'][^>]*/?>',
                  r"![](\1)", text, flags=re.IGNORECASE)

    # Lists
    text = re.sub(r"<li[^>]*>(.*?)</li>", r"\n- \1", text, flags=re.DOTALL | re.IGNORECASE)
    text = re.sub(r"<[uo]l[^>]*>", "\n", text, flags=re.IGNORECASE)
    text = re.sub(r"</[uo]l>", "\n", text, flags=re.IGNORECASE)

    # Block elements
    text = re.sub(r"<br\s*/?>", "\n", text, flags=re.IGNORECASE)
    text = re.sub(r"<p[^>]*>", "\n", text, flags=re.IGNORECASE)
    text = re.sub(r"</p>", "\n", text, flags=re.IGNORECASE)
    text = re.sub(r"<div[^>]*>", "\n", text, flags=re.IGNORECASE)
    text = re.sub(r"</div>", "\n", text, flags=re.IGNORECASE)
    text = re.sub(r"<hr\s*/?>", "\n---\n", text, flags=re.IGNORECASE)

    # Code
    text = re.sub(r"<code[^>]*>(.*?)</code>", r"`\1`", text, flags=re.DOTALL | re.IGNORECASE)
    text = re.sub(r"<pre[^>]*>(.*?)</pre>",
                  lambda m: "\n```\n" + m.group(1).strip() + "\n```\n",
                  text, flags=re.DOTALL | re.IGNORECASE)

    # Strip remaining tags
    text = re.sub(r"<[^>]+>", "", text)

    # Decode HTML entities
    text = text.replace("&amp;", "&").replace("&lt;", "<").replace("&gt;", ">")
    text = text.replace("&quot;", '"').replace("&#39;", "'").replace("&nbsp;", " ")

    # Collapse excessive blank lines
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


# ---------------------------------------------------------------------------
# Core function
# ---------------------------------------------------------------------------

def web_fetch(
    url: str,
    headers: Optional[dict] = None,
    timeout_seconds: int = 30,
    return_format: str = "text",
) -> dict:
    """
    Perform an HTTP GET request to a URL and return the response.

    Args:
        url:            The full URL to fetch (including protocol).
        headers:        Optional HTTP headers (e.g., Authorization, Accept).
        timeout_seconds: Request timeout in seconds. Defaults to 30.
        return_format:  How to return the body: 'text' (raw), 'json' (parsed),
                        or 'markdown' (HTML converted to Markdown).

    Returns:
        dict with keys:
            status      – "success" or "error"
            url         – the requested URL
            status_code – HTTP status code (int)
            headers     – dict of response headers
            body        – response body (str, dict/list if json, or markdown str)
            content_type – Content-Type header value
            error       – human-readable error message (only when status is "error")
            hint        – suggested corrective action (only when status is "error")
    """
    if not url:
        return {
            "status": "error",
            "url": url,
            "error": "url is required",
            "hint": "Provide a full URL including protocol, e.g., https://example.com",
        }

    if not url.startswith(("http://", "https://")):
        return {
            "status": "error",
            "url": url,
            "error": f"Invalid URL scheme: '{url}'. Must start with http:// or https://",
            "hint": "Add https:// or http:// prefix to the URL.",
        }

    request_headers = dict(headers or {})

    # ── Try requests library first ─────────────────────────────────────────
    if HAS_REQUESTS:
        try:
            resp = requests.get(
                url,
                headers=request_headers,
                timeout=max(1, int(timeout_seconds)),
                allow_redirects=True,
            )
            resp_headers = dict(resp.headers)
            content_type = resp.headers.get("Content-Type", "")
            raw_body = resp.text

            body = _format_body(raw_body, return_format, content_type, url)
            if isinstance(body, dict) and body.get("status") == "error":
                return body

            return {
                "status": "success",
                "url": url,
                "status_code": resp.status_code,
                "headers": resp_headers,
                "content_type": content_type,
                "body": body,
            }
        except requests.exceptions.Timeout:
            return {
                "status": "error",
                "url": url,
                "error": f"Request timed out after {timeout_seconds} seconds",
                "hint": "Increase timeout_seconds or check that the server is reachable.",
            }
        except requests.exceptions.ConnectionError as exc:
            return {
                "status": "error",
                "url": url,
                "error": f"Connection error: {exc}",
                "hint": "Check the URL and network connectivity.",
            }
        except requests.exceptions.HTTPError as exc:
            return {
                "status": "error",
                "url": url,
                "error": f"HTTP error: {exc}",
                "hint": "Check the URL path and authentication headers.",
            }
        except Exception as exc:
            return {
                "status": "error",
                "url": url,
                "error": f"Unexpected error: {exc}",
                "hint": "Check the URL format and network configuration.",
            }

    # ── Fallback: urllib (stdlib) ──────────────────────────────────────────
    if HAS_URLLIB:
        try:
            req = _UrllibRequest(url, headers=request_headers)
            with urlopen(req, timeout=max(1, int(timeout_seconds))) as resp:
                raw_bytes = resp.read()
                status_code = resp.status
                resp_headers = dict(resp.headers)
                content_type = resp.headers.get("Content-Type", "")

            raw_body = raw_bytes.decode("utf-8", errors="replace")
            body = _format_body(raw_body, return_format, content_type, url)
            if isinstance(body, dict) and body.get("status") == "error":
                return body

            return {
                "status": "success",
                "url": url,
                "status_code": status_code,
                "headers": resp_headers,
                "content_type": content_type,
                "body": body,
            }
        except _HTTPError as exc:
            return {
                "status": "error",
                "url": url,
                "status_code": exc.code,
                "error": f"HTTP {exc.code}: {exc.reason}",
                "hint": "Check the URL path and authentication headers.",
            }
        except URLError as exc:
            return {
                "status": "error",
                "url": url,
                "error": f"URL error: {exc.reason}",
                "hint": "Check the URL and network connectivity.",
            }
        except Exception as exc:
            return {
                "status": "error",
                "url": url,
                "error": f"Unexpected error: {exc}",
                "hint": "Check the URL format and network configuration.",
            }

    return {
        "status": "error",
        "url": url,
        "error": "No HTTP library available. Neither 'requests' nor 'urllib' found.",
        "hint": "Install requests: pip install requests",
    }


def _format_body(raw_body: str, return_format: str, content_type: str, url: str):
    """Parse/convert the response body according to return_format."""
    if return_format == "json":
        try:
            return json.loads(raw_body)
        except json.JSONDecodeError as exc:
            return {
                "status": "error",
                "url": url,
                "error": f"Response is not valid JSON: {exc}",
                "hint": "Use return_format='text' to see the raw response body.",
            }
    elif return_format == "markdown":
        if "text/html" in content_type or raw_body.lstrip().startswith("<"):
            return _html_to_markdown(raw_body)
        return raw_body  # Already text; return as-is
    else:
        return raw_body


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="Overlord11 Web Fetch Tool")
    parser.add_argument("--url", required=True, help="URL to fetch")
    parser.add_argument("--headers", default="{}", help="JSON object of HTTP headers")
    parser.add_argument("--timeout_seconds", type=int, default=30, help="Request timeout (seconds)")
    parser.add_argument("--return_format", default="text",
                        choices=["text", "json", "markdown"],
                        help="Response body format: text, json, or markdown")
    args = parser.parse_args()

    try:
        headers = json.loads(args.headers)
    except json.JSONDecodeError as exc:
        print(json.dumps({
            "status": "error",
            "error": f"Invalid --headers JSON: {exc}",
            "hint": "Pass headers as a JSON object, e.g., '{\"Accept\": \"application/json\"}'",
        }, indent=2))
        sys.exit(1)

    result = web_fetch(
        url=args.url,
        headers=headers,
        timeout_seconds=args.timeout_seconds,
        return_format=args.return_format,
    )
    print(json.dumps(result, indent=2, ensure_ascii=False, default=str))
    sys.exit(0 if result.get("status") == "success" else 1)


if __name__ == "__main__":
    main()
