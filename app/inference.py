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
pandas and app.artifacts.get_artifact are imported LOCALLY inside the one
function each actually needs (build_input_frame, predict_if_in_domain),
never at module level -- a CI-only failure showed this module's import
graph (pandas, and transitively app.artifacts -> app.features ->
scripts.load_data) triggering one open() call on a fresh Linux process.
Keep it that way; don't move either import back to the top.
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


def out_of_range_features(meta: dict, values: dict) -> list[str]:
    """PHASE9.md D9: every feature in meta["feature_columns"] whose input
    value falls outside meta["ood_bounds"][feature] -- empty list means
    fully in-domain. Iterates feature_columns (not ood_bounds.keys()) so
    the order of a non-empty result is deterministic and matches the
    request schema's field order."""
    bounds = meta["ood_bounds"]
    return [
        col
        for col in meta["feature_columns"]
        if not (bounds[col]["min"] <= values[col] <= bounds[col]["max"])
    ]


def build_input_frame(meta: dict, values: dict) -> "pd.DataFrame":
    """PHASE9.md D17/criterion 74: the one-row DataFrame passed to
    predict()/predict_proba() -- built from EXACTLY meta["feature_columns"]
    (as both the column set and the order) and cast per
    meta["feature_dtypes"], never a DataFrame inferred structurally from
    the request body. A dtype the artifact's own meta declares that pandas
    can't satisfy raises ValueError -- callers map that to 500 (D17), not
    a silently-wrong dtype.

    Imports pandas locally, not at module level (criterion 45): a CI-only
    failure showed `import app.inference` triggering one open() call --
    almost certainly pandas' own import-time behavior on a fresh Linux
    process, not our code, but the fix that actually satisfies the
    criterion is removing pandas from this module's import graph entirely,
    not chasing which library line opened what."""
    import pandas as pd

    columns = meta["feature_columns"]
    dtypes = meta["feature_dtypes"]
    frame = pd.DataFrame([{col: values[col] for col in columns}], columns=columns)
    try:
        for col in columns:
            frame[col] = frame[col].astype(dtypes[col])
    except (TypeError, ValueError) as e:
        raise ValueError(f"failed to cast column {col!r} to dtype {dtypes[col]!r}: {e}") from e
    return frame


def predict_if_in_domain(task: str, meta: dict, values: dict, *, method: str = "predict"):
    """PHASE9.md D9: OOD short-circuits BEFORE the artifact is ever
    touched -- if any feature is out of range, returns (out_of_range,
    None) without calling get_artifact at all (criterion 44). Otherwise
    loads (or reuses) the cached artifact, builds the input frame per
    build_input_frame(), calls `.predict()` or `.predict_proba()` per
    `method`, and returns ([], raw_result). Task-agnostic and
    schema-agnostic on purpose -- the predict/insights routes wrap this
    with their own response-schema construction (warnings, evidence_level,
    etc.), never reimplementing the OOD gate or the DataFrame contract.

    Imports get_artifact locally, not at module level (criterion 45),
    same reasoning as build_input_frame's local pandas import above --
    app.artifacts (and its own import of app.features/scripts.load_data)
    has no business being on app.inference's import graph at all."""
    from app.artifacts import get_artifact

    out_of_range = out_of_range_features(meta, values)
    if out_of_range:
        return out_of_range, None
    artifact = get_artifact(task)
    frame = build_input_frame(meta, values)
    result = getattr(artifact, method)(frame)
    return [], result
