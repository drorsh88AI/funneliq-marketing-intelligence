"""Phase 11 checkpoint 12 (PHASE11.md §ח, criterion row CP12) -- captures
real, live-rendered screenshots for the screen×state matrix DESIGN.md
§9.2/§9.3 deferred from phase 10 ("המימוש האמיתי מרונדר בדפדפן עם תגובה
דטרמיניסטית", not a mockup). Reuses checkpoint 11's own zero-external-
network harness (conftest.py) unchanged -- same real uvicorn subprocess,
same route()-level mocking, same fixtures.py builders.

⚠ NOT a falsification-case test file (unlike test_00-test_08): this file
is deliberately named so it is NOT picked up by a bare `pytest e2e/`
(pytest's default python_files pattern only auto-discovers `test_*.py`/
`*_test.py`; explicitly pointing pytest AT this file's path still
collects it -- the pattern only gates implicit directory-walk discovery).
Run explicitly:
    python -m pytest e2e/capture_state_matrix.py -s -v
Each function's own assertion exists only to fail loudly if the state
never actually rendered (a blank/wrong screenshot would otherwise be
silently "successful") -- these are not meant as a second falsification
suite; CP11 already owns that.

Cell-selection reasoning (recorded here once, not re-derived per
function): DESIGN.md §2.1's own per-screen table decides which cells are
real for THIS run, cross-referenced against §9.2/§9.3's list of what
phase 10 deliberately deferred. Three deliberate exclusions, so a later
reader does not mistake them for oversights:
  - Login's own `loading` cell is the SAME event as the bootstrap
    `loading` cell (bootstrap.js fetches /api/config before the Login
    screen is even interactive) -- captured once, referenced twice.
  - P4S's own `empty` cell (no example, manual/independent entry) is the
    SAME state DESIGN.md §9.3 already says `p4s.jpg` (phase 10) covers
    -- not recaptured here.
  - 401/403/503/500 are bootstrap/shell-level branches (IA.md §9.3), not
    per-screen states -- one screenshot each, not one per screen.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import fixtures as fx
from conftest import (
    install_auth_mocks,
    install_prefill_mock,
    route_deferred,
    route_json,
    route_status,
    sign_in,
    sign_in_and_wait,
)

STATES_DIR = Path(__file__).resolve().parent.parent / "docs" / "design" / "states"
STATES_DIR.mkdir(parents=True, exist_ok=True)

PREDICT_VALUES = {
    "ad_budget": "5000", "num_leads": "100", "leads_answered": "80",
    "followup_1": "70", "followup_2": "60", "followup_3": "50",
    "followup_4": "40", "followup_5": "30", "closed": "10",
    "calls_to_closed": "3", "calls_to_not_closed": "2",
    "customer_acquisition_cost": "500",
}

SHARED_FORM_EXAMPLE_ROW = {
    "source_row_id": 1, "ad_budget": 4000, "num_leads": 90, "leads_answered": 70, "closed": 8,
    "followup_1": 60, "followup_2": 50, "followup_3": 40, "followup_4": 30, "followup_5": 20,
    "calls_to_closed": 3, "calls_to_not_closed": 2, "customer_acquisition_cost": 450,
}
P4S_EXAMPLE_ROW = {"source_row_id": 1, "ad_budget": 4000, "num_leads": 90, "leads_answered": 70, "followup_1": 60}


def shoot(page, name: str) -> None:
    page.screenshot(path=str(STATES_DIR / f"{name}.jpg"), type="jpeg", quality=90, full_page=True)


# ---------------------------------------------------------------------
# Bootstrap / shell-level (IA.md §9.3) -- one screenshot per branch,
# shared across every screen (not per-screen states).
# ---------------------------------------------------------------------

def test_bootstrap_loading(mocked_context):
    """Also Login's own `loading` cell (§2.1) -- the same fetch."""
    config_route = route_deferred(mocked_context, "**/api/config")
    page = mocked_context.new_page()
    page.goto(mocked_context.e2e_base_url)  # type: ignore[attr-defined]
    page.wait_for_selector("#loading:not([hidden])", timeout=10_000)
    shoot(page, "bootstrap-loading")
    config_route.release(payload={"supabase_url": "https://supabase.invalid", "supabase_publishable_key": "e2e-dummy-publishable-key"})


def test_bootstrap_config_error(mocked_context):
    route_status(mocked_context, "**/api/config", 500)
    page = mocked_context.new_page()
    page.goto(mocked_context.e2e_base_url)  # type: ignore[attr-defined]
    page.wait_for_selector("#config-error:not([hidden])", timeout=10_000)
    shoot(page, "bootstrap-config-error")


def test_bootstrap_401_session_expired(mocked_page, mocked_context):
    route_json(mocked_context, "**/api/me", fx.api_me())
    route_json(mocked_context, "**/api/insights/budget-tiers", fx.budget_tiers_response())
    route_json(mocked_context, "**/rest/v1/funnel_records*", [])
    sign_in_and_wait(mocked_page, mocked_context)
    mocked_page.click('a[data-route="predict"]')
    mocked_page.wait_for_selector("#field-ad_budget")
    for field, value in PREDICT_VALUES.items():
        mocked_page.fill(f"#field-{field}", value)
    mocked_page.check(".context-confirmation input[type=checkbox]")
    route_status(mocked_context, "**/api/predict/ltv", 401)
    route_status(mocked_context, "**/api/predict/upsell", 401)
    route_status(mocked_context, "**/api/predict/referral", 401)
    mocked_page.click(".submit-button")
    mocked_page.wait_for_selector("#session-expired-notice:not([hidden])", timeout=10_000)
    shoot(mocked_page, "bootstrap-401")


def test_bootstrap_403_forbidden(mocked_page, mocked_context):
    install_auth_mocks(mocked_context)
    route_status(mocked_context, "**/api/me", 403)
    sign_in(mocked_page)
    mocked_page.wait_for_selector("#forbidden-notice:not([hidden])", timeout=10_000)
    shoot(mocked_page, "bootstrap-403")


def test_bootstrap_503_availability(mocked_page, mocked_context):
    install_auth_mocks(mocked_context)
    route_status(mocked_context, "**/api/me", 503)
    sign_in(mocked_page)
    mocked_page.wait_for_selector("#availability-error:not([hidden])", timeout=10_000)
    assert "503" not in mocked_page.text_content("#availability-error")  # human text only, no raw code
    shoot(mocked_page, "bootstrap-503")


def test_bootstrap_500_availability(mocked_page, mocked_context):
    install_auth_mocks(mocked_context)
    route_status(mocked_context, "**/api/me", 500)
    sign_in(mocked_page)
    mocked_page.wait_for_selector("#availability-error:not([hidden])", timeout=10_000)
    shoot(mocked_page, "bootstrap-500")


# ---------------------------------------------------------------------
# Login screen's OWN error (distinct from the bootstrap-level ones
# above -- a rejected password, form-local, session never touched).
# ---------------------------------------------------------------------

def test_login_signin_error(mocked_page, mocked_context):
    install_auth_mocks(mocked_context, sign_in_ok=False)
    sign_in(mocked_page, password="wrongpass")
    mocked_page.wait_for_selector("#login-error:not([hidden])", timeout=10_000)
    shoot(mocked_page, "login-signin-error")


# ---------------------------------------------------------------------
# Overview
# ---------------------------------------------------------------------

def test_overview_loading(mocked_page, mocked_context):
    install_auth_mocks(mocked_context)
    route_json(mocked_context, "**/api/me", fx.api_me())
    tiers_route = route_deferred(mocked_context, "**/api/insights/budget-tiers")
    sign_in(mocked_page)
    mocked_page.wait_for_selector("#screen-overview .panel-loading", timeout=10_000)
    shoot(mocked_page, "overview-loading")
    tiers_route.release(payload=fx.budget_tiers_response())


def test_overview_error(mocked_page, mocked_context):
    install_auth_mocks(mocked_context)
    route_json(mocked_context, "**/api/me", fx.api_me())
    route_status(mocked_context, "**/api/insights/budget-tiers", 500)
    sign_in(mocked_page)
    mocked_page.wait_for_selector("#screen-overview .panel-error:not([hidden])", timeout=10_000)
    shoot(mocked_page, "overview-error")


# ---------------------------------------------------------------------
# Shared prediction form (P2/P3/P4)
# ---------------------------------------------------------------------

def test_shared_form_loading(mocked_page, mocked_context):
    """§2.1's own `loading` cell for this screen: the example-prefill
    picker's own spinner -- not the submission itself, which the table
    does not call out as a separate loading state."""
    route_json(mocked_context, "**/api/me", fx.api_me())
    route_json(mocked_context, "**/api/insights/budget-tiers", fx.budget_tiers_response())
    sign_in_and_wait(mocked_page, mocked_context)
    prefill_route = route_deferred(mocked_context, "**/rest/v1/funnel_records*")
    mocked_page.click('a[data-route="predict"]')
    mocked_page.wait_for_selector(".prefill-picker-body .panel-loading", timeout=10_000)
    shoot(mocked_page, "shared-form-loading")
    prefill_route.release(payload=[SHARED_FORM_EXAMPLE_ROW])


def test_shared_form_empty_no_example(mocked_page, mocked_context):
    """No example loaded yet, input-details open, input-summary at 0
    progress -- distinct from shared-form.jpg (phase 10), which depicts
    the WITH-RESULTS state (§9.4)."""
    route_json(mocked_context, "**/api/me", fx.api_me())
    route_json(mocked_context, "**/api/insights/budget-tiers", fx.budget_tiers_response())
    install_prefill_mock(mocked_context, [SHARED_FORM_EXAMPLE_ROW])
    sign_in_and_wait(mocked_page, mocked_context)
    mocked_page.click('a[data-route="predict"]')
    mocked_page.wait_for_selector("#field-ad_budget", timeout=10_000)
    assert "0/12" in mocked_page.text_content(".input-summary")
    shoot(mocked_page, "shared-form-empty")


def test_shared_form_error_partial_panel(mocked_page, mocked_context):
    route_json(mocked_context, "**/api/me", fx.api_me())
    route_json(mocked_context, "**/api/insights/budget-tiers", fx.budget_tiers_response())
    route_json(mocked_context, "**/rest/v1/funnel_records*", [])
    sign_in_and_wait(mocked_page, mocked_context)
    route_status(mocked_context, "**/api/predict/ltv", 500)
    route_json(mocked_context, "**/api/predict/upsell", fx.propensity_prediction_success())
    route_json(mocked_context, "**/api/predict/referral", fx.propensity_prediction_success())
    mocked_page.click('a[data-route="predict"]')
    mocked_page.wait_for_selector("#field-ad_budget")
    for field, value in PREDICT_VALUES.items():
        mocked_page.fill(f"#field-{field}", value)
    mocked_page.check(".context-confirmation input[type=checkbox]")
    mocked_page.click(".submit-button")
    mocked_page.wait_for_selector(".prediction-panel-p3 .prediction-primary", timeout=10_000)
    assert mocked_page.query_selector(".prediction-panel-p2 .panel-error") is not None
    shoot(mocked_page, "shared-form-error")


def test_shared_form_ood(mocked_page, mocked_context):
    route_json(mocked_context, "**/api/me", fx.api_me())
    route_json(mocked_context, "**/api/insights/budget-tiers", fx.budget_tiers_response())
    route_json(mocked_context, "**/rest/v1/funnel_records*", [])
    sign_in_and_wait(mocked_page, mocked_context)
    route_json(mocked_context, "**/api/predict/ltv", fx.ltv_prediction_ood())
    route_json(mocked_context, "**/api/predict/upsell", fx.propensity_prediction_success())
    route_json(mocked_context, "**/api/predict/referral", fx.propensity_prediction_success())
    mocked_page.click('a[data-route="predict"]')
    mocked_page.wait_for_selector("#field-ad_budget")
    for field, value in PREDICT_VALUES.items():
        mocked_page.fill(f"#field-{field}", value)
    mocked_page.check(".context-confirmation input[type=checkbox]")
    mocked_page.click(".submit-button")
    mocked_page.wait_for_selector(".prediction-panel-p2 .ood-banner", timeout=10_000)
    shoot(mocked_page, "shared-form-ood")


# ---------------------------------------------------------------------
# P4S
# ---------------------------------------------------------------------

def test_p4s_loading(mocked_page, mocked_context):
    route_json(mocked_context, "**/api/me", fx.api_me())
    route_json(mocked_context, "**/api/insights/budget-tiers", fx.budget_tiers_response())
    sign_in_and_wait(mocked_page, mocked_context)
    prefill_route = route_deferred(mocked_context, "**/rest/v1/funnel_records*")
    mocked_page.click('a[data-route="super-customer"]')
    mocked_page.wait_for_selector(".prefill-picker-body .panel-loading", timeout=10_000)
    shoot(mocked_page, "p4s-loading")
    prefill_route.release(payload=[P4S_EXAMPLE_ROW])


def test_p4s_prefill_loaded(mocked_page, mocked_context):
    """DESIGN.md §9.3's own headline gap: the example-loaded P4S state,
    distinct from p4s.jpg (phase 10's manual/independent-entry state)."""
    route_json(mocked_context, "**/api/me", fx.api_me())
    route_json(mocked_context, "**/api/insights/budget-tiers", fx.budget_tiers_response())
    install_prefill_mock(mocked_context, [P4S_EXAMPLE_ROW])
    sign_in_and_wait(mocked_page, mocked_context)
    mocked_page.click('a[data-route="super-customer"]')
    mocked_page.wait_for_selector("#p4s-field-ad_budget")
    mocked_page.click("text=דוגמה 1")
    mocked_page.wait_for_function("() => document.getElementById('p4s-field-ad_budget').value === '4000'")
    assert "דוגמה היסטורית" in mocked_page.text_content(".input-summary")
    shoot(mocked_page, "p4s-prefill-loaded")


def test_p4s_error(mocked_page, mocked_context):
    route_json(mocked_context, "**/api/me", fx.api_me())
    route_json(mocked_context, "**/api/insights/budget-tiers", fx.budget_tiers_response())
    route_json(mocked_context, "**/rest/v1/funnel_records*", [])
    sign_in_and_wait(mocked_page, mocked_context)
    route_status(mocked_context, "**/api/predict/super-customer", 500)
    mocked_page.click('a[data-route="super-customer"]')
    mocked_page.wait_for_selector("#p4s-field-ad_budget")
    for field in ("ad_budget", "num_leads", "leads_answered", "followup_1"):
        mocked_page.fill(f"#p4s-field-{field}", PREDICT_VALUES[field])
    mocked_page.check(".context-confirmation input[type=checkbox]")
    mocked_page.click(".submit-button")
    mocked_page.wait_for_selector(".prediction-panel-p4s .panel-error", timeout=10_000)
    shoot(mocked_page, "p4s-error")


def test_p4s_ood(mocked_page, mocked_context):
    route_json(mocked_context, "**/api/me", fx.api_me())
    route_json(mocked_context, "**/api/insights/budget-tiers", fx.budget_tiers_response())
    route_json(mocked_context, "**/rest/v1/funnel_records*", [])
    sign_in_and_wait(mocked_page, mocked_context)
    route_json(mocked_context, "**/api/predict/super-customer", fx.super_customer_prediction_ood())
    mocked_page.click('a[data-route="super-customer"]')
    mocked_page.wait_for_selector("#p4s-field-ad_budget")
    for field in ("ad_budget", "num_leads", "leads_answered", "followup_1"):
        mocked_page.fill(f"#p4s-field-{field}", PREDICT_VALUES[field])
    mocked_page.check(".context-confirmation input[type=checkbox]")
    mocked_page.click(".submit-button")
    mocked_page.wait_for_selector(".prediction-panel-p4s .ood-banner", timeout=10_000)
    shoot(mocked_page, "p4s-ood")


# ---------------------------------------------------------------------
# Budget Simulator
# ---------------------------------------------------------------------

def test_budget_loading(mocked_page, mocked_context):
    route_json(mocked_context, "**/api/me", fx.api_me())
    route_json(mocked_context, "**/api/insights/budget-tiers", fx.budget_tiers_response())
    sign_in_and_wait(mocked_page, mocked_context)
    sim_route = route_deferred(mocked_context, "**/api/simulate/budget")
    mocked_page.click('a[data-route="budget"]')
    mocked_page.wait_for_selector("#screen-budget .panel-loading", timeout=10_000)
    shoot(mocked_page, "budget-loading")
    sim_route.release(payload=fx.budget_simulation())


def test_budget_error(mocked_page, mocked_context):
    route_json(mocked_context, "**/api/me", fx.api_me())
    route_json(mocked_context, "**/api/insights/budget-tiers", fx.budget_tiers_response())
    sign_in_and_wait(mocked_page, mocked_context)
    route_status(mocked_context, "**/api/simulate/budget", 500)
    mocked_page.click('a[data-route="budget"]')
    mocked_page.wait_for_selector("#screen-budget .panel-error:not([hidden])", timeout=10_000)
    shoot(mocked_page, "budget-error")


# ---------------------------------------------------------------------
# Follow-up
# ---------------------------------------------------------------------

def test_followup_loading(mocked_page, mocked_context):
    route_json(mocked_context, "**/api/me", fx.api_me())
    route_json(mocked_context, "**/api/insights/budget-tiers", fx.budget_tiers_response())
    sign_in_and_wait(mocked_page, mocked_context)
    followup_route = route_deferred(mocked_context, "**/api/insights/followup")
    mocked_page.click('a[data-route="followup"]')
    mocked_page.wait_for_selector("#screen-followup .panel-loading", timeout=10_000)
    shoot(mocked_page, "followup-loading")
    followup_route.release(payload=fx.followup_response())


def test_followup_error_partial(mocked_page, mocked_context):
    route_json(mocked_context, "**/api/me", fx.api_me())
    route_json(mocked_context, "**/api/insights/budget-tiers", fx.budget_tiers_response())
    route_json(
        mocked_context, "**/api/insights/followup",
        fx.followup_response(stages=fx.followup_stages_available(), calls=fx.followup_calls_unavailable()),
    )
    sign_in_and_wait(mocked_page, mocked_context)
    mocked_page.click('a[data-route="followup"]')
    mocked_page.wait_for_selector(".followup-layout", timeout=10_000)
    groups = mocked_page.query_selector_all(".followup-group")
    assert groups[1].query_selector(".panel-error") is not None
    shoot(mocked_page, "followup-error")
