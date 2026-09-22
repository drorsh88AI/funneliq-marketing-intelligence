"""P11A checkpoint 7 (docs/planning/PHASE11A.md P11A-D8): Desktop-width
layout. Falsification case 14: "ברוחב Desktop: שלושת פאנלי החיזוי
באותה שורה; Overview לא 5 בשורה; Budget בשתי עמודות". Verified via
actual computed bounding boxes at Playwright's default 1280x720
Desktop viewport (this project's e2e harness never overrides it --
grepped e2e/conftest.py, confirmed no viewport fixture exists), not
just DOM presence -- a CSS-only regression (e.g. `.results-wrap`
reverting to `flex-direction: column`) would NOT be caught by any
selector-presence assertion, only by actually measuring position."""
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


def _tops(page, selector):
    return page.eval_on_selector_all(selector, "(elements) => elements.map((el) => el.getBoundingClientRect().top)")


def test_predict_three_panels_share_one_row_on_desktop(mocked_page, mocked_context):
    """DESIGN.md:271 -- "שלוש קבוצות פריסה זה-לצד-זה"."""
    route_json(mocked_context, "**/api/me", fx.api_me())
    route_json(mocked_context, "**/api/insights/budget-tiers", fx.budget_tiers_response())
    route_json(mocked_context, "**/rest/v1/funnel_records*", [])
    route_json(mocked_context, "**/api/predict/ltv", fx.ltv_prediction_success())
    route_json(mocked_context, "**/api/predict/upsell", fx.propensity_prediction_success())
    route_json(mocked_context, "**/api/predict/referral", fx.propensity_prediction_success())
    sign_in_and_wait(mocked_page, mocked_context)

    mocked_page.click('a[data-route="predict"]')
    mocked_page.wait_for_selector("#field-ad_budget")
    for field, value in PREDICT_VALUES.items():
        mocked_page.fill(f"#field-{field}", value)
    mocked_page.check("#screen-predict .context-confirmation input[type=checkbox]")
    mocked_page.click("#screen-predict .submit-button")
    mocked_page.wait_for_selector("#screen-predict .prediction-panel-p2 .prediction-primary", timeout=10_000)

    tops = _tops(mocked_page, "#screen-predict .prediction-panel")
    assert len(tops) == 3
    assert max(tops) - min(tops) < 2, f"expected the three panels on one row (equal top), got {tops}"


def test_overview_capability_index_never_five_in_one_row(mocked_page, mocked_context):
    """DESIGN.md:270 -- "לא שורה קשיחה אחת של חמישה כרטיסים"."""
    route_json(mocked_context, "**/api/me", fx.api_me())
    route_json(mocked_context, "**/api/insights/budget-tiers", fx.budget_tiers_response())
    sign_in_and_wait(mocked_page, mocked_context)

    mocked_page.wait_for_selector("#screen-overview .capability-index", timeout=10_000)
    tops = _tops(mocked_page, "#screen-overview .capability-card")
    assert len(tops) == 5
    distinct_rows = len(set(round(t) for t in tops))
    assert distinct_rows > 1, f"all 5 capability cards landed on one row (tops={tops}) -- forbidden"


def test_budget_table_and_chart_are_two_columns_same_row(mocked_page, mocked_context):
    """DESIGN.md:273 -- "שתי עמודות בלבד": the strategy table and the
    chart side by side, not stacked one above the other."""
    route_json(mocked_context, "**/api/me", fx.api_me())
    route_json(mocked_context, "**/api/insights/budget-tiers", fx.budget_tiers_response())
    route_json(mocked_context, "**/api/simulate/budget", fx.budget_simulation())
    sign_in_and_wait(mocked_page, mocked_context)

    mocked_page.click('a[data-route="budget"]')
    mocked_page.wait_for_selector("#screen-budget .strategy-table", timeout=10_000)

    table_top = mocked_page.eval_on_selector("#screen-budget .strategy-table-wrap", "(el) => el.getBoundingClientRect().top")
    chart_top = mocked_page.eval_on_selector("#screen-budget .chart-live", "(el) => el.getBoundingClientRect().top")
    assert abs(table_top - chart_top) < 2, f"expected the table and chart on one row (equal top), got table={table_top} chart={chart_top}"
