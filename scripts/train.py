"""Phase 6 -- single mechanical entry point for training, calibrating,
and evaluating P2/P3/P4/P6 (docs/planning/PHASE6.md, SPEC.md § שש
החבילות). Imports scripts.load_data.load_and_verify_csv (SHA-256 +
header check, source_row_id) and app.features (TARGET/FEATURES) as the
single mechanical sources of truth for the CSV contract and per-task
feature lists -- nothing here redefines them.

Built incrementally, one PHASE6.md checkpoint at a time. This module
currently holds checkpoint 3's split layer, checkpoint 4's shared CV
folds + preprocessing Pipelines, and checkpoint 5's decision-rule pure
functions (One-SE, the paired guardrail veto, Split Conformal's
quantile, top-decile metrics, Lift@K) -- all built and tested before
any model is trained.
"""
from __future__ import annotations

import math
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from app.features import FEATURES, TARGET, budget_tier  # noqa: E402
from scripts.load_data import load_and_verify_csv  # noqa: E402

import numpy as np
import pandas as pd
from sklearn.compose import ColumnTransformer
from sklearn.model_selection import KFold, StratifiedKFold, train_test_split
from sklearn.preprocessing import FunctionTransformer, OneHotEncoder

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

def one_se_stats(scores) -> tuple[float, float]:
    """A candidate's mean and standard ERROR over its 5 CV fold scores
    (SPEC.md's One-SE rule): SE = std(scores, ddof=1) / sqrt(5).
    ⚠ Standard error, not standard deviation -- the /sqrt(5) is
    mandatory, and ddof=1 (sample std) is mandatory too."""
    scores = np.asarray(scores, dtype=float)
    mean = float(scores.mean())
    se = float(scores.std(ddof=1) / math.sqrt(len(scores)))
    return mean, se


def one_se_eligible(candidate_mean: float, best_mean: float, best_se: float,
                     higher_is_better: bool) -> bool:
    """Whether a candidate is within one standard error of the best
    model b. The threshold uses SE_b -- the *best* model's own SE --
    never the candidate's own SE (SPEC.md's One-SE rule is explicit
    about this). Inclusive at the boundary (<=/>=)."""
    if higher_is_better:
        return candidate_mean >= best_mean - best_se
    return candidate_mean <= best_mean + best_se


def paired_delta_stats(deltas) -> dict:
    """mean, standard error (ddof=1, /sqrt(n)), and the count of
    positive folds for a set of paired per-fold differences -- the
    shared building block behind P6's guardrail veto (D7), P3's
    regular-vs-weighted pairing (D11), and the duplicate-sensitivity
    report (D16, report-only -- these numbers without a veto verdict)."""
    deltas = np.asarray(deltas, dtype=float)
    n = len(deltas)
    mean = float(deltas.mean())
    se = float(deltas.std(ddof=1) / math.sqrt(n))
    return {"mean": mean, "se": se, "n_positive": int((deltas > 0).sum()), "n_folds": n}


def guardrail_vetoed(delta_rmse, delta_abs_bias) -> dict:
    """P6's two-condition guardrail veto (SPEC.md, PHASE6.md D7):
    vetoed if EITHER Δ_RMSE or Δ_absBias satisfies both (1) a
    consistent direction -- Δ>0 in at least 4 of 5 folds -- and (2) a
    magnitude beyond noise -- mean(Δ) > SE(Δ). Checked separately per
    metric; a single metric failing both conditions is enough to veto.
    A veto-only rule: it can disqualify a candidate, never select one."""
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
    residuals = np.sort(np.abs(np.asarray(residuals, dtype=float)))
    n = len(residuals)
    rank = min(math.ceil((n + 1) * (1 - alpha)), n)
    return float(residuals[rank - 1])


def conformal_interval(point_estimate: float, q: float) -> tuple[float, float]:
    """P2's prediction interval (D9): [point - q, point + q], lower
    bound clipped at 0 -- ltv_months is never negative. The clip is a
    documented one-sided deviation from the interval's symmetry, not a
    second, independent decision."""
    return max(0.0, point_estimate - q), point_estimate + q


def top_decile_mask(y_true) -> np.ndarray:
    """The top decile by actual value -- exact-K, K=ceil(0.1*N), same
    convention as scripts/analysis.py's m3_top_decile, stable tie-break
    by original position. Used for P6's guardrail metrics (SPEC.md:
    "מוגדר על cumulative_profit בפועל", never on a prediction)."""
    y_true = np.asarray(y_true, dtype=float)
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
    y_true = np.asarray(y_true, dtype=float)
    y_pred = np.asarray(y_pred, dtype=float)
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
    same tie-break convention as top_decile_mask."""
    y_true = np.asarray(y_true, dtype=float)
    y_score = np.asarray(y_score, dtype=float)
    n = len(y_true)
    K = math.ceil(k * n)
    order = np.argsort(-y_score, kind="stable")
    top_k_true = y_true[order[:K]]
    precision_at_k = float(top_k_true.mean()) if K else None
    base_rate = float(y_true.mean())
    lift = (precision_at_k / base_rate) if base_rate else None
    return {"precision_at_k": precision_at_k, "base_rate": base_rate, "lift": lift, "K": K}


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
