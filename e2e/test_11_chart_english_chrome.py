"""12A, 27.09.2026 (overturns P11A-D7/S11 for chart chrome -- tester
finding O3: "לא ברור מה הגרף אמור להציג, למה הכותרת באנגלית"): the four
live SVG charts (Overview, Budget Simulator, Follow-up's two) now carry
a HEBREW chart title, Hebrew X/Y axis names, and Hebrew per-bar category
labels INSIDE the SVG, matching the accessible fallback table below
each chart. The title keeps a small ENGLISH subtitle line underneath it
(charts.js's own `.chart-title-subtitle`) -- the only English left in
chart chrome. Budget's whisker legend (DESIGN.md:300-304's own mandatory
"מקרא טקסטואלי") is Hebrew too, per the same 12A decision (§ז1: "הכול
בעברית").

Falsification case (PHASE12A.md §ז1 + §CP8): the SVG contains a Hebrew
title, a Hebrew X axis name, a Hebrew Y axis name, and an English
subtitle, for every one of the four charts; no chart chrome text is
English except that one subtitle line.

File name kept from P11A (checkpoint 6) -- this is the same single
"does chart chrome match the language decision" test file the P11A plan
pointed at; only the decision it enforces flipped, in 12A."""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import fixtures as fx
from conftest import route_json, sign_in_and_wait


def _chrome_texts(page, chart_scope_selector):
    """Returns (title_text, subtitle_text, x_axis_name_text,
    y_axis_name_text) for the FIRST chart-live-svg under
    `chart_scope_selector`, relying on charts.js's own fixed append
    order (title, subtitle, then X-axis name, then Y-axis name -- all
    four appended before the grid/bars)."""
    title = page.text_content(f"{chart_scope_selector} .chart-live-svg .chart-title")
    subtitle = page.text_content(f"{chart_scope_selector} .chart-live-svg .chart-title-subtitle")
    axis_names = page.query_selector_all(f"{chart_scope_selector} .chart-live-svg .chart-axis-name")
    assert len(axis_names) == 2, f"expected exactly 2 .chart-axis-name elements (X then Y), found {len(axis_names)}"
    return title, subtitle, axis_names[0].text_content(), axis_names[1].text_content()


def _chrome_texts_from_handle(handle):
    """Same as _chrome_texts, scoped to an already-resolved element
    handle instead of a selector string -- used where two sibling
    elements share the same class (`.followup-group`) and a selector
    string can't distinguish "the first one" reliably."""
    title = handle.query_selector(".chart-live-svg .chart-title").text_content()
    subtitle = handle.query_selector(".chart-live-svg .chart-title-subtitle").text_content()
    axis_names = handle.query_selector_all(".chart-live-svg .chart-axis-name")
    assert len(axis_names) == 2, f"expected exactly 2 .chart-axis-name elements (X then Y), found {len(axis_names)}"
    return title, subtitle, axis_names[0].text_content(), axis_names[1].text_content()


_HEBREW_RANGE = range(0x0590, 0x05FF + 1)


def _assert_has_hebrew(*texts):
    for text in texts:
        assert text, "chart chrome text must not be empty"
        assert any(ord(ch) in _HEBREW_RANGE for ch in text), f"expected Hebrew text, found none in {text!r}"


def _assert_all_english(*texts):
    for text in texts:
        assert text, "chart chrome text must not be empty"
        assert not any(ord(ch) in _HEBREW_RANGE for ch in text), f"expected English-only text, found Hebrew in {text!r}"


def test_overview_chart_has_hebrew_title_and_axis_names(mocked_page, mocked_context):
    route_json(mocked_context, "**/api/me", fx.api_me())
    route_json(mocked_context, "**/api/insights/budget-tiers", fx.budget_tiers_response())
    sign_in_and_wait(mocked_page, mocked_context)

    mocked_page.wait_for_selector("#screen-overview .chart-live-svg", timeout=10_000)
    title, subtitle, x_name, y_name = _chrome_texts(mocked_page, "#screen-overview")
    assert title == "שיעור ההמרה לפי רמת הוצאת הפרסום"
    assert x_name == "רמת הוצאה חודשית על פרסום"
    assert y_name == "שיעור המרה — כמה מהלידים הפכו לעסקה (%)"
    _assert_has_hebrew(title, x_name, y_name)
    assert subtitle == "Conversion Rate by Ad Budget Level"
    _assert_all_english(subtitle)

    # Per-bar category tick labels (charts.js's `d.xHebrew`) are Hebrew
    # too -- Low/Mid/High are never shown unexplained (tester finding:
    # "לא מבינים מה זה mid, high ו-low").
    tick_labels = mocked_page.query_selector_all("#screen-overview .chart-live-svg .chart-axis-label")
    assert len(tick_labels) == 3
    for label in tick_labels:
        _assert_has_hebrew(label.text_content())


def test_budget_chart_has_hebrew_title_axis_names_and_legend(mocked_page, mocked_context):
    route_json(mocked_context, "**/api/me", fx.api_me())
    route_json(mocked_context, "**/api/insights/budget-tiers", fx.budget_tiers_response())
    route_json(mocked_context, "**/api/simulate/budget", fx.budget_simulation())
    sign_in_and_wait(mocked_page, mocked_context)

    mocked_page.click('a[data-route="budget"]')
    mocked_page.wait_for_selector("#screen-budget .chart-live-svg", timeout=10_000)
    title, subtitle, x_name, y_name = _chrome_texts(mocked_page, "#screen-budget")
    assert title == "רווח מצטבר צפוי לפי אופן חלוקת התקציב"
    assert x_name == "אופן החלוקה (קמפיינים × תקציב לקמפיין)"
    assert y_name == "רווח מצטבר צפוי (₪)"
    _assert_has_hebrew(title, x_name, y_name)
    assert subtitle == "Expected Profit by Allocation Strategy"
    _assert_all_english(subtitle)

    # Budget's chart has a whisker (lower/upper bound per strategy) --
    # DESIGN.md:300-304's own mandatory textual legend, Hebrew per 12A
    # (§ז1: "הכול בעברית", overturning P11A-D7's English-legend rule).
    legend_text = mocked_page.text_content("#screen-budget .chart-legend")
    assert legend_text == (
        "הקו האנכי בכל עמודה מראה את טווח האומדן (95%, דגימה חוזרת של "
        "נתוני האימון): עד כמה האומדן משתנה כשחוזרים על החישוב. הקו "
        "יכול לרדת גם מתחת לראש העמודה. זה אינו טווח לרווח שיתקבל "
        "בפועל."
    )
    _assert_has_hebrew(legend_text)


def test_followup_charts_have_hebrew_titles_and_axis_names(mocked_page, mocked_context):
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

    stages_title, stages_subtitle, stages_x, stages_y = _chrome_texts_from_handle(groups[0])
    assert stages_title == "כמה לידים נושרים בכל שלב מעקב"
    assert stages_x == "שלב המעקב"
    assert stages_y == "שיעור נשירה"
    _assert_has_hebrew(stages_title, stages_x, stages_y)
    assert stages_subtitle == "Drop-off Rate by Follow-up Stage"
    _assert_all_english(stages_subtitle)

    calls_title, calls_subtitle, calls_x, calls_y = _chrome_texts_from_handle(groups[1])
    assert calls_title == "בממוצע, כמה שיחות נדרשו עד סגירת עסקה"
    assert calls_x == "ממוצע שיחות עד סגירה (לשורה)"
    assert calls_y == "מספר שורות בנתונים"
    _assert_has_hebrew(calls_title, calls_x, calls_y)
    assert calls_subtitle == "Record Count by Number of Calls to Close"
    _assert_all_english(calls_subtitle)

    # §יב-2 R2's approved caption -- population_n from fx.followup_calls_available()'s
    # default buckets: 200+400+900+700+600+300+150+40+20+8 = 3,318.
    calls_legend = groups[1].query_selector(".chart-legend").text_content()
    assert calls_legend == (
        "כל עמודה מראה בכמה מקרים בנתוני העבר זה היה ממוצע השיחות עד "
        "סגירה. נכללו רק מקרים שבהם נסגרה לפחות עסקה אחת (3,318 מקרים)."
    )


def test_null_conversion_rate_never_renders_as_a_zero_bar(mocked_page, mocked_context):
    """IA.md:112 / charts.js's own `.chart-bar-missing` (12A, tester
    finding: "null נראה כאפס בגרף"): a tier with `conversion_rate: null`
    must render NO `.chart-bar` rect at all -- only the dashed
    `.chart-bar-missing` baseline marker + an "N/A" text label."""
    route_json(mocked_context, "**/api/me", fx.api_me())
    route_json(
        mocked_context, "**/api/insights/budget-tiers",
        fx.budget_tiers_response(rates={"Low": 0.045, "Mid": None, "High": 0.054}),
    )
    sign_in_and_wait(mocked_page, mocked_context)

    mocked_page.wait_for_selector("#screen-overview .chart-live-svg", timeout=10_000)
    bars = mocked_page.query_selector_all("#screen-overview .chart-live-svg .chart-bar")
    assert len(bars) == 2, f"expected 2 real bars (Low, High), found {len(bars)} -- Mid's null must not draw a rect"

    missing = mocked_page.query_selector_all("#screen-overview .chart-live-svg .chart-bar-missing")
    assert len(missing) == 1, f"expected exactly 1 missing-value marker (Mid), found {len(missing)}"

    missing_label = mocked_page.text_content("#screen-overview .chart-live-svg .chart-bar-missing-label")
    assert missing_label == "N/A"
