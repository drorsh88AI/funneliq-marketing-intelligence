"""Local-only tests for GET /api/config.

No network, no real credentials -- env vars are set/cleared per test via
monkeypatch, which overrides whatever app.main's module-level load_dotenv()
already populated from the local .env. See docs/planning/PHASE4.md (test matrix) cases 2-4.
"""
from __future__ import annotations

from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_config_returns_exactly_two_fields(monkeypatch):
    monkeypatch.setenv("SUPABASE_URL", "https://example.supabase.co")
    monkeypatch.setenv("SUPABASE_PUBLISHABLE_KEY", "sb_publishable_test123")

    response = client.get("/api/config")

    assert response.status_code == 200
    body = response.json()
    assert set(body.keys()) == {"supabase_url", "supabase_publishable_key"}


def test_config_never_leaks_secret_key(monkeypatch):
    monkeypatch.setenv("SUPABASE_URL", "https://example.supabase.co")
    monkeypatch.setenv("SUPABASE_PUBLISHABLE_KEY", "sb_publishable_test123")
    monkeypatch.setenv("SUPABASE_SECRET_KEY", "sb_secret_should_never_appear")

    response = client.get("/api/config")

    assert response.status_code == 200
    assert response.json()["supabase_publishable_key"].startswith("sb_publishable_")
    assert "sb_secret" not in response.text


def test_config_missing_env_fails_noisy_not_silent(monkeypatch):
    monkeypatch.delenv("SUPABASE_URL", raising=False)
    monkeypatch.delenv("SUPABASE_PUBLISHABLE_KEY", raising=False)

    response = client.get("/api/config")

    assert response.status_code == 500
