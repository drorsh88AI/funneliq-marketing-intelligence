"""PHASE11.md §י, cases 13, 14, 15 -- overview's budget-tiers
empty-rows handling, per-panel independence of the predict screen's
three predictions, and OOD confined to a single panel."""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import fixtures as fx
from conftest import route_json, route_status, sign_in_and_wait

PREDICT_VALUES = {
    "ad_budget": "5000", "num_leads": "100", "leads_answered": "80",
    "followup_1": "70", "followup_2": "60", "followup_3": "50",
    "followup_4": "40", "followup_5": "30", "closed": "10",
    "calls_to_closed": "3", "calls_to_not_closed": "2",
    "customer_acquisition_cost": "500",
}


def _fill_and_submit_predict_form(page):
    page.click('a[data-route="predict"]')
    page.wait_for_selector("#field-ad_budget")
    for field, value in PREDICT_VALUES.items():
        page.fill(f"#field-{field}", value)
    page.check(".context-confirmation input[type=checkbox]")
    page.click(".submit-button")


def test_case_13_budget_tiers_200_zero_rows_is_availability_error_not_empty(mocked_page, mocked_context):
    """13. budget-tiers מחזיר 200 עם אפס שורות ⇒ שגיאת זמינות, לא empty."""
    route_json(mocked_context, "**/api/me", fx.api_me())
    route_json(mocked_context, "**/api/insights/budget-tiers", fx.budget_tiers_empty())
    sign_in_and_wait(mocked_page, mocked_context)

    mocked_page.wait_for_selector("#screen-overview .panel-error:not([hidden])", timeout=10_000)
    text = mocked_page.text_content("#screen-overview .panel-error")
    # IA.md §2.2's own distinction: a data-availability error, NOT the
    # generic "no data" empty-state wording -- checked by presence of
    # the word for "unavailable right now" rather than a full locked
    # string (the exact phrasing isn't itself part of the contract).
    assert "אין כרגע" in text
    assert mocked_page.query_selector("#screen-overview .panel-empty") is None


def test_case_14_one_of_three_predictions_500_others_stay_intact(mocked_page, mocked_context):
    """14. אחת משלוש קריאות החיזוי מחזירה 500 ⇒ שני הפאנלים האחרים נשארים תקינים."""
    route_json(mocked_context, "**/api/me", fx.api_me())
    route_json(mocked_context, "**/api/insights/budget-tiers", fx.budget_tiers_response())
    sign_in_and_wait(mocked_page, mocked_context)

    route_status(mocked_context, "**/api/predict/ltv", 500)
    route_json(mocked_context, "**/api/predict/upsell", fx.propensity_prediction_success())
    route_json(mocked_context, "**/api/predict/referral", fx.propensity_prediction_success())
    _fill_and_submit_predict_form(mocked_page)

    mocked_page.wait_for_selector(".prediction-panel-p3 .prediction-primary", timeout=10_000)
    # P2 (ltv) failed -- an error panel, not a rendered prediction.
    assert mocked_page.query_selector(".prediction-panel-p2 .prediction-primary") is None
    assert mocked_page.query_selector(".prediction-panel-p2 .panel-error") is not None
    # P3 and P4 succeeded independently.
    assert mocked_page.query_selector(".prediction-panel-p3 .prediction-primary") is not None
    assert mocked_page.query_selector(".prediction-panel-p4 .prediction-primary") is not None


def test_case_15_ood_confined_to_p2_only(mocked_page, mocked_context):
    """15. OOD ב-P2 בלבד ⇒ P2 ללא מספר + סיבה קונקרטית; P3/P4 מציגים מספר."""
    route_json(mocked_context, "**/api/me", fx.api_me())
    route_json(mocked_context, "**/api/insights/budget-tiers", fx.budget_tiers_response())
    sign_in_and_wait(mocked_page, mocked_context)

    route_json(mocked_context, "**/api/predict/ltv", fx.ltv_prediction_ood())
    route_json(mocked_context, "**/api/predict/upsell", fx.propensity_prediction_success())
    route_json(mocked_context, "**/api/predict/referral", fx.propensity_prediction_success())
    _fill_and_submit_predict_form(mocked_page)

    mocked_page.wait_for_selector(".prediction-panel-p2 .ood-banner", timeout=10_000)
    assert mocked_page.query_selector(".prediction-panel-p2 .prediction-primary") is None
    reason_text = mocked_page.text_content(".prediction-panel-p2 .ood-banner-reason")
    assert reason_text and reason_text.strip() != ""

    assert mocked_page.query_selector(".prediction-panel-p3 .prediction-primary") is not None
    assert mocked_page.query_selector(".prediction-panel-p3 .ood-banner") is None
    assert mocked_page.query_selector(".prediction-panel-p4 .prediction-primary") is not None
    assert mocked_page.query_selector(".prediction-panel-p4 .ood-banner") is None
