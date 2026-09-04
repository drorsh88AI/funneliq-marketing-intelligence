"""Data contract for funnel_marketing_data.csv, in three semantically
separate layers. See docs/planning/PHASE5.md D5 for the full design.

Layer A (this checkpoint) -- schema: column order and dtypes. A structural
contract; failure here means the file does not even have the shape the rest
of the project assumes.

Layer B (invariants) and layer C (snapshot expectations) are added in
checkpoint 3 -- not implemented yet. All three layers are blocking under the
pinned SHA-256 gate (see load_data.EXPECTED_SHA256): once a file has passed
that gate, a layer-C mismatch is a regression in our own measurement code,
not a report about a different source file.

Column names and dtypes are NOT redefined here -- they are imported from
scripts.load_data, which is the single existing source of truth for the raw
19-column contract (EXPECTED_COLUMNS / NOT_NULL_INT_COLUMNS /
NULLABLE_INT_COLUMNS). A second column list here would be exactly the drift
this layer exists to prevent.
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
