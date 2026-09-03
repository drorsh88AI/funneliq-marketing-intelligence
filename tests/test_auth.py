"""Local-only tests for the current_user dependency and GET /api/me.

No network, no real Supabase project -- app.auth.get_supabase is replaced
with a fake client via monkeypatch for every test that needs one. Exception
types (AuthApiError, AuthRetryableError, AuthInvalidJwtError) are the real
classes from supabase_auth.errors, not stand-ins -- so the error-mapping
table in current_user is exercised against the actual types it's written to
catch. See docs/planning/PHASE4.md, decision D7א, and section ה (E-local).
"""
from __future__ import annotations

from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient
from supabase_auth.errors import AuthApiError, AuthInvalidJwtError, AuthRetryableError

from app import auth
from app.main import app

client = TestClient(app)


class _FakeAuth:
    """Stands in for supabase_client.auth.get_user(token)."""

    def __init__(self, user=None, exc=None):
        self._user = user
        self._exc = exc

    def get_user(self, token):
        if self._exc is not None:
            raise self._exc
        return SimpleNamespace(user=self._user)


class _FakeClient:
    def __init__(self, user=None, exc=None):
        self.auth = _FakeAuth(user=user, exc=exc)


def _user(app_metadata):
    return SimpleNamespace(email="demo@funneliq.example.com", app_metadata=app_metadata)


def test_me_without_authorization_header_is_401():
    response = client.get("/api/me")
    assert response.status_code == 401


def test_me_with_non_bearer_header_is_401():
    response = client.get("/api/me", headers={"Authorization": "Basic xyz"})
    assert response.status_code == 401


def test_me_missing_env_is_500_not_401(monkeypatch):
    """D7א row 1: a config bug is our fault, not the caller's -- must not
    look like an auth failure."""

    def _raise_key_error():
        raise KeyError("SUPABASE_URL")

    monkeypatch.setattr(auth, "get_supabase", _raise_key_error)
    response = client.get("/api/me", headers={"Authorization": "Bearer whatever"})
    assert response.status_code == 500


def test_me_when_token_rejected_is_401(monkeypatch):
    """D7א row 2: GoTrue actively rejected the token."""
    exc = AuthApiError("invalid token", status=401, code="bad_jwt")
    monkeypatch.setattr(auth, "get_supabase", lambda: _FakeClient(exc=exc))
    response = client.get("/api/me", headers={"Authorization": "Bearer whatever"})
    assert response.status_code == 401


def test_me_when_jwt_malformed_is_401(monkeypatch):
    """D7א row 3: malformed JWT rejected client-side before any request."""
    monkeypatch.setattr(
        auth, "get_supabase", lambda: _FakeClient(exc=AuthInvalidJwtError("bad jwt"))
    )
    response = client.get("/api/me", headers={"Authorization": "Bearer whatever"})
    assert response.status_code == 401


def test_me_when_gotrue_5xx_is_503_not_401(monkeypatch):
    """D7א row 4: GoTrue's own infrastructure failed -- not a bad token."""
    exc = AuthApiError("internal error", status=500, code=None)
    monkeypatch.setattr(auth, "get_supabase", lambda: _FakeClient(exc=exc))
    response = client.get("/api/me", headers={"Authorization": "Bearer whatever"})
    assert response.status_code == 503


def test_me_when_network_retryable_is_503_not_401(monkeypatch):
    """D7א row 5: connection/timeout error -- must not be mapped to 401."""
    exc = AuthRetryableError("connection failed", status=0)
    monkeypatch.setattr(auth, "get_supabase", lambda: _FakeClient(exc=exc))
    response = client.get("/api/me", headers={"Authorization": "Bearer whatever"})
    assert response.status_code == 503


def test_me_when_unexpected_error_propagates_not_swallowed(monkeypatch):
    """D7א row 6: an exception outside the known auth taxonomy must not be
    silently reported as 401 -- that would hide a real bug behind a
    plausible-looking auth failure."""
    monkeypatch.setattr(auth, "get_supabase", lambda: _FakeClient(exc=RuntimeError("boom")))
    with pytest.raises(RuntimeError):
        client.get("/api/me", headers={"Authorization": "Bearer whatever"})


def test_me_when_get_user_returns_no_user_is_401(monkeypatch):
    monkeypatch.setattr(auth, "get_supabase", lambda: _FakeClient(user=None))
    response = client.get("/api/me", headers={"Authorization": "Bearer whatever"})
    assert response.status_code == 401


def test_me_without_organization_claim_is_403(monkeypatch):
    monkeypatch.setattr(
        auth, "get_supabase", lambda: _FakeClient(user=_user({"role": "team_member"}))
    )
    response = client.get("/api/me", headers={"Authorization": "Bearer whatever"})
    assert response.status_code == 403


def test_me_organization_in_user_metadata_only_is_still_403(monkeypatch):
    """Regression: organization must be read from app_metadata, never
    user_metadata, which the end user can edit -- SPEC.md (Auth)."""
    fake_user = SimpleNamespace(
        email="demo@funneliq.example.com",
        app_metadata={"role": "team_member"},
        user_metadata={"organization": "northbound"},
    )
    monkeypatch.setattr(auth, "get_supabase", lambda: _FakeClient(user=fake_user))
    response = client.get("/api/me", headers={"Authorization": "Bearer whatever"})
    assert response.status_code == 403


def test_me_with_northbound_organization_is_200(monkeypatch):
    monkeypatch.setattr(
        auth,
        "get_supabase",
        lambda: _FakeClient(
            user=_user({"organization": "northbound", "role": "team_member"})
        ),
    )
    response = client.get("/api/me", headers={"Authorization": "Bearer whatever"})
    assert response.status_code == 200
    assert response.json() == {
        "email": "demo@funneliq.example.com",
        "organization": "northbound",
        "role": "team_member",
    }
