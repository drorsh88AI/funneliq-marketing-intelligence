"""Phase 9 -- per-request Supabase client, error classification, and
retry/timeout policy. See docs/planning/PHASE9.md D4/D16/D19.

A fresh client per request, carrying the caller's own JWT (D4) -- never a
cached client with a shared Authorization header. postgrest's headers
dict is shared mutable state on the client object; caching one across
requests under uvicorn's threadpool would leak one user's token into a
concurrent request from another user, silently defeating RLS.

D19: every table query app/insights.py builds (checkpoints 8-9) MUST end
its chain with `.retry(False)` before `.execute()` -- postgrest's own
built-in retry (GET/HEAD only, on 503/520, up to 3 attempts with
exponential backoff up to 30s each) would otherwise turn one transient
failure into up to ~7 seconds of blocking sleep in the request thread,
and status_for_supabase_error() below is written to classify ONE failed
call, not a retried sequence.
"""
from __future__ import annotations

import os
from collections.abc import Iterator

import httpx
from fastapi import Depends, HTTPException
from postgrest.exceptions import APIError
from supabase import Client, ClientOptions, create_client

from app.auth import access_token

# D19: no retry layer of our own (postgrest's own built-in retry --
# GET/HEAD only, on 503/520 -- is left alone, see app.supabase_client's
# docstring on _postgrest_retry_disabled below); a fixed request timeout
# instead. Phase 12 measures the real latency and tunes this.
POSTGREST_CLIENT_TIMEOUT_SECONDS = 10


def _build_client(token: str) -> Client:
    """D4's locked shape: publishable key + the caller's own JWT,
    auto_refresh_token/persist_session off (this is a stateless one-shot
    server-side client, not a browser session), a bounded timeout.
    Raises KeyError if SUPABASE_URL/SUPABASE_PUBLISHABLE_KEY are unset --
    the caller maps that to 500, same pattern as app.auth.get_supabase."""
    url = os.environ["SUPABASE_URL"]
    key = os.environ["SUPABASE_PUBLISHABLE_KEY"]
    options = ClientOptions(
        headers={"Authorization": f"Bearer {token}"},
        auto_refresh_token=False,
        persist_session=False,
        postgrest_client_timeout=POSTGREST_CLIENT_TIMEOUT_SECONDS,
    )
    return create_client(url, key, options=options)


def independent_purchased_count(client: Client) -> int:
    """IA.md §7.1: an independent count of `purchased = 1`, used to
    validate the paginated calls_to_closed distribution (checkpoint 9)
    against a SEPARATE source -- never against len(rows) from the same
    paginated fetch, which is circular and would let a silent truncation
    pass. `.range(0, 0)` returns at most one row (max_rows=1000 already
    bounds it further); only `response.count` is read. `.retry(False)`
    (D19) and deliberately not `head=True` -- a documented postgrest
    library bug (base_request_builder.py checks http_method == "HTTP",
    not "HEAD") means HEAD requests are never retried the same way GET
    is, which would make this call behave asymmetrically under a 503
    compared to every other query in this module."""
    response = (
        client.table("funnel_records")
        .select("source_row_id", count="exact")
        .eq("purchased", 1)
        .order("source_row_id")
        .range(0, 0)
        .retry(False)
        .execute()
    )
    return response.count


def get_user_client(token: str = Depends(access_token)) -> Iterator[Client]:
    """Yield-dependency (D4): one client for this request, carrying the
    caller's own JWT (never the service key -- that never reaches this
    process at all, D8). Closed in `finally` exactly once, whether the
    request succeeded or raised."""
    try:
        client = _build_client(token)
    except KeyError:
        raise HTTPException(status_code=500, detail="Supabase configuration missing")
    try:
        yield client
    finally:
        client.auth.close()
        client.postgrest.aclose()


# ---------------------------------------------------------------------------
# D16 -- error classification. Postgrest's APIError.code is `int` when the
# response body wasn't JSON (a bare HTTP status, e.g. a Cloudflare 503
# HTML page) and `str` when it IS a PostgREST/Postgres error body (e.g.
# "PGRST301", "42501"). The branch is chosen by TYPE ONLY, never by a
# digit-based heuristic: "42501".isdigit() is True, so a digit check
# would misroute that SQLSTATE into the numeric-HTTP branch and return
# 500 instead of 403 (verified empirically during planning -- this is
# the exact trap D16 documents).
# ---------------------------------------------------------------------------

_ERROR_DETAIL_401 = "Invalid or expired token"
_ERROR_DETAIL_403 = "Not authorized for this organization"
_ERROR_DETAIL_503 = "Service temporarily unavailable"
_ERROR_DETAIL_500 = "Internal Server Error"

_STR_CODE_401 = {"PGRST301", "PGRST302", "PGRST303"}
_STR_CODE_403 = {"42501"}
_STR_CODE_503 = {"PGRST000", "PGRST001", "PGRST002", "PGRST003"}
# PGRST205 (relation/view missing, HTTP 404) is deliberately NOT in
# _STR_CODE_503 -- a missing view is drift in our own deployment or a bug
# in our own migrations, never a caller-facing availability problem
# (D16). It falls through to the 500 default below, same as any other
# unrecognized code.


def status_for_supabase_error(exc: BaseException) -> tuple[int, str]:
    """Returns (status_code, detail) for any exception a Supabase/
    PostgREST call can raise. Route code wraps a query in try/except and
    does `raise HTTPException(*status_for_supabase_error(exc)) from exc`
    -- never lets the raw exception (or its message, which can carry
    upstream internals) propagate to app.main's generic handler, which
    would map everything to a blanket 500."""
    if isinstance(exc, APIError):
        code = exc.code
        if isinstance(code, int):
            if code == 401:
                return 401, _ERROR_DETAIL_401
            if code == 403:
                return 403, _ERROR_DETAIL_403
            if code == 408 or code == 429 or code >= 500:
                return 503, _ERROR_DETAIL_503
            return 500, _ERROR_DETAIL_500
        normalized = code.strip().upper()
        if normalized in _STR_CODE_401:
            return 401, _ERROR_DETAIL_401
        if normalized in _STR_CODE_403:
            return 403, _ERROR_DETAIL_403
        if normalized in _STR_CODE_503 or normalized.startswith("08") or normalized.startswith("53"):
            return 503, _ERROR_DETAIL_503
        return 500, _ERROR_DETAIL_500
    if isinstance(exc, httpx.TransportError):
        return 503, _ERROR_DETAIL_503
    return 500, _ERROR_DETAIL_500
