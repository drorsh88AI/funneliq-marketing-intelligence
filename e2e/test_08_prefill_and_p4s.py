"""PHASE11.md §י, cases 1, 3, 4, 16, 18 (P4S half), 19 -- the shared
form's and P4S's own SEPARATE prefill selectors and generation
counters (generation.js's own docstring: one shared by P2/P3/P4, a
fully separate one for P4S)."""
from __future__ import annotations

import json
import sys
from pathlib import Path
from urllib.parse import unquote

sys.path.insert(0, str(Path(__file__).resolve().parent))
import fixtures as fx
from conftest import install_prefill_mock, route_deferred, route_json, route_status, sign_in_and_wait

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


def _open_predict(page):
    page.click('a[data-route="predict"]')
    page.wait_for_selector("#field-ad_budget")


def _fill_predict(page, values=PREDICT_VALUES):
    for field, value in values.items():
        page.fill(f"#field-{field}", value)


def _open_p4s(page):
    page.click('a[data-route="super-customer"]')
    page.wait_for_selector("#p4s-field-ad_budget")


def _fill_p4s(page, row):
    for field in ("ad_budget", "num_leads", "leads_answered", "followup_1"):
        page.fill(f"#p4s-field-{field}", str(row[field]))


def test_case_1_loading_example_then_editing_field_clears_result_and_relabels(mocked_page, mocked_context):
    """1. טעינת דוגמה → עריכת שדה אחד ⇒ תוצאה קודמת נעלמת מיד, התווית →
    תרחיש שנערך."""
    route_json(mocked_context, "**/api/me", fx.api_me())
    route_json(mocked_context, "**/api/insights/budget-tiers", fx.budget_tiers_response())
    route_json(mocked_context, "**/rest/v1/funnel_records*", [])
    route_json(mocked_context, "**/api/predict/ltv", fx.ltv_prediction_success())
    route_json(mocked_context, "**/api/predict/upsell", fx.propensity_prediction_success())
    route_json(mocked_context, "**/api/predict/referral", fx.propensity_prediction_success())
    install_prefill_mock(mocked_context, [SHARED_FORM_EXAMPLE_ROW])
    sign_in_and_wait(mocked_page, mocked_context)
    _open_predict(mocked_page)
    _fill_predict(mocked_page)
    mocked_page.check(".context-confirmation input[type=checkbox]")
    mocked_page.click(".submit-button")
    mocked_page.wait_for_selector(".prediction-panel-p2 .prediction-primary", timeout=10_000)

    # §ו.2 (12A): the shared form's prefill-picker is now a folded
    # <details> below the form -- open it before its own example button
    # is clickable/visible.
    mocked_page.click(".prefill-picker summary")
    mocked_page.click("text=דוגמה 1")
    # Loading an example alone already clears the prior result.
    assert mocked_page.query_selector(".prediction-panel-p2 .prediction-primary") is None
    assert "דוגמה היסטורית" in mocked_page.text_content(".input-summary")
    # Selecting an example opens the populated fields and returns the
    # viewport/focus to them, even though the picker is below the form.
    assert mocked_page.eval_on_selector(".input-details", "el => el.open") is True
    assert mocked_page.input_value("#field-ad_budget") == "4000"
    assert mocked_page.is_visible("#field-ad_budget")
    assert mocked_page.evaluate("""() => {
        const rect = document.querySelector('#field-ad_budget').getBoundingClientRect();
        return rect.top >= 0 && rect.bottom <= window.innerHeight;
    }""")
    assert mocked_page.evaluate("document.activeElement.matches('.input-details summary')")
    mocked_page.fill("#field-ad_budget", "7777")
    assert mocked_page.query_selector(".prediction-panel-p2 .prediction-primary") is None
    assert "תרחיש שנערך" in mocked_page.text_content(".input-summary")


def test_case_16_prefill_selector_failure_leaves_manual_entry_and_submit_fully_possible(mocked_page, mocked_context):
    """16. כשל בורר ה-prefill ⇒ הזנה ידנית ושליחה נשארות אפשריות במלואן."""
    route_json(mocked_context, "**/api/me", fx.api_me())
    route_json(mocked_context, "**/api/insights/budget-tiers", fx.budget_tiers_response())
    route_json(mocked_context, "**/rest/v1/funnel_records*", [])
    route_json(mocked_context, "**/api/predict/ltv", fx.ltv_prediction_success())
    route_json(mocked_context, "**/api/predict/upsell", fx.propensity_prediction_success())
    route_json(mocked_context, "**/api/predict/referral", fx.propensity_prediction_success())
    install_prefill_mock(mocked_context, [], status=500)
    sign_in_and_wait(mocked_page, mocked_context)
    _open_predict(mocked_page)

    # §ו.2 (12A): the picker is folded by default -- open it to see its
    # own error state.
    mocked_page.click(".prefill-picker summary")
    mocked_page.wait_for_selector(".prefill-picker-body .panel-error", timeout=10_000)
    # Manual entry and submission are unaffected by the prefill failure.
    _fill_predict(mocked_page)
    mocked_page.check(".context-confirmation input[type=checkbox]")
    assert not mocked_page.is_disabled(".submit-button")
    mocked_page.click(".submit-button")
    mocked_page.wait_for_selector(".prediction-panel-p2 .prediction-primary", timeout=10_000)


def test_case_3_p4s_in_flight_survives_shared_form_field_edit(mocked_page, mocked_context):
    """3. בקשת P4S באוויר → שינוי שדה בטופס המשותף ⇒ תוצאת P4S אינה
    מתבטלת (מוני דור נפרדים לגמרי)."""
    route_json(mocked_context, "**/api/me", fx.api_me())
    route_json(mocked_context, "**/api/insights/budget-tiers", fx.budget_tiers_response())
    route_json(mocked_context, "**/rest/v1/funnel_records*", [])
    sign_in_and_wait(mocked_page, mocked_context)

    _open_p4s(mocked_page)
    _fill_p4s(mocked_page, {"ad_budget": 5000, "num_leads": 100, "leads_answered": 80, "followup_1": 70})
    mocked_page.check(".context-confirmation input[type=checkbox]")
    p4s_route = route_deferred(mocked_context, "**/api/predict/super-customer")
    mocked_page.click(".submit-button")
    p4s_route.wait_for_capture(mocked_page)

    _open_predict(mocked_page)
    mocked_page.fill("#field-ad_budget", "1")  # a shared-form field edit -- its OWN generation counter only

    p4s_route.release(payload=fx.super_customer_prediction_success())
    mocked_page.click('a[data-route="super-customer"]')
    mocked_page.wait_for_selector(".prediction-panel-p4s .prediction-primary", timeout=10_000)


def test_case_4_shared_form_in_flight_survives_p4s_field_edit(mocked_page, mocked_context):
    """4 (סימטרי ל-3). בקשת הטופס המשותף באוויר → שינוי שדה ב-P4S ⇒
    אינה מתבטלת."""
    route_json(mocked_context, "**/api/me", fx.api_me())
    route_json(mocked_context, "**/api/insights/budget-tiers", fx.budget_tiers_response())
    route_json(mocked_context, "**/rest/v1/funnel_records*", [])
    sign_in_and_wait(mocked_page, mocked_context)

    _open_predict(mocked_page)
    _fill_predict(mocked_page)
    mocked_page.check(".context-confirmation input[type=checkbox]")
    ltv_route = route_deferred(mocked_context, "**/api/predict/ltv")
    upsell_route = route_deferred(mocked_context, "**/api/predict/upsell")
    referral_route = route_deferred(mocked_context, "**/api/predict/referral")
    mocked_page.click(".submit-button")
    ltv_route.wait_for_capture(mocked_page)
    upsell_route.wait_for_capture(mocked_page)
    referral_route.wait_for_capture(mocked_page)

    _open_p4s(mocked_page)
    mocked_page.fill("#p4s-field-ad_budget", "1")  # P4S's OWN generation counter only

    ltv_route.release(payload=fx.ltv_prediction_success())
    upsell_route.release(payload=fx.propensity_prediction_success())
    referral_route.release(payload=fx.propensity_prediction_success())
    mocked_page.click('a[data-route="predict"]')
    mocked_page.wait_for_selector(".prediction-panel-p2 .prediction-primary", timeout=10_000)


def test_case_18_p4s_clear_form_cancel_noop_confirm_bumps_generation_first(mocked_page, mocked_context):
    """18 (P4S). נקה טופס → ביטול ⇒ אפס שינוי; → אישור ⇒ מונה הדור עולה
    לפני האיפוס."""
    route_json(mocked_context, "**/api/me", fx.api_me())
    route_json(mocked_context, "**/api/insights/budget-tiers", fx.budget_tiers_response())
    route_json(mocked_context, "**/rest/v1/funnel_records*", [])
    sign_in_and_wait(mocked_page, mocked_context)
    _open_p4s(mocked_page)
    _fill_p4s(mocked_page, {"ad_budget": 5000, "num_leads": 100, "leads_answered": 80, "followup_1": 70})
    mocked_page.check(".context-confirmation input[type=checkbox]")

    mocked_page.click(".clear-form-action >> text=נקה טופס")
    mocked_page.wait_for_selector(".clear-form-confirm")
    mocked_page.click(".clear-form-confirm >> text=ביטול")
    assert mocked_page.input_value("#p4s-field-ad_budget") == "5000"
    assert mocked_page.is_checked(".context-confirmation input[type=checkbox]")

    p4s_route = route_deferred(mocked_context, "**/api/predict/super-customer")
    mocked_page.click(".submit-button")
    p4s_route.wait_for_capture(mocked_page)

    mocked_page.click(".clear-form-action >> text=נקה טופס")
    mocked_page.wait_for_selector(".clear-form-confirm")
    mocked_page.click(".clear-form-confirm >> text=אישור")
    assert mocked_page.input_value("#p4s-field-ad_budget") == ""

    p4s_route.release(payload=fx.super_customer_prediction_success())
    import time
    deadline = time.time() + 1.5
    while time.time() < deadline:
        assert mocked_page.query_selector(".prediction-panel-p4s .prediction-primary") is None
        mocked_page.wait_for_timeout(100)


def test_case_19_p4s_revert_field_decrements_counter_full_revert_shows_4_of_4(mocked_page, mocked_context):
    """19. P4S — החזר לערך הדוגמה על שדה אחד ⇒ מונה השינויים יורד ב-1
    ואישור ההקשר מתאפס; החזרה מלאה ⇒ דוגמה היסטורית · 4/4 בלי מונה."""
    route_json(mocked_context, "**/api/me", fx.api_me())
    route_json(mocked_context, "**/api/insights/budget-tiers", fx.budget_tiers_response())
    route_json(mocked_context, "**/rest/v1/funnel_records*", [])
    install_prefill_mock(mocked_context, [P4S_EXAMPLE_ROW])
    sign_in_and_wait(mocked_page, mocked_context)
    _open_p4s(mocked_page)

    # §ו.2 (12A, CP5): P4S's own prefill-picker moved below the form and
    # folded too (same fix as the shared form's in CP4) -- open it first.
    mocked_page.click(".prefill-picker summary")
    mocked_page.click("text=דוגמה 1")
    # syncFieldValuesToDom() sets the live .value PROPERTY, not the
    # HTML attribute -- an attribute selector like input[value="4000"]
    # never matches it; wait on the actual input value instead.
    mocked_page.wait_for_function(
        "() => document.getElementById('p4s-field-ad_budget').value === '4000'"
    )
    mocked_page.check(".context-confirmation input[type=checkbox]")

    # Edit TWO of the four fields.
    mocked_page.fill("#p4s-field-ad_budget", "9000")
    mocked_page.fill("#p4s-field-num_leads", "9")
    summary = mocked_page.text_content(".input-summary")
    assert "2" in summary and "שונ" in summary
    assert not mocked_page.is_checked(".context-confirmation input[type=checkbox]")  # reset by the first edit already

    mocked_page.check(".context-confirmation input[type=checkbox]")
    mocked_page.click("#p4s-field-ad_budget ~ .revert-field-action, .field:has(#p4s-field-ad_budget) .revert-field-action")
    summary = mocked_page.text_content(".input-summary")
    assert "1" in summary and "שונ" in summary
    assert not mocked_page.is_checked(".context-confirmation input[type=checkbox]")  # reset again by the revert

    mocked_page.check(".context-confirmation input[type=checkbox]")
    mocked_page.click(".field:has(#p4s-field-num_leads) .revert-field-action")
    summary = mocked_page.text_content(".input-summary")
    assert "דוגמה היסטורית" in summary and "4/4" in summary
    assert "שונ" not in summary


def test_shared_form_prefill_requests_the_10_frozen_ids(mocked_page, mocked_context):
    """PHASE12A.md §ו.2: the shared form's prefill no longer sends
    `limit=1000` -- it filters on the 10 committed frozen ids
    (docs/frozen_examples.json), via the same live query mechanism
    (real client/JWT, RLS still applies -- only the id list changed).
    Reads the manifest directly rather than a third, hand-typed id list
    that could drift from it."""
    manifest = json.loads((Path(__file__).resolve().parent.parent / "docs" / "frozen_examples.json").read_text(encoding="utf-8"))
    frozen_ids = {e["source_row_id"] for e in manifest["examples"]}

    route_json(mocked_context, "**/api/me", fx.api_me())
    route_json(mocked_context, "**/api/insights/budget-tiers", fx.budget_tiers_response())
    prefill_route = route_deferred(mocked_context, "**/rest/v1/funnel_records*")
    sign_in_and_wait(mocked_page, mocked_context)
    _open_predict(mocked_page)
    # Folded by default (§ו.2) -- opening it does not re-trigger the
    # fetch (it already ran on screen load); this only makes the
    # already-in-flight request's own effect (the picker body) visible
    # later, once released below.
    mocked_page.click(".prefill-picker summary")

    prefill_route.wait_for_capture(mocked_page)
    decoded_url = unquote(prefill_route.request_url())
    assert "limit=" not in decoded_url, f"prefill still sends a row-count limit: {decoded_url}"
    assert "source_row_id=in.(" in decoded_url, f"prefill does not filter by id list: {decoded_url}"

    ids_in_url = {
        int(x) for x in decoded_url.split("source_row_id=in.(")[1].split(")")[0].split(",")
    }
    assert ids_in_url == frozen_ids, f"prefill's id filter {ids_in_url} != manifest ids {frozen_ids}"

    prefill_route.release(payload=[SHARED_FORM_EXAMPLE_ROW])
