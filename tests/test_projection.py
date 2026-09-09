"""Phase 9 checkpoint 10 -- projection drift check (PHASE9.md D8):
app.main.app's LIVE OpenAPI schema, on the seven business routes, their
reachable component schemas (via $ref/oneOf/anyOf/items closure), and
securitySchemes, must match docs/api/openapi.json's locked contract
exactly on that projection.

Excluded (PHASE9.md D8's own list): `info` (title/version legitimately
differ -- the locked file says "FunnelIQ API contract"/"phase-8", the
live app says "FunnelIQ API"/its own version), /health, /api/config,
/api/me (phases 1/4, never part of this contract), and the static mount.

Reuses tests/test_api_contract.py's _root_closure algorithm (refactored
to take an explicit component_schemas argument) rather than a second
implementation of the same field-path-closure walk (PHASE9.md's own
scope discipline: "שימוש חוזר ב-_walk/_closure/_root_closure").
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.main import app
from tests.test_api_contract import _root_closure

REPO_ROOT = Path(__file__).resolve().parent.parent
LOCKED_SCHEMA: dict = json.loads((REPO_ROOT / "docs" / "api" / "openapi.json").read_text(encoding="utf-8"))

BUSINESS_ROUTES = {
    ("post", "/api/predict/ltv"): "LtvPrediction",
    ("post", "/api/predict/upsell"): "PropensityPrediction",
    ("post", "/api/predict/referral"): "PropensityPrediction",
    ("post", "/api/predict/super-customer"): "SuperCustomerPrediction",
    ("get", "/api/simulate/budget"): "BudgetSimulation",
    ("get", "/api/insights/followup"): "FollowupResponse",
    ("get", "/api/insights/budget-tiers"): "BudgetTiersResponse",
}

REQUEST_BODY_ROOTS = ("FunnelInput", "EarlyFunnelInput")

# D8's exclusion list, verbatim -- "/" covers the StaticFiles mount, which
# FastAPI's openapi() does not itself enumerate as a path (it's not a
# route, just a catch-all ASGI mount), listed here for documentation.
EXCLUDED_PATHS = {"/health", "/api/config", "/api/me", "/"}


@pytest.fixture(scope="module")
def live_schema() -> dict:
    return app.openapi()


def test_live_app_has_exactly_the_seven_business_paths_plus_excluded(live_schema):
    live_paths = set(live_schema["paths"])
    business_paths = {p for _, p in BUSINESS_ROUTES}
    missing = business_paths - live_paths
    assert missing == set(), f"business route(s) missing from the live app: {missing}"

    unexpected = live_paths - business_paths - EXCLUDED_PATHS
    assert unexpected == set(), f"unexpected path(s) in the live app, not in BUSINESS_ROUTES or the D8 exclusion list: {unexpected}"


@pytest.mark.parametrize("method_path", sorted(BUSINESS_ROUTES))
def test_route_security_matches_locked_contract(live_schema, method_path):
    method, path = method_path
    live_security = live_schema["paths"][path][method].get("security")
    locked_security = LOCKED_SCHEMA["paths"][path][method].get("security")
    assert live_security == locked_security == [{"BearerAuth": []}]


@pytest.mark.parametrize("method_path", sorted(BUSINESS_ROUTES))
def test_route_response_status_codes_match_locked_contract(live_schema, method_path):
    method, path = method_path
    live_codes = set(live_schema["paths"][path][method]["responses"])
    locked_codes = set(LOCKED_SCHEMA["paths"][path][method]["responses"])
    assert live_codes == locked_codes


def test_security_schemes_match_locked_contract(live_schema):
    assert live_schema["components"]["securitySchemes"] == LOCKED_SCHEMA["components"]["securitySchemes"]
    assert live_schema["components"]["securitySchemes"] == {"BearerAuth": {"type": "http", "scheme": "bearer"}}


@pytest.mark.parametrize("root", sorted(set(BUSINESS_ROUTES.values()) | set(REQUEST_BODY_ROOTS)))
def test_root_field_closure_matches_locked_contract(live_schema, root):
    """The strongest check: every reachable field path (through $ref,
    oneOf/anyOf, array items) from each response/request root is
    IDENTICAL between the live app and the locked file -- not just "the
    route exists", but the full shape a client would actually see."""
    live_closure = _root_closure(root, live_schema["components"]["schemas"])
    locked_closure = _root_closure(root, LOCKED_SCHEMA["components"]["schemas"])
    assert live_closure == locked_closure


def test_every_closure_is_nonempty():
    """Guards against a vacuous pass -- if a root name were misspelled or
    missing from components.schemas, _root_closure would KeyError, not
    silently return an empty set both sides agree on. This asserts the
    comparison above is actually exercising real field paths."""
    for root in set(BUSINESS_ROUTES.values()) | set(REQUEST_BODY_ROOTS):
        assert len(_root_closure(root, LOCKED_SCHEMA["components"]["schemas"])) > 0, root


# ---------------------------------------------------------------------------
# Criterion 2 -- all seven business routes, exercised through real HTTP
# against app.main.app in one place, each returning 200 with a body that
# validates against its own locked response model.
# ---------------------------------------------------------------------------


def test_all_seven_business_routes_return_200(authed_client):
    import httpx
    from supabase import ClientOptions, create_client

    from app.schemas import (
        BudgetSimulation, BudgetTiersResponse, FollowupResponse,
        LtvPrediction, PropensityPrediction, SuperCustomerPrediction,
    )
    from app.supabase_client import get_user_client
    from tests.conftest import EARLY_FUNNEL_INPUT_IN_DOMAIN, FUNNEL_INPUT_IN_DOMAIN

    stages_rows = [
        {"stage_order": i, "stage": f"followup_{i}", "from_leads": 100 - i * 10,
         "to_leads": 100 - (i + 1) * 10, "drop_rate": 0.1}
        for i in range(1, 6)
    ]
    tier_rows = [{"tier_order": 1, "budget_tier": "Low", "n_records": 10, "conversion_rate": 0.5}]

    def supabase_handler(request):
        url = str(request.url)
        if "budget_tier_insight" in url:
            return httpx.Response(200, json=tier_rows, headers={"content-range": "0-0/1"})
        if "followup_insight" in url:
            return httpx.Response(200, json=stages_rows, headers={"content-range": "0-4/5"})
        if "funnel_records" in url:
            if "limit=1" in url and "select=source_row_id" in url:
                return httpx.Response(200, json=[{"source_row_id": 1}], headers={"content-range": "0-0/1"})
            return httpx.Response(200, json=[{"calls_to_closed": 3}], headers={"content-range": "0-0/1"})
        raise AssertionError(f"unexpected URL: {url}")

    def override():
        options = ClientOptions(
            headers={"Authorization": "Bearer tok"},
            httpx_client=httpx.Client(transport=httpx.MockTransport(supabase_handler)),
        )
        yield create_client("https://example.supabase.co", "sb_publishable_dummy", options=options)

    from app.main import app

    app.dependency_overrides[get_user_client] = override
    try:
        checks = [
            ("POST", "/api/predict/ltv", FUNNEL_INPUT_IN_DOMAIN, LtvPrediction),
            ("POST", "/api/predict/upsell", FUNNEL_INPUT_IN_DOMAIN, PropensityPrediction),
            ("POST", "/api/predict/referral", FUNNEL_INPUT_IN_DOMAIN, PropensityPrediction),
            ("POST", "/api/predict/super-customer", EARLY_FUNNEL_INPUT_IN_DOMAIN, SuperCustomerPrediction),
            ("GET", "/api/simulate/budget", None, BudgetSimulation),
            ("GET", "/api/insights/followup", None, FollowupResponse),
            ("GET", "/api/insights/budget-tiers", None, BudgetTiersResponse),
        ]
        for method, path, body, response_model in checks:
            if method == "POST":
                response = authed_client.post(path, json=body)
            else:
                response = authed_client.get(path)
            assert response.status_code == 200, f"{method} {path} -> {response.status_code}: {response.text}"
            response_model(**response.json())  # must not raise -- body matches its own schema
    finally:
        app.dependency_overrides.pop(get_user_client, None)
