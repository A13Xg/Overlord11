"""
Image Scraper tool — scrapes images from a URL with real metadata via HEAD requests.
More thorough than web_extract_images: includes file size, MIME type, response headers.
"""
from __future__ import annotations

from typing import Any
from urllib.parse import urljoin, urlparse

import requests
from bs4 import BeautifulSoup
from pydantic import BaseModel, ConfigDict, Field

from .base import BaseTool
from .web_common import (
    normalize_url,
    request_with_retries,
    resolve_workspace_path,
    workspace_root,
    slugify_filename,
)
from .web_fetch import WebFetchTool, WebFetchArgs


class ImageScraperInput(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=False)

    url: str = Field(..., min_length=3, description="Web page URL to scrape images from")
    limit: int = Field(20, ge=1, le=200, description="Maximum number of images to return")
    download: bool = Field(False, description="Download images to output_directory")
    output_directory: str | None = Field(None, description="Workspace-relative path to save images (used when download=True)")
    min_size_kb: int | None = Field(None, ge=1, description="Filter out images smaller than this size in KB (requires a HEAD request)")
    require_https: bool = Field(False, description="Only include images served over HTTPS")
    timeout_seconds: float = Field(10.0, ge=1.0, le=60.0)


class ImageScraperTool(BaseTool):
    name = "image_scraper"
    description = (
        "Scrape images from a web page with rich metadata: dimensions (from HTML attributes), "
        "file size, MIME type, and alt text. Optionally download images to workspace. "
        "Uses HEAD requests to resolve real file size and content-type per image."
    )
    risk_level = "low"
    destructive = False
    supports_dry_run = False
    input_model = ImageScraperInput
    examples = [
        {"tool_name": "image_scraper", "arguments": {"url": "https://example.com", "limit": 20}},
        {"tool_name": "image_scraper", "arguments": {"url": "https://example.com", "download": True, "output_directory": "artifacts/images", "min_size_kb": 5}},
    ]

    def execute(self, args: ImageScraperInput) -> dict[str, Any]:
        warnings: list[str] = []
        url = normalize_url(args.url)

        # Fetch page HTML
        fetch_result = WebFetchTool().execute(WebFetchArgs(url=url, timeout_seconds=int(args.timeout_seconds)))
        html = str(fetch_result.get("body") or "")
        if not html:
            return {"url": url, "images": [], "count": 0, "_warnings": ["Page returned empty body"]}

        soup = BeautifulSoup(html, "html.parser")
        img_tags = soup.find_all("img")

        # Collect candidate srcs
        candidates: list[dict[str, Any]] = []
        seen: set[str] = set()
        for img in img_tags:
            src = (img.get("src") or img.get("data-src") or "").strip()
            if not src:
                continue
            abs_url = urljoin(url, src)
            try:
                norm = normalize_url(abs_url)
            except ValueError:
                continue
            if norm in seen:
                continue
            seen.add(norm)
            if args.require_https and not norm.startswith("https://"):
                continue
            candidates.append({
                "src": norm,
                "alt": (img.get("alt") or "").strip(),
                "width": _as_int(img.get("width")),
                "height": _as_int(img.get("height")),
            })

        # HEAD each image to get real metadata
        images: list[dict[str, Any]] = []
        for cand in candidates:
            if len(images) >= args.limit:
                break
            meta = self._head_image(cand["src"], args.timeout_seconds, warnings)
            size_kb = meta.get("size_kb")
            if args.min_size_kb and size_kb is not None and size_kb < args.min_size_kb:
                continue
            record: dict[str, Any] = {
                "src": cand["src"],
                "alt": cand["alt"],
                "width": cand["width"],
                "height": cand["height"],
                "mime_type": meta.get("mime_type"),
                "size_kb": size_kb,
                "status_code": meta.get("status_code"),
            }
            images.append(record)

        # Optionally download
        downloaded: list[str] = []
        if args.download and images:
            out_dir = resolve_workspace_path(args.output_directory or "artifacts/images")
            out_dir.mkdir(parents=True, exist_ok=True)
            for rec in images:
                dl_path = self._download_image(rec["src"], out_dir, args.timeout_seconds, warnings)
                if dl_path:
                    rec["local_path"] = dl_path
                    downloaded.append(dl_path)

        return {
            "url": url,
            "images": images,
            "count": len(images),
            "downloaded": len(downloaded),
            "_warnings": warnings,
        }

    # ------------------------------------------------------------------

    def _head_image(self, src: str, timeout: float, warnings: list[str]) -> dict[str, Any]:
        try:
            resp = requests.head(
                src,
                timeout=timeout,
                allow_redirects=True,
                headers={"User-Agent": "Overlord11-ToolGateway/1.0"},
            )
            ct = resp.headers.get("Content-Type", "")
            cl = resp.headers.get("Content-Length")
            size_kb = round(int(cl) / 1024, 2) if cl and cl.isdigit() else None
            return {
                "status_code": resp.status_code,
                "mime_type": ct.split(";")[0].strip() if ct else None,
                "size_kb": size_kb,
            }
        except Exception as exc:
            warnings.append(f"HEAD {src}: {exc}")
            return {}

    def _download_image(self, src: str, out_dir, timeout: float, warnings: list[str]) -> str | None:
        try:
            resp = requests.get(
                src,
                timeout=timeout,
                stream=True,
                headers={"User-Agent": "Overlord11-ToolGateway/1.0"},
            )
            resp.raise_for_status()
            # Determine filename
            from urllib.parse import urlparse
            fname = slugify_filename(urlparse(src).path.split("/")[-1] or "image")
            if not fname or fname == "image":
                fname = slugify_filename(src[-40:]) + ".bin"
            dest = out_dir / fname
            dest.write_bytes(resp.content)
            return str(dest.relative_to(workspace_root()))
        except Exception as exc:
            warnings.append(f"Download {src}: {exc}")
            return None


def _as_int(value: Any) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None
