"""Shared fixtures for phase 9's business-route tests. Generalizes the
fake-Supabase-auth pattern tests/test_auth.py established per-test, since
every predict/insights route test needs an authenticated client.
"""
from __future__ import annotations

from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from app import auth
from app.main import app


class _FakeAuth:
    def __init__(self, user):
        self._user = user

    def get_user(self, token):
        return SimpleNamespace(user=self._user)


class _FakeSupabaseClient:
    def __init__(self, user):
        self.auth = _FakeAuth(user)


@pytest.fixture
def make_authed_client(monkeypatch):
    """Factory: make_authed_client() -> a TestClient that sends
    "Authorization: Bearer whatever" on every request and whose
    current_user dependency accepts it as a valid northbound team member.
    make_authed_client(organization="other") builds a client whose token
    is "valid" but wrong-org (403), for permission tests."""

    def _make(*, organization: str | None = "northbound", role: str = "team_member") -> TestClient:
        user = SimpleNamespace(
            email="demo@funneliq.example.com",
            app_metadata={"organization": organization, "role": role},
        )
        monkeypatch.setattr(auth, "get_supabase", lambda: _FakeSupabaseClient(user))
        return TestClient(app, headers={"Authorization": "Bearer whatever"})

    return _make


@pytest.fixture
def authed_client(make_authed_client) -> TestClient:
    return make_authed_client()


# In-domain for P2/P3/P4's shared 13-field FunnelInput and every task's
# ood_bounds (PHASE9.md מצב מאומת 16/46) -- ad_budget=2000 is an observed
# training level.
FUNNEL_INPUT_IN_DOMAIN = {
    "ad_budget": 2000, "num_leads": 50, "leads_answered": 40,
    "followup_1": 30, "followup_2": 25, "followup_3": 20, "followup_4": 15,
    "followup_5": 10, "not_closed": 6, "closed": 4, "calls_to_closed": 3,
    "calls_to_not_closed": 2, "customer_acquisition_cost": 500,
}

EARLY_FUNNEL_INPUT_IN_DOMAIN = {
    "ad_budget": 2000, "num_leads": 50, "leads_answered": 40, "followup_1": 30,
}
