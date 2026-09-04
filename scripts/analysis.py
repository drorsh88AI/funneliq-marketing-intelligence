"""Package 1 (ניקוי + EDA) pure computation functions -- PHASE5.md checkpoint 7.

Every function takes a DataFrame (already through
load_data.load_and_verify_csv -- SHA-256 verified, source_row_id added,
schema/invariant-valid) and returns a dict. No I/O, no globals, no file
reads inside these functions -- matches the design in PHASE5.md D6.
tests/test_metrics.py proves each one against a small fixture with a
by-hand-computed answer.

Package 5 (funnel dropout, calls_to_closed distribution, funnel-level
duplicate sensitivity) is NOT implemented here -- checkpoint 8, not this
one. M1-M6 are checkpoint 9. build_results()/findings rendering are
checkpoint 10+. Nothing here performs modeling, splits data, or touches
Supabase (D10).

⚠ Every value returned here is a dataset description (SPEC.md §
גרעיניות מעורבת's "מוסק בלבד" framing, and PHASE5.md D3): none of it is a
causal claim, and none of it may be used to choose features, thresholds,
or a model in phase 6 (D3's table of what may/may not cross into phase 6).
"""
from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from app.features import budget_tier  # noqa: E402
from scripts.data_contract import (  # noqa: E402
    EXPECTED_COLUMNS,
    NOT_NULL_INT_COLUMNS,
    NULLABLE_INT_COLUMNS,
    _measure_snapshot,
)

BUDGET_TIERS = ("Low", "Mid", "High")


def missing_values(df: pd.DataFrame) -> dict:
    """Missing counts for the two nullable columns -- reuses
    data_contract's own snapshot measurement rather than recomputing the
    same three numbers a second way."""
    snap = _measure_snapshot(df)
    return {
        "missing_ltv_months": snap["missing_ltv_months"],
        "missing_cumulative_profit": snap["missing_cumulative_profit"],
        "missing_any": snap["missing_any"],
    }


def budget_tiers(df: pd.DataFrame) -> dict:
    """Per-tier record count and conversion rate (mean of closed/num_leads
    per row, matching the Runtime view's formula -- SPEC.md's row-level
    convention, not sum/sum). Rows in the 1501-1999 gap (budget_tier()
    returns None) are counted separately, not silently dropped or folded
    into a tier."""
    tiers = df["ad_budget"].apply(budget_tier)
    row_rate = df["closed"] / df["num_leads"]

    out: dict = {}
    for name in BUDGET_TIERS:
        mask = tiers == name
        out[name] = {
            "n_records": int(mask.sum()),
            "conversion_rate": float(row_rate[mask].mean()) if mask.any() else None,
        }
    gap_mask = tiers.isna()
    out["gap"] = {"n_records": int(gap_mask.sum())}
    return out


def duplicates(df: pd.DataFrame) -> dict:
    """Every duplicate group (identical across all 19 raw columns, keep=
    False) -- source_row_ids, ad_budget/tier, group size, and the shared
    purchased/closed values (identical within a group by definition of
    "duplicate"). Requires source_row_id on df."""
    dup_mask = df.duplicated(subset=EXPECTED_COLUMNS, keep=False)
    dup_df = df[dup_mask]

    groups = []
    for _, g in dup_df.groupby(EXPECTED_COLUMNS, dropna=False):
        budget = int(g["ad_budget"].iloc[0])
        groups.append({
            "source_row_ids": sorted(int(x) for x in g["source_row_id"]),
            "ad_budget": budget,
            "budget_tier": budget_tier(budget),
            "group_size": int(len(g)),
            "purchased": int(g["purchased"].iloc[0]),
            "closed": int(g["closed"].iloc[0]),
        })
    groups.sort(key=lambda x: x["source_row_ids"][0])

    return {
        "n_duplicate_rows": int(dup_mask.sum()),
        "n_groups": len(groups),
        "groups": groups,
    }


def duplicate_sensitivity(df: pd.DataFrame) -> dict:
    """Package 1's sensitivity leg only (SPEC.md's other two legs --
    package 5's funnel/dropout metrics, and P6 -- are out of scope here;
    P6's leg is deferred to phase 6 entirely, PHASE5.md D7). Compares the
    Low-tier conversion rate with the full data against the same metric
    with the 10 excess duplicate rows removed (keep="first" per group) --
    reported even if the difference is negligible, never skipped."""
    excess_mask = df.duplicated(subset=EXPECTED_COLUMNS, keep="first")
    without = df[~excess_mask]

    def _low_tier_rate(frame: pd.DataFrame) -> dict:
        tiers = frame["ad_budget"].apply(budget_tier)
        mask = tiers == "Low"
        rate = (frame["closed"] / frame["num_leads"])[mask]
        return {
            "n_records": int(mask.sum()),
            "conversion_rate": float(rate.mean()) if mask.any() else None,
        }

    with_dups = _low_tier_rate(df)
    without_excess = _low_tier_rate(without)
    delta = None
    if with_dups["conversion_rate"] is not None and without_excess["conversion_rate"] is not None:
        delta = with_dups["conversion_rate"] - without_excess["conversion_rate"]

    return {
        "population": "budget_tier == Low",
        "with_duplicates": with_dups,
        "without_excess_duplicates": without_excess,
        "delta": delta,
        "n_excess_removed": int(excess_mask.sum()),
    }


def correlations(df: pd.DataFrame) -> dict:
    """Pearson r of every other numeric raw column against
    cumulative_profit -- a dataset-description table (SPEC.md § עובדות
    שנמדדו already reports one example of exactly this, CAC↔ad_budget),
    not a feature-selection step (D3: not used to choose phase-6
    features). pandas' Series.corr() drops NaN pairwise, so each column's
    own missing values and cumulative_profit's 29 missing are each
    handled independently, per pair. A constant column (zero variance)
    correlates to NaN -- reported as None, not silently omitted."""
    candidates = [c for c in NOT_NULL_INT_COLUMNS + NULLABLE_INT_COLUMNS if c != "cumulative_profit"]
    out: dict = {}
    for col in candidates:
        r = df[col].corr(df["cumulative_profit"])
        out[col] = None if pd.isna(r) else float(r)
    return out


def ad_budget_leads_curve(df: pd.DataFrame) -> dict:
    """Median num_leads and record count for each distinct ad_budget value
    present in df -- the raw material for the ad_budget→num_leads curve
    (checkpoint 11's SVG plots from this, not itself)."""
    out: dict = {}
    for budget, group in df.groupby("ad_budget"):
        out[int(budget)] = {
            "n": int(len(group)),
            "median_num_leads": float(group["num_leads"].median()),
        }
    return out
