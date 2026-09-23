"""Phase 12 checkpoint 4 (PHASE12.md CP4, P12-D9, P12-D14) -- the five
model-backed capabilities and the two Supabase-backed insight routes, all
against the real deployed service: Overview, P2/P3/P4, P4S (0-100),
Budget and Follow-up all return a real number; `model_version` in the
five model responses matches BOTH the tracked artifacts (`models/*.meta
.json` on origin/main) AND `business_facts.json.model_versions` (P12-D14);
all seven routes are checked for schema and behavior via the real
`app.schemas` response models. P12-D9's own gate -- positive evidence,
not just the absence of sec 6.1c's degraded strings -- is satisfied for
P2, P4S and Budget by driving the real browser through a real sign-in and
a real submit, capturing the EXACT network response that produced what's
on screen, and independently reconstructing the four D9 layers' expected
text from that same response plus the live `business_facts.json`, using
the identical formatting rules `app/static/js/format.js` and each
screen's own `buildD9*`/`renderSummaryRecommendation` call site use
(cited by file:line throughout).

`test_00_funnel_payload_is_in_domain_for_every_task` is the one exception:
a local, credential-free check (no network, no `demo_credentials`) that
FORM_VALUES/EARLY_FUNNEL_PAYLOAD sit inside every task's real ood_bounds
on origin/main. Every other test in this file (all ten) needs
demo-northbound's real credentials and therefore prompts for
`demo_credentials` -- per P12-D3's own division of labor, Claude prepares
and reviews this file but does not run those; the user runs `pytest -s
live/test_03_capabilities.py` and provides the (censored) output as
evidence.
"""
from __future__ import annotations

import json
import math
import subprocess
import sys
import time
from pathlib import Path

import httpx
import pytest
from playwright.sync_api import TimeoutError as PlaywrightTimeoutError

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))
from app import schemas  # noqa: E402

from conftest import (
    DEMO_NORTHBOUND_EMAIL,
    LIVE_BASE_URL,
    Secret,
    sign_in_via_api,
    sign_in_via_browser,
)

# ---------------------------------------------------------------------------
# A single in-domain, business-rule-valid payload shared by every P2/P3/P4
# route in this file. Chosen inside the INTERSECTION of P2/P3/P4's own
# ood_bounds (models/P2.meta.json, P3.meta.json, P4.meta.json on
# origin/main, read below and diffed against these exact numbers) --
# not eyeballed once and trusted to still hold, but re-verified every run
# by test_00_funnel_payload_is_in_domain_for_every_task below, since an
# OOD hit would silently turn every "real number" claim in this file into
# a null-field response instead.
# ---------------------------------------------------------------------------

FORM_VALUES = {
    "ad_budget": 5000, "num_leads": 100, "leads_answered": 60,
    "followup_1": 55, "followup_2": 45, "followup_3": 35, "followup_4": 25, "followup_5": 15,
    "closed": 5, "calls_to_closed": 4, "calls_to_not_closed": 3, "customer_acquisition_cost": 1000,
}
# validation.js's own deriveNotClosed() (followup_5 - closed) -- the
# frontend computes this itself from the 12 fields above; the two
# httpx-only tests below must send it explicitly since they bypass the
# browser entirely.
FUNNEL_PAYLOAD = {**FORM_VALUES, "not_closed": FORM_VALUES["followup_5"] - FORM_VALUES["closed"]}
EARLY_FUNNEL_PAYLOAD = {k: FORM_VALUES[k] for k in ("ad_budget", "num_leads", "leads_answered", "followup_1")}

# test_p2_d9_layers_show_live_evidence's own wait for the shared form's
# predict.js:808 Promise.all([ltv, upsell, referral, facts.init()]) to
# settle -- P2's panel cannot render before ALL FOUR resolve, referral
# included. A real focused run (2026-09-23) timed out at the original 15s
# bound waiting on this exact selector, before any D9/model_version
# assertion ever ran, reproduced when the test ran alone (not explained
# by the combined-directory run's cross-file test reordering). ⚠ The
# Promise.all above explains why P2's panel CAN be delayed by referral --
# it does NOT by itself establish that referral (as opposed to some other
# request, or an error state that never resolved) was the actual cause of
# THIS timeout; that diagnosis is exactly what the try/except diagnostics
# below exist to produce on the next run, not something already proven
# here. The bound reused below (45s = 3x the original 15s) matches CP6's
# own fix for its two waits on this identical Promise.all
# (live/test_05_edge_cases.py's PREDICT_PROMISE_ALL_WAIT_MS, derived
# there from predict/referral's CP5 warm-latency measurement of 9.750s in
# isolation) -- reused for consistency since it is the same code path,
# not re-derived independently.
PREDICT_PROMISE_ALL_WAIT_MS = 45_000

# Local, pre-network validation against the real request schemas
# (app/schemas.py) -- a payload mistake fails here, immediately, instead
# of burning a live request against the deployed service.
schemas.FunnelInput(**FUNNEL_PAYLOAD)
schemas.EarlyFunnelInput(**EARLY_FUNNEL_PAYLOAD)

# task -> (meta.json stem, response schema, request path)
MODEL_ROUTES = {
    "P2": ("P2", schemas.LtvPrediction, "/api/predict/ltv"),
    "P3": ("P3", schemas.PropensityPrediction, "/api/predict/upsell"),
    "P4": ("P4", schemas.PropensityPrediction, "/api/predict/referral"),
    "P4S": ("P4S", schemas.SuperCustomerPrediction, "/api/predict/super-customer"),
}


def _meta_json(task: str) -> dict:
    """The TRACKED artifact's full meta.json from origin/main -- not the
    local working tree, same anchor as test_02_rls_assets.py's own git
    blob reads (render.yaml pins deployment to branch: main)."""
    blob = subprocess.run(
        ["git", "show", f"origin/main:models/{task}.meta.json"],
        cwd=REPO_ROOT, capture_output=True, check=True,
    ).stdout
    return json.loads(blob)


def _meta_model_version(task: str) -> str:
    return _meta_json(task)["model_version"]


def _bearer_headers(token: Secret) -> dict[str, str]:
    return {"Authorization": f"Bearer {token.reveal()}"}


@pytest.fixture(scope="module")
def northbound_token(demo_credentials: dict[str, Secret]) -> Secret:
    return sign_in_via_api(DEMO_NORTHBOUND_EMAIL, demo_credentials[DEMO_NORTHBOUND_EMAIL])


@pytest.fixture(scope="module")
def live_business_facts() -> dict:
    return httpx.get(f"{LIVE_BASE_URL}/business_facts.json", timeout=30).json()


def test_00_funnel_payload_is_in_domain_for_every_task():
    """Local, credential-free self-check (no network, no northbound_token)
    -- run first (definition order): reads each task's real ood_bounds
    from models/*.meta.json on origin/main and checks FORM_VALUES (via
    FUNNEL_PAYLOAD, which only adds the derived not_closed field) /
    EARLY_FUNNEL_PAYLOAD directly against min/max, arithmetically.

    Deliberately does NOT call the live model routes -- that would just
    re-run the exact four POSTs test_model_route_... already makes and
    infer domain membership indirectly from in_training_domain, which
    only proves the CURRENT payload happens to be in-domain, not that
    THIS check independently verified it against the real bounds."""
    for task in ("P2", "P3", "P4"):
        ood_bounds = _meta_json(task)["ood_bounds"]
        for field, bounds in ood_bounds.items():
            value = FUNNEL_PAYLOAD[field]
            assert bounds["min"] <= value <= bounds["max"], (
                f"{task}.{field}={value} outside ood_bounds "
                f"[{bounds['min']}, {bounds['max']}] -- adjust FORM_VALUES"
            )
    ood_bounds = _meta_json("P4S")["ood_bounds"]
    for field, bounds in ood_bounds.items():
        value = EARLY_FUNNEL_PAYLOAD[field]
        assert bounds["min"] <= value <= bounds["max"], (
            f"P4S.{field}={value} outside ood_bounds "
            f"[{bounds['min']}, {bounds['max']}] -- adjust EARLY_FUNNEL_PAYLOAD"
        )


@pytest.mark.parametrize("task", ["P2", "P3", "P4", "P4S"])
def test_model_route_returns_real_number_with_correct_model_version(task, northbound_token, live_business_facts):
    """PHASE12.md CP4 + P12-D14: the five model responses return a real
    (non-null) prediction, and model_version matches BOTH the tracked
    artifact on origin/main AND business_facts.json.model_versions --
    three-way agreement, not just "the response has SOME model_version
    string"."""
    meta_stem, schema_cls, path = MODEL_ROUTES[task]
    payload = EARLY_FUNNEL_PAYLOAD if task == "P4S" else FUNNEL_PAYLOAD
    response = httpx.post(
        f"{LIVE_BASE_URL}{path}", headers=_bearer_headers(northbound_token), json=payload, timeout=30,
    )
    assert response.status_code == 200, f"{task}: {response.status_code} {response.text}"
    parsed = schema_cls.model_validate(response.json())
    assert parsed.in_training_domain is True

    if task == "P2":
        assert parsed.point_estimate is not None and parsed.lower_bound is not None and parsed.upper_bound is not None
    else:
        assert parsed.event_probability is not None

    tracked_version = _meta_model_version(meta_stem)
    facts_version = live_business_facts["model_versions"][meta_stem]
    assert parsed.model_version == tracked_version == facts_version, (
        f"{task} model_version disagreement: live response={parsed.model_version!r}, "
        f"tracked artifact={tracked_version!r}, business_facts.json={facts_version!r}"
    )


def test_budget_simulation_returns_real_numbers_and_correct_model_version(northbound_token, live_business_facts):
    """PHASE12.md CP4 + P12-D14: GET /api/simulate/budget, no body
    (DESIGN.md §6.1א). Four strategies, each with a real point_estimate,
    and model_version three-way agreement (P6)."""
    response = httpx.get(
        f"{LIVE_BASE_URL}/api/simulate/budget", headers=_bearer_headers(northbound_token), timeout=30,
    )
    assert response.status_code == 200, response.text
    parsed = schemas.BudgetSimulation.model_validate(response.json())
    assert len(parsed.strategies) == 4
    for strategy in parsed.strategies:
        assert strategy.point_estimate is not None
        assert strategy.in_training_domain is True

    tracked_version = _meta_model_version("P6")
    facts_version = live_business_facts["model_versions"]["P6"]
    assert parsed.model_version == tracked_version == facts_version, (
        f"P6 model_version disagreement: live response={parsed.model_version!r}, "
        f"tracked artifact={tracked_version!r}, business_facts.json={facts_version!r}"
    )


def test_insights_budget_tiers_schema_and_behavior(northbound_token):
    """PHASE12.md CP4: Overview's own source route -- schema-valid, and
    at least one named tier (Low/Mid/High) carries a real, non-null
    conversion_rate (DESIGN.md §6.1's Overview row needs at least one
    candidate for "the level with the highest conversion rate")."""
    response = httpx.get(
        f"{LIVE_BASE_URL}/api/insights/budget-tiers", headers=_bearer_headers(northbound_token), timeout=30,
    )
    assert response.status_code == 200, response.text
    parsed = schemas.BudgetTiersResponse.model_validate(response.json())
    named_with_rate = [t for t in parsed.tiers if t.budget_tier is not None and t.conversion_rate is not None]
    assert named_with_rate, f"no named tier carries a real conversion_rate: {parsed.tiers}"


def test_insights_followup_schema_and_behavior(northbound_token):
    """PHASE12.md CP4: Follow-up's two charts -- schema-valid, and both
    parts actually available (not degraded to PartUnavailable), so the
    two D9 rows (נשירה, calls_to_closed) have real content to show."""
    response = httpx.get(
        f"{LIVE_BASE_URL}/api/insights/followup", headers=_bearer_headers(northbound_token), timeout=30,
    )
    assert response.status_code == 200, response.text
    parsed = schemas.FollowupResponse.model_validate(response.json())
    assert parsed.stages.status == "available", getattr(parsed.stages, "error", None)
    assert parsed.calls_to_closed.status == "available", getattr(parsed.calls_to_closed, "error", None)
    assert parsed.calls_to_closed.data.population_n > 0


# ---------------------------------------------------------------------------
# P12-D9 -- positive evidence: the real browser's D9 layers for P2, P4S
# and Budget, reconstructed from the EXACT captured network response(s)
# that produced them plus the live business_facts.json, using the same
# formatting rules and literal wording as the actual rendering code
# (cited by file:line below).
# ---------------------------------------------------------------------------

_D9_EXPECTED_KEYS = ["answer", "meaning", "action", "caveat"]
_D9_EXPECTED_LABELS = ["תשובה", "מה זה אומר", "מה כדאי לעשות", "חשוב לדעת"]
_LTR_START, _LTR_END = chr(0x2066), chr(0x2069)


def _ltr(text) -> str:
    return f"{_LTR_START}{text}{_LTR_END}"


def _js_round(value: float) -> int:
    """JS Math.round: rounds half AWAY FROM ZERO for positive values --
    NOT Python's banker's-rounding round(). Every value rounded in this
    file (point_estimate, bounds, event_probability*100) is non-negative
    by schema (Field(ge=0)), so this single floor(x+0.5) form is exact
    for every case actually reached here."""
    return math.floor(value + 0.5)


def _format_number(value: float, decimals: int = 0) -> str:
    """he-IL Intl.NumberFormat grouping (format.js's own GROUPED()) --
    comma thousands separator, period decimal, verified in format.js's
    own header comment against a real runtime. Python's default ','
    thousands/'.' decimal grouping is byte-identical for these digits."""
    return f"{value:,.{decimals}f}"


def _format_percent(fraction: float, decimals: int = 2) -> str:
    return f"{_format_number(fraction * 100, decimals)}%"


def _format_currency(value: float, decimals: int = 0) -> str:
    return f"₪{_format_number(value, decimals)}"


def _read_d9_layers(page, scope_selector: str):
    return page.eval_on_selector_all(
        f"{scope_selector} .summary-recommendation .summary-layer",
        """(elements) => elements.map((element) => {
            const keyClass = [...element.classList].find(
                (c) => c.startsWith("summary-layer-")
            );
            return {
                key: keyClass ? keyClass.replace("summary-layer-", "") : null,
                label: element.querySelector(".summary-layer-label")?.textContent ?? "",
                text: element.querySelector(".summary-layer-text")?.textContent ?? "",
            };
        })""",
    )


def _assert_well_formed_d9_layers(layers):
    assert [layer["key"] for layer in layers] == _D9_EXPECTED_KEYS
    assert [layer["label"] for layer in layers] == _D9_EXPECTED_LABELS
    for layer in layers:
        assert layer["text"], f"layer {layer['key']!r} has empty text"


def _open_predict(page):
    page.click('a[data-route="predict"]')
    page.wait_for_selector("#field-ad_budget")


def _fill_predict(page, values):
    for field, value in values.items():
        page.fill(f"#field-{field}", str(value))


def _open_p4s(page):
    page.click('a[data-route="super-customer"]')
    page.wait_for_selector("#p4s-field-ad_budget")


def _fill_p4s(page, values):
    for field, value in values.items():
        page.fill(f"#p4s-field-{field}", str(value))


def test_p2_d9_layers_show_live_evidence(live_context, demo_credentials, live_business_facts):
    """PHASE12.md CP4, P12-D9 gate for P2: signs in for real, submits the
    real shared form, captures the exact POST /api/predict/ltv response
    that produced the on-screen panel, and checks the four D9 layers
    against that response's own numbers -- not a second, independent
    call that could (in principle) diverge.

    Diagnostic-only note, 2026-09-23: a real focused run of this test
    alone timed out at the original 15s bound waiting for
    '.prediction-panel-p2 .summary-recommendation', before reaching any
    D9/model_version assertion -- see PREDICT_PROMISE_ALL_WAIT_MS above
    for the mechanism that can explain a delay (predict.js's shared
    Promise.all, same code path as CP6's own diagnosed timeout). ⚠ That
    mechanism is not itself proof of what actually delayed THIS run --
    which request, or whether an error state rendered instead of a
    result -- only a plausible explanation for why a longer, still-finite
    wait is reasonable. The wait below now uses that bound, and, only if
    a Playwright TimeoutError is still raised, prints the same kind of
    structural network/panel diagnostics CP6's
    test_path_failure_shows_error_and_recovers_on_retry already
    established -- method/URL/status and panel class presence only,
    never a request/response body, header, or anything from
    #login-form -- specifically so the next run's actual cause can be
    read off directly, not inferred. Any other exception is left
    unlabeled and re-raised as itself, not misreported as a timeout."""
    captured = {}
    network_log: list[str] = []
    nav_start = time.monotonic()
    page = live_context.new_page()

    def _on_response(response):
        if response.url.endswith("/api/predict/ltv") and response.request.method == "POST":
            captured["ltv"] = response.json()

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
        each panel is in, never the panel's own text content."""
        lines = []
        for name in ("p2", "p3", "p4"):
            selector = f".prediction-panel-{name}"
            exists = page.query_selector(selector) is not None
            has_error = page.query_selector(f"{selector} .panel-error") is not None
            has_primary = page.query_selector(f"{selector} .prediction-primary") is not None
            lines.append(f"  {selector}: exists={exists} panel-error={has_error} prediction-primary={has_primary}")
        return "\n".join(lines)

    page.on("response", _on_response)
    page.on("response", _log_response)
    page.on("requestfailed", _log_request_failed)
    sign_in_via_browser(page, DEMO_NORTHBOUND_EMAIL, demo_credentials[DEMO_NORTHBOUND_EMAIL])
    page.wait_for_selector("#authenticated-shell:not([hidden])", timeout=30_000)

    _open_predict(page)
    _fill_predict(page, FORM_VALUES)
    page.check(".context-confirmation input[type=checkbox]")
    nav_start = time.monotonic()  # reset: the window that matters is from submit, not from page load
    page.click(".submit-button")

    # Races the success selector against .panel-error (a single
    # comma-separated CSS selector matches whichever appears first, same
    # querySelector semantics Playwright uses under the hood) -- a real
    # server-side error should fail this test immediately with what
    # actually happened, not sit through the full 45s waiting for a
    # result that predict.js will never render once ANY of ltv/upsell/
    # referral's Promise.all members rejects or resolves to an error
    # panel (predict.js:829-833, blocked/stale aside -- a hard failure on
    # any of the three still lands here since submitState only ever
    # becomes "done").
    try:
        page.wait_for_selector(
            ".prediction-panel-p2 .summary-recommendation, .prediction-panel-p2 .panel-error",
            timeout=PREDICT_PROMISE_ALL_WAIT_MS,
        )
    except PlaywrightTimeoutError:
        print(
            "\ntest_p2_d9_layers_show_live_evidence diagnostics (Playwright TimeoutError -- neither "
            ".summary-recommendation nor .panel-error appeared on .prediction-panel-p2 after "
            f"{PREDICT_PROMISE_ALL_WAIT_MS}ms):\n"
            + "\n".join(network_log or ["  (no matching network events captured)"])
            + "\npanel state at the moment of timeout:\n"
            + _panel_snapshot(page)
        )
        raise

    if page.query_selector(".prediction-panel-p2 .panel-error") is not None:
        error_text = page.text_content(".prediction-panel-p2 .panel-error")
        pytest.fail(
            "test_p2_d9_layers_show_live_evidence: .prediction-panel-p2 rendered "
            f".panel-error instead of a result -- error text: {error_text!r}\n"
            + "\n".join(network_log or ["  (no matching network events captured)"])
            + "\npanel state at the moment of failure:\n"
            + _panel_snapshot(page)
        )

    assert "ltv" in captured, "POST /api/predict/ltv was never captured -- submit did not fire it"
    d = schemas.LtvPrediction.model_validate(captured["ltv"])
    assert d.in_training_domain is True

    # business_facts.json's own model_versions.P2 must match THIS live
    # response for facts.getLtvLeverage() to unlock the leverage-dependent
    # meaning/action wording (facts.js:178) -- CP4's own model_version
    # criterion, re-asserted here since the D9 text branches on it.
    assert live_business_facts["model_versions"]["P2"] == d.model_version, (
        "business_facts.json.model_versions.P2 does not match this live "
        "response -- D9 would render the DEGRADED wording, not the "
        "healthy branch this test checks"
    )
    # The healthy "meaning"/"action" text below is FIXED prose naming
    # calls_to_closed specifically (predict.js:585-586) -- it is not
    # templated from leverage.dominant_feature at all. So this must
    # independently confirm the live asset's dominant_feature really IS
    # calls_to_closed (and that all three algorithms agree, the claim
    # the leverage tip itself makes: "לפי שלושת המודלים שנבחנו") --
    # not just that SOME dominant_feature is present, which would let a
    # future retrain silently make this hardcoded text factually wrong
    # while every assertion below still passed.
    ltv = live_business_facts["ltv"]
    assert ltv.get("dominant_feature") == "calls_to_closed", (
        f"ltv.dominant_feature={ltv.get('dominant_feature')!r} -- the healthy D9 "
        "meaning/action text below hardcodes 'calls_to_closed' as the leading "
        "signal and is only correct when this is calls_to_closed"
    )
    rank_1_by_algorithm = ltv["rank_1_by_algorithm"]
    for algorithm, rank_1 in rank_1_by_algorithm.items():
        assert rank_1["feature"] == "calls_to_closed", (
            f"ltv.rank_1_by_algorithm.{algorithm}.feature={rank_1['feature']!r}, "
            "not calls_to_closed -- the three algorithms no longer agree"
        )

    rounded = _js_round(d.point_estimate)
    lower = _js_round(d.lower_bound)
    upper = _js_round(d.upper_bound)
    # predict.js:592-596 (buildP2Panel, healthy/leverage-present branch)
    expected = {
        "answer": f"תחזית: {_format_number(rounded)} חודשים, טווח: {_format_number(lower)}–{_format_number(upper)} חודשים",
        "meaning": (
            "הערכה לאורך החיים הכולל של לקוח שנרכש בקמפיין שהסתיים. במודלים "
            "שאומנו על הנתונים ההיסטוריים, מספר השיחות הממוצע עד סגירה היה "
            "האות החזק ביותר, אך אינו מוכיח שיותר שיחות מאריכות קשר"
        ),
        "action": (
            "כשהקלט בתחום ואינו מסומן בתמיכה חלקית, להשתמש באומדן בזהירות "
            "לתכנון ופילוח; לבחון שינוי במדיניות השיחות רק בניסוי שמודד "
            "שימור בפועל"
        ),
        "caveat": (
            "זהו טווח אי־ודאות, לא הבטחה. ב־OOD אין תחזית; בתמיכה חלקית אין "
            "החלטת פילוח לפי המודל בלבד"
        ),
    }

    layers = _read_d9_layers(page, ".prediction-panel-p2")
    _assert_well_formed_d9_layers(layers)
    rendered = {layer["key"]: layer["text"] for layer in layers}
    assert rendered == expected, f"P2 D9 layers != expected: {rendered!r} != {expected!r}"


def test_p4s_d9_layers_show_live_evidence(live_context, demo_credentials, live_business_facts):
    """PHASE12.md CP4, P12-D9 gate for P4S: signs in for real, submits
    the real P4S form, captures the exact POST /api/predict/super-customer
    response, and checks the four D9 layers against that response's own
    numbers plus the live business_facts.json.super_customer_profile
    (getSuperCustomerProfile() has no model_version gate -- facts.js:192-198)."""
    captured = {}
    page = live_context.new_page()

    def _on_response(response):
        if response.url.endswith("/api/predict/super-customer") and response.request.method == "POST":
            captured["p4s"] = response.json()

    page.on("response", _on_response)
    sign_in_via_browser(page, DEMO_NORTHBOUND_EMAIL, demo_credentials[DEMO_NORTHBOUND_EMAIL])
    page.wait_for_selector("#authenticated-shell:not([hidden])", timeout=30_000)

    _open_p4s(page)
    _fill_p4s(page, EARLY_FUNNEL_PAYLOAD)
    page.check(".context-confirmation input[type=checkbox]")
    page.click(".submit-button")
    page.wait_for_selector(".prediction-panel-p4s .summary-recommendation", timeout=15_000)

    assert "p4s" in captured, "POST /api/predict/super-customer was never captured"
    d = schemas.SuperCustomerPrediction.model_validate(captured["p4s"])
    assert d.in_training_domain is True

    profile = live_business_facts["super_customer_profile"]
    assert profile, "business_facts.json.super_customer_profile missing -- meaning would degrade"

    # super-customer.js:557-558,569-575 (buildP4SPanel, healthy branch)
    score = _js_round(d.event_probability * 100)
    base_rate_pct = _format_percent(d.base_rate)
    pct1 = _format_percent(profile["pct_of_purchased"], decimals=1)
    pct2 = _format_percent(profile["pct_of_total_profit"], decimals=1)
    cac_super = _format_currency(profile["cac_super_mean"], decimals=2)
    cac_population = _format_currency(profile["cac_population_mean"], decimals=2)
    pct3 = _format_percent(profile["cac_savings_pct"], decimals=1)
    roc_auc = _format_number(d.metrics.holdout.roc_auc, decimals=3)
    pr_auc = _format_number(d.metrics.holdout.pr_auc, decimals=3)

    expected = {
        "answer": f"ציון לקוח-על: {_ltr(score)} מתוך 100, מול שיעור הבסיס שחזר: {base_rate_pct}",
        "meaning": (
            f"היסטורית, לקוחות-על היו {pct1} מהרוכשים, יצרו {pct2} מהרווח "
            f"המצטבר; עלות הרכישה הממוצעת שלהם הייתה {cac_super}, לעומת "
            f"{cac_population}, כלומר נמוכה ב-{pct3}. זהו פרופיל תיאורי"
        ),
        "action": (
            "רק כשהקלט בתחום, אין סימון תמיכה חלקית והנטייה מעל הבסיס, "
            "אפשר להשתמש בציון כאות מסייע לבדיקה ידנית של רוכש ידוע. בכל "
            "מצב אחר אין תעדוף לפי המודל"
        ),
        "caveat": (
            f"תקף רק אחרי רכישה ידועה, מעקב 1 וחלון חודשי סגור. "
            f"{_ltr(d.model_algorithm)} נמדד ב-Holdout עם ROC-AUC {roc_auc} "
            f"ו-PR-AUC {pr_auc}; הציון הוא אות מסייע בלבד, לא תעדוף אוטומטי"
        ),
    }

    layers = _read_d9_layers(page, ".prediction-panel-p4s")
    _assert_well_formed_d9_layers(layers)
    rendered = {layer["key"]: layer["text"] for layer in layers}
    assert rendered == expected, f"P4S D9 layers != expected: {rendered!r} != {expected!r}"


def test_budget_d9_layers_show_live_evidence(live_context, demo_credentials, live_business_facts):
    """PHASE12.md CP4, P12-D9 gate for Budget: signs in for real,
    navigates to the Budget screen, and checks the four D9 layers against
    the live business_facts.json.budget_backtest (budget.js:263-296) --
    the healthy branch requires model_versions.P6 to match the live
    GET /api/simulate/budget response AND both backtest["500"]/["2000"]
    to be present (facts.js:185-190)."""
    captured = {}
    page = live_context.new_page()

    def _on_response(response):
        if response.url.endswith("/api/simulate/budget") and response.request.method == "GET":
            captured["budget"] = response.json()

    page.on("response", _on_response)
    sign_in_via_browser(page, DEMO_NORTHBOUND_EMAIL, demo_credentials[DEMO_NORTHBOUND_EMAIL])
    page.wait_for_selector("#authenticated-shell:not([hidden])", timeout=30_000)

    page.click('a[data-route="budget"]')
    page.wait_for_selector("#screen-budget .summary-recommendation", timeout=15_000)

    assert "budget" in captured, "GET /api/simulate/budget was never captured"
    sim = schemas.BudgetSimulation.model_validate(captured["budget"])

    backtest = live_business_facts.get("budget_backtest") or {}
    assert live_business_facts["model_versions"]["P6"] == sim.model_version, (
        "business_facts.json.model_versions.P6 does not match this live "
        "GET /api/simulate/budget response -- D9 would render the "
        "DEGRADED wording, not the healthy backtest branch this test checks"
    )
    assert "500" in backtest and "2000" in backtest, (
        f"budget_backtest is missing the 500/2000 keys buildD9() requires: {sorted(backtest)}"
    )

    # buildD9()'s "answer"/"meaning" text below is FIXED prose asserting,
    # as fact, that 100x500 ranks first, 25x2000 ranks second, and the
    # two overlap (budget.js:279-283) -- it does not read sim.strategies
    # or sim.top_two_overlap at all to decide what to say. So this must
    # independently confirm those claims against the ACTUAL captured
    # `sim` response; without this, a future live ranking change would
    # make the hardcoded text factually wrong while the DOM-equality
    # check below still passed (it only proves the DOM matches the
    # hardcoded string, not that the string is still true).
    assert sim.top_two_overlap is True, (
        f"sim.top_two_overlap={sim.top_two_overlap!r} -- the hardcoded D9 text "
        "below asserts the top two strategies overlap"
    )
    ranked = sorted(sim.strategies, key=lambda s: s.rank)
    top_two = [(s.strategy_id, s.rank) for s in ranked[:2]]
    assert top_two == [("100x500", 1), ("25x2000", 2)], (
        f"live top two strategies by rank are {top_two!r}, not "
        "[('100x500', 1), ('25x2000', 2)] -- the hardcoded D9 text below "
        "names these two specific strategies in this specific order"
    )

    b500, b2000 = backtest["500"], backtest["2000"]
    ratio = _format_number(b500["predicted_per_customer"] / b500["actual_mean_per_customer"], decimals=2)
    n2000 = _format_number(b2000["n_train_at_level"])

    # budget.js:279-283 (buildD9, backtest-present branch)
    expected = {
        "answer": "100×500 מדורגת ראשונה מספרית, אך אינה המלצה לפעולה; שתי המובילות חופפות ובדיקת העבר של רמת 500 חלשה מאוד",
        "meaning": f"הדירוג לבדו אינו מכריע: טווחי 100×500 ו־25×2,000 חופפים, ובבדיקת עבר התחזית לרמת 500 הייתה גבוהה פי {_ltr(ratio)} מהתוצאה בפועל",
        "action": f"לא לבצע הקצאה מלאה לפי הדירוג. אם בוחנים אחת מארבע החלופות, לבצע פיילוט מבוקר של 25×2,000, שלה {_ltr(n2000)} שורות אימון ובדיקת עבר קרובה יותר",
        "caveat": "הסכומים הם רווח מצטבר צפוי ומניחים רשומות עצמאיות ואדיטיביות; אינם רווח בחודש הבא, אינם השפעה סיבתית ואינם הבטחה",
    }

    layers = _read_d9_layers(page, "#screen-budget")
    _assert_well_formed_d9_layers(layers)
    rendered = {layer["key"]: layer["text"] for layer in layers}
    assert rendered == expected, f"Budget D9 layers != expected: {rendered!r} != {expected!r}"
