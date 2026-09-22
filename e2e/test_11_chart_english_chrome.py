"""P11A checkpoint 6 (docs/planning/PHASE11A.md P11A-D7): the four
live SVG charts (Overview, Budget Simulator, Follow-up's two) must
carry an English chart title and English X/Y axis names INSIDE the
SVG -- PREVIOUSLY absent entirely (only each bar's own `xEnglish` tick
label existed; renderBarChart()'s `xLabel`/`yLabel` params were used
ONLY for the accessible fallback table's Hebrew headers, never
rendered into the SVG at all). Budget's own chart additionally carries
a whisker (lower/upper bound), so its textual legend must be English
too (DESIGN.md:300-304's own "מקרא טקסטואלי" requirement, English per
D7) -- its PREVIOUS text was Hebrew.

Falsification case 12 (PHASE11A.md §ז): the SVG contains an X axis
name, a Y axis name, and a title, all English, for every one of the
four charts."""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import fixtures as fx
from conftest import route_json, sign_in_and_wait


def _chrome_texts(page, chart_scope_selector):
    """Returns (title_text, x_axis_name_text, y_axis_name_text) for the
    FIRST chart-live-svg under `chart_scope_selector`, relying on
    charts.js's own fixed append order (title, then X-axis name, then
    Y-axis name -- all three appended before the grid/bars)."""
    title = page.text_content(f"{chart_scope_selector} .chart-live-svg .chart-title")
    axis_names = page.query_selector_all(f"{chart_scope_selector} .chart-live-svg .chart-axis-name")
    assert len(axis_names) == 2, f"expected exactly 2 .chart-axis-name elements (X then Y), found {len(axis_names)}"
    return title, axis_names[0].text_content(), axis_names[1].text_content()


def _chrome_texts_from_handle(handle):
    """Same as _chrome_texts, scoped to an already-resolved element
    handle instead of a selector string -- used where two sibling
    elements share the same class (`.followup-group`) and a selector
    string can't distinguish "the first one" reliably."""
    title = handle.query_selector(".chart-live-svg .chart-title").text_content()
    axis_names = handle.query_selector_all(".chart-live-svg .chart-axis-name")
    assert len(axis_names) == 2, f"expected exactly 2 .chart-axis-name elements (X then Y), found {len(axis_names)}"
    return title, axis_names[0].text_content(), axis_names[1].text_content()


def _assert_all_english(*texts):
    hebrew_range = range(0x0590, 0x05FF + 1)
    for text in texts:
        assert text, "chart chrome text must not be empty"
        assert not any(ord(ch) in hebrew_range for ch in text), f"expected English-only text, found Hebrew in {text!r}"


def test_overview_chart_has_english_title_and_axis_names(mocked_page, mocked_context):
    route_json(mocked_context, "**/api/me", fx.api_me())
    route_json(mocked_context, "**/api/insights/budget-tiers", fx.budget_tiers_response())
    sign_in_and_wait(mocked_page, mocked_context)

    mocked_page.wait_for_selector("#screen-overview .chart-live-svg", timeout=10_000)
    title, x_name, y_name = _chrome_texts(mocked_page, "#screen-overview")
    assert title == "Conversion Rate by Ad Budget Level"
    assert x_name == "Ad Budget Level"
    assert y_name == "Conversion Rate"
    _assert_all_english(title, x_name, y_name)


def test_budget_chart_has_english_title_axis_names_and_legend(mocked_page, mocked_context):
    route_json(mocked_context, "**/api/me", fx.api_me())
    route_json(mocked_context, "**/api/insights/budget-tiers", fx.budget_tiers_response())
    route_json(mocked_context, "**/api/simulate/budget", fx.budget_simulation())
    sign_in_and_wait(mocked_page, mocked_context)

    mocked_page.click('a[data-route="budget"]')
    mocked_page.wait_for_selector("#screen-budget .chart-live-svg", timeout=10_000)
    title, x_name, y_name = _chrome_texts(mocked_page, "#screen-budget")
    assert title == "Expected Profit by Allocation Strategy"
    assert x_name == "Strategy"
    assert y_name == "Expected Profit"
    _assert_all_english(title, x_name, y_name)

    # Budget's chart has a whisker (lower/upper bound per strategy) --
    # DESIGN.md:300-304's own mandatory textual legend, English per D7.
    legend_text = mocked_page.text_content("#screen-budget .chart-legend")
    assert legend_text == (
        "The vertical line above each bar shows the uncertainty range "
        "(95% Bootstrap, 2.5-97.5 percentile) around the expected profit."
    )
    _assert_all_english(legend_text)


def test_followup_charts_have_english_titles_and_axis_names(mocked_page, mocked_context):
    route_json(mocked_context, "**/api/me", fx.api_me())
    route_json(mocked_context, "**/api/insights/budget-tiers", fx.budget_tiers_response())
    route_json(
        mocked_context, "**/api/insights/followup",
        fx.followup_response(stages=fx.followup_stages_available(), calls=fx.followup_calls_available()),
    )
    sign_in_and_wait(mocked_page, mocked_context)

    mocked_page.click('a[data-route="followup"]')
    mocked_page.wait_for_selector(".followup-layout", timeout=10_000)
    groups = mocked_page.query_selector_all(".followup-group")
    assert len(groups) == 2

    stages_title, stages_x, stages_y = _chrome_texts_from_handle(groups[0])
    assert stages_title == "Drop-off Rate by Follow-up Stage"
    assert stages_x == "Follow-up Stage"
    assert stages_y == "Drop-off Rate"
    _assert_all_english(stages_title, stages_x, stages_y)

    calls_title, calls_x, calls_y = _chrome_texts_from_handle(groups[1])
    assert calls_title == "Record Count by Number of Calls to Close"
    assert calls_x == "Number of Calls"
    assert calls_y == "Number of Records"
    _assert_all_english(calls_title, calls_x, calls_y)
