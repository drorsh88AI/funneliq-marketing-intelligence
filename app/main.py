"""FunnelIQ API -- health, auth (phase 4), and the static frontend.

Business endpoints (/api/predict/*, /api/simulate/*, /api/insights/*) arrive
in phase 9, behind Depends(current_user) from app.auth.
"""
from __future__ import annotations

from contextlib import asynccontextmanager
from pathlib import Path

from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from app.artifacts import get_assets
from app.auth import router as auth_router

load_dotenv()  # no-op if .env doesn't exist (CI, Render -- env vars set directly)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """PHASE9.md D2: forces the seven static JSON assets to load and
    schema-validate BEFORE the app starts accepting requests. get_assets()
    is itself lazy/idempotent (app.artifacts) -- this call just makes sure
    it happens here, eagerly, so a broken asset raises ArtifactStartupError
    and aborts startup (uvicorn never binds the port; Render's health check
    never passes; the previous deploy stays live) instead of surfacing as
    a per-request 500 on whichever request happens to hit it first."""
    get_assets()
    yield


app = FastAPI(title="FunnelIQ API", version="0.4.0", lifespan=lifespan)


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


app.include_router(auth_router)

# Mounted last on purpose: StaticFiles on "/" swallows every path that isn't
# matched by a route registered before it -- see PHASE4.md decision D13.
STATIC_DIR = Path(__file__).resolve().parent / "static"
app.mount("/", StaticFiles(directory=STATIC_DIR, html=True), name="static")
