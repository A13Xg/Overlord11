"""
Artifacts API — list and download job artifacts.
"""

import os
import re
import subprocess
import tempfile
import zipfile
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel

from ..core.session_store import store

router = APIRouter(prefix="/api/artifacts", tags=["artifacts"])

_BASE_DIR = Path(__file__).resolve().parent.parent.parent
_WORKSPACE_DIR = _BASE_DIR / "workspace"

_JOB_ID_RE = re.compile(r"^[a-f0-9]{8,64}$")
_SESSION_ID_RE = re.compile(r"^[0-9]{8}_[0-9]{6}$")  # YYYYMMDD_HHMMSS engine format
_ARTIFACT_NAME_RE = re.compile(r"^[A-Za-z0-9_\-\.]{1,128}$")


def _validate_job_id(job_id: str) -> None:
    if not _JOB_ID_RE.match(job_id):
        raise HTTPException(status_code=400, detail="Invalid job_id format")


def _validate_artifact_name(name: str) -> None:
    if not _ARTIFACT_NAME_RE.match(name):
        raise HTTPException(status_code=400, detail="Invalid artifact name")


def _session_root(job: object) -> Path:
    """Locate the session workspace root for a job.

    IMPORTANT: Only uses session_id. Job must have completed with a session_id
    assigned. If session_id is not set, raises an error instead of creating
    spurious workspace/job_id folder.
    """
    session_id = getattr(job, "session_id", None)
    if session_id:
        sid_str = str(session_id)
        # Validate session_id is in expected format (YYYYMMDD_HHMMSS or YYYYMMDD_HHMMSS_jobid)
        if _JOB_ID_RE.match(sid_str) or _SESSION_ID_RE.match(sid_str) or "_" in sid_str:
            candidate = _WORKSPACE_DIR / sid_str
            if candidate.is_dir():
                return candidate
    # No valid session_id: raise error instead of creating spurious folder
    raise HTTPException(
        status_code=409,
        detail="Job has not completed yet or session_id is missing. Wait for job to complete."
    )


def _iter_artifact_files(root: Path):
    indexed_roots = {"outputs", "output", "artifacts", "logs", "traces", "tools", "agent"}
    for subdir in ("outputs", "output", "artifacts", "logs", "traces", "tools", "agent"):
        base = root / subdir
        if not base.exists():
            continue
        for entry in sorted(base.rglob("*")):
            if entry.is_file():
                yield subdir, entry
    # Include workspace-root and non-indexed directories as "other" so files
    # written to session root remain visible in WebUI.
    for entry in sorted(root.rglob("*")):
        if not entry.is_file():
            continue
        rel_parts = entry.relative_to(root).parts
        if not rel_parts:
            continue
        if rel_parts[0] in indexed_roots:
            continue
        yield "other", entry


def _artifact_item_from_entry(root: Path, category: str, entry: Path) -> dict:
    stat = entry.stat()
    ext = entry.suffix.lstrip(".").lower()
    rel = str(entry.relative_to(root)).replace("\\", "/")
    return {
        "name": entry.name,
        "relative_path": rel,
        "category": category,
        "size": stat.st_size,
        "mtime": stat.st_mtime,
        "ext": ext,
        "is_html": ext in ("html", "htm"),
        "is_image": ext in ("png", "jpg", "jpeg", "gif", "webp", "bmp", "svg"),
    }


def _collect_artifacts(root: Path) -> list[dict]:
    items: list[dict] = []
    for category, entry in _iter_artifact_files(root):
        items.append(_artifact_item_from_entry(root, category, entry))
    return items


_OUTPUT_EXT_PRIORITY = {
    "html": 0,
    "htm": 1,
    "pdf": 2,
    "csv": 3,
    "json": 4,
    "py": 5,
    "md": 6,
    "txt": 7,
    "png": 8,
    "jpg": 9,
    "jpeg": 10,
    "webp": 11,
    "gif": 12,
    "svg": 13,
    "zip": 14,
}


def _is_primary_output_candidate(item: dict) -> bool:
    rel = (item.get("relative_path") or "").lower()
    name = (item.get("name") or "").lower()
    if name.startswith("answer.") and rel.startswith(("output/", "outputs/")):
        return True
    if rel.startswith("output/answer.") or rel.startswith("outputs/answer."):
        return True
    return False


def _output_rank(item: dict) -> tuple:
    name = (item.get("name") or "").lower()
    rel = (item.get("relative_path") or "").lower()
    ext = (item.get("ext") or "").lower()
    # Lower is better
    if name.startswith("answer.") and rel.startswith(("output/", "outputs/")):
        bucket = 0
    else:
        bucket = 9
    ext_rank = _OUTPUT_EXT_PRIORITY.get(ext, 999)
    # Prefer newest for ties.
    mtime_rank = -float(item.get("mtime") or 0.0)
    return (bucket, ext_rank, mtime_rank, rel)


def _select_primary_output(items: list[dict]) -> Optional[dict]:
    candidates = [it for it in items if _is_primary_output_candidate(it)]
    if not candidates:
        return None
    return sorted(candidates, key=_output_rank)[0]


def _resolve_relative_artifact(root: Path, relative_path: str) -> Path:
    target = (root / relative_path).resolve()
    try:
        target.relative_to(root.resolve())
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid artifact path")
    if not target.exists() or not target.is_file():
        raise HTTPException(status_code=404, detail="Artifact not found")
    return target


def _select_html_source(root: Path, relative_path: Optional[str]) -> Path:
    if relative_path:
        target = _resolve_relative_artifact(root, relative_path)
        if target.suffix.lower() not in (".html", ".htm"):
            raise HTTPException(status_code=400, detail="Screenshot source must be an HTML artifact")
        return target

    for category, entry in _iter_artifact_files(root):
        if category not in ("product", "outputs", "output", "artifacts"):
            continue
        if entry.suffix.lower() in (".html", ".htm"):
            return entry

    raise HTTPException(status_code=404, detail="No HTML artifact found to screenshot")


async def _capture_with_playwright(source_html: Path, output_png: Path) -> None:
    from playwright.async_api import async_playwright

    async with async_playwright() as playwright:
        browser = await playwright.chromium.launch(args=["--no-sandbox", "--disable-dev-shm-usage"])
        page = await browser.new_page(viewport={"width": 1440, "height": 900})
        await page.goto(source_html.resolve().as_uri(), wait_until="networkidle")
        await page.screenshot(path=str(output_png), full_page=True)
        await browser.close()


def _capture_with_wkhtmltoimage(source_html: Path, output_png: Path) -> None:
    command = [
        "wkhtmltoimage",
        "--quality",
        "90",
        str(source_html),
        str(output_png),
    ]
    subprocess.run(command, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)


def _make_workspace_zip(session_root: Path, target_zip: Path) -> None:
    with zipfile.ZipFile(target_zip, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        for path in sorted(session_root.rglob("*")):
            if not path.is_file():
                continue
            rel = path.relative_to(session_root)
            zf.write(path, arcname=str(rel).replace("\\", "/"))


@router.get("/{job_id}/files")
async def list_session_files(job_id: str):
    _validate_job_id(job_id)
    job = store.get_job(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found")

    session_root = _session_root(job)
    if not session_root.exists():
        return []

    items = []
    for entry in sorted(session_root.rglob("*")):
        if entry.is_file():
            stat = entry.stat()
            items.append({
                "name": entry.name,
                "relative_path": str(entry.relative_to(session_root)).replace("\\", "/"),
                "size": stat.st_size,
                "mtime": stat.st_mtime,
            })
    return items

@router.get("/{job_id}")
async def list_artifacts(job_id: str):
    _validate_job_id(job_id)
    job = store.get_job(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found")

    session_root = _session_root(job)
    if not session_root.exists():
        return []

    return _collect_artifacts(session_root)


@router.get("/{job_id}/primary-output")
async def get_primary_output(job_id: str):
    """
    Resolve the most user-visible result artifact for a job.

    Priority:
    1) output/answer.* or outputs/answer.*
    2) fallback output/answer.md when present
    3) output directory hint when no answer.* exists
    """
    _validate_job_id(job_id)
    job = store.get_job(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found")

    session_root = _session_root(job)
    if not session_root.exists():
        raise HTTPException(status_code=404, detail="Session workspace not found")

    items = _collect_artifacts(session_root)
    if not items:
        return {
            "status": "empty",
            "mode": "directory",
            "job_id": job_id,
            "session_id": job.session_id,
            "directory": "output",
            "download_url": f"/api/artifacts/{job_id}/download/workspace.zip",
            "message": "No artifacts found yet.",
        }

    output_items = [
        it for it in items
        if (it.get("relative_path") or "").lower().startswith(("output/answer.", "outputs/answer."))
    ]
    primary = _select_primary_output(items)
    if primary is not None:
        rel = primary["relative_path"]
        ext = (primary.get("ext") or "").lower()
        previewable = bool(
            primary.get("is_html")
            or primary.get("is_image")
            or ext in {"md", "txt", "json", "csv", "pdf"}
        )
        return {
            "status": "ok",
            "mode": "file",
            "job_id": job_id,
            "session_id": job.session_id,
            "primary": primary,
            "previewable": previewable,
            "file_url": f"/api/artifacts/{job_id}/file/{rel}",
            "download_url": f"/api/artifacts/{job_id}/file/{rel}",
            "artifacts_url": f"/api/artifacts/{job_id}",
            "workspace_zip_url": f"/api/artifacts/{job_id}/download/workspace.zip",
            "output_files": sorted(output_items, key=_output_rank)[:25],
        }

    # Fallback to output directory hint when no answer.* deliverable exists yet.
    has_output_dir = any((session_root / d).exists() for d in ("output", "outputs"))
    return {
        "status": "ok",
        "mode": "directory",
        "job_id": job_id,
        "session_id": job.session_id,
        "directory": "output" if has_output_dir else ".",
        "artifacts_url": f"/api/artifacts/{job_id}",
        "workspace_zip_url": f"/api/artifacts/{job_id}/download/workspace.zip",
        "output_files": sorted(output_items, key=_output_rank)[:25],
    }


@router.get("/{job_id}/{name}")
async def download_artifact(job_id: str, name: str):
    _validate_job_id(job_id)
    _validate_artifact_name(name)

    job = store.get_job(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found")

    session_root = _session_root(job).resolve()

    # Derive safe_name from os.path.basename to strip any stray separators,
    # then locate the file by iterating the directory so that the Path used
    # for serving always originates from the filesystem, not from user input.
    safe_name = os.path.basename(name)
    matched: Optional[Path] = None
    for _, entry in _iter_artifact_files(session_root):
        if entry.name == safe_name:
            matched = entry
            break

    if matched is None:
        raise HTTPException(status_code=404, detail="Artifact not found")

    # Paranoia: confirm the filesystem-derived path is still inside art_dir
    try:
        matched.resolve().relative_to(session_root)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid artifact path")

    return FileResponse(str(matched), filename=matched.name)


@router.get("/{job_id}/file/{relative_path:path}")
async def download_artifact_path(job_id: str, relative_path: str):
    _validate_job_id(job_id)

    job = store.get_job(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found")

    session_root = _session_root(job)
    matched = _resolve_relative_artifact(session_root, relative_path)
    return FileResponse(str(matched), filename=matched.name)


@router.get("/{job_id}/download/workspace.zip")
async def download_workspace_zip(job_id: str):
    _validate_job_id(job_id)

    job = store.get_job(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found")

    session_root = _session_root(job)
    if not session_root.exists():
        raise HTTPException(status_code=404, detail="Session workspace not found")

    tmp = tempfile.NamedTemporaryFile(prefix=f"{job_id}_workspace_", suffix=".zip", delete=False)
    tmp_path = Path(tmp.name)
    tmp.close()

    try:
        _make_workspace_zip(session_root, tmp_path)
        return FileResponse(
            str(tmp_path),
            media_type="application/zip",
            filename=f"{session_root.name}.zip",
        )
    finally:
        # Intentionally keep file for response streaming; clean up old temp zips opportunistically.
        try:
            temp_dir = tmp_path.parent
            for stale in temp_dir.glob("*_workspace_*.zip"):
                if stale == tmp_path:
                    continue
                if stale.stat().st_mtime < (tmp_path.stat().st_mtime - 3600):
                    stale.unlink(missing_ok=True)
        except OSError:
            pass


class ScreenshotRequest(BaseModel):
    relative_path: Optional[str] = None


@router.post("/{job_id}/actions/screenshot")
async def create_artifact_screenshot(job_id: str, req: ScreenshotRequest):
    _validate_job_id(job_id)

    job = store.get_job(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found")

    session_root = _session_root(job)
    source = _select_html_source(session_root, req.relative_path)

    screenshots_dir = session_root / "artifacts" / "screenshots"
    screenshots_dir.mkdir(parents=True, exist_ok=True)
    output_name = f"{source.stem}_screenshot.png"
    output_path = screenshots_dir / output_name

    screenshot_error = None
    try:
        await _capture_with_playwright(source, output_path)
    except Exception as exc:
        screenshot_error = exc

    if not output_path.exists():
        try:
            _capture_with_wkhtmltoimage(source, output_path)
        except Exception as fallback_exc:
            if screenshot_error:
                raise HTTPException(
                    status_code=503,
                    detail=(
                        "Unable to generate screenshot. "
                        f"playwright={type(screenshot_error).__name__}: {screenshot_error}; "
                        f"wkhtmltoimage={type(fallback_exc).__name__}: {fallback_exc}"
                    ),
                ) from screenshot_error
            raise HTTPException(
                status_code=503,
                detail=f"Unable to generate screenshot in current environment: {fallback_exc}",
            )

    return {
        "status": "ok",
        "source": str(source.relative_to(session_root)).replace("\\", "/"),
        "relative_path": str(output_path.relative_to(session_root)).replace("\\", "/"),
    }
