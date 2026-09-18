"""PHASE11.md §י, cases 17, 18, 20 -- shared-form validation (closed vs
followup_5), the clear-form confirm/cancel flow, and business_facts.json
model_version-mismatch hiding only the dependent content.

Case 18 here covers the SHARED FORM only (predict.js) -- the P4S
(super-customer.js) side of "בשני המסכים" is left for a follow-up batch,
not silently skipped."""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import fixtures as fx
from conftest import route_deferred, route_json, sign_in_and_wait

PREDICT_VALUES = {
    "ad_budget": "5000", "num_leads": "100", "leads_answered": "80",
    "followup_1": "70", "followup_2": "60", "followup_3": "50",
    "followup_4": "40", "followup_5": "30", "closed": "10",
    "calls_to_closed": "3", "calls_to_not_closed": "2",
    "customer_acquisition_cost": "500",
}


def _open_predict(page):
    page.click('a[data-route="predict"]')
    page.wait_for_selector("#field-ad_budget")


def _fill(page, values):
    for field, value in values.items():
        page.fill(f"#field-{field}", value)


def test_case_17_closed_gt_followup5_blocks_no_clamp_no_silent_change(mocked_page, mocked_context):
    """17. closed > followup_5 ⇒ שגיאה חוסמת; אין חיתוך לאפס ואין שינוי שקט ב-closed."""
    route_json(mocked_context, "**/api/me", fx.api_me())
    route_json(mocked_context, "**/api/insights/budget-tiers", fx.budget_tiers_response())
    sign_in_and_wait(mocked_page, mocked_context)
    _open_predict(mocked_page)

    values = dict(PREDICT_VALUES)
    values["followup_5"] = "30"
    values["closed"] = "999"  # far more "closed" than remain after followup 5
    _fill(mocked_page, values)
    mocked_page.check(".context-confirmation input[type=checkbox]")

    assert mocked_page.is_disabled(".submit-button")
    blocked_text = mocked_page.text_content(".submit-blocked-wrap")
    assert "עסקאות שנסגרו אינן יכולות לעלות על הלידים שנותרו אחרי מעקב 5" in blocked_text

    # The derived value shows the REAL (negative) number -- not clamped
    # to zero -- and `closed` itself keeps the value the user typed.
    derived_text = mocked_page.text_content(".derived-field-value")
    assert "-969" in derived_text
    assert mocked_page.input_value("#field-closed") == "999"


def test_case_18_clear_form_cancel_is_a_no_op_confirm_bumps_generation_first(mocked_page, mocked_context):
    """18 (טופס משותף). נקה טופס → ביטול ⇒ אפס שינוי; → אישור ⇒ מונה
    הדור עולה לפני האיפוס (הבקשה הישנה שבאוויר נזרקת בשקט, לא מרונדרת)."""
    route_json(mocked_context, "**/api/me", fx.api_me())
    route_json(mocked_context, "**/api/insights/budget-tiers", fx.budget_tiers_response())
    sign_in_and_wait(mocked_page, mocked_context)
    _open_predict(mocked_page)
    _fill(mocked_page, PREDICT_VALUES)
    mocked_page.check(".context-confirmation input[type=checkbox]")

    # -- Cancel path: zero change. --
    mocked_page.click(".clear-form-action >> text=נקה טופס")
    mocked_page.wait_for_selector(".clear-form-confirm")
    mocked_page.click(".clear-form-confirm >> text=ביטול")
    assert mocked_page.query_selector(".clear-form-confirm") is None
    assert mocked_page.input_value("#field-ad_budget") == PREDICT_VALUES["ad_budget"]
    assert mocked_page.is_checked(".context-confirmation input[type=checkbox]")

    # -- Confirm path, with a submission in flight: the stale response
    # must never render, and the form resets to blank. --
    ltv_route = route_deferred(mocked_context, "**/api/predict/ltv")
    upsell_route = route_deferred(mocked_context, "**/api/predict/upsell")
    referral_route = route_deferred(mocked_context, "**/api/predict/referral")
    mocked_page.click(".submit-button")
    ltv_route.wait_for_capture(mocked_page)
    upsell_route.wait_for_capture(mocked_page)
    referral_route.wait_for_capture(mocked_page)

    mocked_page.click(".clear-form-action >> text=נקה טופס")
    mocked_page.wait_for_selector(".clear-form-confirm")
    mocked_page.click(".clear-form-confirm >> text=אישור")

    assert mocked_page.input_value("#field-ad_budget") == ""
    assert not mocked_page.is_checked(".context-confirmation input[type=checkbox]")

    ltv_route.release(payload=fx.ltv_prediction_success())
    upsell_route.release(payload=fx.propensity_prediction_success())
    referral_route.release(payload=fx.propensity_prediction_success())
    import time
    deadline = time.time() + 1.5
    while time.time() < deadline:
        assert mocked_page.query_selector(".prediction-panel-p2 .prediction-primary") is None
        mocked_page.wait_for_timeout(100)


def test_case_20_p2_model_version_mismatch_hides_only_leverage_tip(mocked_page, mocked_context):
    """20. model_versions.P2 אינו תואם ⇒ מוסתרת תמצית המנוף בלבד; תוצאת
    P2 וכל שאר המסכים נשארים פעילים."""
    route_json(mocked_context, "**/api/me", fx.api_me())
    route_json(mocked_context, "**/api/insights/budget-tiers", fx.budget_tiers_response())
    sign_in_and_wait(mocked_page, mocked_context)

    mismatched_facts = {
        "budget_backtest": {"500": {"actual_mean_per_customer": 918.65, "n_holdout_at_level": 17, "n_train_at_level": 92, "predicted_per_customer": 7895.94}},
        "followup_context": {"mean_calls_closed_eq_1": 5.65, "mean_calls_closed_ge_2": 3.35, "population_definition": "closed>0"},
        "ltv": {"dominant_feature": "calls_to_closed", "rank_1_by_algorithm": {"catboost": {"feature": "calls_to_closed", "importance": 96.0}}},
        "metrics_sha256": "8af98f45f595a830b26055be5eab053c85c43c6fc6d97732c45b34b9f3166723",
        "model_versions": {
            "P2": "P2-DOES-NOT-MATCH-LIVE",  # deliberately mismatched
            "P3": "P3-xgboost-e2e", "P4": "P4-logistic-e2e",
            "P4S": "P4S-catboost-e2e", "P6": "P6-linear-e2e",
        },
        "schema_version": 1,
        "source_csv_sha256": "8ac67d50a6f96a8ece8abd770a5a1901b34036a5c98656455eb04cee07d707aa",
        "source_keys": {"budget_backtest": "x", "followup_context": "x", "ltv": "x", "super_customer_profile": "x"},
        "super_customer_profile": {"cac_population_mean": 1437.0, "cac_savings_pct": 0.31, "cac_super_mean": 990.0, "n_purchased": 3163, "n_super": 529, "pct_of_purchased": 0.16, "pct_of_total_profit": 0.33, "population_definition": "x"},
    }
    route_json(mocked_context, "**/business_facts.json", mismatched_facts)

    route_json(mocked_context, "**/api/predict/ltv", fx.ltv_prediction_success(model_version="P2-catboost-e2e"))
    route_json(mocked_context, "**/api/predict/upsell", fx.propensity_prediction_success())
    route_json(mocked_context, "**/api/predict/referral", fx.propensity_prediction_success())
    _open_predict(mocked_page)
    _fill(mocked_page, PREDICT_VALUES)
    mocked_page.check(".context-confirmation input[type=checkbox]")
    mocked_page.click(".submit-button")

    mocked_page.wait_for_selector(".prediction-panel-p2 .prediction-primary", timeout=10_000)
    # The result itself renders normally -- only the static leverage tip is gone.
    assert mocked_page.query_selector(".prediction-panel-p2 .ltv-leverage-tip") is None
    assert mocked_page.query_selector(".prediction-panel-p3 .prediction-primary") is not None
    assert mocked_page.query_selector(".prediction-panel-p4 .prediction-primary") is not None
