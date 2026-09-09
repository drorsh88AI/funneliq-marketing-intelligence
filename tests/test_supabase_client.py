"""Tests for app/supabase_client.py (PHASE9.md checkpoint 7, D4/D16/D19).
Client lifecycle, the two-branch D16 error classifier, and the
independent-count query's exact shape -- criteria 18-22, 62-69.
"""
from __future__ import annotations

import re
from pathlib import Path

import httpx
import pytest
from postgrest.exceptions import APIError
from supabase import ClientOptions, create_client

from app import supabase_client as sc

REPO_ROOT = Path(__file__).resolve().parent.parent


def _mock_client(handler):
    """A real supabase Client wired to an httpx.MockTransport, so query
    chains actually build and send a request -- not a stand-in."""
    transport_client = httpx.Client(transport=httpx.MockTransport(handler))
    options = ClientOptions(headers={"Authorization": "Bearer tok"}, httpx_client=transport_client)
    return create_client("https://example.supabase.co", "sb_publishable_dummy", options=options)


# ---------------------------------------------------------------------------
# Criteria 18-19 -- D16's two-branch classifier, parametrized.
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "code,expected_status",
    [
        ("PGRST301", 401), ("PGRST302", 401), ("PGRST303", 401),
        ("42501", 403),  # the isdigit() trap -- a str "42501" must NOT hit the int branch
        ("08006", 503), ("53300", 503),
        ("PGRST000", 503), ("PGRST001", 503), ("PGRST002", 503), ("PGRST003", 503),
        ("PGRST205", 500),  # relation/view missing -- our drift, not a caller's availability problem
        ("some_unknown_code", 500),
    ],
)
def test_str_code_classification(code, expected_status):
    exc = APIError({"message": "x", "code": code, "hint": None, "details": None})
    status, _detail = sc.status_for_supabase_error(exc)
    assert status == expected_status


@pytest.mark.parametrize(
    "code,expected_status",
    [
        (401, 401), (403, 403),
        (408, 503), (429, 503),
        (500, 503), (502, 503), (503, 503), (504, 503), (520, 503),
        (404, 500),  # not one of our recognized codes
    ],
)
def test_int_code_classification(code, expected_status):
    exc = APIError({"message": "x", "code": code, "hint": None, "details": None})
    status, _detail = sc.status_for_supabase_error(exc)
    assert status == expected_status


def test_str_code_is_never_routed_by_isdigit():
    """Direct regression: the classifier must key off type(code) is int,
    never a digit-based heuristic. "42501" is entirely numeric characters
    but must classify via the string branch (403), not the int branch."""
    exc = APIError({"message": "x", "code": "42501", "hint": None, "details": None})
    status, _detail = sc.status_for_supabase_error(exc)
    assert status == 403, "a digit-based classifier would wrongly return 500 here"


def test_transport_error_maps_to_503():
    exc = httpx.ConnectError("connection refused")
    status, _detail = sc.status_for_supabase_error(exc)
    assert status == 503


def test_unrecognized_exception_maps_to_500():
    status, _detail = sc.status_for_supabase_error(RuntimeError("something else"))
    assert status == 500


# ---------------------------------------------------------------------------
# Criteria 20-22 -- .retry(False) means ONE call, not up to postgrest's
# own MAX_RETRIES=3 (i.e. up to 4 attempts).
# ---------------------------------------------------------------------------


def test_503_response_is_a_single_call():
    calls = []

    def handler(request):
        calls.append(1)
        return httpx.Response(503, text="<html>gateway error</html>")

    client = _mock_client(handler)
    with pytest.raises(APIError):
        sc.independent_purchased_count(client)
    assert len(calls) == 1


def test_520_response_is_a_single_call():
    calls = []

    def handler(request):
        calls.append(1)
        return httpx.Response(520, text="<html>unknown error</html>")

    client = _mock_client(handler)
    with pytest.raises(APIError):
        sc.independent_purchased_count(client)
    assert len(calls) == 1


def test_transport_error_is_a_single_call():
    calls = []

    def handler(request):
        calls.append(1)
        raise httpx.ConnectError("simulated network failure")

    client = _mock_client(handler)
    with pytest.raises(httpx.ConnectError):
        sc.independent_purchased_count(client)
    assert len(calls) == 1


# ---------------------------------------------------------------------------
# Criterion 62 -- ClientOptions carries the locked D4 settings.
# ---------------------------------------------------------------------------


def test_build_client_sets_the_locked_options(monkeypatch):
    monkeypatch.setenv("SUPABASE_URL", "https://example.supabase.co")
    monkeypatch.setenv("SUPABASE_PUBLISHABLE_KEY", "sb_publishable_dummy")
    client = sc._build_client("some-jwt")
    assert client.options.auto_refresh_token is False
    assert client.options.persist_session is False
    assert client.options.postgrest_client_timeout == sc.POSTGREST_CLIENT_TIMEOUT_SECONDS
    assert client.options.headers["Authorization"] == "Bearer some-jwt"


# ---------------------------------------------------------------------------
# Criterion 63 -- a separate client per call, never shared/cached.
# ---------------------------------------------------------------------------


def test_build_client_is_never_cached(monkeypatch):
    monkeypatch.setenv("SUPABASE_URL", "https://example.supabase.co")
    monkeypatch.setenv("SUPABASE_PUBLISHABLE_KEY", "sb_publishable_dummy")
    client_a = sc._build_client("token-a")
    client_b = sc._build_client("token-b")
    assert client_a is not client_b
    assert client_a.options.headers["Authorization"] == "Bearer token-a"
    assert client_b.options.headers["Authorization"] == "Bearer token-b"


# ---------------------------------------------------------------------------
# Criterion 64 -- auth.close()/postgrest.aclose() called exactly once,
# in both the success and the failure path through the yield-dependency.
# ---------------------------------------------------------------------------


def test_get_user_client_closes_exactly_once_on_success(monkeypatch):
    monkeypatch.setenv("SUPABASE_URL", "https://example.supabase.co")
    monkeypatch.setenv("SUPABASE_PUBLISHABLE_KEY", "sb_publishable_dummy")

    gen = sc.get_user_client("some-jwt")
    client = next(gen)

    auth_calls = []
    postgrest_calls = []
    monkeypatch.setattr(client.auth, "close", lambda: auth_calls.append(1))
    monkeypatch.setattr(client.postgrest, "aclose", lambda: postgrest_calls.append(1))

    with pytest.raises(StopIteration):
        next(gen)  # drives the generator past `yield`, running the `finally`

    assert auth_calls == [1]
    assert postgrest_calls == [1]


def test_get_user_client_closes_exactly_once_on_failure(monkeypatch):
    monkeypatch.setenv("SUPABASE_URL", "https://example.supabase.co")
    monkeypatch.setenv("SUPABASE_PUBLISHABLE_KEY", "sb_publishable_dummy")

    gen = sc.get_user_client("some-jwt")
    client = next(gen)

    auth_calls = []
    postgrest_calls = []
    monkeypatch.setattr(client.auth, "close", lambda: auth_calls.append(1))
    monkeypatch.setattr(client.postgrest, "aclose", lambda: postgrest_calls.append(1))

    with pytest.raises(RuntimeError, match="simulated route failure"):
        gen.throw(RuntimeError("simulated route failure"))

    assert auth_calls == [1]
    assert postgrest_calls == [1]


def test_get_user_client_missing_config_is_500(monkeypatch):
    monkeypatch.delenv("SUPABASE_URL", raising=False)
    monkeypatch.delenv("SUPABASE_PUBLISHABLE_KEY", raising=False)

    from fastapi import HTTPException

    gen = sc.get_user_client("some-jwt")
    with pytest.raises(HTTPException) as exc_info:
        next(gen)
    assert exc_info.value.status_code == 500


# ---------------------------------------------------------------------------
# Criteria 65-66 -- the JWT actually reaches the wire; two clients never
# share a header.
# ---------------------------------------------------------------------------


def test_the_actual_jwt_reaches_the_request_header():
    seen_headers = []

    def handler(request):
        seen_headers.append(request.headers.get("authorization"))
        return httpx.Response(200, json=[], headers={"content-range": "*/0"})

    options = ClientOptions(
        headers={"Authorization": "Bearer real-user-jwt"},
        httpx_client=httpx.Client(transport=httpx.MockTransport(handler)),
    )
    client = create_client("https://example.supabase.co", "sb_publishable_dummy", options=options)
    client.table("funnel_records").select("source_row_id").retry(False).execute()
    assert seen_headers == ["Bearer real-user-jwt"]


def test_two_concurrent_style_clients_never_cross_contaminate_tokens():
    seen = {}

    def make_client(user_label, token):
        def handler(request):
            seen.setdefault(user_label, []).append(request.headers.get("authorization"))
            return httpx.Response(200, json=[], headers={"content-range": "*/0"})

        options = ClientOptions(
            headers={"Authorization": f"Bearer {token}"},
            httpx_client=httpx.Client(transport=httpx.MockTransport(handler)),
        )
        return create_client("https://example.supabase.co", "sb_publishable_dummy", options=options)

    client_a = make_client("A", "token-A")
    client_b = make_client("B", "token-B")
    client_a.table("funnel_records").select("source_row_id").retry(False).execute()
    client_b.table("funnel_records").select("source_row_id").retry(False).execute()

    assert seen["A"] == ["Bearer token-A"]
    assert seen["B"] == ["Bearer token-B"]


# ---------------------------------------------------------------------------
# Criterion 67 -- SUPABASE_SECRET_KEY never appears in app/.
# ---------------------------------------------------------------------------


_SECRET_KEY_USAGE_PATTERN = re.compile(
    r'os\.environ(\[|\.get\()\s*["\']SUPABASE_SECRET_KEY["\']|os\.getenv\(\s*["\']SUPABASE_SECRET_KEY["\']'
)


def test_secret_key_is_never_read_in_app_source():
    """The mention in app/auth.py's docstring ("Never touches
    SUPABASE_SECRET_KEY -- that key stays local to scripts/*.py", D8) is
    legitimate documentation of the constraint, not a violation of it --
    this checks for actual runtime env-var ACCESS patterns
    (os.environ[...]/os.environ.get(...)/os.getenv(...)), not the bare
    string appearing anywhere at all."""
    app_dir = REPO_ROOT / "app"
    offenders = []
    for path in app_dir.rglob("*.py"):
        if _SECRET_KEY_USAGE_PATTERN.search(path.read_text(encoding="utf-8")):
            offenders.append(str(path))
    assert offenders == [], f"SUPABASE_SECRET_KEY must never be read in app/: {offenders}"


# ---------------------------------------------------------------------------
# Criteria 68-69 -- the independent count query's exact shape.
# ---------------------------------------------------------------------------


def test_independent_count_query_shape_and_retry_disabled():
    captured = {}

    def handler(request):
        captured["url"] = str(request.url)
        captured["method"] = request.method
        return httpx.Response(200, json=[{"source_row_id": 1}], headers={"content-range": "0-0/3163"})

    client = _mock_client(handler)
    count = sc.independent_purchased_count(client)

    assert count == 3163
    assert captured["method"] == "GET"
    assert "purchased=eq.1" in captured["url"]
    assert "select=source_row_id" in captured["url"]
    assert "order=source_row_id.asc" in captured["url"]
    assert re.search(r"[?&]limit=1(&|$)", captured["url"])
    assert "head=" not in captured["url"].lower()


def test_independent_count_query_returns_at_most_one_row():
    def handler(request):
        return httpx.Response(200, json=[{"source_row_id": 1}], headers={"content-range": "0-0/3163"})

    client = _mock_client(handler)
    # The count comes from response.count (parsed from Content-Range),
    # not from len(data) -- but the request itself must still be bounded
    # to at most one row via .range(0, 0), verified by inspecting the
    # limit= query param above. This test locks the return value's
    # source explicitly.
    count = sc.independent_purchased_count(client)
    assert count == 3163
