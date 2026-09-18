"""PHASE11.md §י, cases 22 and 23.

Case 22 is tested via the two screens that actually have a live
business_facts.json consumer wired up: predict.js's P2 leverage tip
and budget.js's backtest recommendation (super-customer.js's own
profile card is a third real consumer, left for a follow-up batch).

⚠ Finding, 2026-09-18: `facts.getFollowupContext()` is exported by
facts.js but never called anywhere in app/static/js/ (grepped the
whole tree) -- followup.js's own D9 "answer" text is a hardcoded
constant (CP4D_RECOMMENDATION), not a runtime read of the
`followup_context` block PHASE11.md's own ד3 table lists as that
block's consumer. So there is no live UI path on the Follow-up screen
for business_facts.json's degradation to affect -- case 22's own
claim about this specific block has no code to falsify on THIS
screen. Not silently worked around: flagged here, and the assertion
below only tests the two blocks that do have a real runtime consumer."""
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


def test_case_22_business_facts_load_failure_hides_only_dependent_content(mocked_page, mocked_context):
    """22. business_facts.json נכשל בטעינה ⇒ מוסתר רק התוכן התלוי בנכס;
    אפס השבתה של תוצאות API. Tested on predict.js's P2 leverage tip and
    budget.js's backtest recommendation -- the two live consumers."""
    route_json(mocked_context, "**/api/me", fx.api_me())
    route_json(mocked_context, "**/api/insights/budget-tiers", fx.budget_tiers_response())
    route_status(mocked_context, "**/business_facts.json", 500)
    route_json(mocked_context, "**/api/predict/ltv", fx.ltv_prediction_success())
    route_json(mocked_context, "**/api/predict/upsell", fx.propensity_prediction_success())
    route_json(mocked_context, "**/api/predict/referral", fx.propensity_prediction_success())
    route_json(mocked_context, "**/api/simulate/budget", fx.budget_simulation())
    sign_in_and_wait(mocked_page, mocked_context)

    mocked_page.click('a[data-route="predict"]')
    mocked_page.wait_for_selector("#field-ad_budget")
    for field, value in PREDICT_VALUES.items():
        mocked_page.fill(f"#field-{field}", value)
    mocked_page.check(".context-confirmation input[type=checkbox]")
    mocked_page.click(".submit-button")

    mocked_page.wait_for_selector(".prediction-panel-p2 .prediction-primary", timeout=10_000)
    assert mocked_page.query_selector(".prediction-panel-p2 .ltv-leverage-tip") is None
    assert mocked_page.query_selector(".prediction-panel-p3 .prediction-primary") is not None
    assert mocked_page.query_selector(".prediction-panel-p4 .prediction-primary") is not None

    mocked_page.click('a[data-route="budget"]')
    mocked_page.wait_for_selector(".strategy-table", timeout=10_000)
    overlap_text = mocked_page.text_content(".overlap-alert")
    assert "8.6" not in overlap_text
    assert len(mocked_page.query_selector_all(".strategy-row")) == 4


def test_case_23_followup_partial_failure_shows_available_marks_missing_no_number(mocked_page, mocked_context):
    """23. followup מחזיר חלק אחד תקין וחלק אחד כושל ⇒ התקין מוצג, החסר
    מסומן, אין מספר שמור."""
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
    assert len(groups) == 2
    # Stages (available) rendered a real chart -- no panel-error inside it.
    stages_group = groups[0]
    assert stages_group.query_selector(".panel-error") is None
    assert stages_group.query_selector("svg, canvas, .bar-chart") is not None or "נשירה" in stages_group.text_content()
    # Calls (unavailable) is explicitly marked, not silently blank or zeroed.
    calls_group = groups[1]
    assert calls_group.query_selector(".panel-error") is not None

    # No invented/leftover combined number -- the joint recommendation
    # explicitly says it is unavailable instead.
    rec_text = mocked_page.text_content(".followup-recommendation")
    assert "אינה זמינה" in rec_text
    assert mocked_page.query_selector(".followup-recommendation h3") is None
