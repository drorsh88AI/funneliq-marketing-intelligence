"""Tests for app/main.py's lifespan wiring (PHASE9.md D2, checkpoint 3).

TestClient(app) without a `with` block does NOT run FastAPI's lifespan
(verified empirically during planning) -- this project's existing tests
(tests/test_health.py, tests/test_auth.py) rely on that fact and never use
the context-manager form. These tests exercise the lifespan function
directly (no event loop plumbing needed beyond bare asyncio.run) plus one
end-to-end check that `with TestClient(app) as client:` really does run it
against the real assets.
"""
from __future__ import annotations

import asyncio

import pytest
from fastapi.testclient import TestClient

from app import artifacts, main


def test_lifespan_calls_get_assets(monkeypatch):
    calls = {"n": 0}

    def counting():
        calls["n"] += 1
        return {"fake": True}

    monkeypatch.setattr(main, "get_assets", counting)

    async def run():
        async with main.lifespan(main.app):
            pass

    asyncio.run(run())
    assert calls["n"] == 1


def test_lifespan_propagates_asset_startup_failure(monkeypatch):
    """The wiring must not swallow ArtifactStartupError -- a broken asset
    has to abort startup, not get logged-and-ignored."""

    def boom():
        raise artifacts.ArtifactStartupError("simulated broken asset")

    monkeypatch.setattr(main, "get_assets", boom)

    async def run():
        async with main.lifespan(main.app):
            pass

    with pytest.raises(artifacts.ArtifactStartupError, match="simulated broken asset"):
        asyncio.run(run())


def test_testclient_context_manager_runs_lifespan_against_real_assets():
    """End-to-end: the real app, the real models/ directory, driven
    through the context-manager form that actually triggers lifespan --
    proves the wiring works outside of mocks too, and that /health still
    responds normally once it has."""
    artifacts.reset_assets_cache_for_tests()
    with TestClient(main.app) as client:
        response = client.get("/health")
        assert response.status_code == 200
    artifacts.reset_assets_cache_for_tests()
