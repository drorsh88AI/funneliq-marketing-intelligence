"""Auth glue for FunnelIQ -- JWT verification against Supabase, plus the two
probes phase 4 needs: GET /api/config (public) and GET /api/me (protected).

Business endpoints (phase 9) reuse `current_user` as their own dependency.
See docs/planning/PHASE4.md, decisions D7-D10, for the contract this implements.

Never touches SUPABASE_SECRET_KEY -- that key stays local to scripts/*.py and
never reaches this process (D8).
"""
from __future__ import annotations

import os
from functools import lru_cache

from fastapi import APIRouter, Depends, Header, HTTPException
from supabase import Client, create_client
from supabase_auth.errors import AuthApiError, AuthInvalidJwtError, AuthRetryableError

router = APIRouter()


@lru_cache(maxsize=1)
def get_supabase() -> Client:
    """Build the Supabase client from env -- publishable key only, never secret.

    Cached so a request doesn't rebuild a client every time. Tests replace
    this function wholesale with monkeypatch.setattr(auth, "get_supabase",
    ...), so the cache never leaks between test cases.
    """
    url = os.environ["SUPABASE_URL"]
    key = os.environ["SUPABASE_PUBLISHABLE_KEY"]
    return create_client(url, key)


@router.get("/api/config")
def get_config() -> dict[str, str]:
    """Public. Lets the browser init supabase-js before any token exists.

    Exactly two fields, never the secret key. Fails noisy (500) if env is
    missing -- a login that breaks silently is the worse failure mode.
    """
    url = os.environ.get("SUPABASE_URL")
    key = os.environ.get("SUPABASE_PUBLISHABLE_KEY")
    if not url or not key:
        raise HTTPException(status_code=500, detail="Supabase configuration missing")
    return {"supabase_url": url, "supabase_publishable_key": key}


def current_user(authorization: str | None = Header(default=None)) -> dict:
    """Dependency for every protected endpoint.

    401 -- no/invalid/expired token. 403 -- valid token, wrong (or missing)
    organization. 500/503 -- our own config or Supabase's own infrastructure,
    never reported as if the caller's credentials were the problem (D7א).
    `organization` is read from app_metadata only -- never user_metadata,
    which the end user can edit themselves.
    """
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing or invalid Authorization header")
    token = authorization.removeprefix("Bearer ").strip()

    # Outside the auth try/except on purpose -- a missing env var is our
    # config bug, not a bad token (D7א row 1).
    try:
        client = get_supabase()
    except KeyError:
        raise HTTPException(status_code=500, detail="Supabase configuration missing")

    try:
        response = client.auth.get_user(token)
    except AuthRetryableError:
        # Network/timeout/upstream 5xx -- Supabase's infrastructure, not the token.
        raise HTTPException(status_code=503, detail="Auth service temporarily unavailable")
    except AuthApiError as e:
        if e.status >= 500:
            raise HTTPException(status_code=503, detail="Auth service temporarily unavailable")
        raise HTTPException(status_code=401, detail="Invalid or expired token")
    except AuthInvalidJwtError:
        raise HTTPException(status_code=401, detail="Invalid or expired token")

    user = getattr(response, "user", None)
    if user is None:
        raise HTTPException(status_code=401, detail="Invalid or expired token")

    app_metadata = user.app_metadata or {}
    if app_metadata.get("organization") != "northbound":
        raise HTTPException(status_code=403, detail="Not authorized for this organization")

    return {
        "email": user.email,
        "organization": app_metadata.get("organization"),
        "role": app_metadata.get("role"),
    }


@router.get("/api/me")
def get_me(user: dict = Depends(current_user)) -> dict:
    return user
