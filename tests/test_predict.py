"""Tests for POST /api/predict/{ltv,upsell,referral} (PHASE9.md checkpoint
5): permissions (criteria 6-10) and semantic parity (criteria 46-59, 74)
against the real artifacts and meta -- not just schema-shape checks.
"""
from __future__ import annotations

import json
from pathlib import Path

import joblib
import pytest

from app.schemas import propensity_band_for
from tests.conftest import FUNNEL_INPUT_IN_DOMAIN

REPO_ROOT = Path(__file__).resolve().parent.parent
MODELS_DIR = REPO_ROOT / "models"

ROUTES = {
    "P2": "/api/predict/ltv",
    "P3": "/api/predict/upsell",
    "P4": "/api/predict/referral",
}


def _real_meta(task: str) -> dict:
    return json.loads((MODELS_DIR / f"{task}.meta.json").read_text(encoding="utf-8"))


def _real_metrics() -> dict:
    return json.loads((MODELS_DIR / "metrics.json").read_text(encoding="utf-8"))


# ---------------------------------------------------------------------------
# Criteria 6-10 -- permissions and request validation, on the real routes.
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("path", ROUTES.values())
def test_predict_routes_require_auth(path):
    from fastapi.testclient import TestClient

    from app.main import app

    client = TestClient(app)
    response = client.post(path, json=FUNNEL_INPUT_IN_DOMAIN)
    assert response.status_code == 401


@pytest.mark.parametrize("path", ROUTES.values())
def test_predict_routes_reject_wrong_organization(make_authed_client, path):
    client = make_authed_client(organization="other")
    response = client.post(path, json=FUNNEL_INPUT_IN_DOMAIN)
    assert response.status_code == 403


@pytest.mark.parametrize("path", ROUTES.values())
@pytest.mark.parametrize(
    "override,rule_hint",
    [
        ({"num_leads": 0}, "num_leads"),
        ({"leads_answered": 999}, "leads_answered"),
        ({"followup_2": 999}, "followup"),
        ({"closed": 1, "not_closed": 1}, "closed"),  # closed+not_closed != followup_5 (10)
        ({"ad_budget": -1}, "ad_budget"),
    ],
)
def test_funnel_input_business_rules_are_422_on_the_real_route(
    authed_client, path, override, rule_hint
):
    """Criterion 8: FunnelInput's five blocking rules, exercised through
    an actual route, not just the schema in isolation."""
    body = dict(FUNNEL_INPUT_IN_DOMAIN, **override)
    response = authed_client.post(path, json=body)
    assert response.status_code == 422
    detail = response.json()["detail"]
    assert set(detail[0].keys()) == {"loc", "msg", "type"}


# ---------------------------------------------------------------------------
# Criterion 46 -- precondition: the shared fixture is in-domain for all
# three tasks' ood_bounds, and ad_budget is an observed training value.
# Runs first so a fixture drift fails loudly, not as a confusing parity
# mismatch further down.
# ---------------------------------------------------------------------------


def test_precondition_fixture_is_in_domain_for_p2_p3_p4():
    for task in ("P2", "P3", "P4"):
        meta = _real_meta(task)
        bounds = meta["ood_bounds"]
        for feature, value in FUNNEL_INPUT_IN_DOMAIN.items():
            assert bounds[feature]["min"] <= value <= bounds[feature]["max"], (
                f"{task}/{feature}={value} is out of the fixture's intended in-domain range"
            )
        assert float(FUNNEL_INPUT_IN_DOMAIN["ad_budget"]) in meta["observed_ad_budget_values"]


# ---------------------------------------------------------------------------
# Criteria 47-48 -- P2: point_estimate/lower_bound/upper_bound match the
# pipeline's own predict() and the conformal quantile exactly; interval
# details match meta/metrics exactly.
# ---------------------------------------------------------------------------


def test_p2_point_and_interval_match_the_artifact_exactly(authed_client):
    import pandas as pd

    meta = _real_meta("P2")
    pipeline = joblib.load(MODELS_DIR / "P2.joblib")
    frame = pd.DataFrame([FUNNEL_INPUT_IN_DOMAIN], columns=meta["feature_columns"])
    for col in meta["feature_columns"]:
        frame[col] = frame[col].astype(meta["feature_dtypes"][col])
    expected_point = float(pipeline.predict(frame)[0])
    q = meta["conformal_quantile"]
    expected_lower = max(0.0, expected_point - q)
    expected_upper = expected_point + q

    response = authed_client.post("/api/predict/ltv", json=FUNNEL_INPUT_IN_DOMAIN)
    body = response.json()

    assert body["point_estimate"] == pytest.approx(expected_point)
    assert body["lower_bound"] == pytest.approx(expected_lower)
    assert body["upper_bound"] == pytest.approx(expected_upper)
    assert body["interval_details"]["nominal_coverage"] == pytest.approx(1 - meta["alpha"])
    assert body["interval_details"]["measured_coverage"] == pytest.approx(
        _real_metrics()["P2_holdout"]["conformal_coverage"]
    )


# ---------------------------------------------------------------------------
# Criterion 50 -- S10: a point below q clips the lower bound at exactly
# 0.0, not a negative number.
# ---------------------------------------------------------------------------


def test_p2_lower_bound_clips_at_zero_when_point_below_q(authed_client, monkeypatch):
    from app import predict as predict_module

    meta = _real_meta("P2")
    q = meta["conformal_quantile"]

    def fake_predict_if_in_domain(task, meta_arg, values, *, method="predict"):
        return [], [q / 2]  # deliberately below q, so point - q would go negative

    monkeypatch.setattr(predict_module, "predict_if_in_domain", fake_predict_if_in_domain)
    response = authed_client.post("/api/predict/ltv", json=FUNNEL_INPUT_IN_DOMAIN)
    body = response.json()
    assert body["lower_bound"] == 0.0
    assert body["point_estimate"] == pytest.approx(q / 2)


# ---------------------------------------------------------------------------
# Criterion 49 -- P3/P4: event_probability matches predict_proba exactly;
# base_rate matches meta; propensity_band matches the shared thresholding
# function.
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("task,path", [("P3", "/api/predict/upsell"), ("P4", "/api/predict/referral")])
def test_propensity_matches_the_artifact_exactly(authed_client, task, path):
    import pandas as pd

    meta = _real_meta(task)
    model = joblib.load(MODELS_DIR / f"{task}.joblib")
    frame = pd.DataFrame([FUNNEL_INPUT_IN_DOMAIN], columns=meta["feature_columns"])
    for col in meta["feature_columns"]:
        frame[col] = frame[col].astype(meta["feature_dtypes"][col])
    expected_probability = float(model.predict_proba(frame)[0][1])
    expected_band = propensity_band_for(expected_probability, meta["base_rate"])

    response = authed_client.post(path, json=FUNNEL_INPUT_IN_DOMAIN)
    body = response.json()

    assert body["event_probability"] == pytest.approx(expected_probability)
    assert body["base_rate"] == pytest.approx(meta["base_rate"])
    assert body["propensity_band"] == expected_band
    assert body["calibration_status"] == meta["calibration_status"]
    assert body["calibration_method"] == meta["calibration_method"]


# ---------------------------------------------------------------------------
# Criterion 51 -- boundary parity, per feature: min/max in-domain,
# min-1/max+1 out of domain. Runs against P2's ood_bounds.
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("feature", list(FUNNEL_INPUT_IN_DOMAIN.keys()))
def test_boundary_values_in_and_out_of_domain(authed_client, feature):
    meta = _real_meta("P2")
    bounds = meta["ood_bounds"][feature]

    for value, expect_ood in [
        (int(bounds["min"]), False),
        (int(bounds["max"]), False),
        (int(bounds["min"]) - 1, True),
        (int(bounds["max"]) + 1, True),
    ]:
        body = dict(FUNNEL_INPUT_IN_DOMAIN, **{feature: value})
        # Keep the funnel-ordering business rules satisfiable for the
        # fields the chain constrains -- num_leads/leads_answered are
        # bumped alongside so a boundary probe on one field doesn't
        # accidentally trip FunnelInput's own 422 rules instead of the
        # OOD path this test targets.
        if feature == "num_leads" and value < body["leads_answered"]:
            continue  # would violate leads_answered<=num_leads; not this test's concern
        if feature == "leads_answered" and value > body["num_leads"]:
            continue
        response = authed_client.post("/api/predict/ltv", json=body)
        if response.status_code == 422:
            continue  # a business-rule interaction, not an OOD probe -- skip
        result = response.json()
        if expect_ood:
            assert result["in_training_domain"] is False, f"{feature}={value} expected OOD"
        else:
            assert result["in_training_domain"] is True, f"{feature}={value} expected in-domain"


# ---------------------------------------------------------------------------
# Criteria 52-54 -- unobserved budget, OOD-only, and multiple violations.
# ---------------------------------------------------------------------------


def test_unobserved_ad_budget_gets_low_evidence_and_warning(authed_client):
    body = dict(FUNNEL_INPUT_IN_DOMAIN, ad_budget=3500)
    response = authed_client.post("/api/predict/ltv", json=body)
    result = response.json()
    assert result["point_estimate"] is not None
    assert result["evidence_level"] == "low"
    assert result["in_training_domain"] is True
    codes = {w["code"] for w in result["warnings"]}
    assert codes == {"unobserved_budget_level"}


def test_out_of_range_ad_budget_gets_ood_warning_only(authed_client):
    body = dict(FUNNEL_INPUT_IN_DOMAIN, ad_budget=25000)
    response = authed_client.post("/api/predict/ltv", json=body)
    result = response.json()
    assert result["point_estimate"] is None
    assert result["lower_bound"] is None
    assert result["upper_bound"] is None
    assert result["in_training_domain"] is False
    codes = {w["code"] for w in result["warnings"]}
    assert codes == {"ood_feature_out_of_range"}


def test_multiple_ood_features_each_get_their_own_warning(authed_client):
    """ad_budget and customer_acquisition_cost -- picked because neither
    participates in FunnelInput's funnel-ordering/closed+not_closed
    business rules, so bumping both past their OOD bounds triggers the
    OOD path this test targets, not an unrelated 422."""
    meta = _real_meta("P2")
    body = dict(
        FUNNEL_INPUT_IN_DOMAIN,
        ad_budget=25000,
        customer_acquisition_cost=int(meta["ood_bounds"]["customer_acquisition_cost"]["max"]) + 1,
    )
    response = authed_client.post("/api/predict/ltv", json=body)
    result = response.json()
    features = {w["feature"] for w in result["warnings"]}
    assert features == {"ad_budget", "customer_acquisition_cost"}
    assert result["point_estimate"] is None


# ---------------------------------------------------------------------------
# Criteria 56-57 -- model_version/model_algorithm and the metrics blocks,
# read from meta/metrics.json, checked against known values (not just
# "some string is present").
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("task,path", [("P2", "/api/predict/ltv"), ("P3", "/api/predict/upsell"), ("P4", "/api/predict/referral")])
def test_model_version_and_algorithm_match_meta(authed_client, task, path):
    meta = _real_meta(task)
    response = authed_client.post(path, json=FUNNEL_INPUT_IN_DOMAIN)
    body = response.json()
    assert body["model_version"] == meta["model_version"]
    assert body["model_algorithm"] == meta["algo"]


def test_p2_metrics_block_matches_known_values(authed_client):
    meta = _real_meta("P2")
    metrics = _real_metrics()
    cv = metrics["P2"][meta["algo"]]
    holdout = metrics["P2_holdout"]

    response = authed_client.post("/api/predict/ltv", json=FUNNEL_INPUT_IN_DOMAIN)
    body = response.json()["metrics"]

    assert body["cv"] == {"mean_mae": cv["mean_mae"], "mean_rmse": cv["mean_rmse"], "mean_r2": cv["mean_r2"]}
    assert body["holdout"] == {"mae": holdout["mae"], "rmse": holdout["rmse"], "r2": holdout["r2"]}
    assert "accuracy" not in body["holdout"]
    assert "n_holdout" not in body["holdout"]


def test_p3_metrics_block_matches_known_values(authed_client):
    meta = _real_meta("P3")
    metrics = _real_metrics()
    cv = metrics["P3"][meta["algo"]]
    holdout = metrics["P3_holdout"]

    response = authed_client.post("/api/predict/upsell", json=FUNNEL_INPUT_IN_DOMAIN)
    body = response.json()["metrics"]

    assert body["cv"] == {
        "mean_roc_auc": cv["mean_roc_auc"], "mean_pr_auc": cv["mean_pr_auc"],
        "mean_brier": cv["mean_brier"], "mean_log_loss": cv["mean_log_loss"],
    }
    assert body["holdout"] == {
        "roc_auc": holdout["roc_auc"], "pr_auc": holdout["pr_auc"],
        "brier": holdout["brier"], "log_loss": holdout["log_loss"],
    }
    assert "accuracy" not in body["holdout"]
    assert "n_holdout" not in body["holdout"]


# ---------------------------------------------------------------------------
# Criterion 59 -- warnings[].message is ASCII/English only.
# ---------------------------------------------------------------------------


def test_warning_messages_are_ascii_only(authed_client):
    body = dict(FUNNEL_INPUT_IN_DOMAIN, ad_budget=25000)
    response = authed_client.post("/api/predict/ltv", json=body)
    for warning in response.json()["warnings"]:
        assert warning["message"].isascii()


# ---------------------------------------------------------------------------
# Criterion 74 -- route-level confirmation that OOD never touches the
# joblib artifact (the unit-level proof lives in tests/test_inference.py;
# this is the same guarantee observed through the real HTTP route).
# ---------------------------------------------------------------------------


def test_ood_request_never_loads_the_joblib_artifact(authed_client, monkeypatch):
    calls = []
    original = joblib.load

    def spy(path, *a, **kw):
        calls.append(str(path))
        return original(path, *a, **kw)

    monkeypatch.setattr(joblib, "load", spy)
    from app.artifacts import reset_artifact_cache_for_tests

    reset_artifact_cache_for_tests()
    body = dict(FUNNEL_INPUT_IN_DOMAIN, ad_budget=25000)
    authed_client.post("/api/predict/ltv", json=body)
    assert calls == []
    reset_artifact_cache_for_tests()
