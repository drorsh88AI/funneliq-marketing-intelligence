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

# The 19th raw column is text, not int -- not covered by either int list.
TEXT_COLUMNS = ["referred"]


def check_schema(df: pd.DataFrame) -> list[str]:
    """Layer A: column order and dtypes match the raw 19-column contract.

    `df` may carry extra derived columns (e.g. source_row_id, inserted by
    load_data.load_and_verify_csv) -- source_row_id is explicitly not part
    of the source contract (PHASE0.md §ג.3), so those are ignored here.
    Missing or reordered columns among the 19, or a wrong dtype for one of
    them, are reported. Order among violations is deterministic.
    """
    violations: list[str] = []

    present = [c for c in df.columns if c in EXPECTED_COLUMNS]
    if present != EXPECTED_COLUMNS:
        violations.append(
            f"column set/order mismatch: expected {EXPECTED_COLUMNS}, got {present}"
        )
        # Can't meaningfully check per-column dtypes when columns are
        # missing or out of order.
        return violations

    for col in NOT_NULL_INT_COLUMNS:
        if not pd.api.types.is_integer_dtype(df[col]):
            violations.append(
                f"{col}: expected not-null integer dtype, got {df[col].dtype}"
            )

    for col in NULLABLE_INT_COLUMNS:
        # A NaN anywhere in the column forces pandas to read it as float64
        # on load -- that is the expected, correct shape for these two
        # columns, not a violation. int64 is also accepted (no NaN present).
        if not (
            pd.api.types.is_integer_dtype(df[col])
            or pd.api.types.is_float_dtype(df[col])
        ):
            violations.append(
                f"{col}: expected nullable integer dtype (int64, or float64 "
                f"due to NaN), got {df[col].dtype}"
            )

    for col in TEXT_COLUMNS:
        # pandas 3.x infers a StringDtype for text columns by default, not
        # the legacy object dtype -- is_string_dtype covers both.
        if not pd.api.types.is_string_dtype(df[col]):
            violations.append(
                f"{col}: expected text/string dtype, got {df[col].dtype}"
            )

    return violations
