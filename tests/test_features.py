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


def _parse_table_text(text: str) -> dict[str, dict[str, str]]:
    """Parse a feature-matrix markdown table into {column: {task: status}}.
    A data row is any line starting with "| " whose second cell is a
    backtick-quoted name -- the header and the "---" separator row don't
    match that shape, and get skipped. A column seen twice raises rather
    than silently keeping the later row's values.

    Column layout (fixed, by construction of the doc):
    | # | column | granularity | meaning | availability | P2 | P3 | P4 | P6 | note |
    """
    parsed: dict[str, dict[str, str]] = {}
    for line in text.splitlines():
        if not line.startswith("| "):
            continue
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        if len(cells) != 10:
            continue
        m = re.fullmatch(r"`(\w+)`", cells[1])
        if not m:
            continue  # not a real column row (header, separator, etc.)
        column = m.group(1)
        if column in parsed:
            raise ValueError(
                f"column {column!r} appears more than once in the table -- "
                f"a duplicate row must fail loudly, not be silently "
                f"overwritten by the later one"
            )
        # "**Target**" is legitimate emphasis for the target column in the
        # doc, not a different status token -- strip markdown bold before
        # comparing.
        statuses = [c.strip("*").strip() for c in cells[5:9]]
        parsed[column] = dict(zip(TASKS, statuses))
    return parsed


def _parse_feature_matrix_table() -> dict[str, dict[str, str]]:
    """The real docs/feature_matrix.md, parsed and filtered to the 19 raw
    source columns (the doc's own intro/snapshot tables use the same
    "| `code` | ... |" shape for unrelated things, e.g. SPEC.md references
    -- anything not one of the 19 is silently not a column row here)."""
    text = FEATURE_MATRIX_MD.read_text(encoding="utf-8")
    parsed = _parse_table_text(text)
    return {c: s for c, s in parsed.items() if c in EXPECTED_COLUMNS}


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


def test_purchased_is_excluded_for_p2_p3_p4_and_derived_for_p6():
    """purchased varies in P6's unfiltered population but is constant
    (nunique=1) in P2/P3/P4's purchased=1 population -- SPEC.md § אוכלוסיות
    אימון, so it's Excluded there for a population reason, not leakage.
    For P6 it is NOT a direct Feature either, despite varying in the
    population: P6's snapshot availability test is "ad_budget בלבד" (§
    נקודות חיזוי) -- at budget-allocation time nothing is known about
    whether a purchase will happen, so purchased is Derived (substituted
    from the budget-tier profile) exactly like every other P6 candidate
    that isn't ad_budget itself. Granularity (customer- vs campaign-level)
    describes what a column MEANS, not when it's available -- the two
    must not be conflated (this is the exact bug a review round caught:
    an earlier version treated "customer-level" as if it answered the
    availability question)."""
    assert feat.column_status("purchased", "P6") == "Derived"
    for task in ("P2", "P3", "P4"):
        assert feat.column_status("purchased", task) == "Excluded"


def test_collinear_trio_is_a_feature_candidate_in_every_task():
    """Listed as candidates -- the 2-of-3 reduction is a phase-6 Pipeline
    decision, not made here."""
    for task in TASKS:
        for col in feat.COLLINEAR_TRIO:
            assert col in feat.FEATURES[task]


# ---------------------------------------------------------------------------
# Four statuses, not three (SPEC.md § מטריצת זמינות פיצ'רים: Feature /
# Target / נגזרת / מוחרגת). The decisive availability test at P6's
# snapshot is "ad_budget בלבד" (§ נקודות חיזוי) -- ad_budget alone is
# known directly; every OTHER P6 candidate is Derived, regardless of
# whether it happens to be campaign-level or customer-level. Granularity
# answers what a column means, not when it's available -- conflating the
# two is exactly the bug an earlier round of review caught (purchased was
# wrongly kept as a direct Feature on a granularity argument).
# ---------------------------------------------------------------------------

# Hand-listed independently of app/features.py's own derivation
# (FEATURES["P6"] - {"ad_budget"}), so this test isn't tautological -- it
# checks the code's OUTPUT against a reference grounded directly in
# SPEC.md, not against its own formula. All 15 P6 candidates minus
# ad_budget: the collinear trio, the five followup stages, not_closed,
# closed, calls_to_closed, calls_to_not_closed, CAC, and purchased.
_P6_DERIVED_REFERENCE = (
    "num_leads", "leads_answered", "leads_not_answered",
    "followup_1", "followup_2", "followup_3", "followup_4", "followup_5",
    "not_closed", "closed", "calls_to_closed", "calls_to_not_closed",
    "customer_acquisition_cost", "purchased",
)


def test_p6_only_ad_budget_is_a_direct_feature():
    """SPEC.md § נקודות חיזוי: at the P6 snapshot (budget allocation
    moment), ad_budget alone is known directly -- every other P6
    candidate, purchased included, must be Derived, not Feature."""
    assert feat.column_status("ad_budget", "P6") == "Feature"
    for col in _P6_DERIVED_REFERENCE:
        assert feat.column_status(col, "P6") == "Derived", col


def test_every_profile_substituted_column_is_marked_derived():
    """DERIVED_FROM_PROFILE["P6"] must be exactly the 14-column reference
    -- not a subset (something silently still Feature) and not a superset
    (something wrongly marked Derived that shouldn't be, e.g. the target
    or an excluded column leaking in)."""
    assert feat.DERIVED_FROM_PROFILE["P6"] == set(_P6_DERIVED_REFERENCE)
    assert len(feat.DERIVED_FROM_PROFILE["P6"]) == 14
    assert "ad_budget" not in feat.DERIVED_FROM_PROFILE["P6"]
    assert feat.TARGET["P6"] not in feat.DERIVED_FROM_PROFILE["P6"]
    assert feat.DERIVED_FROM_PROFILE["P6"].isdisjoint(feat.EXCLUDED["P6"])


def test_only_p6_ever_has_a_derived_column():
    """P2/P3/P4's snapshot (end of campaign cycle) provides every funnel
    aggregate directly -- no profile substitution, so no Derived status
    anywhere in their columns."""
    for task in ("P2", "P3", "P4"):
        statuses = {feat.column_status(c, task) for c in EXPECTED_COLUMNS}
        assert "Derived" not in statuses, f"{task} should have no Derived column"


def test_features_is_exactly_feature_plus_derived_columns():
    """FEATURES[task] is meant as "everything the model actually consumes
    as input" -- Feature and Derived together, since Derived is still a
    real training signal (only the serving-time value is substituted).
    TARGET/EXCLUDED/FEATURES must stay consistent under the finer-grained
    Feature/Derived split, not just under the old three-status view."""
    for task in TASKS:
        expected = {
            c for c in EXPECTED_COLUMNS
            if feat.column_status(c, task) in ("Feature", "Derived")
        }
        assert set(feat.FEATURES[task]) == expected


def test_duplicate_column_row_in_the_matrix_raises_not_silently_overwritten():
    """Proof the parser's duplicate guard actually works, not just that it
    exists: a two-row fixture with the same column twice must raise --
    the second row must not silently win over dict-key collision."""
    header = (
        "| # | עמודה | גרעיניות | משמעות | זמינות | P2 | P3 | P4 | P6 | הערה |"
    )
    row_a = "| 1 | `ad_budget` | קמפיין | x | x | Feature | Feature | Feature | Feature | x |"
    row_b = "| 2 | `ad_budget` | קמפיין | x | x | Excluded | Feature | Feature | Feature | x |"
    with pytest.raises(ValueError, match="ad_budget"):
        _parse_table_text("\n".join([header, row_a, row_b]))


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
