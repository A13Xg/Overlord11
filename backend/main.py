"""
Overlord11 Tactical WebUI — FastAPI application entry point.
"""

import logging
import sys
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

_BASE_DIR = Path(__file__).resolve().parent.parent

# Ensure project root on sys.path for engine imports
if str(_BASE_DIR) not in sys.path:
    sys.path.insert(0, str(_BASE_DIR))

from .api.artifacts import router as artifacts_router
from .api.auth import router as auth_router
from .api.events import router as events_router
from .api.jobs import router as jobs_router
from .api.providers import router as providers_router
from .core.engine_bridge import bridge
from .core.session_store import store

# ------------------------------------------------------------------
# Lifespan (startup / shutdown)
# ------------------------------------------------------------------

@asynccontextmanager
async def lifespan(app: FastAPI):
    store.load()
    bridge.start_worker()
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
