"""Tests for GET /api/simulate/budget (PHASE9.md checkpoint 8, D11):
a pure lookup over P6_simulation.json/metrics.json, never the joblib
artifact. Criteria 60-61, plus permissions.
"""
from __future__ import annotations

import json
from pathlib import Path

import joblib
import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
MODELS_DIR = REPO_ROOT / "models"
PATH = "/api/simulate/budget"


def _real_meta() -> dict:
    return json.loads((MODELS_DIR / "P6.meta.json").read_text(encoding="utf-8"))


def _real_metrics() -> dict:
    return json.loads((MODELS_DIR / "metrics.json").read_text(encoding="utf-8"))


def _real_simulation() -> dict:
    return json.loads((MODELS_DIR / "P6_simulation.json").read_text(encoding="utf-8"))


def test_requires_auth():
    from fastapi.testclient import TestClient

    from app.main import app

    client = TestClient(app)
    response = client.get(PATH)
    assert response.status_code == 401


def test_rejects_wrong_organization(make_authed_client):
    client = make_authed_client(organization="other")
    response = client.get(PATH)
    assert response.status_code == 403


def test_no_body_no_422_on_get(authed_client):
    """D10 -- no request body; the route is a bare GET."""
    response = authed_client.get(PATH)
    assert response.status_code == 200


# ---------------------------------------------------------------------------
# Criterion 60 -- every field matches P6_simulation.json/metrics.json
# exactly.
# ---------------------------------------------------------------------------


def test_all_four_strategies_present_with_correct_ranks(authed_client):
    metrics = _real_metrics()
    ranked = metrics["P6_strategy_ranking"]["ranked"]

    response = authed_client.get(PATH)
    body = response.json()

    assert len(body["strategies"]) == 4
    assert [s["strategy_id"] for s in body["strategies"]] == ranked
    for index, strategy in enumerate(body["strategies"]):
        assert strategy["rank"] == index + 1
    assert body["top_two_overlap"] == metrics["P6_strategy_ranking"]["top_two_overlap"]


def test_point_lower_upper_bootstrap_match_simulation_json_exactly(authed_client):
    simulation = _real_simulation()
    response = authed_client.get(PATH)
    body = response.json()

    for strategy in body["strategies"]:
        sim = simulation[strategy["strategy_id"]]
        assert strategy["point_estimate"] == pytest.approx(sim["point"])
        assert strategy["lower_bound"] == pytest.approx(sim["lower"])
        assert strategy["upper_bound"] == pytest.approx(sim["upper"])
        assert strategy["bootstrap_iterations"] == sim["n_bootstrap_used"]


def test_sample_size_matches_simulation_json_levels(authed_client):
    simulation = _real_simulation()
    response = authed_client.get(PATH)
    body = response.json()

    for strategy in body["strategies"]:
        sim = simulation[strategy["strategy_id"]]
        for allocation in strategy["allocations"]:
            expected_n = sim["levels"][str(allocation["ad_budget"])]["n"]
            assert allocation["sample_size"] == expected_n


def test_in_training_domain_always_true_and_no_warnings(authed_client):
    response = authed_client.get(PATH)
    for strategy in response.json()["strategies"]:
        assert strategy["in_training_domain"] is True
        assert strategy["warnings"] == []


def test_model_version_and_metrics_match_meta(authed_client):
    meta = _real_meta()
    metrics = _real_metrics()
    cv = metrics["P6"][meta["algo"]]
    holdout = metrics["P6_holdout"]

    response = authed_client.get(PATH)
    body = response.json()

    assert body["model_version"] == meta["model_version"]
    assert body["model_algorithm"] == meta["algo"]
    assert body["metrics"]["cv"] == {"mean_mae": cv["mean_mae"], "mean_rmse": cv["mean_rmse"], "mean_r2": cv["mean_r2"]}
    assert body["metrics"]["holdout"] == {"mae": holdout["mae"], "rmse": holdout["rmse"], "r2": holdout["r2"]}


# ---------------------------------------------------------------------------
# Criterion 61 -- constant-vs-artifact parity: the levels STRATEGY_ALLOCATIONS
# names are exactly the levels P6_simulation.json has for that strategy.
# ---------------------------------------------------------------------------


def test_strategy_allocations_levels_match_simulation_json():
    from app.features import STRATEGY_ALLOCATIONS

    simulation = _real_simulation()
    for strategy_id, pairs in STRATEGY_ALLOCATIONS.items():
        expected_levels = {str(ad_budget) for ad_budget, _count in pairs}
        actual_levels = set(simulation[strategy_id]["levels"])
        assert expected_levels == actual_levels, strategy_id


# ---------------------------------------------------------------------------
# D14/criterion 58 (P6-specific half) -- the route's evidence_level comes
# from the SAME schemas.evidence_level_from_n the schema's own invariant
# validates against; a spy on the module attribute observes both.
# ---------------------------------------------------------------------------


def test_evidence_level_comes_from_the_shared_function(authed_client, monkeypatch):
    from app import schemas

    calls = []
    real = schemas.evidence_level_from_n

    def spy(n):
        calls.append(n)
        return real(n)

    monkeypatch.setattr(schemas, "evidence_level_from_n", spy)
    response = authed_client.get(PATH)
    assert response.status_code == 200
    # Called at least once per strategy by the route, PLUS once per
    # strategy again by StrategyResult's own validator -- proof both
    # consumers reach the same patched object.
    assert len(calls) >= 8


def test_evidence_level_matches_min_sample_size_thresholds(authed_client):
    from app.schemas import evidence_level_from_n

    response = authed_client.get(PATH)
    for strategy in response.json()["strategies"]:
        min_n = min(a["sample_size"] for a in strategy["allocations"])
        assert strategy["evidence_level"] == evidence_level_from_n(min_n)


# ---------------------------------------------------------------------------
# D11/criterion 43 (route-level) -- P6.joblib is never loaded via this route.
# ---------------------------------------------------------------------------


def test_p6_joblib_never_loaded(authed_client, monkeypatch):
    calls = []
    original = joblib.load

    def spy(path, *a, **kw):
        calls.append(str(path))
        return original(path, *a, **kw)

    monkeypatch.setattr(joblib, "load", spy)
    from app.artifacts import reset_artifact_cache_for_tests

    reset_artifact_cache_for_tests()
    authed_client.get(PATH)
    assert calls == []
    reset_artifact_cache_for_tests()
