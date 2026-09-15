"""Phase 11 checkpoint 10 -- static/contract tests for the dashboard
frontend's wiring to the locked backend contract (PHASE11.md CP10).

Every test here is STATIC, matching tests/test_api_contract.py's own
convention: no HTTP, no browser, no Node -- reading app/static/js/*.js
source text and comparing it against REAL sources of truth (the locked
docs/api/openapi.json, itself verified elsewhere to match
app/schemas.py; and app.auth's own live-introspected router), never a
third, hand-typed list that could silently drift from either.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

from app import auth

REPO_ROOT = Path(__file__).resolve().parent.parent
STATIC_DIR = REPO_ROOT / "app" / "static"
STATIC_JS = STATIC_DIR / "js"
API_JS = STATIC_JS / "api.js"
BOOTSTRAP_JS = STATIC_JS / "bootstrap.js"
OPENAPI_JSON = REPO_ROOT / "docs" / "api" / "openapi.json"


def _business_routes() -> list[str]:
    spec = json.loads(OPENAPI_JSON.read_text(encoding="utf-8"))
    return sorted(spec["paths"].keys())


def _auth_routes() -> list[str]:
    return sorted(r.path for r in auth.router.routes)


def test_nine_interface_routes_all_wired_in_frontend():
    """PHASE11.md CP10: nine total routes -- the seven locked business
    routes from openapi.json plus /api/config and /api/me from
    app.auth's own router -- must each appear as a literal path string
    in the frontend, sourced from real introspection rather than a
    third hand-typed list."""
    business = _business_routes()
    auth_paths = _auth_routes()
    assert len(business) == 7, f"expected 7 locked business routes, found {business}"
    assert auth_paths == ["/api/config", "/api/me"]
    assert len(business) + len(auth_paths) == 9

    api_js_text = API_JS.read_text(encoding="utf-8")
    for path in business:
        assert f'"{path}"' in api_js_text, f"{path} not wired in api.js"

    bootstrap_text = BOOTSTRAP_JS.read_text(encoding="utf-8")
    for path in auth_paths:
        assert f'"{path}"' in bootstrap_text, f"{path} not wired in bootstrap.js"


def test_every_business_call_attaches_a_bearer_token():
    """CLAUDE.md's own locked decision: "קריאות נתונים למשתמש נושאות את
    ה-JWT שלו כדי ש-RLS תיאכף בפועל" -- applies to every business call,
    not just Supabase's own RLS-enforced reads. api.js's shared call()
    wrapper is the ONE place this is built; checked as exactly one
    function so a future second call-building path can't quietly skip
    it."""
    text = API_JS.read_text(encoding="utf-8")
    assert re.search(r"Authorization:\s*`Bearer \$\{", text), (
        "api.js's call() must attach 'Authorization: Bearer ${...}' to every request"
    )
    assert len(re.findall(r"async function call\(", text)) == 1


def test_no_secret_key_anywhere_in_shipped_frontend():
    """CLAUDE.md's own locked decision: anon/publishable key in the
    browser only, service/secret key confined to scripts/*.py and never
    shipped to app/static/. Static grep across every JS file actually
    served to the browser (not just api.js) plus index.html."""
    forbidden = re.compile(r"service_role|SUPABASE_SECRET|sk-[a-zA-Z0-9]|-----BEGIN", re.IGNORECASE)
    offenders = []
    for path in STATIC_JS.rglob("*.js"):
        if forbidden.search(path.read_text(encoding="utf-8")):
            offenders.append(str(path.relative_to(REPO_ROOT)))
    index_html = STATIC_DIR / "index.html"
    if forbidden.search(index_html.read_text(encoding="utf-8")):
        offenders.append(str(index_html.relative_to(REPO_ROOT)))
    assert not offenders, f"secret-like pattern found in: {offenders}"


# Per-screen-file MINIMUM summary-recommendation call count, matching
# the known target->file mapping (never a single global magic number,
# so one legitimate future call site doesn't force an unrelated edit
# here): Overview(1) + P2/P3/P4(3, each >=1 even though every one of
# them actually carries 2 -- success AND OOD branches) + P4S(1) +
# Budget Simulator(1) + Follow-up's two graphs(2) = the 8 targets
# PHASE10.md's own D9 names.
SCREEN_FILES_MIN_TARGETS = {
    "overview.js": 1,
    "predict.js": 3,
    "super-customer.js": 1,
    "budget.js": 1,
    "followup.js": 2,
}


def test_summary_recommendation_wired_for_all_eight_targets():
    """PHASE10.md D9 / DESIGN.md §6: all eight targets carry a
    summary-recommendation. IA.md's own rule that a D9 layer is never
    optional means every state branch (not just the success path)
    should call it -- checked here as a minimum, not an exact count,
    since OOD/success branches legitimately double some files' calls."""
    screens_dir = STATIC_JS / "screens"
    total_targets = 0
    for filename, min_targets in SCREEN_FILES_MIN_TARGETS.items():
        text = (screens_dir / filename).read_text(encoding="utf-8")
        call_count = len(re.findall(r"renderSummaryRecommendation\(", text))
        assert call_count >= min_targets, (
            f"{filename}: expected >= {min_targets} renderSummaryRecommendation call(s), found {call_count}"
        )
        total_targets += min_targets
    assert total_targets == 8


def test_no_service_key_used_to_build_a_second_supabase_client():
    """CLAUDE.md: the browser holds exactly one Supabase client, built
    once in bootstrap.js from the publishable key /api/config returns
    -- supabase-prefill.js must reuse it (init(client)), never call
    createClient() a second time with a key of its own."""
    prefill_text = (STATIC_JS / "supabase-prefill.js").read_text(encoding="utf-8")
    assert "createClient" not in prefill_text
    bootstrap_text = BOOTSTRAP_JS.read_text(encoding="utf-8")
    # ".createClient(" (the method-call form), not the bare word -- a
    # code comment elsewhere in this file also mentions createClient()
    # by name without calling it.
    assert bootstrap_text.count(".createClient(") == 1
