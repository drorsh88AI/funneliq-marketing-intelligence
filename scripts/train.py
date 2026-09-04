"""Phase 6 -- single mechanical entry point for training, calibrating,
and evaluating P2/P3/P4/P6 (docs/planning/PHASE6.md, SPEC.md § שש
החבילות). Imports scripts.load_data.load_and_verify_csv (SHA-256 +
header check, source_row_id) and app.features (TARGET/FEATURES) as the
single mechanical sources of truth for the CSV contract and per-task
feature lists -- nothing here redefines them.

Built incrementally, one PHASE6.md checkpoint at a time. This module
currently holds checkpoint 3's split layer, checkpoint 4's shared CV
folds + preprocessing Pipelines, checkpoint 5's decision-rule pure
functions (One-SE, the paired guardrail veto, Split Conformal's
quantile, top-decile metrics, Lift@K) -- all built and tested before
any model is trained -- and checkpoints 6-8's actual training (P2, P3,
P4).
"""
from __future__ import annotations

import json
import math
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from app.features import FEATURES, TARGET, budget_tier  # noqa: E402
from scripts.load_data import load_and_verify_csv  # noqa: E402

import numpy as np
import pandas as pd
from sklearn.base import clone
from sklearn.compose import ColumnTransformer
from sklearn.dummy import DummyClassifier, DummyRegressor
from sklearn.linear_model import LinearRegression, LogisticRegression
from sklearn.metrics import accuracy_score, f1_score, make_scorer, precision_score, recall_score, roc_auc_score
from sklearn.model_selection import (
    KFold,
    RandomizedSearchCV,
    StratifiedKFold,
    cross_validate,
    train_test_split,
)
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import FunctionTransformer, OneHotEncoder
from catboost import CatBoostClassifier, CatBoostRegressor
from lightgbm import LGBMClassifier, LGBMRegressor
from xgboost import XGBClassifier, XGBRegressor

# ---------------------------------------------------------------------------
# Checkpoint 3 -- split layer (PHASE6.md D2, D18/S6).
# ---------------------------------------------------------------------------

# One seed per task, documented up front, never chosen after looking at
# a result (PHASE6.md D2).
SEEDS = {"P2": 42, "P3": 43, "P4": 44, "P6": 45, "P4_sensitivity": 46}

# P3/P4 are classifiers and stratify their split by the target class;
# P2/P6 are regressions and don't (PHASE6.md D2).
STRATIFIED_TASKS = {"P3", "P4"}


def task_population(df: pd.DataFrame, task: str) -> pd.DataFrame:
    """The population a task trains and is evaluated on (SPEC.md §
    אוכלוסיות אימון): P2/P3/P4 restrict to purchased == 1 with a
    non-missing target; P6 uses the full population with a non-missing
    target and no purchased filter."""
    target = TARGET[task]
    pop = df[df[target].notna()]
    if task != "P6":
        pop = pop[pop["purchased"] == 1]
    return pop


def split_task(df: pd.DataFrame, task: str) -> dict[str, pd.Series]:
    """Two-stage split (PHASE6.md D2): Holdout 20% of the population,
    then a calibration set 20% of the remaining dev set -- P6 has no
    calibration split, so its train set *is* its dev set. P3/P4
    stratify by the target class; P2/P6 don't. Returns source_row_id
    Series per part so every downstream join is by id, never by
    positional index."""
    pop = task_population(df, task)
    target = TARGET[task]
    seed = SEEDS[task]
    stratify = pop[target] if task in STRATIFIED_TASKS else None

    dev, holdout = train_test_split(
        pop, test_size=0.2, random_state=seed, stratify=stratify
    )
    if task == "P6":
        train, calibration = dev, None
    else:
        stratify_dev = dev[target] if task in STRATIFIED_TASKS else None
        train, calibration = train_test_split(
            dev, test_size=0.2, random_state=seed, stratify=stratify_dev
        )

    return {
        "train": train["source_row_id"].reset_index(drop=True),
        "calibration": (
            None if calibration is None
            else calibration["source_row_id"].reset_index(drop=True)
        ),
        "holdout": holdout["source_row_id"].reset_index(drop=True),
    }


def p4_sensitivity_population(df: pd.DataFrame, p4_holdout_ids: pd.Series) -> pd.DataFrame:
    """The population-sensitivity analysis population (PHASE6.md D18,
    SPEC.md S6): every row with a non-missing `referred`, minus P4's
    own Holdout rows by source_row_id -- never the unfiltered 3,500,
    and never P4's Holdout. Trained with P4's winning hyperparameters,
    no tuning here (D17); evaluated together with the primary P4 model
    on p4_holdout_ids within P4's single Holdout opening (checkpoint
    14), not on a Holdout of its own."""
    target = TARGET["P4"]
    pop = df[df[target].notna()]
    return pop[~pop["source_row_id"].isin(p4_holdout_ids)]


# ---------------------------------------------------------------------------
# Checkpoint 4 -- shared CV folds + preprocessing Pipelines (PHASE6.md
# D3, D4, D5, D6).
# ---------------------------------------------------------------------------

# Dropped inside every Pipeline (D4): leads_not_answered = num_leads -
# leads_answered exactly, so at most two of the three collinear columns
# ever enter a model. num_leads + leads_answered are kept; answer_rate
# is never added, for either model.
DROPPED_COLLINEAR = "leads_not_answered"


def model_feature_columns(task: str) -> list[str]:
    """FEATURES[task] minus the dropped collinear column (D4) -- the
    raw columns every model for this task actually sees. Zero missing
    values among any task's features on the real data (D5, measured in
    PHASE6.md §ב) -- no imputer anywhere in the Pipeline."""
    return [c for c in FEATURES[task] if c != DROPPED_COLLINEAR]


def build_task_train_frame(df: pd.DataFrame, task: str) -> pd.DataFrame:
    """The task's train rows (from split_task), as a 0..n-1-indexed
    frame -- the exact frame every fold's positional indices and every
    later model fit for this task must use, or `cv=` fold positions
    stop meaning what they say."""
    parts = split_task(df, task)
    pop = task_population(df, task)
    return pop[pop["source_row_id"].isin(parts["train"])].reset_index(drop=True)


def build_folds(df: pd.DataFrame, task: str) -> list[tuple[np.ndarray, np.ndarray]]:
    """The 5 shared CV folds over the task's train set (D3) -- built
    once, passed as cv= to every RandomizedSearchCV and every
    Baseline's cross_validate for this task, so every candidate is
    scored on identical folds (SPEC.md's "paired comparison"). P3/P4
    stratify by the target class; P2/P6 don't."""
    train_df = build_task_train_frame(df, task)
    seed = SEEDS[task]
    if task in STRATIFIED_TASKS:
        splitter = StratifiedKFold(n_splits=5, shuffle=True, random_state=seed)
        return list(splitter.split(train_df, train_df[TARGET[task]]))
    splitter = KFold(n_splits=5, shuffle=True, random_state=seed)
    return list(splitter.split(train_df))


def _add_budget_tier(df: pd.DataFrame) -> pd.DataFrame:
    """P4 only (D6): derives a budget_tier categorical column from
    ad_budget, via app.features.budget_tier -- the single mechanical
    source of truth for the tier boundaries. A module-level function
    (not a closure/lambda) so the FunctionTransformer wrapping it stays
    joblib-picklable for the deployed artifact (checkpoint 15). Returns
    a copy; never mutates the input."""
    out = df.copy()
    out["budget_tier"] = out["ad_budget"].map(budget_tier)
    return out


def build_preprocessing_steps(task: str, encode_budget_tier: bool) -> list[tuple[str, object]]:
    """The Pipeline steps every model for this task starts with, before
    the model step (added by later checkpoints) -- numeric passthrough
    of model_feature_columns(task), no imputer (D5). P4 only: budget_tier
    is derived from ad_budget *inside* the Pipeline (D6), so a deployed
    pipeline computes it at serving time from raw features, not from a
    pre-tiered input -- either left as a raw category for CatBoost's
    native categorical handling (encode_budget_tier=False), or one-hot
    encoded for the Logistic baseline (encode_budget_tier=True)."""
    numeric_cols = model_feature_columns(task)
    steps: list[tuple[str, object]] = []
    column_transformers = [("numeric", "passthrough", numeric_cols)]
    if task == "P4":
        steps.append(("budget_tier", FunctionTransformer(_add_budget_tier)))
        encoder = OneHotEncoder(handle_unknown="ignore") if encode_budget_tier else "passthrough"
        column_transformers.append(("budget_tier", encoder, ["budget_tier"]))
    steps.append(("select", ColumnTransformer(column_transformers)))
    return steps


def encode_referred_target(series: pd.Series) -> pd.Series:
    """P4's target, Yes/No -> 1/0 (D6). P4 only -- referred is Excluded
    (never a feature) in every other task."""
    return series.map({"Yes": 1, "No": 0}).astype(int)


# ---------------------------------------------------------------------------
# Checkpoint 5 -- decision-rule pure functions (SPEC.md § בחירת מודל, §
# איכות עסקית; PHASE6.md D3/D7/D9/D11/D13/D16), built and tested BEFORE
# any model is trained -- nothing here has ever seen a real fold's
# scores, and no threshold here is chosen by looking at a result.
# ---------------------------------------------------------------------------

# Every candidate comparison in this project runs over exactly 5 CV
# folds (SPEC.md, throughout) -- enforced once, here, rather than
# trusting every caller to pass the right length. A 4-element array
# must never silently satisfy a ">=4 of 5" rule.
N_FOLDS = 5


def _require_finite_1d(values, name: str) -> np.ndarray:
    """The base check every array input to a decision rule goes
    through: one-dimensional, and every value finite. NaN/±inf must
    never reach a comparison and produce a silent, wrong decision --
    NaN compares False against everything, so an unguarded NaN score
    would quietly make a candidate look ineligible (or a veto look
    unmet) with no error at all."""
    values = np.asarray(values, dtype=float)
    if values.ndim != 1:
        raise ValueError(f"{name} must be one-dimensional, got shape {values.shape}")
    if not np.all(np.isfinite(values)):
        raise ValueError(f"{name} must contain only finite values (no NaN or ±inf)")
    return values


def _require_finite_scalar(value: float, name: str) -> float:
    """Same guarantee as _require_finite_1d, for the scalar inputs
    (means, standard errors, point estimates) that don't go through an
    array-shaped check."""
    value = float(value)
    if not math.isfinite(value):
        raise ValueError(f"{name} must be finite, got {value}")
    return value


def _require_n_folds(values, name: str) -> np.ndarray:
    values = _require_finite_1d(values, name)
    if values.size != N_FOLDS:
        raise ValueError(f"{name} must have exactly {N_FOLDS} values (one per CV fold), got {values.size}")
    return values


def _require_nonempty(values, name: str) -> np.ndarray:
    values = _require_finite_1d(values, name)
    if values.size == 0:
        raise ValueError(f"{name} must not be empty")
    return values


def _require_matching_length(a, b, a_name: str, b_name: str) -> None:
    if len(a) != len(b):
        raise ValueError(f"{a_name} and {b_name} must have the same length, got {len(a)} vs {len(b)}")


def one_se_stats(scores) -> tuple[float, float]:
    """A candidate's mean and standard ERROR over its 5 CV fold scores
    (SPEC.md's One-SE rule: "מתוך 5 ציוני ה-CV שלו"): SE = std(scores,
    ddof=1) / sqrt(5). ⚠ Standard error, not standard deviation -- the
    /sqrt(5) is mandatory, and ddof=1 (sample std) is mandatory too."""
    scores = _require_n_folds(scores, "scores")
    mean = float(scores.mean())
    se = float(scores.std(ddof=1) / math.sqrt(N_FOLDS))
    return mean, se


def one_se_eligible(candidate_mean: float, best_mean: float, best_se: float,
                     higher_is_better: bool) -> bool:
    """Whether a candidate is within one standard error of the best
    model b. The threshold uses SE_b -- the *best* model's own SE --
    never the candidate's own SE (SPEC.md's One-SE rule is explicit
    about this). Inclusive at the boundary (<=/>=). A NaN in any of the
    three inputs compares False against everything -- unguarded, it
    would silently make a candidate look ineligible with no error."""
    candidate_mean = _require_finite_scalar(candidate_mean, "candidate_mean")
    best_mean = _require_finite_scalar(best_mean, "best_mean")
    best_se = _require_finite_scalar(best_se, "best_se")
    if higher_is_better:
        return candidate_mean >= best_mean - best_se
    return candidate_mean <= best_mean + best_se


def paired_delta_stats(deltas) -> dict:
    """mean, standard error (ddof=1, /sqrt(5)), and the count of
    positive folds for a set of exactly 5 paired per-fold differences
    -- the shared building block behind P6's guardrail veto (D7), P3's
    regular-vs-weighted pairing (D11), and the duplicate-sensitivity
    report (D16, report-only -- these numbers without a veto verdict).
    Requires exactly 5 values -- SPEC.md's paired comparisons are
    always over the 5 CV folds, never a partial or padded set."""
    deltas = _require_n_folds(deltas, "deltas")
    mean = float(deltas.mean())
    se = float(deltas.std(ddof=1) / math.sqrt(N_FOLDS))
    return {"mean": mean, "se": se, "n_positive": int((deltas > 0).sum()), "n_folds": N_FOLDS}


def guardrail_vetoed(delta_rmse, delta_abs_bias) -> dict:
    """P6's two-condition guardrail veto (SPEC.md, PHASE6.md D7):
    vetoed if EITHER Δ_RMSE or Δ_absBias satisfies both (1) a
    consistent direction -- Δ>0 in at least 4 of 5 folds -- and (2) a
    magnitude beyond noise -- mean(Δ) > SE(Δ). Checked separately per
    metric; a single metric satisfying both conditions is enough to
    veto. A veto-only rule: it can disqualify a candidate, never select
    one. Both inputs go through paired_delta_stats, which rejects
    anything but exactly 5 values -- so a length mismatch between the
    two, or either being padded/truncated, fails loudly here rather
    than silently tripping (or missing) the ">=4 of 5" condition."""
    def _check(deltas):
        stats = paired_delta_stats(deltas)
        consistent_direction = stats["n_positive"] >= 4
        beyond_noise = stats["mean"] > stats["se"]
        return {"vetoed": consistent_direction and beyond_noise, **stats}

    rmse = _check(delta_rmse)
    abs_bias = _check(delta_abs_bias)
    return {"vetoed": rmse["vetoed"] or abs_bias["vetoed"], "rmse": rmse, "abs_bias": abs_bias}


def conformal_quantile(residuals, alpha: float = 0.05) -> float:
    """Split Conformal's finite-sample-valid quantile (SPEC.md, D9):
    the residual at sorted rank ceil((n+1)(1-alpha)) -- not
    numpy's naive interpolated quantile, which has no finite-sample
    coverage guarantee. Computed once on the calibration set's
    residuals, stored, never recomputed at request time."""
    if not (0 < alpha < 1):
        raise ValueError(f"alpha must be in (0, 1), got {alpha}")
    residuals = _require_nonempty(residuals, "residuals")
    residuals = np.sort(np.abs(residuals))
    n = len(residuals)
    rank = min(math.ceil((n + 1) * (1 - alpha)), n)
    return float(residuals[rank - 1])


def conformal_interval(point_estimate: float, q: float) -> tuple[float, float]:
    """P2's prediction interval (D9): [point - q, point + q], lower
    bound clipped at 0 -- ltv_months is never negative. The clip is a
    documented one-sided deviation from the interval's symmetry, not a
    second, independent decision."""
    point_estimate = _require_finite_scalar(point_estimate, "point_estimate")
    q = _require_finite_scalar(q, "q")
    return max(0.0, point_estimate - q), point_estimate + q


def top_decile_mask(y_true) -> np.ndarray:
    """The top decile by actual value -- exact-K, K=ceil(0.1*N), same
    convention as scripts/analysis.py's m3_top_decile, stable tie-break
    by original position. Used for P6's guardrail metrics (SPEC.md:
    "מוגדר על cumulative_profit בפועל", never on a prediction)."""
    y_true = _require_nonempty(y_true, "y_true")
    n = len(y_true)
    k = math.ceil(0.1 * n)
    order = np.argsort(-y_true, kind="stable")
    mask = np.zeros(n, dtype=bool)
    mask[order[:k]] = True
    return mask


def top_decile_metrics(y_true, y_pred) -> dict:
    """RMSE_top10 and Bias_top10 (SPEC.md's guardrail metrics):
    Bias_top10 = mean(pred - actual) -- the systematic error that
    harms a summing simulator, reported alongside RMSE_top10, never
    instead of it."""
    _require_matching_length(y_true, y_pred, "y_true", "y_pred")
    y_true = _require_nonempty(y_true, "y_true")
    y_pred = _require_finite_1d(y_pred, "y_pred")
    mask = top_decile_mask(y_true)
    yt, yp = y_true[mask], y_pred[mask]
    return {
        "rmse_top10": float(np.sqrt(np.mean((yp - yt) ** 2))),
        "bias_top10": float(np.mean(yp - yt)),
        "k": int(mask.sum()),
    }


def lift_at_k(y_true, y_score, k: float = 0.1) -> dict:
    """Lift@K = precision@K / base_rate (SPEC.md § איכות עסקית).
    base_rate is the positive rate of the SAME evaluation set
    precision@K is computed on -- never the population reference
    values (46.35% / 42.71%), which are report-only context, not the
    denominator. Exact-K = ceil(k*N), ranked by predicted score DESC,
    same tie-break convention as top_decile_mask. A target with zero
    positives (base_rate=0) returns lift=None rather than dividing by
    zero -- precision_at_k is still a well-defined 0.0 in that case."""
    if not (0 < k <= 1):
        raise ValueError(f"k must be in (0, 1], got {k}")
    _require_matching_length(y_true, y_score, "y_true", "y_score")
    y_true = _require_nonempty(y_true, "y_true")
    y_score = _require_finite_1d(y_score, "y_score")
    n = len(y_true)
    K = math.ceil(k * n)
    order = np.argsort(-y_score, kind="stable")
    top_k_true = y_true[order[:K]]
    precision_at_k = float(top_k_true.mean()) if K else None
    base_rate = float(y_true.mean())
    lift = (precision_at_k / base_rate) if base_rate else None
    return {"precision_at_k": precision_at_k, "base_rate": base_rate, "lift": lift, "K": K}


# ---------------------------------------------------------------------------
# Checkpoint 6+ -- locked tuning grid (SPEC.md § מרחב ותקציב ה-Tuning),
# shared across every task's search from here on.
# ---------------------------------------------------------------------------

GRID_LEARNING_RATE = [0.01, 0.05, 0.1, 0.2]
GRID_MAX_DEPTH = [3, 4, 5, 6]
GRID_N_ESTIMATORS = [200, 400, 800]
# num_leaves is paired to max_depth, not an independent search axis
# (SPEC.md: LightGBM splits leaf-wise, so its default num_leaves=31
# would silently cap capacity below what max_depth>=5 implies).
LIGHTGBM_NUM_LEAVES_FOR_DEPTH = {3: 8, 4: 16, 5: 32, 6: 64}

SEARCH_N_ITER = 20
SEARCH_RANDOM_STATE = 42  # locked for both the search and every model's own seed
SEARCH_N_JOBS = 1         # thread=1 at the model level too (D20) -- set per-booster below

SCORING = {
    "P2": "neg_mean_absolute_error",
    "P3": "roc_auc",
    "P4": "roc_auc",
    "P6": "neg_root_mean_squared_error",
}


def xgboost_param_distributions() -> dict:
    return {
        "model__learning_rate": GRID_LEARNING_RATE,
        "model__max_depth": GRID_MAX_DEPTH,
        "model__n_estimators": GRID_N_ESTIMATORS,
    }


def lightgbm_param_distributions() -> list[dict]:
    """Enumerated as fully-specified (max_depth, num_leaves) pairs --
    each dict's values are single-element lists so RandomizedSearchCV
    samples whole dicts, never cross-combining a depth from one dict
    with the num_leaves of another."""
    return [
        {
            "model__learning_rate": [lr],
            "model__max_depth": [depth],
            "model__num_leaves": [LIGHTGBM_NUM_LEAVES_FOR_DEPTH[depth]],
            "model__n_estimators": [n],
        }
        for lr in GRID_LEARNING_RATE
        for depth in GRID_MAX_DEPTH
        for n in GRID_N_ESTIMATORS
    ]


def catboost_param_distributions() -> dict:
    return {
        "model__learning_rate": GRID_LEARNING_RATE,
        "model__depth": GRID_MAX_DEPTH,
        "model__iterations": GRID_N_ESTIMATORS,
    }


def make_p2_boosters() -> dict:
    """The three regressors the brief requires for P2 (SPEC.md §שש
    החבילות), each with its locked param_distributions. Default
    objective/loss for every library -- P2's target is symmetric
    (ltv_months), no special objective needed (that's P6-only)."""
    return {
        "xgboost": (
            XGBRegressor(random_state=SEARCH_RANDOM_STATE, n_jobs=SEARCH_N_JOBS, verbosity=0),
            xgboost_param_distributions(),
        ),
        "lightgbm": (
            LGBMRegressor(random_state=SEARCH_RANDOM_STATE, n_jobs=SEARCH_N_JOBS, verbose=-1),
            lightgbm_param_distributions(),
        ),
        "catboost": (
            CatBoostRegressor(random_state=SEARCH_RANDOM_STATE, thread_count=SEARCH_N_JOBS, verbose=False),
            catboost_param_distributions(),
        ),
    }


# P2's full metric set (D13): MAE is the primary metric that drives
# selection; RMSE and R² are secondary and reported alongside, on the
# exact same winning fold model -- multi-metric scoring computes all
# three per fold without an extra fit, verified empirically against
# sklearn 1.9.0 before writing this (RandomizedSearchCV(scoring=dict,
# refit=<primary>) exposes split{k}_test_<name> for every name in the
# dict, all at the same best_index_).
P2_SCORING = {"mae": "neg_mean_absolute_error", "rmse": "neg_root_mean_squared_error", "r2": "r2"}
P2_PRIMARY_METRIC = "mae"
# Scorers sklearn negates (lower-is-better made higher-is-better) --
# these get sign-flipped back to their natural scale before reporting;
# r2 is already reported on its natural (higher-is-better) scale.
P2_NEGATED_SCORERS = {"mae", "rmse"}


def _search_candidate(estimator, param_distributions, preprocessing_steps, X, y, folds,
                       scoring: dict, refit: str, fit_params: dict | None = None) -> dict:
    """Runs one RandomizedSearchCV over the shared folds and extracts
    the winning configuration's 5 per-fold scores, for every metric in
    `scoring`, from cv_results_ at best_index_ (D3) -- no second CV run
    for the winner, and no second CV run per extra metric either.

    fit_params (step__param, e.g. "model__cat_features") is forwarded
    to .fit() rather than the estimator's constructor -- CatBoost's
    cat_features breaks sklearn's clone() when set at construction
    (verified empirically before writing this: RandomizedSearchCV and
    Pipeline both clone the estimator internally, and CatBoost's
    get_params()/constructor pairing isn't clone-safe for this specific
    parameter), so P4's booster (checkpoint 8) needs this route."""
    pipeline = Pipeline(preprocessing_steps + [("model", estimator)])
    search = RandomizedSearchCV(
        pipeline,
        param_distributions=param_distributions,
        n_iter=SEARCH_N_ITER,
        cv=folds,
        scoring=scoring,
        refit=refit,
        random_state=SEARCH_RANDOM_STATE,
        n_jobs=SEARCH_N_JOBS,
    )
    search.fit(X, y, **(fit_params or {}))
    best = search.best_index_
    fold_scores = {
        name: [float(search.cv_results_[f"split{k}_test_{name}"][best]) for k in range(N_FOLDS)]
        for name in scoring
    }
    return {"best_params": search.best_params_, "fold_scores": fold_scores}


def _baseline_candidate(estimator, preprocessing_steps, X, y, folds, scoring: dict) -> dict:
    """A Baseline has no hyperparameters in the locked grid -- scored
    directly with cross_validate on the same shared folds, not a
    RandomizedSearchCV of one candidate. cross_validate(scoring=dict)
    returns one test_<name> array per metric, same folds, one fit
    each -- no extra CV run per metric."""
    pipeline = Pipeline(preprocessing_steps + [("model", estimator)])
    result = cross_validate(pipeline, X, y, cv=folds, scoring=scoring)
    fold_scores = {name: [float(s) for s in result[f"test_{name}"]] for name in scoring}
    return {"fold_scores": fold_scores}


def _metric_summary(fold_scores: dict, role: str, best_params: dict | None = None,
                     negated_scorers: set = P2_NEGATED_SCORERS) -> dict:
    """One {fold_scores_<metric>, mean_<metric>, std_<metric>,
    se_<metric>} quadruple per metric in fold_scores, sign-corrected
    back to each metric's natural scale for every name in
    `negated_scorers` (sklearn's neg_* scorer convention). mean ± std
    is what D13's "ב-CV — per-fold + ממוצע ± std" column asks for and
    what gets reported; se (= std/sqrt(5)) is kept alongside as a
    separate field for the One-SE rule's own use in checkpoint 10 --
    std and se are different numbers (se = std/√5), not two names for
    the same one."""
    out: dict = {"role": role}
    if best_params is not None:
        out["best_params"] = best_params
    for name, scores in fold_scores.items():
        natural_scores = [-s for s in scores] if name in negated_scorers else list(scores)
        mean, se = one_se_stats(natural_scores)
        std = se * math.sqrt(N_FOLDS)
        out[f"fold_scores_{name}"] = natural_scores
        out[f"mean_{name}"] = mean
        out[f"std_{name}"] = std
        out[f"se_{name}"] = se
    return out


def train_p2(df: pd.DataFrame) -> dict:
    """Checkpoint 6: P2's three required boosters (searched) + two
    Baselines (Dummy, Linear), all scored on the same 5 shared folds
    over P2's train set, on all three of D13's metrics (MAE primary,
    RMSE + R² secondary). Selection (One-SE eligibility + the RSS
    tie-break) is checkpoint 10's job across all four tasks, and uses
    MAE only -- RMSE/R² here are report-only."""
    task = "P2"
    train_df = build_task_train_frame(df, task)
    y = train_df[TARGET[task]]
    folds = build_folds(df, task)
    preprocessing_steps = build_preprocessing_steps(task, encode_budget_tier=False)

    results = {}
    for name, (estimator, param_distributions) in make_p2_boosters().items():
        candidate = _search_candidate(
            estimator, param_distributions, preprocessing_steps, train_df, y, folds,
            P2_SCORING, refit=P2_PRIMARY_METRIC,
        )
        results[name] = _metric_summary(candidate["fold_scores"], "candidate", candidate["best_params"])

    baselines = {
        "dummy": DummyRegressor(strategy="mean"),
        "linear": LinearRegression(),
    }
    for name, estimator in baselines.items():
        candidate = _baseline_candidate(estimator, preprocessing_steps, train_df, y, folds, P2_SCORING)
        role = "benchmark" if name == "dummy" else "baseline"
        results[name] = _metric_summary(candidate["fold_scores"], role)

    return results


# ---------------------------------------------------------------------------
# Checkpoint 7 -- P3: search + Baselines + regular-vs-weighted (D11) +
# two manual rules (D11).
# ---------------------------------------------------------------------------

def _lift_at_10_score_func(y_true, y_score) -> float:
    """Wraps checkpoint 5's lift_at_k as an sklearn scorer function
    (make_scorer(response_method='predict_proba') hands this the
    positive-class column already extracted, verified empirically
    against sklearn 1.9.0 before writing this)."""
    return lift_at_k(y_true, y_score, k=0.1)["lift"]


# D13's full metric set for P3: ROC-AUC is primary; PR-AUC, Accuracy,
# Precision, Recall, F1, Lift@10%, Brier and log loss (tagged
# uncalibrated -- no calibrator exists yet, that's checkpoint 11) are
# secondary and reported alongside, all in the SAME multi-metric search
# -- zero extra fits, same principle checkpoint 6 was corrected to use
# for P2's RMSE/R². K∈{5%,20%} for Lift is explicitly optional
# ("רשאים להתלוות") per SPEC -- skipped here, not required.
P3_SCORING = {
    "roc_auc": "roc_auc",
    "pr_auc": "average_precision",
    "accuracy": "accuracy",
    # zero_division=0, not sklearn's default zero_division='warn' -- a
    # majority-class Dummy predicts zero positives every fold, and the
    # bare "precision" string scorer warns on every one of them
    # (verified empirically: recall/f1 do NOT warn in the same
    # scenario, only precision does -- left as strings).
    "precision": make_scorer(precision_score, zero_division=0),
    "recall": "recall",
    "f1": "f1",
    "brier": "neg_brier_score",
    "log_loss": "neg_log_loss",
    "lift_at_10": make_scorer(_lift_at_10_score_func, response_method="predict_proba"),
}
P3_PRIMARY_METRIC = "roc_auc"
P3_NEGATED_SCORERS = {"brier", "log_loss"}


def make_p3_boosters() -> dict:
    """The three classifiers the brief requires for P3, each with the
    same locked param_distributions as P2 (identical hyperparameter
    names across regression/classification for each library)."""
    return {
        "xgboost": (
            XGBClassifier(random_state=SEARCH_RANDOM_STATE, n_jobs=SEARCH_N_JOBS, verbosity=0, eval_metric="logloss"),
            xgboost_param_distributions(),
        ),
        "lightgbm": (
            LGBMClassifier(random_state=SEARCH_RANDOM_STATE, n_jobs=SEARCH_N_JOBS, verbose=-1),
            lightgbm_param_distributions(),
        ),
        "catboost": (
            CatBoostClassifier(random_state=SEARCH_RANDOM_STATE, thread_count=SEARCH_N_JOBS, verbose=False),
            catboost_param_distributions(),
        ),
    }


def train_p3(df: pd.DataFrame) -> dict:
    """Checkpoint 7: P3's three required boosters (searched) + two
    Baselines (Dummy, Logistic), all scored on the same 5 shared folds
    over P3's train set, on all of D13's metrics (ROC-AUC primary; the
    rest report-only). Selection (One-SE eligibility + the RSS
    tie-break) is checkpoint 10's job, and uses ROC-AUC only."""
    task = "P3"
    train_df = build_task_train_frame(df, task)
    y = train_df[TARGET[task]]
    folds = build_folds(df, task)
    preprocessing_steps = build_preprocessing_steps(task, encode_budget_tier=False)

    results = {}
    for name, (estimator, param_distributions) in make_p3_boosters().items():
        candidate = _search_candidate(
            estimator, param_distributions, preprocessing_steps, train_df, y, folds,
            P3_SCORING, refit=P3_PRIMARY_METRIC,
        )
        results[name] = _metric_summary(
            candidate["fold_scores"], "candidate", candidate["best_params"], negated_scorers=P3_NEGATED_SCORERS,
        )

    baselines = {
        "dummy": DummyClassifier(strategy="most_frequent"),
        # max_iter=5000 -- P3's unscaled features (ad_budget in the
        # thousands next to 0-100 counts) need ~3,500 lbfgs iterations
        # to converge; verified empirically (1000 does not converge,
        # 5000 does with headroom, 20000 changes nothing further).
        "logistic": LogisticRegression(max_iter=5000),
    }
    for name, estimator in baselines.items():
        candidate = _baseline_candidate(estimator, preprocessing_steps, train_df, y, folds, P3_SCORING)
        role = "benchmark" if name == "dummy" else "baseline"
        results[name] = _metric_summary(candidate["fold_scores"], role, negated_scorers=P3_NEGATED_SCORERS)

    return results


def _p3_class_weight_ratio(y) -> float:
    """scale_pos_weight = n_negative / n_positive, computed from the
    train fold's own labels -- the same formula for every booster
    (D11: "אותה נוסחה", not per-library magic)."""
    y = pd.Series(y)
    n_pos = int((y == 1).sum())
    n_neg = int((y == 0).sum())
    return n_neg / n_pos


def train_p3_weighted_comparison(df: pd.DataFrame, p3_results: dict) -> dict:
    """D11: for each of the three boosters, a paired arm using the SAME
    winning hyperparameters as the regular search (no new search), with
    class weighting added via scale_pos_weight -- decided on ROC-AUC
    alone (D11: "לא Brier" -- sigmoid is a monotonic transform, ROC-AUC
    is invariant to it, Brier isn't). The regular arm's ROC-AUC scores
    are reused from p3_results (already computed, zero extra fits);
    only the weighted arm is fit fresh -- 5 fits x 3 boosters = 15,
    matching D11's stated budget exactly.

    The class-weight ratio is recomputed separately inside each fold,
    from that fold's own train-only labels -- cross_validate() can't do
    this (one fixed scale_pos_weight baked into the estimator before
    the fold loop starts would leak that fold's own validation labels
    into its training hyperparameter), so folds are iterated by hand.
    Still exactly 5 fits per booster: the ratio itself costs nothing
    beyond a label count, not a fit."""
    task = "P3"
    train_df = build_task_train_frame(df, task)
    y = train_df[TARGET[task]].to_numpy()
    folds = build_folds(df, task)
    preprocessing_steps = build_preprocessing_steps(task, encode_budget_tier=False)

    comparison = {}
    for name, (estimator, _) in make_p3_boosters().items():
        best_params = {k.removeprefix("model__"): v for k, v in p3_results[name]["best_params"].items()}

        fold_ratios = []
        fold_scores = []
        for train_idx, val_idx in folds:
            ratio = _p3_class_weight_ratio(y[train_idx])  # train-only, no validation leakage
            fold_ratios.append(ratio)

            weighted_estimator = clone(estimator).set_params(**best_params, scale_pos_weight=ratio)
            weighted_pipeline = Pipeline(preprocessing_steps + [("model", weighted_estimator)])
            weighted_pipeline.fit(train_df.iloc[train_idx], y[train_idx])
            proba = weighted_pipeline.predict_proba(train_df.iloc[val_idx])[:, 1]
            fold_scores.append(float(roc_auc_score(y[val_idx], proba)))

        wt_mean, wt_se = one_se_stats(fold_scores)
        reg_mean = p3_results[name]["mean_roc_auc"]

        comparison[name] = {
            "class_weight_ratios_per_fold": fold_ratios,  # kept for audit -- 5 values, one per fold
            "regular_mean_roc_auc": reg_mean,
            "weighted_fold_scores_roc_auc": fold_scores,
            "weighted_mean_roc_auc": wt_mean,
            "weighted_std_roc_auc": wt_se * math.sqrt(N_FOLDS),
            "weighted_se_roc_auc": wt_se,
            "weighted_better": wt_mean > reg_mean,
        }
    return comparison


def _p3_rule_fold_metrics(y: np.ndarray, pred: np.ndarray, folds) -> dict:
    """A zero-fit rule's per-fold metrics -- P3's folds are
    StratifiedKFold (checkpoint 4), so every validation slice has both
    classes present; no defensive branch needed for a degenerate
    single-class fold. ROC-AUC/PR-AUC on a hard 0/1 prediction is the
    degenerate single-operating-point case, still well-defined."""
    fold_scores = {"roc_auc": [], "accuracy": [], "precision": [], "recall": [], "f1": []}
    for _, val_idx in folds:
        yt, yp = y[val_idx], pred[val_idx]
        fold_scores["roc_auc"].append(roc_auc_score(yt, yp))
        fold_scores["accuracy"].append(accuracy_score(yt, yp))
        fold_scores["precision"].append(precision_score(yt, yp, zero_division=0))
        fold_scores["recall"].append(recall_score(yt, yp, zero_division=0))
        fold_scores["f1"].append(f1_score(yt, yp, zero_division=0))
    return _metric_summary(fold_scores, role="rule", negated_scorers=set())


def train_p3_brief_rule(df: pd.DataFrame) -> dict:
    """D11's rule (a) -- the brief's rule, zero fits, thresholds locked
    from train medians. Shown explicitly as a RETROSPECTIVE comparison
    -- ltv_months is Excluded from FEATURES["P3"], not available at
    P3's snapshot."""
    task = "P3"
    train_df = build_task_train_frame(df, task)
    y = train_df[TARGET[task]].to_numpy()
    folds = build_folds(df, task)

    ltv_threshold = float(train_df["ltv_months"].median())
    cac_threshold = float(train_df["customer_acquisition_cost"].median())
    brief_pred = (
        (train_df["ltv_months"] > ltv_threshold) & (train_df["customer_acquisition_cost"] < cac_threshold)
    ).to_numpy().astype(int)

    return {
        "description": "ltv_months > train median AND customer_acquisition_cost < train median "
                        "-- retrospective; ltv_months unavailable at P3's snapshot",
        "thresholds": {"ltv_months_gt": ltv_threshold, "customer_acquisition_cost_lt": cac_threshold},
        **_p3_rule_fold_metrics(y, brief_pred, folds),
    }


def train_p3_operational_rule(df: pd.DataFrame, feature: str, direction: str) -> dict:
    """D11's rule (b) -- an operational alternative using only
    FEATURES['P3'] columns, the fair comparison to the model. `feature`
    (must be in FEATURES['P3']) and `direction` ('gt' or 'lt') are
    chosen explicitly by the user before this runs -- not picked here.
    (An earlier version locked calls_to_closed on its own, without
    prior approval and on a mistaken "engagement" reading of a column
    that actually counts calls needed to close, not engagement; this
    was flagged as a real gap and reverted -- the feature choice
    belongs to the user, made from a plain description of each
    candidate's business rationale, before any run.) AND'd with
    customer_acquisition_cost < train median, the cost signal kept
    from the brief's rule."""
    if feature not in FEATURES["P3"]:
        raise ValueError(f"{feature!r} is not in FEATURES['P3'] -- rule (b) must use only P3-legal columns")
    if direction not in ("gt", "lt"):
        raise ValueError(f"direction must be 'gt' or 'lt', got {direction!r}")

    task = "P3"
    train_df = build_task_train_frame(df, task)
    y = train_df[TARGET[task]].to_numpy()
    folds = build_folds(df, task)

    feature_threshold = float(train_df[feature].median())
    cac_threshold = float(train_df["customer_acquisition_cost"].median())
    feature_cond = train_df[feature] > feature_threshold if direction == "gt" else train_df[feature] < feature_threshold
    operational_pred = (feature_cond & (train_df["customer_acquisition_cost"] < cac_threshold)).to_numpy().astype(int)

    symbol = ">" if direction == "gt" else "<"
    return {
        "description": f"{feature} {symbol} train median AND customer_acquisition_cost < train median "
                        f"-- uses only FEATURES['P3'] columns",
        "thresholds": {f"{feature}_{direction}": feature_threshold, "customer_acquisition_cost_lt": cac_threshold},
        **_p3_rule_fold_metrics(y, operational_pred, folds),
    }


# ---------------------------------------------------------------------------
# Checkpoint 8 -- P4: search + Baselines + budget_tier categorical.
# ---------------------------------------------------------------------------

def make_p4_boosters() -> dict:
    """P4's ONE required booster (SPEC.md §שש החבילות, חבילה 4):
    CatBoost with budget_tier as a native categorical feature -- P2/P3
    each require all three boosters (checkpoints 6/7); P4 requires
    only this one. ⚠ cat_features is deliberately NOT set here, in the
    constructor -- CatBoostClassifier(cat_features=[...]) breaks
    sklearn's clone() (verified empirically: RuntimeError, "constructor
    either does not set or modifies parameter cat_features"), which
    RandomizedSearchCV and Pipeline both call internally. It's passed
    at fit() time instead, via train_p4's fit_params -- see
    _search_candidate's fit_params parameter."""
    return {
        "catboost": (
            CatBoostClassifier(random_state=SEARCH_RANDOM_STATE, thread_count=SEARCH_N_JOBS, verbose=False),
            catboost_param_distributions(),
        ),
    }


def train_p4(df: pd.DataFrame) -> dict:
    """Checkpoint 8: P4's one required booster (CatBoost, budget_tier
    as a native categorical) + two Baselines (Dummy, Logistic), all
    scored on the same 5 shared folds over P4's train set, on the full
    D13 metric set -- identical to P3's (D13: "P4 | ROC-AUC | כנ"ל"),
    reused as-is rather than duplicated. Selection (One-SE eligibility
    + the RSS tie-break) is checkpoint 10's job, and uses ROC-AUC only.

    CatBoost gets budget_tier raw (its native categorical handling);
    Logistic can't consume a raw string column, so its Baseline uses
    the one-hot-encoded preprocessing instead -- a DIFFERENT Pipeline
    from the candidate's, both built from the same
    build_preprocessing_steps(task, encode_budget_tier=...) already in
    place since checkpoint 4. Dummy ignores its features entirely
    (strategy="most_frequent"), so it rides along on the same
    preprocessing as Logistic -- which arm it uses makes no difference
    to a Dummy's prediction."""
    task = "P4"
    train_df = build_task_train_frame(df, task)
    y = encode_referred_target(train_df[TARGET[task]])
    folds = build_folds(df, task)
    catboost_steps = build_preprocessing_steps(task, encode_budget_tier=False)
    baseline_steps = build_preprocessing_steps(task, encode_budget_tier=True)
    # budget_tier's fixed position in catboost_steps' output, right
    # after the numeric columns -- verified empirically before writing
    # this.
    cat_features_index = len(model_feature_columns(task))

    results = {}
    for name, (estimator, param_distributions) in make_p4_boosters().items():
        candidate = _search_candidate(
            estimator, param_distributions, catboost_steps, train_df, y, folds,
            P3_SCORING, refit=P3_PRIMARY_METRIC,
            fit_params={"model__cat_features": [cat_features_index]},
        )
        results[name] = _metric_summary(
            candidate["fold_scores"], "candidate", candidate["best_params"], negated_scorers=P3_NEGATED_SCORERS,
        )

    baselines = {
        "dummy": DummyClassifier(strategy="most_frequent"),
        # max_iter=50000 -- P4's one-hot budget_tier columns next to
        # P3's already-unscaled feature magnitudes push lbfgs further
        # than P3 needed; verified empirically (5000/10000 still warn,
        # 50000 converges with ~5x headroom at ~10,230 iterations used).
        "logistic": LogisticRegression(max_iter=50000),
    }
    for name, estimator in baselines.items():
        candidate = _baseline_candidate(estimator, baseline_steps, train_df, y, folds, P3_SCORING)
        role = "benchmark" if name == "dummy" else "baseline"
        results[name] = _metric_summary(candidate["fold_scores"], role, negated_scorers=P3_NEGATED_SCORERS)

    return results


def read_metrics_json(path: Path) -> dict:
    """Whatever tasks have been written so far -- {} if the file
    doesn't exist yet (checkpoint 6 is the first task to write it)."""
    if not path.exists():
        return {}
    with path.open(encoding="utf-8") as f:
        return json.load(f)


def write_metrics_json(all_results: dict, path: Path) -> None:
    """metrics.json = task -> candidate -> {role, scores, mean, se,
    ...}, nothing else (mirrors scripts/analysis.py's
    write_findings_json convention). ⚠ Deterministic content only --
    no timestamp, git sha, RSS, or run time here; those belong in
    run_metadata.json (D14), written separately in a later checkpoint.
    sort_keys makes the bytes independent of dict insertion order, so
    a re-run from the same CSV reproduces an identical file."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="\n") as f:
        json.dump(all_results, f, sort_keys=True, indent=2, allow_nan=False, ensure_ascii=False)
        f.write("\n")


if __name__ == "__main__":
    df = load_and_verify_csv(Path(__file__).resolve().parent.parent / "funnel_marketing_data.csv")
    for task in ("P2", "P3", "P4", "P6"):
        parts = split_task(df, task)
        n_cal = 0 if parts["calibration"] is None else len(parts["calibration"])
        print(f"{task}: train={len(parts['train'])} calibration={n_cal} "
              f"holdout={len(parts['holdout'])}")
        all_ids = pd.concat(
            [parts["train"], parts["holdout"]]
            + ([] if parts["calibration"] is None else [parts["calibration"]])
        )
        assert all_ids.is_unique, f"{task}: overlapping source_row_id across parts"

    p4_parts = split_task(df, "P4")
    sens_pop = p4_sensitivity_population(df, p4_parts["holdout"])
    overlap = set(sens_pop["source_row_id"]) & set(p4_parts["holdout"])
    print(f"P4_sensitivity: population={len(sens_pop)} overlap_with_P4_holdout={len(overlap)}")

    print("--- checkpoint 4: folds + pipelines ---")
    for task in ("P2", "P3", "P4", "P6"):
        train_df = build_task_train_frame(df, task)
        n_missing = train_df[model_feature_columns(task)].isna().sum().sum()
        folds = build_folds(df, task)
        fold_sizes = [(len(tr_i), len(va_i)) for tr_i, va_i in folds]
        print(f"{task}: n_train={len(train_df)} missing_features={n_missing} "
              f"n_folds={len(folds)} fold_sizes={fold_sizes}")
        assert n_missing == 0, f"{task}: unexpected missing feature values"
        assert len(folds) == 5

    for encode in (False, True):
        steps = build_preprocessing_steps("P4", encode_budget_tier=encode)
        train_df = build_task_train_frame(df, "P4")
        X = train_df
        for _, transformer in steps:
            X = transformer.fit_transform(X)
        print(f"P4 pipeline (encode_budget_tier={encode}): output shape={getattr(X, 'shape', None)}")

    y_encoded = encode_referred_target(build_task_train_frame(df, "P4")["referred"])
    print(f"P4 referred encoded: unique={sorted(y_encoded.unique())} dtype={y_encoded.dtype}")

    print("--- checkpoint 6: P2 search + Baselines ---")
    p2_results = train_p2(df)
    for name, r in sorted(p2_results.items()):
        print(f"P2/{name}: role={r['role']} "
              f"MAE={r['mean_mae']:.4f}+-{r['std_mae']:.4f} "
              f"RMSE={r['mean_rmse']:.4f}+-{r['std_rmse']:.4f} "
              f"R2={r['mean_r2']:.4f}+-{r['std_r2']:.4f}")

    print("--- checkpoint 7: P3 search + Baselines + weighted + manual rules ---")
    p3_results = train_p3(df)
    for name, r in sorted(p3_results.items()):
        print(f"P3/{name}: role={r['role']} "
              f"ROC-AUC={r['mean_roc_auc']:.4f}+-{r['std_roc_auc']:.4f} "
              f"Lift@10%={r['mean_lift_at_10']:.4f}")

    p3_weighted = train_p3_weighted_comparison(df, p3_results)
    for name, r in sorted(p3_weighted.items()):
        print(f"P3/{name} weighted: regular={r['regular_mean_roc_auc']:.4f} "
              f"weighted={r['weighted_mean_roc_auc']:.4f}+-{r['weighted_std_roc_auc']:.4f} "
              f"better={r['weighted_better']} ratios_per_fold={r['class_weight_ratios_per_fold']}")

    p3_brief_rule = train_p3_brief_rule(df)
    print(f"P3/brief_rule: ROC-AUC={p3_brief_rule['mean_roc_auc']:.4f} "
          f"F1={p3_brief_rule['mean_f1']:.4f} thresholds={p3_brief_rule['thresholds']}")

    # Operational rule (D11 rule b): closed > train median, chosen by
    # the user (2026-09-04) from 3 candidate FEATURES["P3"] columns
    # presented with business rationale only, no target scores.
    p3_operational_rule = train_p3_operational_rule(df, feature="closed", direction="gt")
    print(f"P3/operational_rule: ROC-AUC={p3_operational_rule['mean_roc_auc']:.4f} "
          f"F1={p3_operational_rule['mean_f1']:.4f} thresholds={p3_operational_rule['thresholds']}")

    print("--- checkpoint 8: P4 search + Baselines + budget_tier categorical ---")
    p4_results = train_p4(df)
    for name, r in sorted(p4_results.items()):
        print(f"P4/{name}: role={r['role']} "
              f"ROC-AUC={r['mean_roc_auc']:.4f}+-{r['std_roc_auc']:.4f} "
              f"Lift@10%={r['mean_lift_at_10']:.4f}")

    metrics_path = Path(__file__).resolve().parent.parent / "models" / "metrics.json"
    all_metrics = read_metrics_json(metrics_path)
    all_metrics["P2"] = p2_results
    all_metrics["P3"] = p3_results
    all_metrics["P3_weighted_comparison"] = p3_weighted
    all_metrics["P3_manual_rules"] = {"brief_rule": p3_brief_rule, "operational_rule": p3_operational_rule}
    all_metrics["P4"] = p4_results
    write_metrics_json(all_metrics, metrics_path)
    print(f"wrote {metrics_path}")
