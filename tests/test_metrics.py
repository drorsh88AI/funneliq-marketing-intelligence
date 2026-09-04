"""Known-answer tests for scripts/analysis.py's package-1, package-5, and
M1-M6 functions (PHASE5.md checkpoints 7, 8, and 9).

Every fixture below is a tiny synthetic CSV, loaded the same way
load_data.py loads the real one (SHA-256 verified, source_row_id added),
with the expected value for each assertion computed BY HAND and written
in a comment next to it -- not by running the function and trusting its
own output. Runs in CI with no CSV present, per PHASE5.md D4/D6.

build_results()/findings rendering are out of scope -- checkpoint 10+.
"""
from __future__ import annotations

import hashlib
import math
from pathlib import Path

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
    import json

    result = an.calls_to_closed(single_record_df)

    assert result["n_purchased1"] == 1
    assert result["n_calls_to_closed_ge_4"] == 1   # calls_to_closed=5 >= 4
    assert result["n_closed_eq_1"] == 1
    assert result["n_closed_ge_2"] == 0             # empty bucket
    assert result["n_closed_eq_1_calls_ge_4"] == 1
    assert result["mean_calls_to_closed_closed_eq_1"] == pytest.approx(5.0)
    assert result["mean_calls_to_closed_closed_ge_2"] is None  # empty bucket -> None, not NaN

    assert result["corr_closed_calls_to_closed"] is None  # undefined with n=1, not NaN

    serialized = json.dumps(result)
    assert "NaN" not in serialized


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


def test_m2_output_has_no_legitimacy_verdict_field(m124_df):
    """The function's contract is consistency evidence, not a legitimacy
    verdict -- its output must be exactly the six evidence keys, with no
    boolean/verdict field (e.g. "legitimate", "is_valid") anywhere."""
    result = an.m2_zero_profit_consistency(m124_df)
    assert set(result) == {
        "n_zero_profit", "n_known_nonzero_profit", "purchased_rate",
        "closed_gt0_rate", "mean_ltv_months", "mean_cac",
    }
    for forbidden in ("legitimate", "legitimacy", "is_valid", "verdict"):
        assert forbidden not in result


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
