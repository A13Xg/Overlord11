"""
Overlord11 Tactical WebUI — FastAPI application entry point.
"""

import logging
import os
import sys
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

_BASE_DIR = Path(__file__).resolve().parent.parent

# ── Load .env file into os.environ before any other imports ──────────────────
# The setup wizard writes API keys to <project_root>/.env.  We load them here
# so they are available to the engine on every server start without requiring
# the python-dotenv package.
_ENV_FILE = _BASE_DIR / ".env"
if _ENV_FILE.exists():
    try:
        for _line in _ENV_FILE.read_text(encoding="utf-8").splitlines():
            _line = _line.strip()
            if not _line or _line.startswith("#") or "=" not in _line:
                continue
            _key, _, _val = _line.partition("=")
            _key = _key.strip()
            _val = _val.strip().strip('"').strip("'")
            if _key and _key not in os.environ:  # don't override explicit env vars
                os.environ[_key] = _val
    except OSError:
        pass
# ─────────────────────────────────────────────────────────────────────────────

# Ensure project root on sys.path for engine imports
if str(_BASE_DIR) not in sys.path:
    sys.path.insert(0, str(_BASE_DIR))

import json

from .api.artifacts import router as artifacts_router
from .api.auth import router as auth_router
from .api.events import router as events_router
from .api.health import router as health_router
from .api.jobs import router as jobs_router
from .api.providers import router as providers_router
from .api.setup import router as setup_router
from .api.templates import router as templates_router
from .core.engine_bridge import bridge
from .core.session_store import store

_CONFIG_FILE = _BASE_DIR / "config.json"

# ------------------------------------------------------------------
# Lifespan (startup / shutdown)
# ------------------------------------------------------------------

@asynccontextmanager
async def lifespan(app: FastAPI):
    store.load()
    try:
        config = json.loads(_CONFIG_FILE.read_text(encoding="utf-8"))
    except Exception:
        config = {}
    bridge.start_worker(config=config)
    try:
        yield
    finally:
        await bridge.stop_worker()


app = FastAPI(
    title="Overlord11 Tactical WebUI",
    version="2.3.0",
    docs_url="/api/docs",
    redoc_url="/api/redoc",
    lifespan=lifespan,
)

# ------------------------------------------------------------------
# CORS
# ------------------------------------------------------------------
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ------------------------------------------------------------------
# Routers
# ------------------------------------------------------------------
app.include_router(auth_router)
app.include_router(jobs_router)
app.include_router(providers_router)
app.include_router(artifacts_router)
app.include_router(events_router)
app.include_router(health_router)
app.include_router(setup_router)
app.include_router(templates_router)

# ------------------------------------------------------------------
# Frontend — serve index.html for all non-API routes
# ------------------------------------------------------------------
_FRONTEND_DIR = _BASE_DIR / "frontend"
_INDEX_HTML = _FRONTEND_DIR / "index.html"
_LOGIN_HTML = _FRONTEND_DIR / "login.html"


@app.get("/", include_in_schema=False)
async def serve_index():
    return FileResponse(str(_INDEX_HTML))


@app.get("/login", include_in_schema=False)
async def serve_login():
    return FileResponse(str(_LOGIN_HTML))


@app.get("/{full_path:path}", include_in_schema=False)
async def serve_spa(full_path: str):
    # Don't intercept /api routes
    if full_path.startswith("api/"):
        return JSONResponse({"detail": "Not Found"}, status_code=404)
    return FileResponse(str(_INDEX_HTML))


# ------------------------------------------------------------------
# Global exception handler — only catches unexpected non-HTTP errors
# ------------------------------------------------------------------

@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    # Let FastAPI's own HTTP exception handling flow through
    if isinstance(exc, HTTPException):
        raise exc
    logging.getLogger("overlord11.webui").exception("Unhandled exception: %s", exc)
    return JSONResponse(
        status_code=500,
        content={"detail": "Internal server error"},
    )
