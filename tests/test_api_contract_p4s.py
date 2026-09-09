"""Phase 8A checkpoint 10 (PHASE8A.md D20/criterion 20): the 7th route
(POST /api/predict/super-customer) must be a purely ADDITIVE change to the
locked 6-route contract -- not just "still has 6 paths", but the exact old
path items, securitySchemes, and every pre-existing component schema
byte-identical to what was there before.

tests/test_api_contract.py's own closure-based projection check is
BUSINESS_ROUTES-driven and reachability-based, built for the locked file as
a whole; this is a simpler, stronger, separate check deliberately not
folded into it: full byte-identity of everything that existed before,
regardless of reachability, plus explicit growth-only assertions for
what's new. Compares the CURRENT docs/api/openapi.json against a static
fixture (tests/fixtures/openapi_pre_phase8a.json, a frozen copy of the
file as it stood immediately before phase 8A) rather than git HEAD --
git HEAD will itself become the 7-route file once this work is
committed, which would make an old-vs-HEAD diff compare the file against
itself and silently stop testing anything.
"""
import json
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
OPENAPI_JSON = REPO_ROOT / "docs" / "api" / "openapi.json"
PRE_PHASE8A_FIXTURE = Path(__file__).resolve().parent / "fixtures" / "openapi_pre_phase8a.json"

# The 6 paths locked before phase 8A (PHASE8A.md's "part א §7"). A
# snapshot, not derived from the fixture file, so a test bug that loads
# the wrong fixture still gets caught by a mismatch here.
_ORIGINAL_PATHS = frozenset({
    "/api/predict/ltv", "/api/predict/upsell", "/api/predict/referral",
    "/api/simulate/budget", "/api/insights/followup", "/api/insights/budget-tiers",
})


@pytest.fixture(scope="module")
def new_schema() -> dict:
    with OPENAPI_JSON.open(encoding="utf-8") as f:
        return json.load(f)


@pytest.fixture(scope="module")
def old_schema() -> dict:
    with PRE_PHASE8A_FIXTURE.open(encoding="utf-8") as f:
        old = json.load(f)
    assert set(old["paths"]) == _ORIGINAL_PATHS, "fixture drifted from the expected pre-8A path set"
    return old


def test_new_file_has_exactly_one_additional_path(new_schema):
    assert _ORIGINAL_PATHS <= set(new_schema["paths"]), "an original path went missing"
    added = set(new_schema["paths"]) - _ORIGINAL_PATHS
    assert added == {"/api/predict/super-customer"}, f"unexpected path delta: {added}"


def test_every_original_path_item_is_byte_identical(old_schema, new_schema):
    for path in _ORIGINAL_PATHS:
        assert new_schema["paths"][path] == old_schema["paths"][path], f"{path} changed"


def test_security_schemes_are_byte_identical(old_schema, new_schema):
    assert new_schema["components"]["securitySchemes"] == old_schema["components"]["securitySchemes"]


def test_every_preexisting_component_schema_is_byte_identical(old_schema, new_schema):
    old_schemas = old_schema["components"]["schemas"]
    new_schemas = new_schema["components"]["schemas"]
    missing = sorted(set(old_schemas) - set(new_schemas))
    assert missing == [], f"component schemas dropped: {missing}"
    changed = sorted(name for name, body in old_schemas.items() if new_schemas[name] != body)
    assert changed == [], f"pre-existing component schemas mutated: {changed}"


def test_new_route_declares_the_full_error_response_set(new_schema):
    """criterion 23: 200/401/403/422/500/503 and BearerAuth."""
    route = new_schema["paths"]["/api/predict/super-customer"]["post"]
    assert set(route["responses"]) == {"200", "401", "403", "422", "500", "503"}
    assert route["security"] == [{"BearerAuth": []}]
