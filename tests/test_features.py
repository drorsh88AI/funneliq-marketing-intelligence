"""Tests for app/features.py, and full parity against docs/feature_matrix.md
(PHASE5.md checkpoint 6).

The parity test PARSES the markdown table -- it does not just re-assert
what the code already says. If a row's P2/P3/P4/P6 cell in the doc is
edited without updating app/features.py (or vice versa), this test fails.
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

from app import features as feat
from scripts.load_data import EXPECTED_COLUMNS

REPO_ROOT = Path(__file__).resolve().parent.parent
FEATURE_MATRIX_MD = REPO_ROOT / "docs" / "feature_matrix.md"

TASKS = ("P2", "P3", "P4", "P6")


def _parse_feature_matrix_table() -> dict[str, dict[str, str]]:
    """Parse docs/feature_matrix.md's per-column table into
    {column: {task: status}}. A data row is any line starting with "| "
    whose second cell is a backtick-quoted name -- the header and the
    "---" separator row don't match that shape, and get skipped.

    Column layout (fixed, by construction of the doc):
    | # | column | granularity | meaning | availability | P2 | P3 | P4 | P6 | note |
    """
    text = FEATURE_MATRIX_MD.read_text(encoding="utf-8")
    parsed: dict[str, dict[str, str]] = {}
    for line in text.splitlines():
        if not line.startswith("| "):
            continue
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        if len(cells) != 10:
            continue
        col_cell = cells[1]
        m = re.fullmatch(r"`(\w+)`", col_cell)
        if not m:
            continue  # not a real column row (header, separator, etc.)
        column = m.group(1)
        if column not in EXPECTED_COLUMNS:
            continue
        # "**Target**" is legitimate emphasis for the target column in the
        # doc, not a different status token -- strip markdown bold before
        # comparing.
        statuses = [c.strip("*").strip() for c in cells[5:9]]
        parsed[column] = dict(zip(TASKS, statuses))
    return parsed


def test_feature_matrix_md_documents_every_source_column():
    parsed = _parse_feature_matrix_table()
    assert set(parsed) == set(EXPECTED_COLUMNS), (
        f"docs/feature_matrix.md must document exactly the 19 raw source "
        f"columns -- missing: {set(EXPECTED_COLUMNS) - set(parsed)}, "
        f"extra/unrecognized: {set(parsed) - set(EXPECTED_COLUMNS)}"
    )


@pytest.mark.parametrize("task", TASKS)
def test_feature_matrix_md_matches_code_for_every_column(task):
    """Full parity, one column at a time: the doc's status cell and
    app/features.py's column_status() must agree, for all 19 columns."""
    parsed = _parse_feature_matrix_table()
    mismatches = [
        (col, parsed[col][task], feat.column_status(col, task))
        for col in EXPECTED_COLUMNS
        if parsed[col][task] != feat.column_status(col, task)
    ]
    assert mismatches == [], (
        f"{task}: doc vs code mismatches (column, doc_status, code_status): {mismatches}"
    )


def test_target_and_excluded_are_disjoint_and_within_the_19_columns():
    for task in TASKS:
        assert feat.TARGET[task] in EXPECTED_COLUMNS
        assert feat.EXCLUDED[task] <= set(EXPECTED_COLUMNS)
        assert feat.TARGET[task] not in feat.EXCLUDED[task]


def test_feature_lists_are_the_19_columns_minus_target_and_excluded():
    for task in TASKS:
        drop = feat.EXCLUDED[task] | {feat.TARGET[task]}
        assert set(feat.FEATURES[task]) == set(EXPECTED_COLUMNS) - drop
        # order matters -- must follow EXPECTED_COLUMNS, not some other order
        assert feat.FEATURES[task] == [c for c in EXPECTED_COLUMNS if c not in drop]


def test_p6_is_the_only_task_where_purchased_is_a_feature():
    """purchased varies in P6's unfiltered population but is constant
    (nunique=1) in P2/P3/P4's purchased=1 population -- SPEC.md § אוכלוסיות
    אימון. This is the one place the four tasks' feature sets genuinely
    differ beyond their own target/leakage columns."""
    assert feat.column_status("purchased", "P6") == "Feature"
    for task in ("P2", "P3", "P4"):
        assert feat.column_status("purchased", task) == "Excluded"


def test_collinear_trio_is_a_feature_candidate_in_every_task():
    """Listed as candidates -- the 2-of-3 reduction is a phase-6 Pipeline
    decision, not made here."""
    for task in TASKS:
        for col in feat.COLLINEAR_TRIO:
            assert col in feat.FEATURES[task]


# ---------------------------------------------------------------------------
# budget_tier boundaries -- every documented edge, including the gap
# ---------------------------------------------------------------------------

@pytest.mark.parametrize(
    "ad_budget,expected_tier",
    [
        (500, "Low"),
        (1500, "Low"),      # Low boundary, inclusive
        (1501, None),       # first value inside the gap
        (1750, None),       # mid-gap
        (1999, None),       # last value inside the gap
        (2000, "Mid"),      # Mid boundary, inclusive
        (5000, "Mid"),      # Mid boundary, inclusive
        (5001, "High"),     # first value above Mid
        (20000, "High"),
    ],
)
def test_budget_tier_boundaries(ad_budget, expected_tier):
    assert feat.budget_tier(ad_budget) == expected_tier


def test_budget_tier_gap_returns_none_not_mid():
    """The gap must not be silently absorbed into "Mid" -- mirrors the
    migration's CASE with no ELSE (PHASE5.md D8)."""
    for v in range(1501, 2000):
        assert feat.budget_tier(v) is None, f"budget_tier({v}) should be None"
