"""Package 1 + package 5 + M1-M6 (ניקוי + EDA) pure computation functions --
PHASE5.md checkpoints 7, 8, and 9.

Every function takes a DataFrame (already through
load_data.load_and_verify_csv -- SHA-256 verified, source_row_id added,
schema/invariant-valid) and returns a dict. No I/O, no globals, no file
reads inside these functions -- matches the design in PHASE5.md D6.
tests/test_metrics.py proves each one against a small fixture with a
by-hand-computed answer.

build_results() (checkpoint 10) merges these functions' output plus
source_metadata() -- the one function below that touches the filesystem
-- into `results`, nested by an explicit RESULT_BUILDERS registry key,
not func.__name__ (PHASE5.md D6 §3, corrected 2026-09-04 in two rounds:
a flat key union collides for real across several of these functions,
and __name__ is not a stable data contract). write_findings_json()
serializes `results` straight to docs/findings.json -- also checkpoint
10, already implemented here. Only FINDINGS.md's prose rendering (with
$placeholder substitution) and the SVG charts are checkpoints 11-12.
Nothing here performs modeling, splits data, or touches Supabase (D10).

⚠ Every value returned here is a dataset description (SPEC.md §
גרעיניות מעורבת's "מוסק בלבד" framing, and PHASE5.md D3): none of it is a
causal claim, and none of it may be used to choose features, thresholds,
or a model in phase 6 (D3's table of what may/may not cross into phase 6).
"""
from __future__ import annotations

import json
import math
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
from scripts.load_data import sha256_of  # noqa: E402

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


def _safe_corr(a: pd.Series, b: pd.Series) -> float | None:
    """Pearson r, with every NaN-producing case (fewer than two valid
    pairs after alignment, zero variance in either side, or an empty
    input) turned into None instead of a NaN float. NaN is not valid
    JSON (json.dumps emits the bareword `NaN`, which no strict JSON
    parser accepts) -- findings.json must never carry one, so every
    caller of this module routes correlations through here rather than
    calling .corr() directly."""
    r = a.corr(b)
    return None if pd.isna(r) else float(r)


def correlations(df: pd.DataFrame) -> dict:
    """Pearson r of every other numeric raw column against
    cumulative_profit -- a dataset-description table (SPEC.md § עובדות
    שנמדדו already reports one example of exactly this, CAC↔ad_budget),
    not a feature-selection step (D3: not used to choose phase-6
    features). pandas' Series.corr() drops NaN pairwise, so each column's
    own missing values and cumulative_profit's 29 missing are each
    handled independently, per pair. A constant column (zero variance)
    correlates to NaN -- reported as None (_safe_corr), not silently
    omitted and never a raw NaN."""
    candidates = [c for c in NOT_NULL_INT_COLUMNS + NULLABLE_INT_COLUMNS if c != "cumulative_profit"]
    return {col: _safe_corr(df[col], df["cumulative_profit"]) for col in candidates}


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
        "corr_closed_calls_to_closed": _safe_corr(p1["closed"], p1["calls_to_closed"]),
    }


# ---------------------------------------------------------------------------
# M1-M6 (PHASE5.md §ה). ROADMAP.html:753's one-line names, given the
# concrete reading PHASE5.md §ה pins down -- see that section for the
# full reasoning; not re-derived here.
# ---------------------------------------------------------------------------

def m1_zero_profit(df: pd.DataFrame) -> dict:
    """M1 -- rows where cumulative_profit == 0, reported separately from
    the 29 missing. The file represents these explicitly as 0, not NaN,
    which is why they are counted apart from the missing rows -- that is
    a fact about the file's encoding, not a claim about what 0 means:
    its business meaning is not decided here, and cannot be without a
    data dictionary (SPEC.md § גרעיניות מעורבת's "מוסק בלבד" framing;
    see m2_zero_profit_consistency for the evidence that IS reported)."""
    return {
        "n_zero_profit": int((df["cumulative_profit"] == 0).sum()),
        "n_missing_profit": int(df["cumulative_profit"].isna().sum()),
        "n_negative_profit": int((df["cumulative_profit"] < 0).sum()),
    }


def m2_zero_profit_consistency(df: pd.DataFrame) -> dict:
    """M2 -- consistency evidence for the zero-profit rows, NOT a
    legitimacy claim: no data dictionary proves whether 0 is a genuine
    zero-profit outcome or a missing-value stand-in (SPEC.md § גרעיניות
    מעורבת's "מוסק בלבד" framing). Two complementary views -- SPEC.md
    asks for both "cross-tab against purchased/closed/ltv/CAC" AND "the
    zero rate within each slice", which are opposite conditional
    directions, not the same number under two names:

    - purchased_rate / closed_gt0_rate: P(purchased=1 | profit) and
      P(closed>0 | profit), computed within the zero-profit group and
      within the known-nonzero group -- characterizes each group.
    - zero_rate_by_slice: the reverse direction, P(profit=0 | slice) for
      purchased in {0,1} and closed in {==0, >0} -- what fraction of
      EACH slice is zero-profit, with the slice's own n and n_zero
      reported so the denominator is never implicit.
    - mean_ltv_months / mean_cac: the existing zero-vs-known-nonzero
      mean comparison, unbinned. SPEC.md/PHASE5.md define no bins for
      these two continuous columns, so none are invented here -- this
      summary comparison is what's reported for them, not a fabricated
      cut.

    Rows are never dropped by this or any other function here."""
    zero = df[df["cumulative_profit"] == 0]
    known_nonzero = df[df["cumulative_profit"].notna() & (df["cumulative_profit"] != 0)]

    def _rate(frame: pd.DataFrame, mask: pd.Series) -> float | None:
        return float(mask.mean()) if len(frame) else None

    def _mean_ltv(frame: pd.DataFrame) -> float | None:
        vals = frame["ltv_months"].dropna()
        return float(vals.mean()) if len(vals) else None

    def _zero_rate_slice(mask: pd.Series) -> dict:
        sl = df[mask]
        n = int(len(sl))
        n_zero = int((sl["cumulative_profit"] == 0).sum())
        return {"n": n, "n_zero_profit": n_zero, "zero_rate": (n_zero / n) if n else None}

    return {
        "n_zero_profit": int(len(zero)),
        "n_known_nonzero_profit": int(len(known_nonzero)),
        "purchased_rate": {
            "zero_profit": _rate(zero, zero["purchased"] == 1),
            "known_nonzero_profit": _rate(known_nonzero, known_nonzero["purchased"] == 1),
        },
        "closed_gt0_rate": {
            "zero_profit": _rate(zero, zero["closed"] > 0),
            "known_nonzero_profit": _rate(known_nonzero, known_nonzero["closed"] > 0),
        },
        "zero_rate_by_slice": {
            "purchased_0": _zero_rate_slice(df["purchased"] == 0),
            "purchased_1": _zero_rate_slice(df["purchased"] == 1),
            "closed_eq_0": _zero_rate_slice(df["closed"] == 0),
            "closed_gt_0": _zero_rate_slice(df["closed"] > 0),
        },
        "mean_ltv_months": {
            "zero_profit": _mean_ltv(zero),
            "known_nonzero_profit": _mean_ltv(known_nonzero),
        },
        "mean_cac": {
            "zero_profit": float(zero["customer_acquisition_cost"].mean()) if len(zero) else None,
            "known_nonzero_profit": (
                float(known_nonzero["customer_acquisition_cost"].mean()) if len(known_nonzero) else None
            ),
        },
    }


def m3_top_decile(df: pd.DataFrame) -> dict:
    """M3 -- top decile of cumulative_profit, among the rows where it's
    known (the 29 missing are excluded from M3 only, never imputed,
    never filtered by purchased). Primary: exact-K, K=ceil(0.1*N),
    stable sort by profit DESC then source_row_id ASC -- K and its
    actual fraction of N are both reported ("K/N", never claimed to be
    exactly 10%). Sensitivity, reported alongside, not instead: every
    record with profit >= the exact-K boundary value (inclusive ties)."""
    known = df[df["cumulative_profit"].notna()]
    n_missing = int(df["cumulative_profit"].isna().sum())
    n = len(known)
    total_profit = float(known["cumulative_profit"].sum())

    ranked = known.sort_values(["cumulative_profit", "source_row_id"], ascending=[False, True])
    k = math.ceil(0.1 * n)
    exact_k = ranked.iloc[:k]
    boundary_value = float(exact_k["cumulative_profit"].iloc[-1]) if k else None

    if boundary_value is not None:
        ties = known[known["cumulative_profit"] >= boundary_value]
        n_at_boundary = int((known["cumulative_profit"] == boundary_value).sum())
    else:
        ties = known.iloc[0:0]
        n_at_boundary = 0

    def _share(frame: pd.DataFrame) -> float | None:
        return float(frame["cumulative_profit"].sum() / total_profit) if total_profit else None

    return {
        "n_known": n,
        "n_missing_profit": n_missing,
        "K": k,
        "K_fraction_of_N": (k / n) if n else None,
        "boundary_value": boundary_value,
        "n_at_boundary_value": n_at_boundary,
        "exact_k": {"n_records": int(len(exact_k)), "profit_share": _share(exact_k)},
        "inclusive_ties": {"n_records": int(len(ties)), "profit_share": _share(ties)},
    }


def m4_profit_by_tier(df: pd.DataFrame) -> dict:
    """M4 -- cumulative_profit summed AND averaged per budget tier
    (Low/Mid/High, plus gap), n per tier, missing profit values excluded
    from the sum/mean and counted explicitly per tier -- never imputed."""
    tiers = df["ad_budget"].apply(budget_tier)
    out: dict = {}
    for name in (*BUDGET_TIERS, None):
        key = name if name is not None else "gap"
        mask = tiers.isna() if name is None else (tiers == name)
        profit = df.loc[mask, "cumulative_profit"]
        known = profit.dropna()
        out[key] = {
            "n_records": int(mask.sum()),
            "n_missing_profit": int(profit.isna().sum()),
            "sum_cumulative_profit": float(known.sum()) if len(known) else None,
            "mean_cumulative_profit": float(known.mean()) if len(known) else None,
        }
    return out


# 16 non-binary numeric raw columns for M5 -- every NOT_NULL_INT_COLUMNS/
# NULLABLE_INT_COLUMNS column except the two binary ones (purchased,
# upsell). source_row_id (derived, not a raw column) is excluded by
# construction -- it's simply not in either list.
_M5_BINARY_COLUMNS = {"purchased", "upsell"}
_M5_COLUMNS = [c for c in NOT_NULL_INT_COLUMNS + NULLABLE_INT_COLUMNS if c not in _M5_BINARY_COLUMNS]


def m5_outliers(df: pd.DataFrame) -> dict:
    """M5 -- IQR and p1/p99 outlier flags, kept strictly separate, never
    unioned into one "outlier" measure and never triggering removal or
    Winsorization (descriptive only). 16 non-binary numeric raw columns.
    Quantiles computed per column on non-null values only,
    interpolation="linear". Strict inequalities on both boundaries --
    a value exactly at a boundary is not flagged."""
    iqr_cells: dict[str, int] = {}
    p1p99_cells: dict[str, int] = {}
    missing_per_column: dict[str, int] = {}
    iqr_flagged_rows: set[int] = set()
    p1p99_flagged_rows: set[int] = set()

    for col in _M5_COLUMNS:
        series = df[col]
        missing_per_column[col] = int(series.isna().sum())
        valid = series.dropna()

        q1 = valid.quantile(0.25, interpolation="linear")
        q3 = valid.quantile(0.75, interpolation="linear")
        iqr = q3 - q1
        iqr_mask = (series < q1 - 1.5 * iqr) | (series > q3 + 1.5 * iqr)
        iqr_cells[col] = int(iqr_mask.sum())
        iqr_flagged_rows.update(int(x) for x in df.loc[iqr_mask, "source_row_id"])

        p1 = valid.quantile(0.01, interpolation="linear")
        p99 = valid.quantile(0.99, interpolation="linear")
        p_mask = (series < p1) | (series > p99)
        p1p99_cells[col] = int(p_mask.sum())
        p1p99_flagged_rows.update(int(x) for x in df.loc[p_mask, "source_row_id"])

    return {
        "columns": list(_M5_COLUMNS),
        "missing_per_column": missing_per_column,
        "iqr": {
            "cells_flagged_per_column": iqr_cells,
            "n_unique_records_flagged": len(iqr_flagged_rows),
        },
        "p1_p99": {
            "cells_flagged_per_column": p1p99_cells,
            "n_unique_records_flagged": len(p1p99_flagged_rows),
        },
        "n_records_flagged_by_both_methods": len(iqr_flagged_rows & p1p99_flagged_rows),
    }


def m6_duplicate_profile(df: pd.DataFrame) -> dict:
    """M6 -- profile of the duplicate groups: source_row_id, ad_budget,
    group size, purchased/closed, and budget tier per group. Same
    contract as duplicates() (checkpoint 7) -- reuses it directly rather
    than recomputing group membership a second, competing way."""
    return duplicates(df)


def source_metadata(csv_path: Path) -> dict:
    """The one function in this module that touches the filesystem --
    deterministic I/O, not pure, but its entire output is determined by
    the file's bytes. Reuses load_data.sha256_of (no second hashing
    implementation) rather than re-verifying against EXPECTED_SHA256:
    that verification already happened in load_and_verify_csv before df
    reached any function here; this just reports what it read. Existing
    is what lets build_results()'s closure test include source_sha256
    with no exempt metadata key (PHASE5.md D6 §3)."""
    return {"source_sha256": sha256_of(Path(csv_path))}


# Every pure metric function whose output belongs in results, keyed by
# an EXPLICIT, hand-typed string -- not derived from func.__name__.
# build_results()'s closure test reads its expected key set from this
# dict, so adding a function here is what makes it show up in results.
# A function's __name__ is an implementation detail, not a data
# contract: a harmless-looking rename (with its test renamed to match)
# would silently change every key in findings.json while every test
# stayed green, since __name__ was both the production key AND the
# test's own source of truth. The registry key is what downstream
# consumers (findings.json, checkpoints 11-12's FINDINGS.md/SVG
# rendering) actually depend on, so it's pinned here independently of
# whatever the function is currently called. (PHASE5.md D6 §3, round 2
# of the checkpoint 10 correction, Codex finding on commit 386c6dd.)
RESULT_BUILDERS = {
    "missing_values": missing_values,
    "budget_tiers": budget_tiers,
    "duplicates": duplicates,
    "duplicate_sensitivity": duplicate_sensitivity,
    "correlations": correlations,
    "ad_budget_leads_curve": ad_budget_leads_curve,
    "funnel_dropoff": funnel_dropoff,
    "calls_to_closed": calls_to_closed,
    "m1_zero_profit": m1_zero_profit,
    "m2_zero_profit_consistency": m2_zero_profit_consistency,
    "m3_top_decile": m3_top_decile,
    "m4_profit_by_tier": m4_profit_by_tier,
    "m5_outliers": m5_outliers,
    "m6_duplicate_profile": m6_duplicate_profile,
}


def build_results(df: pd.DataFrame, csv_path: Path) -> dict:
    """Merge only -- results[name] = func(df) for every (name, func) in
    RESULT_BUILDERS, plus results["source_metadata"] = source_metadata(csv_path).

    Nested by the registry's fixed key, NOT a flat union of each
    function's own keys and NOT func.__name__. PHASE5.md D6 §3 went
    through two corrections to get here: (1) a flat union of every
    function's own top-level keys collides for real 14 times across
    these functions, several with genuinely different values under the
    same name (e.g. correlations()["followup_1"] is a Pearson r,
    funnel_dropoff()["followup_1"] is a per-stage dropout dict) -- fixed
    by nesting. (2) nesting by func.__name__ is still not a stable data
    contract -- a rename refactor changes findings.json's keys with
    every test still green. RESULT_BUILDERS's hand-typed keys are what
    findings.json and checkpoints 11-12's rendering actually depend on,
    independent of what the function is currently named."""
    results = {name: func(df) for name, func in RESULT_BUILDERS.items()}
    results["source_metadata"] = source_metadata(csv_path)
    return results


def write_findings_json(results: dict, out_path: Path) -> None:
    """findings.json = the serialization of results, nothing else
    (PHASE5.md D6 §4) -- no recomputation, no added field. sort_keys
    makes the bytes independent of dict insertion order, so a re-run
    from the same CSV produces an identical file (checkpoint 13's
    git diff --exit-code). allow_nan=False turns any stray NaN into a
    loud json.dump failure instead of the invalid bareword `NaN` Python
    would otherwise emit (RFC 8259) -- every function here already
    guards against that (_safe_corr), so this is a second, independent
    line of defense, not the only one. No timestamp, run time, library
    version, or local path is written; source_sha256 (inside
    results["source_metadata"]) is the only identifying value, and it's
    a content hash, not an environment fact."""
    out_path = Path(out_path)
    with out_path.open("w", encoding="utf-8", newline="\n") as f:
        json.dump(results, f, sort_keys=True, indent=2, allow_nan=False, ensure_ascii=False)
        f.write("\n")


if __name__ == "__main__":
    from scripts.load_data import DEFAULT_CSV, load_and_verify_csv

    _df = load_and_verify_csv(DEFAULT_CSV)
    _results = build_results(_df, DEFAULT_CSV)
    _out_path = Path(__file__).resolve().parent.parent / "docs" / "findings.json"
    write_findings_json(_results, _out_path)
    print(f"wrote {_out_path}")
