"""Data contract for funnel_marketing_data.csv, in three semantically
separate layers. See docs/planning/PHASE5.md D5 for the full design.

Layer A -- schema: column set, order and dtypes. A structural contract;
failure means the file does not even have the shape the rest of the project
assumes. Assumes nothing about layer B/C.

Layer B -- invariants: the six business-structural rules from
PHASE0.md §ג.1 (funnel identities, monotonicity, non-negativity,
referred domain). Assumes df already passed layer A -- reads columns
trusting they exist with the expected dtypes.

Layer C -- snapshot expectations: attributes of THIS source file from
PHASE0.md §ג.2 (row count, missing/duplicate counts, discrete ad_budget
values, base rates). Semantically these are NOT a business rule -- they are
measured facts about the current CSV, not a structural law that must hold
for any valid file. The distinction from layers A/B is real and kept in the
docstrings below. But on every path this module is reached from, the caller
has already gone through the pinned SHA-256 gate (load_data.EXPECTED_SHA256)
before layer C ever runs -- so a file that reaches this layer is, by
construction, the exact same bytes layer C's expected values were measured
against. A mismatch here is therefore not "a different file has different
attributes" -- it is a regression in our own measurement code. All three
layers are blocking for that reason, despite the semantic difference.

Column names and dtypes are NOT redefined here -- they are imported from
scripts.load_data, which is the single existing source of truth for the raw
19-column contract (EXPECTED_COLUMNS / NOT_NULL_INT_COLUMNS /
NULLABLE_INT_COLUMNS). A second column list here would be exactly the drift
this layer exists to prevent.

checkpoint 4 (the full valid+invalid fixture matrix across all three
layers) is not started here -- this checkpoint only adds the layer B/C
functions themselves.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from scripts.load_data import (  # noqa: E402
    EXPECTED_COLUMNS,
    NOT_NULL_INT_COLUMNS,
    NULLABLE_INT_COLUMNS,
)

# The one column load_and_verify_csv derives beyond the raw 19 -- explicitly
# not part of the source contract (PHASE0.md §ג.3), but the only extra
# column layer A tolerates. Any other extra column is a violation.
DERIVED_COLUMNS = ["source_row_id"]

# Text columns = whatever's left of the raw 19 once the two numeric lists
# are subtracted. Derived from the existing source of truth, not a second
# one -- today this is just ["referred"], but stays correct if the raw
# contract ever grows another text column.
TEXT_COLUMNS = [
    c for c in EXPECTED_COLUMNS
    if c not in NOT_NULL_INT_COLUMNS and c not in NULLABLE_INT_COLUMNS
]


def check_schema(df: pd.DataFrame) -> list[str]:
    """Layer A: column set, order, dtype, and schema-level nullability match
    the raw 19-column contract.

    `df` may carry exactly one derived extra column, source_row_id
    (inserted by load_data.load_and_verify_csv) -- any OTHER extra column is
    reported, not silently dropped. Missing/reordered columns among the 19,
    a wrong dtype, a null in a column the contract says is never null, or a
    fractional value in a nullable-integer column, are all reported. Value
    membership (e.g. referred in {Yes, No}) is layer B's job, not this one.
    """
    violations: list[str] = []

    allowed = set(EXPECTED_COLUMNS) | set(DERIVED_COLUMNS)
    unexpected = [c for c in df.columns if c not in allowed]
    if unexpected:
        violations.append(
            f"unexpected column(s) not in the source contract: {unexpected}"
        )

    present = [c for c in df.columns if c in EXPECTED_COLUMNS]
    if present != EXPECTED_COLUMNS:
        violations.append(
            f"column set/order mismatch: expected {EXPECTED_COLUMNS}, got {present}"
        )
        # Can't meaningfully check per-column dtype/nullability when columns
        # among the 19 are missing or out of order.
        return violations

    for col in NOT_NULL_INT_COLUMNS:
        if not pd.api.types.is_integer_dtype(df[col]):
            violations.append(
                f"{col}: expected not-null integer dtype, got {df[col].dtype}"
            )
        elif df[col].isna().any():
            # pandas' nullable Int64 dtype is still an "integer dtype" by
            # is_integer_dtype() even when it holds nulls -- dtype alone
            # does not prove null-freedom, has to be checked separately.
            violations.append(f"{col}: is a not-null column but contains null(s)")

    for col in NULLABLE_INT_COLUMNS:
        dtype = df[col].dtype
        if pd.api.types.is_integer_dtype(dtype):
            # Whole-valued by construction (numpy int64 can't hold NaN;
            # pandas' nullable Int64 can hold NA but never a fraction).
            continue
        if not pd.api.types.is_float_dtype(dtype):
            violations.append(
                f"{col}: expected nullable integer dtype (int64, or float64 "
                f"due to NaN), got {dtype}"
            )
            continue
        # float64 here is only legitimate because a NaN forces it on load --
        # every non-null value still has to be integer-valued, not a real
        # fraction.
        non_null = df[col].dropna()
        fractional = non_null[(non_null % 1) != 0]
        if not fractional.empty:
            violations.append(
                f"{col}: float dtype must be due to NaN only -- found "
                f"{len(fractional)} fractional value(s), e.g. {fractional.iloc[0]}"
            )

    for col in TEXT_COLUMNS:
        # pandas 3.x infers a StringDtype for text columns by default, not
        # the legacy object dtype -- is_string_dtype covers both.
        if not pd.api.types.is_string_dtype(df[col]):
            violations.append(
                f"{col}: expected text/string dtype, got {df[col].dtype}"
            )
        elif df[col].isna().any():
            violations.append(
                f"{col}: is a not-null text column but contains null(s)"
            )

    return violations


# The funnel stage chain checked for monotonicity by invariant 2 below.
FUNNEL_CHAIN = [
    "leads_answered", "followup_1", "followup_2", "followup_3",
    "followup_4", "followup_5",
]

# Every numeric column, not-null and nullable together -- invariant 4
# (non-negativity) applies to all of them, per PHASE0.md §ג.1.
NUMERIC_COLUMNS = NOT_NULL_INT_COLUMNS + NULLABLE_INT_COLUMNS


def check_invariants(df: pd.DataFrame) -> list[str]:
    """Layer B: the six business-structural invariants from PHASE0.md §ג.1.

    Assumes df already passed check_schema (layer A) -- reads columns
    trusting they exist with the expected dtypes; does not re-check
    presence or dtype itself.
    """
    violations: list[str] = []

    # 1. leads_answered + leads_not_answered = num_leads
    bad = int((df["leads_answered"] + df["leads_not_answered"] != df["num_leads"]).sum())
    if bad:
        violations.append(
            f"leads_answered + leads_not_answered != num_leads in {bad} row(s)"
        )

    # 2. monotonic funnel chain: each stage <= the one before it
    for prev_col, cur_col in zip(FUNNEL_CHAIN, FUNNEL_CHAIN[1:]):
        bad = int((df[cur_col] > df[prev_col]).sum())
        if bad:
            violations.append(
                f"monotonicity violated: {cur_col} > {prev_col} in {bad} row(s)"
            )

    # 3. closed + not_closed = followup_5 (the closing identity -- NOT
    # leads_answered, see SPEC.md)
    bad = int((df["closed"] + df["not_closed"] != df["followup_5"]).sum())
    if bad:
        violations.append(f"closed + not_closed != followup_5 in {bad} row(s)")

    # 4. zero negative values, in every numeric column
    for col in NUMERIC_COLUMNS:
        bad = int((df[col].dropna() < 0).sum())
        if bad:
            violations.append(f"{col}: {bad} negative value(s)")

    # 5. num_leads > 0
    bad = int((df["num_leads"] <= 0).sum())
    if bad:
        violations.append(f"num_leads <= 0 in {bad} row(s)")

    # 6. referred domain -- value membership only; null-freedom is layer A's
    # job (already checked there).
    bad_values = sorted(set(df["referred"].dropna().unique()) - {"Yes", "No"})
    if bad_values:
        violations.append(
            f"referred: unexpected value(s) {bad_values}, expected only Yes/No"
        )

    return violations


def _measure_snapshot(df: pd.DataFrame) -> dict[str, int | tuple[int, ...]]:
    """Compute every layer-C metric from PHASE0.md §ג.2, generically from
    any df that has passed layer A. Every value is an exact integer count
    or a tuple of exact integers -- no percentage or float ever appears in
    this layer, so there is no rounding/tolerance question to get wrong.
    Base rates (e.g. the 46.35% upsell figure) are represented as the
    numerator/denominator counts that produce them, not as a pre-divided
    float.
    """
    # dropna=False -- a duplicate group whose key includes a null (e.g. two
    # rows sharing the same NaN in ltv_months/cumulative_profit) is still a
    # real duplicate group. pandas' groupby default (dropna=True) silently
    # excludes NaN-keyed groups from ngroups, undercounting them.
    dup_mask = df.duplicated(subset=EXPECTED_COLUMNS, keep=False)
    dup_rows = int(dup_mask.sum())
    dup_groups = (
        int(df[dup_mask].groupby(EXPECTED_COLUMNS, dropna=False).ngroups)
        if dup_rows else 0
    )

    # The 1501-1999 gap in the 16 discrete ad_budget values (SPEC.md) --
    # inclusive of both ends, since 1500 and 2000 are themselves valid
    # discrete values and not part of the gap.
    in_gap = df["ad_budget"].between(1501, 1999)

    purchased1 = df[df["purchased"] == 1]

    return {
        "n_rows": int(len(df)),
        "missing_ltv_months": int(df["ltv_months"].isna().sum()),
        "missing_cumulative_profit": int(df["cumulative_profit"].isna().sum()),
        "missing_any": int(
            df[["ltv_months", "cumulative_profit"]].isna().any(axis=1).sum()
        ),
        "duplicate_rows": dup_rows,
        "duplicate_groups": dup_groups,
        "distinct_ad_budgets": int(df["ad_budget"].nunique()),
        # The exact sorted set of values, not just its size -- 16 distinct
        # values and zero in the gap do not prove they are the RIGHT 16
        # values; a swapped-in value of a different amount could pass both
        # counts while being outside the documented discrete list.
        "ad_budget_values": tuple(sorted(int(v) for v in df["ad_budget"].unique())),
        "gap_1501_1999_count": int(in_gap.sum()),
        "edge_closed_gt0_purchased0": int(
            ((df["closed"] > 0) & (df["purchased"] == 0)).sum()
        ),
        "edge_purchased0_ltv_gt0": int(
            ((df["purchased"] == 0) & (df["ltv_months"] > 0)).sum()
        ),
        "n_purchased1": int(len(purchased1)),
        "n_upsell1_within_purchased1": int((purchased1["upsell"] == 1).sum()),
        "n_upsell0_within_purchased1": int((purchased1["upsell"] == 0).sum()),
        "n_referred_yes_within_purchased1": int(
            (purchased1["referred"] == "Yes").sum()
        ),
    }


def check_snapshot(
    df: pd.DataFrame, expected: dict[str, int | list[int] | tuple[int, ...]]
) -> list[str]:
    """Layer C: snapshot expectations from PHASE0.md §ג.2 -- attributes of
    THIS source file, not a business rule (see module docstring for why
    that still makes it blocking here).

    `expected` may be a partial dict: only the keys present are checked, so
    a small fixture test can assert just the one or two metrics relevant to
    it without supplying all of them. An unknown key is a test bug, not a
    silent no-op, and raises immediately. See _measure_snapshot for the
    full set of measurable keys.

    A list-valued expectation (e.g. ad_budget_values) is accepted as either
    a list or a tuple -- both compare by value against the measured tuple,
    never reduced to a count, a percentage, or a hash.
    """
    measured = _measure_snapshot(df)
    violations: list[str] = []
    for key, want in expected.items():
        if key not in measured:
            raise KeyError(f"check_snapshot: unknown expectation key {key!r}")
        got = measured[key]
        if isinstance(got, tuple) or isinstance(want, (list, tuple)):
            mismatch = tuple(got) != tuple(want)
        else:
            mismatch = got != want
        if mismatch:
            violations.append(f"{key}: expected {want}, measured {got}")
    return violations
