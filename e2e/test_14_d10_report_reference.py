"""P11A checkpoint 7 (docs/planning/PHASE11A.md P11A-D10): P4's own
model-details caveat, in BOTH its OOD and healthy (in-domain) branches
(predict.js's own buildP4Panel -- unlike P3, whose caveat in both
branches is the unrelated "עקומת הכיול אינה מונוטונית" sentence and
never referenced REPORT.md at all). The PREVIOUS text ("עקומת הכיול
המלאה מתועדת ב-REPORT.md.") claimed a document already exists (present
tense, "מתועדת") and named an internal repo filename -- both forbidden
by D10. The locked replacement keeps the SAME textual reference IA.md
requires (never removed, per D10's own "ההסרה נפסלה"), reworded to
product language."""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import fixtures as fx
from conftest import route_json, sign_in_and_wait

PREDICT_VALUES = {
    "ad_budget": "5000", "num_leads": "100", "leads_answered": "80",
    "followup_1": "70", "followup_2": "60", "followup_3": "50",
    "followup_4": "40", "followup_5": "30", "closed": "10",
    "calls_to_closed": "3", "calls_to_not_closed": "2",
    "customer_acquisition_cost": "500",
}

_LOCKED_REPORT_REFERENCE = "עקומת הכיול המלאה אינה מוצגת כאן; מקומה בדוח הפרויקט."


def _submit_shared_form(page, context):
    route_json(context, "**/rest/v1/funnel_records*", [])
    page.click('a[data-route="predict"]')
    page.wait_for_selector("#field-ad_budget")
    for field, value in PREDICT_VALUES.items():
        page.fill(f"#field-{field}", value)
    page.check("#screen-predict .context-confirmation input[type=checkbox]")
    page.click("#screen-predict .submit-button")


def test_p4_healthy_shows_locked_report_reference_not_filename(mocked_page, mocked_context):
    route_json(mocked_context, "**/api/me", fx.api_me())
    route_json(mocked_context, "**/api/insights/budget-tiers", fx.budget_tiers_response())
    route_json(mocked_context, "**/api/predict/ltv", fx.ltv_prediction_success())
    route_json(mocked_context, "**/api/predict/upsell", fx.propensity_prediction_success())
    route_json(mocked_context, "**/api/predict/referral", fx.propensity_prediction_success())
    sign_in_and_wait(mocked_page, mocked_context)

    _submit_shared_form(mocked_page, mocked_context)
    mocked_page.wait_for_selector(".prediction-panel-p4 .prediction-primary", timeout=10_000)

    note_text = mocked_page.text_content(".prediction-panel-p4 .model-details-note")
    assert note_text == _LOCKED_REPORT_REFERENCE
    panel_text = mocked_page.text_content(".prediction-panel-p4")
    assert "REPORT.md" not in panel_text
    assert "מתועדת" not in panel_text  # the forbidden present-tense claim


def test_p4_ood_shows_locked_report_reference_not_filename(mocked_page, mocked_context):
    route_json(mocked_context, "**/api/me", fx.api_me())
    route_json(mocked_context, "**/api/insights/budget-tiers", fx.budget_tiers_response())
    route_json(mocked_context, "**/api/predict/ltv", fx.ltv_prediction_success())
    route_json(mocked_context, "**/api/predict/upsell", fx.propensity_prediction_success())
    route_json(mocked_context, "**/api/predict/referral", fx.propensity_prediction_ood(model_version="P4-logistic-e2e"))
    sign_in_and_wait(mocked_page, mocked_context)

    _submit_shared_form(mocked_page, mocked_context)
    mocked_page.wait_for_selector(".prediction-panel-p4 .ood-banner", timeout=10_000)

    note_text = mocked_page.text_content(".prediction-panel-p4 .model-details-note")
    assert note_text == _LOCKED_REPORT_REFERENCE
    panel_text = mocked_page.text_content(".prediction-panel-p4")
    assert "REPORT.md" not in panel_text
    assert "מתועדת" not in panel_text
