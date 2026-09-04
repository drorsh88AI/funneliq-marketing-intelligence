"""Known-answer tests for scripts/analysis.py's package-1 functions
(PHASE5.md checkpoint 7).

Every fixture below is a tiny synthetic CSV, loaded the same way
load_data.py loads the real one (SHA-256 verified, source_row_id added),
with the expected value for each assertion computed BY HAND and written
in a comment next to it -- not by running the function and trusting its
own output. Runs in CI with no CSV present, per PHASE5.md D4/D6.

Package 5, M1-M6, build_results()/findings rendering are out of scope --
checkpoints 8, 9, 10+ respectively.
"""
from __future__ import annotations

import hashlib
from pathlib import Path

import pytest

from scripts import analysis as an
from scripts import load_data as ld

# ---------------------------------------------------------------------------
# Shared 7-row fixture for missing_values / budget_tiers / duplicates /
# duplicate_sensitivity / ad_budget_leads_curve. Rows A-G; row B is an
# EXACT duplicate of row A (all 19 raw columns identical) -- the fixture's
# only duplicate pair. Row G is the fixture's only row with missing
# ltv_months/cumulative_profit. Every row satisfies all six data_contract
# invariants (verified against the code, not just assumed, in
# test_fixture_is_invariant_valid below).
#
#   row  ad_budget  tier  num_leads  closed  conversion (closed/num_leads)
#   A    500        Low   10         1       0.1
#   B    500        Low   10         1       0.1   (== A, exact duplicate)
#   C    800        Low   20         2       0.1
#   D    3000       Mid   40         4       0.1
#   E    10000      High  100        8       0.08
#   F    500        Low   14         1       1/14 ~= 0.0714286
#   G    800        Low   5          0       0.0   (missing ltv/profit)
#   H    1750       gap   6          0       (in the 1501-1999 gap -> untiered)
# ---------------------------------------------------------------------------
OPERATIONAL_CSV_TEXT = (
    ",".join(ld.EXPECTED_COLUMNS) + "\n"
    "500,10,8,2,6,5,4,3,2,1,1,3,5,500,12.0,1,0,1000.0,No\n"     # A
    "500,10,8,2,6,5,4,3,2,1,1,3,5,500,12.0,1,0,1000.0,No\n"     # B (dup of A)
    "800,20,15,5,12,10,8,6,4,2,2,2,4,400,24.0,1,1,3000.0,Yes\n" # C
    "3000,40,30,10,24,20,16,12,8,4,4,4,6,750,18.0,1,0,5000.0,No\n"  # D
    "10000,100,70,30,56,45,36,28,20,12,8,6,8,1250,30.0,1,1,15000.0,Yes\n"  # E
    "500,14,10,4,8,6,5,4,3,2,1,4,6,600,15.0,1,0,1500.0,No\n"    # F
    "800,5,3,2,2,2,1,1,1,1,0,1,2,200,,1,0,,No\n"                # G (missing)
    "1750,6,4,2,3,3,2,1,1,1,0,1,2,300,8.0,1,0,500.0,No\n"       # H (gap)
)


def _load(text: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    p = tmp_path / "sample.csv"
    p.write_text(text)
    monkeypatch.setattr(ld, "EXPECTED_SHA256", hashlib.sha256(p.read_bytes()).hexdigest())
    return ld.load_and_verify_csv(p)


@pytest.fixture
def operational_df(tmp_path, monkeypatch):
    return _load(OPERATIONAL_CSV_TEXT, tmp_path, monkeypatch)


def test_fixture_is_invariant_valid(operational_df):
    """Sanity check on the fixture itself, not the functions under test --
    if this fails, the known answers below were computed against invalid
    data and none of them can be trusted."""
    from scripts.data_contract import check_schema, check_invariants
    assert check_schema(operational_df) == []
    assert check_invariants(operational_df) == []


def test_missing_values(operational_df):
    assert an.missing_values(operational_df) == {
        "missing_ltv_months": 1,
        "missing_cumulative_profit": 1,
        "missing_any": 1,
    }


def test_budget_tiers(operational_df):
    result = an.budget_tiers(operational_df)

    assert result["Low"]["n_records"] == 5  # A, B, C, F, G
    # (0.1 + 0.1 + 0.1 + 1/14 + 0.0) / 5
    assert result["Low"]["conversion_rate"] == pytest.approx((0.1 + 0.1 + 0.1 + 1 / 14 + 0.0) / 5)

    assert result["Mid"]["n_records"] == 1  # D
    assert result["Mid"]["conversion_rate"] == pytest.approx(0.1)

    assert result["High"]["n_records"] == 1  # E
    assert result["High"]["conversion_rate"] == pytest.approx(0.08)

    # row H (ad_budget=1750) falls in the 1501-1999 gap -- must be counted
    # as its own untiered case, not silently dropped or folded into "Mid"
    assert result["gap"]["n_records"] == 1


def test_duplicates(operational_df):
    result = an.duplicates(operational_df)
    assert result["n_duplicate_rows"] == 2
    assert result["n_groups"] == 1
    [group] = result["groups"]
    assert group["source_row_ids"] == [1, 2]  # A is row 1, B is row 2
    assert group["ad_budget"] == 500
    assert group["budget_tier"] == "Low"
    assert group["group_size"] == 2
    assert group["purchased"] == 1
    assert group["closed"] == 1


def test_duplicate_sensitivity(operational_df):
    result = an.duplicate_sensitivity(operational_df)

    assert result["population"] == "budget_tier == Low"
    assert result["n_excess_removed"] == 1  # keep="first" drops only row B

    assert result["with_duplicates"]["n_records"] == 5
    assert result["with_duplicates"]["conversion_rate"] == pytest.approx(
        (0.1 + 0.1 + 0.1 + 1 / 14 + 0.0) / 5
    )

    assert result["without_excess_duplicates"]["n_records"] == 4  # A, C, F, G
    assert result["without_excess_duplicates"]["conversion_rate"] == pytest.approx(
        (0.1 + 0.1 + 1 / 14 + 0.0) / 4
    )

    # reported even though it's small -- never skipped
    expected_delta = (0.1 + 0.1 + 0.1 + 1 / 14 + 0.0) / 5 - (0.1 + 0.1 + 1 / 14 + 0.0) / 4
    assert result["delta"] == pytest.approx(expected_delta)


def test_ad_budget_leads_curve(operational_df):
    result = an.ad_budget_leads_curve(operational_df)

    assert result[500]["n"] == 3       # A, B, F -> num_leads 10, 10, 14
    assert result[500]["median_num_leads"] == 10.0

    assert result[800]["n"] == 2       # C, G -> num_leads 20, 5
    assert result[800]["median_num_leads"] == 12.5  # (5 + 20) / 2

    assert result[3000]["n"] == 1
    assert result[3000]["median_num_leads"] == 40.0

    assert result[10000]["n"] == 1
    assert result[10000]["median_num_leads"] == 100.0

    # the gap-tier row (1750, budget_tier() -> None) is still a legitimate
    # curve data point -- ad_budget_leads_curve doesn't tier at all
    assert result[1750]["n"] == 1
    assert result[1750]["median_num_leads"] == 6.0


# ---------------------------------------------------------------------------
# correlations() -- a separate, purpose-built 4-row fixture where every
# column except ad_budget and cumulative_profit is held CONSTANT across
# rows (zero variance -> correlation is mathematically undefined, must
# come back as None, not raise or silently vanish), and ad_budget is a
# perfect linear function of cumulative_profit (ad_budget = profit / 2
# exactly) so r = 1.0 exactly -- both ends of the known-answer range are
# exactly hand-verifiable, not just plausible-looking.
# ---------------------------------------------------------------------------
CORRELATION_CSV_TEXT = (
    ",".join(ld.EXPECTED_COLUMNS) + "\n"
    "500,10,8,2,6,5,4,3,2,1,1,2,3,100,10.0,1,0,1000.0,No\n"
    "1000,10,8,2,6,5,4,3,2,1,1,2,3,100,10.0,1,0,2000.0,No\n"
    "1500,10,8,2,6,5,4,3,2,1,1,2,3,100,10.0,1,0,3000.0,No\n"
    "2000,10,8,2,6,5,4,3,2,1,1,2,3,100,10.0,1,0,4000.0,No\n"
)


@pytest.fixture
def correlation_df(tmp_path, monkeypatch):
    return _load(CORRELATION_CSV_TEXT, tmp_path, monkeypatch)


def test_correlations_perfect_linear_and_constant_columns(correlation_df):
    result = an.correlations(correlation_df)

    assert result["ad_budget"] == pytest.approx(1.0)  # ad_budget = profit/2 exactly

    # every other numeric column is constant across all 4 rows -> zero
    # variance -> correlation undefined -> None, not omitted or 0.0
    constant_columns = [
        "num_leads", "leads_answered", "leads_not_answered",
        "followup_1", "followup_2", "followup_3", "followup_4", "followup_5",
        "not_closed", "closed", "calls_to_closed", "calls_to_not_closed",
        "customer_acquisition_cost", "purchased", "upsell", "ltv_months",
    ]
    for col in constant_columns:
        assert result[col] is None, col

    assert set(result) == set(constant_columns) | {"ad_budget"}
