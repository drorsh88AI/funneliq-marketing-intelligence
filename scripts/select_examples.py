"""Phase 12A, CP1 step 1 (docs/planning/PHASE12A.md §ו.2): selects the 10
frozen historical examples shared by the predict form's and P4S's
prefill pickers, and writes them to `docs/frozen_examples.json`.

Locked selection rule (§ו.2, approved after a counter-review round):
  - Composition: 2 Low / 5 Mid / 3 High (close to the CSV's own
    purchaser composition: 571 / 1,640 / 952 -- PHASE0.md).
  - Stage 0, eligibility (population condition, NOT a quality filter):
    `purchased == 1`, passes FunnelInput's business-rule validation
    (app/schemas.py), and every field is within ALL FOUR models' own
    ood_bounds (P2, P3, P4, P4S) simultaneously. Never uses the
    super-customer outcome columns (referred/upsell/ltv_months/
    cumulative_profit) or any model score to choose or exclude a row.
  - Stage 1, position (within each tier): evenly spread positions over
    the ASCENDING-sorted eligible source_row_id, floor((i+0.5)*n/k) for
    i in range(k) -- never the first k rows.
  - Locked (committed) BEFORE any P4S score is ever computed for these
    rows (A1) -- a row is never swapped out because of its score.

This script requires `funnel_marketing_data.csv` (frozen, not in the
repo's own history beyond PHASE0's hash record) -- run locally only.
CI never runs this script; CI's own structural checks (10 unique ids,
2/5/3 composition re-derived from the stored ad_budget values via
app.features.budget_tier) read ONLY the committed output file.
"""
from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

import pandas as pd

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from app.features import budget_tier  # noqa: E402
from app.schemas import FunnelInput  # noqa: E402

CSV_PATH = REPO_ROOT / "funnel_marketing_data.csv"
EXPECTED_SHA256 = "8ac67d50a6f96a8ece8abd770a5a1901b34036a5c98656455eb04cee07d707aa"
OUTPUT_PATH = REPO_ROOT / "docs" / "frozen_examples.json"

INPUT_FIELDS = [
    "ad_budget", "num_leads", "leads_answered",
    "followup_1", "followup_2", "followup_3", "followup_4", "followup_5",
    "not_closed", "closed", "calls_to_closed", "calls_to_not_closed",
    "customer_acquisition_cost",
]
TIER_TARGETS = {"Low": 2, "Mid": 5, "High": 3}


def load_ood_bounds() -> dict[str, dict[str, tuple[float, float]]]:
    bounds: dict[str, dict[str, tuple[float, float]]] = {}
    for model_name in ("P2", "P3", "P4", "P4S"):
        meta = json.loads((REPO_ROOT / "models" / f"{model_name}.meta.json").read_text(encoding="utf-8"))
        for field, b in meta["ood_bounds"].items():
            bounds.setdefault(field, []).append((b["min"], b["max"]))
    # intersection across whichever models use each field
    return {
        field: (max(lo for lo, _ in pairs), min(hi for _, hi in pairs))
        for field, pairs in bounds.items()
    }


def passes_business_rules(row: pd.Series) -> bool:
    try:
        FunnelInput(**{f: int(row[f]) for f in INPUT_FIELDS})
    except Exception:
        return False
    return True


def within_ood_bounds(row: pd.Series, bounds: dict[str, tuple[float, float]]) -> bool:
    for field, (lo, hi) in bounds.items():
        if field not in row:
            continue
        v = row[field]
        if not (lo <= v <= hi):
            return False
    return True


def main() -> None:
    actual_sha256 = hashlib.sha256(CSV_PATH.read_bytes()).hexdigest()
    if actual_sha256 != EXPECTED_SHA256:
        raise SystemExit(
            f"CSV hash mismatch -- expected {EXPECTED_SHA256}, got {actual_sha256}. "
            "PHASE0.md's frozen-file guarantee no longer holds; stop."
        )

    df = pd.read_csv(CSV_PATH)
    df.index = df.index + 1  # source_row_id is 1-based (schema.sql comment)

    bounds = load_ood_bounds()

    eligible_mask = (
        (df["purchased"] == 1)
        & df.apply(passes_business_rules, axis=1)
        & df.apply(lambda r: within_ood_bounds(r, bounds), axis=1)
    )
    eligible = df[eligible_mask].copy()
    eligible["tier"] = eligible["ad_budget"].apply(budget_tier)

    selected_rows = []
    for tier, k in TIER_TARGETS.items():
        tier_rows = eligible[eligible["tier"] == tier].sort_index()
        n = len(tier_rows)
        if n < k:
            raise SystemExit(f"tier {tier} has only {n} eligible rows, need {k}")
        positions = [int((i + 0.5) * n / k) for i in range(k)]
        chosen_source_row_ids = tier_rows.index[positions]
        for source_row_id in chosen_source_row_ids:
            selected_rows.append(int(source_row_id))

    selected_rows.sort()

    manifest = {
        "examples": [
            {
                "source_row_id": source_row_id,
                **{f: int(df.loc[source_row_id, f]) for f in INPUT_FIELDS},
            }
            for source_row_id in selected_rows
        ]
    }

    OUTPUT_PATH.write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    # Report for human review -- tier composition + a quick sanity echo.
    tier_by_id = {int(idx): eligible.loc[idx, "tier"] for idx in selected_rows}
    print(f"eligible population: {len(eligible)} rows (Low={sum(eligible['tier']=='Low')}, "
          f"Mid={sum(eligible['tier']=='Mid')}, High={sum(eligible['tier']=='High')}, "
          f"gap={sum(eligible['tier'].isna())})")
    print(f"selected {len(selected_rows)} ids: {selected_rows}")
    for source_row_id in selected_rows:
        print(f"  source_row_id={source_row_id} tier={tier_by_id[source_row_id]} "
              f"ad_budget={df.loc[source_row_id, 'ad_budget']}")
    print(f"wrote {OUTPUT_PATH.relative_to(REPO_ROOT)}")


if __name__ == "__main__":
    main()
