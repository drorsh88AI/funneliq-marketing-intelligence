"""Auth glue for FunnelIQ -- JWT verification against Supabase, plus the two
probes phase 4 needs: GET /api/config (public) and GET /api/me (protected).

Business endpoints (phase 9) reuse `current_user` as their own dependency,
and the new `access_token` dependency below (phase 9, D5/D6) for routes
that need the caller's own JWT to reach Supabase with (PHASE9.md D4).
See docs/planning/PHASE4.md, decisions D7-D10, and docs/planning/PHASE9.md
D5/D6, for the contract this implements.

Never touches SUPABASE_SECRET_KEY -- that key stays local to scripts/*.py and
never reaches this process (D8).
"""
from __future__ import annotations

import os
from functools import lru_cache

from fastapi import APIRouter, Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from supabase import Client, create_client
from supabase_auth.errors import AuthApiError, AuthInvalidJwtError, AuthRetryableError

router = APIRouter()

# PHASE9.md D6: a real FastAPI security scheme (not a bare Header param) so
# the OpenAPI schema this app emits carries `security` + `securitySchemes`
# and matches docs/api/openapi.json's projection (PHASE8.md D13).
# auto_error=False preserves today's behavior -- a missing/malformed header
# reaches access_token() below and gets our own worded 401, not FastAPI's.
#
# Two declared deltas from the pre-phase-9 Header(default=None) parameter
# (PHASE9.md D6, both covered by tests):
#   1. GET /api/me loses the 422 it carries today (a Header param counts
#      toward FastAPI's request-validation surface; a security dependency
#      does not).
#   2. The scheme match becomes case-insensitive ("bearer"/"BEARER" now
#      accepted) -- FastAPI's HTTPBearer lowercases before comparing;
#      the old code's `.startswith("Bearer ")` did not.
bearer = HTTPBearer(scheme_name="BearerAuth", auto_error=False)


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


def access_token(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer),
) -> str:
    """PHASE9.md D5: the base dependency every protected route (current_user
    included) builds on. Returns the raw bearer token string, or 401 if the
    header is missing or not a Bearer scheme -- `bearer`'s auto_error=False
    means both cases arrive here as `credentials is None`, so this is the
    single place that turns "no usable Authorization header" into 401.

    Exists as its own dependency (not inlined into current_user) so
    business routes that need to call Supabase WITH the caller's own JWT
    (PHASE9.md D4 -- a fresh client per request, `Authorization: Bearer
    <token>`) can depend on it directly, instead of re-deriving the token
    from current_user's return value. current_user's own return value
    stays exactly the three fields it always was (email/organization/role)
    -- the token itself is never added to it, so it never reaches
    GET /api/me's response body."""
    if credentials is None:
        raise HTTPException(status_code=401, detail="Missing or invalid Authorization header")
    return credentials.credentials


def current_user(token: str = Depends(access_token)) -> dict:
    """Dependency for every protected endpoint.

    401 -- no/invalid/expired token. 403 -- valid token, wrong (or missing)
    organization. 500/503 -- our own config or Supabase's own infrastructure,
    never reported as if the caller's credentials were the problem (D7א).
    `organization` is read from app_metadata only -- never user_metadata,
    which the end user can edit themselves.
    """
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
