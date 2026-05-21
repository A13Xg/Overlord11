from __future__ import annotations

from typing import Any, Literal
from urllib.parse import urljoin

from bs4 import BeautifulSoup
from pydantic import BaseModel, ConfigDict, Field, field_validator

from .base import BaseTool
from .web_common import domain_from_url, make_metadata, normalize_url
from .web_fetch import WebFetchTool, WebFetchArgs


class WebExtractImagesArgs(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    url: str = Field(min_length=3)
    limit: int = Field(default=20, ge=1, le=200)
    include_alt_text: bool = True
    min_width: int | None = Field(default=None, ge=1)
    min_height: int | None = Field(default=None, ge=1)
    image_type: Literal["auto", "hero", "thumbnail", "logo", "icon", "all"] = "auto"

    @field_validator("url")
    @classmethod
    def validate_url(cls, value: str) -> str:
        return normalize_url(value)


class WebExtractImagesTool(BaseTool):
    name = "web_extract_images"
    description = "Extract image metadata from a webpage"
    risk_level = "low"
    destructive = False
    supports_dry_run = False
    timeout_behavior = "Uses web_fetch timeouts"
    examples = [
        {"url": "https://example.com"},
        {"url": "https://example.com", "limit": 10, "image_type": "hero", "min_width": 200},
    ]
    input_model = WebExtractImagesArgs

    def execute(self, args: WebExtractImagesArgs) -> dict[str, Any]:
        warnings: list[str] = []
        fallbacks: list[str] = []

        fetch = WebFetchTool().execute(WebFetchArgs(url=args.url))
        html = str(fetch.get("body") or "")
        warnings.extend(fetch.get("_warnings", []))
        fallbacks.extend(fetch.get("_metadata", {}).get("fallbacks_used", []))

        soup = BeautifulSoup(html, "html.parser")
        seen: set[str] = set()
        images: list[dict[str, Any]] = []

        for img in soup.find_all("img"):
            src = (img.get("src") or "").strip()
            if not src:
                continue
            abs_url = urljoin(args.url, src)
            try:
                norm = normalize_url(abs_url)
            except ValueError:
                continue
            if norm in seen:
                continue
            seen.add(norm)

            width = _as_int(img.get("width"))
            height = _as_int(img.get("height"))
            if args.min_width and (width is None or width < args.min_width):
                continue
            if args.min_height and (height is None or height < args.min_height):
                continue

            inferred_type = self._infer_type(norm, img)
            if args.image_type not in {"auto", "all"} and inferred_type != args.image_type:
                continue

            rec = {
                "url": norm,
                "domain": domain_from_url(norm),
                "width": width,
                "height": height,
                "image_type": inferred_type,
                "alt_text": (img.get("alt") or "").strip() if args.include_alt_text else "",
            }
            images.append(rec)
            if len(images) >= args.limit:
                break

        return {
            "url": args.url,
            "images": images,
            "count": len(images),
            "_warnings": warnings,
            "_metadata": make_metadata(
                partial_success=bool(warnings),
                fallbacks_used=fallbacks,
                inferred_values={},
            ),
        }

    def _infer_type(self, url: str, tag) -> str:
        raw = f"{url} {(tag.get('class') or [])} {(tag.get('id') or '')} {(tag.get('alt') or '')}".lower()
        if "logo" in raw or "icon" in raw or "favicon" in raw:
            return "logo"
        if "thumb" in raw or "thumbnail" in raw:
            return "thumbnail"
        if "hero" in raw or "banner" in raw:
            return "hero"
        return "image"


def _as_int(value: Any) -> int | None:
    try:
        if value is None:
            return None
        return int(str(value).strip())
    except (TypeError, ValueError):
        return None
