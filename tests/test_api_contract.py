"""Phase 8 -- the 19 static acceptance-test groups locking the API
contract (docs/planning/PHASE8.md section ט).

Every test here is STATIC: no HTTP, no Auth, no model loading, no
Supabase. "Static" means one of two things: (a) inspecting the exported
docs/api/openapi.json / app/schemas.py JSON-Schema shape, or (b)
instantiating app.schemas models directly with hand-built payloads and
checking they accept/reject as the contract requires. Phase 9 is what
wires these schemas to real predictions.
"""
from __future__ import annotations

import json
import math
from pathlib import Path

import pytest
from pydantic import ValidationError

from app.features import MODEL_INPUT_FEATURES, STRATEGY_ALLOCATIONS
from app.schemas import (
    AvailablePart,
    BudgetAllocation,
    BudgetSimulation,
    BudgetTiersResponse,
    CallsBucket,
    CallsDistribution,
    ErrorDetail,
    FollowupResponse,
    FunnelInput,
    FunnelStage,
    HTTPValidationError,
    LtvPrediction,
    OODWarning,
    PropensityPrediction,
    StagesPart,
    StrategyResult,
    TierRow,
    UnobservedBudgetWarning,
    ValidationErrorItem,
)
from scripts.export_openapi import _serialize, export_schema

REPO_ROOT = Path(__file__).resolve().parent.parent
OPENAPI_PATH = REPO_ROOT / "docs" / "api" / "openapi.json"

SCHEMA: dict = json.loads(OPENAPI_PATH.read_text(encoding="utf-8"))
COMPONENT_SCHEMAS: dict = SCHEMA["components"]["schemas"]

BUSINESS_ROUTES = {
    ("post", "/api/predict/ltv"): "LtvPrediction",
    ("post", "/api/predict/upsell"): "PropensityPrediction",
    ("post", "/api/predict/referral"): "PropensityPrediction",
    ("get", "/api/simulate/budget"): "BudgetSimulation",
    ("get", "/api/insights/followup"): "FollowupResponse",
    ("get", "/api/insights/budget-tiers"): "BudgetTiersResponse",
}
POST_ROUTES = {(m, p) for (m, p) in BUSINESS_ROUTES if m == "post"}
GET_ROUTES = {(m, p) for (m, p) in BUSINESS_ROUTES if m == "get"}


# =============================================================================
# The canonical root-resolved-closure field-path algorithm (PHASE8.md ה.1).
# Operates purely on the OpenAPI JSON -- this is what makes criterion 5 test
# the actual artifact, not app/schemas.py's Python shape.
# =============================================================================


def _walk(node: dict, prefix: str, seen_refs: frozenset, results: set) -> None:
    if "$ref" in node:
        ref_name = node["$ref"].rsplit("/", 1)[-1]
        if ref_name in seen_refs:
            return  # cycle guard -- not exercised by this contract, kept for totality
        _closure(ref_name, prefix, seen_refs, results)
        return
    branches = node.get("oneOf") or node.get("anyOf")
    if branches is not None:
        for branch in branches:
            _walk(branch, prefix, seen_refs, results)
        return
    if "properties" in node:
        for prop_name, prop_schema in node["properties"].items():
            path = f"{prefix}.{prop_name}" if prefix else prop_name
            results.add(path)
            _walk(prop_schema, path, seen_refs, results)
        return
    if "items" in node:
        # A scalar-only array (e.g. bootstrap_percentiles' prefixItems) has
        # no "items" key at all and falls through to the leaf case below --
        # it is counted once, by its own property name, and never gets "[]".
        _walk(node["items"], f"{prefix}[]", seen_refs, results)
        return
    # leaf: plain scalar, or a prefixItems-only tuple -- no named children.


def _closure(schema_name: str, prefix: str, seen_refs: frozenset, results: set) -> None:
    _walk(COMPONENT_SCHEMAS[schema_name], prefix, seen_refs | {schema_name}, results)


def _root_closure(root_name: str) -> set[str]:
    """Root-resolved closure for one of the eight named roots. The root's
    own name is never part of any path (PHASE8.md ה.1 rule 6)."""
    results: set[str] = set()
    _closure(root_name, "", frozenset(), results)
    return results


# Hand-transcribed, independently of the algorithm above, straight from
# PHASE8.md section ה.1's per-root field lists -- this is what criterion 5
# actually compares the computed closure against.
ROOT_FIELD_MAPS: dict[str, set[str]] = {
    "FunnelInput": {
        "ad_budget", "num_leads", "leads_answered", "followup_1", "followup_2",
        "followup_3", "followup_4", "followup_5", "not_closed", "closed",
        "calls_to_closed", "calls_to_not_closed", "customer_acquisition_cost",
    },
    "LtvPrediction": {
        "point_estimate", "lower_bound", "upper_bound", "interval_method",
        "evidence_level", "in_training_domain", "warnings", "model_version",
        "interval_details", "interval_details.nominal_coverage", "interval_details.measured_coverage",
        "model_algorithm",
        "metrics", "metrics.cv", "metrics.cv.mean_mae", "metrics.cv.mean_rmse", "metrics.cv.mean_r2",
        "metrics.holdout", "metrics.holdout.mae", "metrics.holdout.rmse", "metrics.holdout.r2",
        "warnings[].code", "warnings[].message", "warnings[].feature",
        "warnings[].value", "warnings[].min", "warnings[].max",
    },
    "PropensityPrediction": {
        "event_probability", "base_rate", "propensity_band",
        "evidence_level", "in_training_domain", "warnings", "model_version",
        "calibration_status", "calibration_method",
        "model_algorithm",
        "metrics", "metrics.cv", "metrics.cv.mean_roc_auc", "metrics.cv.mean_pr_auc",
        "metrics.cv.mean_brier", "metrics.cv.mean_log_loss",
        "metrics.holdout", "metrics.holdout.roc_auc", "metrics.holdout.pr_auc",
        "metrics.holdout.brier", "metrics.holdout.log_loss",
        "warnings[].code", "warnings[].message", "warnings[].feature",
        "warnings[].value", "warnings[].min", "warnings[].max",
    },
    "BudgetSimulation": {
        "interval_method", "model_version",
        "total_budget", "bootstrap_percentiles", "top_two_overlap", "model_algorithm",
        "metrics", "metrics.cv", "metrics.cv.mean_mae", "metrics.cv.mean_rmse", "metrics.cv.mean_r2",
        "metrics.holdout", "metrics.holdout.mae", "metrics.holdout.rmse", "metrics.holdout.r2",
        "strategies",
        "strategies[].point_estimate", "strategies[].lower_bound", "strategies[].upper_bound",
        "strategies[].evidence_level", "strategies[].in_training_domain", "strategies[].warnings",
        "strategies[].strategy_id", "strategies[].rank", "strategies[].bootstrap_iterations",
        "strategies[].allocations",
        "strategies[].allocations[].sample_size",
        "strategies[].allocations[].ad_budget", "strategies[].allocations[].count",
        "strategies[].warnings[].code", "strategies[].warnings[].message",
        "strategies[].warnings[].feature", "strategies[].warnings[].value",
        "strategies[].warnings[].min", "strategies[].warnings[].max",
    },
    "FollowupResponse": {
        "stages", "stages.status", "stages.data",
        "stages.data[].stage_order", "stages.data[].stage",
        "stages.data[].from_leads", "stages.data[].to_leads", "stages.data[].drop_rate",
        "stages.error", "stages.error.reason_code", "stages.error.message",
        "calls_to_closed", "calls_to_closed.status", "calls_to_closed.data",
        "calls_to_closed.data.population_n", "calls_to_closed.data.distribution",
        "calls_to_closed.data.distribution[].calls", "calls_to_closed.data.distribution[].n",
        "calls_to_closed.error", "calls_to_closed.error.reason_code", "calls_to_closed.error.message",
    },
    "BudgetTiersResponse": {
        "tiers", "tiers[].tier_order", "tiers[].budget_tier",
        "tiers[].n_records", "tiers[].conversion_rate",
    },
    "ErrorDetail": {"detail"},
    "HTTPValidationError": {"detail", "detail[].loc", "detail[].msg", "detail[].type"},
}

FOURTEEN_CONTRACT_FIELDS = [
    "point_estimate", "lower_bound", "upper_bound", "interval_method",
    "event_probability", "base_rate", "propensity_band", "evidence_level",
    "sample_size", "in_training_domain", "warnings", "model_version",
    "calibration_status", "calibration_method",
]
PREDICTION_ROOTS = ["LtvPrediction", "PropensityPrediction", "BudgetSimulation"]


# =============================================================================
# Valid-instance factories -- one baseline per model, so invariant tests can
# mutate a single field off of a known-good payload.
# =============================================================================


def _valid_interval_details() -> dict:
    return {"nominal_coverage": 0.95, "measured_coverage": 0.9289}


def _valid_regression_metrics() -> dict:
    return {
        "cv": {"mean_mae": 2.0, "mean_rmse": 2.5, "mean_r2": 0.9},
        "holdout": {"mae": 2.1, "rmse": 2.7, "r2": 0.94},
    }


def _valid_classification_metrics() -> dict:
    return {
        "cv": {"mean_roc_auc": 0.9, "mean_pr_auc": 0.85, "mean_brier": 0.1, "mean_log_loss": 0.3},
        "holdout": {"roc_auc": 0.91, "pr_auc": 0.86, "brier": 0.11, "log_loss": 0.29},
    }


def _ood_warning(feature: str = "ad_budget", value: float = 999999.0, lo: float = 0.0, hi: float = 50000.0) -> dict:
    return {"code": "ood_feature_out_of_range", "message": "out of range", "feature": feature, "value": value, "min": lo, "max": hi}


def _unobserved_warning(value: float = 3500.0) -> dict:
    return {"code": "unobserved_budget_level", "message": "unobserved level", "feature": "ad_budget", "value": value}


def _valid_ltv(**overrides) -> dict:
    base = dict(
        point_estimate=100.0, lower_bound=50.0, upper_bound=150.0,
        interval_method="split_conformal",
        interval_details=_valid_interval_details(),
        evidence_level=None, in_training_domain=True, warnings=[],
        model_version="v1", model_algorithm="catboost",
        metrics=_valid_regression_metrics(),
    )
    base.update(overrides)
    return base


def _valid_propensity(**overrides) -> dict:
    base = dict(
        event_probability=0.4635, base_rate=0.4635, propensity_band="near_base",
        evidence_level=None, in_training_domain=True, warnings=[],
        model_version="v1", model_algorithm="logistic",
        calibration_status="calibrated", calibration_method="sigmoid",
        metrics=_valid_classification_metrics(),
    )
    base.update(overrides)
    return base


def _local_evidence_level(n: int) -> str:
    """D2's P6 thresholds, re-coded independently of app.schemas so rule-14
    tests aren't tautological against the code under test."""
    if n >= 200:
        return "high"
    if n >= 50:
        return "medium"
    return "low"


def _valid_allocations(strategy_id: str, sample_size: int = 250) -> list[dict]:
    return [{"ad_budget": ad, "count": count, "sample_size": sample_size} for ad, count in STRATEGY_ALLOCATIONS[strategy_id]]


def _valid_strategy(strategy_id: str, rank: int, sample_size: int = 250, **overrides) -> dict:
    base = dict(
        strategy_id=strategy_id, rank=rank,
        allocations=_valid_allocations(strategy_id, sample_size),
        point_estimate=100.0, lower_bound=50.0, upper_bound=150.0,
        bootstrap_iterations=1000,
        evidence_level=_local_evidence_level(sample_size),
        in_training_domain=True, warnings=[],
    )
    base.update(overrides)
    return base


def _valid_budget_simulation(**overrides) -> dict:
    strategies = [_valid_strategy(sid, rank=i + 1) for i, sid in enumerate(STRATEGY_ALLOCATIONS)]
    base = dict(
        total_budget=50000, interval_method="bootstrap_percentile",
        bootstrap_percentiles=(2.5, 97.5), top_two_overlap=True,
        strategies=strategies, model_version="v1", model_algorithm="linear",
        metrics=_valid_regression_metrics(),
    )
    base.update(overrides)
    return base


_STAGE_NAMES = ["followup_1", "followup_2", "followup_3", "followup_4", "followup_5"]


def _valid_stage_rows(leads: list[int] | None = None) -> list[dict]:
    leads = leads or [1000, 800, 600, 400, 200, 100]
    rows = []
    for i in range(5):
        frm, to = leads[i], leads[i + 1]
        drop = None if frm == 0 else 1 - to / frm
        rows.append({"stage_order": i + 1, "stage": _STAGE_NAMES[i], "from_leads": frm, "to_leads": to, "drop_rate": drop})
    return rows


def _valid_calls_distribution() -> dict:
    dist = [{"calls": 0, "n": 5}, {"calls": 1, "n": 3}, {"calls": 2, "n": 2}]
    return {"population_n": sum(b["n"] for b in dist), "distribution": dist}


def _valid_tier_rows() -> list[dict]:
    return [
        {"tier_order": 1, "budget_tier": "Low", "n_records": 780, "conversion_rate": 0.1},
        {"tier_order": 2, "budget_tier": "Mid", "n_records": 1717, "conversion_rate": 0.2},
        {"tier_order": 3, "budget_tier": "High", "n_records": 1003, "conversion_rate": 0.3},
    ]


def _valid_funnel_input(**overrides) -> dict:
    base = dict(
        ad_budget=5000, num_leads=100, leads_answered=90,
        followup_1=80, followup_2=70, followup_3=60, followup_4=50, followup_5=40,
        not_closed=30, closed=10, calls_to_closed=15, calls_to_not_closed=45,
        customer_acquisition_cost=200,
    )
    base.update(overrides)
    return base


# =============================================================================
# 1 -- drift: re-exporting must reproduce docs/api/openapi.json exactly.
# =============================================================================


def test_group1_reexport_matches_locked_artifact():
    assert _serialize(export_schema()) == OPENAPI_PATH.read_text(encoding="utf-8")


# =============================================================================
# 2 / 2a -- exactly the six locked routes, and each route's signature.
# =============================================================================


def test_group2_exactly_six_business_routes_with_locked_methods():
    actual = set()
    for path, methods in SCHEMA["paths"].items():
        for method in methods:
            actual.add((method, path))
    assert actual == BUSINESS_ROUTES.keys()


@pytest.mark.parametrize("method_path", sorted(BUSINESS_ROUTES))
def test_group2a_route_signature(method_path):
    method, path = method_path
    op = SCHEMA["paths"][path][method]
    response_model = BUSINESS_ROUTES[method_path]
    ok_schema = op["responses"]["200"]["content"]["application/json"]["schema"]
    assert ok_schema == {"$ref": f"#/components/schemas/{response_model}"}
    if method_path in POST_ROUTES:
        assert op["requestBody"]["required"] is True
        assert op["requestBody"]["content"]["application/json"]["schema"] == {"$ref": "#/components/schemas/FunnelInput"}
    else:
        assert "requestBody" not in op
        assert "parameters" not in op


# =============================================================================
# 3 -- five response families + reachable sub-schemas + two error schemas,
# exported and resolvable. No component-count lock (D7).
# =============================================================================


def test_group3_families_and_error_schemas_are_exported_and_resolvable():
    required_roots = [
        "LtvPrediction", "PropensityPrediction", "BudgetSimulation",
        "FollowupResponse", "BudgetTiersResponse", "ErrorDetail", "HTTPValidationError",
    ]
    for root in required_roots:
        assert root in COMPONENT_SCHEMAS
        _root_closure(root)  # every $ref in the closure must resolve without KeyError


# =============================================================================
# 4 -- all 14 minimum fields map to at least one prediction family.
# =============================================================================


def test_group4_all_fourteen_fields_covered_by_prediction_families():
    bare_names: set[str] = set()
    for root in PREDICTION_ROOTS:
        bare_names |= {path.split(".")[-1] for path in _root_closure(root)}
    missing = [f for f in FOURTEEN_CONTRACT_FIELDS if f not in bare_names]
    assert not missing


# =============================================================================
# 5 / 5a -- ה.1's field map matches the OpenAPI, per-root, bidirectionally,
# including warnings-branch fields under max_length=0.
# =============================================================================


@pytest.mark.parametrize("root", sorted(ROOT_FIELD_MAPS))
def test_group5_field_map_matches_openapi_per_root(root):
    computed = _root_closure(root)
    expected = ROOT_FIELD_MAPS[root]
    missing = expected - computed
    extra = computed - expected
    assert not missing and not extra, f"{root}: missing={sorted(missing)} extra={sorted(extra)}"


def test_group5a_warnings_closure_present_even_under_max_length_zero():
    # StrategyResult.warnings is max_length=0 -- the schema still describes
    # OODWarning's full shape, because the map describes the SCHEMA, not
    # the reachable values (PHASE8.md ה.1).
    strategies_closure = _root_closure("BudgetSimulation")
    for leaf in ("min", "max", "code", "message", "feature", "value"):
        assert f"strategies[].warnings[].{leaf}" in strategies_closure


# =============================================================================
# 6 -- enums, nullability, discriminator.
# =============================================================================


def test_group6_interval_method_has_exactly_two_values_across_the_contract():
    values = {
        COMPONENT_SCHEMAS["LtvPrediction"]["properties"]["interval_method"]["const"],
        COMPONENT_SCHEMAS["BudgetSimulation"]["properties"]["interval_method"]["const"],
    }
    assert values == {"split_conformal", "bootstrap_percentile"}


def test_group6_evidence_level_nullable_in_p2_p3_p4_not_in_p6():
    for root in ("LtvPrediction", "PropensityPrediction"):
        prop = COMPONENT_SCHEMAS[root]["properties"]["evidence_level"]
        branch_types = {b.get("type") for b in prop["anyOf"]}
        assert "null" in branch_types
    strategy_prop = COMPONENT_SCHEMAS["StrategyResult"]["properties"]["evidence_level"]
    assert "anyOf" not in strategy_prop
    assert set(strategy_prop["enum"]) == {"high", "medium", "low"}


def test_group6_warnings_is_oneof_with_discriminator():
    for root in ("LtvPrediction", "PropensityPrediction"):
        items = COMPONENT_SCHEMAS[root]["properties"]["warnings"]["items"]
        assert {r["$ref"] for r in items["oneOf"]} == {
            "#/components/schemas/OODWarning",
            "#/components/schemas/UnobservedBudgetWarning",
        }
        assert items["discriminator"]["propertyName"] == "code"


# =============================================================================
# 7 -- FunnelInput rejects each of the five business-rule violations,
# directly on the model.
# =============================================================================


def test_group7_funnel_input_rejects_non_positive_num_leads():
    with pytest.raises(ValidationError):
        FunnelInput(**_valid_funnel_input(num_leads=0))


def test_group7_funnel_input_rejects_answered_exceeding_leads():
    with pytest.raises(ValidationError):
        FunnelInput(**_valid_funnel_input(leads_answered=101))


def test_group7_funnel_input_rejects_non_monotonic_followup_chain():
    with pytest.raises(ValidationError):
        FunnelInput(**_valid_funnel_input(followup_2=85))  # > followup_1=80


def test_group7_funnel_input_rejects_closed_not_closed_mismatch():
    with pytest.raises(ValidationError):
        FunnelInput(**_valid_funnel_input(closed=1))  # 1 + 30 != followup_5=40


def test_group7_funnel_input_rejects_negative_field():
    with pytest.raises(ValidationError):
        FunnelInput(**_valid_funnel_input(ad_budget=-1))


def test_group7_funnel_input_accepts_the_untouched_baseline():
    FunnelInput(**_valid_funnel_input())  # sanity: the fixture itself is valid


# =============================================================================
# 7a -- model policy: FunnelInput type coercion, every StrictInt/StrictBool
# field, and inf/nan across contract models.
# =============================================================================


def test_group7a_funnel_input_rejects_string_bool_float_and_extra_field():
    with pytest.raises(ValidationError):
        FunnelInput(**_valid_funnel_input(ad_budget="1"))
    with pytest.raises(ValidationError):
        FunnelInput(**_valid_funnel_input(ad_budget=True))
    with pytest.raises(ValidationError):
        FunnelInput(**_valid_funnel_input(ad_budget=1.0))
    with pytest.raises(ValidationError):
        FunnelInput(**_valid_funnel_input(), extra_field=1)


_STRICT_INT_CASES = [
    (StrategyResult, _valid_strategy("100x500", rank=1), "rank"),
    (StrategyResult, _valid_strategy("100x500", rank=1), "bootstrap_iterations"),
    (BudgetAllocation, {"ad_budget": 500, "count": 100, "sample_size": 92}, "ad_budget"),
    (BudgetAllocation, {"ad_budget": 500, "count": 100, "sample_size": 92}, "count"),
    (BudgetAllocation, {"ad_budget": 500, "count": 100, "sample_size": 92}, "sample_size"),
    (FunnelStage, _valid_stage_rows()[0], "stage_order"),
    (FunnelStage, _valid_stage_rows()[0], "from_leads"),
    (FunnelStage, _valid_stage_rows()[0], "to_leads"),
    (CallsDistribution, _valid_calls_distribution(), "population_n"),
    (CallsBucket, {"calls": 1, "n": 3}, "calls"),
    (CallsBucket, {"calls": 1, "n": 3}, "n"),
    (TierRow, _valid_tier_rows()[0], "n_records"),
]


@pytest.mark.parametrize(
    "model_cls,valid_kwargs,field",
    _STRICT_INT_CASES,
    ids=[f"{cls.__name__}.{field}" for cls, _, field in _STRICT_INT_CASES],
)
def test_group7a_strict_int_fields_reject_bool_and_float(model_cls, valid_kwargs, field):
    for bad in (True, 1.0):
        with pytest.raises(ValidationError):
            model_cls(**{**valid_kwargs, field: bad})
    model_cls(**valid_kwargs)  # sanity: the untouched fixture is valid


def test_group7a_loc_int_member_rejects_bool_and_float():
    for bad in (True, 1.0):
        with pytest.raises(ValidationError):
            ValidationErrorItem(loc=[bad], msg="m", type="t")
    ValidationErrorItem(loc=["body", 0], msg="m", type="t")  # sanity


def test_group7a_strict_bool_fields_reject_int_and_string_truthy_values():
    for bad in (1, 0, "true", "yes"):
        with pytest.raises(ValidationError):
            LtvPrediction(**_valid_ltv(in_training_domain=bad))
        with pytest.raises(ValidationError):
            BudgetSimulation(**_valid_budget_simulation(top_two_overlap=bad))


def test_group7a_contract_models_reject_inf_and_nan():
    with pytest.raises(ValidationError):
        LtvPrediction(**_valid_ltv(point_estimate=math.inf))
    with pytest.raises(ValidationError):
        LtvPrediction(**_valid_ltv(point_estimate=math.nan))


# =============================================================================
# 7b -- required + additionalProperties + no default, per schema.
# =============================================================================


def test_group7b_every_schema_forbids_extra_and_has_no_defaults():
    for name, schema in COMPONENT_SCHEMAS.items():
        if schema.get("type") != "object":
            continue  # discriminated-union aliases etc. carry no properties block
        assert schema.get("additionalProperties") is False, name
        for prop_name, prop_schema in schema.get("properties", {}).items():
            assert "default" not in prop_schema, f"{name}.{prop_name} must not declare a default"


def test_group7b_required_is_exact_and_includes_nullable_fields():
    ltv = COMPONENT_SCHEMAS["LtvPrediction"]
    assert set(ltv["required"]) == set(ltv["properties"].keys())
    assert "point_estimate" in ltv["required"]  # nullable, still required
    assert "evidence_level" in ltv["required"]  # nullable, still required


def test_group7b_http_validation_error_detail_has_min_items_one():
    assert COMPONENT_SCHEMAS["HTTPValidationError"]["properties"]["detail"]["minItems"] == 1


# =============================================================================
# 8a -- OOD rules per family in the schema: the right fields are nullable,
# model-detail fields are not.
# =============================================================================


def test_group8a_ltv_prediction_fields_nullable_model_details_are_not():
    props = COMPONENT_SCHEMAS["LtvPrediction"]["properties"]
    for nullable_field in ("point_estimate", "lower_bound", "upper_bound"):
        assert "null" in {b.get("type") for b in props[nullable_field]["anyOf"]}
    for stable_field in ("interval_details", "model_version", "model_algorithm", "metrics"):
        assert "anyOf" not in props[stable_field]


def test_group8a_propensity_prediction_fields_nullable_model_details_are_not():
    props = COMPONENT_SCHEMAS["PropensityPrediction"]["properties"]
    assert "null" in {b.get("type") for b in props["propensity_band"]["anyOf"]}
    for stable_field in ("base_rate", "calibration_status", "calibration_method", "model_version", "model_algorithm", "metrics"):
        assert "anyOf" not in props[stable_field]


# =============================================================================
# 8b -- the 22 invariants (6 from D.8, 4 from D.8b, 12 from D.8c), all via
# direct model instantiation.
# =============================================================================

# --- D.8's six invariants, on both LtvPrediction and PropensityPrediction ---

_D8_CASES = [
    (LtvPrediction, _valid_ltv, ["point_estimate", "lower_bound", "upper_bound"]),
    (PropensityPrediction, _valid_propensity, ["event_probability", "propensity_band"]),
]


@pytest.mark.parametrize("model_cls,valid_factory,pred_fields", _D8_CASES, ids=["LtvPrediction", "PropensityPrediction"])
def test_group8b_d8_rule1_false_domain_with_numeric_prediction_rejected(model_cls, valid_factory, pred_fields):
    kwargs = valid_factory(in_training_domain=False, warnings=[_ood_warning()])
    # leave prediction fields populated (violates rule 1) instead of nulling them
    with pytest.raises(ValidationError):
        model_cls(**kwargs)


@pytest.mark.parametrize("model_cls,valid_factory,pred_fields", _D8_CASES, ids=["LtvPrediction", "PropensityPrediction"])
def test_group8b_d8_rule2_false_domain_without_ood_warning_rejected(model_cls, valid_factory, pred_fields):
    kwargs = valid_factory(in_training_domain=False, warnings=[], **{f: None for f in pred_fields})
    with pytest.raises(ValidationError):
        model_cls(**kwargs)


@pytest.mark.parametrize("model_cls,valid_factory,pred_fields", _D8_CASES, ids=["LtvPrediction", "PropensityPrediction"])
def test_group8b_d8_rule3_true_domain_with_ood_warning_rejected(model_cls, valid_factory, pred_fields):
    kwargs = valid_factory(in_training_domain=True, warnings=[_ood_warning()])
    with pytest.raises(ValidationError):
        model_cls(**kwargs)


@pytest.mark.parametrize("model_cls,valid_factory,pred_fields", _D8_CASES, ids=["LtvPrediction", "PropensityPrediction"])
def test_group8b_d8_rule4_true_domain_with_null_prediction_rejected(model_cls, valid_factory, pred_fields):
    kwargs = valid_factory(in_training_domain=True, warnings=[], **{f: None for f in pred_fields})
    with pytest.raises(ValidationError):
        model_cls(**kwargs)


@pytest.mark.parametrize("model_cls,valid_factory,pred_fields", _D8_CASES, ids=["LtvPrediction", "PropensityPrediction"])
def test_group8b_d8_rule5_low_evidence_without_unobserved_warning_rejected(model_cls, valid_factory, pred_fields):
    kwargs = valid_factory(evidence_level="low", warnings=[])
    with pytest.raises(ValidationError):
        model_cls(**kwargs)


@pytest.mark.parametrize("model_cls,valid_factory,pred_fields", _D8_CASES, ids=["LtvPrediction", "PropensityPrediction"])
def test_group8b_d8_rule6_null_evidence_with_unobserved_warning_rejected(model_cls, valid_factory, pred_fields):
    kwargs = valid_factory(evidence_level=None, warnings=[_unobserved_warning()])
    with pytest.raises(ValidationError):
        model_cls(**kwargs)


def test_group8b_d8_both_warnings_together_is_accepted():
    # D2/D5: the two biconditionals are independent -- a record can carry
    # both warnings at once.
    LtvPrediction(**_valid_ltv(
        in_training_domain=False, evidence_level="low",
        point_estimate=None, lower_bound=None, upper_bound=None,
        warnings=[_ood_warning(), _unobserved_warning()],
    ))


# --- D.8b's four invariants, on BudgetSimulation.strategies ---


def test_group8b_d8b_rule7_strategy_ids_must_be_exactly_the_four_locked_ones():
    strategies = [_valid_strategy(sid, rank=i + 1) for i, sid in enumerate(STRATEGY_ALLOCATIONS)]
    strategies[0] = {**strategies[0], "strategy_id": strategies[1]["strategy_id"]}  # duplicate
    with pytest.raises(ValidationError):
        BudgetSimulation(**_valid_budget_simulation(strategies=strategies))


def test_group8b_d8b_rule8_rank_must_be_unique_and_cover_1_to_4():
    strategies = [_valid_strategy(sid, rank=1) for sid in STRATEGY_ALLOCATIONS]  # all rank 1
    with pytest.raises(ValidationError):
        BudgetSimulation(**_valid_budget_simulation(strategies=strategies))


def test_group8b_d8b_rule9_strategies_must_be_sorted_by_rank_ascending():
    ids = list(STRATEGY_ALLOCATIONS)
    strategies = [_valid_strategy(ids[0], rank=2), _valid_strategy(ids[1], rank=1), _valid_strategy(ids[2], rank=3), _valid_strategy(ids[3], rank=4)]
    with pytest.raises(ValidationError):
        BudgetSimulation(**_valid_budget_simulation(strategies=strategies))


def test_group8b_d8b_rule10_allocations_must_match_strategy_allocations_exactly():
    strategies = [_valid_strategy(sid, rank=i + 1) for i, sid in enumerate(STRATEGY_ALLOCATIONS)]
    # swap the first strategy's allocations for a DIFFERENT strategy's composition
    wrong_id = list(STRATEGY_ALLOCATIONS)[1]
    strategies[0] = {**strategies[0], "allocations": _valid_allocations(wrong_id)}
    with pytest.raises(ValidationError):
        BudgetSimulation(**_valid_budget_simulation(strategies=strategies))


def test_group8b_d8b_valid_budget_simulation_is_accepted():
    BudgetSimulation(**_valid_budget_simulation())  # sanity: the fixture itself is valid


# --- D.8c's twelve invariants (11-22) ---


def test_group8b_d8c_rule11_ltv_bounds_order():
    with pytest.raises(ValidationError):
        LtvPrediction(**_valid_ltv(lower_bound=200.0))  # > point_estimate


def test_group8b_d8c_rule12_strategy_lower_le_upper():
    with pytest.raises(ValidationError):
        StrategyResult(**_valid_strategy("100x500", rank=1, lower_bound=200.0, upper_bound=100.0))


def test_group8b_d8c_rule12_strategy_point_outside_interval_is_accepted():
    # explicitly NOT required to fall inside [lower, upper] (PHASE8.md D.8c)
    StrategyResult(**_valid_strategy("100x500", rank=1, point_estimate=9999.0, lower_bound=50.0, upper_bound=150.0))


def test_group8b_d8c_rule13_propensity_band_must_match_thresholds():
    with pytest.raises(ValidationError):
        PropensityPrediction(**_valid_propensity(event_probability=0.9, propensity_band="near_base"))


def test_group8b_d8c_rule14_evidence_level_must_match_min_sample_size():
    with pytest.raises(ValidationError):
        StrategyResult(**_valid_strategy("100x500", rank=1, sample_size=250, evidence_level="low"))


def test_group8b_d8c_rule15_ood_warning_bounds_and_value_position():
    with pytest.raises(ValidationError):
        OODWarning(**_ood_warning(value=25.0, lo=0.0, hi=50.0))  # value inside [min, max]
    with pytest.raises(ValidationError):
        OODWarning(**_ood_warning(lo=50.0, hi=0.0))  # min > max


def test_group8b_d8c_rule16_stage_sequence_must_be_exact_and_in_order():
    rows = _valid_stage_rows()
    rows[0] = {**rows[0], "stage": "followup_2"}  # wrong stage name at position 1
    with pytest.raises(ValidationError):
        StagesPart(status="available", data=rows)


def test_group8b_d8c_rule17_to_leads_must_not_exceed_from_leads():
    with pytest.raises(ValidationError):
        FunnelStage(stage_order=1, stage="followup_1", from_leads=10, to_leads=20, drop_rate=0.0)


def test_group8b_d8c_rule18_chaining_between_consecutive_stages():
    rows = _valid_stage_rows()
    rows[1] = {**rows[1], "from_leads": 999, "to_leads": 500, "drop_rate": 1 - 500 / 999}  # breaks chain with rows[0].to_leads
    with pytest.raises(ValidationError):
        StagesPart(status="available", data=rows)


def test_group8b_d8c_rule19_drop_rate_null_iff_from_leads_zero():
    with pytest.raises(ValidationError):
        FunnelStage(stage_order=1, stage="followup_1", from_leads=0, to_leads=0, drop_rate=0.0)
    with pytest.raises(ValidationError):
        FunnelStage(stage_order=1, stage="followup_1", from_leads=100, to_leads=50, drop_rate=None)
    with pytest.raises(ValidationError):
        FunnelStage(stage_order=1, stage="followup_1", from_leads=100, to_leads=50, drop_rate=0.9)  # should be 0.5


def test_group8b_d8c_rule20_calls_unique_and_sum_matches_population_n():
    dist = _valid_calls_distribution()
    with pytest.raises(ValidationError):
        CallsDistribution(population_n=dist["population_n"], distribution=[{"calls": 1, "n": 3}, {"calls": 1, "n": 2}])
    with pytest.raises(ValidationError):
        CallsDistribution(population_n=999, distribution=dist["distribution"])


def test_group8b_d8c_rule21_tier_pair_must_be_one_of_the_four_valid_pairs():
    with pytest.raises(ValidationError):
        TierRow(tier_order=1, budget_tier="High", n_records=10, conversion_rate=0.1)
    TierRow(tier_order=None, budget_tier=None, n_records=10, conversion_rate=0.1)  # sanity: future case is valid


def test_group8b_d8c_rule22_no_duplicate_tier_pairs():
    rows = _valid_tier_rows()
    rows.append(dict(rows[0]))
    with pytest.raises(ValidationError):
        BudgetTiersResponse(tiers=rows)


# =============================================================================
# 8c -- numeric/boolean Literal enforced via before-validator.
# =============================================================================


def test_group8c_in_training_domain_rejects_1_and_1_0():
    for bad in (1, 1.0):
        with pytest.raises(ValidationError):
            StrategyResult(**_valid_strategy("100x500", rank=1, in_training_domain=bad))


def test_group8c_total_budget_rejects_50000_0_and_true():
    for bad in (50000.0, True):
        with pytest.raises(ValidationError):
            BudgetSimulation(**_valid_budget_simulation(total_budget=bad))


def test_group8c_tier_order_rejects_true_and_1_0():
    for bad in (True, 1.0):
        with pytest.raises(ValidationError):
            TierRow(tier_order=bad, budget_tier="Low", n_records=10, conversion_rate=0.1)


def test_group8c_bootstrap_percentiles_rejects_strings_and_reversed_order_accepts_correct():
    with pytest.raises(ValidationError):
        BudgetSimulation(**_valid_budget_simulation(bootstrap_percentiles=("2.5", "97.5")))
    with pytest.raises(ValidationError):
        BudgetSimulation(**_valid_budget_simulation(bootstrap_percentiles=(97.5, 2.5)))
    BudgetSimulation(**_valid_budget_simulation(bootstrap_percentiles=(2.5, 97.5)))  # sanity


# =============================================================================
# 9 -- MODEL_INPUT_FEATURES[task] == meta.json.feature_columns, full order.
# =============================================================================


@pytest.mark.parametrize("task", ["P2", "P3", "P4", "P6"])
def test_group9_model_input_features_matches_meta_json_feature_columns(task):
    meta = json.loads((REPO_ROOT / "models" / f"{task}.meta.json").read_text(encoding="utf-8"))
    assert MODEL_INPUT_FEATURES[task] == meta["feature_columns"]


def test_group9_expected_field_counts():
    assert [len(MODEL_INPUT_FEATURES[t]) for t in ("P2", "P3", "P4", "P6")] == [13, 13, 13, 14]


# =============================================================================
# 10 -- CV + Holdout metric keys exist for the winning algorithm, 4 tasks.
# =============================================================================

_METRICS = json.loads((REPO_ROOT / "models" / "metrics.json").read_text(encoding="utf-8"))
_REGRESSION_CV_KEYS = {"mean_mae", "mean_rmse", "mean_r2"}
_REGRESSION_HOLDOUT_KEYS = {"mae", "rmse", "r2"}
_CLASSIFICATION_CV_KEYS = {"mean_roc_auc", "mean_pr_auc", "mean_brier", "mean_log_loss"}
_CLASSIFICATION_HOLDOUT_KEYS = {"roc_auc", "pr_auc", "brier", "log_loss"}


@pytest.mark.parametrize(
    "task,cv_keys,holdout_keys",
    [
        ("P2", _REGRESSION_CV_KEYS, _REGRESSION_HOLDOUT_KEYS),
        ("P3", _CLASSIFICATION_CV_KEYS, _CLASSIFICATION_HOLDOUT_KEYS),
        ("P4", _CLASSIFICATION_CV_KEYS, _CLASSIFICATION_HOLDOUT_KEYS),
        ("P6", _REGRESSION_CV_KEYS, _REGRESSION_HOLDOUT_KEYS),
    ],
)
def test_group10_winning_algorithm_carries_required_cv_and_holdout_keys(task, cv_keys, holdout_keys):
    meta = json.loads((REPO_ROOT / "models" / f"{task}.meta.json").read_text(encoding="utf-8"))
    algo = meta["algo"]
    assert cv_keys <= set(_METRICS[task][algo].keys())
    assert holdout_keys <= set(_METRICS[f"{task}_holdout"].keys())


# =============================================================================
# 11 -- STRATEGY_ALLOCATIONS parity: vs P6_simulation.json (ids + levels)
# and vs an independent constant transcribed from IA.md §6 (count + sum).
# =============================================================================

_P6_SIMULATION = json.loads((REPO_ROOT / "models" / "P6_simulation.json").read_text(encoding="utf-8"))

# Independently transcribed from docs/IA.md:274-277 -- NOT derived from
# app.features.STRATEGY_ALLOCATIONS, so this actually catches a drift.
_EXPECTED_STRATEGY_ALLOCATIONS = {
    "2x20000_1x10000": [(20000, 2), (10000, 1)],
    "10x5000": [(5000, 10)],
    "25x2000": [(2000, 25)],
    "100x500": [(500, 100)],
}


def test_group11_strategy_allocations_matches_ia_md_independently():
    assert STRATEGY_ALLOCATIONS == _EXPECTED_STRATEGY_ALLOCATIONS


def test_group11_every_strategy_sums_to_50000():
    for strategy_id, pairs in _EXPECTED_STRATEGY_ALLOCATIONS.items():
        assert sum(level * count for level, count in pairs) == 50000, strategy_id


def test_group11_strategy_ids_and_ad_budget_levels_match_p6_simulation_json():
    assert set(STRATEGY_ALLOCATIONS) == set(_P6_SIMULATION)
    for strategy_id, pairs in STRATEGY_ALLOCATIONS.items():
        expected_levels = {ad_budget for ad_budget, _count in pairs}
        actual_levels = {int(level) for level in _P6_SIMULATION[strategy_id]["levels"]}
        assert expected_levels == actual_levels, strategy_id


# =============================================================================
# 12 -- partial-failure schemas (per-part union) and the empty budget-tiers
# array are locked.
# =============================================================================


def test_group12_followup_parts_are_locked_discriminated_unions():
    for part_name in ("stages", "calls_to_closed"):
        prop = COMPONENT_SCHEMAS["FollowupResponse"]["properties"][part_name]
        assert prop["discriminator"]["propertyName"] == "status"
        assert "#/components/schemas/PartUnavailable" in {r["$ref"] for r in prop["oneOf"]}


def test_group12_part_unavailable_shape_is_locked():
    part_error = COMPONENT_SCHEMAS["PartError"]
    assert set(part_error["properties"]["reason_code"]["enum"]) == {"data_unavailable", "aggregation_mismatch"}


def test_group12_budget_tiers_empty_array_is_valid():
    BudgetTiersResponse(tiers=[])  # 200 + empty array, not an error (D11)
    tiers_prop = COMPONENT_SCHEMAS["BudgetTiersResponse"]["properties"]["tiers"]
    assert tiers_prop.get("minItems", 0) == 0
    assert tiers_prop["maxItems"] == 4


# =============================================================================
# 13 -- security scheme + status codes declared per route.
# =============================================================================


def test_group13_bearer_auth_security_scheme_declared():
    assert SCHEMA["components"]["securitySchemes"] == {"BearerAuth": {"type": "http", "scheme": "bearer"}}


@pytest.mark.parametrize("method_path", sorted(BUSINESS_ROUTES))
def test_group13_every_route_declares_security_and_common_error_codes(method_path):
    method, path = method_path
    op = SCHEMA["paths"][path][method]
    assert op["security"] == [{"BearerAuth": []}]
    for code in ("401", "403", "500", "503"):
        assert code in op["responses"]


def test_group13_422_only_on_post_routes():
    for method, path in POST_ROUTES:
        assert "422" in SCHEMA["paths"][path][method]["responses"]
    for method, path in GET_ROUTES:
        assert "422" not in SCHEMA["paths"][path][method]["responses"]
