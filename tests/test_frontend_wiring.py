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
    third hand-typed list.

    Second-pass self-review, 2026-09-15 (no external reviewer
    available): the first draft only checked substring presence
    anywhere in the file, which a code COMMENT mentioning a path would
    also satisfy -- caught in this same file's own
    test_no_service_key_used_to_build_a_second_supabase_client, whose
    first draft counted "createClient(" and was fooled by exactly this.
    Tightened here to require each path appear specifically as the
    first argument of postJson(/getJson(/fetch( -- an actual call site,
    not a comment mentioning the route in passing."""
    business = _business_routes()
    auth_paths = _auth_routes()
    assert len(business) == 7, f"expected 7 locked business routes, found {business}"
    assert auth_paths == ["/api/config", "/api/me"]
    assert len(business) + len(auth_paths) == 9

    api_js_text = API_JS.read_text(encoding="utf-8")
    for path in business:
        pattern = re.compile(r'(?:postJson|getJson)\(\s*"' + re.escape(path) + r'"')
        assert pattern.search(api_js_text), f"{path} is not called via postJson(/getJson( in api.js (comment mention doesn't count)"

    bootstrap_text = BOOTSTRAP_JS.read_text(encoding="utf-8")
    for path in auth_paths:
        pattern = re.compile(r'fetch\(\s*"' + re.escape(path) + r'"')
        assert pattern.search(bootstrap_text), f"{path} is not called via fetch( in bootstrap.js (comment mention doesn't count)"


def test_every_business_call_attaches_a_bearer_token():
    """CLAUDE.md's own locked decision: "קריאות נתונים למשתמש נושאות את
    ה-JWT שלו כדי ש-RLS תיאכף בפועל" -- applies to every business call,
    not just Supabase's own RLS-enforced reads. api.js's shared call()
    wrapper is the ONE place this is built; checked as exactly one
    function so a future second call-building path can't quietly skip
    it.

    Second-pass self-review, 2026-09-15: the first draft searched the
    Authorization pattern across the WHOLE file, which would still pass
    even if it only existed in a comment or dead code while the real
    call() body had lost it. Tightened to search specifically within
    call()'s own body (from its declaration to the next top-level
    function), the same class of gap the route-wiring test above had."""
    text = API_JS.read_text(encoding="utf-8")
    start = text.index("async function call(")
    end = text.index("\nfunction postJson(", start)
    call_body = text[start:end]
    assert re.search(r"Authorization:\s*`Bearer \$\{", call_body), (
        "call()'s own body must attach 'Authorization: Bearer ${...}' to every request"
    )
    assert len(re.findall(r"async function call\(", text)) == 1


def test_no_secret_key_anywhere_in_shipped_frontend():
    """CLAUDE.md's own locked decision: anon/publishable key in the
    browser only, service/secret key confined to scripts/*.py and never
    shipped to app/static/. Static grep across every JS file actually
    served to the browser plus index.html.

    Second-pass self-review, 2026-09-15: the first draft scanned only
    STATIC_JS.rglob("*.js") -- app/static/js/**/*.js -- which silently
    MISSES app/static/app.js itself (the SPA entry point, one directory
    up from app/static/js/), the file that wires the Supabase client
    and every screen's auth-gated bootstrap. Fixed to scan STATIC_DIR
    (app/static/) recursively instead, so app.js is included."""
    forbidden = re.compile(r"service_role|SUPABASE_SECRET|sk-[a-zA-Z0-9]|-----BEGIN", re.IGNORECASE)
    offenders = []
    for path in STATIC_DIR.rglob("*.js"):
        if forbidden.search(path.read_text(encoding="utf-8")):
            offenders.append(str(path.relative_to(REPO_ROOT)))
    index_html = STATIC_DIR / "index.html"
    if forbidden.search(index_html.read_text(encoding="utf-8")):
        offenders.append(str(index_html.relative_to(REPO_ROOT)))
    assert not offenders, f"secret-like pattern found in: {offenders}"


def _function_body(text: str, func_name: str, next_func_name: str | None) -> str:
    """Slice from `function func_name(`'s declaration to the next named
    function's declaration (or EOF if `next_func_name` is None). Robust
    to line-number drift, unlike hardcoding offsets."""
    start = text.index(f"function {func_name}(")
    end = text.index(f"function {next_func_name}(", start) if next_func_name else len(text)
    return text[start:end]


# Single-target files: per-file presence is already exactly per-target
# (no aggregation blind spot -- see the multi-target files below).
SINGLE_TARGET_FILES = ["overview.js", "super-customer.js", "budget.js"]

# Multi-target files: (target label, owning function, next function to
# bound the slice). Second-pass self-review, 2026-09-15 (no external
# reviewer available): the original version of this test only checked a
# per-FILE minimum count (predict.js >= 3, followup.js >= 2) -- which
# would still pass even if one target's own call were entirely missing,
# as long as ANOTHER target in the same file happened to call it an
# extra time (e.g. a duplicate in P2's own branch masking a missing
# call in P4's). Rewritten to slice each target's own function body by
# name and check it individually, closing that blind spot -- the same
# class of gap test_nine_interface_routes_all_wired_in_frontend and
# test_every_business_call_attaches_a_bearer_token had, both already
# tightened above in this same review pass.
MULTI_TARGET_FUNCTIONS = [
    ("predict.js", "P2", "buildP2Panel", "buildP3Panel"),
    ("predict.js", "P3", "buildP3Panel", "buildP4Panel"),
    ("predict.js", "P4", "buildP4Panel", "renderResults"),
    ("followup.js", "dropout", "buildStagesGroup", "computeStagesD9"),
    ("followup.js", "calls_to_closed", "buildCallsGroup", "computeCallsD9"),
]


def test_summary_recommendation_wired_for_all_eight_targets():
    """PHASE10.md D9 / DESIGN.md §6: all eight targets carry a
    summary-recommendation, checked per TARGET (not per file) so one
    target's own call can never be substituted by another's."""
    screens_dir = STATIC_JS / "screens"
    covered = 0

    for filename in SINGLE_TARGET_FILES:
        text = (screens_dir / filename).read_text(encoding="utf-8")
        assert "renderSummaryRecommendation(" in text, f"{filename}: no summary-recommendation call found"
        covered += 1

    file_text_cache: dict[str, str] = {}
    for filename, target_label, func_name, next_func_name in MULTI_TARGET_FUNCTIONS:
        text = file_text_cache.setdefault(filename, (screens_dir / filename).read_text(encoding="utf-8"))
        body = _function_body(text, func_name, next_func_name)
        # computeStagesD9/computeCallsD9's OWN body (not their caller
        # buildStagesGroup/buildCallsGroup) is what actually builds the
        # D9 props object -- but the CALL to renderSummaryRecommendation
        # happens in the caller. Include both: the caller function's
        # body already spans up to the next declared function, which
        # for buildStagesGroup/buildCallsGroup is exactly
        # computeStagesD9/computeCallsD9's own declaration line (not its
        # body) -- so the call site itself (inside the caller) is
        # captured correctly by this slice.
        assert "renderSummaryRecommendation(" in body, (
            f"{filename} ({target_label}): no summary-recommendation call found in {func_name}()"
        )
        covered += 1

    assert covered == 8


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
