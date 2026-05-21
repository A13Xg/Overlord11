from __future__ import annotations

import hashlib
import os
import re
from pathlib import Path
from typing import Any
from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse

import requests

_ALLOWED_SCHEMES = {"http", "https"}
_DEFAULT_UA = "Overlord11-ToolGateway/1.0"


def workspace_root() -> Path:
    return Path(os.environ.get("OVERLORD11_TASK_DIR") or os.getcwd()).resolve()


def resolve_workspace_path(path_value: str | None, *, default_subdir: str = "") -> Path:
    base = workspace_root()
    rel = path_value.strip() if isinstance(path_value, str) else ""
    if not rel:
        candidate = base / default_subdir if default_subdir else base
    else:
        p = Path(rel)
        candidate = (base / p).resolve() if not p.is_absolute() else p.resolve()
    try:
        candidate.relative_to(base)
    except ValueError as exc:
        raise ValueError("path must resolve within workspace root") from exc
    return candidate


def normalize_url(url: str, *, require_https: bool = False) -> str:
    parsed = urlparse((url or "").strip())
    scheme = (parsed.scheme or "https").lower()
    if scheme not in _ALLOWED_SCHEMES:
        raise ValueError("url scheme must be http or https")
    if require_https and scheme != "https":
        raise ValueError("url must use https")
    if not parsed.netloc:
        raise ValueError("url must include host")
    netloc = parsed.netloc.lower()
    path = parsed.path or "/"
    query = urlencode(sorted(parse_qsl(parsed.query, keep_blank_values=False)))
    return urlunparse((scheme, netloc, path, "", query, ""))


def domain_from_url(url: str) -> str:
    host = (urlparse(url).hostname or "").lower()
    return host[4:] if host.startswith("www.") else host


def request_with_retries(
    *,
    method: str,
    url: str,
    timeout_seconds: int,
    follow_redirects: bool,
    headers: dict[str, str] | None = None,
    retries: int = 2,
) -> tuple[requests.Response | None, list[str], list[str]]:
    warnings: list[str] = []
    fallbacks: list[str] = []
    merged_headers = {"User-Agent": _DEFAULT_UA}
    if headers:
        merged_headers.update(headers)

    last_err: Exception | None = None
    for attempt in range(1, retries + 1):
        try:
            response = requests.request(
                method=method.upper(),
                url=url,
                timeout=timeout_seconds,
                allow_redirects=follow_redirects,
                headers=merged_headers,
            )
            return response, warnings, fallbacks
        except requests.RequestException as exc:
            last_err = exc
            if attempt < retries:
                fallbacks.append(f"retry_request_attempt_{attempt + 1}")
    if last_err is not None:
        warnings.append(f"request failed: {last_err}")
    return None, warnings, fallbacks


def make_metadata(
    *,
    partial_success: bool = False,
    fallbacks_used: list[str] | None = None,
    inferred_values: dict[str, Any] | None = None,
    extra: dict[str, Any] | None = None,
) -> dict[str, Any]:
    metadata: dict[str, Any] = {
        "workspace": str(workspace_root()),
        "partial_success": partial_success,
        "fallbacks_used": list(fallbacks_used or []),
        "inferred_values": dict(inferred_values or {}),
    }
    if extra:
        metadata.update(extra)
    return metadata


def slugify_filename(name: str, fallback: str = "image") -> str:
    clean = re.sub(r"[^a-zA-Z0-9._-]+", "-", (name or "").strip().lower()).strip("-.")
    return clean or fallback


def content_hash(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def trim_text(text: str, max_chars: int = 20000) -> str:
    t = (text or "").strip()
    return t[:max_chars]
