"""Tests for scripts/train.py -- checkpoint 3 (the split layer, D2,
D18/S6) and checkpoint 4 (shared CV folds + preprocessing Pipelines,
D3, D4, D5, D6). Later checkpoints (actual model training) get their
own test coverage as they're built.

Nothing here touches the real funnel_marketing_data.csv -- a synthetic
fixture, loaded the same way load_data.py loads the real one (so
dtypes match real end-to-end parsing, not hand-set via astype()). Runs
in CI with no CSV present, same convention as test_data_contract.py.
The real dataset's exact split sizes (2,776/695 for P6, 2,867 for the
P4 population-sensitivity analysis) are checked separately, against
the real CSV, at the local integration path (scripts/train.py's
__main__ block) -- not here.
"""
from __future__ import annotations

import hashlib
import math
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from app.features import budget_tier
from scripts import load_data as ld
from scripts import train as tr

# 60 rows: 40 purchased (2 of those with a missing ltv_months, to prove
# task_population applies the target-notna filter *in addition to* the
# purchased filter) + 20 not purchased. upsell/referred alternate for a
# clean 20/20 (purchased population) stratification split. Three of the
# last (not-purchased) rows carry a missing cumulative_profit, to prove
# P6's population excludes them despite having no purchased filter.
N_PURCHASED = 40
N_NOT_PURCHASED = 20
N = N_PURCHASED + N_NOT_PURCHASED

# Spans all three budget_tier boundaries (Low <=1500 / Mid 2000-5000 /
# High >5000) so checkpoint-4 pipeline tests actually exercise one-hot
# encoding across multiple categories, not just one.
TIER_BUDGETS = [500, 1200, 1500, 2000, 3000, 5000, 5500, 6000, 8000, 12000]


def _build_fixture_text() -> str:
    purchased = [1] * N_PURCHASED + [0] * N_NOT_PURCHASED
    ltv_months = []
    for i in range(N):
        if purchased[i] == 0 or i >= N_PURCHASED - 2:
            ltv_months.append("")  # missing: not-purchased, or last 2 purchased rows
        else:
            ltv_months.append(str(float(i + 1)))
    upsell = [i % 2 for i in range(N)]
    referred = ["Yes" if i % 2 == 0 else "No" for i in range(N)]
    cumulative_profit = [str(float(i * 100)) for i in range(N)]
    for i in (N - 3, N - 2, N - 1):
        cumulative_profit[i] = ""  # missing, in the not-purchased tail

    lines = [",".join(ld.EXPECTED_COLUMNS)]
    for i in range(N):
        row = [
            str(TIER_BUDGETS[i % len(TIER_BUDGETS)]), str(20 + i % 5), str(15 + i % 4), str(5 + i % 3),
            str(10 + i % 3), str(8 + i % 3), str(6 + i % 3), str(5 + i % 2), str(4 + i % 2),
            str(2 + i % 2), str(i % 2), str(1 + i % 3), str(1 + i % 2),
            str(500 + i), ltv_months[i], str(purchased[i]), str(upsell[i]),
            cumulative_profit[i], referred[i],
        ]
        lines.append(",".join(row))
    return "\n".join(lines) + "\n"


@pytest.fixture()
def df(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> pd.DataFrame:
    p = tmp_path / "sample.csv"
    p.write_text(_build_fixture_text())
    monkeypatch.setattr(ld, "EXPECTED_SHA256", hashlib.sha256(p.read_bytes()).hexdigest())
    return ld.load_and_verify_csv(p)


# ---------------------------------------------------------------------------
# task_population
# ---------------------------------------------------------------------------

def test_task_population_p2_excludes_not_purchased_and_missing_target(df):
    pop = tr.task_population(df, "P2")
    assert len(pop) == N_PURCHASED - 2  # 2 purchased rows have missing ltv_months
    assert (pop["purchased"] == 1).all()
    assert pop["ltv_months"].notna().all()


def test_task_population_p3_p4_are_purchased_only(df):
    for task in ("P3", "P4"):
        pop = tr.task_population(df, task)
        assert len(pop) == N_PURCHASED
        assert (pop["purchased"] == 1).all()


def test_task_population_p6_ignores_purchased_but_needs_target(df):
    pop = tr.task_population(df, "P6")
    assert len(pop) == N - 3  # 3 rows have missing cumulative_profit
    assert pop["cumulative_profit"].notna().all()
    assert set(pop["purchased"]) == {0, 1}  # no purchased filter applied


# ---------------------------------------------------------------------------
# split_task -- exact sizes, no overlap, union == population, determinism,
# stratification.
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("task", ["P2", "P3", "P4", "P6"])
def test_split_sizes_and_no_overlap(df, task):
    parts = tr.split_task(df, task)
    pop_n = len(tr.task_population(df, task))

    n_train, n_holdout = len(parts["train"]), len(parts["holdout"])
    n_cal = 0 if parts["calibration"] is None else len(parts["calibration"])

    # Exact two-stage 20%/20% split sizes -- ceil for the test set, per
    # sklearn's train_test_split(test_size=0.2) (PHASE6.md D2, S1).
    expected_holdout = math.ceil(pop_n * 0.2)
    expected_dev = pop_n - expected_holdout
    assert n_holdout == expected_holdout

    if task == "P6":
        assert parts["calibration"] is None
        assert n_train == expected_dev
    else:
        expected_cal = math.ceil(expected_dev * 0.2)
        expected_train = expected_dev - expected_cal
        assert n_cal == expected_cal
        assert n_train == expected_train

    # No overlap between any two parts, by source_row_id.
    train_ids, holdout_ids = set(parts["train"]), set(parts["holdout"])
    assert train_ids.isdisjoint(holdout_ids)
    if parts["calibration"] is not None:
        cal_ids = set(parts["calibration"])
        assert train_ids.isdisjoint(cal_ids)
        assert holdout_ids.isdisjoint(cal_ids)


@pytest.mark.parametrize("task", ["P2", "P3", "P4", "P6"])
def test_split_union_equals_task_population_exactly(df, task):
    """The three parts partition the population exactly -- no row
    dropped, no row invented, no row counted twice."""
    parts = tr.split_task(df, task)
    all_ids = set(parts["train"]) | set(parts["holdout"])
    if parts["calibration"] is not None:
        all_ids |= set(parts["calibration"])
    pop_ids = set(tr.task_population(df, task)["source_row_id"])
    assert all_ids == pop_ids


@pytest.mark.parametrize("task", ["P2", "P3", "P4", "P6"])
def test_split_is_deterministic_across_repeated_calls(df, task):
    first = tr.split_task(df, task)
    second = tr.split_task(df, task)
    assert list(first["train"]) == list(second["train"])
    assert list(first["holdout"]) == list(second["holdout"])
    if first["calibration"] is None:
        assert second["calibration"] is None
    else:
        assert list(first["calibration"]) == list(second["calibration"])


@pytest.mark.parametrize("task", ["P3", "P4"])
def test_split_stratifies_p3_p4_by_target_class(df, task):
    """A perfectly balanced 20/20 population must not tip a stratified
    split into a lopsided part -- each part stays within one row of the
    50/50 split it started from."""
    target = tr.TARGET[task]
    pop = tr.task_population(df, task)
    parts = tr.split_task(df, task)

    by_id = pop.set_index("source_row_id")[target]
    for part_name in ("train", "calibration", "holdout"):
        ids = parts[part_name]
        values = by_id.loc[ids]
        counts = values.value_counts()
        assert len(counts) == 2, f"{task} {part_name}: lost a class entirely"
        assert abs(counts.iloc[0] - counts.iloc[1]) <= 1, (
            f"{task} {part_name}: stratification not preserved, got {counts.to_dict()}"
        )


# ---------------------------------------------------------------------------
# p4_sensitivity_population -- population size and zero overlap with P4's
# own Holdout (PHASE6.md D18, SPEC.md S6).
# ---------------------------------------------------------------------------

def test_p4_sensitivity_population_size_and_no_holdout_overlap(df):
    p4_parts = tr.split_task(df, "P4")
    p4_holdout_ids = p4_parts["holdout"]

    sens_pop = tr.p4_sensitivity_population(df, p4_holdout_ids)

    referred_notna_n = df["referred"].notna().sum()
    assert len(sens_pop) == referred_notna_n - len(p4_holdout_ids)

    overlap = set(sens_pop["source_row_id"]) & set(p4_holdout_ids)
    assert overlap == set()

    # Not purchased-filtered -- this is exactly the point of the
    # counterfactual population (SPEC.md § אוכלוסיות אימון).
    assert set(sens_pop["purchased"]) == {0, 1}


# ---------------------------------------------------------------------------
# build_folds -- 5 shared folds over the train set (D3): valid partition,
# no leakage between a fold's own train/val, stratification preserved.
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("task", ["P2", "P3", "P4", "P6"])
def test_build_folds_returns_five_folds_that_partition_the_train_set(df, task):
    train_df = tr.build_task_train_frame(df, task)
    folds = tr.build_folds(df, task)
    assert len(folds) == 5

    for tr_idx, va_idx in folds:
        # Each fold's own train/val split is itself a clean, disjoint
        # partition of the same train_df -- positional indices, not ids.
        assert set(tr_idx).isdisjoint(set(va_idx))
        assert set(tr_idx) | set(va_idx) == set(range(len(train_df)))


def test_build_folds_is_deterministic_across_repeated_calls(df):
    first = tr.build_folds(df, "P4")
    second = tr.build_folds(df, "P4")
    for (tr1, va1), (tr2, va2) in zip(first, second):
        assert list(tr1) == list(tr2)
        assert list(va1) == list(va2)


@pytest.mark.parametrize("task", ["P3", "P4"])
def test_build_folds_stratifies_validation_splits(df, task):
    """Each fold's validation slice keeps both target classes present
    -- a plain KFold on a class-sorted population could starve one
    class out of a fold entirely. And it's not enough for both classes
    to merely appear somewhere: StratifiedKFold's actual guarantee is
    that each class's count is spread as evenly as possible across the
    5 folds, so no fold ends up skewed relative to the others -- that's
    checked here directly (max-min <= 1 per class across folds), not
    just presence."""
    train_df = tr.build_task_train_frame(df, task)
    target = tr.TARGET[task]
    folds = tr.build_folds(df, task)

    per_fold_counts = []
    for _, va_idx in folds:
        counts = train_df.iloc[va_idx][target].value_counts()
        assert len(counts) == 2
        per_fold_counts.append(counts)

    for cls in train_df[target].unique():
        cls_counts = [c.get(cls, 0) for c in per_fold_counts]
        assert max(cls_counts) - min(cls_counts) <= 1, (
            f"{task}: class {cls!r} spread unevenly across folds: {cls_counts}"
        )


# ---------------------------------------------------------------------------
# build_preprocessing_steps -- D4 (collinear column dropped), D5 (no
# missing / no imputer), D6 (budget_tier derived in-Pipeline, P4 only).
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("task", ["P2", "P3", "P4", "P6"])
def test_model_feature_columns_drops_the_collinear_column(task):
    cols = tr.model_feature_columns(task)
    assert tr.DROPPED_COLLINEAR not in cols
    assert "num_leads" in cols
    assert "leads_answered" in cols
    assert "answer_rate" not in cols  # never added, per D4


def test_budget_tier_only_added_for_p4(df):
    for task in ("P2", "P3", "P6"):
        steps = tr.build_preprocessing_steps(task, encode_budget_tier=False)
        assert all(name != "budget_tier" for name, _ in steps)

    steps = tr.build_preprocessing_steps("P4", encode_budget_tier=False)
    assert any(name == "budget_tier" for name, _ in steps)


def test_p4_pipeline_passthrough_keeps_budget_tier_as_one_raw_column(df):
    """Column count alone doesn't prove the raw column *is* budget_tier
    -- checked here by comparing its values, row for row, against
    independently computed Low/Mid/High labels."""
    train_df = tr.build_task_train_frame(df, "P4")
    X = train_df
    for _, transformer in tr.build_preprocessing_steps("P4", encode_budget_tier=False):
        X = transformer.fit_transform(X)
    n_numeric = len(tr.model_feature_columns("P4"))
    assert X.shape == (len(train_df), n_numeric + 1)  # +1 raw budget_tier column

    expected = train_df["ad_budget"].map(budget_tier).to_numpy()
    actual = X[:, -1]  # budget_tier is the last ColumnTransformer block
    assert list(actual) == list(expected)
    assert set(actual) <= {"Low", "Mid", "High"}


def test_p4_pipeline_one_hot_expands_budget_tier_into_multiple_columns(df):
    """Column count alone doesn't prove the extra columns are the
    Low/Mid/High categories -- checked here against the fitted
    OneHotEncoder's actual categories_, not just their count."""
    train_df = tr.build_task_train_frame(df, "P4")
    expected_tiers = sorted(train_df["ad_budget"].map(budget_tier).unique())
    assert set(expected_tiers) <= {"Low", "Mid", "High"}
    assert len(expected_tiers) >= 2, "fixture must span more than one budget tier"

    X = train_df
    column_transformer = None
    for name, transformer in tr.build_preprocessing_steps("P4", encode_budget_tier=True):
        X = transformer.fit_transform(X)
        if name == "select":
            column_transformer = transformer

    one_hot = column_transformer.named_transformers_["budget_tier"]
    assert sorted(one_hot.categories_[0]) == expected_tiers

    n_numeric = len(tr.model_feature_columns("P4"))
    assert X.shape == (len(train_df), n_numeric + len(expected_tiers))


def test_preprocessing_pipeline_produces_no_missing_values(df):
    """D5: no imputer anywhere -- only safe because the real data has
    zero missing feature values (measured in PHASE6.md §ב). On this
    fixture, every selected feature column is fully populated too."""
    for task in ("P2", "P3", "P4", "P6"):
        train_df = tr.build_task_train_frame(df, task)
        assert train_df[tr.model_feature_columns(task)].isna().sum().sum() == 0


def test_encode_referred_target_maps_yes_no_to_one_zero(df):
    train_df = tr.build_task_train_frame(df, "P4")
    encoded = tr.encode_referred_target(train_df["referred"])
    assert set(encoded.unique()) == {0, 1}
    assert (encoded[train_df["referred"] == "Yes"] == 1).all()
    assert (encoded[train_df["referred"] == "No"] == 0).all()


# ---------------------------------------------------------------------------
# Checkpoint 5 -- decision-rule pure functions, known-answer tests
# (PHASE6.md D3/D7/D9/D11/D13/D16). Hand-verified numbers, not the
# function re-deriving its own expectation.
# ---------------------------------------------------------------------------

def test_one_se_stats_known_answer():
    mean, se = tr.one_se_stats([1, 2, 3, 4, 5])
    assert mean == pytest.approx(3.0)
    assert se == pytest.approx(1 / math.sqrt(2))  # std(ddof=1)=sqrt(2.5), /sqrt(5)=sqrt(0.5)


def test_one_se_eligible_boundary_is_inclusive():
    best_mean, best_se = 3.0, 1 / math.sqrt(2)  # ~0.70710678

    # MAE/RMSE: lower is better. Exactly at the boundary -> eligible.
    assert tr.one_se_eligible(best_mean + best_se, best_mean, best_se, higher_is_better=False)
    assert not tr.one_se_eligible(best_mean + best_se + 0.001, best_mean, best_se, higher_is_better=False)

    # ROC-AUC: higher is better. Exactly at the boundary -> eligible.
    assert tr.one_se_eligible(0.9 - 0.02, 0.9, 0.02, higher_is_better=True)
    assert not tr.one_se_eligible(0.9 - 0.02 - 0.001, 0.9, 0.02, higher_is_better=True)


def test_one_se_eligible_uses_the_best_models_se_not_the_candidates():
    """A candidate 0.03 below the best mean is eligible against a wide
    best_se (0.05) but not against a narrow one (0.01) -- the
    eligibility band is a property of the best model, never redefined
    by whichever candidate is being checked."""
    assert tr.one_se_eligible(0.87, 0.90, best_se=0.05, higher_is_better=True)
    assert not tr.one_se_eligible(0.87, 0.90, best_se=0.01, higher_is_better=True)


def test_paired_delta_stats_known_answer():
    stats = tr.paired_delta_stats([1, 1, 1, 1, -1])
    assert stats["mean"] == pytest.approx(0.6)
    assert stats["se"] == pytest.approx(0.4)
    assert stats["n_positive"] == 4
    assert stats["n_folds"] == 5


def test_guardrail_vetoed_when_one_metric_is_consistent_and_beyond_noise():
    result = tr.guardrail_vetoed(
        delta_rmse=[1, 1, 1, 1, -1],          # 4/5 positive, mean 0.6 > se 0.4 -> vetoes
        delta_abs_bias=[0, 0, 0, 0, 0],        # flat -> neither condition holds
    )
    assert result["vetoed"] is True
    assert result["rmse"]["vetoed"] is True
    assert result["abs_bias"]["vetoed"] is False


def test_guardrail_not_vetoed_when_direction_is_inconsistent_on_both_metrics():
    result = tr.guardrail_vetoed(
        delta_rmse=[1, -1, 1, -1, 1],          # 3/5 positive -- fails condition (1)
        delta_abs_bias=[1, -1, 1, -1, 0],      # 2/5 positive -- fails condition (1)
    )
    assert result["vetoed"] is False
    assert result["rmse"]["vetoed"] is False
    assert result["abs_bias"]["vetoed"] is False


def test_conformal_quantile_known_answer():
    # n=39, residuals 1..39: rank = ceil(40*0.95) = 38 exactly -> the
    # 38th-smallest value, i.e. 38.
    q = tr.conformal_quantile(list(range(1, 40)), alpha=0.05)
    assert q == pytest.approx(38.0)


def test_conformal_quantile_clips_rank_to_n_for_small_samples():
    # n=3: rank = ceil(4*0.95) = 4, clipped to 3 -> the largest
    # residual. Also proves abs() is applied (negative input).
    q = tr.conformal_quantile([-5, 3, -1], alpha=0.05)
    assert q == pytest.approx(5.0)


def test_conformal_interval_clips_lower_bound_at_zero():
    assert tr.conformal_interval(100.0, 5.0) == pytest.approx((95.0, 105.0))
    assert tr.conformal_interval(3.0, 5.0) == pytest.approx((0.0, 8.0))


def test_top_decile_mask_known_answer():
    y_true = np.arange(1, 26)  # 1..25, n=25 -> k=ceil(2.5)=3
    mask = tr.top_decile_mask(y_true)
    assert mask.sum() == 3
    assert set(np.where(mask)[0]) == {22, 23, 24}  # values 23, 24, 25


def test_top_decile_metrics_known_answer():
    y_true = np.array([1, 2, 3, 4, 5, 6, 7, 8, 9, 10], dtype=float)
    y_pred = np.array([0, 0, 0, 0, 0, 0, 0, 0, 0, 12], dtype=float)  # only index 9 is top decile
    result = tr.top_decile_metrics(y_true, y_pred)
    assert result["k"] == 1
    assert result["rmse_top10"] == pytest.approx(2.0)   # |12-10|
    assert result["bias_top10"] == pytest.approx(2.0)   # 12-10


def test_lift_at_k_known_answer():
    y_true = np.array([1, 0, 1, 0, 1, 0, 1, 0, 1, 0], dtype=float)  # base_rate = 0.5
    y_score = np.array([10, 9, 1, 2, 3, 4, 5, 6, 7, 8], dtype=float)

    top1 = tr.lift_at_k(y_true, y_score, k=0.1)  # K=1, top score is a positive
    assert top1["K"] == 1
    assert top1["precision_at_k"] == pytest.approx(1.0)
    assert top1["base_rate"] == pytest.approx(0.5)
    assert top1["lift"] == pytest.approx(2.0)

    top2 = tr.lift_at_k(y_true, y_score, k=0.2)  # K=2, one positive one negative
    assert top2["K"] == 2
    assert top2["precision_at_k"] == pytest.approx(0.5)
    assert top2["lift"] == pytest.approx(1.0)  # no ranking value at K=2 here


def test_lift_at_k_base_rate_is_the_evaluation_sets_own_rate_not_a_constant():
    """base_rate must be recomputed per set -- a population reference
    (e.g. 46.35%) must never leak in as the denominator."""
    y_true_a = np.array([1, 1, 0, 0], dtype=float)  # base_rate 0.5
    y_true_b = np.array([1, 0, 0, 0], dtype=float)  # base_rate 0.25
    y_score = np.array([4, 3, 2, 1], dtype=float)
    assert tr.lift_at_k(y_true_a, y_score, k=0.25)["base_rate"] == pytest.approx(0.5)
    assert tr.lift_at_k(y_true_b, y_score, k=0.25)["base_rate"] == pytest.approx(0.25)


# ---------------------------------------------------------------------------
# Checkpoint 5 -- negative-input tests (D21: every check gets a valid AND
# an invalid case). The finding these were missing: a 4-element delta
# array could silently satisfy a ">=4 of 5" veto condition -- these
# prove that's no longer possible.
# ---------------------------------------------------------------------------

def test_one_se_stats_rejects_wrong_length():
    with pytest.raises(ValueError, match="exactly 5"):
        tr.one_se_stats([1, 2, 3, 4])  # 4, not 5
    with pytest.raises(ValueError, match="exactly 5"):
        tr.one_se_stats([1, 2, 3, 4, 5, 6])  # 6, not 5
    with pytest.raises(ValueError):
        tr.one_se_stats([])


def test_paired_delta_stats_rejects_wrong_length():
    with pytest.raises(ValueError, match="exactly 5"):
        tr.paired_delta_stats([1, 1, 1, 1])  # 4, not 5
    with pytest.raises(ValueError):
        tr.paired_delta_stats([])


def test_guardrail_vetoed_rejects_a_four_element_delta_array():
    """The regression this guards: [1,1,1,1] has n_positive=4, which
    would satisfy a naive ">=4" check even though it isn't "4 of 5" --
    it's 4 of 4. Must raise, not silently veto (or silently not veto)."""
    with pytest.raises(ValueError, match="exactly 5"):
        tr.guardrail_vetoed(
            delta_rmse=[1, 1, 1, 1],           # 4 values, all positive
            delta_abs_bias=[0, 0, 0, 0, 0],    # 5 values
        )


def test_guardrail_vetoed_rejects_mismatched_lengths():
    with pytest.raises(ValueError):
        tr.guardrail_vetoed(
            delta_rmse=[1, 1, 1, 1, 1],        # 5 values
            delta_abs_bias=[0, 0, 0, 0],       # 4 values
        )


def test_conformal_quantile_rejects_empty_input():
    with pytest.raises(ValueError, match="empty"):
        tr.conformal_quantile([], alpha=0.05)


@pytest.mark.parametrize("bad_alpha", [0.0, 1.0, -0.1, 1.5])
def test_conformal_quantile_rejects_alpha_out_of_range(bad_alpha):
    with pytest.raises(ValueError, match="alpha"):
        tr.conformal_quantile([1, 2, 3], alpha=bad_alpha)


def test_top_decile_mask_rejects_empty_input():
    with pytest.raises(ValueError, match="empty"):
        tr.top_decile_mask([])


def test_top_decile_metrics_rejects_mismatched_lengths():
    with pytest.raises(ValueError):
        tr.top_decile_metrics([1, 2, 3], [1, 2])


def test_lift_at_k_rejects_empty_input():
    with pytest.raises(ValueError, match="empty"):
        tr.lift_at_k([], [], k=0.1)


def test_lift_at_k_rejects_mismatched_lengths():
    with pytest.raises(ValueError):
        tr.lift_at_k([1, 0, 1], [3, 2], k=0.1)


@pytest.mark.parametrize("bad_k", [0.0, -0.1, 1.5])
def test_lift_at_k_rejects_k_out_of_range(bad_k):
    with pytest.raises(ValueError, match="k must be"):
        tr.lift_at_k([1, 0, 1, 0], [4, 3, 2, 1], k=bad_k)


def test_lift_at_k_handles_zero_positives_without_crashing():
    """No ValueError -- an all-negative target is a valid evaluation
    set (e.g. a small fold with no positive cases), not malformed
    input. precision_at_k is a well-defined 0.0; lift is None because
    dividing by a zero base_rate is undefined, not because anything
    failed."""
    y_true = np.array([0, 0, 0, 0], dtype=float)
    y_score = np.array([4, 3, 2, 1], dtype=float)
    result = tr.lift_at_k(y_true, y_score, k=0.25)
    assert result["base_rate"] == pytest.approx(0.0)
    assert result["precision_at_k"] == pytest.approx(0.0)
    assert result["lift"] is None


# ---------------------------------------------------------------------------
# Checkpoint 5 -- NaN/±inf must raise, never silently misfire (NaN
# compares False against everything, so an unguarded NaN could make a
# candidate look ineligible, or a veto look unmet, with no error).
# ---------------------------------------------------------------------------

NON_FINITE = [float("nan"), float("inf"), float("-inf")]


@pytest.mark.parametrize("bad", NON_FINITE)
def test_one_se_stats_rejects_non_finite_scores(bad):
    with pytest.raises(ValueError, match="finite"):
        tr.one_se_stats([1, 2, 3, 4, bad])


@pytest.mark.parametrize("bad", NON_FINITE)
def test_one_se_eligible_rejects_non_finite_inputs(bad):
    with pytest.raises(ValueError, match="finite"):
        tr.one_se_eligible(bad, 3.0, 0.5, higher_is_better=True)
    with pytest.raises(ValueError, match="finite"):
        tr.one_se_eligible(3.0, bad, 0.5, higher_is_better=True)
    with pytest.raises(ValueError, match="finite"):
        tr.one_se_eligible(3.0, 3.0, bad, higher_is_better=True)


@pytest.mark.parametrize("bad", NON_FINITE)
def test_paired_delta_stats_rejects_non_finite_deltas(bad):
    with pytest.raises(ValueError, match="finite"):
        tr.paired_delta_stats([1, 1, 1, 1, bad])


@pytest.mark.parametrize("bad", NON_FINITE)
def test_guardrail_vetoed_rejects_non_finite_deltas(bad):
    with pytest.raises(ValueError, match="finite"):
        tr.guardrail_vetoed(
            delta_rmse=[1, 1, 1, 1, bad],
            delta_abs_bias=[0, 0, 0, 0, 0],
        )


@pytest.mark.parametrize("bad", NON_FINITE)
def test_conformal_quantile_rejects_non_finite_residuals(bad):
    with pytest.raises(ValueError, match="finite"):
        tr.conformal_quantile([1, 2, 3, bad], alpha=0.05)


@pytest.mark.parametrize("bad", NON_FINITE)
def test_conformal_interval_rejects_non_finite_inputs(bad):
    with pytest.raises(ValueError, match="finite"):
        tr.conformal_interval(bad, 5.0)
    with pytest.raises(ValueError, match="finite"):
        tr.conformal_interval(100.0, bad)


@pytest.mark.parametrize("bad", NON_FINITE)
def test_top_decile_mask_rejects_non_finite_y_true(bad):
    with pytest.raises(ValueError, match="finite"):
        tr.top_decile_mask([1, 2, 3, bad])


@pytest.mark.parametrize("bad", NON_FINITE)
def test_top_decile_metrics_rejects_non_finite_y_pred(bad):
    with pytest.raises(ValueError, match="finite"):
        tr.top_decile_metrics([1, 2, 3, 4], [1, 2, 3, bad])


@pytest.mark.parametrize("bad", NON_FINITE)
def test_lift_at_k_rejects_non_finite_y_score(bad):
    with pytest.raises(ValueError, match="finite"):
        tr.lift_at_k([1, 0, 1, 0], [1, 2, 3, bad], k=0.25)


def test_require_finite_1d_rejects_non_one_dimensional_input():
    with pytest.raises(ValueError, match="one-dimensional"):
        tr.one_se_stats([[1, 2], [3, 4], [5, 6], [7, 8], [9, 10]])


# ---------------------------------------------------------------------------
# Checkpoint 6 -- read/write_metrics_json (D14): round-trip, determinism,
# allow_nan=False, and no silently-injected volatile fields. Synthetic
# dicts only -- D21 rules out full training in CI, not testing the
# read/write plumbing itself.
# ---------------------------------------------------------------------------

def test_write_metrics_json_round_trip(tmp_path):
    data = {"P2": {"xgboost": {"role": "candidate", "mean_mae": 2.08, "fold_scores_mae": [1, 2, 3]}}}
    path = tmp_path / "metrics.json"
    tr.write_metrics_json(data, path)
    assert tr.read_metrics_json(path) == data


def test_read_metrics_json_returns_empty_dict_when_file_absent(tmp_path):
    assert tr.read_metrics_json(tmp_path / "does_not_exist.json") == {}


def test_write_metrics_json_is_deterministic_byte_for_byte(tmp_path):
    """Same content in a different dict insertion order must still
    produce byte-identical output (sort_keys) -- a re-run from the same
    CSV must reproduce the file exactly (checkpoint 6's own real-CSV
    determinism check relies on this)."""
    data_a = {"P2": {"linear": {"role": "baseline", "fold_scores_mae": [1.0, 2.0]}}}
    data_b = {"P2": {"linear": {"fold_scores_mae": [1.0, 2.0], "role": "baseline"}}}
    path_a, path_b = tmp_path / "a.json", tmp_path / "b.json"
    tr.write_metrics_json(data_a, path_a)
    tr.write_metrics_json(data_b, path_b)
    assert path_a.read_bytes() == path_b.read_bytes()


def test_write_metrics_json_rejects_nan(tmp_path):
    data = {"P2": {"xgboost": {"mean_mae": float("nan")}}}
    with pytest.raises(ValueError):
        tr.write_metrics_json(data, tmp_path / "out.json")


def test_write_metrics_json_never_injects_volatile_fields(tmp_path):
    """metrics.json must stay purely deterministic content -- D14
    requires volatile facts (timestamp, git sha, RSS, run time) to live
    in run_metadata.json instead, never here. Locks that
    write_metrics_json itself never silently adds any of them."""
    data = {
        "P2": {
            "xgboost": {
                "role": "candidate",
                "fold_scores_mae": [1.0, 2.0, 3.0, 4.0, 5.0],
                "mean_mae": 3.0,
                "best_params": {"model__max_depth": 4},
            },
        }
    }
    path = tmp_path / "metrics.json"
    tr.write_metrics_json(data, path)
    assert tr.read_metrics_json(path) == data  # nothing added, nothing dropped

    text = path.read_text(encoding="utf-8").lower()
    for term in ("timestamp", "git_sha", "git sha", "rss", "run_time", "runtime", "duration"):
        assert term not in text, f"unexpected volatile field marker {term!r} in metrics.json"


# ---------------------------------------------------------------------------
# Checkpoint 6 -- _metric_summary known-answer test: mean/std/se all
# hand-verified, and std != se (std = se * sqrt(5)), for both a
# negated scorer (mae, rmse) and one that isn't (r2).
# ---------------------------------------------------------------------------

def test_metric_summary_known_answer_mean_std_se_and_sign_correction():
    fold_scores = {
        "mae": [-1, -2, -3, -4, -5],      # negated -> natural [1,2,3,4,5]
        "rmse": [-2, -3, -4, -5, -6],     # negated -> natural [2,3,4,5,6]
        "r2": [10, 20, 30, 40, 50],       # not negated -- left as-is
    }
    result = tr._metric_summary(fold_scores, role="candidate", best_params={"x": 1})

    assert result["role"] == "candidate"
    assert result["best_params"] == {"x": 1}

    assert result["fold_scores_mae"] == [1, 2, 3, 4, 5]
    assert result["mean_mae"] == pytest.approx(3.0)
    assert result["std_mae"] == pytest.approx(1.5811388300841898)
    assert result["se_mae"] == pytest.approx(0.7071067811865476)

    assert result["fold_scores_rmse"] == [2, 3, 4, 5, 6]
    assert result["mean_rmse"] == pytest.approx(4.0)
    assert result["std_rmse"] == pytest.approx(1.5811388300841898)
    assert result["se_rmse"] == pytest.approx(0.7071067811865476)

    # r2 is NOT sign-corrected -- stored exactly as given.
    assert result["fold_scores_r2"] == [10, 20, 30, 40, 50]
    assert result["mean_r2"] == pytest.approx(30.0)
    assert result["std_r2"] == pytest.approx(15.811388300841896)
    assert result["se_r2"] == pytest.approx(7.071067811865475)

    # std and se are genuinely different numbers -- std = se * sqrt(5).
    assert result["std_mae"] == pytest.approx(result["se_mae"] * math.sqrt(5))
    assert result["std_mae"] != pytest.approx(result["se_mae"])


# ---------------------------------------------------------------------------
# Checkpoint 7 -- the P3 pieces that involve zero model fitting: the
# class-weight ratio formula, the manual rules (D11), and the lift
# scorer wrapper. train_p3/train_p3_weighted_comparison (real
# RandomizedSearchCV/cross_validate fits) stay local-only per D21, same
# precedent as train_p2 in checkpoint 6.
# ---------------------------------------------------------------------------

def test_p3_class_weight_ratio_known_answer():
    y = pd.Series([1, 1, 0, 0, 0])  # 2 positive, 3 negative
    assert tr._p3_class_weight_ratio(y) == pytest.approx(3 / 2)


def test_p3_class_weight_ratio_matches_train_set_counts(df):
    """Checked against the train set's own class counts, independently
    recomputed -- not assumed from the population's 20/20 balance,
    which a stratified split of a 24-or-25-row train set can't
    preserve exactly after two rounds of rounding."""
    train_df = tr.build_task_train_frame(df, "P3")
    y = train_df[tr.TARGET["P3"]]
    expected = (y == 0).sum() / (y == 1).sum()
    assert tr._p3_class_weight_ratio(y) == pytest.approx(expected)


def test_lift_at_10_score_func_matches_lift_at_k(df):
    y_true = np.array([1, 0, 1, 0, 1, 0, 1, 0, 1, 0], dtype=float)
    y_score = np.array([10, 9, 1, 2, 3, 4, 5, 6, 7, 8], dtype=float)
    expected = tr.lift_at_k(y_true, y_score, k=0.1)["lift"]
    assert tr._lift_at_10_score_func(y_true, y_score) == pytest.approx(expected)


def test_train_p3_brief_rule_thresholds_are_train_medians(df):
    """Zero-fit rule -- no model.fit() anywhere in this path, so this
    runs the real function end to end on the synthetic fixture (not a
    training smoke test D21 would rule out)."""
    train_df = tr.build_task_train_frame(df, "P3")
    rule = tr.train_p3_brief_rule(df)

    assert "description" in rule
    assert "thresholds" in rule
    for metric in ("roc_auc", "accuracy", "precision", "recall", "f1"):
        assert f"fold_scores_{metric}" in rule
        assert len(rule[f"fold_scores_{metric}"]) == 5
        assert f"mean_{metric}" in rule
        assert f"std_{metric}" in rule

    assert rule["thresholds"]["ltv_months_gt"] == pytest.approx(train_df["ltv_months"].median())
    assert rule["thresholds"]["customer_acquisition_cost_lt"] == pytest.approx(
        train_df["customer_acquisition_cost"].median()
    )


def test_train_p3_brief_rule_predictions_match_the_and_condition(df):
    """Directly recomputes the brief rule's prediction from the raw
    columns and thresholds, independent of train_p3_brief_rule's own
    internals -- proves the AND condition is what's actually scored,
    not just that some plausible-looking numbers came out."""
    train_df = tr.build_task_train_frame(df, "P3")
    y = train_df[tr.TARGET["P3"]].to_numpy()
    folds = tr.build_folds(df, "P3")

    rule = tr.train_p3_brief_rule(df)
    ltv_t = rule["thresholds"]["ltv_months_gt"]
    cac_t = rule["thresholds"]["customer_acquisition_cost_lt"]
    pred = ((train_df["ltv_months"] > ltv_t) & (train_df["customer_acquisition_cost"] < cac_t)).to_numpy().astype(int)

    expected = tr._p3_rule_fold_metrics(y, pred, folds)
    assert rule["fold_scores_accuracy"] == expected["fold_scores_accuracy"]
    assert rule["mean_roc_auc"] == pytest.approx(expected["mean_roc_auc"])


def test_train_p3_operational_rule_rejects_a_non_p3_feature(df):
    with pytest.raises(ValueError, match="FEATURES\\['P3'\\]"):
        tr.train_p3_operational_rule(df, feature="ltv_months", direction="gt")


def test_train_p3_operational_rule_rejects_a_bad_direction(df):
    with pytest.raises(ValueError, match="direction"):
        tr.train_p3_operational_rule(df, feature="closed", direction="up")


def test_train_p3_operational_rule_uses_the_given_feature_and_direction(df):
    """The chosen feature/direction actually drive the prediction --
    checked against an independently recomputed AND condition, both
    for 'gt' and 'lt', not just that the function runs."""
    train_df = tr.build_task_train_frame(df, "P3")
    y = train_df[tr.TARGET["P3"]].to_numpy()
    folds = tr.build_folds(df, "P3")
    cac_t = float(train_df["customer_acquisition_cost"].median())

    for feature, direction, op in [("closed", "gt", "__gt__"), ("not_closed", "lt", "__lt__")]:
        rule = tr.train_p3_operational_rule(df, feature=feature, direction=direction)
        feature_t = rule["thresholds"][f"{feature}_{direction}"]
        assert feature_t == pytest.approx(train_df[feature].median())

        feature_cond = getattr(train_df[feature], op)(feature_t)
        expected_pred = (feature_cond & (train_df["customer_acquisition_cost"] < cac_t)).to_numpy().astype(int)
        expected = tr._p3_rule_fold_metrics(y, expected_pred, folds)
        assert rule["fold_scores_accuracy"] == expected["fold_scores_accuracy"]


# ---------------------------------------------------------------------------
# Checkpoint 8 -- the P4 piece that involves zero model fitting: the
# clone-safety of make_p4_boosters' CatBoost estimator. train_p4 (real
# fits) stays local-only per D21, same precedent as train_p2/train_p3.
# ---------------------------------------------------------------------------

def test_make_p4_boosters_catboost_is_clone_safe():
    """cat_features must NOT be in the constructor -- CatBoostClassifier
    (cat_features=[...]) breaks sklearn's clone() (verified empirically
    before writing train_p4: RuntimeError, "constructor either does
    not set or modifies parameter cat_features"), which
    RandomizedSearchCV and Pipeline both call internally. It's passed
    at fit() time instead, via train_p4's fit_params."""
    from sklearn.base import clone

    estimator, param_distributions = tr.make_p4_boosters()["catboost"]
    assert "cat_features" not in estimator.get_params()
    clone(estimator)  # must not raise
    assert param_distributions == tr.catboost_param_distributions()


def test_p4_cat_features_index_matches_model_feature_columns_length():
    """train_p4 points CatBoost's cat_features at the position right
    after P4's numeric columns in build_preprocessing_steps' output --
    this is exactly len(model_feature_columns("P4")), the same count
    checkpoint 4's pipeline-shape tests already pin down."""
    n_numeric = len(tr.model_feature_columns("P4"))
    assert n_numeric == 13  # 14 FEATURES["P4"] minus leads_not_answered (D4)
