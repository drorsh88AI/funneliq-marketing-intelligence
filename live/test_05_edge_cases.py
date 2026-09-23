"""Phase 12 checkpoint 6 (PHASE12.md CP6, P12-D12, falsification cases 5
and 10 in sec ZAYIN) -- live edge cases against the real deployed
service, split strictly into TWO evidence classes that must never be
conflated (P12-D12):

  REAL BACKEND evidence (the server itself genuinely behaves this way):
    - test_real_ood_returns_null_fields_with_real_warnings
    - test_real_validation_blocks_closed_exceeding_followup5

  FRONTEND-INJECTED-FAILURE evidence (the deployed frontend's own error
  handling, proven against a REAL session -- the server does NOT fail in
  these cases; a Playwright route handler substitutes one specific
  response client-side, never called "live end-to-end"):
    - test_path_failure_shows_error_and_recovers_on_retry
    - test_partial_followup_failure_shows_healthy_half_only
    - test_prefill_failure_does_not_block_manual_entry

CP6 explicitly forbids injecting a failure into business_facts.json
(PHASE12.md CP6 row) -- none of the tests below do. That asset IS still
fetched for real during these tests (app.js's own facts.init() runs on
every authenticated-shell mount, including the predict/followup
submissions below) -- the constraint is specifically on INJECTING A
FAILURE into it, not on avoiding contact with it.

Every test needs demo-northbound's real credentials (`demo_credentials`)
-- per P12-D3's own division of labor, Claude prepares and reviews this
file but does not run it; the user runs `pytest -s
live/test_05_edge_cases.py` and provides the (censored) output as
evidence.
"""
from __future__ import annotations

import json
import subprocess
import time
from pathlib import Path

import httpx
import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent

from conftest import (
    DEMO_NORTHBOUND_EMAIL,
    LIVE_BASE_URL,
    Secret,
    sign_in_via_api,
    sign_in_via_browser,
)

# test_path_failure_shows_error_and_recovers_on_retry's own wait for the
# shared form's Promise.all([ltv, upsell, referral]) to settle, and for
# the identical Promise.all a retry re-triggers. Evidence-based, not
# arbitrary: a real run's diagnostics (2026-09-23) showed the injected
# ltv route firing correctly in 0.05s, upsell taking 13.12s, and referral
# still unresolved at the original 15s bound -- i.e. this was never a
# sign the injection failed, only that predict/referral (already flagged
# as a warm-latency outlier in CP5's own evidence, 9.75s there in
# isolation, worse under this test's concurrent Promise.all load) needed
# more room. 45s is 3x that original bound -- generous but still finite,
# and in line with this file's and CP4's own precedent for genuinely
# slow live calls (this file's cold-start anchor uses 120s for Render's
# own wake-up latency; several direct httpx calls elsewhere use 60s).
PREDICT_PROMISE_ALL_WAIT_MS = 45_000

# Same in-domain baseline CP4/CP5 both verified against every task's real
# ood_bounds on origin/main -- copied, not imported, so this file stays
# self-contained like every other live/test_0N file.
FORM_VALUES = {
    "ad_budget": 5000, "num_leads": 100, "leads_answered": 60,
    "followup_1": 55, "followup_2": 45, "followup_3": 35, "followup_4": 25, "followup_5": 15,
    "closed": 5, "calls_to_closed": 4, "calls_to_not_closed": 3, "customer_acquisition_cost": 1000,
}
FUNNEL_PAYLOAD = {**FORM_VALUES, "not_closed": FORM_VALUES["followup_5"] - FORM_VALUES["closed"]}


def _bearer_headers(token: Secret) -> dict[str, str]:
    return {"Authorization": f"Bearer {token.reveal()}"}


@pytest.fixture(scope="module")
def northbound_token(demo_credentials: dict[str, Secret]) -> Secret:
    return sign_in_via_api(DEMO_NORTHBOUND_EMAIL, demo_credentials[DEMO_NORTHBOUND_EMAIL])


def _format_percent(fraction: float, decimals: int = 1) -> str:
    """format.js's own formatPercent(fraction, {decimals}) -- he-IL
    grouped, `{X}%`. Used to tie one real, captured stage's drop_rate to
    the exact text followup.js's computeStagesD9() would render for it
    (charts.js:...formatValue uses the same decimals=1 for this chart)."""
    return f"{fraction * 100:,.{decimals}f}%"


def _meta_ood_bounds(task: str) -> dict:
    """models/{task}.meta.json's ood_bounds, read from origin/main --
    same local-only git-blob anchor as CP3/CP4's own reads (render.yaml
    pins deployment to branch: main)."""
    blob = subprocess.run(
        ["git", "show", f"origin/main:models/{task}.meta.json"],
        cwd=REPO_ROOT, capture_output=True, check=True,
    ).stdout
    return json.loads(blob)["ood_bounds"]


# ---------------------------------------------------------------------------
# REAL BACKEND -- falsification case 5: genuine OOD from the model itself.
# ---------------------------------------------------------------------------


def test_real_ood_returns_null_fields_with_real_warnings(northbound_token):
    """PHASE12.md CP6 + falsification case 5: 'קלט מחוץ לתחום האימון =>
    OOD אמיתי מהמודל, ⛔ בלי מספר.' `ad_budget=50000` is genuinely outside
    P2's own tracked ood_bounds (max 20000, verified below against
    origin/main, not hand-typed) -- everything else stays inside the
    in-domain baseline, isolating ad_budget as the ONLY out-of-range
    feature so the warning can be checked against exactly one field."""
    p2_bounds = _meta_ood_bounds("P2")
    ood_ad_budget = 50000
    assert ood_ad_budget > p2_bounds["ad_budget"]["max"], (
        f"ood_ad_budget={ood_ad_budget} is not actually above P2's own max "
        f"({p2_bounds['ad_budget']['max']}) -- this payload would not trigger real OOD"
    )
    payload = {**FUNNEL_PAYLOAD, "ad_budget": ood_ad_budget}

    response = httpx.post(
        f"{LIVE_BASE_URL}/api/predict/ltv", headers=_bearer_headers(northbound_token),
        json=payload, timeout=30,
    )
    assert response.status_code == 200, response.text
    body = response.json()

    assert body["in_training_domain"] is False
    assert body["point_estimate"] is None and body["lower_bound"] is None and body["upper_bound"] is None, (
        "OOD response still carries a prediction number -- D.8's own "
        "in_training_domain=false <=> every prediction field null invariant"
    )
    warnings = body["warnings"]
    assert warnings, "in_training_domain=false but warnings[] is empty"
    ad_budget_warnings = [w for w in warnings if w["feature"] == "ad_budget"]
    assert len(ad_budget_warnings) == 1, f"expected exactly one ad_budget warning, got {ad_budget_warnings}"
    warning = ad_budget_warnings[0]
    assert warning["value"] == ood_ad_budget
    assert warning["min"] == p2_bounds["ad_budget"]["min"]
    assert warning["max"] == p2_bounds["ad_budget"]["max"]


# ---------------------------------------------------------------------------
# REAL BACKEND -- falsification case (CP6 row): validation blocking.
# ---------------------------------------------------------------------------


def test_real_validation_blocks_closed_exceeding_followup5(northbound_token):
    """PHASE12.md CP6: 'חסימת ולידציה (closed > followup_5) -- backend
    חי.' FunnelInput's own business rule (app/schemas.py: 'closed +
    not_closed must equal followup_5') rejects this with a real 422 from
    the live FastAPI process, not a client-side-only check -- sent with
    validation.js's own precondition already satisfied server-side
    (not_closed >= 0), so the ONLY thing that can fail is this rule."""
    payload = {**FUNNEL_PAYLOAD, "closed": 999, "not_closed": 0}  # 999 + 0 != followup_5 (15)
    response = httpx.post(
        f"{LIVE_BASE_URL}/api/predict/ltv", headers=_bearer_headers(northbound_token),
        json=payload, timeout=30,
    )
    assert response.status_code == 422, response.text
    body = response.json()
    messages = " | ".join(item["msg"] for item in body["detail"])
    assert "closed" in messages and "followup_5" in messages, (
        f"422 body doesn't mention the actual violated rule: {messages!r}"
    )


# ---------------------------------------------------------------------------
# FRONTEND-INJECTED FAILURE (P12-D12) -- path failure + recovery.
# ---------------------------------------------------------------------------


def test_path_failure_shows_error_and_recovers_on_retry(live_context, demo_credentials):
    """PHASE12.md CP6: 'כשל נתיב ... הזרקת כשל על ה-frontend הפרוס.'
    The REAL server never fails here -- Playwright intercepts the
    browser's own POST /api/predict/ltv and answers 503 exactly once
    (api.js:104: any non-200/401/403 status -> reason='unavailable' ->
    predict.js:416 -> 'השירות אינו זמין כרגע. נסו לשלוח את הטופס שוב.'),
    then lets every subsequent attempt through to the real backend --
    proving both the failure UI (no fabricated number), that the failure
    is ISOLATED to ltv alone (P3/P4 -- never intercepted -- still show
    real results from the very same submission), AND real recovery on
    retry (a real prediction, not a stuck state).

    Diagnostic-only note, 2026-09-23: a real run timed out waiting for
    '.prediction-panel-p2 .panel-error' (15s). predict.js's submitForm()
    awaits Promise.all([ltv, upsell, referral]) before rendering ANY of
    the three panels -- CP5's own warm-latency evidence already showed
    predict/referral at 9.750s, ~24x slower than the fastest route in
    that same sample, so the timeout is not necessarily proof the
    injection itself failed; it could equally be the shared Promise.all
    simply not having settled yet. A first attempt at diagnosing this
    (2026-09-23) only logged completed responses -- not enough to
    distinguish "still waiting on Promise.all" from "a request failed at
    the network level with no response at all" or "rendering itself is
    stuck despite every request settling". This version additionally
    captures REQUEST FAILURES (page.on('requestfailed') -- a request
    that never got a response, e.g. aborted or DNS-level, would
    otherwise be invisible to a response-only log) and, at the moment of
    timeout, a DIRECT SNAPSHOT of each of the three prediction panels'
    own state (error / real result / neither-yet, read structurally via
    class presence, never full innerHTML). ⛔ Only method/URL/status and
    structural presence/absence are ever printed here -- never a request
    body, a response body, or anything from #login-form's own fields;
    nothing in this diagnostic path touches credentials at all. The
    timeout itself is UNCHANGED -- still not raised without evidence
    that it should be."""
    attempt_count = {"n": 0}
    network_log: list[str] = []
    nav_start = time.monotonic()

    def _fail_once_then_real(route):
        attempt_count["n"] += 1
        if attempt_count["n"] == 1:
            route.fulfill(status=503, content_type="application/json", body="{}")
        else:
            route.continue_()

    def _relevant(url: str) -> bool:
        return any(marker in url for marker in ("/api/predict/", "/api/simulate/", "business_facts.json"))

    def _log_response(response):
        if _relevant(response.url):
            elapsed = time.monotonic() - nav_start
            network_log.append(f"t+{elapsed:.2f}s RESPONSE {response.request.method} {response.url} -> {response.status}")

    def _log_request_failed(request):
        if _relevant(request.url):
            elapsed = time.monotonic() - nav_start
            failure = request.failure or "unknown"
            network_log.append(f"t+{elapsed:.2f}s REQUEST-FAILED {request.method} {request.url} ({failure})")

    def _panel_snapshot(page) -> str:
        """Structural only -- which of {error, real result, neither yet}
        each panel is in, never the panel's own text content (which
        could, in principle, someday carry more than a plain prediction
        number; class presence alone is enough to diagnose this)."""
        lines = []
        for name in ("p2", "p3", "p4"):
            selector = f".prediction-panel-{name}"
            exists = page.query_selector(selector) is not None
            has_error = page.query_selector(f"{selector} .panel-error") is not None
            has_primary = page.query_selector(f"{selector} .prediction-primary") is not None
            lines.append(f"  {selector}: exists={exists} panel-error={has_error} prediction-primary={has_primary}")
        return "\n".join(lines)

    page = live_context.new_page()
    page.route("**/api/predict/ltv", _fail_once_then_real)
    page.on("response", _log_response)
    page.on("requestfailed", _log_request_failed)
    sign_in_via_browser(page, DEMO_NORTHBOUND_EMAIL, demo_credentials[DEMO_NORTHBOUND_EMAIL])
    page.wait_for_selector("#authenticated-shell:not([hidden])", timeout=30_000)

    page.click('a[data-route="predict"]')
    page.wait_for_selector("#field-ad_budget")
    for field, value in FORM_VALUES.items():
        page.fill(f"#field-{field}", str(value))
    page.check(".context-confirmation input[type=checkbox]")
    nav_start = time.monotonic()  # reset: the window that actually matters is from submit, not from page load
    page.click(".submit-button")

    try:
        page.wait_for_selector(".prediction-panel-p2 .panel-error", timeout=PREDICT_PROMISE_ALL_WAIT_MS)
    except Exception:
        print(
            "\ntest_path_failure_shows_error_and_recovers_on_retry diagnostics "
            f"(attempt_count={attempt_count['n']}, i.e. did the injected route fire at all):\n"
            + "\n".join(network_log or ["  (no matching network events captured)"])
            + "\npanel state at the moment of timeout:\n"
            + _panel_snapshot(page)
        )
        raise

    error_text = page.text_content(".prediction-panel-p2 .panel-error")
    assert "השירות אינו זמין כרגע" in error_text, error_text
    assert page.query_selector(".prediction-panel-p2 .prediction-primary") is None, (
        "a prediction number rendered despite the injected 503 -- no number may ever be fabricated"
    )

    # The failure is isolated to ltv -- P3/P4 were never intercepted and
    # must show real results from this SAME submission, not a blanket
    # failure across the shared form.
    p3_text = page.text_content(".prediction-panel-p3 .prediction-primary")
    assert p3_text and "נטייה לאפסייל" in p3_text, f"P3 did not show a real result: {p3_text!r}"
    p4_text = page.text_content(".prediction-panel-p4 .prediction-primary")
    assert p4_text and "נטייה להפניה" in p4_text, f"P4 did not show a real result: {p4_text!r}"

    retry_button = page.query_selector(".prediction-panel-p2 .panel-error button")
    assert retry_button is not None, "no retry ('ניסיון חוזר') button rendered on the failed panel"
    retry_button.click()

    page.wait_for_selector(".prediction-panel-p2 .prediction-primary", timeout=PREDICT_PROMISE_ALL_WAIT_MS)
    primary_text = page.text_content(".prediction-panel-p2 .prediction-primary")
    assert primary_text and "תחזית" in primary_text, (
        f"retry did not recover to a real prediction: {primary_text!r}"
    )
    assert attempt_count["n"] >= 2, "retry click did not actually re-send the request"


# ---------------------------------------------------------------------------
# FRONTEND-INJECTED FAILURE (P12-D12) -- partial followup failure.
# ---------------------------------------------------------------------------


def test_partial_followup_failure_shows_healthy_half_only(live_context, demo_credentials):
    """PHASE12.md CP6 + falsification case 10: 'שני חלקי followup --
    אחד נופל => התקין מוצג, ⛔ אין מספר שמור מומצא.' The REAL server
    response is fetched by the route handler itself (route.fetch()) --
    `stages` is passed through completely untouched (real live data);
    only `calls_to_closed` is replaced with a PartUnavailable shape
    (app/schemas.py's own contract). Proves: the healthy half renders
    the ACTUAL captured response's own data (not merely "a
    recommendation exists" -- one real stage's drop_rate is tied to the
    rendered D9 text), the failed half shows its own error (not a
    stored/invented number), and the combined recommendation correctly
    refuses to appear (followup.js:267)."""
    injected_message = "נתוני מספר השיחות עד סגירה אינם זמינים כרגע."
    captured = {}

    def _corrupt_calls_to_closed(route):
        response = route.fetch()
        assert response.status == 200, (
            f"real GET /api/insights/followup returned {response.status}, not 200 -- "
            "nothing healthy to corrupt into a partial-failure scenario"
        )
        data = response.json()
        assert data["stages"]["status"] == "available", (
            "real live /api/insights/followup already has stages unavailable -- "
            "this test needs a healthy real response to corrupt, not a pre-broken one"
        )
        captured["stages_rows"] = data["stages"]["data"]
        data["calls_to_closed"] = {
            "status": "unavailable",
            "error": {"reason_code": "data_unavailable", "message": injected_message},
        }
        route.fulfill(response=response, json=data)

    page = live_context.new_page()
    page.route("**/api/insights/followup", _corrupt_calls_to_closed)
    sign_in_via_browser(page, DEMO_NORTHBOUND_EMAIL, demo_credentials[DEMO_NORTHBOUND_EMAIL])
    page.wait_for_selector("#authenticated-shell:not([hidden])", timeout=30_000)

    page.click('a[data-route="followup"]')
    page.wait_for_selector(".followup-group", timeout=15_000)

    assert "stages_rows" in captured, "the followup route handler never fired -- nothing was actually captured/corrupted"

    groups = page.query_selector_all(".followup-group")
    assert len(groups) == 2, f"expected exactly 2 followup groups, found {len(groups)}"

    stages_group, calls_group = groups[0], groups[1]
    assert stages_group.query_selector(".panel-error") is None, "the REAL stages half rendered an error"
    stages_recommendation = stages_group.query_selector(".summary-recommendation")
    assert stages_recommendation is not None, "the real, healthy stages half did not render its D9 recommendation"

    # Tie the rendered text to THIS capture's own real data, not just to
    # "a recommendation exists" -- at least one real stage's drop_rate,
    # formatted exactly as computeStagesD9()/the chart's formatValue
    # would (format.js formatPercent, decimals=1), must appear.
    rows_with_rate = [r for r in captured["stages_rows"] if r["drop_rate"] is not None]
    assert rows_with_rate, "captured stages data has no row with a non-null drop_rate to tie to"
    expected_value_texts = [_format_percent(r["drop_rate"]) for r in rows_with_rate]
    stages_text = stages_recommendation.text_content()
    assert any(v in stages_text for v in expected_value_texts), (
        f"none of the real captured drop_rate values {expected_value_texts} appear in the "
        f"rendered stages recommendation -- cannot confirm it reflects THIS live response: {stages_text!r}"
    )

    calls_error = calls_group.query_selector(".panel-error")
    assert calls_error is not None, "the injected calls_to_closed failure did not render panel-error"
    assert injected_message in calls_error.text_content()
    assert calls_group.query_selector(".summary-recommendation") is None, (
        "the failed calls_to_closed half rendered a recommendation anyway -- "
        "no number may be invented for a part that failed"
    )

    unavailable_note = page.query_selector(".followup-recommendation-unavailable")
    assert unavailable_note is not None, (
        "the combined recommendation did not show its own 'unavailable' notice "
        "when only one of the two parts is available"
    )

    # The unavailable notice alone doesn't prove the healthy combined
    # recommendation is ABSENT -- followup.js:259-263 renders either the
    # "unavailable" paragraph OR the heading+CP4D_RECOMMENDATION pair,
    # never both, inside the same .followup-recommendation wrapper.
    # Check that wrapper directly, not just for the presence of one of
    # the two possible children.
    recommendation_wrap = page.query_selector(".followup-recommendation")
    assert recommendation_wrap is not None, ".followup-recommendation wrapper itself is missing"
    assert recommendation_wrap.query_selector("h3") is None, (
        "the healthy combined recommendation's own heading ('המלצה') rendered "
        "ALONGSIDE the unavailable notice -- followup.js's own if/else is exclusive"
    )
    recommendation_text = recommendation_wrap.text_content()
    assert "לא. אין לאמץ עצירה אוטומטית" not in recommendation_text, (
        f"the healthy CP4D_RECOMMENDATION text leaked into a degraded response: {recommendation_text!r}"
    )


# ---------------------------------------------------------------------------
# FRONTEND-INJECTED FAILURE (P12-D12) -- prefill failure never blocks
# manual entry.
# ---------------------------------------------------------------------------


def test_prefill_failure_does_not_block_manual_entry(live_context, demo_credentials):
    """PHASE12.md CP6: 'כשל prefill שאינו חוסם הזנה ידנית.' The REAL
    server never fails -- Playwright intercepts the browser's own
    Supabase PostgREST prefill query (supabase-prefill.js's
    fetchSharedFormPrefill()) and answers 503, proving predict.js's
    prefill-picker shows its own error (predict.js:854's exact string)
    while the 12 manual fields remain fully usable and a real submission
    still produces a real prediction -- prefill being down never blocks
    the manual-entry path CP7's own human-journey checklist depends on.

    `page.route()` takes precedence over `live_context`'s own
    `context.route()` P12-D4 write-guard (Playwright's own documented
    precedence: page-level routes are checked before context-level ones
    -- https://playwright.dev/python/docs/api/class-page), so this
    handler alone decides the outcome for a matching request. Self-check
    inside the handler: it must actually have fired, and only for GET --
    a route pattern silently matching zero requests (e.g. after a
    frontend refactor changes the prefill query's URL shape) would let
    this test pass for the wrong reason (nothing intercepted, prefill
    just never loaded for some other reason), not the one it claims to
    prove."""
    intercepted = {"count": 0, "methods": []}

    def _fail_prefill(route):
        intercepted["count"] += 1
        intercepted["methods"].append(route.request.method)
        route.fulfill(status=503, content_type="application/json", body="{}")

    page = live_context.new_page()
    page.route("**/rest/v1/funnel_records*", _fail_prefill)
    sign_in_via_browser(page, DEMO_NORTHBOUND_EMAIL, demo_credentials[DEMO_NORTHBOUND_EMAIL])
    page.wait_for_selector("#authenticated-shell:not([hidden])", timeout=30_000)

    page.click('a[data-route="predict"]')
    page.wait_for_selector(".prefill-picker .panel-error", timeout=15_000)
    assert "שגיאה בטעינת הדוגמאות" in page.text_content(".prefill-picker .panel-error")

    assert intercepted["count"] >= 1, (
        "the prefill route handler never fired -- the 'panel-error' above did not "
        "actually come from the injected failure this test claims to prove"
    )
    assert all(m == "GET" for m in intercepted["methods"]), (
        f"prefill interception fired for non-GET method(s): {intercepted['methods']} -- "
        "the shared-form prefill query is a read (supabase-prefill.js), not a write"
    )

    for field, value in FORM_VALUES.items():
        page.fill(f"#field-{field}", str(value))
        assert page.input_value(f"#field-{field}") == str(value), (
            f"#field-{field} did not accept manual input while prefill was down"
        )
    page.check(".context-confirmation input[type=checkbox]")
    assert page.is_enabled(".submit-button"), "submit button disabled despite a fully valid manual form"
    page.click(".submit-button")

    page.wait_for_selector(".prediction-panel-p2 .prediction-primary", timeout=15_000)
    primary_text = page.text_content(".prediction-panel-p2 .prediction-primary")
    assert primary_text and "תחזית" in primary_text, (
        f"manual submission with prefill down did not produce a real prediction: {primary_text!r}"
    )
