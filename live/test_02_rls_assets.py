"""Phase 12 checkpoint 3 (PHASE12.md CP3, falsification cases 2-3 in §ז)
-- real RLS on funnel_records, and asset integrity: no service_role/
secret/raw JWT in any JS actually served, SRI on the live page matches
the actually-served CDN script byte-for-byte, and business_facts.json's
live bytes match its git blob exactly.

Four of these six tests are credential-free: test_anon_select_is_blocked
(the publishable key alone, no sign-in, since P12-D11's anon case is
about the ABSENCE of a JWT), test_no_secret_or_raw_jwt_in_served_js,
test_sri_integrity_matches_served_cdn_script, and
test_business_facts_json_live_matches_git_blob (all plain public GETs).
The two organization-scoped RLS tests need a real JWT via
sign_in_via_api() and therefore prompt for demo_credentials; per
P12-D3's division of labor, Claude prepares and reviews them but does
not run them.
"""
from __future__ import annotations

import base64
import hashlib
import re
import subprocess
from pathlib import Path

import httpx

from conftest import (
    DEMO_NOORG_EMAIL,
    DEMO_NORTHBOUND_EMAIL,
    LIVE_BASE_URL,
    PostgrestReadOnly,
    live_config,
    sign_in_via_api,
)

REPO_ROOT = Path(__file__).resolve().parent.parent

# The REAL shared-form prefill query, byte-for-byte the same shape
# supabase-prefill.js's own fetchSharedFormPrefill() sends
# (app/static/js/supabase-prefill.js: SHARED_FORM_COLUMNS,
# .eq("purchased", 1), .order("source_row_id", {ascending: true}),
# .limit(PREFILL_LIMIT=1000)). Self-review finding: selecting only
# source_row_id proves the RLS gate opens or closes, but not that real
# PREFILL DATA -- the actual columns the shared form needs -- comes
# back. Used identically in all three RLS tests below (anon,
# northbound, noorg), since the claim being tested is about what THIS
# EXACT query does for each identity, not a simplified stand-in.
SHARED_FORM_COLUMNS = [
    "source_row_id", "ad_budget", "num_leads", "leads_answered", "closed",
    "followup_1", "followup_2", "followup_3", "followup_4", "followup_5",
    "calls_to_closed", "calls_to_not_closed", "customer_acquisition_cost",
]
PREFILL_PARAMS = {
    "select": ",".join(SHARED_FORM_COLUMNS),
    "purchased": "eq.1",
    "order": "source_row_id.asc",
    "limit": "1000",
}


def test_anon_select_is_blocked():
    """PHASE12.md CP3: 'anon ⇒ חסימה'.

    Verified live (22.09.2026) before this test was written: Postgres
    denies the query outright with 42501 (no table-level GRANT exists
    for the anon role at all -- see
    supabase/migrations/20260901164903_schema.sql:39, `grant select ...
    to authenticated` only) -- a genuinely different, stronger failure
    than RLS's zero-rows for a signed-in wrong-organization user (the
    noorg test below). ⛔ Do not conflate the two: this is a permission
    error before RLS is even evaluated, not an RLS-filtered empty
    result.

    Self-review finding: this used to depend on the `postgrest` fixture
    purely to read `live_context.live_supabase_url` off it -- pulling
    in an entire Playwright BrowserContext (and P12-D4's route guard)
    for a plain server-to-server httpx call that never touches a
    browser at all. Built directly from live_config() instead, matching
    the two RLS tests below it exactly (they differ only in whether an
    access_token is attached)."""
    config = live_config()
    client = PostgrestReadOnly(base_url=config["supabase_url"], publishable_key=config["supabase_publishable_key"])
    response = client.get("/funnel_records", params=PREFILL_PARAMS)
    assert response.status_code == 401
    assert response.json()["code"] == "42501"


def test_demo_northbound_prefill_returns_rows_under_real_rls(demo_credentials):
    """PHASE12.md CP3 / §ז case 2: 'demo-northbound + JWT ⇒ נתוני
    prefill חוזרים'. ⛔ Not a claim of row-level isolation between
    organizations (P12-D11) -- funnel_records has no organization
    column at all; the policy is a binary gate on
    auth.jwt()->app_metadata->>'organization' = 'northbound'
    (schema.sql:42-44). This proves the gate opens for the org it's
    meant to open for.

    Self-review finding: selecting only source_row_id (limit 5) proved
    the gate opened, but not that real PREFILL DATA comes back -- this
    now sends the exact SHARED_FORM_COLUMNS/purchased/order/limit query
    supabase-prefill.js's fetchSharedFormPrefill() actually sends, and
    checks the returned rows carry every column the shared form needs,
    not just that some row exists."""
    config = live_config()
    token = sign_in_via_api(DEMO_NORTHBOUND_EMAIL, demo_credentials[DEMO_NORTHBOUND_EMAIL])
    client = PostgrestReadOnly(
        base_url=config["supabase_url"],
        publishable_key=config["supabase_publishable_key"],
        access_token=token,
    )
    response = client.get("/funnel_records", params=PREFILL_PARAMS)
    assert response.status_code == 200
    rows = response.json()
    assert len(rows) > 0, "demo-northbound got zero rows -- the RLS gate did not open"
    assert set(SHARED_FORM_COLUMNS) <= set(rows[0].keys()), (
        f"prefill row is missing expected columns: got {sorted(rows[0].keys())}"
    )


def test_demo_noorg_prefill_returns_zero_rows_under_real_rls(demo_credentials):
    """PHASE12.md CP3 / §ז case 2: 'demo-noorg/ארגון שגוי ⇒ אפס שורות'.
    A signed-in user WITH a real JWT, but the policy's own claim check
    fails -- unlike the anon case above, this is a 200 with an empty
    array (RLS filtered every row), not a permission error. Uses the
    same real prefill query as the northbound test above -- the claim
    is that THIS EXACT query returns nothing for this identity, not a
    simplified stand-in."""
    config = live_config()
    token = sign_in_via_api(DEMO_NOORG_EMAIL, demo_credentials[DEMO_NOORG_EMAIL])
    client = PostgrestReadOnly(
        base_url=config["supabase_url"],
        publishable_key=config["supabase_publishable_key"],
        access_token=token,
    )
    response = client.get("/funnel_records", params=PREFILL_PARAMS)
    assert response.status_code == 200
    assert response.json() == []


# ---------------------------------------------------------------------------
# §ז case 3 -- every JS file actually served, scanned for a leaked secret.
# ---------------------------------------------------------------------------

_FORBIDDEN_JS_PATTERNS = re.compile(
    r"service_role|SUPABASE_SECRET_KEY|sb_secret_[a-zA-Z0-9]"
    # A real JWT's shape, not just "some base64 that starts with eyJ" --
    # header.payload.signature, header and payload each base64url JSON
    # (so each segment itself starts with eyJ, the base64 encoding of
    # '{"'). Self-review finding: the original bare `eyJ[A-Za-z0-9_-]{10,}`
    # would false-positive on any unrelated base64-encoded JSON blob (an
    # inline source map, for instance), which isn't a JWT at all.
    r"|eyJ[A-Za-z0-9_-]+\.eyJ[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+"
)


def test_no_secret_or_raw_jwt_in_served_js():
    """PHASE12.md §ז case 3, verbatim: 'סריקת כל קובץ JS מוגש בפועל
    מהפריסה ⇒ אפס service_role/secret/JWT גולמי'.

    The file list is discovered from origin/main's tree via `git
    ls-tree` (every *.js file under app/static/, recursively) rather
    than hand-maintained, so this test never silently stops covering a
    new screen module someone adds later. Each one is then fetched from
    the LIVE deployment -- this is about what's actually served, not
    what's in git.

    Self-review finding (round two): the file list used to come from
    the local working tree (`rglob` on disk), not from origin/main --
    render.yaml pins deployment to `branch: main` (render.yaml:7), so
    that's the correct anchor, same reasoning as
    test_business_facts_json_live_matches_git_blob below. Both lists
    happen to be identical right now (18 files each), but the anchor
    itself was wrong: running this on a branch (this repo's own
    test/acceptance included) that had added or removed a JS file
    before merging would silently scan the wrong set.

    Self-review finding (round one): fetches through one shared
    httpx.Client (a single keep-alive connection to the deployment),
    not a fresh httpx.get() -- and its own fresh TCP+TLS handshake --
    per file; 18+ files is enough for that overhead to matter against a
    real, network-bound deployment."""
    tree_output = subprocess.run(
        ["git", "ls-tree", "-r", "--name-only", "origin/main", "--", "app/static"],
        cwd=REPO_ROOT,
        capture_output=True,
        check=True,
        text=True,
    ).stdout
    local_js_files = sorted(
        path.removeprefix("app/static/")
        for path in tree_output.splitlines()
        if path.endswith(".js")
    )
    assert local_js_files, "no JS files found under app/static/ on origin/main -- the scan itself is broken"

    offenders = []
    with httpx.Client(timeout=30) as client:
        for rel_path in local_js_files:
            response = client.get(f"{LIVE_BASE_URL}/{rel_path}")
            assert response.status_code == 200, f"{rel_path}: expected 200, got {response.status_code}"
            match = _FORBIDDEN_JS_PATTERNS.search(response.text)
            if match:
                offenders.append(f"{rel_path}: matched {match.group(0)[:20]}...")

    assert offenders == [], offenders


# ---------------------------------------------------------------------------
# SRI on the live page vs. the actually-served CDN script.
# ---------------------------------------------------------------------------

_SUPABASE_SCRIPT_PATTERN = re.compile(
    r'<script src="([^"]+supabase-js[^"]+)"\s+integrity="sha384-([^"]+)"'
)


def test_sri_integrity_matches_served_cdn_script():
    """PHASE12.md CP3: 'integrity (SRI) על הדף החי תקף'. Recomputes the
    real sha384 of the CDN script the live page actually references and
    compares it to the integrity attribute in that same live page --
    not to app/static/index.html's tracked copy, since the whole point
    is proving what a real browser would actually verify against."""
    html = httpx.get(LIVE_BASE_URL, timeout=30).text
    match = _SUPABASE_SCRIPT_PATTERN.search(html)
    assert match, "supabase-js script tag with an integrity attribute not found in the live page"

    script_url, declared_hash = match.group(1), match.group(2)
    script_bytes = httpx.get(script_url, timeout=30).content
    computed_hash = base64.b64encode(hashlib.sha384(script_bytes).digest()).decode()

    assert computed_hash == declared_hash, (
        f"SRI mismatch: page declares {declared_hash}, served script hashes to {computed_hash}"
    )


# ---------------------------------------------------------------------------
# business_facts.json: live bytes vs. the tracked git blob.
# ---------------------------------------------------------------------------


def test_business_facts_json_live_matches_git_blob():
    """PHASE12.md CP3: 'business_facts.json החי = ה-blob'.

    Compares against origin/main's git BLOB, not HEAD and not the local
    Windows working-tree file. Two independent reasons, not one:
    (1) .gitattributes' `* text=auto` means the working tree differs
    from any blob by line-ending normalization alone (established
    during the phase-12 planning gate) -- a blob is the only correct
    anchor at all. (2) Self-review finding: `HEAD` is whatever commit
    happens to be checked out when this runs, which is NOT necessarily
    what's actually deployed -- render.yaml pins deployment to
    `branch: main` (render.yaml:7), so running this on a divergent
    branch (this repo's own test/acceptance included, if it ever
    changes this file before merging) would compare against the wrong
    target and fail on a spurious mismatch that has nothing to do with
    real asset-integrity drift."""
    blob_bytes = subprocess.run(
        ["git", "show", "origin/main:app/static/business_facts.json"],
        cwd=REPO_ROOT,
        capture_output=True,
        check=True,
    ).stdout
    live_bytes = httpx.get(f"{LIVE_BASE_URL}/business_facts.json", timeout=30).content
    assert live_bytes == blob_bytes, (
        f"business_facts.json live (sha256={hashlib.sha256(live_bytes).hexdigest()[:12]}) "
        f"!= blob (sha256={hashlib.sha256(blob_bytes).hexdigest()[:12]})"
    )
