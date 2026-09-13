"""Build the small, versioned display-facts asset defined in DESIGN §6.1.

The browser receives approved aggregates only. It never receives the full
metrics/findings documents or any customer-level row.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path


TASKS = ("P2", "P3", "P4", "P4S", "P6")
P2_ALGORITHMS = ("catboost", "lightgbm", "xgboost")


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _read_json(path: Path) -> dict:
    with path.open(encoding="utf-8") as handle:
        return json.load(handle)


def build_business_facts(metrics: dict, findings: dict, model_versions: dict,
                         *, source_csv_sha256: str, metrics_sha256: str) -> dict:
    importance = metrics["global_feature_importance"]["P2"]
    rank_1 = {}
    for algorithm in P2_ALGORITHMS:
        values = importance[algorithm]
        raw_feature, value = max(values.items(), key=lambda item: (item[1], item[0]))
        rank_1[algorithm] = {
            "feature": raw_feature.removeprefix("numeric__"),
            "importance": float(value),
        }
    leaders = {entry["feature"] for entry in rank_1.values()}

    super_profile = metrics["super_customer_profile"]
    calls = findings["calls_to_closed"]
    if calls.get("population_definition") != "closed>0":
        raise ValueError("calls_to_closed facts must use the closed>0 population")

    return {
        "schema_version": 1,
        "source_csv_sha256": source_csv_sha256,
        "metrics_sha256": metrics_sha256,
        "model_versions": {task: model_versions[task] for task in TASKS},
        "source_keys": {
            "ltv": "models/metrics.json.global_feature_importance.P2",
            "super_customer_profile": "models/metrics.json.super_customer_profile",
            "followup_context": "docs/findings.json.calls_to_closed",
            "budget_backtest": "models/metrics.json.P6_backtest",
        },
        "ltv": {
            "rank_1_by_algorithm": rank_1,
            "dominant_feature": next(iter(leaders)) if len(leaders) == 1 else None,
        },
        "super_customer_profile": {
            **{key: super_profile[key] for key in (
                "n_purchased", "n_super", "pct_of_purchased", "pct_of_total_profit",
                "cac_super_mean", "cac_population_mean", "cac_savings_pct",
            )},
            "population_definition": "purchased=1 AND referred=Yes AND upsell=1 AND ltv_months>=34",
        },
        "followup_context": {
            "population_definition": "closed>0",
            "mean_calls_closed_eq_1": calls["mean_calls_to_closed_closed_eq_1"],
            "mean_calls_closed_ge_2": calls["mean_calls_to_closed_closed_ge_2"],
        },
        "budget_backtest": {
            level: {key: metrics["P6_backtest"][level][key] for key in (
                "predicted_per_customer", "actual_mean_per_customer",
                "n_train_at_level", "n_holdout_at_level",
            )}
            for level in ("500", "2000")
        },
    }


def build_from_project(project_root: Path) -> dict:
    metrics_path = project_root / "models" / "metrics.json"
    findings_path = project_root / "docs" / "findings.json"
    metrics = _read_json(metrics_path)
    findings = _read_json(findings_path)
    meta = {task: _read_json(project_root / "models" / f"{task}.meta.json") for task in TASKS}
    source_hashes = {task: meta[task]["checksums"]["source_csv_sha256"] for task in TASKS}
    if len(set(source_hashes.values())) != 1:
        raise ValueError(f"model metadata disagree on source CSV: {source_hashes}")
    return build_business_facts(
        metrics,
        findings,
        {task: meta[task]["model_version"] for task in TASKS},
        source_csv_sha256=next(iter(source_hashes.values())),
        metrics_sha256=_sha256(metrics_path),
    )


def write_business_facts(facts: dict, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="\n") as handle:
        json.dump(facts, handle, ensure_ascii=False, indent=2, sort_keys=True, allow_nan=False)
        handle.write("\n")


if __name__ == "__main__":
    root = Path(__file__).resolve().parent.parent
    destination = root / "app" / "static" / "business_facts.json"
    write_business_facts(build_from_project(root), destination)
    print(f"wrote {destination}")
