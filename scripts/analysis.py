"""Package 1 + package 5 + M1-M6 (ניקוי + EDA) pure computation functions --
PHASE5.md checkpoints 7, 8, 9, plus checkpoints 10-11's build_results,
findings.json, and SVG rendering.

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
10, already implemented here. write_svgs() (checkpoint 11) renders the 5
PHASE5.md D9 charts from `results` alone -- every builder in SVG_BUILDERS
takes `results`, never a DataFrame, so recomputing a value from the CSV
inside a chart is structurally impossible. Only FINDINGS.md's prose
rendering (with $placeholder substitution) is checkpoint 12+. Nothing
here performs modeling, splits data, or touches Supabase (D10).

⚠ Every value returned here is a dataset description (SPEC.md §
גרעיניות מעורבת's "מוסק בלבד" framing, and PHASE5.md D3): none of it is a
causal claim, and none of it may be used to choose features, thresholds,
or a model in phase 6 (D3's table of what may/may not cross into phase 6).
"""
from __future__ import annotations

import io
import json
import math
import re
import sys
import xml.etree.ElementTree as ET
from pathlib import Path
from string import Template
from xml.sax.saxutils import escape as _xml_escape

import matplotlib
matplotlib.use("Agg")  # headless -- no display/GUI toolkit needed, CI-safe
# Without a fixed hashsalt, matplotlib's SVG backend IDs every clip path
# with a random uuid4 fragment -- same figure, different bytes every run.
# A fixed salt makes those IDs a deterministic hash instead, which is what
# makes write_svgs() reproducible (PHASE5.md D9 / D6's determinism bar).
matplotlib.rcParams["svg.hashsalt"] = "funneliq-phase5-checkpoint11"
import matplotlib.pyplot as plt  # noqa: E402
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
    """Missing counts for the two nullable columns, plus the file's total
    row count -- reuses data_contract's own snapshot measurement rather
    than recomputing these numbers a second way. n_rows added checkpoint
    12, 2026-09-04: FINDINGS.md's population label (3,500) needs a
    results-sourced value, not a hand-typed one, and _measure_snapshot
    already computes it -- it just wasn't forwarded here yet."""
    snap = _measure_snapshot(df)
    return {
        "n_rows": snap["n_rows"],
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
    """calls_to_closed within the purchased=1 population -- SPEC.md's own
    established reading of this column (PHASE0.md's verified reference
    numbers). calls_to_closed is documented as a record-level average,
    not a per-deal call history (SPEC.md § עובדות שנמדדו) -- every
    quantity below stays explicit about which unit (record vs. deal) and
    which subpopulation it's counted over, per SPEC.md's warning against
    conflating the two.

    frequency_by_calls_to_closed is the actual distribution SPEC.md
    package 5/PHASE5.md checkpoint 8 asks for: exact observed
    calls_to_closed value -> record count, over purchased=1, with no
    invented bins -- a value that never occurs in this population simply
    has no key (checkpoint 11 correction, 2026-09-04: the two per-
    closed-subgroup means below are complementary summary evidence, not
    themselves "the distribution" -- that label belongs to this field).

    rate_calls_to_closed_ge_4 / rate_closed_eq_1_calls_ge_4 (checkpoint
    12 correction, 2026-09-04): SPEC.md's P5 conclusion needs these two
    ratios (n_calls_to_closed_ge_4/n_purchased1,
    n_closed_eq_1_calls_ge_4/n_closed_eq_1) as percentages. Computing a
    ratio is analysis, not display formatting -- it belongs here, in a
    tested pure function, not in FINDINGS.md's rendering layer, which
    may only format an already-computed value from results. None when
    the denominator is 0, never a fabricated 0.0 (same principle as
    every other None in this module)."""
    p1 = df[df["purchased"] == 1]
    n_p1 = len(p1)

    closed1 = p1[p1["closed"] == 1]
    closed2p = p1[p1["closed"] >= 2]

    freq = p1["calls_to_closed"].value_counts()
    frequency_by_calls_to_closed = {int(k): int(v) for k, v in sorted(freq.items())}

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
        "frequency_by_calls_to_closed": frequency_by_calls_to_closed,
        "rate_calls_to_closed_ge_4": (
            int((p1["calls_to_closed"] >= 4).sum()) / n_p1 if n_p1 else None
        ),
        "rate_closed_eq_1_calls_ge_4": (
            int((closed1["calls_to_closed"] >= 4).sum()) / len(closed1) if len(closed1) else None
        ),
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


# ---------------------------------------------------------------------------
# checkpoint 11 -- 5 static SVG charts, PHASE5.md D9. Every builder below
# takes `results: dict` ONLY (never a DataFrame) -- that's what makes
# recomputing a metric from the CSV structurally impossible here, not a
# promise kept by convention. English axis/tick labels (matplotlib does no
# bidi text shaping, so Hebrew glyphs drawn on a chart render in the wrong
# visual order); the Hebrew caption/explanation instead lives in each SVG's
# own accessible <title>/<desc> (see _write_svg_with_description), which
# also serves as the required accessible textual description -- one
# mechanism satisfies both requirements instead of two.
# ---------------------------------------------------------------------------

def _write_svg_with_description(fig, out_path: Path, title_en: str, description_he: str) -> None:
    """Serializes `fig` to `out_path` as SVG with an accessible <title>/
    <desc> pair injected right after the opening <svg> tag -- screen
    readers and other assistive tech read these; matplotlib's savefig
    doesn't add them on its own. metadata={"Date": None} strips the
    generation-timestamp SVG backend embeds by default, so re-rendering
    the same figure produces byte-identical output (no volatile
    metadata, PHASE5.md D9)."""
    buf = io.BytesIO()
    fig.savefig(buf, format="svg", metadata={"Date": None})
    svg_text = buf.getvalue().decode("utf-8")
    accessible = f"<title>{_xml_escape(title_en)}</title><desc>{_xml_escape(description_he)}</desc>"
    open_tag_end = svg_text.index(">", svg_text.index("<svg")) + 1
    svg_text = svg_text[:open_tag_end] + accessible + svg_text[open_tag_end:]
    Path(out_path).write_text(svg_text, encoding="utf-8", newline="\n")


def _bar_with_na(ax, categories: list, values: list, color: str) -> None:
    """Draws one vertical bar per (category, value) pair whose value is
    not None -- a None value gets no bar (never a fabricated 0-height
    one, which would be indistinguishable from a genuinely measured
    zero) and is marked "N/A" in text near the axis baseline instead, so
    the category still appears rather than silently vanishing.
    (checkpoint 11 correction, 2026-09-04: None was previously drawn as
    a real 0.)"""
    xs = list(range(len(categories)))
    ax.set_xticks(xs)
    ax.set_xticklabels(categories)
    for x, v in zip(xs, values):
        if v is None:
            ax.text(x, 0, "N/A", ha="center", va="bottom", fontsize=8, color="#666666")
        else:
            ax.bar([x], [v], color=color)


def _barh_with_na(ax, categories: list, values: list, color: str) -> None:
    """Horizontal-bar counterpart of _bar_with_na -- used by
    _svg_correlations, where a None (undefined r) must never render as
    r=0."""
    ys = list(range(len(categories)))
    ax.set_yticks(ys)
    ax.set_yticklabels(categories)
    for y, v in zip(ys, values):
        if v is None:
            ax.text(0, y, "N/A", ha="left", va="center", fontsize=8, color="#666666")
        else:
            ax.barh([y], [v], color=color)


_FUNNEL_STAGE_KEYS = ["followup_1", "followup_2", "followup_3", "followup_4", "followup_5"]


def _svg_funnel_dropoff(results: dict, out_path: Path) -> None:
    data = results["funnel_dropoff"]
    values = [data[k] for k in _FUNNEL_STAGE_KEYS]  # None preserved -- never zeroed

    fig, ax = plt.subplots(figsize=(6, 4))
    _bar_with_na(ax, _FUNNEL_STAGE_KEYS, values, color="#4C72B0")
    ax.set_ylim(bottom=0)
    ax.set_xlabel("funnel stage")
    ax.set_ylabel("dropout rate (1 - stage_sum/prev_sum)")
    ax.set_title("Funnel dropoff by stage")
    fig.tight_layout()
    _write_svg_with_description(
        fig, out_path,
        title_en="Funnel dropoff by stage (followup_1..followup_5)",
        description_he=(
            "תרשים עמודות: שיעור הנשירה בכל שלב במשפך השיווקי, מ-leads_answered "
            "ועד followup_5. כל עמודה מחושבת כ-1 פחות סכום השלב חלקי סכום השלב "
            "הקודם (Σ/Σ), לא כממוצע יחסים לשורה. שלב ללא ערך מוגדר (למשל "
            "כשסכום השלב הקודם הוא אפס) מסומן N/A במפורש ולא מצויר כעמודת "
            "אפס. כל הערכים לקוחים ישירות מ-results['funnel_dropoff'], בלי "
            "חישוב חוזר מה-CSV. סטטוס: תיאור דטהסט (dataset description) "
            "בלבד, לפי D3 -- לא נמצא בו קשר סיבתי."
        ),
    )
    plt.close(fig)


def _svg_ad_budget_leads_curve(results: dict, out_path: Path) -> None:
    data = results["ad_budget_leads_curve"]
    budgets = sorted(data.keys())  # explicit numeric-ascending order, not dict order
    medians = [data[b]["median_num_leads"] for b in budgets]

    fig, ax = plt.subplots(figsize=(6, 4))
    ax.plot(budgets, medians, marker="o", color="#DD8452")
    ax.set_ylim(bottom=0)
    ax.set_xlabel("ad_budget")
    ax.set_ylabel("median num_leads")
    ax.set_title("ad_budget vs. median num_leads")
    fig.tight_layout()
    _write_svg_with_description(
        fig, out_path,
        title_en="ad_budget vs. median num_leads curve",
        description_he=(
            "תרשים קו: החציון של num_leads עבור כל אחד מ-16 ערכי ad_budget "
            "הבדידים בקובץ, מסודר בסדר עולה לפי ad_budget. כל נקודה לקוחה "
            "ישירות מ-results['ad_budget_leads_curve'], בלי חישוב חוזר מה-CSV. "
            "תיאור דטהסט בלבד -- אין כאן מסקנה על יעילות תקציב."
        ),
    )
    plt.close(fig)


def _svg_budget_tier_conversion(results: dict, out_path: Path) -> None:
    data = results["budget_tiers"]
    tiers = list(BUDGET_TIERS)  # explicit ("Low","Mid","High") order, not dict order
    rates = [data[t]["conversion_rate"] for t in tiers]  # None preserved -- never zeroed
    gap_n = data["gap"]["n_records"]  # read from results, not recomputed

    fig, ax = plt.subplots(figsize=(6, 4))
    _bar_with_na(ax, tiers, rates, color="#55A868")
    ax.set_ylim(bottom=0)
    ax.set_xlabel("budget tier")
    ax.set_ylabel("conversion rate (mean of closed/num_leads per row)")
    ax.set_title("Conversion rate by budget tier")
    fig.tight_layout()
    _write_svg_with_description(
        fig, out_path,
        title_en="Conversion rate by budget tier (Low/Mid/High)",
        description_he=(
            "תרשים עמודות: שיעור ההמרה הממוצע (closed/num_leads לשורה) בכל "
            "אחד משלושת טייירי התקציב Low/Mid/High. הטייר 'gap' (טווח "
            f"ad_budget 1501-1999, {gap_n} רשומות בקובץ) אינו כלול בתרשים -- "
            "אין לו conversion_rate מוגדר ב-results, רק ספירת רשומות. טייר "
            "עם conversion_rate=None (למשל אפס רשומות באוכלוסייה) מסומן N/A "
            "במפורש ולא מצויר כעמודת אפס. כל הערכים לקוחים ישירות מ-"
            "results['budget_tiers'], בלי חישוב חוזר מה-CSV."
        ),
    )
    plt.close(fig)


def _svg_calls_to_closed_distribution(results: dict, out_path: Path) -> None:
    """The actual distribution (checkpoint 11 correction, 2026-09-04): one
    bar per exact observed calls_to_closed value, height = record count,
    within purchased=1. No invented bins -- a value with no bar simply
    never occurs in this population. Round 1 of this chart plotted the
    mean calls_to_closed for the closed=1 vs. closed>=2 subgroups, which
    is a real, useful comparison but is not a distribution of
    calls_to_closed itself; that comparison is still available in
    results['calls_to_closed']'s mean_calls_to_closed_closed_eq_1/
    _closed_ge_2 fields, just not charted here or called a distribution."""
    data = results["calls_to_closed"]
    freq = data["frequency_by_calls_to_closed"]
    calls_values = sorted(freq.keys())  # explicit numeric-ascending order, not dict order
    counts = [freq[v] for v in calls_values]

    fig, ax = plt.subplots(figsize=(6, 4))
    ax.bar(calls_values, counts, color="#C44E52")
    ax.set_ylim(bottom=0)
    ax.set_xlabel("calls_to_closed (exact observed value)")
    ax.set_ylabel("record count")
    ax.set_title("calls_to_closed distribution (purchased=1 population)")
    fig.tight_layout()
    _write_svg_with_description(
        fig, out_path,
        title_en="calls_to_closed distribution (purchased=1 population)",
        description_he=(
            "תרשים עמודות: התפלגות calls_to_closed בפועל בתוך אוכלוסיית "
            "purchased=1 -- לכל ערך calls_to_closed שנצפה בקובץ (ציר x), "
            "ספירת הרשומות עם אותו ערך בדיוק (ציר y), בלי חלוקה ל-bins "
            f"מומצאים. סך התדירויות שווה n_purchased1={data['n_purchased1']}. "
            "calls_to_closed מתועד ב-SPEC.md כממוצע ברמת רשומה, לא כהיסטוריית "
            "שיחות לעסקה בודדת. כל הערכים לקוחים ישירות מ-"
            "results['calls_to_closed']['frequency_by_calls_to_closed'], בלי "
            "חישוב חוזר מה-CSV."
        ),
    )
    plt.close(fig)


def _svg_correlations(results: dict, out_path: Path) -> None:
    data = results["correlations"]
    cols = sorted(data.keys())  # explicit alphabetical order, not dict order
    values = [data[c] for c in cols]  # None preserved -- an undefined r is never drawn as r=0

    fig, ax = plt.subplots(figsize=(8, 6))
    _barh_with_na(ax, cols, values, color="#8172B2")
    # Correlation is bidirectional (r in [-1, 1]) -- a bar chart of it can't
    # honestly "start at zero" the way a count/rate chart can without
    # hiding negative bars. Fixed to the full valid r range instead of the
    # data's own min/max, so zero is always the visible baseline and the
    # axis never truncates toward whichever values this run happens to have.
    ax.set_xlim(-1, 1)
    ax.axvline(0, color="black", linewidth=0.8)
    ax.set_xlabel("Pearson r vs. cumulative_profit")
    ax.set_ylabel("column")
    ax.set_title("Correlations with cumulative_profit")
    fig.tight_layout()
    _write_svg_with_description(
        fig, out_path,
        title_en="Correlations with cumulative_profit",
        description_he=(
            "תרשים עמודות אופקי: מקדם המתאם של פירסון (r) בין כל אחת מ-17 "
            "העמודות המספריות הגולמיות (למעט cumulative_profit עצמו) לבין "
            "cumulative_profit, ממוין בסדר אלפביתי לפי שם עמודה. עמודה עם "
            "שונות אפס או פחות משני זוגות תקפים (None ב-results, לא NaN) "
            "מסומנת N/A במפורש ואינה מצוירת -- אינה שקולה ל-r=0, שהוא ערך "
            "אמיתי (העדר קשר קווי נמדד). כל הערכים לקוחים ישירות מ-"
            "results['correlations'], בלי חישוב חוזר מה-CSV. תיאור דטהסט "
            "בלבד -- לא בסיס לבחירת פיצ'רים (D3)."
        ),
    )
    plt.close(fig)


# Explicit filename -> builder registry, keyed by string (same reasoning as
# RESULT_BUILDERS, checkpoint 10: a filename derived from a function's
# __name__ is not a stable contract either).
SVG_BUILDERS = {
    "funnel_dropoff.svg": _svg_funnel_dropoff,
    "ad_budget_leads_curve.svg": _svg_ad_budget_leads_curve,
    "budget_tier_conversion.svg": _svg_budget_tier_conversion,
    "calls_to_closed_distribution.svg": _svg_calls_to_closed_distribution,
    "correlations_cumulative_profit.svg": _svg_correlations,
}


def write_svgs(results: dict, out_dir: Path) -> dict[str, Path]:
    """Renders all 5 PHASE5.md D9 charts from `results` into `out_dir`.
    Returns {filename: path}. Every builder in SVG_BUILDERS takes only
    `results` (never a DataFrame), so there is no code path here that
    could recompute a value from the CSV."""
    out_dir = Path(out_dir)
    written: dict[str, Path] = {}
    for filename, builder in SVG_BUILDERS.items():
        out_path = out_dir / filename
        builder(results, out_path)
        written[filename] = out_path
    return written


# ---------------------------------------------------------------------------
# checkpoint 12 -- FINDINGS.md rendering, PHASE5.md D6 §4. Every analytical
# number in _FINDINGS_TEMPLATE is a $placeholder resolved from `results` by
# _findings_context() -- the context builder does formatting/projection
# only (rounding, thousands separators, percentage display of two counts
# that already both exist together in the same results sub-dict, None ->
# "לא זמין") and introduces no new statistic. Placeholder names never
# contain a digit, so scan_template_for_digit_sequences() can treat every
# digit run found in the raw template as literal prose with no risk of
# confusing a placeholder name for one.
# ---------------------------------------------------------------------------

def _comma(value: int) -> str:
    """Thousands-separator display of an already-computed count."""
    return f"{value:,}"


def _pct_from_fraction(fraction: float | None, decimals: int) -> str:
    """Percentage display of an already-computed fraction (e.g. a
    conversion_rate or funnel_dropoff stage, both already 0-1 floats in
    results) -- multiply-by-100-and-round formatting, not a new
    computation. None (undefined, e.g. an empty tier) is never rendered
    as 0%, same principle as the SVG N/A handling (checkpoint 11)."""
    return "לא זמין" if fraction is None else f"{fraction * 100:.{decimals}f}"


def _num_or_na(value: float | None, decimals: int) -> str:
    """Thousands-separator display of a float, or "לא זמין" for None --
    never a fabricated 0 (same principle as _pct_from_fraction)."""
    return "לא זמין" if value is None else f"{value:,.{decimals}f}"


def _read_svg_description(svg_path: Path) -> str:
    """Reads the accessible Hebrew <desc> back out of an already-rendered
    SVG file (written by write_svgs) -- reused as FINDINGS.md's own
    caption for that chart rather than a second hand-typed copy that
    could drift from what the SVG itself says."""
    ns = "{http://www.w3.org/2000/svg}"
    root = ET.fromstring(Path(svg_path).read_text(encoding="utf-8"))
    desc = root.find(f"{ns}desc")
    return desc.text if desc is not None and desc.text else ""


def _findings_context(results: dict, svg_dir: Path) -> dict[str, str]:
    """Builds the flat {name: str} namespace string.Template substitutes
    into _FINDINGS_TEMPLATE. Every value is read from `results` (via the
    formatting helpers above) or read back from an already-rendered SVG's
    own accessible description -- no DataFrame, no recomputation."""
    mv, bt, dup = results["missing_values"], results["budget_tiers"], results["duplicates"]
    corr, fd, ctc = results["correlations"], results["funnel_dropoff"], results["calls_to_closed"]
    m1, m2 = results["m1_zero_profit"], results["m2_zero_profit_consistency"]
    m3, m4, m5 = results["m3_top_decile"], results["m4_profit_by_tier"], results["m5_outliers"]
    sm = results["source_metadata"]
    zrs = m2["zero_rate_by_slice"]

    return {
        "pop_full": _comma(mv["n_rows"]),
        "pop_known_profit": _comma(m3["n_known"]),
        "pop_purchased": _comma(ctc["n_purchased1"]),
        "source_sha": sm["source_sha256"],

        "missing_ltv": str(mv["missing_ltv_months"]),
        "missing_profit": str(mv["missing_cumulative_profit"]),
        "missing_any": str(mv["missing_any"]),

        "tier_low_n": _comma(bt["Low"]["n_records"]),
        "tier_low_rate_pct": _pct_from_fraction(bt["Low"]["conversion_rate"], 1),
        "tier_mid_n": _comma(bt["Mid"]["n_records"]),
        "tier_mid_rate_pct": _pct_from_fraction(bt["Mid"]["conversion_rate"], 1),
        "tier_high_n": _comma(bt["High"]["n_records"]),
        "tier_high_rate_pct": _pct_from_fraction(bt["High"]["conversion_rate"], 1),
        "tier_gap_n": _comma(bt["gap"]["n_records"]),

        "dup_rows": str(dup["n_duplicate_rows"]),
        "dup_groups": str(dup["n_groups"]),
        "budget_distinct_n": str(len(results["ad_budget_leads_curve"])),

        "corr_ltv": f"{corr['ltv_months']:.2f}",
        "corr_upsell": f"{corr['upsell']:.2f}",
        "corr_columns_n": str(len(corr)),

        "dropoff_first_pct": _pct_from_fraction(fd["followup_1"], 1),
        "dropoff_second_pct": _pct_from_fraction(fd["followup_2"], 1),
        "dropoff_third_pct": _pct_from_fraction(fd["followup_3"], 1),
        "dropoff_fourth_pct": _pct_from_fraction(fd["followup_4"], 1),
        "dropoff_fifth_pct": _pct_from_fraction(fd["followup_5"], 1),

        "p1_n": _comma(ctc["n_purchased1"]),
        "ge4_n": _comma(ctc["n_calls_to_closed_ge_4"]),
        "ge4_pct": _pct_from_fraction(ctc["rate_calls_to_closed_ge_4"], 0),
        "closed_eq1_n": _comma(ctc["n_closed_eq_1"]),
        "closed_eq1_ge4_n": _comma(ctc["n_closed_eq_1_calls_ge_4"]),
        "closed_eq1_ge4_pct": _pct_from_fraction(ctc["rate_closed_eq_1_calls_ge_4"], 2),

        "zero_profit_n": _comma(m1["n_zero_profit"]),
        "missing_profit_n": _comma(m1["n_missing_profit"]),
        "negative_profit_n": str(m1["n_negative_profit"]),

        "zero_rate_purchased_zero_pct": _pct_from_fraction(zrs["purchased_0"]["zero_rate"], 1),
        "zero_rate_purchased_one_pct": _pct_from_fraction(zrs["purchased_1"]["zero_rate"], 1),
        "zero_rate_closed_zero_pct": _pct_from_fraction(zrs["closed_eq_0"]["zero_rate"], 1),
        "zero_rate_closed_pos_pct": _pct_from_fraction(zrs["closed_gt_0"]["zero_rate"], 1),
        "mean_ltv_zero_group": _num_or_na(m2["mean_ltv_months"]["zero_profit"], 1),
        "mean_ltv_known_group": _num_or_na(m2["mean_ltv_months"]["known_nonzero_profit"], 1),
        "mean_cac_zero_group": _num_or_na(m2["mean_cac"]["zero_profit"], 0),
        "mean_cac_known_group": _num_or_na(m2["mean_cac"]["known_nonzero_profit"], 0),

        "decile_k": str(m3["K"]),
        "decile_k_pct": _pct_from_fraction(m3["K_fraction_of_N"], 1),
        "decile_boundary": _comma(int(m3["boundary_value"])),
        "decile_n_at_boundary": str(m3["n_at_boundary_value"]),
        "decile_ties_n": str(m3["inclusive_ties"]["n_records"]),
        "decile_share_exact_pct": _pct_from_fraction(m3["exact_k"]["profit_share"], 1),
        "decile_share_ties_pct": _pct_from_fraction(m3["inclusive_ties"]["profit_share"], 1),

        "profit_low_n": _comma(m4["Low"]["n_records"]),
        "profit_low_missing": str(m4["Low"]["n_missing_profit"]),
        "profit_low_sum": _num_or_na(m4["Low"]["sum_cumulative_profit"], 0),
        "profit_low_mean": _num_or_na(m4["Low"]["mean_cumulative_profit"], 0),
        "profit_mid_n": _comma(m4["Mid"]["n_records"]),
        "profit_mid_missing": str(m4["Mid"]["n_missing_profit"]),
        "profit_mid_sum": _num_or_na(m4["Mid"]["sum_cumulative_profit"], 0),
        "profit_mid_mean": _num_or_na(m4["Mid"]["mean_cumulative_profit"], 0),
        "profit_high_n": _comma(m4["High"]["n_records"]),
        "profit_high_missing": str(m4["High"]["n_missing_profit"]),
        "profit_high_sum": _num_or_na(m4["High"]["sum_cumulative_profit"], 0),
        "profit_high_mean": _num_or_na(m4["High"]["mean_cumulative_profit"], 0),
        "profit_gap_n": str(m4["gap"]["n_records"]),
        "profit_gap_missing": str(m4["gap"]["n_missing_profit"]),

        "outlier_iqr_n": str(m5["iqr"]["n_unique_records_flagged"]),
        "outlier_pctile_n": str(m5["p1_p99"]["n_unique_records_flagged"]),
        "outlier_both_n": str(m5["n_records_flagged_by_both_methods"]),

        "desc_funnel": _read_svg_description(svg_dir / "funnel_dropoff.svg"),
        "desc_ad_budget": _read_svg_description(svg_dir / "ad_budget_leads_curve.svg"),
        "desc_tier": _read_svg_description(svg_dir / "budget_tier_conversion.svg"),
        "desc_calls": _read_svg_description(svg_dir / "calls_to_closed_distribution.svg"),
        "desc_corr": _read_svg_description(svg_dir / "correlations_cumulative_profit.svg"),
    }


# The P5 conclusion -- word-for-word from SPEC.md § מסקנת P5, with only
# the analytical numbers replaced by $placeholders. Every OTHER digit left
# literal below (the "1" in purchased=1/closed=1, the "4"/"2" in the >=4/
# >=2 thresholds) is a fixed metric-defining threshold, not a measured
# finding -- SPEC.md itself writes these as literal condition values, not
# results. tests/test_metrics.py verifies this resolves to an EXACT match
# against SPEC.md's own live text (read from the file, not retyped), so a
# transcription slip here fails a test rather than silently drifting.
_P5_CONCLUSION_TEMPLATE = """\
> הנתונים **אינם תומכים** בעצירה אוטומטית אחרי המעקב השלישי. שיעור הנשירה בשלב
> הרביעי הוא הנמוך בשרשרת ($dropoff_fourth_pct%). בנוסף, ב-$ge4_n מתוך $p1_n רשומות שבהן
> `purchased = 1` ($ge4_pct%) הערך **הממוצע** של `calls_to_closed` הוא 4 ומעלה,
> ובתת-האוכלוסייה `closed = 1` — $closed_eq1_ge4_n מתוך $closed_eq1_n רשומות ($closed_eq1_ge4_pct%) מציגות
> `calls_to_closed >= 4`.
> **מה שהנתונים אינם מוכיחים:** `calls_to_closed` הוא ממוצע ברמת רשומה ולא
> היסטוריה פר-עסקה, ולכן **אין לטעון ש-$ge4_pct% מהעסקאות הבודדות דרשו 4+ שיחות**
> ואין לטעון שעצירה אחרי השלישית הייתה מוותרת על כל $ge4_n הרשומות.
> תת-האוכלוסייה `closed = 1` נבדלת תיאורית בגודל, בתקציב, בהמרה ובמספר השיחות,
> ולכן אינה מייצגת בהכרח את כלל הרשומות או העסקאות. **לא ניתן להסיק ממנה את
> שיעור העסקאות הכולל ולא את כיוון ההטיה** — יחידת ההשוואה היא רשומה, ורשומת
> `closed ≥ 2` נספרת כאחת אף שהיא מכילה כמה עסקאות.
> הנתונים אגרגטיביים ואינם מאפשרים לאמוד סיבתיות או כדאיות כלכלית שולית.
> **ההמלצה:** להמשיך את המעקבים באופן מבוקר, ולמדוד בניסוי תפעולי את שיעור
> הסגירה השולי, זמן העבודה ועלות כל שלב.
"""

# Every analytical value below is a $placeholder resolved from `results`
# via _findings_context() -- see that function's docstring for the "no new
# computation" rule. Every finding carries a population label (3,500 /
# 3,471 / 3,163) and a "dataset description" tag per PHASE5.md/SPEC.md §
# מטריצת זמינות פיצ'רים -- none of this is a causal claim or a phase-6
# feature-selection input (D3).
_FINDINGS_TEMPLATE = Template("""\
# FINDINGS.md — ניקוי + EDA (פאזה 5)

מסמך זה מרונדר אוטומטית מתוך `results` (ר' `docs/findings.json`) ע"י
`scripts/analysis.py`'s `render_findings_md` -- כל ערך אנליטי כאן הוא
`$$placeholder` שנפתר מפלט פונקציית חישוב טהורה ובדוקה (PHASE5.md D6).
מקור הנתונים: `funnel_marketing_data.csv`, `source_sha256=$source_sha`.

⚠ **כל הממצאים במסמך זה הם `dataset description` בלבד** (SPEC.md §
גרעיניות מעורבת's "מוסק בלבד" framing, PHASE5.md D3): שום ממצא כאן אינו
טענה סיבתית, ואף אחד מהם אינו משמש לבחירת פיצ'רים, ספים או מודל בפאזה 6.

## סקירת הקובץ (אוכלוסייה: $pop_full, dataset description)

- שורות בקובץ: **$pop_full**.
- חסרים: `ltv_months` -- $missing_ltv, `cumulative_profit` -- $missing_profit,
  לפחות אחד מהשניים -- $missing_any.
- כפילויות: $dup_rows שורות ב-$dup_groups קבוצות (זהות בכל 19 העמודות הגולמיות).

## חבילה 1 — טייר תקציב, כפילויות, קורלציות (אוכלוסייה: $pop_full, dataset description)

שיעור ההמרה הממוצע לפי טייר תקציב (ממוצע `closed/num_leads` לשורה):

| טייר | n | שיעור המרה |
|---|---|---|
| Low | $tier_low_n | $tier_low_rate_pct% |
| Mid | $tier_mid_n | $tier_mid_rate_pct% |
| High | $tier_high_n | $tier_high_rate_pct% |
| gap (1501-1999) | $tier_gap_n | לא מוגדר -- אין ערך `conversion_rate` |

![Conversion rate by budget tier](budget_tier_conversion.svg)

$desc_tier

עקומת `ad_budget` → חציון `num_leads`, על $budget_distinct_n ערכי `ad_budget`
בדידים:

![ad_budget vs. median num_leads](ad_budget_leads_curve.svg)

$desc_ad_budget

קורלציית פירסון (r) מול `cumulative_profit`, לכל $corr_columns_n העמודות
המספריות הגולמיות האחרות (למשל `ltv_months`: $corr_ltv, `upsell`: $corr_upsell):

![Correlations with cumulative_profit](correlations_cumulative_profit.svg)

$desc_corr

## חבילה 5 — נשירה במשפך, calls_to_closed (אוכלוסייה: $pop_full / $pop_purchased, dataset description)

נשירה בכל שלב במשפך (Σ/Σ, לא ממוצע יחסים לשורה), על $pop_full הרשומות:

![Funnel dropoff by stage](funnel_dropoff.svg)

$desc_funnel

שלב 1: $dropoff_first_pct% · שלב 2: $dropoff_second_pct% · שלב 3: $dropoff_third_pct% ·
שלב 4: $dropoff_fourth_pct% · שלב 5: $dropoff_fifth_pct%.

התפלגות `calls_to_closed` בתוך אוכלוסיית `purchased=1` ($pop_purchased רשומות):

![calls_to_closed distribution](calls_to_closed_distribution.svg)

$desc_calls

מתוך $p1_n רשומות `purchased=1`, ב-$ge4_n מהן ($ge4_pct%) `calls_to_closed`
הממוצע הוא 4 ומעלה. בתת-האוכלוסייה `closed=1` ($closed_eq1_n רשומות),
$closed_eq1_ge4_n מהן ($closed_eq1_ge4_pct%) מציגות `calls_to_closed >= 4`.

## M1 — ספירת אפסים ב-cumulative_profit (אוכלוסייה: $pop_full, dataset description)

$zero_profit_n שורות עם `cumulative_profit == 0`, בנפרד מ-$missing_profit_n
השורות החסרות ומ-$negative_profit_n שורות שליליות. הקובץ מייצג אפס במפורש
כ-0, ולכן הוא נספר בנפרד מ-`NaN` -- משמעותו העסקית אינה מוכרעת ללא מילון
נתונים.

## M2 — עקביות האפסים, לא לגיטימיות (אוכלוסייה: $pop_full, dataset description)

⚠ אין כאן טענת לגיטימיות: אין מילון נתונים שמוכיח אם `0` הוא רווח אפס אמיתי
או קידוד למשהו חסר (SPEC.md § גרעיניות מעורבת). ראיות עקביות בלבד:

שיעור האפסים בכל חתך (P(profit=0|slice), המכנה גלוי):

| חתך | שיעור אפסים |
|---|---|
| purchased=0 | $zero_rate_purchased_zero_pct% |
| purchased=1 | $zero_rate_purchased_one_pct% |
| closed=0 | $zero_rate_closed_zero_pct% |
| closed>0 | $zero_rate_closed_pos_pct% |

ממוצע `ltv_months`: קבוצת אפס $mean_ltv_zero_group, קבוצת ידוע-לא-אפס
$mean_ltv_known_group. ממוצע CAC: קבוצת אפס $mean_cac_zero_group, קבוצת
ידוע-לא-אפס $mean_cac_known_group.

## M3 — עשירון עליון (אוכלוסייה: $pop_known_profit, dataset description)

אוכלוסייה: $pop_known_profit הרשומות שבהן `cumulative_profit` ידוע
($missing_profit המוחרגות מדווחות לצידו, לא מוטמעות ולא מסוננות). `K=$decile_k`
($decile_k_pct%), ערך גבול $decile_boundary, עם $decile_n_at_boundary
רשומות עליו בדיוק. חלק העשירון מסך הרווח: $decile_share_exact_pct%
(exact-K, $decile_k רשומות) לעומת $decile_share_ties_pct% (inclusive-ties,
$decile_ties_n רשומות).

## M4 — רווח לפי טייר (אוכלוסייה: $pop_full, dataset description)

| טייר | n | חסרים | סכום | ממוצע |
|---|---|---|---|---|
| Low | $profit_low_n | $profit_low_missing | $profit_low_sum | $profit_low_mean |
| Mid | $profit_mid_n | $profit_mid_missing | $profit_mid_sum | $profit_mid_mean |
| High | $profit_high_n | $profit_high_missing | $profit_high_sum | $profit_high_mean |
| gap | $profit_gap_n | $profit_gap_missing | לא זמין | לא זמין |

## M5 — ספירת outliers (אוכלוסייה: $pop_full, dataset description)

שתי שיטות בנפרד, לעולם לא מאוחדות: `1.5×IQR` -- $outlier_iqr_n רשומות
ייחודיות מסומנות; `p1/p99` -- $outlier_pctile_n רשומות ייחודיות מסומנות.
חפיפה בין שתי השיטות: $outlier_both_n רשומות. סימון תיאורי בלבד -- אינו
גורר מחיקה או Winsorization; הספים אינם עוברים לפאזה 6.

## M6 — פרופיל הכפילויות (אוכלוסייה: $pop_full, dataset description)

זהה במדויק לנתוני חבילה 1 לעיל ($dup_rows שורות ב-$dup_groups קבוצות)
-- `m6_duplicate_profile()` הוא alias ל-`duplicates()`, לא הגדרה מתחרה.

## מסקנת P5 — תיאורית, לא סיבתית (אוכלוסייה: $pop_full / $pop_purchased, dataset description)

הניסוח הבא זהה מילולית לניסוח הנעול ב-SPEC.md § מסקנת P5:

$p5_conclusion

## מקור הנתונים

`funnel_marketing_data.csv`, `source_sha256=$source_sha`. אין נגיעה
ב-Supabase (D10). ראה `docs/findings.json` לפלט המלא, ו-checkpoints
7-11 ב-`ROADMAP.html` לראיות המימוש והבדיקות.
""")


def scan_template_for_digit_sequences() -> dict[str, int]:
    """Information output, never an assertion (PHASE5.md D6 §5, corrected
    from an earlier assert+allowlist design that was brittle and proved
    nothing about provenance -- see PHASE5.md §י round 2). Scans the RAW
    template text (both _FINDINGS_TEMPLATE and the embedded
    _P5_CONCLUSION_TEMPLATE), before substitution, for every digit run.
    Placeholder names never contain a digit (by construction), so every
    digit found here is literal prose -- checkpoint 12 requires pasting
    this list into PHASE5.md §ח with a justification for each one, not
    filtering any of them out here."""
    raw = _FINDINGS_TEMPLATE.template + _P5_CONCLUSION_TEMPLATE
    counts: dict[str, int] = {}
    for match in re.findall(r"\d+", raw):
        counts[match] = counts.get(match, 0) + 1
    return dict(sorted(counts.items(), key=lambda kv: int(kv[0])))


def render_findings_md(results: dict, svg_dir: Path) -> str:
    """Renders FINDINGS.md's full text from `results` and the already-
    rendered SVGs in `svg_dir` -- string.Template substitution only, no
    analytical computation happens in this function itself (that's
    _findings_context()'s job, and ultimately checkpoints 7-10's pure
    functions')."""
    ctx = _findings_context(results, svg_dir)
    p5_conclusion = Template(_P5_CONCLUSION_TEMPLATE).substitute(ctx)
    return _FINDINGS_TEMPLATE.substitute({**ctx, "p5_conclusion": p5_conclusion})


def write_findings_md(results: dict, svg_dir: Path, out_path: Path) -> None:
    """Writes render_findings_md()'s output to `out_path`. No timestamp,
    run time, or library version is written -- source_sha (inside the
    rendered text) is the only identifying value, and it's a content
    hash, not an environment fact (same convention as write_findings_json)."""
    text = render_findings_md(results, svg_dir)
    Path(out_path).write_text(text, encoding="utf-8", newline="\n")


if __name__ == "__main__":
    from scripts.load_data import DEFAULT_CSV, load_and_verify_csv

    _df = load_and_verify_csv(DEFAULT_CSV)
    _results = build_results(_df, DEFAULT_CSV)
    _docs_dir = Path(__file__).resolve().parent.parent / "docs"

    _out_path = _docs_dir / "findings.json"
    write_findings_json(_results, _out_path)
    print(f"wrote {_out_path}")

    for _name, _path in write_svgs(_results, _docs_dir).items():
        print(f"wrote {_path} ({_path.stat().st_size} bytes)")

    _findings_md_path = _docs_dir / "FINDINGS.md"
    write_findings_md(_results, _docs_dir, _findings_md_path)
    print(f"wrote {_findings_md_path}")

    print("digit sequences remaining in the raw FINDINGS.md template (info only, PHASE5.md §ח):")
    for _digits, _count in scan_template_for_digit_sequences().items():
        print(f"  {_digits}  (x{_count})")
