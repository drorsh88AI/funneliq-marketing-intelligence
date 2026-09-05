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


# ---------------------------------------------------------------------------
# Checkpoint 9 -- P6 search + paired guardrail crossover (D7). Pure/
# mechanical pieces only (D21): _Winsorizer's fit/transform contract,
# build_preprocessing_steps(winsorize=True)'s structure, and
# make_p6_boosters' locked objective params + clone-safety. train_p6 and
# train_p6_guardrail (real fits) stay local-only, same precedent as
# train_p2/train_p3/train_p4.
# ---------------------------------------------------------------------------

def test_winsorizer_fit_computes_column_wise_p1_p99_from_the_given_rows():
    train = pd.DataFrame({"a": list(range(100)), "b": list(range(100, 200))})
    w = tr._Winsorizer(columns=["a", "b"])
    w.fit(train)
    assert w.bounds_["a"] == (train["a"].quantile(0.01), train["a"].quantile(0.99))
    assert w.bounds_["b"] == (train["b"].quantile(0.01), train["b"].quantile(0.99))


def test_winsorizer_transform_clips_to_the_fitted_bounds_not_a_recomputation():
    """The bounds come from fit()'s rows only -- transform() applies
    them unchanged to whatever it's given, even values far outside what
    fit() ever saw. This is the fold-isolation contract D7/D8א require:
    a validation fold's own extreme values must never widen the bounds
    learned from its fold's training rows."""
    train = pd.DataFrame({"a": list(range(100))})  # p1~0.99, p99~98.01
    w = tr._Winsorizer(columns=["a"]).fit(train)
    lo, hi = w.bounds_["a"]

    val = pd.DataFrame({"a": [-1000, 0, 50, 99, 1000]})
    out = w.transform(val)
    assert out["a"].iloc[0] == lo   # far below train's p1 -> clipped to train's bound
    assert out["a"].iloc[1] == lo   # 0 is also below lo here -> clipped
    assert out["a"].iloc[2] == 50   # inside bounds -> unchanged
    assert out["a"].iloc[3] == hi   # above train's p99 -> clipped to train's bound
    assert out["a"].iloc[4] == hi   # far above -> clipped to the same bound, not re-fit
    assert w.bounds_["a"] == (lo, hi)  # transform never mutates bounds_


def test_winsorizer_transform_does_not_mutate_the_input_frame():
    train = pd.DataFrame({"a": [1, 2, 3, 1000]})
    w = tr._Winsorizer(columns=["a"]).fit(train)
    before = train.copy()
    w.transform(train)
    pd.testing.assert_frame_equal(train, before)


def test_build_preprocessing_steps_winsorize_true_adds_a_winsorize_step_before_select():
    steps = tr.build_preprocessing_steps("P6", encode_budget_tier=False, winsorize=True)
    assert [name for name, _ in steps] == ["winsorize", "select"]
    winsorizer = dict(steps)["winsorize"]
    assert isinstance(winsorizer, tr._Winsorizer)
    assert winsorizer.columns == tr.model_feature_columns("P6")


def test_build_preprocessing_steps_winsorize_false_is_unchanged_from_before():
    """Regression guard: adding the winsorize parameter must not alter
    the default (or explicit False) behavior every other task/checkpoint
    already depends on."""
    default_steps = tr.build_preprocessing_steps("P6", encode_budget_tier=False)
    explicit_false_steps = tr.build_preprocessing_steps("P6", encode_budget_tier=False, winsorize=False)
    assert [name for name, _ in default_steps] == ["select"]
    assert [name for name, _ in explicit_false_steps] == ["select"]


def test_make_p6_boosters_has_the_four_locked_candidates():
    boosters = tr.make_p6_boosters()
    assert set(boosters) == {"p6_1_reference", "p6_2_tweedie", "p6_3_huber", "p6_5_winsorized"}
    for name, (_, param_distributions, winsorize) in boosters.items():
        assert param_distributions == tr.xgboost_param_distributions()
        assert winsorize == (name == "p6_5_winsorized")


def test_make_p6_boosters_objectives_match_spec_and_are_locked_not_searched():
    boosters = tr.make_p6_boosters()
    assert boosters["p6_1_reference"][0].get_params()["objective"] == "reg:squarederror"
    tweedie = boosters["p6_2_tweedie"][0].get_params()
    assert tweedie["objective"] == "reg:tweedie"
    assert tweedie["tweedie_variance_power"] == 1.5
    huber = boosters["p6_3_huber"][0].get_params()
    assert huber["objective"] == "reg:pseudohubererror"
    assert huber["huber_slope"] == 1.0
    assert boosters["p6_5_winsorized"][0].get_params()["objective"] == "reg:squarederror"
    # None of the locked objective params are search axes.
    for param_distributions in (tr.xgboost_param_distributions(),):
        assert "model__objective" not in param_distributions
        assert "model__tweedie_variance_power" not in param_distributions
        assert "model__huber_slope" not in param_distributions


def test_make_p6_boosters_estimators_are_clone_safe():
    """Verified empirically before writing train_p6_guardrail (which
    clones each of these): unlike CatBoost's cat_features (checkpoint
    8), none of XGBoost's tweedie_variance_power/huber_slope break
    clone()."""
    from sklearn.base import clone
    for estimator, _, _ in tr.make_p6_boosters().values():
        clone(estimator)  # must not raise


def test_p6_experimental_variants_excludes_the_reference():
    """The guardrail veto's scope is explicitly limited to the 3
    experimental variants (SPEC.md § מקבילת ההשוואה) -- p6_1_reference
    IS the generic comparator and is never vetoed against itself."""
    assert "p6_1_reference" not in tr.P6_EXPERIMENTAL_VARIANTS
    assert set(tr.P6_EXPERIMENTAL_VARIANTS) == {"p6_2_tweedie", "p6_3_huber", "p6_5_winsorized"}


def test_train_p6_guardrail_pairs_each_variant_against_a_single_change_comparator(df, monkeypatch):
    """The wiring test the earlier round of tests was missing: every
    other checkpoint-9 test above checks a building block in isolation
    (_Winsorizer, build_preprocessing_steps, make_p6_boosters) but none
    of them prove train_p6_guardrail itself assembles those blocks
    correctly. This one calls the REAL train_p6_guardrail, with
    _p6_fold_top_decile monkeypatched to a recording fake (avoiding a
    real XGBoost fit, per D21 -- train_p6_guardrail's actual fits stay
    local-only) so every call's estimator/preprocessing/folds/population
    argument is captured and can be asserted on directly, and proves
    for every experimental variant:
      - the SAME 5 folds and the SAME train population feed both arms
        (and the reference's own call);
      - the comparator is reg:squarederror with the VARIANT's winning
        hyperparameters (not the reference's, not its own tuned set);
      - preprocessing differs ONLY by the winsorize step, and only for
        p6_5_winsorized -- p6_2_tweedie/p6_3_huber's comparator uses
        the identical (non-winsorized) steps as their own variant arm;
      - delta_rmse/delta_abs_bias are computed as variant MINUS
        comparator (not the reverse) and are exactly what reaches
        guardrail_vetoed.
    """
    calls: list[dict] = []

    def fake_top_decile(estimator, preprocessing_steps, train_df, y, folds):
        calls.append({
            "params": estimator.get_params(),
            "step_names": [name for name, _ in preprocessing_steps],
            "train_df_id": id(train_df),
            "y_id": id(y),
            "folds_id": id(folds),
        })
        call_no = len(calls)  # 1-indexed: this call's position in the sequence
        return [{"rmse_top10": 100.0 * call_no + i, "bias_top10": 10.0 * call_no - i, "k": 1} for i in range(5)]

    monkeypatch.setattr(tr, "_p6_fold_top_decile", fake_top_decile)

    winning_params = {"model__learning_rate": 0.1, "model__max_depth": 3, "model__n_estimators": 50}
    p6_results = {name: {"best_params": dict(winning_params)} for name in tr.make_p6_boosters()}

    result = tr.train_p6_guardrail(df, p6_results)

    # Call order is fixed by train_p6_guardrail's own code: reference
    # first (1 call), then each experimental variant (variant arm, then
    # comparator arm) in P6_EXPERIMENTAL_VARIANTS order.
    assert len(calls) == 1 + 2 * len(tr.P6_EXPERIMENTAL_VARIANTS) == 7

    ref_call = calls[0]
    assert ref_call["step_names"] == ["select"]
    assert ref_call["params"]["objective"] == "reg:squarederror"

    expected_objective = {"p6_2_tweedie": "reg:tweedie", "p6_3_huber": "reg:pseudohubererror", "p6_5_winsorized": "reg:squarederror"}
    expected_variant_steps = {"p6_2_tweedie": ["select"], "p6_3_huber": ["select"], "p6_5_winsorized": ["winsorize", "select"]}

    for i, name in enumerate(tr.P6_EXPERIMENTAL_VARIANTS):
        variant_call = calls[1 + 2 * i]
        comparator_call = calls[2 + 2 * i]

        # Same population and same 5 folds in every arm, including the reference's.
        for call in (variant_call, comparator_call):
            assert call["folds_id"] == ref_call["folds_id"]
            assert call["train_df_id"] == ref_call["train_df_id"]
            assert call["y_id"] == ref_call["y_id"]

        # Preprocessing: identical for both arms, except p6_5_winsorized's variant arm.
        assert variant_call["step_names"] == expected_variant_steps[name]
        assert comparator_call["step_names"] == ["select"]

        # Objective: variant keeps its own locked objective; comparator is
        # ALWAYS reg:squarederror -- the single-change discipline (D7).
        assert variant_call["params"]["objective"] == expected_objective[name]
        assert comparator_call["params"]["objective"] == "reg:squarederror"

        # Hyperparameters: BOTH arms get the variant's own winning
        # hyperparameters (never the reference's, never re-tuned).
        for call in (variant_call, comparator_call):
            assert call["params"]["learning_rate"] == 0.1
            assert call["params"]["max_depth"] == 3
            assert call["params"]["n_estimators"] == 50

        # delta = variant - comparator, computed from the fake's
        # call-order-dependent values -- proves the subtraction isn't
        # reversed, not just that some numbers came out.
        v_call_no, c_call_no = 2 + 2 * i, 3 + 2 * i  # 1-indexed call numbers
        expected_delta_rmse = [100.0 * v_call_no - 100.0 * c_call_no] * 5
        expected_delta_abs_bias = [
            abs(10.0 * v_call_no - k) - abs(10.0 * c_call_no - k) for k in range(5)
        ]
        assert result[name]["delta_rmse_per_fold"] == expected_delta_rmse
        assert result[name]["delta_abs_bias_per_fold"] == expected_delta_abs_bias

        # And those exact deltas are what reached the veto -- not a
        # recomputation, not a different pair of arrays.
        assert result[name]["veto"] == tr.guardrail_vetoed(expected_delta_rmse, expected_delta_abs_bias)

    # The reference's own (unpaired) top-decile metrics are reported
    # verbatim from its single call, with no comparator and no veto key.
    assert result["p6_1_reference"]["top_decile_per_fold"] == [
        {"rmse_top10": 100.0 + i, "bias_top10": 10.0 - i, "k": 1} for i in range(5)
    ]
    assert "veto" not in result["p6_1_reference"]


# ---------------------------------------------------------------------------
# Checkpoint 10 -- One-SE eligibility, the paired guardrail's
# step-ג' removal, and the winner tie-break: all pure decision
# functions over synthetic {mean_*, std_*, se_*, role} dicts, no real
# fit involved (D21). build_fitted_candidate/measure_rss_and_predict_time
# /lock_winner do real fits + spawn a subprocess and stay local-only,
# same precedent as every other train_pX function.
# ---------------------------------------------------------------------------

def test_eligible_candidates_higher_is_better_uses_the_best_models_se():
    results = {
        "best": {"role": "candidate", "mean_roc_auc": 0.80, "se_roc_auc": 0.02},
        "within_one_se": {"role": "candidate", "mean_roc_auc": 0.79, "se_roc_auc": 0.005},
        "outside_one_se": {"role": "candidate", "mean_roc_auc": 0.77, "se_roc_auc": 0.005},
        "dummy": {"role": "benchmark", "mean_roc_auc": 0.99, "se_roc_auc": 0.0},
    }
    eligible = tr.eligible_candidates(results, "roc_auc", higher_is_better=True)
    assert set(eligible) == {"best", "within_one_se"}  # dummy excluded regardless of its mean


def test_eligible_candidates_lower_is_better_uses_the_best_models_se():
    results = {
        "best": {"role": "candidate", "mean_mae": 2.00, "se_mae": 0.10},
        "within_one_se": {"role": "baseline", "mean_mae": 2.05, "se_mae": 0.03},
        "outside_one_se": {"role": "candidate", "mean_mae": 2.20, "se_mae": 0.03},
        "dummy": {"role": "benchmark", "mean_mae": 0.50, "se_mae": 0.0},
    }
    eligible = tr.eligible_candidates(results, "mae", higher_is_better=False)
    assert set(eligible) == {"best", "within_one_se"}


def test_p6_deployable_results_removes_only_vetoed_variants():
    p6_results = {name: {"role": "candidate"} for name in tr.make_p6_boosters()}
    p6_results["dummy"] = {"role": "benchmark"}
    p6_results["linear"] = {"role": "baseline"}
    p6_guardrail = {
        "p6_2_tweedie": {"veto": {"vetoed": True}},
        "p6_3_huber": {"veto": {"vetoed": False}},
        "p6_5_winsorized": {"veto": {"vetoed": False}},
    }
    deployable = tr.p6_deployable_results(p6_results, p6_guardrail)
    assert set(deployable) == {"p6_1_reference", "p6_3_huber", "p6_5_winsorized", "dummy", "linear"}
    assert "p6_2_tweedie" not in deployable


def test_select_winner_baseline_wins_outright_when_eligible():
    """Simplicity beats any Boosting score -- the eligible baseline is
    picked even though a candidate has a far better std/RSS/time."""
    eligible = {
        "booster": {"role": "candidate", "std_roc_auc": 0.001},
        "baseline": {"role": "baseline", "std_roc_auc": 0.5},
    }
    rss_bytes = {"booster": 1, "baseline": 999_999_999}
    predict_seconds = {"booster": 0.0001, "baseline": 10.0}
    assert tr.select_winner(eligible, "roc_auc", rss_bytes, predict_seconds) == "baseline"


def test_select_winner_breaks_ties_by_std_then_rss_then_predict_time():
    # (a) distinct std -> lowest std wins even with worse RSS/time.
    eligible = {
        "a": {"role": "candidate", "std_rmse": 1.0},
        "b": {"role": "candidate", "std_rmse": 2.0},
    }
    rss = {"a": 999, "b": 1}
    ms = {"a": 999.0, "b": 0.1}
    assert tr.select_winner(eligible, "rmse", rss, ms) == "a"

    # (b) tied std -> lowest RSS wins.
    eligible = {
        "a": {"role": "candidate", "std_rmse": 1.0},
        "b": {"role": "candidate", "std_rmse": 1.0},
    }
    rss = {"a": 500, "b": 100}
    ms = {"a": 0.001, "b": 999.0}
    assert tr.select_winner(eligible, "rmse", rss, ms) == "b"

    # (c) tied std AND RSS -> lowest predict time wins.
    eligible = {
        "a": {"role": "candidate", "std_rmse": 1.0},
        "b": {"role": "candidate", "std_rmse": 1.0},
    }
    rss = {"a": 100, "b": 100}
    ms = {"a": 5.0, "b": 0.5}
    assert tr.select_winner(eligible, "rmse", rss, ms) == "b"


def test_rss_measurement_script_is_valid_python_syntax():
    """Never executed in CI (Windows ctypes/psapi + a real fitted
    pipeline, both local-only per D19/D21) -- but a typo in this
    string would otherwise only surface the next time someone runs
    checkpoint 10 for real."""
    compile(tr._RSS_MEASUREMENT_SCRIPT, "<_RSS_MEASUREMENT_SCRIPT>", "exec")


def test_lock_winner_orchestrates_build_measure_then_select(df, monkeypatch, tmp_path):
    """The wiring test the other checkpoint-10 tests above don't cover:
    they each check eligible_candidates/p6_deployable_results/select_winner
    in isolation, but none of them prove lock_winner itself calls them
    together correctly. build_fitted_candidate and
    measure_rss_and_predict_time are monkeypatched (no real fit, per
    D21) to a call-recording fake; build_task_train_frame is left real
    (pure pandas, already covered elsewhere, zero fit involved) so
    lock_winner's own df/task plumbing runs for real. Proves:
      - exactly the One-SE eligible names are built and measured, each
        exactly once -- not the ineligible candidate, not the benchmark;
      - every eligible candidate's build+measure happens BEFORE
        select_winner is even called (D19, criterion 6: measured for
        every eligible candidate, not only whichever pair is tied);
      - for P6, `results` is passed straight through to
        build_fitted_candidate untouched -- lock_winner does not
        re-apply the guardrail itself, that's p6_deployable_results'
        job in the caller, before lock_winner ever sees the dict;
      - the returned eligible/winner/rss_bytes/predict_seconds match
        exactly what the fakes produced.
    """
    results = {
        "best": {"role": "candidate", "mean_rmse": 5.0, "se_rmse": 0.1, "std_rmse": 0.2},
        "within_one_se": {"role": "candidate", "mean_rmse": 5.05, "se_rmse": 0.01, "std_rmse": 0.3},
        "outside_one_se": {"role": "candidate", "mean_rmse": 10.0, "se_rmse": 0.01, "std_rmse": 0.01},
        "dummy": {"role": "benchmark", "mean_rmse": 0.1, "se_rmse": 0.0, "std_rmse": 0.0},
    }
    results_snapshot = {k: dict(v) for k, v in results.items()}
    events: list[tuple[str, str]] = []

    def fake_build(task, name, res, given_df):
        assert task == "P6"
        assert res is results  # straight through, not re-filtered by lock_winner
        assert given_df is df
        events.append(("build", name))
        return f"pipeline:{name}"

    def fake_measure(pipeline, sample, tmp_dir_arg):
        assert tmp_dir_arg == tmp_path
        name = pipeline.split(":", 1)[1]
        events.append(("measure", name))
        return {"rss_bytes": 1000 + len(name), "predict_seconds": 0.001 * len(name)}

    def fake_select_winner(eligible, primary_metric, rss_bytes, predict_seconds):
        events.append(("select", ""))
        # every eligible candidate must already be measured by now
        assert set(eligible) == set(rss_bytes) == set(predict_seconds)
        return "within_one_se"

    monkeypatch.setattr(tr, "build_fitted_candidate", fake_build)
    monkeypatch.setattr(tr, "measure_rss_and_predict_time", fake_measure)
    monkeypatch.setattr(tr, "select_winner", fake_select_winner)

    result = tr.lock_winner("P6", df, results, tmp_path)

    # exactly the One-SE eligible names, each built and measured exactly once
    built_names = [n for op, n in events if op == "build"]
    measured_names = [n for op, n in events if op == "measure"]
    assert built_names == ["best", "within_one_se"]
    assert measured_names == ["best", "within_one_se"]

    # select_winner only runs after every eligible candidate is measured
    assert events[-1] == ("select", "")
    assert [op for op, _ in events[:-1]] == ["build", "measure", "build", "measure"]

    # lock_winner must not mutate or re-filter what it was given
    assert {k: dict(v) for k, v in results.items()} == results_snapshot

    assert result["eligible"] == ["best", "within_one_se"]
    assert result["winner"] == "within_one_se"
    assert result["rss_bytes"] == {"best": 1000 + len("best"), "within_one_se": 1000 + len("within_one_se")}
    assert result["predict_seconds"] == {"best": 0.001 * len("best"), "within_one_se": 0.001 * len("within_one_se")}


# ---------------------------------------------------------------------------
# Checkpoint 11 -- P3/P4 sigmoid calibration (D10) + P2's Split
# Conformal quantile (D9). build_task_calibration_frame is pure pandas
# (CI-safe, like build_task_train_frame). fit_sigmoid_calibrator does a
# real (but cheap -- LogisticRegression, not a real booster) fit, so
# its success/failure branches are tested directly with real sklearn
# behavior. calibrate_task_winner/train_p2_conformal call
# build_fitted_candidate, which fits an expensive real booster -- kept
# local-only (D21) except for an orchestration test per candidate that
# monkeypatches build_fitted_candidate to a CHEAP-but-real stand-in
# (same build_preprocessing_steps/build_task_train_frame plumbing,
# LogisticRegression/LinearRegression instead of the real booster) so
# the calibration/conformal machinery itself still runs for real
# against the real calibration split.
# ---------------------------------------------------------------------------

def test_build_task_calibration_frame_matches_split_task_calibration_ids(df):
    for task in ("P2", "P3", "P4"):
        cal_df = tr.build_task_calibration_frame(df, task)
        parts = tr.split_task(df, task)
        assert set(cal_df["source_row_id"]) == set(parts["calibration"])
        assert list(cal_df.index) == list(range(len(cal_df)))


def test_build_task_calibration_frame_rejects_p6():
    with pytest.raises(ValueError):
        tr.build_task_calibration_frame(pd.DataFrame({"source_row_id": []}), "P6")


def test_fit_sigmoid_calibrator_reports_calibrated_on_success():
    rng = np.random.default_rng(1)
    X = pd.DataFrame({"a": rng.random(40), "b": rng.random(40)})
    y = (X["a"] > 0.5).astype(int)
    pipeline = tr.LogisticRegression().fit(X, y)

    result = tr.fit_sigmoid_calibrator(pipeline, X, y)
    assert result["calibration_status"] == "calibrated"
    assert result["calibration_method"] == "sigmoid"
    assert result["calibrator"] is not None
    assert result["calibrator"].predict_proba(X).shape == (40, 2)


def test_fit_sigmoid_calibrator_reports_uncalibrated_on_a_real_failure():
    """A single-class calibration target is a genuine sklearn failure
    (verified empirically before writing fit_sigmoid_calibrator) --
    not simulated, to prove the except branch catches the REAL
    exception type CalibratedClassifierCV actually raises."""
    rng = np.random.default_rng(1)
    X = pd.DataFrame({"a": rng.random(40), "b": rng.random(40)})
    pipeline = tr.LogisticRegression().fit(X, (X["a"] > 0.5).astype(int))  # fitted on 2 classes

    y_single_class = pd.Series([0] * 40)
    result = tr.fit_sigmoid_calibrator(pipeline, X, y_single_class)
    assert result["calibration_status"] == "uncalibrated"
    assert result["calibration_method"] == "sigmoid"
    assert result["calibrator"] is None
    assert "error" in result and result["error"]  # the real exception message, not swallowed


def _fake_cheap_classifier_pipeline(task, name, results, given_df):
    """Stands in for build_fitted_candidate in checkpoint-11
    orchestration tests: a REAL fit, using the SAME preprocessing
    plumbing (build_preprocessing_steps/build_task_train_frame) a real
    candidate would use, with LogisticRegression swapped in for the
    expensive booster -- so the returned Pipeline is shaped exactly
    like what CalibratedClassifierCV will later see on the real
    calibration frame, without ever fitting a real booster (D21)."""
    steps = tr.build_preprocessing_steps(task, encode_budget_tier=(task == "P4"))
    pipeline = tr.Pipeline(steps + [("model", tr.LogisticRegression(max_iter=1000))])
    train_df = tr.build_task_train_frame(given_df, task)
    y_train = tr.encode_referred_target(train_df[tr.TARGET[task]]) if task == "P4" else train_df[tr.TARGET[task]]
    pipeline.fit(train_df, y_train)
    return pipeline


def _synthetic_calibration_frame(task: str, n_per_class: int = 15) -> pd.DataFrame:
    """A calibration-shaped frame big enough for CalibratedClassifierCV's
    default cv=5 (needs >=5 members per class even with a FrozenEstimator
    -- verified empirically: it still runs cross_val_predict internally
    to gather held-out-style predictions). The real calibration splits
    are 506 rows; the shared 60-row fixture's own calibration split (7
    rows) is realistic for split-size tests but too small for a real
    sigmoid fit, so this orchestration test supplies its own."""
    rng = np.random.default_rng(42)
    cols = tr.model_feature_columns(task)
    n = n_per_class * 2
    data = {c: rng.random(n) * 100 for c in cols}
    data[tr.TARGET[task]] = (["Yes"] * n_per_class + ["No"] * n_per_class) if task == "P4" else ([1] * n_per_class + [0] * n_per_class)
    return pd.DataFrame(data)


def test_calibrate_task_winner_wires_the_right_split_and_target_encoding(df, monkeypatch):
    for task in ("P3", "P4"):
        calls = []
        fake_results = {"stub": {"role": "candidate"}}
        fake_cal_df = _synthetic_calibration_frame(task)

        def fake_build(t, name, res, given_df, _calls=calls):
            _calls.append((t, name, res is fake_results, given_df is df))
            return _fake_cheap_classifier_pipeline(t, name, res, given_df)

        def fake_calibration_frame(given_df, t, _fake_cal_df=fake_cal_df):
            assert given_df is df
            return _fake_cal_df

        monkeypatch.setattr(tr, "build_fitted_candidate", fake_build)
        monkeypatch.setattr(tr, "build_task_calibration_frame", fake_calibration_frame)

        result = tr.calibrate_task_winner(task, df, fake_results, "stub")

        assert calls == [(task, "stub", True, True)]  # called once, with the exact args given
        assert result["winner"] == "stub"
        assert result["calibration_status"] == "calibrated"
        assert result["calibration_method"] == "sigmoid"
        assert result["calibrator"] is not None


def test_train_p2_conformal_computes_the_quantile_from_calibration_residuals(df, monkeypatch):
    calls = []
    fake_results = {"stub": {"role": "candidate"}}

    def fake_build_p2(task, name, res, given_df):
        calls.append((task, name, res is fake_results, given_df is df))
        steps = tr.build_preprocessing_steps("P2", encode_budget_tier=False)
        pipeline = tr.Pipeline(steps + [("model", tr.LinearRegression())])
        train_df = tr.build_task_train_frame(given_df, "P2")
        pipeline.fit(train_df, train_df[tr.TARGET["P2"]])
        return pipeline

    monkeypatch.setattr(tr, "build_fitted_candidate", fake_build_p2)

    result = tr.train_p2_conformal(df, fake_results, "stub")

    assert calls == [("P2", "stub", True, True)]
    assert result["winner"] == "stub"
    assert result["alpha"] == 0.05

    # Recompute independently through the same (deterministic) fake
    # pipeline + the real calibration frame -- proves the returned q is
    # the wiring's actual output, not just some float.
    independent_pipeline = fake_build_p2("P2", "stub", fake_results, df)
    cal_df = tr.build_task_calibration_frame(df, "P2")
    expected_residuals = cal_df[tr.TARGET["P2"]].to_numpy() - independent_pipeline.predict(cal_df)
    expected_q = tr.conformal_quantile(expected_residuals, alpha=0.05)
    assert result["q"] == pytest.approx(expected_q)


# ---------------------------------------------------------------------------
# Checkpoint 12 -- P6 Bootstrap (D8), exact-budget profiles (D8א), the
# four locked spending strategies, and the lookup table. strategy_totals/
# compute_budget_profiles/simulate_strategies are pure (CI-safe, no fit
# involved at all). p6_bootstrap_simulation calls build_fitted_candidate
# (a real fit) B+1 times -- kept local-only (D21) except for an
# orchestration test (written proactively, following checkpoints 9-11's
# established pattern) that monkeypatches build_fitted_candidate AND
# build_task_train_frame to a cheap deterministic stand-in.
# ---------------------------------------------------------------------------

def test_strategy_totals_all_equal_50000():
    assert tr.strategy_totals() == {name: 50_000 for name in tr.STRATEGY_ALLOCATIONS}


def test_compute_budget_profiles_computes_median_per_exact_level_and_flags_unavailable():
    cols = list(tr.DERIVED_FROM_PROFILE["P6"])
    rows = []
    for num_leads in (1, 2, 3):  # level 500 -> median 2.0
        rows.append({**{c: 0.0 for c in cols}, "ad_budget": 500, "num_leads": float(num_leads)})
    for num_leads in (10, 20):  # level 2000 -> median 15.0
        rows.append({**{c: 0.0 for c in cols}, "ad_budget": 2000, "num_leads": float(num_leads)})
    train_df = pd.DataFrame(rows)

    profiles = tr.compute_budget_profiles(train_df, [500, 2000, 5000])
    assert profiles[500]["n"] == 3
    assert profiles[500]["profile"]["num_leads"] == 2.0
    assert "ad_budget" not in profiles[500]["profile"]  # never part of the profile itself
    assert profiles[2000]["n"] == 2
    assert profiles[2000]["profile"]["num_leads"] == 15.0
    assert profiles[5000] == {"profile": None, "n": 0}  # zero rows -> unavailable, not completed from elsewhere


class _FakePipelineByBudget:
    """predict() depends only on ad_budget -- exercises
    simulate_strategies' weighted-sum logic without any real model."""
    def predict(self, X):
        return np.array([X["ad_budget"].iloc[0] / 100.0])


def test_simulate_strategies_sums_predictions_weighted_by_count():
    profiles = {level: {"profile": {"num_leads": 10.0}, "n": 5} for level in tr.STRATEGY_LEVELS}
    result = tr.simulate_strategies(_FakePipelineByBudget(), profiles)
    for name, allocations in tr.STRATEGY_ALLOCATIONS.items():
        expected = sum((level / 100.0) * count for level, count in allocations)
        assert result[name] == pytest.approx(expected)


def test_simulate_strategies_returns_none_only_for_strategies_needing_the_unavailable_level():
    profiles = {level: {"profile": {"num_leads": 10.0}, "n": 5} for level in tr.STRATEGY_LEVELS}
    profiles[500] = {"profile": None, "n": 0}
    result = tr.simulate_strategies(_FakePipelineByBudget(), profiles)
    assert result["100x500"] is None       # needs level 500
    assert result["10x5000"] is not None   # doesn't need level 500
    assert result["25x2000"] is not None
    assert result["2x20000_1x10000"] is not None


def test_p6_bootstrap_simulation_wires_point_and_bootstrap_calls_correctly(monkeypatch):
    cols = list(tr.DERIVED_FROM_PROFILE["P6"])
    rows = [
        {**{c: 0.0 for c in cols}, "ad_budget": level}
        for level in tr.STRATEGY_LEVELS
        for _ in range(30)  # enough per level that a 5-iteration bootstrap essentially never misses one
    ]
    synthetic_train_df = pd.DataFrame(rows)

    def fake_train_frame(given_df, task):
        assert task == "P6"
        return synthetic_train_df

    monkeypatch.setattr(tr, "build_task_train_frame", fake_train_frame)

    class _IdentityBudgetPipeline:
        def predict(self, X):
            return np.array([float(X["ad_budget"].iloc[0])])

    calls = []

    def fake_build(task, name, results, given_df, train_df=None):
        assert task == "P6"
        assert name == "stub"
        calls.append(len(train_df) if train_df is not None else None)
        return _IdentityBudgetPipeline()

    monkeypatch.setattr(tr, "build_fitted_candidate", fake_build)

    result = tr.p6_bootstrap_simulation(object(), {"stub": {"role": "candidate"}}, "stub", b=5)

    # 1 point-estimate call (the real train_df) + 5 bootstrap calls (each a resample of the SAME size)
    assert len(calls) == 6
    assert all(c == len(synthetic_train_df) for c in calls)

    for name, allocations in tr.STRATEGY_ALLOCATIONS.items():
        r = result[name]
        expected = sum(level * count for level, count in allocations)  # predict(ad_budget) = ad_budget
        assert r["point"] == pytest.approx(expected)
        assert r["interval_method"] == "bootstrap_percentile"
        assert r["n_bootstrap_used"] == 5  # every level present in every resample
        assert r["lower"] == pytest.approx(expected)
        assert r["upper"] == pytest.approx(expected)
