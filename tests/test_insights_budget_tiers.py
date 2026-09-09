"""Tests for GET /api/insights/budget-tiers (PHASE9.md checkpoint 8,
D12/D15/PHASE8.md D11). Criterion 71 plus permissions and error mapping.

⚠ Criterion 72 (live evidence against a deployed Render URL with
demo-northbound/demo-noorg) is NOT covered here -- it requires an actual
deployment, gated behind checkpoint 11's push/PR/deploy approval per
PHASE9.md's own "עצירות מחייבות". These tests cover everything
verifiable against a mocked Supabase transport.
"""
from __future__ import annotations

import httpx
import pytest
from supabase import ClientOptions, create_client

from app.main import app
from app.supabase_client import get_user_client

PATH = "/api/insights/budget-tiers"


def _override_with(handler):
    def _make_client() -> ClientOptions:
        options = ClientOptions(
            headers={"Authorization": "Bearer tok"},
            httpx_client=httpx.Client(transport=httpx.MockTransport(handler)),
        )
        return create_client("https://example.supabase.co", "sb_publishable_dummy", options=options)

    def override():
        yield _make_client()

    return override


@pytest.fixture(autouse=True)
def _clear_overrides():
    yield
    app.dependency_overrides.pop(get_user_client, None)


def test_requires_auth():
    from fastapi.testclient import TestClient

    client = TestClient(app)
    response = client.get(PATH)
    assert response.status_code == 401


def test_rejects_wrong_organization(make_authed_client):
    client = make_authed_client(organization="other")
    response = client.get(PATH)
    assert response.status_code == 403


# ---------------------------------------------------------------------------
# Criterion 71 -- sorting, empty-rows-is-200, and .order not relied upon.
# ---------------------------------------------------------------------------


_REAL_TIERS = [
    {"tier_order": 3, "budget_tier": "High", "n_records": 1003, "conversion_rate": 0.0543},
    {"tier_order": 1, "budget_tier": "Low", "n_records": 780, "conversion_rate": 0.0452},
    {"tier_order": None, "budget_tier": None, "n_records": 5, "conversion_rate": None},
    {"tier_order": 2, "budget_tier": "Mid", "n_records": 1717, "conversion_rate": 0.0822},
]


def test_shuffled_rows_are_sorted_tier_order_ascending_null_last(authed_client):
    def handler(request):
        return httpx.Response(200, json=_REAL_TIERS, headers={"content-range": "0-3/4"})

    app.dependency_overrides[get_user_client] = _override_with(handler)
    response = authed_client.get(PATH)
    body = response.json()

    assert response.status_code == 200
    orders = [t["tier_order"] for t in body["tiers"]]
    assert orders == [1, 2, 3, None]


def test_zero_rows_is_200_with_empty_tiers_list(authed_client):
    def handler(request):
        return httpx.Response(200, json=[], headers={"content-range": "*/0"})

    app.dependency_overrides[get_user_client] = _override_with(handler)
    response = authed_client.get(PATH)
    assert response.status_code == 200
    assert response.json() == {"tiers": []}


def test_no_order_by_relied_on_from_the_view_itself(authed_client):
    """budget_tier_insight has no ORDER BY (verified against the
    migration during planning) -- the route must sort itself, not assume
    postgrest returns rows in any particular order. This test feeds rows
    in reverse of the expected output order to prove the route's own
    sort, not the mock's incidental ordering, produces the result."""
    reversed_rows = list(reversed(_REAL_TIERS))

    def handler(request):
        return httpx.Response(200, json=reversed_rows, headers={"content-range": "0-3/4"})

    app.dependency_overrides[get_user_client] = _override_with(handler)
    response = authed_client.get(PATH)
    orders = [t["tier_order"] for t in response.json()["tiers"]]
    assert orders == [1, 2, 3, None]


def test_full_response_matches_known_dataset_values(authed_client):
    """IA.md §2's documented values: Low 780/4.5%, Mid 1717/8.2%, High
    1003/5.4%."""
    rows = [
        {"tier_order": 1, "budget_tier": "Low", "n_records": 780, "conversion_rate": 0.04524},
        {"tier_order": 2, "budget_tier": "Mid", "n_records": 1717, "conversion_rate": 0.08220},
        {"tier_order": 3, "budget_tier": "High", "n_records": 1003, "conversion_rate": 0.05433},
    ]

    def handler(request):
        return httpx.Response(200, json=rows, headers={"content-range": "0-2/3"})

    app.dependency_overrides[get_user_client] = _override_with(handler)
    response = authed_client.get(PATH)
    body = response.json()
    assert response.status_code == 200
    assert body["tiers"] == rows


# ---------------------------------------------------------------------------
# Error mapping (D16) exercised through this route -- one representative
# case per family; the exhaustive classification matrix is
# tests/test_supabase_client.py's job.
# ---------------------------------------------------------------------------


def test_upstream_503_maps_to_503(authed_client):
    def handler(request):
        return httpx.Response(503, text="<html>gateway</html>")

    app.dependency_overrides[get_user_client] = _override_with(handler)
    response = authed_client.get(PATH)
    assert response.status_code == 503
    assert response.json() == {"detail": "Service temporarily unavailable"}


def test_expired_jwt_maps_to_401(authed_client):
    def handler(request):
        return httpx.Response(
            401, json={"message": "JWT expired", "code": "PGRST301", "hint": None, "details": None}
        )

    app.dependency_overrides[get_user_client] = _override_with(handler)
    response = authed_client.get(PATH)
    assert response.status_code == 401
    assert response.json() == {"detail": "Invalid or expired token"}


def test_insufficient_privilege_maps_to_403(authed_client):
    def handler(request):
        return httpx.Response(
            403, json={"message": "permission denied", "code": "42501", "hint": None, "details": None}
        )

    app.dependency_overrides[get_user_client] = _override_with(handler)
    response = authed_client.get(PATH)
    assert response.status_code == 403
    assert response.json() == {"detail": "Not authorized for this organization"}
