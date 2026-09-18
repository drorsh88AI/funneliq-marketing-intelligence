"""Phase 11 checkpoint 11 -- response fixtures for e2e/'s route() mocks.

PHASE11.md §ו: "מודמים ב-route() עם fixtures שנגזרים מ-app/schemas.py/
app/auth.py". Every business-response builder here instantiates the
REAL pydantic model from app/schemas.py and calls .model_dump(mode=
"json") -- never a hand-typed dict -- so a fixture can never silently
drift from the locked contract; if a field is renamed or a constraint
tightens, these builders fail loudly at fixture-construction time, not
by quietly feeding the frontend a shape the real API could never send.
"""
from __future__ import annotations

import json
import time
from typing import Any

from app.schemas import (
    BudgetAllocation,
    BudgetSimulation,
    BudgetTiersResponse,
    CallsBucket,
    CallsDistribution,
    ClassificationMetrics,
    FollowupResponse,
    FunnelStage,
    IntervalDetails,
    LtvPrediction,
    OODWarning,
    PartError,
    PropensityPrediction,
    RegressionMetrics,
    StrategyResult,
    SuperCustomerOODWarning,
    SuperCustomerPrediction,
    TierRow,
    UnobservedBudgetWarning,
)


def _dump(model) -> dict[str, Any]:
    return json.loads(model.model_dump_json())


# ---------------------------------------------------------------------
# Auth (app/auth.py's own two probes + the Supabase Auth token/logout
# shapes supabase-js itself expects -- verified empirically against the
# real, unmodified library, not assumed from memory. See the commit
# history for the diagnostic runs that confirmed these exact shapes.)
# ---------------------------------------------------------------------

def supabase_user(*, user_id: str = "user-1", email: str = "demo@example.com", organization: str | None = "northbound", role: str = "analyst") -> dict:
    app_metadata: dict[str, Any] = {"role": role}
    if organization is not None:
        app_metadata["organization"] = organization
    return {
        "id": user_id,
        "aud": "authenticated",
        "role": "authenticated",
        "email": email,
        "app_metadata": app_metadata,
        "user_metadata": {},
        "created_at": "2026-01-01T00:00:00Z",
    }


def supabase_token_response(*, access_token: str = "fake-access-token-1", refresh_token: str = "fake-refresh-token-1", user: dict | None = None) -> dict:
    return {
        "access_token": access_token,
        "token_type": "bearer",
        "expires_in": 3600,
        "expires_at": int(time.time()) + 3600,
        "refresh_token": refresh_token,
        "user": user or supabase_user(),
    }


def api_me(*, email: str = "demo@example.com", organization: str | None = "northbound", role: str = "analyst") -> dict:
    """GET /api/me's own response shape (app/auth.py's get_me/
    current_user -- a plain dict, not one of app/schemas.py's
    ContractModel classes, since this route predates the phase-8/8A
    contract and is intentionally outside it)."""
    return {"email": email, "organization": organization, "role": role}


# ---------------------------------------------------------------------
# Overview
# ---------------------------------------------------------------------

def budget_tiers_response(rates: dict[str, float | None] | None = None) -> dict:
    """`rates`: {"Low": 0.045, "Mid": 0.082, "High": 0.054} by default --
    the project's own frozen, non-monotonic reference values (IA.md §1's
    own worked example)."""
    rates = rates if rates is not None else {"Low": 0.045, "Mid": 0.082, "High": 0.054}
    order = {"Low": 1, "Mid": 2, "High": 3}
    tiers = [
        TierRow(tier_order=order[name], budget_tier=name, n_records=100, conversion_rate=rate)
        for name, rate in rates.items()
    ]
    return _dump(BudgetTiersResponse(tiers=tiers))


def budget_tiers_empty() -> dict:
    return _dump(BudgetTiersResponse(tiers=[]))


# ---------------------------------------------------------------------
# Shared prediction form (P2/P3/P4)
# ---------------------------------------------------------------------

def _regression_metrics() -> RegressionMetrics:
    return RegressionMetrics.model_validate({
        "cv": {"mean_mae": 2.1, "mean_rmse": 3.2, "mean_r2": 0.42},
        "holdout": {"mae": 2.3, "rmse": 3.4, "r2": 0.40},
    })


def _classification_metrics() -> ClassificationMetrics:
    return ClassificationMetrics.model_validate({
        "cv": {"mean_roc_auc": 0.78, "mean_pr_auc": 0.35, "mean_brier": 0.15, "mean_log_loss": 0.45},
        "holdout": {"roc_auc": 0.80, "pr_auc": 0.37, "brier": 0.14, "log_loss": 0.43},
    })


def ood_warning(feature: str, value: float, lo: float, hi: float) -> OODWarning:
    return OODWarning(code="ood_feature_out_of_range", message=f"{feature} מחוץ לטווח האימון", feature=feature, value=value, min=lo, max=hi)


def unobserved_budget_warning(value: float = 750) -> UnobservedBudgetWarning:
    return UnobservedBudgetWarning(code="unobserved_budget_level", message="רמת הוצאה זו לא נצפתה באימון", feature="ad_budget", value=value)


def ltv_prediction_success(*, point=24.0, lower=18.0, upper=30.0, evidence_level=None, warnings=None, model_version="P2-catboost-e2e") -> dict:
    m = LtvPrediction(
        point_estimate=point, lower_bound=lower, upper_bound=upper,
        interval_method="split_conformal",
        interval_details=IntervalDetails(nominal_coverage=0.9, measured_coverage=0.91),
        evidence_level=evidence_level, in_training_domain=True,
        warnings=warnings or [], model_version=model_version, model_algorithm="CatBoost",
        metrics=_regression_metrics(),
    )
    return _dump(m)


def ltv_prediction_ood(*, feature="num_leads", value=99999, lo=1, hi=500, model_version="P2-catboost-e2e") -> dict:
    m = LtvPrediction(
        point_estimate=None, lower_bound=None, upper_bound=None,
        interval_method="split_conformal",
        interval_details=IntervalDetails(nominal_coverage=0.9, measured_coverage=0.91),
        evidence_level=None, in_training_domain=False,
        warnings=[ood_warning(feature, value, lo, hi)],
        model_version=model_version, model_algorithm="CatBoost", metrics=_regression_metrics(),
    )
    return _dump(m)


def propensity_prediction_success(*, event_probability=0.55, base_rate=0.4635, band="above_base", calibration_status="calibrated", evidence_level=None, warnings=None, model_version="P3-xgboost-e2e") -> dict:
    m = PropensityPrediction(
        event_probability=event_probability, base_rate=base_rate, propensity_band=band,
        evidence_level=evidence_level, in_training_domain=True, warnings=warnings or [],
        model_version=model_version, model_algorithm="XGBoost",
        calibration_status=calibration_status, calibration_method="sigmoid",
        metrics=_classification_metrics(),
    )
    return _dump(m)


def propensity_prediction_ood(*, feature="num_leads", value=99999, lo=1, hi=500, base_rate=0.4635, model_version="P3-xgboost-e2e") -> dict:
    m = PropensityPrediction(
        event_probability=None, base_rate=base_rate, propensity_band=None,
        evidence_level=None, in_training_domain=False,
        warnings=[ood_warning(feature, value, lo, hi)],
        model_version=model_version, model_algorithm="XGBoost",
        calibration_status="uncalibrated", calibration_method="sigmoid",
        metrics=_classification_metrics(),
    )
    return _dump(m)


# ---------------------------------------------------------------------
# P4S
# ---------------------------------------------------------------------

def super_customer_prediction_success(*, event_probability=0.2, base_rate=0.1672, band="above_base", evidence_level=None, warnings=None, model_version="P4S-catboost-e2e") -> dict:
    m = SuperCustomerPrediction(
        event_probability=event_probability, base_rate=base_rate, propensity_band=band,
        evidence_level=evidence_level, in_training_domain=True, warnings=warnings or [],
        model_version=model_version, model_algorithm="CatBoost",
        calibration_status="calibrated", calibration_method="sigmoid",
        metrics=_classification_metrics(),
        target_definition="referred=Yes AND upsell=1 AND ltv_months>=34",
        population_definition="purchased=1",
    )
    return _dump(m)


def super_customer_prediction_ood(*, feature="num_leads", value=99999, lo=1, hi=500, base_rate=0.1672, model_version="P4S-catboost-e2e") -> dict:
    m = SuperCustomerPrediction(
        event_probability=None, base_rate=base_rate, propensity_band=None,
        evidence_level=None, in_training_domain=False,
        warnings=[SuperCustomerOODWarning(code="ood_feature_out_of_range", message=f"{feature} מחוץ לטווח האימון", feature=feature, value=value, min=lo, max=hi)],
        model_version=model_version, model_algorithm="CatBoost",
        calibration_status="calibrated", calibration_method="sigmoid",
        metrics=_classification_metrics(),
        target_definition="referred=Yes AND upsell=1 AND ltv_months>=34",
        population_definition="purchased=1",
    )
    return _dump(m)


# ---------------------------------------------------------------------
# Budget Simulator
# ---------------------------------------------------------------------

STRATEGY_ALLOCATIONS = {
    "2x20000_1x10000": [(20000, 2), (10000, 1)],
    "10x5000": [(5000, 10)],
    "25x2000": [(2000, 25)],
    "100x500": [(500, 100)],
}


def budget_simulation(*, top_two_overlap=True, model_version="P6-linear-e2e") -> dict:
    strategies = []
    profit_by_id = {"100x500": 789594.0, "25x2000": 530953.0, "10x5000": 227214.0, "2x20000_1x10000": 7642.0}
    ranges = {
        "100x500": (379299.0, 856634.0), "25x2000": (519335.0, 549756.0),
        "10x5000": (177031.0, 261079.0), "2x20000_1x10000": (477.0, 13981.0),
    }
    # IA.md §5's own real, documented per-level sample sizes -- high:
    # n>=200, medium: 50<=n<200, low: n<50; a multi-level strategy takes
    # the MIN across its own levels. Hand-picking a synthetic formula
    # here (an earlier version used max(c*3, 30)) produced an
    # evidence_level inconsistent with its own sample_size, caught by
    # the real schema's own cross-field validator -- exactly what
    # deriving fixtures from app/schemas.py exists to catch.
    sample_sizes = {"100x500": [92], "25x2000": [322], "10x5000": [249], "2x20000_1x10000": [57, 161]}
    evidence = {"100x500": "medium", "25x2000": "high", "10x5000": "high", "2x20000_1x10000": "medium"}
    for rank, sid in enumerate(["100x500", "25x2000", "10x5000", "2x20000_1x10000"], start=1):
        allocations = [
            BudgetAllocation(ad_budget=b, count=c, sample_size=n)
            for (b, c), n in zip(STRATEGY_ALLOCATIONS[sid], sample_sizes[sid])
        ]
        lo, hi = ranges[sid]
        strategies.append(StrategyResult(
            strategy_id=sid, rank=rank, allocations=allocations,
            point_estimate=profit_by_id[sid], lower_bound=lo, upper_bound=hi,
            bootstrap_iterations=1000, evidence_level=evidence[sid],
            in_training_domain=True, warnings=[],
        ))
    m = BudgetSimulation(
        total_budget=50000, interval_method="bootstrap_percentile", bootstrap_percentiles=(2.5, 97.5),
        top_two_overlap=top_two_overlap, strategies=strategies,
        model_version=model_version, model_algorithm="LinearRegression",
        metrics=_regression_metrics(),
    )
    return _dump(m)


# ---------------------------------------------------------------------
# Follow-up
# ---------------------------------------------------------------------

def followup_stages_available(rates=(0.217, 0.257, 0.186, 0.104, 0.292)) -> dict:
    leads = 10000
    rows = []
    for i, rate in enumerate(rates, start=1):
        from_leads = leads
        to_leads = round(from_leads * (1 - rate))
        rows.append(FunnelStage(stage_order=i, stage=f"followup_{i}", from_leads=from_leads, to_leads=to_leads, drop_rate=round(1 - to_leads / from_leads, 10)))
        leads = to_leads
    part = {"status": "available", "data": [_dump(r) for r in rows]}
    return part


def followup_stages_unavailable(message="נתוני הנשירה אינם זמינים כרגע.") -> dict:
    return {"status": "unavailable", "error": _dump(PartError(reason_code="data_unavailable", message=message))}


def followup_calls_available(buckets: list[tuple[int, int]] | None = None) -> dict:
    buckets = buckets or [(0, 200), (1, 400), (2, 900), (3, 700), (4, 600), (5, 300), (6, 150), (7, 40), (8, 20), (9, 8)]
    population_n = sum(n for _, n in buckets)
    dist = CallsDistribution(population_n=population_n, distribution=[CallsBucket(calls=c, n=n) for c, n in buckets])
    return {"status": "available", "data": _dump(dist)}


def followup_calls_unavailable(message="נתוני מספר השיחות אינם זמינים כרגע.") -> dict:
    return {"status": "unavailable", "error": _dump(PartError(reason_code="aggregation_mismatch", message=message))}


def followup_response(*, stages=None, calls=None) -> dict:
    stages = stages if stages is not None else followup_stages_available()
    calls = calls if calls is not None else followup_calls_available()
    # FollowupResponse itself validates the discriminated unions; build
    # it from the two parts to fail loudly if either part shape drifts.
    payload = {"stages": stages, "calls_to_closed": calls}
    FollowupResponse.model_validate(payload)  # raises if either part is contract-invalid
    return payload
