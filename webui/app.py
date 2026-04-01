"""Tactical WebUI — FastAPI backend for Overlord11 job browsing and control."""
from __future__ import annotations

import json
import mimetypes
import os
import re
import time
import uuid
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any, Dict, List, Optional

from fastapi import FastAPI, HTTPException, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

# Load .env before anything else; override=False respects env vars already set
try:
    from dotenv import load_dotenv as _load_dotenv
    _load_dotenv(Path(__file__).resolve().parent.parent / ".env", override=False)
except ImportError:
    pass  # python-dotenv not installed; rely on system env vars

from . import provider_health, state_store
from .logging_config import get_webui_logger
from .models import (
    VALID_PROVIDERS,
    ArtifactInfo,
    ConfigInfo,
    CreateJobRequest,
    JobDetail,
    JobStatus,
    JobSummary,
    SelectionRequest,
)

log = get_webui_logger()

CONFIG_FILE = Path(__file__).resolve().parent.parent / "config.json"
STATIC_DIR = Path(__file__).resolve().parent / "static"
# User-selected model preference (persisted across page refreshes, not in config.json)
PREFS_FILE = Path(__file__).resolve().parent.parent / "workspace" / ".webui_prefs.json"


# ── Lifespan ──────────────────────────────────────────────────────────────────

@asynccontextmanager
async def lifespan(app: FastAPI):
    log.info("Overlord11 Tactical WebUI starting", extra={"event": "startup", "version": "2.3.0"})
    import asyncio

    async def _background_probe():
        """Run provider probes at startup without blocking the server."""
        try:
            await provider_health.probe_all()
            log.info("Startup provider probes complete", extra={"event": "probe_complete"})
        except Exception as exc:
            log.error("Startup provider probe failed", extra={"event": "probe_error", "exc": str(exc)})

    asyncio.ensure_future(_background_probe())
    log.info("Background provider probes initiated", extra={"event": "probe_start"})
    yield
    log.info("Overlord11 Tactical WebUI shutting down", extra={"event": "shutdown"})


# ── App ───────────────────────────────────────────────────────────────────────

app = FastAPI(
    title="Overlord11 Tactical WebUI",
    description="Browse jobs, artifacts, and finished products",
    version="2.3.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["GET", "HEAD", "OPTIONS", "PUT", "POST", "DELETE"],
    allow_headers=["*"],
)


@app.middleware("http")
async def log_requests(request: Request, call_next):
    t0 = time.monotonic()
    try:
        response = await call_next(request)
    except Exception as exc:
        ms = int((time.monotonic() - t0) * 1000)
        log.error(
            f"Unhandled error: {request.method} {request.url.path}",
            extra={"event": "http_error", "method": request.method,
                   "path": request.url.path, "exc": str(exc), "ms": ms},
        )
        raise
    ms = int((time.monotonic() - t0) * 1000)
    log.info(
        f"{request.method} {request.url.path} → {response.status_code} ({ms}ms)",
        extra={"event": "http_request", "method": request.method,
               "path": request.url.path, "status": response.status_code, "ms": ms},
    )
    return response


# ── Config helpers ─────────────────────────────────────────────────────────────

def _load_config() -> dict:
    try:
        return json.loads(CONFIG_FILE.read_text(encoding="utf-8"))
    except Exception as exc:
        log.error("Failed to load config.json", extra={"exc": str(exc)})
        return {}


def _load_prefs() -> dict:
    try:
        if PREFS_FILE.exists():
            return json.loads(PREFS_FILE.read_text(encoding="utf-8"))
    except Exception as exc:
        log.warning("Failed to load webui prefs", extra={"exc": str(exc)})
    return {}


def _save_prefs(prefs: dict) -> None:
    try:
        PREFS_FILE.parent.mkdir(parents=True, exist_ok=True)
        PREFS_FILE.write_text(
            json.dumps(prefs, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
    except Exception as exc:
        log.error("Failed to save webui prefs", extra={"exc": str(exc)})


def _effective_selection() -> tuple[str, str]:
    """Return (provider, model) merging prefs > config defaults."""
    prefs = _load_prefs()
    cfg = _load_config()
    providers_cfg = cfg.get("providers", {})
    provider = prefs.get("provider") or providers_cfg.get("active", "gemini")
    model = prefs.get("model") or providers_cfg.get(provider, {}).get("model", "")
    return provider, model


# ── Health ─────────────────────────────────────────────────────────────────────

@app.get("/api/health")
def health():
    provider, model = _effective_selection()
    return {
        "status": "ok",
        "service": "Overlord11 Tactical WebUI",
        "version": "2.3.0",
        "active_provider": provider,
        "active_model": model,
    }


# ── Jobs ───────────────────────────────────────────────────────────────────────

@app.get("/api/jobs", response_model=List[JobSummary])
def list_jobs(status: Optional[str] = None, q: Optional[str] = None):
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


@app.post("/api/jobs", response_model=JobSummary, status_code=201)
def create_job(req: CreateJobRequest):
    """Create a new pending job. Requires a runner to execute."""
    if not req.goal or not req.goal.strip():
        raise HTTPException(status_code=400, detail="Goal cannot be empty")

    # Resolve provider / model: request > prefs > config
    cfg = _load_config()
    prefs = _load_prefs()
    providers_cfg = cfg.get("providers", {})
    provider = req.provider or prefs.get("provider") or providers_cfg.get("active", "gemini")
    model = req.model or prefs.get("model") or providers_cfg.get(provider, {}).get("model", "")

    if provider not in VALID_PROVIDERS:
        raise HTTPException(status_code=400,
                            detail=f"Unknown provider: {provider}. Valid: {VALID_PROVIDERS}")

    job_id = uuid.uuid4().hex[:16]
    jobs_dir = state_store.JOBS_DIR
    jobs_dir.mkdir(parents=True, exist_ok=True)
    new_job_dir = jobs_dir / job_id
    new_job_dir.mkdir()

    now = time.time()
    state_data = {
        "job_id": job_id,
        "goal": req.goal.strip(),
        "status": "pending",
        "provider": provider,
        "model": model,
        "verify_command": req.verify_command,
        "created": now,
        "updated": now,
    }
    (new_job_dir / "state.json").write_text(
        json.dumps(state_data, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    log.info(
        f"Job created: {job_id}",
        extra={"event": "job_create", "job_id": job_id,
               "provider": provider, "model": model},
    )
    return JobSummary(
        job_id=job_id,
        goal=req.goal.strip(),
        status=JobStatus.pending,
        created=now,
        updated=now,
        provider=provider,
        model=model,
    )


# ── Artifacts ─────────────────────────────────────────────────────────────────

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


# ── Config / Providers ────────────────────────────────────────────────────────

@app.get("/api/config", response_model=ConfigInfo)
def get_config():
    """Get current provider configuration. API keys are never exposed."""
    cfg = _load_config()
    prefs = _load_prefs()
    providers_cfg = cfg.get("providers", {})
    active = prefs.get("provider") or providers_cfg.get("active", "gemini")
    default_model = prefs.get("model") or providers_cfg.get(active, {}).get("model", "")

    providers_out: Dict[str, Any] = {}
    for pname in VALID_PROVIDERS:
        pcfg = providers_cfg.get(pname, {})
        effective_model = (
            prefs.get("model") if pname == active else pcfg.get("model")
        )
        providers_out[pname] = {
            "model": effective_model,
            "available_models": pcfg.get("available_models", {}),
            "api_key_env": pcfg.get("api_key_env", ""),
            "api_key_set": bool(os.environ.get(pcfg.get("api_key_env", ""), "")),
        }

    return ConfigInfo(
        active_provider=active,
        providers=providers_out,
        default_model=default_model,
    )


@app.get("/api/providers/status")
async def get_provider_status(force: bool = False):
    """Live API health status for all providers. ?force=true re-probes immediately."""
    if force:
        log.info("Forced provider re-probe", extra={"event": "probe_force"})
        return await provider_health.probe_all(force=True)
    cached = provider_health.get_cached()
    # If everything is still in "checking", kick off a fresh probe
    if all(v.get("status") == "checking" for v in cached.values()):
        return await provider_health.probe_all()
    return cached


@app.get("/api/config/selection")
def get_selection():
    """Current active provider/model selection (prefs override config defaults)."""
    prefs = _load_prefs()
    provider, model = _effective_selection()
    return {
        "provider": provider,
        "model": model,
        "from_prefs": bool(prefs.get("provider") or prefs.get("model")),
    }


@app.put("/api/config/selection")
def set_selection(req: SelectionRequest):
    """Set active provider and/or model for the next queued job."""
    if req.provider and req.provider not in VALID_PROVIDERS:
        raise HTTPException(
            status_code=400,
            detail=f"Unknown provider '{req.provider}'. Valid: {VALID_PROVIDERS}",
        )
    # Validate model against known config models + live API models
    if req.provider and req.model:
        cfg = _load_config()
        pcfg = cfg.get("providers", {}).get(req.provider, {})
        config_models = set(pcfg.get("available_models", {}).keys())
        live_models = set(provider_health.get_cached().get(req.provider, {}).get("models", []))
        all_known = config_models | live_models
        if all_known and req.model not in all_known:
            raise HTTPException(
                status_code=400,
                detail=f"Unknown model '{req.model}' for provider '{req.provider}'",
            )
    prefs = {"provider": req.provider, "model": req.model}
    _save_prefs(prefs)
    log.info(
        f"Selection updated: {req.provider}/{req.model}",
        extra={"event": "selection_update", "provider": req.provider, "model": req.model},
    )
    return {"ok": True, "provider": req.provider, "model": req.model}


@app.delete("/api/config/selection")
def clear_selection():
    """Reset selection to config.json defaults."""
    _save_prefs({})
    log.info("Selection cleared", extra={"event": "selection_clear"})
    provider, model = _effective_selection()
    return {"ok": True, "provider": provider, "model": model}


@app.get("/api/providers/gemini/fallback")
def gemini_fallback_info():
    """Return the Gemini rate-limit fallback chain and current active model."""
    cached = provider_health.get_cached().get("gemini", {})
    return {
        "fallback_chain": provider_health.GEMINI_FALLBACK_CHAIN,
        "current_status": cached.get("status"),
        "rate_limit_retry_after": provider_health.get_rate_limit_retry_after("gemini"),
        "active_model_override": cached.get("active_model_override"),
    }


# ── Static frontend ───────────────────────────────────────────────────────────

if STATIC_DIR.exists():
    app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

    @app.get("/", include_in_schema=False)
    @app.get("/{path:path}", include_in_schema=False)
    def serve_frontend(path: str = ""):
        index = STATIC_DIR / "index.html"
        if index.exists():
            return FileResponse(str(index), media_type="text/html; charset=utf-8")
        return JSONResponse({"error": "Frontend not found"}, status_code=404)
