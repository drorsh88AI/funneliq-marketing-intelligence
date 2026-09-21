"""P11A checkpoint 7 (docs/planning/PHASE11A.md P11A-D8/D9): every
visible screen carries EXACTLY ONE h1 and ZERO heading-level skips (no
h3 without a preceding h2 somewhere on that same screen). PREVIOUSLY,
the only h1 anywhere was Login's; every other heading was h3, and
budget.js had no heading at all.

Falsification case 15: "כל מסך גלוי ⇒ h1 אחד בדיוק, ⛔ ואפס דילוגי רמה
-- ⛔ אין h3 בלי h2 שקודם לו באותו מסך"."""
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
P4S_ROW = {"ad_budget": 5000, "num_leads": 100, "leads_answered": 80, "followup_1": 70}


def _heading_levels(page, scope_selector):
    """Returns the heading levels (1-6) found under `scope_selector`, in
    DOM order -- e.g. [1, 2, 3, 3]."""
    return page.eval_on_selector_all(
        f"{scope_selector} h1, {scope_selector} h2, {scope_selector} h3, {scope_selector} h4, {scope_selector} h5, {scope_selector} h6",
        "(elements) => elements.map((el) => Number(el.tagName[1]))",
    )


def _assert_valid_heading_hierarchy(levels):
    assert levels, "no headings found on this screen"
    assert levels.count(1) == 1, f"expected exactly one h1, got heading levels {levels}"
    max_seen = 0
    for level in levels:
        assert level <= max_seen + 1, f"heading level skip in {levels} (jumped to h{level} with max seen h{max_seen})"
        max_seen = max(max_seen, level)


def test_login_screen_has_exactly_one_h1(mocked_page, mocked_context):
    levels = _heading_levels(mocked_page, "#login-section")
    _assert_valid_heading_hierarchy(levels)
    assert levels == [1]


def test_overview_screen_heading_hierarchy(mocked_page, mocked_context):
    route_json(mocked_context, "**/api/me", fx.api_me())
    route_json(mocked_context, "**/api/insights/budget-tiers", fx.budget_tiers_response())
    sign_in_and_wait(mocked_page, mocked_context)

    mocked_page.wait_for_selector("#screen-overview .capability-index", timeout=10_000)
    levels = _heading_levels(mocked_page, "#screen-overview")
    _assert_valid_heading_hierarchy(levels)
    # h1 (screen title), h2 (capability index), 5x h3 (one per capability card).
    assert levels == [1, 2, 3, 3, 3, 3, 3]


def test_predict_screen_heading_hierarchy_after_submit(mocked_page, mocked_context):
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

    levels = _heading_levels(mocked_page, "#screen-predict")
    _assert_valid_heading_hierarchy(levels)
    # h1 (screen title), h2 (prefill picker), 3x h3 (P2/P3/P4 panels).
    assert levels == [1, 2, 3, 3, 3]


def test_super_customer_screen_heading_hierarchy_after_submit(mocked_page, mocked_context):
    route_json(mocked_context, "**/api/me", fx.api_me())
    route_json(mocked_context, "**/api/insights/budget-tiers", fx.budget_tiers_response())
    route_json(mocked_context, "**/rest/v1/funnel_records*", [])
    route_json(mocked_context, "**/api/predict/super-customer", fx.super_customer_prediction_success())
    sign_in_and_wait(mocked_page, mocked_context)

    mocked_page.click('a[data-route="super-customer"]')
    mocked_page.wait_for_selector("#p4s-field-ad_budget")
    for field in ("ad_budget", "num_leads", "leads_answered", "followup_1"):
        mocked_page.fill(f"#p4s-field-{field}", str(P4S_ROW[field]))
    mocked_page.check("#screen-super-customer .context-confirmation input[type=checkbox]")
    mocked_page.click("#screen-super-customer .submit-button")
    mocked_page.wait_for_selector("#screen-super-customer .prediction-panel-p4s .prediction-primary", timeout=10_000)

    levels = _heading_levels(mocked_page, "#screen-super-customer")
    _assert_valid_heading_hierarchy(levels)
    # h1 (screen title), h2 (prefill picker), h3 (the single P4S panel).
    assert levels == [1, 2, 3]


def test_budget_screen_heading_hierarchy_and_locked_h1_text(mocked_page, mocked_context):
    """D8's own lock: the sole h1 carries `total_budget`'s display value
    (DESIGN.md:403/:457) -- D9's own note that this single heading must
    satisfy BOTH D8 and D9 together, not two competing headings."""
    route_json(mocked_context, "**/api/me", fx.api_me())
    route_json(mocked_context, "**/api/insights/budget-tiers", fx.budget_tiers_response())
    route_json(mocked_context, "**/api/simulate/budget", fx.budget_simulation())
    sign_in_and_wait(mocked_page, mocked_context)

    mocked_page.click('a[data-route="budget"]')
    mocked_page.wait_for_selector("#screen-budget .strategy-table", timeout=10_000)

    levels = _heading_levels(mocked_page, "#screen-budget")
    _assert_valid_heading_hierarchy(levels)
    assert levels == [1]  # no h3 anywhere on this screen -- one h1 is already sufficient
    assert mocked_page.text_content("#screen-budget h1") == "₪50,000"


def test_budget_h1_is_derived_from_response_not_hardcoded(mocked_page, mocked_context):
    """Companion to the test above: `total_budget=50000` alone does NOT
    prove the h1 is actually READ from the response, since a hardcoded
    "₪50,000" would coincidentally match it too (a prior draft of this
    checkpoint did exactly that, and a Codex review correctly rejected
    it). `BudgetSimulation.total_budget` is schema-locked to
    `Literal[50000]` -- unconstructable with any other value through
    fx.budget_simulation() itself -- so this test builds the raw JSON
    payload directly (Playwright's route mock is never schema-validated,
    unlike the real backend) with a deliberately different total_budget,
    proving the h1 is wired to the live field."""
    deliberately_different_total_budget = 12345
    payload = fx.budget_simulation()
    payload["total_budget"] = deliberately_different_total_budget
    route_json(mocked_context, "**/api/me", fx.api_me())
    route_json(mocked_context, "**/api/insights/budget-tiers", fx.budget_tiers_response())
    route_json(mocked_context, "**/api/simulate/budget", payload)
    sign_in_and_wait(mocked_page, mocked_context)

    mocked_page.click('a[data-route="budget"]')
    mocked_page.wait_for_selector("#screen-budget .strategy-table", timeout=10_000)
    assert mocked_page.text_content("#screen-budget h1") == "₪12,345"


def test_followup_screen_heading_hierarchy(mocked_page, mocked_context):
    route_json(mocked_context, "**/api/me", fx.api_me())
    route_json(mocked_context, "**/api/insights/budget-tiers", fx.budget_tiers_response())
    route_json(
        mocked_context, "**/api/insights/followup",
        fx.followup_response(stages=fx.followup_stages_available(), calls=fx.followup_calls_available()),
    )
    sign_in_and_wait(mocked_page, mocked_context)

    mocked_page.click('a[data-route="followup"]')
    mocked_page.wait_for_selector("#screen-followup .followup-layout", timeout=10_000)

    levels = _heading_levels(mocked_page, "#screen-followup")
    _assert_valid_heading_hierarchy(levels)
    # h1 (screen title), h2 "נשירה", h2 "מספר שיחות עד סגירה", h3 "המלצה".
    assert levels == [1, 2, 2, 3]
