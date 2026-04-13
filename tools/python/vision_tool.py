"""
Overlord11 - Vision Tool
=========================
Provides screenshot capture and image analysis capabilities.

Actions:
  screenshot     - Capture a screenshot of the entire screen or a region.
  analyze_image  - Describe / analyze a local image file using an LLM-ready
                   base64 payload or EXIF / pixel metadata extraction.
  ocr            - Extract text from an image file using pytesseract (if
                   installed) with a pure-Python fallback that returns the
                   base64 payload for LLM OCR.
  list_images    - List image files in a directory.
  compare_images - Compare two images and return a similarity score and diff.

Hard dependencies (graceful degradation if missing):
  - Pillow (PIL)       — screenshot, image metadata, compare
  - pytesseract        — OCR text extraction
  - pyautogui / mss    — cross-platform screenshot capture

Usage (CLI):
    python vision_tool.py --action screenshot --output /tmp/screen.png
    python vision_tool.py --action screenshot --region 0,0,1280,720 --output /tmp/region.png
    python vision_tool.py --action analyze_image --image /path/to/image.png
    python vision_tool.py --action ocr --image /path/to/image.png
    python vision_tool.py --action list_images --directory /tmp
    python vision_tool.py --action compare_images --image /a.png --image2 /b.png
"""

import argparse
import base64
import json
import os
import sys
import time
from datetime import datetime
from pathlib import Path

# ---------------------------------------------------------------------------
# Project-root path resolution and optional log import
# ---------------------------------------------------------------------------
SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = SCRIPT_DIR.parent.parent

try:
    sys.path.insert(0, str(SCRIPT_DIR))
    from log_manager import log_tool_invocation, log_error
    from task_workspace import ensure_env_task_layout
    HAS_LOG = True
except ImportError:
    HAS_LOG = False
    def log_tool_invocation(*a, **kw): pass
    def log_error(*a, **kw): pass
    def ensure_env_task_layout(*a, **kw): return None

# ---------------------------------------------------------------------------
# Optional dependency probes
# ---------------------------------------------------------------------------
try:
    from PIL import Image, ImageChops, ImageStat
    import io as _io
    HAS_PIL = True
except ImportError:
    HAS_PIL = False

try:
    import pytesseract
    HAS_TESSERACT = True
except ImportError:
    HAS_TESSERACT = False

try:
    import mss
    import mss.tools
    HAS_MSS = True
except ImportError:
    HAS_MSS = False

try:
    import pyautogui as _pag
    HAS_PYAUTOGUI = True
except ImportError:
    HAS_PYAUTOGUI = False

# Supported image extensions
IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".gif", ".bmp", ".webp", ".tiff", ".tif"}


# ---------------------------------------------------------------------------
# Helper: encode image as base64 string
# ---------------------------------------------------------------------------

def _image_to_b64(path: Path) -> str:
    """Read an image file and return its base64-encoded representation."""
    raw = path.read_bytes()
    return base64.b64encode(raw).decode("ascii")


def _image_metadata(path: Path) -> dict:
    """Extract image metadata using Pillow if available."""
    if not HAS_PIL:
        return {"error": "Pillow not installed — pip install Pillow"}
    try:
        with Image.open(str(path)) as img:
            return {
                "format": img.format,
                "mode": img.mode,
                "width": img.width,
                "height": img.height,
                "size_bytes": path.stat().st_size,
            }
    except Exception as exc:
        return {"error": str(exc)}


# ---------------------------------------------------------------------------
# Actions
# ---------------------------------------------------------------------------

def screenshot(
    output: str = None,
    region: str = None,
    format: str = "png",
) -> dict:
    """Capture a screenshot of the entire screen or a specific region.

    Args:
        output: File path to save the screenshot.  Auto-generated if None.
        region: Comma-separated "left,top,width,height" for a sub-region.
        format: Image format ('png' or 'jpeg').

    Returns:
        dict with status, file path, dimensions, and base64 payload.
    """
    if not HAS_PIL:
        return {
            "status": "error",
            "error": "Pillow not installed. Run: pip install Pillow",
        }

    # Determine output path
    if output is None:
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        layout = ensure_env_task_layout()
        if layout:
            output = str(layout["tools_vision"] / f"screenshot_{ts}.{format}")
        else:
            output = str(PROJECT_ROOT / "workspace" / f"screenshot_{ts}.{format}")

    output_path = Path(output)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    # Parse optional region
    parsed_region = None
    if region:
        try:
            parts = [int(x.strip()) for x in region.split(",")]
            if len(parts) == 4:
                parsed_region = {"left": parts[0], "top": parts[1],
                                 "width": parts[2], "height": parts[3]}
        except ValueError:
            return {"status": "error", "error": f"Invalid region format: '{region}'. Use 'left,top,width,height'"}

    # Attempt capture via mss (cross-platform, no display server required for headless-ish)
    if HAS_MSS:
        try:
            with mss.mss() as sct:
                monitor = parsed_region or sct.monitors[0]
                sct_img = sct.grab(monitor)
                img = Image.frombytes("RGB", sct_img.size, sct_img.bgra, "raw", "BGRX")
                img.save(str(output_path), format=format.upper())
        except Exception as exc:
            return {"status": "error", "error": f"mss capture failed: {exc}"}
    elif HAS_PYAUTOGUI:
        try:
            if parsed_region:
                img = _pag.screenshot(region=(
                    parsed_region["left"], parsed_region["top"],
                    parsed_region["width"], parsed_region["height"]
                ))
            else:
                img = _pag.screenshot()
            img.save(str(output_path))
        except Exception as exc:
            return {"status": "error", "error": f"pyautogui capture failed: {exc}"}
    else:
        return {
            "status": "error",
            "error": (
                "No screenshot backend available. "
                "Install 'mss' or 'pyautogui': pip install mss pyautogui"
            ),
        }

    # Build response
    meta = _image_metadata(output_path)
    b64 = _image_to_b64(output_path)

    return {
        "status": "ok",
        "file": str(output_path),
        "format": format,
        "width": meta.get("width"),
        "height": meta.get("height"),
        "size_bytes": meta.get("size_bytes"),
        "base64": b64[:200] + "...[truncated]" if len(b64) > 200 else b64,
        "base64_full_available": True,
        "llm_note": (
            "Pass the 'file' path to analyze_image or ocr for further processing. "
            "Full base64 payload can be sent directly to a vision-capable LLM."
        ),
    }


def analyze_image(image_path: str, include_b64: bool = True) -> dict:
    """Return metadata and an LLM-ready base64 payload for an image file.

    Args:
        image_path: Path to the image file.
        include_b64: Whether to include the full base64 in the response.

    Returns:
        dict with metadata, MIME type, and optionally the base64 payload.
    """
    path = Path(image_path)
    if not path.exists():
        return {"status": "error", "error": f"Image not found: {image_path}"}
    if path.suffix.lower() not in IMAGE_EXTENSIONS:
        return {"status": "error", "error": f"Unsupported image format: {path.suffix}"}

    meta = _image_metadata(path)
    suffix = path.suffix.lower().lstrip(".")
    mime_map = {
        "jpg": "image/jpeg", "jpeg": "image/jpeg", "png": "image/png",
        "gif": "image/gif", "bmp": "image/bmp", "webp": "image/webp",
        "tiff": "image/tiff", "tif": "image/tiff",
    }
    mime = mime_map.get(suffix, "application/octet-stream")

    result = {
        "status": "ok",
        "file": str(path),
        "mime_type": mime,
        **meta,
        "llm_prompt": (
            "The following image has been encoded as base64. Analyze its content and "
            "describe what you see in detail, including any text, objects, charts, or notable features."
        ),
    }

    if include_b64:
        b64 = _image_to_b64(path)
        result["base64"] = b64
        result["base64_length"] = len(b64)

    return result


def ocr(image_path: str) -> dict:
    """Extract text from an image using pytesseract or return base64 for LLM OCR.

    Args:
        image_path: Path to the image file.

    Returns:
        dict with extracted text (or base64 fallback if tesseract unavailable).
    """
    path = Path(image_path)
    if not path.exists():
        return {"status": "error", "error": f"Image not found: {image_path}"}

    if HAS_TESSERACT and HAS_PIL:
        try:
            with Image.open(str(path)) as img:
                text = pytesseract.image_to_string(img)
            return {
                "status": "ok",
                "file": str(path),
                "method": "pytesseract",
                "text": text.strip(),
                "char_count": len(text.strip()),
            }
        except Exception as exc:
            # Tesseract failed — log and fall through to base64 fallback
            tesseract_error = str(exc)
            if HAS_LOG:
                log_error("system", "vision_tool.ocr", tesseract_error)
        else:
            tesseract_error = None
    else:
        tesseract_error = None

    # Fallback: return base64 for LLM to perform OCR
    b64 = _image_to_b64(path)
    fallback = {
        "status": "ok_fallback",
        "file": str(path),
        "method": "base64_llm_fallback",
        "base64": b64,
        "llm_prompt": (
            "Please extract and return all visible text from the following image. "
            "Preserve formatting where possible."
        ),
        "note": (
            "pytesseract not installed or failed. Pass the base64 payload to a vision-capable LLM "
            "for OCR. Install: pip install pytesseract Pillow"
        ),
    }
    if tesseract_error:
        fallback["tesseract_error"] = tesseract_error
    return fallback


def list_images(directory: str, recursive: bool = False) -> dict:
    """List all image files in a directory.

    Args:
        directory: Path to search.
        recursive: Whether to search subdirectories.

    Returns:
        dict with list of image file paths and metadata.
    """
    dir_path = Path(directory)
    if not dir_path.exists():
        return {"status": "error", "error": f"Directory not found: {directory}"}

    glob_pattern = "**/*" if recursive else "*"
    images = []
    for p in dir_path.glob(glob_pattern):
        if p.is_file() and p.suffix.lower() in IMAGE_EXTENSIONS:
            entry = {"file": str(p), "size_bytes": p.stat().st_size}
            if HAS_PIL:
                entry.update(_image_metadata(p))
            images.append(entry)

    return {
        "status": "ok",
        "directory": str(dir_path),
        "recursive": recursive,
        "image_count": len(images),
        "images": images,
    }


def compare_images(image1: str, image2: str) -> dict:
    """Compare two images and return similarity metrics.

    Args:
        image1: Path to first image.
        image2: Path to second image.

    Returns:
        dict with similarity score (0.0=identical, 1.0=completely different) and diff info.
    """
    if not HAS_PIL:
        return {"status": "error", "error": "Pillow not installed — pip install Pillow"}

    p1, p2 = Path(image1), Path(image2)
    for p in (p1, p2):
        if not p.exists():
            return {"status": "error", "error": f"Image not found: {p}"}

    try:
        with Image.open(str(p1)) as img1, Image.open(str(p2)) as img2:
            # Resize to same dimensions for comparison
            size = (min(img1.width, img2.width), min(img1.height, img2.height))
            a = img1.convert("RGB").resize(size)
            b = img2.convert("RGB").resize(size)

            diff = ImageChops.difference(a, b)
            stat = ImageStat.Stat(diff)
            # RMS across all channels: 0 = identical, 255 = max difference
            rms = (sum(v**2 for v in stat.rms) / len(stat.rms)) ** 0.5
            similarity_score = round(1.0 - (rms / 255.0), 4)
            difference_score = round(rms / 255.0, 4)

            return {
                "status": "ok",
                "image1": str(p1),
                "image2": str(p2),
                "similarity": similarity_score,
                "difference": difference_score,
                "rms_diff": round(rms, 4),
                "same_size": img1.size == img2.size,
                "image1_size": list(img1.size),
                "image2_size": list(img2.size),
                "interpretation": (
                    "identical" if rms < 1.0
                    else "nearly identical" if rms < 10.0
                    else "similar" if rms < 40.0
                    else "different"
                ),
            }
    except Exception as exc:
        return {"status": "error", "error": str(exc)}


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="Overlord11 Vision Tool")
    parser.add_argument("--action", required=True,
                        choices=["screenshot", "analyze_image", "ocr",
                                 "list_images", "compare_images"],
                        help="Vision action to perform")
    parser.add_argument("--image", default=None, help="Path to image file")
    parser.add_argument("--image2", default=None, help="Second image path for compare_images")
    parser.add_argument("--output", default=None, help="Output file path for screenshot")
    parser.add_argument("--region", default=None,
                        help="Screen region 'left,top,width,height' for screenshot")
    parser.add_argument("--format", default="png", choices=["png", "jpeg"],
                        help="Image format for screenshot")
    parser.add_argument("--directory", default=None, help="Directory for list_images")
    parser.add_argument("--recursive", action="store_true", help="Recursive search for list_images")
    parser.add_argument("--no_b64", action="store_true",
                        help="Omit base64 payload from analyze_image response")

    args = parser.parse_args()
    start = time.time()

    try:
        if args.action == "screenshot":
            result = screenshot(output=args.output, region=args.region, format=args.format)
        elif args.action == "analyze_image":
            if not args.image:
                result = {"error": "--image is required for analyze_image"}
            else:
                result = analyze_image(args.image, include_b64=not args.no_b64)
        elif args.action == "ocr":
            if not args.image:
                result = {"error": "--image is required for ocr"}
            else:
                result = ocr(args.image)
        elif args.action == "list_images":
            if not args.directory:
                result = {"error": "--directory is required for list_images"}
            else:
                result = list_images(args.directory, recursive=args.recursive)
        elif args.action == "compare_images":
            if not args.image or not args.image2:
                result = {"error": "--image and --image2 are required for compare_images"}
            else:
                result = compare_images(args.image, args.image2)
        else:
            result = {"error": f"Unknown action: {args.action}"}

    except Exception as exc:
        result = {"status": "error", "error": str(exc), "action": args.action}
        if HAS_LOG:
            log_error("system", "vision_tool", str(exc))

    duration_ms = (time.time() - start) * 1000
    if HAS_LOG:
        log_tool_invocation(
            session_id="system",
            tool_name="vision_tool",
            params={"action": args.action},
            result={"status": result.get("status", "error")},
            duration_ms=duration_ms,
        )

    print(json.dumps(result, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
