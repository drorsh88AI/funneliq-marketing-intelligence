"""Phase 9 -- serving-side pure helpers, importable without pulling in
scripts.train's heavy module-level dependencies (matplotlib, catboost,
lightgbm, xgboost -- see PHASE9.md D3/D13).

conformal_interval() and _require_finite_scalar() are moved here FROM
scripts/train.py, which re-imports them back (D13) -- a pure transfer,
same value, same logic, zero behavior change, same pattern phase 8 used
for MODEL_INPUT_FEATURES/STRATEGY_ALLOCATIONS/EARLY_FUNNEL_FEATURES
(app/features.py). The move exists because P2's serving path does not
otherwise import scripts.train (verified: only P4/P4S do, via the
_add_budget_tier pickle reference -- PHASE9.md D3), and importing it just
for these 8 lines would drag lightgbm+matplotlib into every P2 request
for nothing.

⛔ Do not add anything here that reads a file, loads an artifact, or
otherwise has an import-time side effect -- PHASE9.md criterion 45 checks
`import app.inference` makes zero calls to open/json.load/joblib.load.
"""
from __future__ import annotations

import math


def _require_finite_scalar(value: float, name: str) -> float:
    """Guards a scalar input (point estimates, quantiles) against NaN/±inf
    reaching arithmetic and producing a silent, wrong result."""
    value = float(value)
    if not math.isfinite(value):
        raise ValueError(f"{name} must be finite, got {value}")
    return value


def conformal_interval(point_estimate: float, q: float) -> tuple[float, float]:
    """P2's prediction interval (SPEC.md D9): [point - q, point + q], lower
    bound clipped at 0 -- ltv_months is never negative. The clip is a
    documented one-sided deviation from the interval's symmetry, not a
    second, independent decision (S10: the interval width is fixed by q,
    not adjusted for evidence_level or local sample size)."""
    point_estimate = _require_finite_scalar(point_estimate, "point_estimate")
    q = _require_finite_scalar(q, "q")
    return max(0.0, point_estimate - q), point_estimate + q
