"""Tactical WebUI — FastAPI backend for Overlord11 job browsing."""
import json
import mimetypes
import re
from pathlib import Path
from typing import List, Optional

from fastapi import FastAPI, HTTPException, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from . import state_store
from .models import (
    VALID_PROVIDERS,
    ArtifactInfo,
    ConfigInfo,
    JobDetail,
    JobSummary,
)

CONFIG_FILE = Path(__file__).resolve().parent.parent / "config.json"
STATIC_DIR = Path(__file__).resolve().parent / "static"

app = FastAPI(
    title="Overlord11 Tactical WebUI",
    description="Browse jobs, artifacts, and finished products",
    version="2.3.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["GET", "HEAD", "OPTIONS"],
    allow_headers=["*"],
)


def _load_config() -> dict:
    try:
        return json.loads(CONFIG_FILE.read_text(encoding="utf-8"))
    except Exception:
        return {}


# ─── Read-only API endpoints ─────────────────────────────────────────────────

@app.get("/api/jobs", response_model=List[JobSummary])
def list_jobs(
    status: Optional[str] = None,
    q: Optional[str] = None,
):
    """List all jobs, optionally filtered by status or search query."""
    jobs = state_store.list_jobs()
    if status:
        jobs = [j for j in jobs if j.status.value == status]
    if q:
        q_lower = q.lower()
        jobs = [
            j for j in jobs
            if (j.goal and q_lower in j.goal.lower()) or q_lower in j.job_id.lower()
        ]
    return jobs


@app.get("/api/jobs/{job_id}", response_model=JobDetail)
def get_job(job_id: str):
    """Get full job detail including state, events, and artifacts."""
    if not re.match(r'^[a-zA-Z0-9_\-]{1,128}$', job_id):
        raise HTTPException(status_code=400, detail="Invalid job_id")
    job = state_store.get_job(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found")
    return job


@app.get("/api/jobs/{job_id}/artifacts", response_model=List[ArtifactInfo])
def list_artifacts(job_id: str):
    """List artifacts for a job."""
    if not re.match(r'^[a-zA-Z0-9_\-]{1,128}$', job_id):
        raise HTTPException(status_code=400, detail="Invalid job_id")
    arts = state_store.list_artifacts(job_id)
    if arts is None:
        raise HTTPException(status_code=404, detail="Job not found")
    return arts


@app.get("/api/jobs/{job_id}/artifacts/{artifact_path:path}")
def get_artifact(job_id: str, artifact_path: str):
    """Fetch a specific artifact file."""
    if not re.match(r'^[a-zA-Z0-9_\-]{1,128}$', job_id):
        raise HTTPException(status_code=400, detail="Invalid job_id")
    data = state_store.read_artifact(job_id, artifact_path)
    if data is None:
        raise HTTPException(status_code=404, detail="Artifact not found")
    mime, _ = mimetypes.guess_type(artifact_path)
    if mime is None:
        mime = "application/octet-stream"
    return Response(content=data, media_type=mime)


@app.get("/api/config", response_model=ConfigInfo)
def get_config():
    """Get current provider configuration."""
    cfg = _load_config()
    providers_cfg = cfg.get("providers", {})
    active = providers_cfg.get("active", "gemini")
    active_cfg = providers_cfg.get(active, {})
    default_model = active_cfg.get("model", "gemini-3.1-flash-lite-preview")

    providers_out = {}
    for pname in VALID_PROVIDERS:
        pcfg = providers_cfg.get(pname, {})
        providers_out[pname] = {
            "model": pcfg.get("model"),
            "available_models": pcfg.get("available_models", {}),
        }

    return ConfigInfo(
        active_provider=active,
        providers=providers_out,
        default_model=default_model,
    )


@app.get("/api/health")
def health():
    return {"status": "ok", "service": "Overlord11 Tactical WebUI"}


# ─── Static frontend ──────────────────────────────────────────────────────────

if STATIC_DIR.exists():
    app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

    @app.get("/", include_in_schema=False)
    @app.get("/{path:path}", include_in_schema=False)
    def serve_frontend(path: str = ""):
        index = STATIC_DIR / "index.html"
        if index.exists():
            return FileResponse(str(index))
        return JSONResponse({"error": "Frontend not found"}, status_code=404)
