"""Tests for POST /api/predict/super-customer (PHASE9.md checkpoint 6,
PHASE8A.md D20): permissions, EarlyFunnelInput's three rules, semantic
parity, and the SuperCustomerOODWarning class (criterion 55).
"""
from __future__ import annotations

import json
from pathlib import Path

import joblib
import pandas as pd
import pytest

from app.schemas import propensity_band_for
from tests.conftest import EARLY_FUNNEL_INPUT_IN_DOMAIN

REPO_ROOT = Path(__file__).resolve().parent.parent
MODELS_DIR = REPO_ROOT / "models"
PATH = "/api/predict/super-customer"


def _real_meta() -> dict:
    return json.loads((MODELS_DIR / "P4S.meta.json").read_text(encoding="utf-8"))


def _real_metrics() -> dict:
    return json.loads((MODELS_DIR / "metrics.json").read_text(encoding="utf-8"))


# ---------------------------------------------------------------------------
# Permissions + EarlyFunnelInput's three rules (⚠ not FunnelInput's five).
# ---------------------------------------------------------------------------


def test_requires_auth():
    from fastapi.testclient import TestClient

    from app.main import app

    client = TestClient(app)
    response = client.post(PATH, json=EARLY_FUNNEL_INPUT_IN_DOMAIN)
    assert response.status_code == 401


def test_rejects_wrong_organization(make_authed_client):
    client = make_authed_client(organization="other")
    response = client.post(PATH, json=EARLY_FUNNEL_INPUT_IN_DOMAIN)
    assert response.status_code == 403


@pytest.mark.parametrize(
    "override",
    [
        {"num_leads": 0},                              # rule 1: num_leads > 0
        {"leads_answered": 999},                        # rule 2: leads_answered <= num_leads
        {"followup_1": 999},                             # rule 3: followup_1 <= leads_answered
    ],
)
def test_early_funnel_input_three_rules_are_422(authed_client, override):
    """Criterion 9: EXACTLY three rules, not FunnelInput's five --
    EarlyFunnelInput has no followup_2..5/closed/not_closed fields at all."""
    body = dict(EARLY_FUNNEL_INPUT_IN_DOMAIN, **override)
    response = authed_client.post(PATH, json=body)
    assert response.status_code == 422


def test_extra_field_from_funnel_input_is_rejected(authed_client):
    """EarlyFunnelInput has exactly 4 fields (extra="forbid") -- sending
    one of FunnelInput's other 9 fields must be a 422, not silently
    accepted."""
    body = dict(EARLY_FUNNEL_INPUT_IN_DOMAIN, closed=1)
    response = authed_client.post(PATH, json=body)
    assert response.status_code == 422


# ---------------------------------------------------------------------------
# Criterion 49 (P4S variant) -- event_probability/base_rate/propensity_band
# match the artifact exactly, plus target_definition/population_definition.
# ---------------------------------------------------------------------------


def test_parity_with_the_artifact(authed_client):
    meta = _real_meta()
    model = joblib.load(MODELS_DIR / "P4S.joblib")
    frame = pd.DataFrame([EARLY_FUNNEL_INPUT_IN_DOMAIN], columns=meta["feature_columns"])
    for col in meta["feature_columns"]:
        frame[col] = frame[col].astype(meta["feature_dtypes"][col])
    expected_probability = float(model.predict_proba(frame)[0][1])
    expected_band = propensity_band_for(expected_probability, meta["base_rate"])

    response = authed_client.post(PATH, json=EARLY_FUNNEL_INPUT_IN_DOMAIN)
    body = response.json()

    assert response.status_code == 200
    assert body["event_probability"] == pytest.approx(expected_probability)
    assert body["base_rate"] == pytest.approx(meta["base_rate"])
    assert body["propensity_band"] == expected_band
    assert body["calibration_status"] == "calibrated"
    assert body["calibration_method"] == meta["calibration_method"]
    assert body["model_version"] == meta["model_version"]
    assert body["model_algorithm"] == meta["algo"]
    assert body["target_definition"] == "referred=Yes AND upsell=1 AND ltv_months>=34"
    assert body["population_definition"] == "purchased=1"


def test_metrics_block_matches_known_values(authed_client):
    meta = _real_meta()
    metrics = _real_metrics()
    cv = metrics["P4S"][meta["algo"]]
    holdout = metrics["P4S_holdout"]

    response = authed_client.post(PATH, json=EARLY_FUNNEL_INPUT_IN_DOMAIN)
    body = response.json()["metrics"]

    assert body["cv"] == {
        "mean_roc_auc": cv["mean_roc_auc"], "mean_pr_auc": cv["mean_pr_auc"],
        "mean_brier": cv["mean_brier"], "mean_log_loss": cv["mean_log_loss"],
    }
    assert body["holdout"] == {
        "roc_auc": holdout["roc_auc"], "pr_auc": holdout["pr_auc"],
        "brier": holdout["brier"], "log_loss": holdout["log_loss"],
    }


# ---------------------------------------------------------------------------
# Criterion 55 -- P4S returns SuperCustomerOODWarning, not OODWarning.
# The two share the same `code`, so this must be checked on `feature`'s
# allowed values (SuperCustomerOODWarning's Literal is the 4-name P4S set,
# OODWarning's is the 13-name P2/P3/P4 set) as the observable proxy for
# "which class" in a plain JSON response, plus that the schema itself
# accepted the narrower feature name.
# ---------------------------------------------------------------------------


def test_ood_warning_uses_the_narrow_p4s_feature_set(authed_client):
    meta = _real_meta()
    body = dict(EARLY_FUNNEL_INPUT_IN_DOMAIN, ad_budget=25000)
    response = authed_client.post(PATH, json=body)
    result = response.json()
    assert result["in_training_domain"] is False
    assert result["event_probability"] is None
    warning = result["warnings"][0]
    assert warning["code"] == "ood_feature_out_of_range"
    assert warning["feature"] in ("ad_budget", "num_leads", "leads_answered", "followup_1")


def test_ood_response_still_carries_target_and_population_definition(authed_client):
    """Even the OOD (all-null-prediction) branch must carry the fixed
    definition literals -- they're not conditional on in_training_domain."""
    body = dict(EARLY_FUNNEL_INPUT_IN_DOMAIN, ad_budget=25000)
    response = authed_client.post(PATH, json=body)
    result = response.json()
    assert result["target_definition"] == "referred=Yes AND upsell=1 AND ltv_months>=34"
    assert result["population_definition"] == "purchased=1"


def test_unobserved_budget_sets_low_evidence(authed_client):
    body = dict(EARLY_FUNNEL_INPUT_IN_DOMAIN, ad_budget=3500)
    response = authed_client.post(PATH, json=body)
    result = response.json()
    assert result["event_probability"] is not None
    assert result["evidence_level"] == "low"
    assert result["warnings"][0]["code"] == "unobserved_budget_level"


# ---------------------------------------------------------------------------
# Criterion 74 (P4S variant) -- OOD never loads the joblib artifact.
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
    body = dict(EARLY_FUNNEL_INPUT_IN_DOMAIN, ad_budget=25000)
    authed_client.post(PATH, json=body)
    assert calls == []
    reset_artifact_cache_for_tests()
