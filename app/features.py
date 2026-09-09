"""Single mechanical source of truth for per-task feature lists and the
budget-tier mapping (CLAUDE.md § app/features.py; PHASE5.md D2).

docs/feature_matrix.md is the methodological companion -- business
meaning, granularity, availability timing, and the reasoning behind every
Feature/Target/Derived/Excluded status below, for all 19 raw source
columns across P2/P3/P4/P6. tests/test_features.py checks the two never
drift apart. Grounded directly in SPEC.md § החרגות דליפה, § אוכלוסיות
אימון, and § נקודות חיזוי -- nothing here is inferred from a measured
target relationship (SPEC.md's D3 rule for this phase).

Four statuses, not three (SPEC.md § מטריצת זמינות פיצ'רים names all four:
Feature / Target / נגזרת / מוחרגת). The decisive availability test for
P6's snapshot is exactly "`ad_budget` בלבד" (§ נקודות חיזוי) -- ad_budget
alone is known directly at prediction time; nothing else is, regardless
of whether a candidate column happens to be campaign-level or
customer-level ("שאר המשפך" is illustrative wording there, not a
narrower rule -- every other P6 candidate, `purchased` included, is
substituted from a median profile per exact ad_budget level at serving
time (חבילה 6), not read from the column itself. That is exactly what
"Derived" (נגזרת) names, and it applies to P6 only -- P2/P3/P4's
snapshot (end of campaign cycle) has every candidate column available
directly, no substitution needed.

Not connected to app/main.py and does not perform any modeling in phase 5
-- imported by tests only. Phase 6 wires it into the actual training/
serving Pipelines.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from scripts.load_data import EXPECTED_COLUMNS  # noqa: E402

# ---------------------------------------------------------------------------
# Per-task target and leakage exclusions (SPEC.md § החרגות דליפה).
#
# P2/P3/P4 also exclude `purchased`, but for a DIFFERENT reason than the
# other three columns in each set: SPEC.md § אוכלוסיות אימון states it is
# dropped because it is constant (nunique=1) in the purchased=1 population
# those three tasks train on -- not because it leaks a downstream outcome.
# The net effect on the feature list is identical either way, so it is kept
# in the same EXCLUDED set; docs/feature_matrix.md keeps the two reasons
# distinct in prose. P6 trains on the full population (no purchased=1
# filter), where `purchased` varies and is NOT excluded.
# ---------------------------------------------------------------------------

# The four original tasks -- FEATURES/MODEL_INPUT_FEATURES below are
# derived generically for exactly these, via _feature_list()'s "every
# column not excluded" rule. P4S (added in phase 8A) does NOT fit that
# rule -- it uses a curated 4-column subset, not "everything left over"
# -- so it is deliberately excluded from this tuple and assigned its
# FEATURES/MODEL_INPUT_FEATURES entries by hand, below.
_ORIGINAL_TASKS = ("P2", "P3", "P4", "P6")

TARGET = {
    "P2": "ltv_months",
    "P3": "upsell",
    "P4": "referred",
    "P6": "cumulative_profit",
    # P4S (phase 8A, docs/planning/PHASE8A.md D1): a LOGICAL identifier,
    # NOT a raw CSV column -- there is no `super_customer` column. Every
    # access to this task's target values must go through
    # target_values() below; df["super_customer"] does not exist and
    # raises KeyError.
    "P4S": "super_customer",
}

EXCLUDED = {
    "P2": {"cumulative_profit", "upsell", "referred", "purchased"},
    "P3": {"cumulative_profit", "referred", "ltv_months", "purchased"},
    "P4": {"cumulative_profit", "upsell", "ltv_months", "purchased"},
    "P6": {"ltv_months", "upsell", "referred"},
    # P4S (PHASE8A.md D1/D3): the three label components (referred,
    # upsell, ltv_months) -- excluded so a leakage check on this task
    # correctly flags them -- plus cumulative_profit (leakage) and
    # purchased (constant in this purchased=1 population, same
    # reasoning as P2/P3/P4). Used by column_status(); FEATURES["P4S"]
    # is NOT derived from this via _feature_list() -- see below.
    "P4S": {"referred", "upsell", "ltv_months", "cumulative_profit", "purchased"},
}


def super_customer_label(df: pd.DataFrame) -> pd.Series:
    """P4S's synthetic target (PHASE8A.md D2): a super-customer is a
    purchased customer who was referred, upsold, and stayed >= 34
    months (SPEC's locked threshold). Pure -- does not mutate `df`.
    This is the SINGLE mechanical source of truth for the formula:
    scripts/analysis.py's super_customer_profile() consumes this exact
    function rather than recomputing the three conditions a second
    time. Makes no population assumption itself (callers restrict to
    purchased=1 first if that's what they want) -- defined for any row
    that has the three columns."""
    return (df["referred"] == "Yes") & (df["upsell"] == 1) & (df["ltv_months"] >= 34)


def target_values(df: pd.DataFrame, task: str) -> pd.Series:
    """The task's target values as a Series aligned to df: df[TARGET[task]]
    for the four original tasks (a real CSV column), and
    super_customer_label(df).astype(int) for P4S (TARGET["P4S"] is a
    logical id, not a column -- D1). Every generic, task-parameterized
    access to target values (in this module and in scripts/train.py)
    must go through this function; nothing may read
    df[TARGET["P4S"]] directly, since that column does not exist.
    Task-specific functions that already hardcode a real task's own
    literal target column (e.g. scripts/train.py's train_p2/p3/p4/p6)
    are unaffected -- they never call this."""
    if task == "P4S":
        return super_customer_label(df).astype(int)
    return df[TARGET[task]]

# The three-way collinear group SPEC.md flags for in-Pipeline reduction
# ("שתיים בלבד... בתוך ה-Pipeline") -- leads_not_answered = num_leads -
# leads_answered exactly (perfect collinearity), so at most two of the
# three ever enter a model. Listed here as candidates in every task's
# feature list below; WHICH two (or num_leads + answer_rate instead) is a
# phase-6 Pipeline-build decision, not made or implemented here.
COLLINEAR_TRIO = ("num_leads", "leads_answered", "leads_not_answered")

# Moved here from scripts/train.py (PHASE6.md checkpoint 4, D4) in phase 8
# (docs/planning/PHASE8.md § ו.1) -- app/schemas.py needs a real model-input
# feature list without pulling in scripts.train's xgboost/lightgbm/catboost
# imports. Pure transfer: same value, same logic, zero behavior change.
# leads_not_answered = num_leads - leads_answered exactly (perfect
# collinearity), so at most two of the three COLLINEAR_TRIO columns ever
# enter a model; num_leads + leads_answered are kept.
DROPPED_COLLINEAR = "leads_not_answered"


def model_feature_columns(task: str) -> list[str]:
    """FEATURES[task] minus the dropped collinear column -- the raw
    columns every model for this task actually sees. scripts/train.py
    imports this (and re-exports it as tr.model_feature_columns) instead
    of defining it a second time."""
    return [c for c in FEATURES[task] if c != DROPPED_COLLINEAR]


def _feature_list(task: str) -> list[str]:
    """Every raw column that is neither the task's target nor excluded --
    Feature-status and Derived-status columns together, since both are
    real model inputs (Derived just means the value is substituted from a
    profile at serving time, not that it's absent from the model). In
    EXPECTED_COLUMNS order, the single existing source of truth for the
    raw 19-column contract (scripts.load_data), not redefined here."""
    drop = EXCLUDED[task] | {TARGET[task]}
    return [c for c in EXPECTED_COLUMNS if c not in drop]


FEATURES = {task: _feature_list(task) for task in _ORIGINAL_TASKS}

# Phase 8 (docs/planning/PHASE8.md § ו.1) -- the exact model-input columns
# for each task's request/response contract, in order, with the collinear
# column already dropped. app/schemas.py's FunnelInput is checked against
# MODEL_INPUT_FEATURES["P2"]/["P3"]/["P4"] (13 identical names, same
# order); ["P6"] has 14 (purchased included) and is NOT a user-request
# schema -- P6's simulator takes no request body at all (D10).
MODEL_INPUT_FEATURES = {task: model_feature_columns(task) for task in _ORIGINAL_TASKS}

# D17's "early funnel data" experiment (P4, research_only) AND P4S's
# actual served feature set (phase 8A). Moved here from
# scripts/train.py:1919 (PHASE8A.md D6) -- pure transfer, same value,
# zero behavior change; scripts/train.py re-exports this same name so
# train_p4_early_funnel keeps working unmodified.
EARLY_FUNNEL_FEATURES = ["ad_budget", "num_leads", "leads_answered", "followup_1"]

# P4S (phase 8A): a curated 4-feature subset, not "everything not
# excluded" like P2/P3/P4/P6 -- _feature_list()'s generic derivation
# does not apply here, by design (PHASE8A.md D3). None of these four
# is DROPPED_COLLINEAR ("leads_not_answered"), so model_feature_columns
# returns them unchanged; still routed through it for the same
# guarantee every other task gets (a future DROPPED_COLLINEAR change
# would apply here too, automatically).
FEATURES["P4S"] = list(EARLY_FUNNEL_FEATURES)
MODEL_INPUT_FEATURES["P4S"] = model_feature_columns("P4S")

# P6 only. The decisive availability test at P6's snapshot (budget
# allocation moment) is "ad_budget בלבד" (§ נקודות חיזוי) -- computed as
# every P6 candidate EXCEPT ad_budget, directly from FEATURES["P6"] rather
# than hand-listed a second time, so this set can never silently drift
# from what FEATURES actually contains (the bug a prior round of review
# caught: purchased was hand-kept out of an earlier version of this set
# on a granularity argument -- "customer-level, not part of המשפך" -- that
# does not answer the availability question SPEC.md's snapshot rule
# actually asks. Every candidate other than ad_budget, purchased included,
# is substituted from the median profile per exact ad_budget level at
# serving time (חבילה 6), computed from training data within each fold.
# Still a real, observed training feature; only the SERVING-time value
# is profile-derived, not the training signal itself.
DERIVED_FROM_PROFILE = {
    "P6": frozenset(FEATURES["P6"]) - {"ad_budget"},
}


def column_status(column: str, task: str) -> str:
    """One of "Target" / "Excluded" / "Derived" / "Feature" for a raw
    column in a given task -- the single function docs/feature_matrix.md's
    parity test and any future caller check against, instead of
    re-deriving the four sets by hand."""
    if column == TARGET[task]:
        return "Target"
    if column in EXCLUDED[task]:
        return "Excluded"
    if column in DERIVED_FROM_PROFILE.get(task, ()):
        return "Derived"
    return "Feature"


# ---------------------------------------------------------------------------
# P6 budget-simulator strategy composition (SPEC's four locked spending
# strategies). Moved here from scripts/train.py (PHASE6.md checkpoint 12,
# D8) in phase 8 (docs/planning/PHASE8.md § ו.2) -- app/schemas.py's
# ד.8ב invariant 10 (allocations must match STRATEGY_ALLOCATIONS[strategy_id]
# exactly, in order) needs this without importing scripts.train. Pure
# transfer: same value, zero behavior change. Every strategy must sum to
# exactly 50,000 (checked in scripts/train.py's strategy_totals(), not
# re-asserted here -- one checker, not two).
# ---------------------------------------------------------------------------
STRATEGY_ALLOCATIONS = {
    "2x20000_1x10000": [(20000, 2), (10000, 1)],
    "10x5000": [(5000, 10)],
    "25x2000": [(2000, 25)],
    "100x500": [(500, 100)],
}


# ---------------------------------------------------------------------------
# Budget tiers (SPEC.md § שש החבילות, חבילה 1). Mirrors
# supabase/migrations/20260901164904_views.sql's budget_tier_insight CASE
# exactly, including the deliberate absence of an ELSE branch (PHASE5.md
# D8): a value in the gap is its own case, not silently folded into "Mid".
# ---------------------------------------------------------------------------

def budget_tier(ad_budget: int | float) -> str | None:
    """Low <=1500 / Mid 2000-5000 / High >5000. Returns None for the
    1501-1999 gap -- empty in the real dataset (PHASE0.md), but a caller
    must not guess a tier for it."""
    if ad_budget <= 1500:
        return "Low"
    if 2000 <= ad_budget <= 5000:
        return "Mid"
    if ad_budget > 5000:
        return "High"
    return None
