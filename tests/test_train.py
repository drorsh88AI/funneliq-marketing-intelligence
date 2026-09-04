"""Tests for scripts/train.py -- checkpoint 3, the split layer only
(PHASE6.md D2, D18/S6). Later checkpoints (folds, Pipelines, training)
get their own test coverage as they're built.

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
from pathlib import Path

import pandas as pd
import pytest

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
            str(1000 + i), str(20 + i % 5), str(15 + i % 4), str(5 + i % 3),
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
    import math
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
