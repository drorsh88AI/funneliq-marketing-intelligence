"""Package 1 + package 5 (ניקוי + EDA) pure computation functions --
PHASE5.md checkpoints 7 and 8.

Every function takes a DataFrame (already through
load_data.load_and_verify_csv -- SHA-256 verified, source_row_id added,
schema/invariant-valid) and returns a dict. No I/O, no globals, no file
reads inside these functions -- matches the design in PHASE5.md D6.
tests/test_metrics.py proves each one against a small fixture with a
by-hand-computed answer.

M1-M6 are checkpoint 9. build_results()/findings rendering are
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
    """Both non-P6 sensitivity legs SPEC.md requires (PHASE5.md D7): the
    P6 leg is deferred to phase 6 entirely, not implemented here.

    - package 1: budget_tier == Low conversion rate (closed/num_leads
      mean per row) -- the tier every one of the 10 excess duplicate
      rows falls in.
    - package 5: the funnel_dropoff() stage rates, on the full
      population (dropout is a campaign-level funnel metric, not
      tier-scoped).

    Each leg compares the metric with the full data against the same
    metric with the 10 excess duplicate rows removed (keep="first" per
    group) -- reported even when the difference is negligible, never
    skipped."""
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

    with_low, without_low = _low_tier_rate(df), _low_tier_rate(without)
    low_delta = None
    if with_low["conversion_rate"] is not None and without_low["conversion_rate"] is not None:
        low_delta = with_low["conversion_rate"] - without_low["conversion_rate"]

    with_dropoff, without_dropoff = funnel_dropoff(df), funnel_dropoff(without)
    dropoff_delta = {
        stage: (
            with_dropoff[stage] - without_dropoff[stage]
            if with_dropoff[stage] is not None and without_dropoff[stage] is not None
            else None
        )
        for stage in with_dropoff
    }

    return {
        "n_excess_removed": int(excess_mask.sum()),
        "package1_low_tier": {
            "population": "budget_tier == Low",
            "with_duplicates": with_low,
            "without_excess_duplicates": without_low,
            "delta": low_delta,
        },
        "package5_funnel_dropoff": {
            "population": "all rows",
            "with_duplicates": with_dropoff,
            "without_excess_duplicates": without_dropoff,
            "delta": dropoff_delta,
        },
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


# The funnel stage chain, cumulative-sum dropout rate at each step
# (mirrors data_contract's FUNNEL_CHAIN -- not reimported to keep this
# module's only cross-file dependency the ones it already has).
_FUNNEL_CHAIN = [
    "leads_answered", "followup_1", "followup_2", "followup_3",
    "followup_4", "followup_5",
]


def funnel_dropoff(df: pd.DataFrame) -> dict:
    """Stage-by-stage dropout rate, one per followup stage, using
    cumulative sums (Σ/Σ) -- 1 - Σ(stage)/Σ(previous stage) -- NOT a
    per-row mean of individual ratios. PHASE0.md verified this by
    checking both formulas against the documented reference values: Σ/Σ
    matches exactly (21.7/25.7/18.6/10.4/29.2), the per-row-mean
    alternative is off by up to 0.6 percentage points and was rejected.
    Runs over whatever population df represents -- dropout is a
    campaign-level funnel metric, not scoped to purchased=1."""
    out: dict = {}
    for i, (prev_col, cur_col) in enumerate(zip(_FUNNEL_CHAIN, _FUNNEL_CHAIN[1:]), start=1):
        prev_sum = df[prev_col].sum()
        cur_sum = df[cur_col].sum()
        out[f"followup_{i}"] = float(1 - cur_sum / prev_sum) if prev_sum else None
    return out


def calls_to_closed(df: pd.DataFrame) -> dict:
    """Distribution of calls_to_closed within the purchased=1 population
    -- SPEC.md's own established reading of this column (PHASE0.md's
    verified reference numbers). calls_to_closed is documented as a
    record-level average, not a per-deal call history (SPEC.md § עובדות
    שנמדדו) -- every quantity below stays explicit about which unit
    (record vs. deal) and which subpopulation it's counted over, per
    SPEC.md's warning against conflating the two."""
    p1 = df[df["purchased"] == 1]
    n_p1 = len(p1)

    closed1 = p1[p1["closed"] == 1]
    closed2p = p1[p1["closed"] >= 2]

    return {
        "n_purchased1": int(n_p1),
        "n_calls_to_closed_ge_4": int((p1["calls_to_closed"] >= 4).sum()),
        "n_closed_eq_1": int(len(closed1)),
        "n_closed_ge_2": int(len(closed2p)),
        "n_closed_eq_1_calls_ge_4": int((closed1["calls_to_closed"] >= 4).sum()),
        "mean_calls_to_closed_closed_eq_1": (
            float(closed1["calls_to_closed"].mean()) if len(closed1) else None
        ),
        "mean_calls_to_closed_closed_ge_2": (
            float(closed2p["calls_to_closed"].mean()) if len(closed2p) else None
        ),
        "corr_closed_calls_to_closed": (
            float(p1["closed"].corr(p1["calls_to_closed"])) if n_p1 else None
        ),
    }
