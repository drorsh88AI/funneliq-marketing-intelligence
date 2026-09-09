"""Phase 9 -- the five prediction/simulation routes (PHASE9.md D1):
POST /api/predict/ltv, /api/predict/upsell, /api/predict/referral,
/api/predict/super-customer (checkpoint 6), and GET /api/simulate/budget
(checkpoint 8).

Each POST route follows the same shape (D9): assess the request against
the artifact's ood_bounds BEFORE touching the model (app.inference's
out_of_range_features/predict_if_in_domain) -- an out-of-range feature
returns immediately with every prediction field null and an OODWarning,
never loading the joblib artifact. In-domain requests get a real
prediction; a failure loading or running the model (ArtifactLoadError) is
deliberately NOT caught here -- it propagates to app.main's generic
Exception handler, which already returns the correct 500 ErrorDetail body
(D7) without this file needing its own try/except for it.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends

from app.api_contract import ERROR_RESPONSES
from app.artifacts import get_assets
from app.auth import bearer, current_user
from app.inference import out_of_range_features, predict_if_in_domain
from app.schemas import (
    ClassificationMetrics,
    EarlyFunnelInput,
    FunnelInput,
    IntervalDetails,
    LtvPrediction,
    OODWarning,
    PropensityPrediction,
    RegressionMetrics,
    SuperCustomerOODWarning,
    SuperCustomerPrediction,
    UnobservedBudgetWarning,
    _CvClassification,
    _CvRegression,
    _HoldoutClassification,
    _HoldoutRegression,
)
from app.schemas import propensity_band_for
from app.inference import conformal_interval

router = APIRouter()


def _ood_warnings(meta: dict, out_of_range: list[str], values: dict, warning_cls: type) -> list:
    """One OODWarning (or the task-specific subclass, D15) per feature
    outside meta["ood_bounds"] -- min/max/value read straight from meta,
    never hand-typed."""
    result = []
    for feature in out_of_range:
        bounds = meta["ood_bounds"][feature]
        result.append(
            warning_cls(
                code="ood_feature_out_of_range",
                message=f"{feature} is outside the observed training range",
                feature=feature,
                value=float(values[feature]),
                min=float(bounds["min"]),
                max=float(bounds["max"]),
            )
        )
    return result


def _assess(task: str, meta: dict, values: dict, warning_cls: type) -> tuple[list, bool, str | None]:
    """PHASE9.md D9/D15: the OOD-and-evidence assessment, done entirely
    from meta -- no model touched. Returns (warnings, in_training_domain,
    evidence_level). `warning_cls` is OODWarning for P2/P3/P4,
    SuperCustomerOODWarning for P4S (checkpoint 6) -- never widened into
    the same discriminated union (PHASE8A.md D19)."""
    out_of_range = out_of_range_features(meta, values)
    warnings = _ood_warnings(meta, out_of_range, values, warning_cls)
    in_training_domain = not out_of_range

    evidence_level = None
    if in_training_domain:
        ad_budget = values["ad_budget"]
        if float(ad_budget) not in meta["observed_ad_budget_values"]:
            evidence_level = "low"
            warnings.append(
                UnobservedBudgetWarning(
                    code="unobserved_budget_level",
                    message=f"ad_budget={ad_budget} is within range but was not one of the observed training values",
                    feature="ad_budget",
                    value=float(ad_budget),
                )
            )
    return warnings, in_training_domain, evidence_level


def _regression_metrics(metrics_json: dict, task: str, algo: str) -> RegressionMetrics:
    cv = metrics_json[task][algo]
    holdout = metrics_json[f"{task}_holdout"]
    return RegressionMetrics(
        cv=_CvRegression(mean_mae=cv["mean_mae"], mean_rmse=cv["mean_rmse"], mean_r2=cv["mean_r2"]),
        holdout=_HoldoutRegression(mae=holdout["mae"], rmse=holdout["rmse"], r2=holdout["r2"]),
    )


def _classification_metrics(metrics_json: dict, task: str, algo: str) -> ClassificationMetrics:
    cv = metrics_json[task][algo]
    holdout = metrics_json[f"{task}_holdout"]
    return ClassificationMetrics(
        cv=_CvClassification(
            mean_roc_auc=cv["mean_roc_auc"], mean_pr_auc=cv["mean_pr_auc"],
            mean_brier=cv["mean_brier"], mean_log_loss=cv["mean_log_loss"],
        ),
        holdout=_HoldoutClassification(
            roc_auc=holdout["roc_auc"], pr_auc=holdout["pr_auc"],
            brier=holdout["brier"], log_loss=holdout["log_loss"],
        ),
    )


@router.post(
    "/api/predict/ltv",
    response_model=LtvPrediction,
    dependencies=[Depends(bearer)],
    responses=ERROR_RESPONSES,
)
def predict_ltv(body: FunnelInput, user: dict = Depends(current_user)) -> LtvPrediction:
    assets = get_assets()
    meta = assets["meta"]["P2"]
    values = body.model_dump()
    warnings, in_domain, evidence_level = _assess("P2", meta, values, OODWarning)
    metrics_block = _regression_metrics(assets["metrics"], "P2", meta["algo"])
    interval_details = IntervalDetails(
        nominal_coverage=1 - meta["alpha"],
        measured_coverage=assets["metrics"]["P2_holdout"]["conformal_coverage"],
    )

    if not in_domain:
        return LtvPrediction(
            point_estimate=None, lower_bound=None, upper_bound=None,
            interval_method="split_conformal", interval_details=interval_details,
            evidence_level=evidence_level, in_training_domain=False, warnings=warnings,
            model_version=meta["model_version"], model_algorithm=meta["algo"],
            metrics=metrics_block,
        )

    _, raw = predict_if_in_domain("P2", meta, values, method="predict")
    point_estimate = float(raw[0])
    lower_bound, upper_bound = conformal_interval(point_estimate, meta["conformal_quantile"])

    return LtvPrediction(
        point_estimate=point_estimate, lower_bound=lower_bound, upper_bound=upper_bound,
        interval_method="split_conformal", interval_details=interval_details,
        evidence_level=evidence_level, in_training_domain=True, warnings=warnings,
        model_version=meta["model_version"], model_algorithm=meta["algo"],
        metrics=metrics_block,
    )


def _predict_propensity(task: str, body: FunnelInput) -> PropensityPrediction:
    """Shared body for /api/predict/upsell (P3) and /api/predict/referral
    (P4) -- same PropensityPrediction response family, different artifact
    and base_rate (PHASE8.md ד.0: "אותה סכמה, שני ארטיפקטים שונים")."""
    assets = get_assets()
    meta = assets["meta"][task]
    values = body.model_dump()
    warnings, in_domain, evidence_level = _assess(task, meta, values, OODWarning)
    metrics_block = _classification_metrics(assets["metrics"], task, meta["algo"])
    base_rate = meta["base_rate"]

    if not in_domain:
        return PropensityPrediction(
            event_probability=None, base_rate=base_rate, propensity_band=None,
            evidence_level=evidence_level, in_training_domain=False, warnings=warnings,
            model_version=meta["model_version"], model_algorithm=meta["algo"],
            calibration_status=meta["calibration_status"], calibration_method=meta["calibration_method"],
            metrics=metrics_block,
        )

    _, raw = predict_if_in_domain(task, meta, values, method="predict_proba")
    event_probability = float(raw[0][1])
    propensity_band = propensity_band_for(event_probability, base_rate)

    return PropensityPrediction(
        event_probability=event_probability, base_rate=base_rate, propensity_band=propensity_band,
        evidence_level=evidence_level, in_training_domain=True, warnings=warnings,
        model_version=meta["model_version"], model_algorithm=meta["algo"],
        calibration_status=meta["calibration_status"], calibration_method=meta["calibration_method"],
        metrics=metrics_block,
    )


@router.post(
    "/api/predict/upsell",
    response_model=PropensityPrediction,
    dependencies=[Depends(bearer)],
    responses=ERROR_RESPONSES,
)
def predict_upsell(body: FunnelInput, user: dict = Depends(current_user)) -> PropensityPrediction:
    return _predict_propensity("P3", body)


@router.post(
    "/api/predict/referral",
    response_model=PropensityPrediction,
    dependencies=[Depends(bearer)],
    responses=ERROR_RESPONSES,
)
def predict_referral(body: FunnelInput, user: dict = Depends(current_user)) -> PropensityPrediction:
    return _predict_propensity("P4", body)


# PHASE8A.md D14/D19 -- fixed literals, not read from any artifact: the
# label formula and the population P4S trains on. Locked at the schema
# level too (SuperCustomerPrediction.target_definition/population_definition
# are each a one-value Literal) -- these are the only values that pass.
_P4S_TARGET_DEFINITION = "referred=Yes AND upsell=1 AND ltv_months>=34"
_P4S_POPULATION_DEFINITION = "purchased=1"


@router.post(
    "/api/predict/super-customer",
    response_model=SuperCustomerPrediction,
    dependencies=[Depends(bearer)],
    responses=ERROR_RESPONSES,
)
def predict_super_customer(
    body: EarlyFunnelInput, user: dict = Depends(current_user)
) -> SuperCustomerPrediction:
    """PHASE8A.md D20: mirrors _predict_propensity's shape, with P4S's own
    artifact/meta, SuperCustomerOODWarning instead of OODWarning (D15/D19
    -- a subclass, never folded into the same discriminated union as the
    other three tasks'), and the two fixed definition literals."""
    assets = get_assets()
    meta = assets["meta"]["P4S"]
    values = body.model_dump()
    warnings, in_domain, evidence_level = _assess("P4S", meta, values, SuperCustomerOODWarning)
    metrics_block = _classification_metrics(assets["metrics"], "P4S", meta["algo"])
    base_rate = meta["base_rate"]

    if not in_domain:
        return SuperCustomerPrediction(
            event_probability=None, base_rate=base_rate, propensity_band=None,
            evidence_level=evidence_level, in_training_domain=False, warnings=warnings,
            model_version=meta["model_version"], model_algorithm=meta["algo"],
            calibration_status=meta["calibration_status"], calibration_method=meta["calibration_method"],
            metrics=metrics_block,
            target_definition=_P4S_TARGET_DEFINITION, population_definition=_P4S_POPULATION_DEFINITION,
        )

    _, raw = predict_if_in_domain("P4S", meta, values, method="predict_proba")
    event_probability = float(raw[0][1])
    propensity_band = propensity_band_for(event_probability, base_rate)

    return SuperCustomerPrediction(
        event_probability=event_probability, base_rate=base_rate, propensity_band=propensity_band,
        evidence_level=evidence_level, in_training_domain=True, warnings=warnings,
        model_version=meta["model_version"], model_algorithm=meta["algo"],
        calibration_status=meta["calibration_status"], calibration_method=meta["calibration_method"],
        metrics=metrics_block,
        target_definition=_P4S_TARGET_DEFINITION, population_definition=_P4S_POPULATION_DEFINITION,
    )
