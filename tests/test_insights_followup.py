"""Tests for GET /api/insights/followup (PHASE9.md checkpoint 9, D12):
priority ordering (auth beats partial data), pagination, the independent
count check, and per-part failure classification. Criteria 20-26, 70, 73.

⚠ Criterion 73 (live evidence against a deployed Render URL) is NOT
covered here -- see tests/test_insights_budget_tiers.py's module
docstring for why.
"""
from __future__ import annotations

import httpx
import pytest
from supabase import ClientOptions, create_client

from app.main import app
from app.supabase_client import get_user_client

PATH = "/api/insights/followup"
TOTAL_PURCHASED = 3163

STAGES_ROWS = [
    {"stage_order": 1, "stage": "followup_1", "from_leads": 100, "to_leads": 78, "drop_rate": 0.22},
    {"stage_order": 2, "stage": "followup_2", "from_leads": 78, "to_leads": 58, "drop_rate": 0.2564102564102564},
    {"stage_order": 3, "stage": "followup_3", "from_leads": 58, "to_leads": 47, "drop_rate": 0.1896551724137931},
    {"stage_order": 4, "stage": "followup_4", "from_leads": 47, "to_leads": 42, "drop_rate": 0.10638297872340426},
    {"stage_order": 5, "stage": "followup_5", "from_leads": 42, "to_leads": 30, "drop_rate": 0.2857142857142857},
]


def _funnel_records_page(offset: int, total: int = TOTAL_PURCHASED) -> httpx.Response:
    page = min(1000, max(0, total - offset))
    data = [{"calls_to_closed": (offset + i) % 9 + 1} for i in range(page)]
    return httpx.Response(200, json=data, headers={"content-range": f"{offset}-{offset + page - 1}/{total}"})


def _make_handler(*, stages_response, funnel_records_total=TOTAL_PURCHASED, independent_count=None):
    """stages_response: an httpx.Response, or a callable(request) -> Response.
    independent_count defaults to funnel_records_total (i.e. no mismatch)."""
    count = funnel_records_total if independent_count is None else independent_count

    def handler(request):
        url = str(request.url)
        if "followup_insight" in url:
            return stages_response(request) if callable(stages_response) else stages_response
        if "funnel_records" in url:
            if "limit=1" in url and "select=source_row_id" in url:
                return httpx.Response(200, json=[{"source_row_id": 1}], headers={"content-range": f"0-0/{count}"})
            offset = int(dict(p.split("=") for p in url.split("?")[1].split("&"))["offset"])
            return _funnel_records_page(offset, total=funnel_records_total)
        raise AssertionError(f"unexpected URL: {url}")

    return handler


def _override(handler):
    def _make():
        options = ClientOptions(
            headers={"Authorization": "Bearer tok"},
            httpx_client=httpx.Client(transport=httpx.MockTransport(handler)),
        )
        yield create_client("https://example.supabase.co", "sb_publishable_dummy", options=options)

    return _make


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
# Happy path -- both parts available, full pagination, real numbers.
# ---------------------------------------------------------------------------


def test_happy_path_both_parts_available(authed_client):
    handler = _make_handler(stages_response=httpx.Response(200, json=STAGES_ROWS, headers={"content-range": "0-4/5"}))
    app.dependency_overrides[get_user_client] = _override(handler)

    response = authed_client.get(PATH)
    body = response.json()

    assert response.status_code == 200
    assert body["stages"]["status"] == "available"
    assert [s["stage_order"] for s in body["stages"]["data"]] == [1, 2, 3, 4, 5]
    assert body["calls_to_closed"]["status"] == "available"
    assert body["calls_to_closed"]["data"]["population_n"] == TOTAL_PURCHASED
    assert sum(b["n"] for b in body["calls_to_closed"]["data"]["distribution"]) == TOTAL_PURCHASED


def test_stages_are_sorted_even_when_returned_shuffled(authed_client):
    shuffled = list(reversed(STAGES_ROWS))
    handler = _make_handler(stages_response=httpx.Response(200, json=shuffled, headers={"content-range": "0-4/5"}))
    app.dependency_overrides[get_user_client] = _override(handler)

    response = authed_client.get(PATH)
    body = response.json()
    assert [s["stage_order"] for s in body["stages"]["data"]] == [1, 2, 3, 4, 5]


# ---------------------------------------------------------------------------
# Criteria 23-24 -- auth priority: 401 beats 403 beats unavailable/503.
# ---------------------------------------------------------------------------


def test_auth_failure_in_stages_beats_transport_error_in_calls(authed_client):
    """Criterion 23: PGRST301 (stages) + TransportError (calls) -> 401,
    not 503."""

    def handler(request):
        url = str(request.url)
        if "followup_insight" in url:
            return httpx.Response(
                401, json={"message": "JWT expired", "code": "PGRST301", "hint": None, "details": None}
            )
        if "funnel_records" in url:
            raise httpx.ConnectError("simulated network failure")
        raise AssertionError(url)

    app.dependency_overrides[get_user_client] = _override(handler)
    response = authed_client.get(PATH)
    assert response.status_code == 401
    assert response.json() == {"detail": "Invalid or expired token"}


def test_401_beats_403_when_both_parts_have_auth_failures(authed_client):
    """Criterion 24: PGRST301 (401, stages) + 42501 (403, calls) -> 401."""

    def handler(request):
        url = str(request.url)
        if "followup_insight" in url:
            return httpx.Response(
                401, json={"message": "JWT expired", "code": "PGRST301", "hint": None, "details": None}
            )
        if "funnel_records" in url:
            return httpx.Response(
                403, json={"message": "permission denied", "code": "42501", "hint": None, "details": None}
            )
        raise AssertionError(url)

    app.dependency_overrides[get_user_client] = _override(handler)
    response = authed_client.get(PATH)
    assert response.status_code == 401


def test_403_when_only_calls_part_has_an_auth_failure(authed_client):
    def handler(request):
        url = str(request.url)
        if "followup_insight" in url:
            return httpx.Response(200, json=STAGES_ROWS, headers={"content-range": "0-4/5"})
        if "funnel_records" in url:
            return httpx.Response(
                403, json={"message": "permission denied", "code": "42501", "hint": None, "details": None}
            )
        raise AssertionError(url)

    app.dependency_overrides[get_user_client] = _override(handler)
    response = authed_client.get(PATH)
    assert response.status_code == 403


# ---------------------------------------------------------------------------
# Criterion 25 -- negative control: the part that already succeeded must
# NOT leak into the body alongside an auth failure from the other part.
# ---------------------------------------------------------------------------


def test_successful_stages_data_is_not_leaked_alongside_an_auth_failure(authed_client):
    def handler(request):
        url = str(request.url)
        if "followup_insight" in url:
            return httpx.Response(200, json=STAGES_ROWS, headers={"content-range": "0-4/5"})
        if "funnel_records" in url:
            return httpx.Response(
                401, json={"message": "JWT expired", "code": "PGRST301", "hint": None, "details": None}
            )
        raise AssertionError(url)

    app.dependency_overrides[get_user_client] = _override(handler)
    response = authed_client.get(PATH)

    assert response.status_code == 401
    body = response.json()
    assert set(body.keys()) == {"detail"}
    assert "stages" not in response.text
    assert "followup_1" not in response.text


# ---------------------------------------------------------------------------
# Criterion 26 -- one part unavailable is 200; both unavailable is 503.
# ---------------------------------------------------------------------------


def test_one_part_unavailable_is_200_with_the_other_part_intact(authed_client):
    def handler(request):
        url = str(request.url)
        if "followup_insight" in url:
            return httpx.Response(503, text="<html>gateway</html>")
        if "funnel_records" in url:
            if "limit=1" in url and "select=source_row_id" in url:
                return httpx.Response(200, json=[{"source_row_id": 1}], headers={"content-range": "0-0/3163"})
            offset = int(dict(p.split("=") for p in url.split("?")[1].split("&"))["offset"])
            return _funnel_records_page(offset)
        raise AssertionError(url)

    app.dependency_overrides[get_user_client] = _override(handler)
    response = authed_client.get(PATH)
    body = response.json()

    assert response.status_code == 200
    assert body["stages"]["status"] == "unavailable"
    assert body["stages"]["error"]["reason_code"] == "data_unavailable"
    assert body["calls_to_closed"]["status"] == "available"


def test_both_parts_unavailable_is_503(authed_client):
    def handler(request):
        return httpx.Response(503, text="<html>gateway</html>")

    app.dependency_overrides[get_user_client] = _override(handler)
    response = authed_client.get(PATH)
    assert response.status_code == 503
    assert response.json() == {"detail": "Service temporarily unavailable"}


# ---------------------------------------------------------------------------
# Criterion 70 -- aggregation mismatch: paginated fetch vs. independent
# count. NEVER validated against len(rows) from the same fetch.
# ---------------------------------------------------------------------------


def test_aggregation_mismatch_marks_calls_part_unavailable_not_stages(authed_client):
    """The paginated fetch returns 3163 rows, but the independent count
    query reports 3164 -- a mismatch that must be caught, not silently
    accepted because len(rows) alone looked plausible."""
    handler = _make_handler(
        stages_response=httpx.Response(200, json=STAGES_ROWS, headers={"content-range": "0-4/5"}),
        funnel_records_total=3163,
        independent_count=3164,
    )
    app.dependency_overrides[get_user_client] = _override(handler)

    response = authed_client.get(PATH)
    body = response.json()

    assert response.status_code == 200
    assert body["stages"]["status"] == "available"
    assert body["calls_to_closed"]["status"] == "unavailable"
    assert body["calls_to_closed"]["error"]["reason_code"] == "aggregation_mismatch"


def test_truncated_pagination_is_caught_by_the_independent_count(authed_client):
    """A paginated fetch that silently returns fewer rows than the real
    population (e.g. a cut-off final page) must be caught by the
    independent count, not accepted because it 'looked like' a real
    distribution -- fetch reports 2000 rows total, independent count
    reports the true 3163."""
    handler = _make_handler(
        stages_response=httpx.Response(200, json=STAGES_ROWS, headers={"content-range": "0-4/5"}),
        funnel_records_total=2000,
        independent_count=3163,
    )
    app.dependency_overrides[get_user_client] = _override(handler)

    response = authed_client.get(PATH)
    body = response.json()
    assert response.status_code == 200
    assert body["calls_to_closed"]["status"] == "unavailable"
    assert body["calls_to_closed"]["error"]["reason_code"] == "aggregation_mismatch"


# ---------------------------------------------------------------------------
# Wrong stage count/sequence -> stages part unavailable, not a 500.
# ---------------------------------------------------------------------------


def test_wrong_number_of_stages_marks_the_part_unavailable_not_500(authed_client):
    handler = _make_handler(stages_response=httpx.Response(200, json=STAGES_ROWS[:4], headers={"content-range": "0-3/4"}))
    app.dependency_overrides[get_user_client] = _override(handler)

    response = authed_client.get(PATH)
    body = response.json()
    assert response.status_code == 200
    assert body["stages"]["status"] == "unavailable"
    assert body["stages"]["error"]["reason_code"] == "data_unavailable"
