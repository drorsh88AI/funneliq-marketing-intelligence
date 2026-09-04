"""Phase 6 -- single mechanical entry point for training, calibrating,
and evaluating P2/P3/P4/P6 (docs/planning/PHASE6.md, SPEC.md § שש
החבילות). Imports scripts.load_data.load_and_verify_csv (SHA-256 +
header check, source_row_id) and app.features (TARGET/FEATURES) as the
single mechanical sources of truth for the CSV contract and per-task
feature lists -- nothing here redefines them.

Built incrementally, one PHASE6.md checkpoint at a time. This module
currently holds checkpoint 3's split layer only.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from app.features import TARGET  # noqa: E402
from scripts.load_data import load_and_verify_csv  # noqa: E402

import pandas as pd
from sklearn.model_selection import train_test_split

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
