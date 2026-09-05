"""Known-answer tests for scripts/analysis.py's package-1, package-5, and
M1-M6 functions (PHASE5.md checkpoints 7, 8, and 9).

Every fixture below is a tiny synthetic CSV, loaded the same way
load_data.py loads the real one (SHA-256 verified, source_row_id added),
with the expected value for each assertion computed BY HAND and written
in a comment next to it -- not by running the function and trusting its
own output. Runs in CI with no CSV present, per PHASE5.md D4/D6.

build_results()/findings.json are checkpoint 10, SVG rendering is
checkpoint 11, FINDINGS.md's prose rendering is checkpoint 12.
"""
from __future__ import annotations

import hashlib
import inspect
import json
import math
import re
import xml.etree.ElementTree as ET
from pathlib import Path
from string import Template

import pytest

from scripts import analysis as an
from scripts import load_data as ld

# ---------------------------------------------------------------------------
# Shared 8-row fixture for missing_values / budget_tiers / duplicates /
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
        "n_rows": 8,  # the fixture's own row count -- added checkpoint 12
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
    """Both legs SPEC.md requires in phase 5 (P6's leg stays deferred to
    phase 6, PHASE5.md D7): package 1 (Low-tier conversion rate) and
    package 5 (funnel_dropoff on all rows), each with vs. without the
    single excess duplicate row (B) in this fixture."""
    result = an.duplicate_sensitivity(operational_df)
    assert result["n_excess_removed"] == 1  # keep="first" drops only row B

    # --- package 1 leg: unchanged from checkpoint 7, now nested ---
    p1 = result["package1_low_tier"]
    assert p1["population"] == "budget_tier == Low"
    assert p1["with_duplicates"]["n_records"] == 5
    assert p1["with_duplicates"]["conversion_rate"] == pytest.approx(
        (0.1 + 0.1 + 0.1 + 1 / 14 + 0.0) / 5
    )
    assert p1["without_excess_duplicates"]["n_records"] == 4  # A, C, F, G
    assert p1["without_excess_duplicates"]["conversion_rate"] == pytest.approx(
        (0.1 + 0.1 + 1 / 14 + 0.0) / 4
    )
    expected_p1_delta = (0.1 + 0.1 + 0.1 + 1 / 14 + 0.0) / 5 - (0.1 + 0.1 + 1 / 14 + 0.0) / 4
    assert p1["delta"] == pytest.approx(expected_p1_delta)

    # --- package 5 leg: funnel_dropoff on all 8 rows vs. all 7 without B ---
    # leads_answered per row: A=8,B=8,C=15,D=30,E=70,F=10,G=3,H=4
    #   sum(with)=148, sum(without B)=140
    # followup_1:  with sum=117, without=111
    # followup_2:  with sum=96,  without=91
    # followup_3:  with sum=76,  without=72
    # followup_4:  with sum=58,  without=55
    # followup_5:  with sum=41,  without=39
    p5 = result["package5_funnel_dropoff"]
    assert p5["population"] == "all rows"

    with_expected = {
        "followup_1": 1 - 117 / 148,
        "followup_2": 1 - 96 / 117,
        "followup_3": 1 - 76 / 96,
        "followup_4": 1 - 58 / 76,
        "followup_5": 1 - 41 / 58,
    }
    without_expected = {
        "followup_1": 1 - 111 / 140,
        "followup_2": 1 - 91 / 111,
        "followup_3": 1 - 72 / 91,
        "followup_4": 1 - 55 / 72,
        "followup_5": 1 - 39 / 55,
    }
    for stage in with_expected:
        assert p5["with_duplicates"][stage] == pytest.approx(with_expected[stage])
        assert p5["without_excess_duplicates"][stage] == pytest.approx(without_expected[stage])
        # reported even though every stage's delta is small -- never skipped
        assert p5["delta"][stage] == pytest.approx(with_expected[stage] - without_expected[stage])


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


# ---------------------------------------------------------------------------
# funnel_dropoff() -- Σ/Σ, not a per-row mean of ratios. A 2-row fixture
# with simple integer sums, so every stage's fraction is hand-verifiable.
#
#   row  leads_answered  fu1  fu2  fu3  fu4  fu5
#   1    10              8    6    4    2    1
#   2    20              15   10   8    5    3
#   sum  30              23   16   12   7    4
# ---------------------------------------------------------------------------
FUNNEL_DROPOFF_CSV_TEXT = (
    ",".join(ld.EXPECTED_COLUMNS) + "\n"
    "500,13,10,3,8,6,4,2,1,1,0,0,3,100,5.0,1,0,200.0,No\n"
    "800,23,20,3,15,10,8,5,3,2,1,4,5,150,8.0,1,0,400.0,No\n"
)


@pytest.fixture
def funnel_dropoff_df(tmp_path, monkeypatch):
    return _load(FUNNEL_DROPOFF_CSV_TEXT, tmp_path, monkeypatch)


def test_funnel_dropoff_uses_sum_over_sum_not_mean_of_row_ratios(funnel_dropoff_df):
    result = an.funnel_dropoff(funnel_dropoff_df)
    assert result["followup_1"] == pytest.approx(1 - 23 / 30)  # 7/30
    assert result["followup_2"] == pytest.approx(1 - 16 / 23)  # 7/23
    assert result["followup_3"] == pytest.approx(1 - 12 / 16)  # 4/16 = 0.25
    assert result["followup_4"] == pytest.approx(1 - 7 / 12)   # 5/12
    assert result["followup_5"] == pytest.approx(1 - 4 / 7)    # 3/7

    # the per-row-mean alternative PHASE0.md checked and rejected would
    # give a DIFFERENT answer here -- row 1's own ratio is 1-8/10=0.2,
    # row 2's is 1-15/20=0.25, mean=0.225 -- proves this is really Σ/Σ,
    # not silently the rejected formula
    per_row_mean_alternative = ((1 - 8 / 10) + (1 - 15 / 20)) / 2
    assert result["followup_1"] != pytest.approx(per_row_mean_alternative)


# ---------------------------------------------------------------------------
# calls_to_closed() -- purchased=1 population only. 4 purchased rows with
# distinct closed/calls_to_closed combinations, plus one ADVERSARIAL
# purchased=0 row (P5): closed=2 (lands in the closed>=2 bucket if the
# purchased filter leaks) and calls_to_closed=999 (an extreme outlier
# that would wreck mean_calls_to_closed_closed_ge_2 and the correlation
# if it leaked in). A boring excluded row (e.g. closed=0) wouldn't land
# in either bucket and so wouldn't perturb most metrics even if the
# filter were broken -- P5 is deliberately built to break every metric
# below if the exclusion has any bug, not just the population count.
#
#   row  purchased  closed  calls_to_closed
#   P1   1          1       5
#   P2   1          1       3
#   P3   1          2       2
#   P4   1          3       1
#   P5   0          2       999   (adversarial -- must be excluded)
# ---------------------------------------------------------------------------
CALLS_TO_CLOSED_CSV_TEXT = (
    ",".join(ld.EXPECTED_COLUMNS) + "\n"
    "500,10,8,2,6,5,4,3,2,1,1,5,3,100,10.0,1,0,500.0,No\n"    # P1
    "800,15,12,3,10,8,6,4,3,2,1,3,4,120,12.0,1,0,600.0,No\n"  # P2
    "1000,25,20,5,16,13,10,7,5,3,2,2,5,150,15.0,1,1,1200.0,Yes\n"  # P3
    "1500,30,25,5,20,16,12,8,6,3,3,1,6,180,20.0,1,1,2000.0,Yes\n"  # P4
    "2000,40,35,5,28,22,17,12,8,6,2,999,5,200,5.0,0,0,100.0,No\n"  # P5 (adversarial, not purchased)
)


@pytest.fixture
def calls_to_closed_df(tmp_path, monkeypatch):
    return _load(CALLS_TO_CLOSED_CSV_TEXT, tmp_path, monkeypatch)


def test_calls_to_closed(calls_to_closed_df):
    result = an.calls_to_closed(calls_to_closed_df)

    assert result["n_purchased1"] == 4  # P1-P4; P5 excluded
    assert result["n_calls_to_closed_ge_4"] == 1  # only P1 (5 >= 4)
    assert result["n_closed_eq_1"] == 2   # P1, P2
    assert result["n_closed_ge_2"] == 2   # P3, P4
    assert result["n_closed_eq_1_calls_ge_4"] == 1  # within {P1,P2}, only P1

    assert result["mean_calls_to_closed_closed_eq_1"] == pytest.approx((5 + 3) / 2)  # 4.0
    assert result["mean_calls_to_closed_closed_ge_2"] == pytest.approx((2 + 1) / 2)  # 1.5

    # corr([1,1,2,3], [5,3,2,1]) computed by hand:
    #   means: closed=1.75, calls=2.75
    #   deviations: closed=[-.75,-.75,.25,1.25]  calls=[2.25,.25,-.75,-1.75]
    #   sum(products) = -1.6875-.1875-.1875-2.1875 = -4.25
    #   sum(closed_dev^2) = .5625+.5625+.0625+1.5625 = 2.75
    #   sum(calls_dev^2)  = 5.0625+.0625+.5625+3.0625 = 8.75
    #   r = -4.25 / sqrt(2.75 * 8.75) = -4.25 / sqrt(24.0625)
    import math
    expected_r = -4.25 / math.sqrt(2.75 * 8.75)
    assert result["corr_closed_calls_to_closed"] == pytest.approx(expected_r)

    # frequency_by_calls_to_closed: P1-P4 have calls_to_closed 5,3,2,1 --
    # four distinct values, each occurring once. Sum of frequencies must
    # equal n_purchased1 (checkpoint 11 correction, 2026-09-04: this is
    # the actual distribution -- the two per-closed-subgroup means above
    # are complementary summary evidence, not themselves "the
    # distribution").
    assert result["frequency_by_calls_to_closed"] == {1: 1, 2: 1, 3: 1, 5: 1}
    assert sum(result["frequency_by_calls_to_closed"].values()) == result["n_purchased1"]

    # rate_calls_to_closed_ge_4 = 1/4 = 0.25, rate_closed_eq_1_calls_ge_4 =
    # 1/2 = 0.5 -- computed here (checkpoint 12 correction, 2026-09-04),
    # not by dividing raw counts in FINDINGS.md's rendering layer
    assert result["rate_calls_to_closed_ge_4"] == pytest.approx(0.25)
    assert result["rate_closed_eq_1_calls_ge_4"] == pytest.approx(0.5)


def test_calls_to_closed_excludes_adversarial_purchased_0_row_from_every_metric(calls_to_closed_df):
    """P5 is adversarial, not incidental: closed=2 would join the
    closed>=2 bucket (making n_closed_ge_2=3, not 2) and
    calls_to_closed=999 would drag mean_calls_to_closed_closed_ge_2 from
    1.5 to (2+1+999)/3=334.0 and distort the correlation, if the
    purchased=1 filter leaked it in anywhere. Every field below must
    still equal the exact 4-row (P1-P4) known answer -- not just the
    population count, which a boring excluded row could pass by
    accident even with a broken filter."""
    result = an.calls_to_closed(calls_to_closed_df)

    assert result["n_purchased1"] == 4
    assert result["n_calls_to_closed_ge_4"] == 1
    assert result["n_closed_eq_1"] == 2
    assert result["n_closed_ge_2"] == 2  # NOT 3 -- P5's closed=2 must not join this bucket
    assert result["n_closed_eq_1_calls_ge_4"] == 1

    assert result["mean_calls_to_closed_closed_eq_1"] == pytest.approx((5 + 3) / 2)
    # NOT (2+1+999)/3=334.0 -- P5's extreme calls_to_closed must not leak in
    assert result["mean_calls_to_closed_closed_ge_2"] == pytest.approx((2 + 1) / 2)

    import math
    expected_r = -4.25 / math.sqrt(2.75 * 8.75)  # same derivation as test_calls_to_closed
    assert result["corr_closed_calls_to_closed"] == pytest.approx(expected_r)

    # NOT {..., 999: 1} -- P5's extreme calls_to_closed=999 must not appear
    # as its own bucket in the distribution either
    assert result["frequency_by_calls_to_closed"] == {1: 1, 2: 1, 3: 1, 5: 1}

    # same 0.25/0.5 as the clean 4-row population -- P5 must not shift
    # either denominator or numerator
    assert result["rate_calls_to_closed_ge_4"] == pytest.approx(0.25)
    assert result["rate_closed_eq_1_calls_ge_4"] == pytest.approx(0.5)


# ---------------------------------------------------------------------------
# A single-record purchased=1 population -- pandas' Series.corr() on a
# lone point is mathematically undefined (needs at least two pairs) and
# returns NaN, not an exception. Proves _safe_corr() (used by both
# calls_to_closed and correlations) turns that into None, not a raw NaN
# that would break findings.json's JSON validity later.
# ---------------------------------------------------------------------------
SINGLE_RECORD_CSV_TEXT = (
    ",".join(ld.EXPECTED_COLUMNS) + "\n"
    "500,10,8,2,6,5,4,3,2,1,1,5,3,100,10.0,1,0,500.0,No\n"
)


@pytest.fixture
def single_record_df(tmp_path, monkeypatch):
    return _load(SINGLE_RECORD_CSV_TEXT, tmp_path, monkeypatch)


def test_calls_to_closed_single_record_population_correlation_is_none_not_nan(single_record_df):
    """n_p1=1: correlation is undefined (fewer than two valid pairs), not
    computable as any real number -- must come back as None, and the
    whole dict must be JSON-serializable without emitting a bareword NaN."""
    result = an.calls_to_closed(single_record_df)

    assert result["n_purchased1"] == 1
    assert result["n_calls_to_closed_ge_4"] == 1   # calls_to_closed=5 >= 4
    assert result["n_closed_eq_1"] == 1
    assert result["n_closed_ge_2"] == 0             # empty bucket
    assert result["n_closed_eq_1_calls_ge_4"] == 1
    assert result["mean_calls_to_closed_closed_eq_1"] == pytest.approx(5.0)
    assert result["mean_calls_to_closed_closed_ge_2"] is None  # empty bucket -> None, not NaN

    # both denominators (n_purchased1=1, n_closed_eq_1=1) are nonzero here,
    # so both rates are defined: 1/1 = 1.0 either way
    assert result["rate_calls_to_closed_ge_4"] == pytest.approx(1.0)
    assert result["rate_closed_eq_1_calls_ge_4"] == pytest.approx(1.0)

    assert result["corr_closed_calls_to_closed"] is None  # undefined with n=1, not NaN
    assert result["frequency_by_calls_to_closed"] == {5: 1}

    serialized = json.dumps(result)
    assert "NaN" not in serialized


# ---------------------------------------------------------------------------
# rate_calls_to_closed_ge_4 / rate_closed_eq_1_calls_ge_4 -- None when their
# own denominator is 0, never a fabricated 0.0. Two distinct denominators,
# tested separately: n_purchased1 (NO_PURCHASED1_CSV_TEXT has zero
# purchased=1 rows at all) and n_closed_eq_1 (NO_CLOSED_EQ1_CSV_TEXT has
# purchased=1 rows, but none with closed==1 exactly).
# ---------------------------------------------------------------------------
NO_PURCHASED1_CSV_TEXT = (
    ",".join(ld.EXPECTED_COLUMNS) + "\n"
    "500,10,8,2,6,5,4,3,2,1,1,5,3,100,10.0,0,0,500.0,No\n"
)

NO_CLOSED_EQ1_CSV_TEXT = (
    ",".join(ld.EXPECTED_COLUMNS) + "\n"
    "500,10,8,2,6,5,4,3,2,3,0,5,3,100,10.0,1,0,500.0,No\n"  # closed=0, calls_to_closed=5 (>=4)
    "800,15,12,3,10,8,6,4,3,1,2,1,4,120,12.0,1,0,600.0,No\n"  # closed=2, calls_to_closed=1 (<4)
)


@pytest.fixture
def no_purchased1_df(tmp_path, monkeypatch):
    return _load(NO_PURCHASED1_CSV_TEXT, tmp_path, monkeypatch)


@pytest.fixture
def no_closed_eq1_df(tmp_path, monkeypatch):
    return _load(NO_CLOSED_EQ1_CSV_TEXT, tmp_path, monkeypatch)


def test_calls_to_closed_rate_ge_4_is_none_when_no_purchased1_rows(no_purchased1_df):
    result = an.calls_to_closed(no_purchased1_df)
    assert result["n_purchased1"] == 0
    assert result["rate_calls_to_closed_ge_4"] is None  # 0-denominator -> None, not 0.0
    # n_closed_eq_1 is a subset of purchased=1, so it's also empty here
    assert result["n_closed_eq_1"] == 0
    assert result["rate_closed_eq_1_calls_ge_4"] is None


def test_calls_to_closed_rate_closed_eq1_ge_4_is_none_when_no_closed_eq1_rows(no_closed_eq1_df):
    result = an.calls_to_closed(no_closed_eq1_df)
    assert result["n_purchased1"] == 2
    assert result["n_calls_to_closed_ge_4"] == 1  # row 1 only (calls_to_closed=5)
    assert result["rate_calls_to_closed_ge_4"] == pytest.approx(0.5)  # defined: 1/2

    assert result["n_closed_eq_1"] == 0  # neither row has closed==1 (0 and 2)
    assert result["rate_closed_eq_1_calls_ge_4"] is None  # 0-denominator -> None, not 0.0


# ---------------------------------------------------------------------------
# M1 / M2 / M4 -- share a 6-row fixture built around cumulative_profit:
# zero vs. positive vs. missing, spread across tiers and purchased status.
#
#   row  tier  purchased  closed  cumulative_profit  ltv_months  CAC
#   A    Low   1          1       1000.0             10.0        200
#   B    Low   0          0       0.0    (zero)        5.0        150
#   C    Mid   1          2       2000.0             20.0        400
#   D    Mid   0          1       0.0    (zero)        8.0        350
#   E    High  1          0       (missing)          (missing)   900
#   F    Low   1          1       500.0              15.0        180
# ---------------------------------------------------------------------------
M124_CSV_TEXT = (
    ",".join(ld.EXPECTED_COLUMNS) + "\n"
    "500,10,8,2,6,5,4,3,2,1,1,3,4,200,10.0,1,0,1000.0,No\n"      # A
    "800,15,10,5,8,6,5,3,2,2,0,0,3,150,5.0,0,0,0.0,No\n"         # B
    "3000,30,25,5,20,16,12,8,6,4,2,2,5,400,20.0,1,1,2000.0,Yes\n"  # C
    "3000,25,20,5,16,13,10,6,5,4,1,1,4,350,8.0,0,0,0.0,No\n"     # D
    "10000,80,65,15,52,42,33,25,18,18,0,0,6,900,,1,0,,No\n"      # E (missing)
    "500,12,9,3,7,5,4,3,2,1,1,2,4,180,15.0,1,0,500.0,No\n"       # F
)


@pytest.fixture
def m124_df(tmp_path, monkeypatch):
    return _load(M124_CSV_TEXT, tmp_path, monkeypatch)


def test_m1_zero_profit(m124_df):
    result = an.m1_zero_profit(m124_df)
    assert result == {
        "n_zero_profit": 2,       # B, D
        "n_missing_profit": 1,    # E
        "n_negative_profit": 0,
    }


def test_m2_zero_profit_consistency(m124_df):
    """zero-profit group = {B, D}; known-nonzero group = {A, C, F} (E is
    missing, excluded from both -- M2 never imputes)."""
    result = an.m2_zero_profit_consistency(m124_df)

    assert result["n_zero_profit"] == 2
    assert result["n_known_nonzero_profit"] == 3

    # purchased: B=0, D=0 -> mean 0.0 | A=1, C=1, F=1 -> mean 1.0
    assert result["purchased_rate"]["zero_profit"] == pytest.approx(0.0)
    assert result["purchased_rate"]["known_nonzero_profit"] == pytest.approx(1.0)

    # closed>0: B closed=0 (False), D closed=1 (True) -> mean 0.5
    # A closed=1, C closed=2, F closed=1 -- all True -> mean 1.0
    assert result["closed_gt0_rate"]["zero_profit"] == pytest.approx(0.5)
    assert result["closed_gt0_rate"]["known_nonzero_profit"] == pytest.approx(1.0)

    # ltv_months: zero group (B=5.0, D=8.0) -> mean 6.5
    # known-nonzero group (A=10.0, C=20.0, F=15.0) -> mean 15.0
    assert result["mean_ltv_months"]["zero_profit"] == pytest.approx(6.5)
    assert result["mean_ltv_months"]["known_nonzero_profit"] == pytest.approx(15.0)

    # CAC: zero group (B=150, D=350) -> mean 250 | known-nonzero (A=200,C=400,F=180) -> mean 260
    assert result["mean_cac"]["zero_profit"] == pytest.approx(250.0)
    assert result["mean_cac"]["known_nonzero_profit"] == pytest.approx(260.0)

    # zero_rate_by_slice: reverse direction, P(profit=0 | slice), with n /
    # n_zero_profit made explicit per slice -- not the same number as
    # purchased_rate/closed_gt0_rate above under a different name.
    #
    # purchased=0 -> {B, D}, both zero -> n=2, n_zero=2, rate=1.0
    slc = result["zero_rate_by_slice"]["purchased_0"]
    assert slc == {"n": 2, "n_zero_profit": 2, "zero_rate": pytest.approx(1.0)}
    # purchased=1 -> {A, C, E, F}, none zero (E is missing, not zero) -> rate=0.0
    slc = result["zero_rate_by_slice"]["purchased_1"]
    assert slc == {"n": 4, "n_zero_profit": 0, "zero_rate": pytest.approx(0.0)}
    # closed==0 -> {B, E}, only B is zero (E is missing) -> n=2, n_zero=1, rate=0.5
    slc = result["zero_rate_by_slice"]["closed_eq_0"]
    assert slc == {"n": 2, "n_zero_profit": 1, "zero_rate": pytest.approx(0.5)}
    # closed>0 -> {A, C, D, F}, only D is zero -> n=4, n_zero=1, rate=0.25
    slc = result["zero_rate_by_slice"]["closed_gt_0"]
    assert slc == {"n": 4, "n_zero_profit": 1, "zero_rate": pytest.approx(0.25)}


def test_m2_output_has_no_legitimacy_verdict_field(m124_df):
    """The function's contract is consistency evidence, not a legitimacy
    verdict -- its output must be exactly the seven evidence keys, with no
    boolean/verdict field (e.g. "legitimate", "is_valid") anywhere."""
    result = an.m2_zero_profit_consistency(m124_df)
    assert set(result) == {
        "n_zero_profit", "n_known_nonzero_profit", "purchased_rate",
        "closed_gt0_rate", "zero_rate_by_slice", "mean_ltv_months", "mean_cac",
    }
    for forbidden in ("legitimate", "legitimacy", "is_valid", "verdict"):
        assert forbidden not in result


# ---------------------------------------------------------------------------
# M2 direction-divergence fixture: proves zero_rate_by_slice tests the
# REVERSE conditional (P(zero|slice)) and not just purchased_rate re-keyed.
# 5 rows, purchased in {0,1} x zero-profit in {True,False}:
#
#   row  purchased  closed  cumulative_profit
#   1    1          1       100.0
#   2    1          1       200.0
#   3    1          1       300.0
#   4    1          1       0.0    (zero)
#   5    0          0       0.0    (zero)
#
# zero-profit rows = {4, 5} -> purchased_rate["zero_profit"] = P(purchased=1|zero)
#   = 1/2 = 0.5 (row 4 purchased=1, row 5 purchased=0)
# zero_rate_by_slice["purchased_1"]["zero_rate"] = P(zero|purchased=1)
#   = 1/4 = 0.25 (only row 4, among rows 1-4)
# 0.5 != 0.25 -- the two directions are genuinely different numbers.
# ---------------------------------------------------------------------------
M2_DIRECTION_CSV_TEXT = (
    ",".join(ld.EXPECTED_COLUMNS) + "\n"
    "500,10,8,2,6,5,4,3,2,1,1,3,4,200,10.0,1,0,100.0,No\n"   # row 1
    "500,10,8,2,6,5,4,3,2,1,1,3,4,200,10.0,1,0,200.0,No\n"   # row 2
    "500,10,8,2,6,5,4,3,2,1,1,3,4,200,10.0,1,0,300.0,No\n"   # row 3
    "500,10,8,2,6,5,4,3,2,1,1,3,4,200,10.0,1,0,0.0,No\n"     # row 4 (zero)
    "500,10,8,2,6,5,4,3,2,0,1,3,4,200,10.0,0,0,0.0,No\n"     # row 5 (zero)
)


@pytest.fixture
def m2_direction_df(tmp_path, monkeypatch):
    return _load(M2_DIRECTION_CSV_TEXT, tmp_path, monkeypatch)


def test_m2_zero_rate_by_slice_direction_differs_from_purchased_rate(m2_direction_df):
    result = an.m2_zero_profit_consistency(m2_direction_df)

    # P(purchased=1 | zero) = 0.5 -- the existing, kept field
    assert result["purchased_rate"]["zero_profit"] == pytest.approx(0.5)

    # P(zero | purchased=1) = 0.25 -- the new, reverse-direction field
    slc = result["zero_rate_by_slice"]["purchased_1"]
    assert slc == {"n": 4, "n_zero_profit": 1, "zero_rate": pytest.approx(0.25)}

    # The two conditional directions are genuinely different numbers, not
    # the same value under two key names.
    assert result["purchased_rate"]["zero_profit"] != slc["zero_rate"]


def test_m4_profit_by_tier(m124_df):
    result = an.m4_profit_by_tier(m124_df)

    # Low: A(1000.0), B(0.0), F(500.0) -- 3 records, 0 missing
    assert result["Low"]["n_records"] == 3
    assert result["Low"]["n_missing_profit"] == 0
    assert result["Low"]["sum_cumulative_profit"] == pytest.approx(1500.0)  # 1000+0+500
    assert result["Low"]["mean_cumulative_profit"] == pytest.approx(500.0)  # 1500/3

    # Mid: C(2000.0), D(0.0) -- 2 records, 0 missing
    assert result["Mid"]["n_records"] == 2
    assert result["Mid"]["n_missing_profit"] == 0
    assert result["Mid"]["sum_cumulative_profit"] == pytest.approx(2000.0)
    assert result["Mid"]["mean_cumulative_profit"] == pytest.approx(1000.0)

    # High: E only, and E's profit is missing -- sum/mean must be None,
    # not 0 or silently dropped
    assert result["High"]["n_records"] == 1
    assert result["High"]["n_missing_profit"] == 1
    assert result["High"]["sum_cumulative_profit"] is None
    assert result["High"]["mean_cumulative_profit"] is None

    # gap: no rows in this fixture
    assert result["gap"]["n_records"] == 0
    assert result["gap"]["sum_cumulative_profit"] is None

    # sanity: missing counts across tiers sum to the fixture's one missing row
    total_missing = sum(result[t]["n_missing_profit"] for t in ("Low", "Mid", "High", "gap"))
    assert total_missing == 1


# ---------------------------------------------------------------------------
# M3 -- a 10-row fixture built specifically for a tie at the exact-K
# boundary. cumulative_profit values: [100, 100, 90, 80, 70, 60, 50, 40,
# 30, 20] for source_row_id 1..10 -- rows 1 and 2 are tied for the
# highest value.
#
# N=10, K=ceil(0.1*10)=1. Ranked profit DESC, source_row_id ASC as
# tiebreak: row 1 (100) sorts before row 2 (100) -- exact-K = {row 1}
# only. boundary_value=100. Both row 1 AND row 2 have profit==100, so
# n_at_boundary_value=2, and inclusive-ties = every record with
# profit>=100 = {row 1, row 2} = 2 records -- proving ties genuinely
# extend the sensitivity set beyond exact-K.
#
# total_profit = 100+100+90+80+70+60+50+40+30+20 = 640
# exact_k share = 100/640 = 0.15625
# ties share    = 200/640 = 0.3125
# ---------------------------------------------------------------------------
def _m3_row(ad_budget: int, profit: int) -> str:
    return f"{ad_budget},10,8,2,6,5,4,3,2,1,1,2,3,100,10.0,1,0,{profit}.0,No\n"


M3_CSV_TEXT = ",".join(ld.EXPECTED_COLUMNS) + "\n" + "".join(
    _m3_row(b, p)
    for b, p in zip(
        [500, 800, 1000, 1500, 2000, 2500, 3000, 4000, 5000, 6000],
        [100, 100, 90, 80, 70, 60, 50, 40, 30, 20],
    )
)


@pytest.fixture
def m3_df(tmp_path, monkeypatch):
    return _load(M3_CSV_TEXT, tmp_path, monkeypatch)


def test_m3_top_decile_exact_k_and_ties(m3_df):
    result = an.m3_top_decile(m3_df)

    assert result["n_known"] == 10
    assert result["n_missing_profit"] == 0
    assert result["K"] == 1  # ceil(0.1*10)
    assert result["K_fraction_of_N"] == pytest.approx(0.1)
    assert result["boundary_value"] == pytest.approx(100.0)
    assert result["n_at_boundary_value"] == 2  # rows 1 AND 2 both == 100

    # exact-K: only row 1 (the source_row_id tiebreak winner)
    assert result["exact_k"]["n_records"] == 1
    assert result["exact_k"]["profit_share"] == pytest.approx(100 / 640)

    # inclusive ties: row 1 AND row 2 -- one more record than exact-K,
    # proving ties genuinely extend the set, not a no-op
    assert result["inclusive_ties"]["n_records"] == 2
    assert result["inclusive_ties"]["profit_share"] == pytest.approx(200 / 640)
    assert result["inclusive_ties"]["n_records"] != result["exact_k"]["n_records"]


def test_m3_excludes_missing_without_imputing_or_filtering_by_purchased(tmp_path, monkeypatch):
    """A row with missing cumulative_profit must lower n_known and raise
    n_missing_profit, but never be treated as 0 profit, and never be
    dropped based on purchased."""
    text = M3_CSV_TEXT + "1750,10,8,2,6,5,4,3,2,1,1,2,3,100,10.0,0,0,,No\n"  # purchased=0, missing profit
    df = _load(text, tmp_path, monkeypatch)
    result = an.m3_top_decile(df)
    assert result["n_known"] == 10   # unchanged -- the new row doesn't count
    assert result["n_missing_profit"] == 1
    # K and shares are unaffected -- computed only over the known 10
    assert result["K"] == 1
    assert result["exact_k"]["profit_share"] == pytest.approx(100 / 640)


# ---------------------------------------------------------------------------
# M5 -- IQR strict-boundary proof. Two 8-row fixtures, identical except
# for the LAST row's customer_acquisition_cost (CAC): 1150 vs. 1151.
# CAC values: [100, 200, 300, 400, 500, 600, 700, X].
#
# Q1/Q3 for n=8 (pandas quantile, interpolation="linear") are determined
# by ranks 1,2 (Q1) and 5,6 (Q3) ONLY -- verified independent of X, as
# long as X stays the maximum (>=700):
#   Q1 = 200 + 0.75*(300-200) = 275.0
#   Q3 = 600 + 0.25*(700-600) = 625.0
#   IQR = 350.0
#   upper = Q3 + 1.5*IQR = 625 + 525 = 1150.0  (exact, both fixtures)
#
# X=1150 sits AT the boundary -> strict ">" means NOT flagged.
# X=1151 sits just past it -> flagged.
# ---------------------------------------------------------------------------
def _m5_row(ad_budget: int, cac: int) -> str:
    return f"{ad_budget},10,8,2,6,5,4,3,2,1,1,2,3,{cac},10.0,1,0,1000.0,No\n"


def _m5_csv_text(last_cac: int) -> str:
    budgets = [500, 800, 1000, 1500, 2000, 2500, 3000, 4000]
    cacs = [100, 200, 300, 400, 500, 600, 700, last_cac]
    return ",".join(ld.EXPECTED_COLUMNS) + "\n" + "".join(
        _m5_row(b, c) for b, c in zip(budgets, cacs)
    )


@pytest.fixture
def m5_at_boundary_df(tmp_path, monkeypatch):
    return _load(_m5_csv_text(1150), tmp_path, monkeypatch)


@pytest.fixture
def m5_past_boundary_df(tmp_path, monkeypatch):
    return _load(_m5_csv_text(1151), tmp_path, monkeypatch)


def test_m5_iqr_value_exactly_at_boundary_is_not_flagged(m5_at_boundary_df):
    result = an.m5_outliers(m5_at_boundary_df)
    assert result["iqr"]["cells_flagged_per_column"]["customer_acquisition_cost"] == 0


def test_m5_iqr_value_just_past_boundary_is_flagged(m5_past_boundary_df):
    result = an.m5_outliers(m5_past_boundary_df)
    assert result["iqr"]["cells_flagged_per_column"]["customer_acquisition_cost"] == 1


def test_m5_covers_exactly_the_16_non_binary_numeric_columns(m5_at_boundary_df):
    result = an.m5_outliers(m5_at_boundary_df)
    assert len(result["columns"]) == 16
    assert "purchased" not in result["columns"]
    assert "upsell" not in result["columns"]
    assert "referred" not in result["columns"]  # text, not numeric
    assert "source_row_id" not in result["columns"]  # derived, not raw


def test_m5_iqr_and_p1p99_never_unioned_into_one_measure(m5_at_boundary_df):
    """Both methods must be reported separately -- no combined "outlier"
    key anywhere in the output."""
    result = an.m5_outliers(m5_at_boundary_df)
    assert "iqr" in result and "p1_p99" in result
    assert "outlier" not in result  # no unified key
    assert set(result) == {
        "columns", "missing_per_column", "iqr", "p1_p99",
        "n_records_flagged_by_both_methods",
    }


def test_m5_p1_p99_matches_pandas_own_quantile_definition(m5_at_boundary_df):
    """p1/p99's boundary values are exactly what pandas.Series.quantile
    (interpolation="linear") computes -- the specification's own defining
    primitive, not a re-assertion of this module's code. Checked on the
    ad_budget column, which is fully populated (no missing) in this
    fixture."""
    col = m5_at_boundary_df["ad_budget"]
    p1 = col.quantile(0.01, interpolation="linear")
    p99 = col.quantile(0.99, interpolation="linear")
    expected_flags = int(((col < p1) | (col > p99)).sum())

    result = an.m5_outliers(m5_at_boundary_df)
    assert result["p1_p99"]["cells_flagged_per_column"]["ad_budget"] == expected_flags


# ---------------------------------------------------------------------------
# M6 -- must be exactly duplicates()'s output, not a competing
# reimplementation. Reuses the operational_df fixture already defined
# above (its one duplicate pair, A and B).
# ---------------------------------------------------------------------------
def test_m6_duplicate_profile_reuses_duplicates_output_exactly(operational_df):
    assert an.m6_duplicate_profile(operational_df) == an.duplicates(operational_df)


# ---------------------------------------------------------------------------
# checkpoint 10 -- source_metadata, build_results, write_findings_json.
#
# build_results is a NESTED merge (results[name] = func(df) for (name, func)
# in RESULT_BUILDERS.items()), keyed by an explicit registry string, NOT a
# flat union of each function's own keys and NOT func.__name__.
#
# Round 1 (PHASE5.md D6 §3, corrected 2026-09-04, user approved): the
# original spec was a flat union; checking it against the real functions
# found 14 real top-level key collisions (e.g. correlations()["followup_1"]
# is a Pearson r, funnel_dropoff()["followup_1"] is a per-stage dropout
# dict -- same key, different values). Fixed by nesting.
#
# Round 2 (Codex finding on commit 386c6dd): nesting by func.__name__ is
# still not a stable data contract -- a rename refactor (with its test
# renamed to match) silently changes findings.json's keys while every test
# stays green, because __name__ was both the production key and the test's
# own source of truth. Fixed with RESULT_BUILDERS, a hand-typed registry;
# the tests below derive their expectations from RESULT_BUILDERS, and
# test_build_results_key_is_the_registry_key_not_dunder_name proves the
# JSON key tracks the registry, not whatever the callable happens to be
# named.
# ---------------------------------------------------------------------------
def test_source_metadata_fixed_fixture(tmp_path):
    """source_metadata reads a fixed file's bytes and reports its SHA-256.
    The expected hash is HAND-TYPED below, not computed by this test --
    computing it here would be circular (PHASE5.md D6 §2)."""
    p = tmp_path / "fixed.txt"
    p.write_bytes(b"source_metadata fixed fixture content\n")

    assert an.source_metadata(p) == {
        "source_sha256": "f353ca665d47627697c0feb2644f3c1c960783a7c590d339bf43a012525ff2b8"
    }


def test_build_results_closure(tmp_path, monkeypatch):
    """set(results) is exactly set(RESULT_BUILDERS) | {"source_metadata"} --
    no hidden or declared exception, no manual metadata key. Each nested
    value equals calling the registered function directly: build_results
    never recomputes, only merges."""
    df = _load(OPERATIONAL_CSV_TEXT, tmp_path, monkeypatch)
    csv_path = tmp_path / "sample.csv"  # the exact path _load() writes to

    results = an.build_results(df, csv_path)

    expected_keys = set(an.RESULT_BUILDERS) | {"source_metadata"}
    assert set(results) == expected_keys

    for name, func in an.RESULT_BUILDERS.items():
        assert results[name] == func(df)
    assert results["source_metadata"] == {
        "source_sha256": hashlib.sha256(csv_path.read_bytes()).hexdigest()
    }


def test_build_results_key_is_the_registry_key_not_dunder_name(tmp_path, monkeypatch):
    """Regression guard for the Codex finding on commit 386c6dd: the
    JSON/results key must come from RESULT_BUILDERS's own key, not from
    the callable's __name__.

    Round 1 of this test built `results` itself with the same
    comprehension build_results() uses -- Codex correctly pointed out
    that proves the comprehension works, not that build_results()
    itself is keyed correctly; a regression to func.__name__ inside
    build_results() would still pass it. Fixed: monkeypatch.setattr
    replaces the actual an.RESULT_BUILDERS module global with an
    experimental registry (a callable whose __name__ deliberately
    disagrees with its registry key), then calls an.build_results(df,
    csv_path) itself -- the real production function, not a
    re-implementation. If build_results() ever regresses to keying by
    __name__, this fails."""
    df = _load(OPERATIONAL_CSV_TEXT, tmp_path, monkeypatch)
    csv_path = tmp_path / "sample.csv"

    def renamed_but_registered_as_missing_values(frame):
        return an.missing_values(frame)
    renamed_but_registered_as_missing_values.__name__ = "totally_different_name"

    experimental_registry = dict(an.RESULT_BUILDERS)
    experimental_registry["missing_values"] = renamed_but_registered_as_missing_values
    monkeypatch.setattr(an, "RESULT_BUILDERS", experimental_registry)

    results = an.build_results(df, csv_path)  # calls production code, not a copy of it

    assert "missing_values" in results               # the registry key survives
    assert "totally_different_name" not in results   # __name__ never leaks in
    assert results["missing_values"] == an.missing_values(df)
    assert "source_metadata" in results               # source_metadata still merged in


def test_build_results_has_no_flat_key_collision_now_that_it_is_nested(tmp_path, monkeypatch):
    """Regression guard for the collision that forced the nested-merge
    correction: a flat union of budget_tiers()/m4_profit_by_tier()'s tier
    keys (Low/Mid/High/gap) and correlations()/funnel_dropoff()'s
    followup_1..5 keys would silently drop one side. Nested, both survive
    intact and independently addressable."""
    df = _load(OPERATIONAL_CSV_TEXT, tmp_path, monkeypatch)
    csv_path = tmp_path / "sample.csv"
    results = an.build_results(df, csv_path)

    assert results["budget_tiers"]["Low"] != results["m4_profit_by_tier"]["Low"]
    assert set(results["budget_tiers"]["Low"]) == {"n_records", "conversion_rate"}
    assert set(results["m4_profit_by_tier"]["Low"]) == {
        "n_records", "n_missing_profit", "sum_cumulative_profit", "mean_cumulative_profit",
    }


def test_write_findings_json_is_deterministic_json_no_volatile_metadata(tmp_path, monkeypatch):
    df = _load(OPERATIONAL_CSV_TEXT, tmp_path, monkeypatch)
    csv_path = tmp_path / "sample.csv"

    out1 = tmp_path / "findings1.json"
    out2 = tmp_path / "findings2.json"
    # two independently rebuilt results dicts, not the same object twice
    an.write_findings_json(an.build_results(df, csv_path), out1)
    an.write_findings_json(an.build_results(df, csv_path), out2)

    bytes1 = out1.read_bytes()
    assert bytes1 == out2.read_bytes()  # re-run -> byte-identical file

    text = bytes1.decode("utf-8")
    assert "NaN" not in text  # no invalid bareword NaN anywhere
    parsed = json.loads(text)  # must be strictly valid JSON
    assert set(parsed) == set(an.RESULT_BUILDERS) | {"source_metadata"}
    assert "source_sha256" in parsed["source_metadata"]

    # no volatile/environment metadata and no local filesystem path leaked
    for forbidden in ("timestamp", "run_time", "runtime", "generated_at", str(tmp_path)):
        assert forbidden not in text


def test_write_findings_json_raises_on_nan_instead_of_writing_invalid_json(tmp_path):
    """allow_nan=False turns a stray NaN into a loud ValueError, not the
    invalid bareword `NaN` Python's json module would otherwise silently
    emit (not valid per RFC 8259)."""
    bad_results = {"some_func": {"value": float("nan")}}
    out = tmp_path / "bad.json"

    with pytest.raises(ValueError):
        an.write_findings_json(bad_results, out)


# ---------------------------------------------------------------------------
# checkpoint 11 -- 5 SVG charts, PHASE5.md D9. Every SVG_BUILDERS entry
# takes `results` only (never a DataFrame), which is what makes
# recomputing a metric from the CSV inside a chart structurally
# impossible, not just a documented convention.
# ---------------------------------------------------------------------------
_EXPECTED_SVG_FILENAMES = {
    "funnel_dropoff.svg",
    "ad_budget_leads_curve.svg",
    "budget_tier_conversion.svg",
    "calls_to_closed_distribution.svg",
    "correlations_cumulative_profit.svg",
}


def test_svg_builders_take_only_results_dict_no_dataframe():
    """Structural proof, not a convention: none of the 5 chart builders
    can even accept a DataFrame -- their signature is exactly
    (results, out_path)."""
    assert set(an.SVG_BUILDERS) == _EXPECTED_SVG_FILENAMES
    for builder in an.SVG_BUILDERS.values():
        params = list(inspect.signature(builder).parameters)
        assert params == ["results", "out_path"]
        assert not any("df" in p.lower() or "frame" in p.lower() for p in params)


def test_write_svgs_creates_exactly_the_five_expected_files(tmp_path, monkeypatch):
    df = _load(OPERATIONAL_CSV_TEXT, tmp_path, monkeypatch)
    csv_path = tmp_path / "sample.csv"
    results = an.build_results(df, csv_path)

    out_dir = tmp_path / "svg_out"
    out_dir.mkdir()
    written = an.write_svgs(results, out_dir)

    assert set(written) == _EXPECTED_SVG_FILENAMES
    on_disk = {p.name for p in out_dir.glob("*")}
    assert on_disk == _EXPECTED_SVG_FILENAMES  # exactly 5 files, nothing extra


def test_write_svgs_output_is_valid_svg_with_accessible_description(tmp_path, monkeypatch):
    df = _load(OPERATIONAL_CSV_TEXT, tmp_path, monkeypatch)
    csv_path = tmp_path / "sample.csv"
    results = an.build_results(df, csv_path)

    out_dir = tmp_path / "svg_out"
    out_dir.mkdir()
    written = an.write_svgs(results, out_dir)

    ns = "{http://www.w3.org/2000/svg}"
    for path in written.values():
        text = path.read_text(encoding="utf-8")
        root = ET.fromstring(text)  # raises if not well-formed XML
        assert root.tag == f"{ns}svg"

        title = root.find(f"{ns}title")
        desc = root.find(f"{ns}desc")
        assert title is not None and (title.text or "").strip()
        assert desc is not None and (desc.text or "").strip()
        # accessible description is the Hebrew caption/explanation --
        # technical chart labels stay English (matplotlib does no bidi
        # text shaping, so Hebrew glyphs drawn on the chart itself would
        # render in the wrong visual order)
        assert any("֐" <= ch <= "׿" for ch in desc.text)

        # no volatile metadata (generation date, run time, local path)
        for forbidden in ("2026-", "AppData", str(tmp_path)):
            assert forbidden not in text


def test_write_svgs_works_from_a_fabricated_results_dict_with_no_dataframe_anywhere(tmp_path):
    """The strongest provenance proof: this test never constructs a
    DataFrame or loads any CSV at all -- results is a hand-typed dict with
    distinctive, made-up numbers. If any chart builder tried to recompute
    a value from a CSV, there would be no CSV or DataFrame in scope for it
    to use; if it silently invented a value instead of reading `results`,
    the fabricated numbers below couldn't possibly be reflected in
    write_svgs()'s successful, complete output."""
    fake_results = {
        "funnel_dropoff": {
            "followup_1": 0.987654, "followup_2": 0.111111, "followup_3": None,
            "followup_4": 0.5, "followup_5": 0.0,
        },
        "ad_budget_leads_curve": {
            999999: {"n": 1, "median_num_leads": 424242.0},
            111: {"n": 2, "median_num_leads": 3.5},
        },
        "budget_tiers": {
            "Low": {"n_records": 7, "conversion_rate": 0.42},
            "Mid": {"n_records": 0, "conversion_rate": None},
            "High": {"n_records": 3, "conversion_rate": 0.99},
            "gap": {"n_records": 5},
        },
        "calls_to_closed": {
            "n_purchased1": 9, "n_calls_to_closed_ge_4": 1, "n_closed_eq_1": 4,
            "n_closed_ge_2": 5, "n_closed_eq_1_calls_ge_4": 1,
            "mean_calls_to_closed_closed_eq_1": 1.23,
            "mean_calls_to_closed_closed_ge_2": 8.76,
            "corr_closed_calls_to_closed": None,
            "frequency_by_calls_to_closed": {2: 3, 5: 4, 9: 2},
        },
        "correlations": {"ad_budget": 0.5, "num_leads": None, "closed": -0.5},
    }

    out_dir = tmp_path / "svg_out"
    out_dir.mkdir()
    written = an.write_svgs(fake_results, out_dir)

    assert set(written) == _EXPECTED_SVG_FILENAMES
    for path in written.values():
        assert path.exists() and path.stat().st_size > 0
        ET.fromstring(path.read_text(encoding="utf-8"))  # still valid SVG/XML


def test_write_svgs_is_byte_identical_on_rerun(tmp_path, monkeypatch):
    df = _load(OPERATIONAL_CSV_TEXT, tmp_path, monkeypatch)
    csv_path = tmp_path / "sample.csv"
    results = an.build_results(df, csv_path)

    out1, out2 = tmp_path / "svg_out1", tmp_path / "svg_out2"
    out1.mkdir()
    out2.mkdir()
    an.write_svgs(results, out1)
    an.write_svgs(results, out2)

    for filename in _EXPECTED_SVG_FILENAMES:
        assert (out1 / filename).read_bytes() == (out2 / filename).read_bytes()


# ---------------------------------------------------------------------------
# checkpoint 11 correction, 2026-09-04 (Codex finding on commit f50a542):
# None must never render as a drawn 0-height bar -- indistinguishable from
# a genuinely measured zero, and actively wrong for correlations (r=0 is a
# real, meaningful value; None means undefined). Tested directly against
# matplotlib's own Axes object model (ax.patches for bars, ax.texts for
# the "N/A" label) -- not by grepping SVG bytes, since matplotlib renders
# text as vector glyph paths, not literal XML text nodes, so a string
# search for "N/A" in the SVG would never find it even when correct.
# ---------------------------------------------------------------------------
def test_bar_with_na_never_draws_a_bar_for_none():
    fig, ax = an.plt.subplots()
    an._bar_with_na(ax, ["a", "b", "c"], [1.0, None, 3.0], color="#000000")

    assert len(ax.patches) == 2  # exactly 2 real bars -- "b" gets none, not a 0-height one
    assert sorted(p.get_height() for p in ax.patches) == [1.0, 3.0]

    assert [t.get_text() for t in ax.texts] == ["N/A"]  # exactly one N/A label, for "b"
    an.plt.close(fig)


def test_barh_with_na_never_draws_a_bar_for_none():
    """Same guard, horizontal orientation -- what _svg_correlations uses.
    Includes a negative value: a real negative correlation must still be
    drawn (not confused with the None/undefined case)."""
    fig, ax = an.plt.subplots()
    an._barh_with_na(ax, ["x", "y", "z"], [0.5, None, -0.5], color="#000000")

    assert len(ax.patches) == 2
    assert sorted(p.get_width() for p in ax.patches) == [-0.5, 0.5]

    assert [t.get_text() for t in ax.texts] == ["N/A"]
    an.plt.close(fig)


def test_correlations_svg_never_draws_none_as_a_zero_bar(tmp_path, monkeypatch):
    """Regression guard for the Codex finding on commit 623533e: round 1
    of this test never called _svg_correlations at all -- it built a
    separate figure directly with _barh_with_na, proving the helper
    works but nothing about what the builder actually passes it. A
    regression where _svg_correlations converts None to 0.0 (or 0)
    before calling _barh_with_na would still have passed that version
    silently.

    Fixed: monkeypatch.setattr replaces the real an._barh_with_na with a
    spy that records the exact (categories, values) it's called with and
    then forwards to the original -- so _svg_correlations() itself is
    exercised (production code, not a reimplementation) and the real SVG
    is still produced correctly."""
    fake_results = {
        "correlations": {"defined_positive": 0.7, "undefined": None, "defined_negative": -0.3},
    }

    original_barh_with_na = an._barh_with_na
    captured: dict = {}

    def spy(ax, categories, values, color):
        captured["categories"] = list(categories)
        captured["values"] = list(values)
        return original_barh_with_na(ax, categories, values, color)

    monkeypatch.setattr(an, "_barh_with_na", spy)

    an._svg_correlations(fake_results, tmp_path / "corr.svg")

    # explicit alphabetical order -- what _svg_correlations itself sorts by
    assert captured["categories"] == ["defined_negative", "defined_positive", "undefined"]

    values_by_col = dict(zip(captured["categories"], captured["values"]))
    # the undefined column must reach the helper as None -- not 0 or 0.0,
    # which would be indistinguishable from a genuinely measured r=0
    assert values_by_col["undefined"] is None
    # the defined values pass through unchanged, in the right slots
    assert values_by_col["defined_positive"] == 0.7
    assert values_by_col["defined_negative"] == -0.3

    # the real chart file is still produced correctly (spy forwarded to
    # the original helper)
    text = (tmp_path / "corr.svg").read_text(encoding="utf-8")
    assert ET.fromstring(text).tag == "{http://www.w3.org/2000/svg}svg"


# ---------------------------------------------------------------------------
# checkpoint 12 -- FINDINGS.md rendering, PHASE5.md D6 §4.
# ---------------------------------------------------------------------------
def _build_results_and_svgs(tmp_path, monkeypatch):
    """Shared setup for the checkpoint-12 tests below: a small fixture df
    -> real results -> real SVGs written to tmp_path (render_findings_md
    reads their <desc> back, so they must actually exist on disk)."""
    df = _load(OPERATIONAL_CSV_TEXT, tmp_path, monkeypatch)
    csv_path = tmp_path / "sample.csv"
    results = an.build_results(df, csv_path)
    svg_dir = tmp_path / "svg"
    svg_dir.mkdir()
    an.write_svgs(results, svg_dir)
    return results, svg_dir


def test_render_findings_md_raises_on_missing_context_key():
    """string.Template.substitute() (not safe_substitute) is used
    deliberately in render_findings_md/write_findings_md: a missing
    placeholder must raise loudly, not silently render as a literal
    '$name' string an unresolved-variable check might miss."""
    incomplete_ctx = {"pop_full": "3500"}  # deliberately missing almost every key
    with pytest.raises(KeyError):
        an._FINDINGS_TEMPLATE.substitute(incomplete_ctx)


def test_render_findings_md_has_no_unresolved_placeholders(tmp_path, monkeypatch):
    """Defense in depth alongside the KeyError test above: the actual
    rendered output, built through the real production path, must not
    contain a literal $identifier anywhere (the intro's literal
    "$placeholder" documentation string uses $$ -- Template's escape for
    a literal $ -- and must render as a single $, not leak as $$ or stay
    unresolved either)."""
    results, svg_dir = _build_results_and_svgs(tmp_path, monkeypatch)
    text = an.render_findings_md(results, svg_dir)

    assert "$placeholder" in text               # the escaped $$ resolved to a literal $
    assert "$$placeholder" not in text           # not left as the escaped form
    # no OTHER unresolved $name survived -- strip the one known-intentional
    # literal "$placeholder" (from the $$ escape) before checking, since a
    # bare regex would also flag that correct, intended output
    assert not re.search(r"\$[A-Za-z_]", text.replace("$placeholder", ""))


def test_render_findings_md_embeds_all_five_svgs_with_population_and_dataset_description_tags(tmp_path, monkeypatch):
    results, svg_dir = _build_results_and_svgs(tmp_path, monkeypatch)
    text = an.render_findings_md(results, svg_dir)

    for filename in (
        "funnel_dropoff.svg", "ad_budget_leads_curve.svg", "budget_tier_conversion.svg",
        "calls_to_closed_distribution.svg", "correlations_cumulative_profit.svg",
    ):
        assert f"]({filename})" in text  # markdown image reference

    assert text.count("dataset description") >= 10  # every section tagged
    assert "אוכלוסייה" in text  # population label present

    # the accessible <desc> text read back from a real SVG is embedded
    # verbatim as that chart's caption -- not a second hand-typed copy
    funnel_desc = an._read_svg_description(svg_dir / "funnel_dropoff.svg")
    assert funnel_desc in text


def test_render_findings_md_is_byte_identical_on_rerun(tmp_path, monkeypatch):
    results, svg_dir = _build_results_and_svgs(tmp_path, monkeypatch)

    out1, out2 = tmp_path / "F1.md", tmp_path / "F2.md"
    an.write_findings_md(results, svg_dir, out1)
    an.write_findings_md(results, svg_dir, out2)

    assert out1.read_bytes() == out2.read_bytes()


def test_findings_context_reflects_a_results_change_not_a_cached_value(tmp_path, monkeypatch):
    """Provenance guard: mutating a single results field (a copy, not the
    real function output) must change the corresponding number in the
    rendered text, and the old number must no longer appear in that
    field's sentence -- proving the value is read live from `results`,
    not a frozen/hardcoded string in the template."""
    results, svg_dir = _build_results_and_svgs(tmp_path, monkeypatch)

    text_before = an.render_findings_md(results, svg_dir)
    assert "M1 —" in text_before
    m1_section_before = text_before.split("## M1 —")[1].split("## M2")[0]

    mutated = json.loads(json.dumps(results))  # deep copy via round-trip
    original_n = mutated["m1_zero_profit"]["n_zero_profit"]
    mutated_n = original_n + 12345  # distinctive: no fixture value collides with it
    mutated["m1_zero_profit"]["n_zero_profit"] = mutated_n
    text_after = an.render_findings_md(mutated, svg_dir)
    m1_section_after = text_after.split("## M1 —")[1].split("## M2")[0]

    # the mutated value reaches the rendered text through the same
    # thousands-separator formatting production code uses (an._comma) --
    # not a bare str(), which would wrongly expect "12345" instead of
    # "12,345". (Not asserting the old value's absence: when original_n
    # is 0, the M1 prose legitimately contains other literal "0"s --
    # e.g. "cumulative_profit == 0" -- unrelated to zero_profit_n, so
    # that check would be fragile precisely in the fixture's actual case.)
    assert an._comma(mutated_n) in m1_section_after
    assert m1_section_after != m1_section_before


def test_findings_percentages_reflect_the_rate_fields_not_a_recomputation_from_counts(tmp_path, monkeypatch):
    """Provenance guard for the checkpoint 12 correction (Codex finding on
    commit da3e6ff): ge4_pct/closed_eq1_ge4_pct in FINDINGS.md must come
    from results['calls_to_closed']['rate_calls_to_closed_ge_4'] /
    ['rate_closed_eq_1_calls_ge_4'] directly -- _findings_context() may
    only format an already-computed fraction (_pct_from_fraction), never
    divide two counts itself. Mutates ONLY the two rate fields (the raw
    counts n_calls_to_closed_ge_4/n_purchased1/n_closed_eq_1/
    n_closed_eq_1_calls_ge_4 are left exactly as they are) and confirms
    the rendered percentages change to match the new rates -- if the
    context builder were still secretly dividing the counts itself, this
    mutation would have no visible effect at all."""
    results, svg_dir = _build_results_and_svgs(tmp_path, monkeypatch)

    mutated = json.loads(json.dumps(results))  # deep copy via round-trip
    mutated["calls_to_closed"]["rate_calls_to_closed_ge_4"] = 0.6789
    mutated["calls_to_closed"]["rate_closed_eq_1_calls_ge_4"] = 0.1234
    text = an.render_findings_md(mutated, svg_dir)

    assert an._pct_from_fraction(0.6789, 0) + "%" in text   # "68%"
    assert an._pct_from_fraction(0.1234, 2) + "%" in text   # "12.34%"


def test_scan_template_for_digit_sequences(monkeypatch):
    """Exercises the real scan_template_for_digit_sequences() (not a
    reimplementation) against a small controlled template via
    monkeypatch -- proves it finds every maximal digit run with correct
    counts. Not a frozen snapshot of the real FINDINGS.md template's
    digit list: PHASE5.md D6 §5 already rejected an assert+allowlist
    design as brittle once; this function is info output, checked here
    only for correct mechanism, never asserted against the production
    template's specific content."""
    monkeypatch.setattr(an, "_FINDINGS_TEMPLATE", Template("abc 123 def $name ghi 123 jkl 4567"))
    monkeypatch.setattr(an, "_P5_CONCLUSION_TEMPLATE", "no placeholders here, but 89 is a digit run")

    assert an.scan_template_for_digit_sequences() == {"89": 1, "123": 2, "4567": 1}


def test_p5_conclusion_matches_spec_md_verbatim():
    """Acceptance criterion 13: FINDINGS.md's P5 conclusion must be
    identical, word for word, to SPEC.md's own locked wording. Tested
    with a SYNTHETIC set of numbers engineered to equal SPEC's locked
    values exactly under the same rounding rules used in production
    (an._pct_from_fraction/_comma) -- not the real CSV (this project's
    committed tests never substitute real-CSV values for a synthetic
    known-answer fixture). The percentages are pre-divided fractions fed
    through _pct_from_fraction, matching checkpoint 12's corrected
    contract: FINDINGS.md's context layer only formats an
    already-computed fraction (calls_to_closed()'s own
    rate_calls_to_closed_ge_4/rate_closed_eq_1_calls_ge_4 fields in
    production), it never divides two counts itself. Compares against
    SPEC.md's own live text, read from the file at test time, not
    retyped here -- so a transcription slip in the template fails this
    test instead of silently drifting from the locked source of truth."""
    ctx = {
        "dropoff_fourth_pct": an._pct_from_fraction(0.10371680652328663, 1),  # -> "10.4"
        "ge4_n": an._comma(1519),
        "p1_n": an._comma(3163),
        "ge4_pct": an._pct_from_fraction(1519 / 3163, 0),            # -> "48"
        "closed_eq1_ge4_n": an._comma(439),
        "closed_eq1_n": an._comma(488),
        "closed_eq1_ge4_pct": an._pct_from_fraction(439 / 488, 2),   # -> "89.96"
    }
    rendered = Template(an._P5_CONCLUSION_TEMPLATE).substitute(ctx)

    spec_path = Path(__file__).resolve().parent.parent / "docs" / "planning" / "SPEC.md"
    lines = spec_path.read_text(encoding="utf-8").splitlines(keepends=True)
    start = next(i for i, line in enumerate(lines) if "הניסוח שייכתב" in line)
    block: list[str] = []
    started = False
    for line in lines[start + 1:]:
        if line.startswith(">"):
            started = True
            block.append(line)
        elif started:
            break  # blockquote ended
        # else: still skipping the blank line(s) before the blockquote starts
    spec_locked_text = "".join(block)

    assert spec_locked_text, "extraction anchor not found in SPEC.md -- test itself is broken, not a wording mismatch"
    assert rendered == spec_locked_text


# ---------------------------------------------------------------------------
# Checkpoint 13 (phase 6) -- super_customer_profile, deferred from phase
# 5 (PHASE6.md D16). A dedicated fixture, not the shared 8-row one above
# -- none of its rows happen to satisfy the super-customer filter.
# ---------------------------------------------------------------------------
SUPER_CUSTOMER_CSV_TEXT = (
    ",".join(ld.EXPECTED_COLUMNS) + "\n"
    "500,10,8,2,6,5,4,3,2,1,1,3,5,500,40.0,1,1,5000.0,Yes\n"    # super: referred=Yes, upsell=1, ltv=40>=34
    "500,10,8,2,6,5,4,3,2,1,1,3,5,1000,20.0,1,1,2000.0,Yes\n"   # purchased, not super (ltv<34)
    "500,10,8,2,6,5,4,3,2,1,1,3,5,1500,50.0,1,1,3000.0,No\n"    # purchased, not super (not referred)
    "500,10,8,2,6,5,4,3,2,1,1,3,5,99999,50.0,0,1,99999.0,Yes\n" # purchased=0 -> excluded entirely
)


@pytest.fixture
def super_customer_df(tmp_path, monkeypatch):
    return _load(SUPER_CUSTOMER_CSV_TEXT, tmp_path, monkeypatch)


def test_super_customer_profile(super_customer_df):
    result = an.super_customer_profile(super_customer_df)
    assert result["n_super"] == 1
    assert result["n_purchased"] == 3  # the purchased=0 row is excluded entirely
    assert result["pct_of_purchased"] == pytest.approx(1 / 3)
    assert result["pct_of_total_profit"] == pytest.approx(5000 / (5000 + 2000 + 3000))
    assert result["cac_super_mean"] == pytest.approx(500.0)
    assert result["cac_population_mean"] == pytest.approx((500 + 1000 + 1500) / 3)
    assert result["cac_savings_pct"] == pytest.approx(1 - 500 / ((500 + 1000 + 1500) / 3))


def test_super_customer_profile_matches_spec_locked_numbers():
    """The real CSV must reproduce SPEC.md's own stated figures exactly
    -- these are given as ground truth in the brief, not computed here
    for the first time. Skipped when the real CSV isn't present (CI)."""
    csv_path = ld.DEFAULT_CSV
    if not csv_path.exists():
        pytest.skip("real CSV not present (expected in CI)")
    df = ld.load_and_verify_csv(csv_path)
    result = an.super_customer_profile(df)
    assert result["n_super"] == 529
    assert result["n_purchased"] == 3163
    assert result["pct_of_purchased"] == pytest.approx(0.1672, abs=1e-4)
    assert result["pct_of_total_profit"] == pytest.approx(0.3361, abs=1e-4)
    assert result["cac_super_mean"] == pytest.approx(990.71, abs=0.01)
    assert result["cac_population_mean"] == pytest.approx(1437.46, abs=0.01)
    assert result["cac_savings_pct"] == pytest.approx(0.311, abs=1e-3)
