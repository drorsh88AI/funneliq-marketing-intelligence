"""FunnelIQ API -- health, auth (phase 4), and the static frontend.

Business endpoints (/api/predict/*, /api/simulate/*, /api/insights/*) arrive
in phase 9, behind Depends(current_user) from app.auth.
"""
from __future__ import annotations

from pathlib import Path

from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from app.auth import router as auth_router

load_dotenv()  # no-op if .env doesn't exist (CI, Render -- env vars set directly)

app = FastAPI(title="FunnelIQ API", version="0.4.0")


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


app.include_router(auth_router)

# Mounted last on purpose: StaticFiles on "/" swallows every path that isn't
# matched by a route registered before it -- see PHASE4.md decision D13.
STATIC_DIR = Path(__file__).resolve().parent / "static"
app.mount("/", StaticFiles(directory=STATIC_DIR, html=True), name="static")
