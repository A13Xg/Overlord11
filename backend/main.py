"""
backend/main.py
================
Overlord11 Backend API — FastAPI application entry point.

Endpoints
---------
  /api/jobs/*           Job management
  /api/events/*         SSE event streaming
  /ws/*                 WebSocket streaming
  /api/models/*         Model management
  /api/providers/*      Provider status
  /api/artifacts/*      Artifact management
  /api/config           Config read/write
  /health               Health check
  /                     Serves the frontend (if built)

Run
---
  python scripts/run_backend.py
  # or
  uvicorn backend.main:app --reload --port 8080
"""

import os
import sys
from pathlib import Path

# Ensure project root is on path
_PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from backend.api.jobs import router as jobs_router
from backend.api.events import router as events_router
from backend.api.models_api import router as models_router
from backend.api.artifacts import router as artifacts_router
from backend.core.session_store import SessionStore

# ---------------------------------------------------------------------------
# App instance
# ---------------------------------------------------------------------------

app = FastAPI(
    title="Overlord11 API",
    description="Full-stack AI platform backend — engine + WebUI",
    version="3.0.0",
    docs_url="/api/docs",
    redoc_url="/api/redoc",
)

# ---------------------------------------------------------------------------
# CORS (allow Next.js dev server)
# ---------------------------------------------------------------------------

_CORS_ORIGINS = os.environ.get(
    "CORS_ORIGINS",
    "http://localhost:3000,http://127.0.0.1:3000",
).split(",")

app.add_middleware(
    CORSMiddleware,
    allow_origins=_CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ---------------------------------------------------------------------------
# Shared state — store singleton (injected into routers via dependency)
# ---------------------------------------------------------------------------

store = SessionStore(store_dir=str(_PROJECT_ROOT / "logs" / "jobs"))

# ---------------------------------------------------------------------------
# Routers
# ---------------------------------------------------------------------------

app.include_router(jobs_router)
app.include_router(events_router)
app.include_router(models_router)
app.include_router(artifacts_router)

# ---------------------------------------------------------------------------
# Health
# ---------------------------------------------------------------------------

@app.get("/health", tags=["system"])
def health():
    return {"status": "ok", "version": "3.0.0"}


# ---------------------------------------------------------------------------
# Serve built frontend (optional — only if frontend/out/ exists)
# ---------------------------------------------------------------------------

_FRONTEND_OUT = _PROJECT_ROOT / "frontend" / "out"
if _FRONTEND_OUT.exists():
    app.mount("/", StaticFiles(directory=str(_FRONTEND_OUT), html=True), name="frontend")


# ---------------------------------------------------------------------------
# Dev entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import uvicorn

    port = int(os.environ.get("PORT", 8080))
    uvicorn.run("backend.main:app", host="0.0.0.0", port=port, reload=True)
