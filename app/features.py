"""Single mechanical source of truth for per-task feature lists and the
budget-tier mapping (CLAUDE.md § app/features.py; PHASE5.md D2).

docs/feature_matrix.md is the methodological companion -- business
meaning, granularity, availability timing, and the reasoning behind every
Feature/Target/Excluded status below, for all 19 raw source columns across
P2/P3/P4/P6. tests/test_features.py checks the two never drift apart.
Grounded directly in SPEC.md § החרגות דליפה, § אוכלוסיות אימון, and
§ נקודות חיזוי -- nothing here is inferred from a measured target
relationship (SPEC.md's D3 rule for this phase).

Not connected to app/main.py and does not perform any modeling in phase 5
-- imported by tests only. Phase 6 wires it into the actual training/
serving Pipelines.
"""
from __future__ import annotations

import sys
from pathlib import Path

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

TARGET = {
    "P2": "ltv_months",
    "P3": "upsell",
    "P4": "referred",
    "P6": "cumulative_profit",
}

EXCLUDED = {
    "P2": {"cumulative_profit", "upsell", "referred", "purchased"},
    "P3": {"cumulative_profit", "referred", "ltv_months", "purchased"},
    "P4": {"cumulative_profit", "upsell", "ltv_months", "purchased"},
    "P6": {"ltv_months", "upsell", "referred"},
}

# The three-way collinear group SPEC.md flags for in-Pipeline reduction
# ("שתיים בלבד... בתוך ה-Pipeline") -- leads_not_answered = num_leads -
# leads_answered exactly (perfect collinearity), so at most two of the
# three ever enter a model. Listed here as candidates in every task's
# feature list below; WHICH two (or num_leads + answer_rate instead) is a
# phase-6 Pipeline-build decision, not made or implemented here.
COLLINEAR_TRIO = ("num_leads", "leads_answered", "leads_not_answered")


def _feature_list(task: str) -> list[str]:
    """Every raw column that is neither the task's target nor excluded --
    in EXPECTED_COLUMNS order, the single existing source of truth for the
    raw 19-column contract (scripts.load_data), not redefined here."""
    drop = EXCLUDED[task] | {TARGET[task]}
    return [c for c in EXPECTED_COLUMNS if c not in drop]


FEATURES = {task: _feature_list(task) for task in TARGET}


def column_status(column: str, task: str) -> str:
    """One of "Target" / "Excluded" / "Feature" for a raw column in a given
    task -- the single function docs/feature_matrix.md's parity test and
    any future caller check against, instead of re-deriving the three sets
    by hand."""
    if column == TARGET[task]:
        return "Target"
    if column in EXCLUDED[task]:
        return "Excluded"
    return "Feature"


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
