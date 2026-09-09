"""Phase 8 -- the locked API contract (docs/planning/PHASE8.md).

Pure Pydantic models: request/response shape, field types, nullability,
and every cross-field invariant that is derivable from the payload alone
(sections D1-D13, section D "סכמות מדויקות"). Zero I/O, zero model
loading, zero Supabase calls -- phase 9 fills these schemas in with real
predictions. scripts/export_openapi.py is the only other file that
imports from here (to register the six locked routes and produce
docs/api/openapi.json); app/main.py never imports this module (D1).

Six business endpoints, five response families, no "one model with 14
nullable fields" (D4) -- a field that is not relevant to a task's schema
does not appear in that schema at all, rather than appearing as null.
"""
from __future__ import annotations

from typing import Annotated, Generic, Literal, TypeVar, Union

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.features import MODEL_INPUT_FEATURES, STRATEGY_ALLOCATIONS

# ---------------------------------------------------------------------------
# D.0b -- shared model policy.
#
# extra="forbid": the pydantic v2 default (`ignore`) silently accepts
# extra fields. allow_inf_nan=False: the default silently accepts inf/nan
# in float fields, neither of which is valid JSON. Both verified empirically
# against pydantic 2.13.4 during planning (PHASE8.md D.0b).
#
# strict is per-FIELD (StrictInt/StrictBool), never per-model, for every
# model that mixes int/bool with float: ConfigDict(strict=True) applies to
# ALL fields on a model, including float ones -- verified it rejects
# f="2.5" on a strict float field, which would make every metrics.* field
# unusable. FunnelInput is the one exception: all 13 of its fields are
# int, so model-level strict is both correct and simpler there.
# ---------------------------------------------------------------------------


class ContractModel(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)


StrictInt = Annotated[int, Field(strict=True)]
StrictBool = Annotated[bool, Field(strict=True)]

# The 13 P2/P3/P4 model-input feature names, in MODEL_INPUT_FEATURES order
# -- OODWarning.feature is drawn from this enum, never a hand-typed string
# (D.7). P2/P3/P4 share the same 13 names in the same order (verified,
# section B finding 1); P6's 14-name list includes `purchased`, which is
# never a user-facing OOD feature, so P6 is deliberately not the source.
_INPUT_FEATURE_NAMES = tuple(MODEL_INPUT_FEATURES["P2"])
InputFeatureName = Literal[_INPUT_FEATURE_NAMES]


def _evidence_level_from_n(n: int) -> Literal["high", "medium", "low"]:
    """D2's P6 thresholds -- a decision from phase 7, not a stored field
    in any artifact. n>=200 high, 50<=n<200 medium, n<50 low."""
    if n >= 200:
        return "high"
    if n >= 50:
        return "medium"
    return "low"


def _propensity_band(event_probability: float, base_rate: float) -> Literal["below_base", "near_base", "above_base"]:
    """IA.md §4's three thresholds, always against the exact base_rate
    from meta.json, never the rounded display value (D.3)."""
    if event_probability < 0.9 * base_rate:
        return "below_base"
    if event_probability > 1.1 * base_rate:
        return "above_base"
    return "near_base"


# ---------------------------------------------------------------------------
# D.1 -- request body for the three predict/* routes.
# ---------------------------------------------------------------------------


class FunnelInput(ContractModel):
    """The 13 model-input features, all strict int, all >= 0. Model-level
    strict (ConfigDict) is correct here since every field is int -- see
    D.0b."""

    model_config = ConfigDict(extra="forbid", allow_inf_nan=False, strict=True)

    ad_budget: int = Field(ge=0)
    num_leads: int = Field(ge=0)
    leads_answered: int = Field(ge=0)
    followup_1: int = Field(ge=0)
    followup_2: int = Field(ge=0)
    followup_3: int = Field(ge=0)
    followup_4: int = Field(ge=0)
    followup_5: int = Field(ge=0)
    not_closed: int = Field(ge=0)
    closed: int = Field(ge=0)
    calls_to_closed: int = Field(ge=0)
    calls_to_not_closed: int = Field(ge=0)
    customer_acquisition_cost: int = Field(ge=0)

    @model_validator(mode="after")
    def _check_business_rules(self) -> "FunnelInput":
        """The five blocking validation rules (D.1) -- a violation is 422,
        never an OOD signal. Non-negativity (rule 5) is already enforced
        field-by-field via ge=0 above."""
        if self.num_leads <= 0:
            raise ValueError("num_leads must be > 0")
        if self.leads_answered > self.num_leads:
            raise ValueError("leads_answered must be <= num_leads")
        chain = [
            self.leads_answered,
            self.followup_1,
            self.followup_2,
            self.followup_3,
            self.followup_4,
            self.followup_5,
        ]
        if any(chain[i] < chain[i + 1] for i in range(len(chain) - 1)):
            raise ValueError(
                "leads_answered >= followup_1 >= followup_2 >= followup_3 "
                ">= followup_4 >= followup_5 must hold"
            )
        if self.closed + self.not_closed != self.followup_5:
            raise ValueError("closed + not_closed must equal followup_5")
        return self


# ---------------------------------------------------------------------------
# PHASE8A.md D20 -- EarlyFunnelInput (P4S): the same 4 columns as
# EARLY_FUNNEL_FEATURES (app/features.py), not the 13-field FunnelInput --
# P4S is served from campaign-level early-funnel signals only.
# ---------------------------------------------------------------------------


class EarlyFunnelInput(ContractModel):
    """P4S's request body -- ad_budget/num_leads/leads_answered/followup_1
    only, mirroring FunnelInput's shape at a smaller size."""

    model_config = ConfigDict(extra="forbid", allow_inf_nan=False, strict=True)

    ad_budget: int = Field(ge=0)
    num_leads: int = Field(ge=0)
    leads_answered: int = Field(ge=0)
    followup_1: int = Field(ge=0)

    @model_validator(mode="after")
    def _check_business_rules(self) -> "EarlyFunnelInput":
        """Same funnel-ordering rules as FunnelInput's own chain, truncated
        to the fields P4S actually has."""
        if self.num_leads <= 0:
            raise ValueError("num_leads must be > 0")
        if self.leads_answered > self.num_leads:
            raise ValueError("leads_answered must be <= num_leads")
        if self.followup_1 > self.leads_answered:
            raise ValueError("followup_1 must be <= leads_answered")
        return self


# ---------------------------------------------------------------------------
# D.7 -- warnings: a discriminated union, never a string array or a single
# model with optional fields (D3).
# ---------------------------------------------------------------------------


class OODWarning(ContractModel):
    code: Literal["ood_feature_out_of_range"]
    message: str = Field(min_length=1)
    feature: InputFeatureName
    value: float
    min: float
    max: float

    @model_validator(mode="after")
    def _check_bounds(self) -> "OODWarning":
        """D.8g rule 15: min<=max, and value must actually be outside the
        range -- an OOD warning whose value sits inside [min, max] is a
        contradiction."""
        if self.min > self.max:
            raise ValueError("min must be <= max")
        if self.min <= self.value <= self.max:
            raise ValueError("value must be outside [min, max] for an OOD warning")
        return self


class UnobservedBudgetWarning(ContractModel):
    code: Literal["unobserved_budget_level"]
    message: str = Field(min_length=1)
    feature: Literal["ad_budget"]
    value: float = Field(gt=0)


ContractWarning = Annotated[Union[OODWarning, UnobservedBudgetWarning], Field(discriminator="code")]


class SuperCustomerOODWarning(OODWarning):
    """PHASE8A.md D19/D12: P4S's own OOD warning, narrowed to its 4
    input features -- a SUBCLASS of OODWarning (not a member of the
    same ContractWarning union), so `isinstance(w, OODWarning)` keeps
    returning True for it and _check_ood_and_evidence_invariants below
    keeps working unchanged. Verified during planning: putting
    OODWarning and this class in the SAME discriminated union raises
    TypeError at class-definition time (both carry
    code="ood_feature_out_of_range") -- ContractWarning above must
    never be widened to include this class."""

    feature: Literal["ad_budget", "num_leads", "leads_answered", "followup_1"]


SuperCustomerContractWarning = Annotated[
    Union[SuperCustomerOODWarning, UnobservedBudgetWarning], Field(discriminator="code")
]


def _has_ood_warning(warnings: list) -> bool:
    return any(isinstance(w, OODWarning) for w in warnings)


def _has_unobserved_budget_warning(warnings: list) -> bool:
    return any(isinstance(w, UnobservedBudgetWarning) for w in warnings)


def _check_ood_and_evidence_invariants(
    *,
    in_training_domain: bool,
    prediction_fields: list,
    warnings: list,
    evidence_level: str | None,
) -> None:
    """D.8's six invariants, shared by LtvPrediction and
    PropensityPrediction -- the only difference between the two callers is
    which fields count as "the prediction". Two independent biconditionals
    (D.8): in_training_domain=false <=> an OODWarning is present, and
    evidence_level="low" <=> an UnobservedBudgetWarning is present. A
    record can carry both warnings, one, or neither."""
    has_ood = _has_ood_warning(warnings)
    has_unobserved = _has_unobserved_budget_warning(warnings)

    if in_training_domain:
        if any(field is None for field in prediction_fields):
            raise ValueError("in_training_domain=true requires every prediction field to be non-null")
        if has_ood:
            raise ValueError("in_training_domain=true is incompatible with an OODWarning")
    else:
        if any(field is not None for field in prediction_fields):
            raise ValueError("in_training_domain=false requires every prediction field to be null")
        if not has_ood:
            raise ValueError("in_training_domain=false requires an OODWarning")

    if evidence_level == "low":
        if not has_unobserved:
            raise ValueError('evidence_level="low" requires an UnobservedBudgetWarning')
    elif evidence_level is None:
        if has_unobserved:
            raise ValueError("evidence_level=null is incompatible with an UnobservedBudgetWarning")


# ---------------------------------------------------------------------------
# D.7 -- metrics blocks: the winning algorithm's CV + Holdout numbers only
# (D6), no accuracy/n_holdout (not required by any screen).
# ---------------------------------------------------------------------------


class _CvRegression(ContractModel):
    mean_mae: float = Field(ge=0)
    mean_rmse: float = Field(ge=0)
    mean_r2: float = Field(le=1)


class _HoldoutRegression(ContractModel):
    mae: float = Field(ge=0)
    rmse: float = Field(ge=0)
    r2: float = Field(le=1)


class RegressionMetrics(ContractModel):
    """P2 and P6. r2 is bounded above by 1 and deliberately NOT bounded
    below -- a negative R2 (worse than the mean predictor) is a
    legitimate value."""

    cv: _CvRegression
    holdout: _HoldoutRegression


class _CvClassification(ContractModel):
    mean_roc_auc: float = Field(ge=0, le=1)
    mean_pr_auc: float = Field(ge=0, le=1)
    mean_brier: float = Field(ge=0, le=1)
    mean_log_loss: float = Field(ge=0)


class _HoldoutClassification(ContractModel):
    roc_auc: float = Field(ge=0, le=1)
    pr_auc: float = Field(ge=0, le=1)
    brier: float = Field(ge=0, le=1)
    log_loss: float = Field(ge=0)


class ClassificationMetrics(ContractModel):
    """P3 and P4. log_loss is bounded below by 0 and deliberately not
    bounded above."""

    cv: _CvClassification
    holdout: _HoldoutClassification


class IntervalDetails(ContractModel):
    """P2's conformal-coverage detail block -- a sub-model of
    LtvPrediction only (D7), not RegressionMetrics, which is shared with
    P6 and has no measured coverage of its own."""

    nominal_coverage: float = Field(ge=0, le=1)
    measured_coverage: float = Field(ge=0, le=1)


# ---------------------------------------------------------------------------
# D.2 -- LtvPrediction (P2). Covers contract fields 1,2,3,4,8,10,11,12.
# ---------------------------------------------------------------------------


class LtvPrediction(ContractModel):
    point_estimate: float | None
    lower_bound: float | None
    upper_bound: float | None
    interval_method: Literal["split_conformal"]
    interval_details: IntervalDetails
    evidence_level: Literal["low"] | None
    in_training_domain: StrictBool
    warnings: list[ContractWarning]
    model_version: str = Field(min_length=1)
    model_algorithm: str = Field(min_length=1)
    metrics: RegressionMetrics

    @model_validator(mode="after")
    def _check_invariants(self) -> "LtvPrediction":
        _check_ood_and_evidence_invariants(
            in_training_domain=self.in_training_domain,
            prediction_fields=[self.point_estimate, self.lower_bound, self.upper_bound],
            warnings=self.warnings,
            evidence_level=self.evidence_level,
        )
        # D.8g rule 11: lower <= point <= upper, checked only when all
        # three are populated (in_training_domain=true, per D.8 above).
        if self.point_estimate is not None and self.lower_bound is not None and self.upper_bound is not None:
            if not (self.lower_bound <= self.point_estimate <= self.upper_bound):
                raise ValueError("lower_bound <= point_estimate <= upper_bound must hold")
        return self


# ---------------------------------------------------------------------------
# D.3 -- PropensityPrediction (P3, P4). Covers contract fields
# 5,6,7,8,10,11,12,13,14. "Propensity", not "Probability" -- the field
# SPEC locks is propensity_band.
# ---------------------------------------------------------------------------


class PropensityPrediction(ContractModel):
    event_probability: float | None = Field(ge=0, le=1)
    base_rate: float = Field(ge=0, le=1)
    propensity_band: Literal["below_base", "near_base", "above_base"] | None
    evidence_level: Literal["low"] | None
    in_training_domain: StrictBool
    warnings: list[ContractWarning]
    model_version: str = Field(min_length=1)
    model_algorithm: str = Field(min_length=1)
    calibration_status: Literal["calibrated", "uncalibrated"]
    calibration_method: Literal["sigmoid"]
    metrics: ClassificationMetrics

    @model_validator(mode="after")
    def _check_invariants(self) -> "PropensityPrediction":
        _check_ood_and_evidence_invariants(
            in_training_domain=self.in_training_domain,
            prediction_fields=[self.event_probability, self.propensity_band],
            warnings=self.warnings,
            evidence_level=self.evidence_level,
        )
        # D.8g rule 13: propensity_band must match the IA.md §4 thresholds
        # applied to event_probability/base_rate, checked only when both
        # are populated.
        if self.event_probability is not None and self.propensity_band is not None:
            expected = _propensity_band(self.event_probability, self.base_rate)
            if expected != self.propensity_band:
                raise ValueError(
                    f"propensity_band={self.propensity_band!r} is inconsistent with "
                    f"event_probability={self.event_probability!r} and base_rate={self.base_rate!r} "
                    f"(expected {expected!r})"
                )
        return self


# ---------------------------------------------------------------------------
# PHASE8A.md D20 -- SuperCustomerPrediction (P4S). Mirrors
# PropensityPrediction's shape, with three deliberate differences: (a)
# warnings is SuperCustomerContractWarning, not ContractWarning (D19's
# narrowed feature enum); (b) calibration_status is narrowed to
# Literal["calibrated"] only (D10 -- no uncalibrated fallback is ever
# deployable for P4S); (c) target_definition/population_definition are
# required (D14 -- one without the other would mislead about what the
# score means).
# ---------------------------------------------------------------------------


class SuperCustomerPrediction(ContractModel):
    event_probability: float | None = Field(ge=0, le=1)
    base_rate: float = Field(ge=0, le=1)
    propensity_band: Literal["below_base", "near_base", "above_base"] | None
    evidence_level: Literal["low"] | None
    in_training_domain: StrictBool
    warnings: list[SuperCustomerContractWarning]
    model_version: str = Field(min_length=1)
    model_algorithm: str = Field(min_length=1)
    calibration_status: Literal["calibrated"]
    calibration_method: Literal["sigmoid"]
    metrics: ClassificationMetrics
    target_definition: Literal["referred=Yes AND upsell=1 AND ltv_months>=34"]
    population_definition: Literal["purchased=1"]

    @model_validator(mode="after")
    def _check_invariants(self) -> "SuperCustomerPrediction":
        _check_ood_and_evidence_invariants(
            in_training_domain=self.in_training_domain,
            prediction_fields=[self.event_probability, self.propensity_band],
            warnings=self.warnings,
            evidence_level=self.evidence_level,
        )
        if self.event_probability is not None and self.propensity_band is not None:
            expected = _propensity_band(self.event_probability, self.base_rate)
            if expected != self.propensity_band:
                raise ValueError(
                    f"propensity_band={self.propensity_band!r} is inconsistent with "
                    f"event_probability={self.event_probability!r} and base_rate={self.base_rate!r} "
                    f"(expected {expected!r})"
                )
        return self


# ---------------------------------------------------------------------------
# D.4 -- BudgetSimulation (P6). Covers contract fields
# 1,2,3,4,8,9,10,11,12 via StrategyResult / BudgetAllocation.
# ---------------------------------------------------------------------------


class BudgetAllocation(ContractModel):
    ad_budget: StrictInt = Field(gt=0)
    count: StrictInt = Field(gt=0)
    sample_size: StrictInt = Field(gt=0)


class StrategyResult(ContractModel):
    strategy_id: Literal["2x20000_1x10000", "10x5000", "25x2000", "100x500"]
    rank: StrictInt = Field(ge=1, le=4)
    allocations: list[BudgetAllocation] = Field(min_length=1, max_length=2)
    point_estimate: float = Field(ge=0)
    lower_bound: float = Field(ge=0)
    upper_bound: float = Field(ge=0)
    bootstrap_iterations: StrictInt = Field(gt=0)
    evidence_level: Literal["high", "medium", "low"]
    in_training_domain: Literal[True]
    warnings: list[ContractWarning] = Field(max_length=0)

    @field_validator("in_training_domain", mode="before")
    @classmethod
    def _validate_in_training_domain(cls, value: object) -> object:
        """Numeric/boolean Literal coercion is NOT guarded by strict=True
        (verified: Literal[True] still accepts 1 and 1.0 even under
        ConfigDict(strict=True) -- Literal is checked AFTER coercion).
        A before-validator is the only way to actually reject them."""
        if type(value) is not bool or value is not True:
            raise ValueError("in_training_domain must be exactly True")
        return value

    @model_validator(mode="after")
    def _check_invariants(self) -> "StrategyResult":
        # D.8g rule 12: lower <= upper only -- point is NOT required to
        # fall inside the bootstrap interval (P6_simulation.json computes
        # point/lower/upper independently; phase 6 makes no such claim).
        if not (self.lower_bound <= self.upper_bound):
            raise ValueError("lower_bound <= upper_bound must hold")
        # D.8g rule 14: evidence_level must match D2's thresholds applied
        # to the minimum sample_size across this strategy's allocations.
        min_n = min(allocation.sample_size for allocation in self.allocations)
        expected = _evidence_level_from_n(min_n)
        if expected != self.evidence_level:
            raise ValueError(
                f"evidence_level={self.evidence_level!r} is inconsistent with "
                f"min(sample_size)={min_n} (expected {expected!r})"
            )
        return self


class BudgetSimulation(ContractModel):
    total_budget: Literal[50000]
    interval_method: Literal["bootstrap_percentile"]
    bootstrap_percentiles: tuple[Literal[2.5], Literal[97.5]]
    top_two_overlap: StrictBool
    strategies: list[StrategyResult] = Field(min_length=4, max_length=4)
    model_version: str = Field(min_length=1)
    model_algorithm: str = Field(min_length=1)
    metrics: RegressionMetrics

    @field_validator("total_budget", mode="before")
    @classmethod
    def _validate_total_budget(cls, value: object) -> object:
        """Same Literal-coercion gap as in_training_domain above:
        Literal[50000] alone still accepts 50000.0 and (being an int
        subclass) True."""
        if type(value) is not int or value != 50000:
            raise ValueError("total_budget must be exactly the int 50000")
        return value

    @model_validator(mode="after")
    def _check_strategy_invariants(self) -> "BudgetSimulation":
        """D.8b rules 7-10 -- these need the full `strategies` list, so
        they live here rather than on StrategyResult itself."""
        ids = [strategy.strategy_id for strategy in self.strategies]
        expected_ids = set(STRATEGY_ALLOCATIONS)
        if set(ids) != expected_ids or len(ids) != len(expected_ids):
            raise ValueError(
                f"strategies must be exactly the four locked ids {sorted(expected_ids)}, "
                "no duplicates and no gaps"
            )

        ranks = [strategy.rank for strategy in self.strategies]
        if set(ranks) != {1, 2, 3, 4}:
            raise ValueError("rank must be unique and cover exactly {1,2,3,4}")

        for index, strategy in enumerate(self.strategies):
            if strategy.rank != index + 1:
                raise ValueError("strategies must be sorted by rank ascending")

        for strategy in self.strategies:
            expected_pairs = STRATEGY_ALLOCATIONS[strategy.strategy_id]
            actual_pairs = [(allocation.ad_budget, allocation.count) for allocation in strategy.allocations]
            if actual_pairs != expected_pairs:
                raise ValueError(
                    f"allocations for {strategy.strategy_id!r} must match STRATEGY_ALLOCATIONS "
                    f"exactly, in order: expected {expected_pairs}, got {actual_pairs}"
                )
        return self


# ---------------------------------------------------------------------------
# D.5 -- FollowupResponse. Each part is an explicit union on `status`
# (D12), never an empty array or null standing in for "unavailable".
# ---------------------------------------------------------------------------


class PartError(ContractModel):
    reason_code: Literal["data_unavailable", "aggregation_mismatch"]
    message: str = Field(min_length=1)


class PartUnavailable(ContractModel):
    status: Literal["unavailable"]
    error: PartError


_T = TypeVar("_T")


class AvailablePart(ContractModel, Generic[_T]):
    status: Literal["available"]
    data: _T


class FunnelStage(ContractModel):
    stage_order: StrictInt = Field(ge=1, le=5)
    stage: Literal["followup_1", "followup_2", "followup_3", "followup_4", "followup_5"]
    from_leads: StrictInt = Field(ge=0)
    to_leads: StrictInt = Field(ge=0)
    drop_rate: float | None = Field(ge=0, le=1)

    @model_validator(mode="after")
    def _check_row_invariants(self) -> "FunnelStage":
        """D.8g rules 17 and 19 -- both derivable from this row alone,
        mirroring followup_insight's own SQL exactly (nullif-guarded
        1 - to/from, tolerance 1e-9 for the float round-trip)."""
        if self.to_leads > self.from_leads:
            raise ValueError("to_leads must be <= from_leads")
        if self.from_leads == 0:
            if self.drop_rate is not None:
                raise ValueError("drop_rate must be null when from_leads == 0")
        else:
            if self.drop_rate is None:
                raise ValueError("drop_rate must not be null when from_leads > 0")
            expected = 1 - self.to_leads / self.from_leads
            if abs(self.drop_rate - expected) > 1e-9:
                raise ValueError(
                    f"drop_rate={self.drop_rate!r} is inconsistent with "
                    f"1 - to_leads/from_leads={expected!r}"
                )
        return self


_EXPECTED_STAGE_SEQUENCE = (
    (1, "followup_1"),
    (2, "followup_2"),
    (3, "followup_3"),
    (4, "followup_4"),
    (5, "followup_5"),
)


class StagesPart(AvailablePart[list[FunnelStage]]):
    """A specialized AvailablePart[list[FunnelStage]] carrying the
    list-level invariants (D.8g rules 16, 18) that the generic base
    cannot express: exactly 5 rows, in the fixed stage_order/stage
    sequence, chained to_leads[i] == from_leads[i+1] -- both mirror
    followup_insight's five fixed `union all` branches exactly."""

    data: list[FunnelStage] = Field(min_length=5, max_length=5)

    @model_validator(mode="after")
    def _check_sequence(self) -> "StagesPart":
        actual = tuple((stage.stage_order, stage.stage) for stage in self.data)
        if actual != _EXPECTED_STAGE_SEQUENCE:
            raise ValueError(
                f"stages must be exactly {_EXPECTED_STAGE_SEQUENCE} in order, got {actual}"
            )
        for index in range(4):
            if self.data[index].to_leads != self.data[index + 1].from_leads:
                raise ValueError(
                    f"to_leads of stage {index + 1} must equal from_leads of stage {index + 2}"
                )
        return self


class CallsBucket(ContractModel):
    calls: StrictInt = Field(ge=0)
    n: StrictInt = Field(gt=0)


class CallsDistribution(ContractModel):
    population_n: StrictInt = Field(gt=0)
    distribution: list[CallsBucket] = Field(min_length=1)

    @model_validator(mode="after")
    def _check_invariants(self) -> "CallsDistribution":
        """D.8g rule 20 -- internal consistency of THIS response only:
        the declared total against its own breakdown. Verifying that
        total against an independent Supabase count("exact") is phase 9
        (IA.md §7.1), and is what actually catches a paginated fetch that
        silently truncated."""
        calls_values = [bucket.calls for bucket in self.distribution]
        if len(calls_values) != len(set(calls_values)):
            raise ValueError("calls values in distribution must be unique")
        total = sum(bucket.n for bucket in self.distribution)
        if total != self.population_n:
            raise ValueError(
                f"sum(distribution[].n)={total} must equal population_n={self.population_n}"
            )
        return self


class CallsPart(AvailablePart[CallsDistribution]):
    pass


class FollowupResponse(ContractModel):
    """Neither of the 14 contract fields -- this is insight aggregation,
    not a prediction (D4)."""

    stages: Annotated[Union[StagesPart, PartUnavailable], Field(discriminator="status")]
    calls_to_closed: Annotated[Union[CallsPart, PartUnavailable], Field(discriminator="status")]


# ---------------------------------------------------------------------------
# D.6 -- BudgetTiersResponse. Package 1, not a prediction either.
# ---------------------------------------------------------------------------

_VALID_TIER_PAIRS = frozenset({(1, "Low"), (2, "Mid"), (3, "High"), (None, None)})


class TierRow(ContractModel):
    tier_order: Literal[1, 2, 3] | None
    budget_tier: Literal["Low", "Mid", "High"] | None
    n_records: StrictInt = Field(gt=0)
    conversion_rate: float | None = Field(ge=0, le=1)

    @field_validator("tier_order", mode="before")
    @classmethod
    def _validate_tier_order(cls, value: object) -> object:
        """Same Literal-coercion gap: Literal[1,2,3] | None alone would
        still accept True (bool is an int subclass) and 1.0."""
        if value is not None and type(value) is not int:
            raise ValueError("tier_order must be an int or null")
        return value

    @model_validator(mode="after")
    def _check_pair(self) -> "TierRow":
        """D.8g rule 21. A row with tier_order=null/budget_tier=null is a
        legitimate future value (the 1501-1999 CASE gap with no ELSE) --
        not observed in today's data (16 observed ad_budget values skip
        1500->2000 directly), but the schema must accept it."""
        pair = (self.tier_order, self.budget_tier)
        if pair not in _VALID_TIER_PAIRS:
            raise ValueError(f"(tier_order, budget_tier)={pair!r} is not one of the valid pairs")
        return self


class BudgetTiersResponse(ContractModel):
    tiers: list[TierRow] = Field(max_length=4)

    @model_validator(mode="after")
    def _check_no_duplicates(self) -> "BudgetTiersResponse":
        """D.8g rule 22 -- a duplicate (tier_order, budget_tier) pair in
        the same response is impossible from a `group by` on real data,
        but the schema forbids it explicitly rather than relying on that."""
        pairs = [(tier.tier_order, tier.budget_tier) for tier in self.tiers]
        if len(pairs) != len(set(pairs)):
            raise ValueError("tiers must not contain duplicate (tier_order, budget_tier) pairs")
        return self


# ---------------------------------------------------------------------------
# D.7 -- error schemas. HTTPValidationError is a deliberately narrow
# FunnelIQ contract (loc/msg/type only), NOT FastAPI's own default shape
# (which also carries ctx/input and varies across versions) -- phase 9
# owns a RequestValidationError handler that normalizes exc.errors() into
# this shape.
# ---------------------------------------------------------------------------


class ErrorDetail(ContractModel):
    """401 / 403 / 500 / 503."""

    detail: str = Field(min_length=1)


class ValidationErrorItem(ContractModel):
    loc: list[Union[str, StrictInt]] = Field(min_length=1)
    msg: str = Field(min_length=1)
    type: str = Field(min_length=1)


class HTTPValidationError(ContractModel):
    """422 only."""

    detail: list[ValidationErrorItem] = Field(min_length=1)
