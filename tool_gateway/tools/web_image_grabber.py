from __future__ import annotations

from pathlib import Path
from typing import Any, Literal
from urllib.parse import urlparse

from pydantic import BaseModel, ConfigDict, Field, model_validator

from .base import BaseTool
from .web_common import content_hash, is_blacklisted, make_metadata, normalize_url, request_with_retries, resolve_workspace_path, slugify_filename
from .web_extract_images import WebExtractImagesTool, WebExtractImagesArgs
from .web_search import WebSearchTool, WebSearchArgs


class WebImageGrabberArgs(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    source_mode: Literal["search_query", "page_urls", "direct_urls"] = "search_query"
    query: str | None = None
    urls: list[str] = Field(default_factory=list)
    output_directory: str | None = None
    max_images: int = Field(default=10, ge=1, le=200)
    matching_mode: Literal["visual_guess", "strict"] = "visual_guess"
    allowed_extensions: list[str] = Field(default_factory=lambda: ["jpg", "jpeg", "png", "webp", "gif"])
    require_https: bool = True
    deduplicate: bool = True
    overwrite_existing: bool = False
    create_manifest: bool = True
    dry_run: bool = False

    @model_validator(mode="after")
    def require_input(self) -> "WebImageGrabberArgs":
        if not self.query and not self.urls:
            raise ValueError("at least one of query or urls is required")
        self.allowed_extensions = sorted({e.lower().lstrip(".") for e in self.allowed_extensions if e})
        return self


class WebImageGrabberTool(BaseTool):
    name = "web_image_grabber"
    description = "Search/extract/download images into workspace with dedupe and manifest"
    risk_level = "medium"
    destructive = True
    supports_dry_run = True
    timeout_behavior = "Per-image request timeout with partial success"
    examples = [
        {"query": "mountain landscape", "max_images": 5},
        {"source_mode": "direct_urls", "urls": ["https://example.com/a.png"], "dry_run": True},
    ]
    input_model = WebImageGrabberArgs

    def execute(self, args: WebImageGrabberArgs) -> dict[str, Any]:
        warnings: list[str] = []
        fallbacks: list[str] = []

        output_dir = resolve_workspace_path(args.output_directory, default_subdir="artifacts/images")
        output_dir.mkdir(parents=True, exist_ok=True)

        candidate_urls: list[str] = []
        if args.query and args.source_mode == "search_query":
            search = WebSearchTool().execute(WebSearchArgs(query=args.query, max_results=max(args.max_images * 2, 10), result_type="images"))
            warnings.extend(search.get("_warnings", []))
            for x in search.get("results", []):
                if not isinstance(x, dict):
                    continue
                # Prefer the direct image URL (image_url) over the page URL (url)
                img_url = x.get("image_url") or x.get("url", "")
                if img_url:
                    candidate_urls.append(img_url)
        if args.urls:
            candidate_urls.extend(args.urls)
        if args.source_mode == "page_urls":
            for page_url in args.urls:
                try:
                    extracted = WebExtractImagesTool().execute(WebExtractImagesArgs(url=page_url, limit=max(args.max_images * 2, 20)))
                    candidate_urls.extend([x.get("url", "") for x in extracted.get("images", []) if isinstance(x, dict)])
                except Exception as exc:
                    warnings.append(f"page image extraction failed for {page_url}: {exc}")

        normalized_urls: list[str] = []
        for raw in candidate_urls:
            if not raw:
                continue
            try:
                normed = normalize_url(str(raw), require_https=args.require_https)
            except ValueError:
                warnings.append(f"skipped invalid image url: {raw}")
                continue
            if is_blacklisted(normed, tool_name="web_image_grabber"):
                warnings.append(f"skipped blacklisted url: {normed}")
                continue
            normalized_urls.append(normed)

        if args.deduplicate:
            normalized_urls = sorted(dict.fromkeys(normalized_urls))

        saved_images: list[dict[str, Any]] = []
        rejected_images: list[dict[str, Any]] = []
        seen_hashes: set[str] = set()

        for img_url in normalized_urls:
            if len(saved_images) >= args.max_images:
                break
            ext = _infer_extension(img_url)
            if ext not in args.allowed_extensions:
                rejected_images.append({"url": img_url, "reason": "extension_not_allowed"})
                continue

            if args.dry_run:
                saved_images.append({"url": img_url, "path": "", "size_bytes": 0, "hash": "", "dry_run": True})
                continue

            response, rw, rf = request_with_retries(
                method="GET",
                url=img_url,
                timeout_seconds=20,
                follow_redirects=True,
                retries=2,
            )
            warnings.extend(rw)
            fallbacks.extend(rf)
            if response is None:
                rejected_images.append({"url": img_url, "reason": "download_failed"})
                continue

            content_type = (response.headers.get("Content-Type") or "").lower()
            if not content_type.startswith("image/"):
                rejected_images.append({"url": img_url, "reason": "non_image_mime"})
                continue

            content = response.content or b""
            if not content:
                rejected_images.append({"url": img_url, "reason": "empty_content"})
                continue
            if len(content) > 25 * 1024 * 1024:
                rejected_images.append({"url": img_url, "reason": "file_too_large"})
                continue

            digest = content_hash(content)
            if args.deduplicate and digest in seen_hashes:
                rejected_images.append({"url": img_url, "reason": "duplicate_hash"})
                continue
            seen_hashes.add(digest)

            stem = slugify_filename(Path(urlparse(img_url).path).stem or "image")
            target = output_dir / f"{stem}.{ext}"
            idx = 1
            while target.exists() and not args.overwrite_existing:
                idx += 1
                target = output_dir / f"{stem}_{idx}.{ext}"
            if target.exists() and not args.overwrite_existing:
                rejected_images.append({"url": img_url, "reason": "file_exists"})
                continue

            target.write_bytes(content)
            saved_images.append({
                "url": img_url,
                "path": str(target),
                "size_bytes": len(content),
                "hash": digest,
                "dry_run": False,
            })

        manifest_path = ""
        if args.create_manifest:
            import json

            manifest = {
                "saved_images": saved_images,
                "rejected_images": rejected_images,
                "saved_count": len(saved_images),
                "rejected_count": len(rejected_images),
            }
            manifest_file = output_dir / "manifest.json"
            manifest_file.write_text(json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8")
            manifest_path = str(manifest_file)

        return {
            "saved_images": saved_images,
            "rejected_images": rejected_images,
            "manifest_path": manifest_path,
            "saved_count": len(saved_images),
            "rejected_count": len(rejected_images),
            "output_directory": str(output_dir),
            "_warnings": sorted(dict.fromkeys(warnings)),
            "_metadata": make_metadata(
                partial_success=bool(rejected_images or warnings),
                fallbacks_used=sorted(dict.fromkeys(fallbacks)),
                inferred_values={},
            ),
        }


def _infer_extension(url: str) -> str:
    suffix = Path(urlparse(url).path).suffix.lower().lstrip(".")
    return suffix or "jpg"
