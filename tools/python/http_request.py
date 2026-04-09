"""
Overlord11 - HTTP Request Tool
================================
Full-featured HTTP client supporting GET, POST, PUT, PATCH, DELETE, HEAD, OPTIONS.
Handles JSON bodies, custom headers, authentication, query parameters, file uploads,
and response parsing.

Usage (CLI):
    python http_request.py --method GET --url https://api.example.com/items
    python http_request.py --method POST --url https://api.example.com/items --json_body '{"name": "Widget"}'
    python http_request.py --method PUT --url https://api.example.com/items/1 --headers '{"Authorization": "Bearer TOKEN"}'
"""

import argparse
import json
import sys
from typing import Any, Optional


try:
    import requests
    HAS_REQUESTS = True
except ImportError:
    HAS_REQUESTS = False

try:
    from urllib.request import urlopen, Request as _UReq
    from urllib.error import URLError, HTTPError as _HTTPError
    from urllib.parse import urlencode, urlparse, urlunparse, parse_qs, urljoin
    HAS_URLLIB = True
except ImportError:
    HAS_URLLIB = False


def http_request(
    method: str,
    url: str,
    headers: Optional[dict] = None,
    params: Optional[dict] = None,
    json_body: Optional[Any] = None,
    form_data: Optional[dict] = None,
    body: Optional[str] = None,
    timeout_seconds: int = 30,
    follow_redirects: bool = True,
    auth_bearer: Optional[str] = None,
    auth_basic: Optional[str] = None,
    return_format: str = "auto",
) -> dict:
    """
    Perform an HTTP request.

    Args:
        method:          HTTP method: GET, POST, PUT, PATCH, DELETE, HEAD, OPTIONS.
        url:             Full URL including protocol.
        headers:         Optional dict of HTTP headers.
        params:          Optional dict of query string parameters.
        json_body:       Request body as a JSON-serializable object (sets Content-Type: application/json).
        form_data:       Request body as form fields (sets Content-Type: application/x-www-form-urlencoded).
        body:            Raw request body string. Use when json_body and form_data are not suitable.
        timeout_seconds: Request timeout in seconds. Defaults to 30.
        follow_redirects: Follow HTTP redirects. Defaults to True.
        auth_bearer:     Bearer token for Authorization header (replaces manual header).
        auth_basic:      Basic auth as 'username:password' string.
        return_format:   How to parse the response body:
                         'auto' (detect from Content-Type), 'json', 'text', 'bytes_b64'.

    Returns:
        dict with keys:
            status       – "success" or "error"
            method       – HTTP method used
            url          – final URL (after redirects)
            status_code  – HTTP status code (int)
            ok           – True if status_code < 400
            headers      – dict of response headers
            body         – parsed response body
            content_type – Content-Type header value
            elapsed_ms   – request duration in milliseconds (if available)
            error        – error description (only on failure)
            hint         – corrective action suggestion (only on failure)
    """
    method = method.upper()
    valid_methods = {"GET", "POST", "PUT", "PATCH", "DELETE", "HEAD", "OPTIONS"}
    if method not in valid_methods:
        return {
            "status": "error",
            "method": method,
            "url": url,
            "error": f"Invalid HTTP method: '{method}'",
            "hint": f"Use one of: {', '.join(sorted(valid_methods))}",
        }

    if not url or not url.startswith(("http://", "https://")):
        return {
            "status": "error",
            "method": method,
            "url": url,
            "error": "URL must start with http:// or https://",
            "hint": "Include the full URL with protocol prefix.",
        }

    # Build headers
    request_headers = {}
    if auth_bearer:
        request_headers["Authorization"] = f"Bearer {auth_bearer}"
    if headers:
        request_headers.update(headers)

    # ── requests library path ──────────────────────────────────────────────
    if HAS_REQUESTS:
        try:
            send_kwargs: dict = {
                "headers": request_headers,
                "params": params,
                "timeout": max(1, int(timeout_seconds)),
                "allow_redirects": follow_redirects,
            }

            if auth_basic:
                parts = auth_basic.split(":", 1)
                if len(parts) == 2:
                    send_kwargs["auth"] = (parts[0], parts[1])

            if json_body is not None:
                send_kwargs["json"] = json_body
            elif form_data is not None:
                send_kwargs["data"] = form_data
            elif body is not None:
                send_kwargs["data"] = body.encode("utf-8")

            resp = requests.request(method, url, **send_kwargs)
            elapsed_ms = round(resp.elapsed.total_seconds() * 1000, 1) if hasattr(resp, "elapsed") and resp.elapsed else None

            return _build_success(
                method=method,
                final_url=resp.url,
                status_code=resp.status_code,
                resp_headers=dict(resp.headers),
                raw_body=resp.text,
                content_type=resp.headers.get("Content-Type", ""),
                return_format=return_format,
                elapsed_ms=elapsed_ms,
            )

        except requests.exceptions.Timeout:
            return _timeout_error(method, url, timeout_seconds)
        except requests.exceptions.ConnectionError as exc:
            return _conn_error(method, url, exc)
        except Exception as exc:
            return {
                "status": "error",
                "method": method,
                "url": url,
                "error": f"Request failed: {exc}",
                "hint": "Check URL, network connectivity, and request parameters.",
            }

    # ── urllib fallback ────────────────────────────────────────────────────
    if HAS_URLLIB:
        try:
            from urllib.parse import urlencode as _urlencode, urlparse as _urlparse, urlunparse as _urlunparse

            # Append query params
            if params:
                parsed = _urlparse(url)
                qs = _urlencode(params)
                url = _urlunparse(parsed._replace(query=qs))

            req_body = None
            if json_body is not None:
                req_body = json.dumps(json_body).encode("utf-8")
                request_headers.setdefault("Content-Type", "application/json")
            elif form_data is not None:
                req_body = _urlencode(form_data).encode("utf-8")
                request_headers.setdefault("Content-Type", "application/x-www-form-urlencoded")
            elif body is not None:
                req_body = body.encode("utf-8")

            if auth_basic:
                import base64 as _b64
                encoded = _b64.b64encode(auth_basic.encode()).decode()
                request_headers["Authorization"] = f"Basic {encoded}"

            req = _UReq(url, data=req_body, headers=request_headers, method=method)
            with urlopen(req, timeout=max(1, int(timeout_seconds))) as resp:
                raw_bytes = resp.read()
                status_code = resp.status
                resp_headers = dict(resp.headers)
                content_type = resp.headers.get("Content-Type", "")
                final_url = resp.url if hasattr(resp, "url") else url

            raw_body = raw_bytes.decode("utf-8", errors="replace")
            return _build_success(
                method=method,
                final_url=final_url,
                status_code=status_code,
                resp_headers=resp_headers,
                raw_body=raw_body,
                content_type=content_type,
                return_format=return_format,
                elapsed_ms=None,
            )

        except _HTTPError as exc:
            raw = exc.read().decode("utf-8", errors="replace") if exc.fp else ""
            return {
                "status": "error",
                "method": method,
                "url": url,
                "status_code": exc.code,
                "ok": False,
                "error": f"HTTP {exc.code}: {exc.reason}",
                "body": raw,
                "hint": "Check the URL path, authentication, and request body.",
            }
        except URLError as exc:
            return _conn_error(method, url, exc)
        except Exception as exc:
            return {
                "status": "error",
                "method": method,
                "url": url,
                "error": f"Request failed: {exc}",
                "hint": "Check URL, network connectivity, and request parameters.",
            }

    return {
        "status": "error",
        "method": method,
        "url": url,
        "error": "No HTTP library available. Install requests: pip install requests",
        "hint": "pip install requests",
    }


def _build_success(method, final_url, status_code, resp_headers, raw_body,
                   content_type, return_format, elapsed_ms):
    """Parse response body and build the success result dict."""
    body = _parse_body(raw_body, content_type, return_format)
    return {
        "status": "success",
        "method": method,
        "url": final_url,
        "status_code": status_code,
        "ok": status_code < 400,
        "headers": resp_headers,
        "content_type": content_type,
        "body": body,
        "elapsed_ms": elapsed_ms,
    }


def _parse_body(raw_body: str, content_type: str, return_format: str):
    if return_format == "json" or (return_format == "auto" and "application/json" in content_type):
        try:
            return json.loads(raw_body)
        except json.JSONDecodeError:
            return raw_body
    return raw_body


def _timeout_error(method, url, timeout_seconds):
    return {
        "status": "error",
        "method": method,
        "url": url,
        "error": f"Request timed out after {timeout_seconds}s",
        "hint": "Increase timeout_seconds or check server availability.",
    }


def _conn_error(method, url, exc):
    return {
        "status": "error",
        "method": method,
        "url": url,
        "error": f"Connection error: {exc}",
        "hint": "Check URL spelling and network connectivity.",
    }


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="Overlord11 HTTP Request Tool")
    parser.add_argument("--method", default="GET",
                        choices=["GET", "POST", "PUT", "PATCH", "DELETE", "HEAD", "OPTIONS"])
    parser.add_argument("--url", required=True, help="Full URL including protocol")
    parser.add_argument("--headers", default="{}", help="JSON dict of HTTP headers")
    parser.add_argument("--params", default="{}", help="JSON dict of query parameters")
    parser.add_argument("--json_body", default=None, help="JSON request body")
    parser.add_argument("--form_data", default=None, help="JSON dict for form-encoded body")
    parser.add_argument("--body", default=None, help="Raw string request body")
    parser.add_argument("--timeout_seconds", type=int, default=30)
    parser.add_argument("--follow_redirects", default="true", help="Follow HTTP redirects (true/false). Default: true.")
    parser.add_argument("--auth_bearer", default=None, help="Bearer token")
    parser.add_argument("--auth_basic", default=None, help="Basic auth as user:password")
    parser.add_argument("--return_format", default="auto", choices=["auto", "json", "text"])

    args = parser.parse_args()

    def _parse_json_arg(s, name):
        try:
            return json.loads(s) if s else None
        except json.JSONDecodeError as exc:
            print(json.dumps({"status": "error", "error": f"Invalid JSON for {name}: {exc}"}), flush=True)
            sys.exit(1)

    result = http_request(
        method=args.method,
        url=args.url,
        headers=_parse_json_arg(args.headers, "--headers"),
        params=_parse_json_arg(args.params, "--params"),
        json_body=_parse_json_arg(args.json_body, "--json_body"),
        form_data=_parse_json_arg(args.form_data, "--form_data"),
        body=args.body,
        timeout_seconds=args.timeout_seconds,
        follow_redirects=args.follow_redirects.lower() != "false",
        auth_bearer=args.auth_bearer,
        auth_basic=args.auth_basic,
        return_format=args.return_format,
    )
    print(json.dumps(result, indent=2, ensure_ascii=False, default=str))
    sys.exit(0 if result.get("status") == "success" else 1)


if __name__ == "__main__":
    main()
