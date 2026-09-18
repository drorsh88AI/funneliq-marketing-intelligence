"""PHASE11.md §י, cases 2 and 5 -- the shared form's own per-screen
generation counter (generation.js), independent of session epoch.
Cases 1, 3, 4 (example-loading / P4S-vs-shared-form cross-screen
independence) need example-prefill mocking not yet built here -- left
for a follow-up batch."""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import fixtures as fx
from conftest import (
    route_deferred,
    route_json,
    sign_in_and_wait,
)

PREDICT_VALUES = {
    "ad_budget": "5000", "num_leads": "100", "leads_answered": "80",
    "followup_1": "70", "followup_2": "60", "followup_3": "50",
    "followup_4": "40", "followup_5": "30", "closed": "10",
    "calls_to_closed": "3", "calls_to_not_closed": "2",
    "customer_acquisition_cost": "500",
}


def _fill_and_open_predict_form(page):
    page.click('a[data-route="predict"]')
    page.wait_for_selector("#field-ad_budget")
    for field, value in PREDICT_VALUES.items():
        page.fill(f"#field-{field}", value)
    page.check(".context-confirmation input[type=checkbox]")


def test_case_2_field_edit_while_submitting_discards_the_late_response(mocked_page, mocked_context):
    """2. שליחה → שינוי שדה בזמן בקשה ⇒ התשובה המאוחרת אינה מרונדרת."""
    route_json(mocked_context, "**/api/insights/budget-tiers", fx.budget_tiers_response())
    route_json(mocked_context, "**/api/me", fx.api_me())
    sign_in_and_wait(mocked_page, mocked_context)
    _fill_and_open_predict_form(mocked_page)

    ltv_route = route_deferred(mocked_context, "**/api/predict/ltv")
    upsell_route = route_deferred(mocked_context, "**/api/predict/upsell")
    referral_route = route_deferred(mocked_context, "**/api/predict/referral")
    mocked_page.click(".submit-button")
    ltv_route.wait_for_capture(mocked_page)
    upsell_route.wait_for_capture(mocked_page)
    referral_route.wait_for_capture(mocked_page)

    # Edit ONE field while the submission is in flight -- IA.md §9.4's
    # own unconditional trigger, regardless of the form's current
    # source (predict.js's own onFieldInput() docstring: fixed after a
    # review found this wrongly gated behind source==="historical").
    mocked_page.fill("#field-ad_budget", "6000")

    ltv_route.release(payload=fx.ltv_prediction_success())
    upsell_route.release(payload=fx.propensity_prediction_success())
    referral_route.release(payload=fx.propensity_prediction_success())

    import time
    deadline = time.time() + 2.0
    while time.time() < deadline:
        if mocked_page.query_selector(".prediction-panel-p2 .prediction-primary") is not None:
            raise AssertionError("stale prediction rendered after a mid-flight field edit")
        mocked_page.wait_for_timeout(100)
    # The edited value itself must survive -- only the STALE RESULT is discarded.
    assert mocked_page.input_value("#field-ad_budget") == "6000"


def test_case_5_two_submissions_old_returns_last_only_new_renders(mocked_page, mocked_context):
    """5. שתי שליחות רצופות באותו מסך, הישנה חוזרת אחרונה ⇒ מרונדרת רק החדשה."""
    route_json(mocked_context, "**/api/insights/budget-tiers", fx.budget_tiers_response())
    route_json(mocked_context, "**/api/me", fx.api_me())
    sign_in_and_wait(mocked_page, mocked_context)
    _fill_and_open_predict_form(mocked_page)

    # First submission -- held open (the "old" one, which will resolve LAST).
    ltv_route_1 = route_deferred(mocked_context, "**/api/predict/ltv")
    upsell_route_1 = route_deferred(mocked_context, "**/api/predict/upsell")
    referral_route_1 = route_deferred(mocked_context, "**/api/predict/referral")
    mocked_page.click(".submit-button")
    ltv_route_1.wait_for_capture(mocked_page)
    upsell_route_1.wait_for_capture(mocked_page)
    referral_route_1.wait_for_capture(mocked_page)

    # A field edit (case 2's own trigger) invalidates submission #1 and
    # re-enables the submit button; a second, distinguishable submission
    # follows. The new deferred routes MUST be registered BEFORE the
    # click -- ltv_route_1's own handler is still active (registrations
    # persist) and, being currently the last-registered one for this
    # pattern, would otherwise swallow submission #2's request into its
    # own capture list instead of a fresh one.
    ltv_route_2 = route_deferred(mocked_context, "**/api/predict/ltv")
    upsell_route_2 = route_deferred(mocked_context, "**/api/predict/upsell")
    referral_route_2 = route_deferred(mocked_context, "**/api/predict/referral")
    mocked_page.fill("#field-ad_budget", "9999")
    mocked_page.click(".submit-button")
    ltv_route_2.wait_for_capture(mocked_page)
    upsell_route_2.wait_for_capture(mocked_page)
    referral_route_2.wait_for_capture(mocked_page)

    new_ltv = fx.ltv_prediction_success(point=77.0, lower=70.0, upper=85.0)
    ltv_route_2.release(payload=new_ltv)
    upsell_route_2.release(payload=fx.propensity_prediction_success())
    referral_route_2.release(payload=fx.propensity_prediction_success())

    mocked_page.wait_for_selector(".prediction-panel-p2 .prediction-primary", timeout=10_000)
    rendered_text = mocked_page.text_content(".prediction-panel-p2 .prediction-primary")
    assert "77" in rendered_text

    # THEN the old (#1) submission's response finally arrives -- must
    # NOT overwrite the already-rendered new one.
    old_ltv = fx.ltv_prediction_success(point=11.0, lower=5.0, upper=15.0)
    ltv_route_1.release(payload=old_ltv)
    upsell_route_1.release(payload=fx.propensity_prediction_success())
    referral_route_1.release(payload=fx.propensity_prediction_success())

    import time
    deadline = time.time() + 1.5
    while time.time() < deadline:
        text = mocked_page.text_content(".prediction-panel-p2 .prediction-primary")
        assert "11" not in text, "the OLD submission's late response overwrote the new one"
        mocked_page.wait_for_timeout(100)
    assert "77" in mocked_page.text_content(".prediction-panel-p2 .prediction-primary")
