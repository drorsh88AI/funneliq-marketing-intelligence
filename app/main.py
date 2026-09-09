"""FunnelIQ API -- health, auth (phase 4), business endpoints (phase 9),
and the static frontend.

Business endpoints (/api/predict/*, /api/simulate/*, /api/insights/*) sit
behind Depends(current_user)/Depends(access_token) from app.auth.
"""
from __future__ import annotations

from contextlib import asynccontextmanager
from pathlib import Path

from dotenv import load_dotenv
from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError, ResponseValidationError
from fastapi.staticfiles import StaticFiles
from fastapi.responses import JSONResponse

from app.artifacts import get_assets
from app.auth import router as auth_router
from app.insights import router as insights_router
from app.predict import router as predict_router
from app.schemas import ErrorDetail, HTTPValidationError, ValidationErrorItem

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


# PHASE9.md D7 -- three handlers, closing the gap D7's own body documents:
# by default, an unhandled exception (or a response that fails its own
# response_model) reaches the client as `text/plain "Internal Server
# Error"`, not the locked ErrorDetail JSON body every 500/503 in the
# contract promises (verified empirically during planning). Registering a
# handler for HTTPException is NOT needed and NOT done here -- FastAPI's
# own default HTTPException handler already returns exactly
# {"detail": exc.detail} (app/auth.py's raise HTTPException(...) calls
# already rely on this), and adding a broader Exception handler does not
# override it (verified: FastAPI dispatches to the most specific
# registered handler type, not just the first one that matches).


@app.exception_handler(RequestValidationError)
async def request_validation_exception_handler(
    request: Request, exc: RequestValidationError
) -> JSONResponse:
    """422 on the three POST routes' body violations. FastAPI's own
    default 422 body carries `input` (the raw value that failed) and
    sometimes `ctx` -- both dropped here (D7): `input` can echo back
    caller-supplied data, `ctx`'s shape varies by pydantic version. Only
    loc/msg/type, the narrow FunnelIQ contract locked in
    app/schemas.py's HTTPValidationError."""
    detail = [
        ValidationErrorItem(loc=list(error["loc"]), msg=error["msg"], type=error["type"])
        for error in exc.errors()
    ]
    body = HTTPValidationError(detail=detail)
    return JSONResponse(status_code=422, content=body.model_dump())


@app.exception_handler(ResponseValidationError)
async def response_validation_exception_handler(
    request: Request, exc: ResponseValidationError
) -> JSONResponse:
    """500 -- a route handler returned data that failed its own
    response_model. This is our bug, not the caller's: never echo the
    validation errors (which would leak internal field names/values) back
    in the response body."""
    body = ErrorDetail(detail="Internal Server Error")
    return JSONResponse(status_code=500, content=body.model_dump())


@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    """500 -- the catch-all. No traceback, no exception class name, no
    file path, no input values in the body (D7) -- those belong in
    server-side logs, never in a response a caller can read."""
    body = ErrorDetail(detail="Internal Server Error")
    return JSONResponse(status_code=500, content=body.model_dump())


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


app.include_router(auth_router)
app.include_router(predict_router)
app.include_router(insights_router)

# Mounted last on purpose: StaticFiles on "/" swallows every path that isn't
# matched by a route registered before it -- see PHASE4.md decision D13.
STATIC_DIR = Path(__file__).resolve().parent / "static"
app.mount("/", StaticFiles(directory=STATIC_DIR, html=True), name="static")
