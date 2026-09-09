"""Phase 8A checkpoint 9 -- direct-instantiation tests for the P4S schema
additions (PHASE8A.md D19/D20), same style as test_api_contract.py's own
structural checks but exercising pydantic validation directly rather than
through the exported OpenAPI document.
"""
from typing import Annotated, Union

import pytest
from pydantic import BaseModel, Field, ValidationError

from app.schemas import (
    ClassificationMetrics,
    EarlyFunnelInput,
    OODWarning,
    SuperCustomerOODWarning,
    SuperCustomerPrediction,
)

_METRICS = {
    "cv": {"mean_roc_auc": 0.7, "mean_pr_auc": 0.5, "mean_brier": 0.1, "mean_log_loss": 0.3},
    "holdout": {"roc_auc": 0.7, "pr_auc": 0.5, "brier": 0.1, "log_loss": 0.3},
}
_BASE_PREDICTION_FIELDS = dict(
    base_rate=0.1672,
    evidence_level=None,
    model_version="P4S-catboost-20260909-abc1234",
    model_algorithm="catboost",
    calibration_method="sigmoid",
    metrics=_METRICS,
    target_definition="referred=Yes AND upsell=1 AND ltv_months>=34",
    population_definition="purchased=1",
)


def test_metrics_block_is_the_shared_classification_metrics_type():
    ClassificationMetrics(**_METRICS)


def test_super_customer_ood_warning_is_an_oodwarning_instance():
    """D19/criterion 21: isinstance-based invariants (e.g.
    _check_ood_and_evidence_invariants) must keep recognizing this
    subclass as an OODWarning."""
    w = SuperCustomerOODWarning(
        code="ood_feature_out_of_range", message="x", feature="ad_budget", value=1.0, min=500.0, max=20000.0,
    )
    assert isinstance(w, OODWarning)


def test_super_customer_ood_warning_rejects_a_non_early_funnel_feature_name():
    """D19: the enum is narrowed to the 4 P4S inputs -- one of the other
    9 OODWarning.feature names must be rejected."""
    with pytest.raises(ValidationError):
        SuperCustomerOODWarning(
            code="ood_feature_out_of_range", message="x", feature="closed", value=1.0, min=0.0, max=10.0,
        )


def test_mixing_oodwarning_and_super_customer_oodwarning_in_one_union_raises_typeerror():
    """D19/criterion 22: both carry code='ood_feature_out_of_range', so a
    discriminated union containing both must fail at class-definition
    time -- this is exactly why SuperCustomerContractWarning is a
    SEPARATE union from ContractWarning, never a widened one."""
    with pytest.raises(TypeError):
        class _Bad(BaseModel):
            w: Annotated[Union[OODWarning, SuperCustomerOODWarning], Field(discriminator="code")]


def test_early_funnel_input_enforces_the_funnel_ordering_rules():
    with pytest.raises(ValidationError):
        EarlyFunnelInput(ad_budget=1000, num_leads=5, leads_answered=3, followup_1=4)
    with pytest.raises(ValidationError):
        EarlyFunnelInput(ad_budget=1000, num_leads=0, leads_answered=0, followup_1=0)
    with pytest.raises(ValidationError):
        EarlyFunnelInput(ad_budget=1000, num_leads=5, leads_answered=6, followup_1=0)
    ok = EarlyFunnelInput(ad_budget=1000, num_leads=5, leads_answered=3, followup_1=2)
    assert ok.leads_answered == 3


def test_super_customer_prediction_builds_with_a_valid_payload():
    pred = SuperCustomerPrediction(
        event_probability=0.2, propensity_band="above_base", in_training_domain=True,
        warnings=[], calibration_status="calibrated", **_BASE_PREDICTION_FIELDS,
    )
    assert pred.calibration_status == "calibrated"


def test_super_customer_prediction_rejects_uncalibrated():
    """D10/criterion 11: no uncalibrated fallback is ever deployable for
    P4S -- narrower than PropensityPrediction, which still allows it."""
    with pytest.raises(ValidationError):
        SuperCustomerPrediction(
            event_probability=0.2, propensity_band="above_base", in_training_domain=True,
            warnings=[], calibration_status="uncalibrated", **_BASE_PREDICTION_FIELDS,
        )


def test_super_customer_prediction_warnings_accept_the_narrowed_ood_warning():
    ood = SuperCustomerOODWarning(
        code="ood_feature_out_of_range", message="x", feature="num_leads", value=-1.0, min=0.0, max=200.0,
    )
    pred = SuperCustomerPrediction(
        event_probability=None, propensity_band=None, in_training_domain=False,
        warnings=[ood], calibration_status="calibrated", **_BASE_PREDICTION_FIELDS,
    )
    assert pred.warnings[0].feature == "num_leads"
