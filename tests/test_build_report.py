"""CP3 infrastructure for REPORT.md (PHASE13.md D2, D8, D9, A3, A5).

Everything here runs in CI without the CSV, except the tests named
`..._from_the_csv`, which skip when it is absent (the repo's existing pattern).
The byte-for-byte SVG comparisons are LOCAL evidence: they skip when CI=true,
because the committed SVGs were produced on one platform and matplotlib's own
test-suite does not rely on cross-platform SVG byte equality.

Expected numbers are written by hand from the committed assets and from the
CSV measurements recorded in PHASE13.md appendix A; they are not read back
from the code under test.
"""
from __future__ import annotations

import json
import os
import re
import xml.etree.ElementTree as ET
from decimal import Decimal
from pathlib import Path

import pytest

from scripts import build_report as br
from scripts import load_data as ld

REPO = Path(__file__).resolve().parents[1]


def _lf(data: bytes) -> bytes:
    """Git on Windows checks files out with CRLF; the committed blob is LF."""
    return data.replace(b"\r\n", b"\n")


def _skip_byte_equality_in_ci():
    if os.environ.get("CI", "").lower() == "true":
        pytest.skip("byte-for-byte SVG equality is local evidence; CI renders on another platform")


# ---------------------------------------------------------------------------
# Sources: a closed list, and the CSV is not on it
# ---------------------------------------------------------------------------
def test_the_source_list_is_exactly_the_closed_list_from_the_plan():
    assert sorted(br.SOURCES.values()) == sorted([
        "models/metrics.json",
        "docs/findings.json",
        "models/P6_simulation.json",
        "app/static/business_facts.json",
        "models/P2.meta.json",
        "models/P3.meta.json",
        "models/P4.meta.json",
        "models/P4S.meta.json",
        "models/P6.meta.json",
        "docs/p4s_a2_train_tiers.json",
    ])


def test_no_source_is_the_csv_so_the_manifest_can_run_in_ci():
    assert not any(path.endswith(".csv") for path in br.SOURCES.values())


def test_every_source_is_exercised_by_at_least_one_manifest_entry():
    used = set()
    for entry in br.MANIFEST.values():
        if isinstance(entry, br.Ref):
            used.add(entry.source)
        else:
            used.update(source for source, _ in entry.inputs)
    assert used == set(br.SOURCES)


def test_a_source_outside_the_list_is_refused():
    with pytest.raises(br.ReportError, match="closed source list"):
        br.Sources().get("csv")


def test_a_missing_source_file_is_reported_by_name(tmp_path):
    with pytest.raises(br.ReportError, match=r"source file missing: models/metrics\.json"):
        br.Sources(root=tmp_path).get("metrics")


def test_a_path_that_does_not_resolve_names_the_path_and_the_file(monkeypatch):
    monkeypatch.setitem(br.MANIFEST, "broken", br.Ref("metrics", ("P3_holdout", "no_such_key"), "int"))
    with pytest.raises(br.ReportError, match=r"no_such_key.*models/metrics\.json"):
        br.resolve("broken", br.Sources())


# ---------------------------------------------------------------------------
# The manifest against the committed assets
# ---------------------------------------------------------------------------
def test_every_manifest_entry_resolves_against_the_committed_sources():
    sources = br.Sources()
    for name in br.MANIFEST:
        value = br.resolve(name, sources)
        assert value and value not in {"None", "nan"} and "Decimal" not in value, name


# The three majority rates, each tied to ITS population (PHASE13.md A3.2).
# Measured against the CSV in CP0: 1,697 of 3,163 purchasers; the dummy
# classifier over the 5 CV folds of the 2,024-row training split; 633 Holdout.
@pytest.mark.parametrize("name, expected", [
    ("n_purchasers_all", "3,163"),
    ("majority_all_pct", "53.65"),        # 1 - base_rate 0.4635 (all purchasers)
    ("n_train_p3", "2,024"),
    ("majority_cv_pct", "53.66"),         # mean accuracy of the CV dummy, 0.536561...
    ("n_holdout_p3", "633"),
    ("majority_holdout_pct", "53.71"),    # 1 - 0.462875... (Holdout base rate)
    ("p3_holdout_accuracy_pct", "76.15"),
    ("p3_gain_over_majority_pp", "22.43"),  # 76.145 - 53.712 = 22.433 points
    ("missing_rows", "33"),
    ("leads_per_1000_lowest", "26.0"),
    ("super_share_of_total_profit_pct", "33.6"),
    ("p6_point_100x500", "789,594"),
    ("p4s_holdout_roc_auc", "0.801"),
    ("p4s_train_n", "2,024"),
    ("p6_train_n", "2,776"),
    ("a2_mid_n", "1,041"),
    ("a2_mid_super_rate_pct", "32.5"),
])
def test_manifest_known_answers(name, expected):
    assert br.resolve(name, br.Sources()) == expected


def test_the_three_majority_rates_are_three_different_numbers():
    rates = {br.resolve(n, br.Sources()) for n in ("majority_all_pct", "majority_cv_pct", "majority_holdout_pct")}
    assert len(rates) == 3


# ---------------------------------------------------------------------------
# Number formatting
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("value, fmt, expected", [
    (21.25, "num1", "21.3"),          # exact half: rounds UP (float format() gives 21.2)
    (8.75, "num1", "8.8"),
    (0.5365, "pct2", "53.65"),
    (0.3246878, "pct1", "32.5"),
    (3163, "comma", "3,163"),
    (789593.59, "comma", "789,594"),
    (33, "int", "33"),
    (26.0, "num1", "26.0"),
    (1234.5, "num2", "1,234.50"),
    (0.80135, "num3", "0.801"),
])
def test_format_value(value, fmt, expected):
    assert br.format_value(value, fmt) == expected


def test_format_value_refuses_what_it_cannot_say_honestly():
    with pytest.raises(br.ReportError):
        br.format_value(33.5, "int")          # not an integer
    with pytest.raises(br.ReportError):
        br.format_value(1.0, "nonsense")
    with pytest.raises(br.ReportError):
        br.format_value(None, "int")
    with pytest.raises(br.ReportError):
        br.format_value(True, "int")


@pytest.mark.parametrize("value, fmt", [
    (0.00004, "pct2"),      # 0.004 points, would print 0.00
    (-0.00004, "pct2"),     # would print -0.00
    (0.4, "comma"),         # a non-zero count that would print 0
    (0.004, "num2"),
    (-0.0004, "num3"),
])
def test_a_non_zero_value_that_rounds_to_zero_raises_instead_of_printing_zero(value, fmt):
    with pytest.raises(br.ReportError, match="not zero but rounds to zero"):
        br.format_value(value, fmt)


@pytest.mark.parametrize("value, fmt, expected", [
    (0, "pct2", "0.00"),
    (0.0, "num1", "0.0"),
    (-0.0, "pct2", "0.00"),     # a true zero never prints a sign
    (-0.0, "num2", "0.00"),
    (-0.0, "comma", "0"),
    (-1.5, "num1", "-1.5"),     # real negatives are untouched
    (0.00005, "pct3", "0.005"),  # a finer format makes a small value representable
    (0.004999, "pct2", "0.50"),
])
def test_zero_and_small_values_that_do_survive_rounding(value, fmt, expected):
    assert br.format_value(value, fmt) == expected


def test_a_derived_value_is_exact_not_float_noise():
    # In floating point 1 - 0.4635 is 0.5365000000000001.
    assert br.DERIVED["one_minus"](0.4635) == Decimal("0.5365")


# ---------------------------------------------------------------------------
# Rendering
# ---------------------------------------------------------------------------
def test_render_substitutes_declared_placeholders_and_the_dollar_escape():
    out = br.render_report("n=$n_purchasers_all, majority=${majority_holdout_pct}%, price $$5")
    assert out == "n=3,163, majority=53.71%, price $5"


def test_an_undeclared_placeholder_fails_the_render_and_is_named():
    with pytest.raises(br.ReportError, match="not declared in the manifest.*invented_number"):
        br.render_report("a $n_purchasers_all and $invented_number")


def test_a_malformed_dollar_is_a_report_error():
    with pytest.raises(br.ReportError, match="malformed placeholder"):
        br.render_report("cost: $ 5 $n_purchasers_all")


# ---------------------------------------------------------------------------
# Embedded blocks: verbatim from docs/feature_matrix.md
# ---------------------------------------------------------------------------
def _matrix_lines():
    return (REPO / "docs" / "feature_matrix.md").read_text(encoding="utf-8").splitlines()


def _independent_table_after(heading):
    """Re-derived here by a different route than the code under test."""
    lines = _matrix_lines()
    start = next(i for i, line in enumerate(lines) if line == heading)
    first = next(i for i in range(start + 1, len(lines)) if lines[i].startswith("|"))
    last = first
    while last + 1 < len(lines) and lines[last + 1].startswith("|"):
        last += 1
    return lines[first:last + 1]


def test_the_feature_table_block_is_verbatim_from_feature_matrix():
    block = br.block_value("feature_table").split("\n")
    assert block == _independent_table_after("## הטבלה")


def test_the_feature_summary_block_is_verbatim_from_feature_matrix():
    block = br.block_value("feature_summary").split("\n")
    assert block == _independent_table_after("## סיכום פיצ'רים בפועל")


def test_the_feature_table_has_one_row_for_each_of_the_19_source_columns():
    rows = br.block_value("feature_table").split("\n")[2:]          # header + separator
    assert len(rows) == 19
    named = [re.match(r"\|\s*\d+\s*\|\s*`([^`]+)`", row).group(1) for row in rows]
    assert sorted(named) == sorted(ld.EXPECTED_COLUMNS)


def test_a_block_placeholder_renders_the_block_unchanged():
    assert br.render_report("$feature_table") == br.block_value("feature_table")


def test_a_missing_heading_or_table_is_refused():
    with pytest.raises(br.ReportError, match="not found"):
        br.table_after_heading("# only a title\n", "## הטבלה")
    with pytest.raises(br.ReportError, match="no table between"):
        br.table_after_heading("## הטבלה\ntext only\n## next\n| a |\n", "## הטבלה")


# ---------------------------------------------------------------------------
# The chart-heading rule (PHASE13.md A5)
# ---------------------------------------------------------------------------
HEBREW = "עקומת כיול"
CONTROLS = (
    [0x200E, 0x200F, 0x061C]
    + [0x202A, 0x202B, 0x202C, 0x202D, 0x202E]
    + [0x2066, 0x2067, 0x2068, 0x2069]
)


@pytest.mark.parametrize("text", [
    "עקומת כיול P3",
    "3 שיעורי רוב",
    "— (2) עקומת כיול",
    "כיול P4S (calibration)",
    "(1) עקומת כיול",
])
def test_a_heading_whose_first_strong_character_is_hebrew_passes(text):
    assert br.heading_rule_violation(text) is None


@pytest.mark.parametrize("text", [
    "P3 — עקומת כיול",
    "SHAP — הסבר מקומי",
    "cumulative_profit — רווח מצטבר",
    "123",
    "",
])
def test_a_heading_whose_first_strong_character_is_not_hebrew_fails(text):
    assert br.heading_rule_violation(text) is not None


@pytest.mark.parametrize("code_point", CONTROLS)
def test_every_direction_control_character_fails_at_the_start_in_the_middle_and_at_the_end(code_point):
    mark = chr(code_point)
    for heading in (mark + HEBREW, HEBREW[:4] + mark + HEBREW[4:], HEBREW + mark):
        reason = br.heading_rule_violation(heading)
        assert reason and "direction-control" in reason, (hex(code_point), heading)


def test_the_nine_controls_a_first_strong_scan_would_skip_still_fail_here():
    """LRE RLE PDF LRO RLO LRI RLI FSI PDI are not classes L/R/AL, so scanning for
    the first strong character alone would pass `RLE + Hebrew`. Step 1 stops it."""
    for code_point in (0x202A, 0x202B, 0x202C, 0x202D, 0x202E, 0x2066, 0x2067, 0x2068, 0x2069):
        assert br.heading_rule_violation(chr(code_point) + HEBREW).startswith("direction-control")


def test_the_control_list_in_the_code_is_exactly_the_twelve_characters():
    assert sorted(br.DIRECTION_CONTROLS) == sorted(CONTROLS)


@pytest.mark.parametrize("raw, rendered", [
    ("### **עקומת** כיול", "עקומת כיול"),
    ("## [עקומת כיול](x.md)", "עקומת כיול"),
    ("### `P3` כיול", "P3 כיול"),           # code content is part of what is rendered
    ("### <b>עקומת</b> כיול", "עקומת כיול"),
    ("#### ![alt](x.svg) עקומת", "alt עקומת"),
    ("###   עקומת   כיול  ", "עקומת כיול"),
])
def test_rendered_heading_text(raw, rendered):
    assert br.rendered_heading_text(raw) == rendered


def test_a_code_span_that_opens_a_hebrew_heading_fails_because_its_content_is_rendered():
    assert br.heading_rule_violation(br.rendered_heading_text("### `P3` עקומת כיול")) is not None


GOOD = "### עקומת כיול P3\n\n![P3](docs/calibration_curve_P3.svg)\n\nכיתוב בעברית.\n"


def test_a_chart_with_a_hebrew_heading_above_it_has_no_violations():
    assert br.chart_heading_violations(GOOD) == []


def test_a_chart_without_a_heading_directly_above_is_a_violation():
    problems = br.chart_heading_violations("טקסט\n\n![x](a.svg)\n")
    assert any("no heading directly above" in p for p in problems)
    assert any("1 charts but 0 headings" in p for p in problems)


def test_a_latin_first_heading_above_a_chart_is_a_violation():
    problems = br.chart_heading_violations("### P3 — עקומת כיול\n\n![x](a.svg)\n")
    assert any("not a Hebrew letter" in p for p in problems)


def test_a_second_chart_under_the_same_heading_is_a_violation():
    problems = br.chart_heading_violations("### עקומת כיול\n\n![a](a.svg)\n\n![b](b.svg)\n")
    assert any("2 charts but 1 headings" in p for p in problems)


def test_the_number_of_charts_equals_the_number_of_hebrew_headings_over_two_charts():
    text = GOOD + "\n### צורת הקשר\n\n![x](docs/b.svg)\n"
    assert br.chart_heading_violations(text) == []


def test_the_real_p4s_chart_reference_would_pass_the_rule():
    text = "### עקומת כיול P4S\n\n![P4S calibration curve](docs/calibration_curve_P4S.svg)\n"
    assert br.chart_heading_violations(text) == []
    assert (REPO / "docs" / "calibration_curve_P4S.svg").is_file()


@pytest.mark.parametrize("line, is_heading", [
    ("# title", True),
    ("###### six hashes", True),
    ("###", True),                       # an empty heading is still a heading
    ("   ### three spaces of indent", True),
    ("### closed ###", True),
    ("#עקומת כיול", False),              # no space after the hashes
    ("####### seven hashes", False),
    ("    ### four spaces: an indented code block", False),
    ("עקומת כיול", False),
    ("", False),
])
def test_is_atx_heading_follows_commonmark(line, is_heading):
    assert br.is_atx_heading(line) is is_heading


def test_a_hash_with_no_space_above_a_chart_is_not_a_heading():
    problems = br.chart_heading_violations("#עקומת כיול\n\n![x](a.svg)\n")
    assert any("no heading directly above" in p for p in problems)


def test_seven_hashes_above_a_chart_is_not_a_heading():
    assert br.chart_heading_violations("####### עקומת כיול\n\n![x](a.svg)\n")


def test_an_indented_code_line_above_a_chart_is_not_a_heading():
    assert br.chart_heading_violations("    ### עקומת כיול\n\n![x](a.svg)\n")


def test_a_setext_heading_is_not_accepted_the_report_uses_atx_only():
    assert br.chart_heading_violations("עקומת כיול\n==========\n\n![x](a.svg)\n")


def test_the_closing_hash_sequence_is_not_part_of_the_rendered_heading():
    assert br.rendered_heading_text("### עקומת כיול ###") == "עקומת כיול"
    assert br.rendered_heading_text("### שפת C#") == "שפת C#"        # a '#' with no space before it stays


@pytest.mark.parametrize("image", [
    '![x](a.svg "a title")',
    "![x](a.svg 'a title')",
    "![x](a.svg (a title))",
    "![x](A.SVG)",
    "  ![x](a.svg)  ",
])
def test_an_svg_image_with_a_title_or_odd_spelling_is_still_a_chart(image):
    """If the image were not recognised as a chart, a bad heading above it
    would slip through unchecked."""
    bad = br.chart_heading_violations(f"### P3 — עקומת כיול\n\n{image}\n")
    assert any("not a Hebrew letter" in p for p in bad), image
    assert br.chart_heading_violations(f"### עקומת כיול\n\n{image}\n") == [], image


def test_a_chart_after_a_closed_fence_is_checked_again():
    text = "```\ncode\n```\n\n![x](a.svg)\n"
    assert any("no heading directly above" in p for p in br.chart_heading_violations(text))


LATIN_HEADING = "### P3 — עקומת כיול\n\n"
HEBREW_HEADING = "### עקומת כיול\n\n"


def _violations_with(heading: str, rest: str) -> list[str]:
    return br.chart_heading_violations(heading + rest)


# --- numbers that are not numbers --------------------------------------------
@pytest.mark.parametrize("value", [float("nan"), float("inf"), float("-inf"), Decimal("NaN"), Decimal("Infinity")])
def test_a_non_finite_number_is_refused_by_every_format(value):
    for fmt in ("int", "comma", "pct2", "num1"):
        with pytest.raises(br.ReportError, match="not a finite number"):
            br.format_value(value, fmt)


@pytest.mark.parametrize("literal", ["NaN", "Infinity", "-Infinity"])
def test_a_non_finite_number_in_a_source_never_reaches_the_report(literal, tmp_path, monkeypatch):
    """json.loads accepts these literals, so a source file can carry them."""
    (tmp_path / "models").mkdir()
    (tmp_path / "models" / "metrics.json").write_text('{"x": %s}' % literal, encoding="utf-8")
    monkeypatch.setitem(br.MANIFEST, "bad_ref", br.Ref("metrics", ("x",), "pct2"))
    monkeypatch.setitem(br.MANIFEST, "bad_derived", br.Derived("one_minus", (("metrics", ("x",)),), "pct2"))
    sources = br.Sources(root=tmp_path)
    for placeholder in ("bad_ref", "bad_derived"):
        with pytest.raises(br.ReportError, match="not a finite number"):
            br.render_report(f"Accuracy: ${placeholder}%", sources=sources)


# --- the allow-list for images and raw HTML (review round 3) -----------------
NBSP = chr(0xA0)


def _problems(rest: str, heading: str = HEBREW_HEADING) -> list[str]:
    return br.chart_heading_violations(heading + rest)


def test_a_fence_closed_by_a_non_breaking_space_cannot_hide_a_chart():
    """Review round 3, finding 1. Code fences are not tracked at all any more, so
    there is nothing to desynchronise: the chart is simply checked."""
    md = "~~~\n~~~" + NBSP + "\n~~~\n\n" + LATIN_HEADING + "![x](a.svg)\n"
    assert any("not a Hebrew letter" in p for p in br.chart_heading_violations(md))


def test_an_img_tag_split_over_two_lines_is_refused():
    """Review round 3, finding 2: the opening tag decides, not the line its src is on."""
    assert any("raw HTML is limited" in p for p in _problems('<img\nsrc="a.svg">\n', LATIN_HEADING))


def test_a_reference_definition_split_over_two_lines_cannot_hide_a_chart():
    """Review round 3, finding 3: reference-style images are not accepted at all."""
    problems = _problems("[fig]:\na.svg\n\n![x][fig]\n", LATIN_HEADING)
    assert any("an image must be written inline" in p for p in problems)


# --- every "![" that is not one of the two exact forms is a violation ---------
@pytest.mark.parametrize("markup", [
    "ראו ![x](a.svg) כאן",                       # inside a sentence
    "> ![x](a.svg)",                             # blockquote
    "- ![x](a.svg)",                             # bullet
    "1. ![x](a.svg)",                            # ordered list
    "| ![x](a.svg) |",                           # table cell
    "*![x](a.svg)*",                             # emphasis
    "[![x](a.svg)](http://x)",                   # wrapped in a link
    "# ![x](a.svg)",                             # inside a heading
    "![x](a.svg) ![y](b.svg)",                   # two on a line
    "![x](a.svg) כיתוב",                         # image then text
    "כיתוב ![x](a.svg)",                         # text then image
    "![x][fig]",                                 # reference style: full
    "![fig][]",                                  # collapsed
    "![fig]",                                    # shortcut
    "![x][nope]",                                # undefined label (refused, not guessed)
    "![x\ny](a.svg)",                            # alt text over two lines
    "![x](\na.svg)",                             # target on the next line
    "![x](a&#46;svg)",                           # entity-encoded dot
    "![x](a&period;svg)",
    "![x](a%2Esvg)",                             # percent-encoded dot
    "![x](data:image/svg+xml;base64,AAAA)",      # data URI
    "![x](a.svg?raw=1)",                         # query string
    "![x](a.svg#view)",                          # fragment
    "![x](a.svg",                                # never closed
    "![x](a.bmp)",                               # extension that is not allowed
])
def test_an_image_that_is_not_one_of_the_two_exact_forms_is_refused(markup):
    problems = _problems(markup + "\n", LATIN_HEADING)
    assert any("an image must be written inline" in p for p in problems), markup


# --- raw HTML is an allow-list: details, summary, br and comments -------------
@pytest.mark.parametrize("markup", [
    '<img src="a.svg">',
    '<img\nsrc="a.svg">',
    "<IMG SRC='a.svg'>",
    '<img/src="a.svg">',
    '<picture><source srcset="a.svg"></picture>',
    '<svg width="1"></svg>',
    '<object data="a.svg"></object>',
    '<embed src="a.svg">',
    '<iframe src="a.svg"></iframe>',
    '<video poster="a.svg"></video>',        # the one a picture-element blocklist missed
    '<audio src="a.svg"></audio>',
    '<canvas data-src="a.svg"></canvas>',
    '<div style="background:url(a.svg)">x</div>',
    '<a href="x"><img src="a.svg"></a>',
    "<span>x</span>",
    '<a href="x">link</a>',                   # a single-letter tag ALONE (no <img> to mask it)
    "<p>paragraph</p>",
    "<b>bold</b>",
    "<i>x</i>",
    "<objective>",
    "<imgs>",
    "<!DOCTYPE html>",
    "<![CDATA[x]]>",
    "<?xml version='1.0'?>",
])
def test_any_raw_html_tag_outside_the_allow_list_is_refused(markup):
    problems = _problems(markup + "\n", LATIN_HEADING)
    assert any("raw HTML is limited" in p for p in problems), markup


@pytest.mark.parametrize("text", [
    "<details>",
    "</details>",
    "<DETAILS open>",
    "<summary>פרטים טכניים</summary>",
    "שורה<br>אחרת<br/>ועוד<BR>",
    "<!-- הערה למחבר -->",
    "המודל טוב ב-p<0.05 וגם 3<5 ו-A>B",       # a "<" not followed by a letter is text
    "a < b",
])
def test_the_html_that_a_report_may_use_is_accepted(text):
    assert _problems(text + "\n", LATIN_HEADING) == [], text


def test_a_folded_section_with_a_chart_inside_is_still_checked():
    md = "<details>\n<summary>פרטים</summary>\n\n" + LATIN_HEADING + "![x](a.svg)\n\n</details>\n"
    assert any("not a Hebrew letter" in p for p in br.chart_heading_violations(md))
    ok = "<details>\n<summary>פרטים</summary>\n\n" + HEBREW_HEADING + "![x](a.svg)\n\n</details>\n"
    assert br.chart_heading_violations(ok) == []


# --- inline code, fences and rasters ----------------------------------------
@pytest.mark.parametrize("line", [
    "``![x](a.svg)`",                # unequal runs: renders an image beside literal backticks (review round 4)
    "`![x](a.svg)``",
    "```![x](a.svg)``",
    "`![x](a.svg)`",                 # balanced: harmless to a reader, still refused (fail closed)
    "``![x](a.svg)``",
    "ראו `![x](a.svg)` בדוגמה",
    "`ראו ![x](a.svg) כאן",          # an unclosed backtick
    "ו-``![y][z]`` בדוגמה",
])
def test_image_syntax_is_refused_even_next_to_backticks(line):
    """Code spans are not tracked at all. An earlier version stripped them before
    scanning, and unequal backtick runs made it hide a real image."""
    for heading in (LATIN_HEADING, HEBREW_HEADING):
        assert any("an image must be written inline" in p for p in _problems(line + "\n", heading)), (line, heading)


@pytest.mark.parametrize("line", ["`<img>` ו-`n<m` הן דוגמאות", "``a`<img>`b``", "`<div>`"])
def test_html_inside_backticks_is_refused_like_any_other_html(line):
    assert any("raw HTML is limited" in p for p in _problems(line + "\n", LATIN_HEADING)), line


# --- headings above a chart: no entities, no escapes (review round 4) --------
@pytest.mark.parametrize("heading", [
    "### &#80;3 — עקומת כיול",            # displayed as "P3"
    "### &#0080;3 — עקומת כיול",
    "### &#x50;3 — עקומת כיול",
    "### &#X50;3 — עקומת כיול",
    "### &Aopf;3 — עקומת כיול",           # a named entity for a Latin-looking letter
    "### &amp;P3 — עקומת כיול",
    "### [&#80;3](x.md) — עקומת כיול",    # an entity inside a link label
    "### &#8207;עקומת כיול",              # an invisible right-to-left mark
    "### &#1506;קומת כיול",               # a Hebrew letter by entity: refused too (fail closed)
    "### עקומת &amp; כיול",
    "### " + chr(92) + "P3 — עקומת כיול",
    "### עקומת" + chr(92) + " כיול",
    "### " + chr(92) + "*עקומת* כיול",
])
def test_a_chart_heading_with_an_entity_or_a_backslash_is_refused(heading):
    problems = br.chart_heading_violations(heading + "\n\n![x](a.svg)\n")
    assert any("may not contain" in p for p in problems), heading


def test_the_ampersand_and_backslash_rule_applies_only_to_headings_above_a_chart():
    assert br.chart_heading_violations("### &#80;3 — כותרת רגילה\n\nטקסט ללא גרף\n") == []
    assert br.chart_heading_violations("טקסט עם & וגם " + chr(92) + " באמצע\n") == []


def test_a_plain_hebrew_heading_above_a_chart_is_still_accepted():
    assert br.chart_heading_violations("### עקומת כיול P3\n\n![x](a.svg)\n") == []


def test_image_syntax_inside_a_code_fence_is_still_checked_a_documented_false_positive():
    """Fences are not tracked, so a chart written inside one cannot hide. The cost
    is that image syntax shown in a fenced example is flagged: write such an
    example in an inline code span instead."""
    assert br.chart_heading_violations("```\n![x](a.svg)\n```\n")


@pytest.mark.parametrize("image", [
    "![shot](a.png)",
    "![shot](a.jpg)",
    "![shot](a.JPEG)",
    "![shot](a.gif)",
    "![shot](a.webp)",
    '![shot](a.png "a title")',
    "  ![shot](a.png)  ",
])
def test_a_raster_image_alone_on_its_line_is_allowed_and_needs_no_heading(image):
    assert br.chart_heading_violations(image + "\n") == []
    assert br.chart_heading_violations(LATIN_HEADING + image + "\n") == []      # not a chart, so the heading is not judged


def test_an_angle_bracket_target_is_refused_it_would_read_as_an_html_tag():
    assert br.chart_heading_violations(HEBREW_HEADING + "![x](<a b.svg>)\n")
    assert br.chart_heading_violations("![x](<a b.png>)\n")


def test_a_backslash_escaped_dot_is_a_literal_target_that_renders_as_a_chart_and_is_checked():
    target = "a" + chr(92) + ".svg"
    assert br.chart_heading_violations(HEBREW_HEADING + f"![x]({target})\n") == []
    bad = br.chart_heading_violations(LATIN_HEADING + f"![x]({target})\n")
    assert any("not a Hebrew letter" in p for p in bad)


@pytest.mark.parametrize("line", [
    "ראו ![x](a.png) כאן",              # text before
    "![x](a.png) כיתוב",                # text after
    "![x](a.png) ![y](b.png)",          # two rasters on one line
    "![x](a.png) ![y](b.svg)",          # a raster then a chart
])
def test_a_raster_image_that_is_not_alone_on_its_line_is_refused(line):
    assert br.chart_heading_violations(line + "\n"), line


def test_a_plain_link_to_an_svg_file_is_not_an_image_and_is_allowed():
    assert br.chart_heading_violations("ראו [את הגרף](docs/a.svg) בקובץ.\n") == []


# ---------------------------------------------------------------------------
# The digit scan is INFORMATIONAL
# ---------------------------------------------------------------------------
def test_digit_scan_counts_literal_digits_and_ignores_placeholders():
    scan = br.scan_template_digits("פרק 3 — $p3_acc% ו-$$5 ו-${n_2024} 12 ו-12")
    assert scan == {"3": 1, "5": 1, "12": 2}


def test_digit_scan_is_sorted_numerically_and_never_raises():
    assert list(br.scan_template_digits("100 9 20 3")) == ["3", "9", "20", "100"]
    assert br.scan_template_digits("") == {}


# ---------------------------------------------------------------------------
# The CLI
# ---------------------------------------------------------------------------
def test_main_reports_a_missing_template_without_writing_anything(monkeypatch, tmp_path, capsys):
    monkeypatch.setattr(br, "DEFAULT_TEMPLATE", tmp_path / "absent.md")
    monkeypatch.setattr(br, "DEFAULT_OUT", tmp_path / "REPORT.md")
    assert br.main([]) == 1
    assert "template not found" in capsys.readouterr().err
    assert not (tmp_path / "REPORT.md").exists()


def test_main_renders_a_template_writes_report_and_prints_the_digit_scan(monkeypatch, tmp_path, capsys):
    template = tmp_path / "t.md"
    template.write_text(GOOD + "\nשיעור: $majority_holdout_pct% מתוך $n_holdout_p3, 7 דוגמאות.\n", encoding="utf-8")
    monkeypatch.setattr(br, "DEFAULT_TEMPLATE", template)
    monkeypatch.setattr(br, "DEFAULT_OUT", tmp_path / "REPORT.md")
    assert br.main([]) == 0
    written = (tmp_path / "REPORT.md").read_text(encoding="utf-8")
    assert "53.71% מתוך 633" in written and "$" not in written
    out = capsys.readouterr().out
    assert "digit sequences" in out and "  7  (x1)" in out


def test_main_refuses_to_write_a_report_that_breaks_the_chart_rule(monkeypatch, tmp_path, capsys):
    template = tmp_path / "t.md"
    template.write_text("### P3 — עקומת כיול\n\n![x](a.svg)\n", encoding="utf-8")
    monkeypatch.setattr(br, "DEFAULT_TEMPLATE", template)
    monkeypatch.setattr(br, "DEFAULT_OUT", tmp_path / "REPORT.md")
    assert br.main([]) == 1
    assert "chart rule violations" in capsys.readouterr().err
    assert not (tmp_path / "REPORT.md").exists()


def test_main_calibration_svg_needs_a_task(capsys):
    assert br.main(["--calibration-svg"]) == 2


# ---------------------------------------------------------------------------
# A2: the committed evidence file (PHASE13.md D9)
# ---------------------------------------------------------------------------
A2_PATH = REPO / "docs" / "p4s_a2_train_tiers.json"


def _a2():
    return json.loads(A2_PATH.read_text(encoding="utf-8"))


def test_a2_has_exactly_the_provenance_fields_and_no_environment_facts():
    assert sorted(_a2()) == [
        "label_definition", "n_train", "population_definition", "source_sha256", "split", "task", "tiers",
    ]
    assert _a2()["task"] == "P4S"
    assert _a2()["split"] == {"function": "scripts.train.split_task", "part": "train"}


def test_a2_is_train_only_and_says_nothing_about_calibration_or_holdout():
    text = A2_PATH.read_text(encoding="utf-8").lower()
    assert "holdout" not in text and "calibration" not in text


def test_a2_source_sha256_equals_the_one_in_findings_json():
    findings = json.loads((REPO / "docs" / "findings.json").read_text(encoding="utf-8"))
    assert _a2()["source_sha256"] == findings["source_metadata"]["source_sha256"]


def test_a2_tier_counts_sum_to_the_p4s_train_size_in_the_artifact_metadata():
    meta = json.loads((REPO / "models" / "P4S.meta.json").read_text(encoding="utf-8"))
    a2 = _a2()
    assert sum(tier["n"] for tier in a2["tiers"].values()) == a2["n_train"] == meta["population_n"]["train"] == 2024


def test_a2_rates_are_n_super_over_n_and_the_mid_pattern_is_the_documented_one():
    tiers = _a2()["tiers"]
    assert sorted(tiers) == ["High", "Low", "Mid"]
    for tier in tiers.values():
        assert tier["rate"] == (tier["n_super"] / tier["n"] if tier["n"] else None)
    # PHASE12A.md: 0% in Low (n=362) and High (n=621), 32.47% in Mid (n=1,041)
    assert (tiers["Low"]["n"], tiers["Low"]["n_super"]) == (362, 0)
    assert (tiers["High"]["n"], tiers["High"]["n_super"]) == (621, 0)
    assert (tiers["Mid"]["n"], tiers["Mid"]["n_super"]) == (1041, 338)


def test_a2_file_uses_the_findings_json_serialization_convention():
    text = _lf(A2_PATH.read_bytes()).decode("utf-8")
    assert text.endswith("}\n")
    assert text == json.dumps(_a2(), sort_keys=True, indent=2, allow_nan=False, ensure_ascii=False) + "\n"


def test_run_a2_prints_what_compute_a2_returns(monkeypatch, capsys):
    from scripts import p4s_diagnosis as diag

    monkeypatch.setattr(diag, "compute_a2", lambda df: {
        "n_population": 10, "n_train": 6, "n_calibration": 2, "n_holdout": 2,
        "tiers": {"Low": {"n": 4, "n_super": 0, "rate": 0.0}, "Mid": {"n": 2, "n_super": 1, "rate": 0.5},
                  "High": {"n": 0, "n_super": 0, "rate": None}},
    })
    diag.run_a2(None)
    out = capsys.readouterr().out
    assert "population=10 train=6 calibration=2 holdout=2" in out
    assert "tier=Mid  n=2     n_super_customer=1    rate=0.5" in out
    assert "tier=High n=0     n_super_customer=0    rate=None" in out


def test_a2_json_regenerates_byte_for_byte_from_the_csv(tmp_path):
    """LOCAL evidence (PHASE13.md D9, CP3): a `passed` here, with the CSV in
    place, is what closes CP3 -- a skip is not evidence."""
    from scripts import p4s_diagnosis as diag

    if not diag.CSV_PATH.exists():
        pytest.skip("real CSV not present (expected in CI)")
    df = ld.load_and_verify_csv(diag.CSV_PATH)
    out = tmp_path / "a2.json"
    diag.write_a2_json(df, diag.CSV_PATH, out)
    assert _lf(out.read_bytes()) == _lf(A2_PATH.read_bytes())


# ---------------------------------------------------------------------------
# The calibration charts, rendered from metrics.json with no training
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("task", ["P3", "P4", "P4S"])
def test_a_calibration_chart_regenerates_byte_for_byte_from_metrics_json(task, tmp_path):
    """P3 and P4 prove the renderer is faithful: regenerated from metrics.json
    they equal the committed charts (line endings aside). P4S, which had no
    chart, must equal its committed file the same way."""
    _skip_byte_equality_in_ci()
    out = tmp_path / f"{task}.svg"
    br.write_calibration_svg(task, out)
    assert _lf(out.read_bytes()) == _lf((REPO / "docs" / f"calibration_curve_{task}.svg").read_bytes())


def _metrics():
    return json.loads((REPO / "models" / "metrics.json").read_text(encoding="utf-8"))


@pytest.mark.parametrize("task", ["P3", "P4", "P4S"])
def test_the_renderer_is_given_the_requested_tasks_own_curve(task, tmp_path, monkeypatch):
    """Runs in CI. The byte comparison above is local evidence, so on its own
    a bug that drew P4S from P3's data would pass CI. This intercepts the call
    to the renderer and checks WHICH task, curve and path it receives."""
    from scripts import train

    calls = []
    monkeypatch.setattr(train, "_svg_calibration_curve", lambda *args: calls.append(args))
    out = tmp_path / "chart.svg"
    br.write_calibration_svg(task, out)

    metrics = _metrics()
    assert calls == [(task, metrics[f"{task}_holdout"]["calibration_curve"], out)]
    # the three curves differ, so a swap between tasks would be visible here
    others = [metrics[f"{other}_holdout"]["calibration_curve"] for other in ("P3", "P4", "P4S") if other != task]
    assert all(curve != calls[0][1] for curve in others)


def test_the_cli_writes_the_p4s_chart_into_docs_with_the_p4s_curve(tmp_path, monkeypatch):
    from scripts import train

    (tmp_path / "docs").mkdir()
    calls = []
    monkeypatch.setattr(train, "_svg_calibration_curve", lambda *args: calls.append(args))
    monkeypatch.setattr(br, "REPO", tmp_path)
    assert br.main(["--calibration-svg", "P4S"]) == 0
    assert calls == [("P4S", _metrics()["P4S_holdout"]["calibration_curve"], tmp_path / "docs" / "calibration_curve_P4S.svg")]


def test_the_p4s_calibration_chart_exists_with_an_english_title_and_a_hebrew_description():
    ns = "{http://www.w3.org/2000/svg}"
    root = ET.parse(REPO / "docs" / "calibration_curve_P4S.svg").getroot()
    assert root.find(f"{ns}title").text == "P4S calibration curve"
    desc = root.find(f"{ns}desc").text
    assert "P4S" in desc and "Holdout" in desc and "עקומת כיול" in desc


def test_the_p4s_chart_is_drawn_from_the_p4s_holdout_curve_in_metrics_json():
    metrics = json.loads((REPO / "models" / "metrics.json").read_text(encoding="utf-8"))
    bins = metrics["P4S_holdout"]["calibration_curve"]["bins"]
    assert sum(b["n"] for b in bins) == metrics["P4S_holdout"]["n_holdout"] == 633
    assert len([b for b in bins if b["n"] > 0]) == 6


@pytest.mark.parametrize("heading", [
    "### [](a b) — עקומת כיול",          # not a link (space in the target): shown literally, starts with 'a'
    "### [ ](a b.svg) עקומת כיול",
    "### [עקומת כיול](a.svg)",           # a link to the SVG itself, above the chart
    "### [P3](x.md) — עקומת כיול",
    "### [עקומת][r] כיול",
    "### עקומת כיול [1]",
    "### עקומת ] כיול",
])
def test_a_chart_heading_with_a_bracket_is_refused(heading):
    problems = br.chart_heading_violations(heading + "\n\n![x](a.svg)\n")
    assert any("may not contain" in p for p in problems), heading


def test_the_bracket_rule_applies_only_to_headings_above_a_chart():
    assert br.chart_heading_violations("### [x](a b) כותרת רגילה\n\nטקסט ללא גרף\n") == []
    assert br.chart_heading_violations("### עקומת כיול (P4S)\n\n![x](a.svg)\n") == []


# ---------------------------------------------------------------------------
# CP4: the real report. The committed REPORT.md must be exactly what the
# template and the committed sources render to (D2), and obey the chart rule.
# ---------------------------------------------------------------------------
def _lf_text(text: str) -> str:
    return text.replace("\r\n", "\n")


def test_the_committed_report_is_what_the_template_renders():
    template = br.DEFAULT_TEMPLATE.read_text(encoding="utf-8")
    assert _lf_text(br.DEFAULT_OUT.read_text(encoding="utf-8")) == _lf_text(br.render_report(template))


def test_the_real_template_satisfies_the_chart_rule():
    rendered = br.render_report(br.DEFAULT_TEMPLATE.read_text(encoding="utf-8"))
    assert br.chart_heading_violations(rendered) == []
    assert "![" in rendered      # the report does contain charts


def test_every_chart_in_the_report_exists_on_disk():
    rendered = br.render_report(br.DEFAULT_TEMPLATE.read_text(encoding="utf-8"))
    targets = re.findall(r"!\[[^\]]*\]\(([^)\s]+\.svg)\)", rendered)
    assert targets
    for target in targets:
        assert (br.REPO / target).is_file(), target


def test_no_unfilled_placeholder_or_nan_survives_in_the_report():
    text = br.DEFAULT_OUT.read_text(encoding="utf-8")
    assert "${" not in text and "nan" not in text.lower().replace("finance", "")


def test_the_report_opens_with_the_five_founder_answers():
    text = _lf_text(br.DEFAULT_OUT.read_text(encoding="utf-8"))
    head = text.split("## 1. ", 1)[0]
    answers = [line for line in head.splitlines() if re.match(r"^[1-5]\. \*\*", line)]
    assert len(answers) == 5
