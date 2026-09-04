"""Tests for scripts/data_contract.py.

checkpoint 4: the full valid+invalid fixture matrix across all three
layers, per PHASE5.md. Layer C is tested as a mechanism (does check_snapshot
correctly detect match/mismatch given expected values that match the small
fixture) -- the real 3,500-row values themselves are only checked at the
integration path (checkpoint 5), not here. Some tests below (checkpoints 2
and 3) started as regression tests for a specific bug a review round found;
they're kept as-is, now folded into the layer they belong to.

Nothing here touches the real funnel_marketing_data.csv or Supabase -- tiny
fixture CSVs, loaded the same way load_data.py loads the real one, so
dtypes match real parsing behaviour (not hand-set via astype()). Runs in CI
with no CSV present, per PHASE5.md D4.
"""
from __future__ import annotations

import hashlib
from pathlib import Path

import pandas as pd
import pytest

from scripts import data_contract as dc
from scripts import load_data as ld

VALID_CSV_TEXT = (
    ",".join(ld.EXPECTED_COLUMNS) + "\n"
    "2500,36,24,12,19,14,11,10,7,5,2,2,4,1250,38.0,1,0,20777.0,No\n"
    "15000,98,55,43,43,32,26,25,18,14,4,5,3,3750,,1,0,,Yes\n"
)


def _load_fixture(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> pd.DataFrame:
    """Write the fixture CSV and load it through load_data, so dtypes match
    real end-to-end parsing (source_row_id included, columns in order)."""
    p = tmp_path / "sample.csv"
    p.write_text(VALID_CSV_TEXT)
    monkeypatch.setattr(ld, "EXPECTED_SHA256", hashlib.sha256(p.read_bytes()).hexdigest())
    return ld.load_and_verify_csv(p)


def test_check_schema_passes_on_a_valid_fixture(tmp_path, monkeypatch):
    df = _load_fixture(tmp_path, monkeypatch)
    assert dc.check_schema(df) == []


def test_check_schema_passes_without_source_row_id(tmp_path, monkeypatch):
    """The only tolerated extra column is source_row_id -- and it's also
    optional: a raw 19-column frame (no derived column at all) is valid."""
    df = _load_fixture(tmp_path, monkeypatch)
    raw = df.drop(columns=["source_row_id"])
    assert dc.check_schema(raw) == []


def test_check_schema_flags_extra_foreign_column(tmp_path, monkeypatch):
    df = _load_fixture(tmp_path, monkeypatch)
    df["bogus_extra"] = 1
    violations = dc.check_schema(df)
    assert any("bogus_extra" in v for v in violations)


def test_check_schema_flags_null_in_not_null_column_even_as_Int64(tmp_path, monkeypatch):
    """dtype alone doesn't prove null-freedom -- pandas' nullable Int64 is
    still an integer dtype while holding an actual null."""
    df = _load_fixture(tmp_path, monkeypatch)
    df["ad_budget"] = df["ad_budget"].astype("Int64")
    df.loc[0, "ad_budget"] = pd.NA
    violations = dc.check_schema(df)
    assert any("ad_budget" in v and "null" in v for v in violations)


def test_check_schema_flags_fractional_value_in_nullable_int_column(tmp_path, monkeypatch):
    """float64 on a nullable-integer column is only legitimate because NaN
    forces it -- a genuine fraction is still a violation."""
    df = _load_fixture(tmp_path, monkeypatch)
    df.loc[0, "cumulative_profit"] = 3.5
    violations = dc.check_schema(df)
    assert any("cumulative_profit" in v and "fractional" in v for v in violations)


def test_check_schema_flags_null_in_referred(tmp_path, monkeypatch):
    df = _load_fixture(tmp_path, monkeypatch)
    df.loc[0, "referred"] = None
    violations = dc.check_schema(df)
    assert any("referred" in v and "null" in v for v in violations)


def test_check_schema_flags_missing_or_reordered_column(tmp_path, monkeypatch):
    df = _load_fixture(tmp_path, monkeypatch)
    renamed = df.rename(columns={"ad_budget": "zzz_ad_budget"})
    violations = dc.check_schema(renamed)
    assert any("mismatch" in v for v in violations)
    assert any("zzz_ad_budget" in v for v in violations)  # also unexpected


def test_check_schema_flags_wrong_dtype_on_not_null_column(tmp_path, monkeypatch):
    df = _load_fixture(tmp_path, monkeypatch)
    df["ad_budget"] = df["ad_budget"].astype(str)
    violations = dc.check_schema(df)
    assert any("ad_budget" in v and "integer dtype" in v for v in violations)


def test_check_schema_flags_wrong_dtype_on_nullable_column(tmp_path, monkeypatch):
    """Neither integer nor float dtype at all -- a category error, distinct
    from the fractional-value case (which is float64, just with a bad
    value)."""
    df = _load_fixture(tmp_path, monkeypatch)
    df["cumulative_profit"] = df["cumulative_profit"].astype(str)
    violations = dc.check_schema(df)
    assert any("cumulative_profit" in v and "nullable integer dtype" in v for v in violations)


def test_check_schema_flags_wrong_dtype_on_referred(tmp_path, monkeypatch):
    df = _load_fixture(tmp_path, monkeypatch)
    df["referred"] = df["referred"].map({"Yes": 1, "No": 0})
    violations = dc.check_schema(df)
    assert any("referred" in v and "text/string dtype" in v for v in violations)


# ---------------------------------------------------------------------------
# Layer B -- invariants (PHASE0.md §ג.1)
# ---------------------------------------------------------------------------

def test_check_invariants_passes_on_a_valid_fixture(tmp_path, monkeypatch):
    df = _load_fixture(tmp_path, monkeypatch)
    assert dc.check_invariants(df) == []


def test_check_invariants_flags_leads_sum_mismatch(tmp_path, monkeypatch):
    df = _load_fixture(tmp_path, monkeypatch)
    df.loc[0, "num_leads"] = df.loc[0, "num_leads"] + 1
    violations = dc.check_invariants(df)
    assert any("leads_answered" in v and "num_leads" in v for v in violations)


def test_check_invariants_flags_monotonicity_violation(tmp_path, monkeypatch):
    df = _load_fixture(tmp_path, monkeypatch)
    df.loc[0, "followup_2"] = df.loc[0, "followup_1"] + 5  # now > followup_1
    violations = dc.check_invariants(df)
    assert any("monotonicity" in v and "followup_2" in v for v in violations)


def test_check_invariants_flags_closing_identity_mismatch(tmp_path, monkeypatch):
    df = _load_fixture(tmp_path, monkeypatch)
    df.loc[0, "followup_5"] = df.loc[0, "followup_5"] + 1
    violations = dc.check_invariants(df)
    assert any("closed + not_closed" in v for v in violations)


def test_check_invariants_flags_negative_value(tmp_path, monkeypatch):
    df = _load_fixture(tmp_path, monkeypatch)
    df.loc[0, "ad_budget"] = -100
    violations = dc.check_invariants(df)
    assert any("ad_budget" in v and "negative" in v for v in violations)


def test_check_invariants_flags_num_leads_not_positive(tmp_path, monkeypatch):
    df = _load_fixture(tmp_path, monkeypatch)
    df.loc[0, "num_leads"] = 0
    violations = dc.check_invariants(df)
    assert any("num_leads" in v and "<= 0" in v for v in violations)


def test_check_invariants_flags_referred_domain_violation(tmp_path, monkeypatch):
    df = _load_fixture(tmp_path, monkeypatch)
    df.loc[0, "referred"] = "Maybe"
    violations = dc.check_invariants(df)
    assert any("referred" in v and "Maybe" in v for v in violations)


# ---------------------------------------------------------------------------
# Layer C -- snapshot expectations (PHASE0.md §ג.2), tested as a mechanism:
# given a DataFrame and expected values that match it, does check_snapshot
# correctly detect match/mismatch. The real 3,500-row values are only
# checked at the integration path (checkpoint 5), not here.
# ---------------------------------------------------------------------------

# Every measured key on the two-row VALID_CSV_TEXT fixture, computed once
# via _measure_snapshot and pinned here -- not retyped by hand.
FIXTURE_SNAPSHOT = {
    "n_rows": 2,
    "missing_ltv_months": 1,
    "missing_cumulative_profit": 1,
    "missing_any": 1,
    "duplicate_rows": 0,
    "duplicate_groups": 0,
    "distinct_ad_budgets": 2,
    "ad_budget_values": (2500, 15000),
    "gap_1501_1999_count": 0,
    "edge_closed_gt0_purchased0": 0,
    "edge_purchased0_ltv_gt0": 0,
    "n_purchased1": 2,
    "n_upsell1_within_purchased1": 0,
    "n_upsell0_within_purchased1": 2,
    "n_referred_yes_within_purchased1": 1,
}


def test_check_snapshot_passes_when_expected_matches_every_key(tmp_path, monkeypatch):
    """The comprehensive valid case -- all fifteen measured keys at once,
    not just the one or two a narrower regression test touches."""
    df = _load_fixture(tmp_path, monkeypatch)
    assert dc.check_snapshot(df, FIXTURE_SNAPSHOT) == []
    # _measure_snapshot's key set must exactly match what's pinned above --
    # catches a metric silently added or removed without updating this test.
    assert set(dc._measure_snapshot(df)) == set(FIXTURE_SNAPSHOT)


def test_check_snapshot_flags_missing_count_mismatch(tmp_path, monkeypatch):
    df = _load_fixture(tmp_path, monkeypatch)
    df.loc[0, "ltv_months"] = None  # row 0 was fully populated -> now also missing
    violations = dc.check_snapshot(df, {"missing_ltv_months": 1, "missing_any": 1})
    assert any("missing_ltv_months" in v for v in violations)
    assert any("missing_any" in v for v in violations)


def test_check_snapshot_flags_edge_case_mismatch(tmp_path, monkeypatch):
    df = _load_fixture(tmp_path, monkeypatch)
    df.loc[0, "purchased"] = 0  # row 0 has closed=2>0 -> now closed>0 & purchased=0
    violations = dc.check_snapshot(df, {"edge_closed_gt0_purchased0": 0})
    assert any("edge_closed_gt0_purchased0" in v for v in violations)


def test_check_snapshot_flags_base_rate_count_mismatch(tmp_path, monkeypatch):
    df = _load_fixture(tmp_path, monkeypatch)
    df.loc[0, "upsell"] = 1  # row 0 was upsell=0
    violations = dc.check_snapshot(
        df, {"n_upsell1_within_purchased1": 0, "n_upsell0_within_purchased1": 2}
    )
    assert any("n_upsell1_within_purchased1" in v for v in violations)
    assert any("n_upsell0_within_purchased1" in v for v in violations)


def test_check_snapshot_unknown_key_raises_keyerror(tmp_path, monkeypatch):
    df = _load_fixture(tmp_path, monkeypatch)
    with pytest.raises(KeyError):
        dc.check_snapshot(df, {"bogus_key": 1})


def test_check_snapshot_partial_dict_only_checks_supplied_keys(tmp_path, monkeypatch):
    """A caller asserting on one metric shouldn't need to supply all
    fifteen -- and an unsupplied, wrong metric must NOT surface."""
    df = _load_fixture(tmp_path, monkeypatch)
    d = df.copy()
    d.loc[0, "ad_budget"] = 999999  # would break ad_budget_values/distinct/gap
    violations = dc.check_snapshot(d, {"n_rows": 2})  # only this key checked
    assert violations == []


def test_check_snapshot_scalar_key_given_a_list_raises_clear_typeerror(tmp_path, monkeypatch):
    """A scalar-valued key (e.g. n_rows) given a list/tuple `expected` must
    fail loudly and clearly -- not with Python's raw 'int object is not
    iterable' from inside the list/tuple normalization."""
    df = _load_fixture(tmp_path, monkeypatch)
    with pytest.raises(TypeError, match="n_rows"):
        dc.check_snapshot(df, {"n_rows": [2]})


def test_check_snapshot_list_key_given_a_scalar_raises_clear_typeerror(tmp_path, monkeypatch):
    """The mirror case: a list-valued key (ad_budget_values) given a bare
    scalar instead of a list/tuple."""
    df = _load_fixture(tmp_path, monkeypatch)
    with pytest.raises(TypeError, match="ad_budget_values"):
        dc.check_snapshot(df, {"ad_budget_values": 16})


def test_check_snapshot_distinct_and_gap_alone_miss_a_value_swap(tmp_path, monkeypatch):
    """distinct_ad_budgets and gap_1501_1999_count alone do not prove the
    values themselves are right -- a swap that keeps both counts unchanged
    passes silently through them."""
    df = _load_fixture(tmp_path, monkeypatch)  # ad_budget: 2500, 15000
    swapped = df.copy()
    swapped.loc[0, "ad_budget"] = 900  # not 2500, still outside [1501,1999]

    violations = dc.check_snapshot(
        swapped, {"distinct_ad_budgets": 2, "gap_1501_1999_count": 0}
    )
    assert violations == [], (
        "sanity check: distinct+gap alone really are insufficient to "
        "detect the swap -- if this fails, the fixture stopped "
        "reproducing the gap this test exists to guard"
    )


def test_check_snapshot_ad_budget_values_catches_the_same_swap(tmp_path, monkeypatch):
    df = _load_fixture(tmp_path, monkeypatch)  # ad_budget: 2500, 15000
    swapped = df.copy()
    swapped.loc[0, "ad_budget"] = 900

    violations = dc.check_snapshot(swapped, {"ad_budget_values": [2500, 15000]})
    assert any("ad_budget_values" in v for v in violations)

    # a list and a tuple expectation must behave identically
    violations_tuple = dc.check_snapshot(swapped, {"ad_budget_values": (2500, 15000)})
    assert any("ad_budget_values" in v for v in violations_tuple)

    # and the untouched fixture still matches its own real values, either way
    assert dc.check_snapshot(df, {"ad_budget_values": [2500, 15000]}) == []
    assert dc.check_snapshot(df, {"ad_budget_values": (2500, 15000)}) == []


DUPLICATE_WITH_NULL_CSV_TEXT = (
    ",".join(ld.EXPECTED_COLUMNS) + "\n"
    "2500,36,24,12,19,14,11,10,7,5,2,2,4,1250,,1,0,20777.0,No\n"
    "2500,36,24,12,19,14,11,10,7,5,2,2,4,1250,,1,0,20777.0,No\n"
)


def test_check_snapshot_counts_a_duplicate_group_keyed_on_a_null(tmp_path, monkeypatch):
    """pandas' groupby default (dropna=True) silently excludes a group
    whose key contains a null -- two rows that are identical including a
    shared NaN in ltv_months must still count as one duplicate group."""
    p = tmp_path / "dup_with_null.csv"
    p.write_text(DUPLICATE_WITH_NULL_CSV_TEXT)
    monkeypatch.setattr(ld, "EXPECTED_SHA256", hashlib.sha256(p.read_bytes()).hexdigest())
    df = ld.load_and_verify_csv(p)

    assert dc.check_snapshot(df, {"duplicate_rows": 2, "duplicate_groups": 1}) == []
