from __future__ import annotations

import json

from scripts.business_facts import build_business_facts, write_business_facts


def _inputs():
    metrics = {
        "P6_backtest": {
            level: {"predicted_per_customer": 800.0, "actual_mean_per_customer": 100.0,
                    "n_train_at_level": 90, "n_holdout_at_level": 17,
                    "profile_source_row_id": 123}
            for level in ("500", "2000")
        },
        "global_feature_importance": {"P2": {
            "catboost": {"numeric__calls_to_closed": 9.0, "numeric__ad_budget": 1.0},
            "lightgbm": {"numeric__calls_to_closed": 8.0, "numeric__ad_budget": 2.0},
            "xgboost": {"numeric__calls_to_closed": 7.0, "numeric__ad_budget": 3.0},
        }},
        "super_customer_profile": {
            "n_purchased": 10, "n_super": 2, "pct_of_purchased": 0.2,
            "pct_of_total_profit": 0.3, "cac_super_mean": 100.0,
            "cac_population_mean": 150.0, "cac_savings_pct": 1 / 3,
        },
    }
    findings = {"calls_to_closed": {
        "population_definition": "closed>0",
        "mean_calls_to_closed_closed_eq_1": 5.6,
        "mean_calls_to_closed_closed_ge_2": 3.4,
    }}
    versions = {task: f"{task}-v1" for task in ("P2", "P3", "P4", "P4S", "P6")}
    return metrics, findings, versions


def test_business_facts_is_minimal_and_marks_consensus():
    metrics, findings, versions = _inputs()
    facts = build_business_facts(
        metrics, findings, versions,
        source_csv_sha256="a" * 64, metrics_sha256="b" * 64,
    )
    assert facts["schema_version"] == 1
    assert facts["ltv"]["dominant_feature"] == "calls_to_closed"
    assert set(facts["ltv"]["rank_1_by_algorithm"]) == {"catboost", "lightgbm", "xgboost"}
    assert facts["followup_context"]["population_definition"] == "closed>0"
    assert "P2" not in facts  # no full metrics blocks
    assert "distribution" not in json.dumps(facts)
    assert set(facts["budget_backtest"]) == {"500", "2000"}
    assert facts["budget_backtest"]["500"]["predicted_per_customer"] == 800.0
    assert "profile_source_row_id" not in json.dumps(facts)


def test_business_facts_does_not_claim_consensus_when_one_model_differs():
    metrics, findings, versions = _inputs()
    metrics["global_feature_importance"]["P2"]["xgboost"]["numeric__ad_budget"] = 10.0
    facts = build_business_facts(
        metrics, findings, versions,
        source_csv_sha256="a" * 64, metrics_sha256="b" * 64,
    )
    assert facts["ltv"]["dominant_feature"] is None


def test_business_facts_writer_is_byte_deterministic(tmp_path):
    metrics, findings, versions = _inputs()
    facts = build_business_facts(
        metrics, findings, versions,
        source_csv_sha256="a" * 64, metrics_sha256="b" * 64,
    )
    first, second = tmp_path / "first.json", tmp_path / "second.json"
    write_business_facts(facts, first)
    write_business_facts(facts, second)
    assert first.read_bytes() == second.read_bytes()
