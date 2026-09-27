"""Phase 12A, CP1 steps 3 (A1, A2): local, offline P4S diagnosis --
docs/planning/PHASE12A.md §ג. Never touches the live deployment, Supabase,
or any credential. Reuses scripts.train's own split_task/task_population
and app.features' own target_values/budget_tier -- never reimplements
the train/calibration/holdout split logic, to avoid silently diverging
from what scripts/train.py actually used to build the shipped artifact.

A1: scores מ1 (the 10 frozen examples, docs/frozen_examples.json), מ2
(the one manual in-domain scenario locked in PHASE12A.md §ג), and a
DESCRIPTIVE tier x score summary over מ3 (the old prefill population --
purchased=1, ordered by source_row_id, first 1000 -- exactly
supabase-prefill.js's own query, reconstructed locally from the frozen
CSV since it is purely descriptive, not a live-authority claim).

A2: super-customer rate by budget_tier, TRAIN ONLY (excludes both
calibration and holdout -- split_task's own three-way split), never
opens Holdout itself. Describes whether the Mid-only pattern PHASE12A.md
already read from metrics.json (Holdout) also shows up outside Holdout;
this is NOT a new Holdout evaluation and proves nothing about prediction
quality (§ג's own explicit limits)."""
from __future__ import annotations

import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from app.features import budget_tier, target_values  # noqa: E402
from app.inference import predict_if_in_domain  # noqa: E402
from scripts.load_data import load_and_verify_csv  # noqa: E402
from scripts.train import split_task, task_population  # noqa: E402

CSV_PATH = REPO_ROOT / "funnel_marketing_data.csv"
FROZEN_EXAMPLES_PATH = REPO_ROOT / "docs" / "frozen_examples.json"
P4S_FIELDS = ["ad_budget", "num_leads", "leads_answered", "followup_1"]

# מ2 -- locked in PHASE12A.md §ג (27.09.2026): manual, valid, NOT a CSV row.
M2_SCENARIO = {"ad_budget": 3300, "num_leads": 45, "leads_answered": 30, "followup_1": 22}

OLD_PREFILL_LIMIT = 1000


def score_one(meta: dict, values: dict) -> dict:
    """A1's own local scoring rule: Math.round(p*100), no labels
    (`app.inference` directly, mirroring app/predict.py's own
    predict_if_in_domain(..., method="predict_proba") call)."""
    out_of_range, raw = predict_if_in_domain("P4S", meta, values, method="predict_proba")
    if out_of_range:
        return {"in_domain": False, "out_of_range_features": out_of_range}
    p = float(raw[0][1])
    return {"in_domain": True, "event_probability": p, "displayed_score": round(p * 100)}


def run_a1(meta: dict, df) -> None:
    print("=== A1: local scoring (app.inference, predict_proba) ===")

    frozen = json.loads(FROZEN_EXAMPLES_PATH.read_text(encoding="utf-8"))["examples"]
    print(f"\n-- מ1: {len(frozen)} frozen examples --")
    for ex in frozen:
        values = {f: ex[f] for f in P4S_FIELDS}
        result = score_one(meta, values)
        print(f"  source_row_id={ex['source_row_id']:>4} {values} -> {result}")

    print("\n-- מ2: manual scenario --")
    result = score_one(meta, M2_SCENARIO)
    print(f"  {M2_SCENARIO} -> {result}")

    print(f"\n-- מ3: old prefill population (purchased=1, ordered by "
          f"source_row_id, first {OLD_PREFILL_LIMIT}) -- DESCRIPTIVE ONLY --")
    pop = df[df["purchased"] == 1].sort_values("source_row_id").head(OLD_PREFILL_LIMIT)
    tier_counts: dict[str, dict] = {}
    for _, row in pop.iterrows():
        values = {f: int(row[f]) for f in P4S_FIELDS}
        tier = budget_tier(row["ad_budget"]) or "gap"
        bucket = tier_counts.setdefault(tier, {"n": 0, "n_scored": 0, "scores": []})
        bucket["n"] += 1
        result = score_one(meta, values)
        if result["in_domain"]:
            bucket["n_scored"] += 1
            bucket["scores"].append(result["displayed_score"])
    for tier in ("Low", "Mid", "High", "gap"):
        if tier not in tier_counts:
            continue
        b = tier_counts[tier]
        scores = b["scores"]
        mean_score = sum(scores) / len(scores) if scores else None
        n_at_1 = sum(1 for s in scores if s <= 1)
        print(f"  tier={tier:<4} n={b['n']:<4} n_scored(in-domain)={b['n_scored']:<4} "
              f"mean_displayed_score={mean_score if mean_score is None else round(mean_score, 2):<6} "
              f"n_score<=1={n_at_1}")


def run_a2(df) -> None:
    print("\n=== A2: super-customer rate by budget_tier, TRAIN ONLY (not Holdout) ===")
    parts = split_task(df, "P4S")
    train_ids = set(parts["train"])
    calib_ids = set(parts["calibration"])
    holdout_ids = set(parts["holdout"])
    assert not (train_ids & holdout_ids), "train/holdout overlap -- would silently reopen Holdout"
    assert not (train_ids & calib_ids), "train/calibration overlap"

    pop = task_population(df, "P4S")
    train_pop = pop[pop["source_row_id"].isin(train_ids)]
    labels = target_values(train_pop, "P4S")

    print(f"population={len(pop)} train={len(train_pop)} calibration={len(calib_ids)} holdout={len(holdout_ids)}")
    for tier in ("Low", "Mid", "High"):
        tier_mask = train_pop["ad_budget"].apply(budget_tier) == tier
        n = int(tier_mask.sum())
        n_super = int(labels[tier_mask].sum())
        rate = n_super / n if n else None
        print(f"  tier={tier:<4} n={n:<5} n_super_customer={n_super:<4} "
              f"rate={rate if rate is None else round(rate, 4)}")


def main() -> None:
    meta = json.loads((REPO_ROOT / "models" / "P4S.meta.json").read_text(encoding="utf-8"))
    df = load_and_verify_csv(CSV_PATH)  # already adds a 1-based "source_row_id" column

    run_a1(meta, df)
    run_a2(df)


if __name__ == "__main__":
    main()
