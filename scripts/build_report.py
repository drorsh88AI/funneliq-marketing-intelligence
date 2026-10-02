"""REPORT.md builder -- PHASE13.md D2 (numbers), D8 (charts), A3.1 (feature
table), A3.2 (three majority rates).

REPORT.md is rendered from a template (string.Template, the pattern
scripts/analysis.py's render_findings_md already uses). Every quantitative
claim in the template is a $placeholder that must be declared in MANIFEST: a
source file, a path inside it, an optional derivation, and a number format.
A placeholder that is not in the manifest fails the render, and so does a
path that does not resolve, so no number can reach REPORT.md without a
declared origin.

SOURCES is a CLOSED list of committed JSON files. It deliberately does NOT
include the CSV, so the manifest can be checked in CI, where the CSV does not
exist.

Embedded blocks (BLOCKS) are cut verbatim from docs/feature_matrix.md, never
retyped.

This module also holds the chart-heading rule (D8 / PHASE13.md A5) and the
INFORMATIONAL digit scan of a template (PHASE5.md D6 section 5: a scan whose
output is reviewed, never an assertion).

CLI:
  python -m scripts.build_report                     render the template to REPORT.md
  python -m scripts.build_report --calibration-svg P4S
                                                     render docs/calibration_curve_P4S.svg
                                                     from models/metrics.json (no training)
"""
from __future__ import annotations

import json
import re
import sys
import unicodedata
from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal
from pathlib import Path
from string import Template

REPO = Path(__file__).resolve().parent.parent
DEFAULT_TEMPLATE = REPO / "docs" / "report_template.md"
DEFAULT_OUT = REPO / "REPORT.md"


class ReportError(Exception):
    """A manifest, source, block or chart-rule violation."""


# ---------------------------------------------------------------------------
# Sources -- the closed list (PHASE13.md D2).
# ---------------------------------------------------------------------------
SOURCES: dict[str, str] = {
    "metrics": "models/metrics.json",
    "findings": "docs/findings.json",
    "p6_simulation": "models/P6_simulation.json",
    "business_facts": "app/static/business_facts.json",
    "meta_P2": "models/P2.meta.json",
    "meta_P3": "models/P3.meta.json",
    "meta_P4": "models/P4.meta.json",
    "meta_P4S": "models/P4S.meta.json",
    "meta_P6": "models/P6.meta.json",
    "a2": "docs/p4s_a2_train_tiers.json",
}


class Sources:
    """Reads the closed source list from `root`, once each."""

    def __init__(self, root: Path = REPO) -> None:
        self.root = Path(root)
        self._cache: dict[str, object] = {}

    def get(self, name: str):
        if name not in SOURCES:
            raise ReportError(f"source {name!r} is not in the closed source list")
        if name not in self._cache:
            path = self.root / SOURCES[name]
            if not path.is_file():
                raise ReportError(f"source file missing: {SOURCES[name]}")
            self._cache[name] = json.loads(path.read_text(encoding="utf-8"))
        return self._cache[name]

    def value(self, source: str, path: tuple):
        node = self.get(source)
        walked = []
        for key in path:
            walked.append(key)
            try:
                node = node[key]
            except (KeyError, IndexError, TypeError):
                raise ReportError(f"path {list(walked)!r} does not resolve in {SOURCES[source]}") from None
        return node


# ---------------------------------------------------------------------------
# Manifest
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class Ref:
    """A number taken as-is from a source."""
    source: str
    path: tuple
    fmt: str


@dataclass(frozen=True)
class Derived:
    """A number computed from declared inputs by a NAMED formula, so the
    derivation is part of the manifest and not hidden in the template."""
    formula: str
    inputs: tuple          # ((source, path), ...), in the formula's argument order
    fmt: str


def _dec(value) -> Decimal:
    """Exact decimal of a JSON number: Decimal(repr(x)) is the shortest
    decimal that round-trips the float, so 1 - 0.4635 is exactly 0.5365
    instead of 0.5365000000000001."""
    if isinstance(value, bool) or not isinstance(value, (int, float, Decimal)):
        raise ReportError(f"not a number: {value!r}")
    number = value if isinstance(value, Decimal) else Decimal(repr(value))
    if not number.is_finite():
        # json.loads accepts NaN and Infinity, and Decimal formats them as text;
        # a report must never print "Accuracy: NaN%".
        raise ReportError(f"not a finite number: {value!r}")
    return number


DERIVED: dict[str, object] = {
    # 1 - x, e.g. the majority-class rate from the positive-class rate.
    "one_minus": lambda x: Decimal(1) - _dec(x),
    # (accuracy - majority) in percentage points, majority = 1 - base_rate.
    "accuracy_minus_majority_pp": lambda accuracy, base_rate: (_dec(accuracy) - (Decimal(1) - _dec(base_rate))) * 100,
    # one feature's share of the model's total importance (the dict is the
    # model's whole importance map); only meaningful within ONE model.
    "share_of_total": lambda value, importances: _dec(value) / sum(_dec(v) for v in importances.values()),
}

MANIFEST: dict[str, Ref | Derived] = {
    # --- A3.2: three majority rates, each tied to ITS population -------------
    # all purchasers, before any split
    "n_purchasers_all": Ref("business_facts", ("super_customer_profile", "n_purchased"), "comma"),
    "majority_all_pct": Derived("one_minus", (("meta_P3", ("base_rate",)),), "pct2"),
    # the 5 cross-validation folds of the TRAINING split
    "n_train_p3": Ref("meta_P3", ("population_n", "train"), "comma"),
    "majority_cv_pct": Ref("metrics", ("P3", "dummy", "mean_accuracy"), "pct2"),
    # the Holdout
    "n_holdout_p3": Ref("metrics", ("P3_holdout", "n_holdout"), "comma"),
    "majority_holdout_pct": Derived("one_minus", (("metrics", ("P3_holdout", "lift_at_10", "base_rate")),), "pct2"),
    "p3_holdout_accuracy_pct": Ref("metrics", ("P3_holdout", "accuracy"), "pct2"),
    "p3_gain_over_majority_pp": Derived(
        "accuracy_minus_majority_pp",
        (("metrics", ("P3_holdout", "accuracy")), ("metrics", ("P3_holdout", "lift_at_10", "base_rate"))),
        "num2",
    ),
    # --- one entry per remaining source, so every source is exercised --------
    "missing_rows": Ref("findings", ("missing_values", "missing_any"), "int"),
    "leads_per_1000_lowest": Ref("findings", ("budget_leads_per_1000", "summary", "leads_per_1000_lowest"), "num1"),
    "super_share_of_total_profit_pct": Ref("business_facts", ("super_customer_profile", "pct_of_total_profit"), "pct1"),
    "p6_point_100x500": Ref("p6_simulation", ("100x500", "point"), "comma"),
    "p4s_holdout_roc_auc": Ref("metrics", ("P4S_holdout", "roc_auc"), "num3"),
    "p4s_train_n": Ref("meta_P4S", ("population_n", "train"), "comma"),
    "p6_train_n": Ref("meta_P6", ("population_n", "train"), "comma"),
    "p2_train_n": Ref("meta_P2", ("population_n", "train"), "comma"),
    "p4_train_n": Ref("meta_P4", ("population_n", "train"), "comma"),
    "a2_mid_n": Ref("a2", ("tiers", "Mid", "n"), "comma"),
    "a2_mid_super_rate_pct": Ref("a2", ("tiers", "Mid", "rate"), "pct1"),

    # --- CP4: the numbers the report text uses, one entry each ---------------
    # data and cleaning (package 1)
    "n_rows": Ref("findings", ("missing_values", "n_rows"), "comma"),
    "missing_ltv": Ref("findings", ("missing_values", "missing_ltv_months"), "int"),
    "missing_profit": Ref("findings", ("missing_values", "missing_cumulative_profit"), "int"),
    "dup_rows": Ref("findings", ("duplicates", "n_duplicate_rows"), "int"),
    "dup_groups": Ref("findings", ("duplicates", "n_groups"), "int"),
    "zero_profit_rows": Ref("findings", ("m1_zero_profit", "n_zero_profit"), "int"),
    "p6_population_n": Ref("findings", ("task_exclusions", "by_task", "P6", "n_population"), "comma"),
    "p6_removed_missing_target": Ref("findings", ("task_exclusions", "by_task", "P6", "n_lost_to_missing_target"), "int"),
    "p2_removed_missing_target": Ref("findings", ("task_exclusions", "by_task", "P2", "n_lost_to_missing_target"), "int"),
    "conv_low_pct": Ref("findings", ("budget_tiers", "Low", "conversion_rate"), "pct1"),
    "conv_mid_pct": Ref("findings", ("budget_tiers", "Mid", "conversion_rate"), "pct1"),
    "conv_high_pct": Ref("findings", ("budget_tiers", "High", "conversion_rate"), "pct1"),
    "conv_gap_pp": Ref("findings", ("tier_conversion_shape", "best_minus_runner_up_pp"), "num1"),
    "leads_per_1000_highest": Ref("findings", ("budget_leads_per_1000", "summary", "leads_per_1000_highest"), "num1"),
    "budget_multiple": Ref("findings", ("budget_leads_per_1000", "summary", "budget_multiple"), "int"),
    "leads_multiple": Ref("findings", ("budget_leads_per_1000", "summary", "median_leads_multiple"), "num1"),
    "corr_ltv": Ref("findings", ("correlations", "ltv_months"), "num2"),
    "corr_upsell": Ref("findings", ("correlations", "upsell"), "num2"),
    "corr_calls_to_closed": Ref("findings", ("correlations", "calls_to_closed"), "num2"),
    "corr_cac": Ref("findings", ("correlations", "customer_acquisition_cost"), "num2"),

    # P2 -- lifetime
    "p2_cat_rmse": Ref("metrics", ("P2", "catboost", "mean_rmse"), "num2"),
    "p2_cat_r2": Ref("metrics", ("P2", "catboost", "mean_r2"), "num3"),
    "p2_lgbm_rmse": Ref("metrics", ("P2", "lightgbm", "mean_rmse"), "num2"),
    "p2_lgbm_r2": Ref("metrics", ("P2", "lightgbm", "mean_r2"), "num3"),
    "p2_xgb_rmse": Ref("metrics", ("P2", "xgboost", "mean_rmse"), "num2"),
    "p2_xgb_r2": Ref("metrics", ("P2", "xgboost", "mean_r2"), "num3"),
    "p2_linear_rmse": Ref("metrics", ("P2", "linear", "mean_rmse"), "num2"),
    "p2_dummy_rmse": Ref("metrics", ("P2", "dummy", "mean_rmse"), "num2"),
    "p2_hold_n": Ref("metrics", ("P2_holdout", "n_holdout"), "comma"),
    "p2_hold_rmse": Ref("metrics", ("P2_holdout", "rmse"), "num2"),
    "p2_hold_r2": Ref("metrics", ("P2_holdout", "r2"), "num3"),
    "p2_conformal_q": Ref("metrics", ("P2_holdout", "conformal_q"), "num1"),
    "p2_conformal_coverage_pct": Ref("metrics", ("P2_holdout", "conformal_coverage"), "pct1"),
    "p2_cat_calls_share_pct": Derived(
        "share_of_total",
        (("metrics", ("global_feature_importance", "P2", "catboost", "numeric__calls_to_closed")),
         ("metrics", ("global_feature_importance", "P2", "catboost"))), "pct0"),
    "p2_xgb_calls_share_pct": Derived(
        "share_of_total",
        (("metrics", ("global_feature_importance", "P2", "xgboost", "numeric__calls_to_closed")),
         ("metrics", ("global_feature_importance", "P2", "xgboost"))), "pct0"),

    # P3 -- upsell
    "p3_base_rate_pct": Ref("metrics", ("P3_holdout", "lift_at_10", "base_rate"), "pct1"),
    "p3_weight_ratio": Ref("metrics", ("P3_weighted_comparison", "xgboost", "class_weight_ratios_per_fold", 0), "num2"),
    "p3_xgb_auc_plain": Ref("metrics", ("P3_weighted_comparison", "xgboost", "regular_mean_roc_auc"), "num3"),
    "p3_xgb_auc_weighted": Ref("metrics", ("P3_weighted_comparison", "xgboost", "weighted_mean_roc_auc"), "num3"),
    "p3_cat_auc_plain": Ref("metrics", ("P3_weighted_comparison", "catboost", "regular_mean_roc_auc"), "num3"),
    "p3_cat_auc_weighted": Ref("metrics", ("P3_weighted_comparison", "catboost", "weighted_mean_roc_auc"), "num3"),
    "p3_lgbm_auc_plain": Ref("metrics", ("P3_weighted_comparison", "lightgbm", "regular_mean_roc_auc"), "num3"),
    "p3_lgbm_auc_weighted": Ref("metrics", ("P3_weighted_comparison", "lightgbm", "weighted_mean_roc_auc"), "num3"),
    "p3_xgb_cv_acc_pct": Ref("metrics", ("P3", "xgboost", "mean_accuracy"), "pct1"),
    "p3_xgb_cv_prec_pct": Ref("metrics", ("P3", "xgboost", "mean_precision"), "pct1"),
    "p3_xgb_cv_rec_pct": Ref("metrics", ("P3", "xgboost", "mean_recall"), "pct1"),
    "p3_xgb_cv_f1_pct": Ref("metrics", ("P3", "xgboost", "mean_f1"), "pct1"),
    "p3_xgb_cv_auc": Ref("metrics", ("P3", "xgboost", "mean_roc_auc"), "num3"),
    "p3_cat_cv_auc": Ref("metrics", ("P3", "catboost", "mean_roc_auc"), "num3"),
    "p3_lgbm_cv_auc": Ref("metrics", ("P3", "lightgbm", "mean_roc_auc"), "num3"),
    "p3_logistic_cv_auc": Ref("metrics", ("P3", "logistic", "mean_roc_auc"), "num3"),
    "p3_hold_prec_pct": Ref("metrics", ("P3_holdout", "precision"), "pct1"),
    "p3_hold_rec_pct": Ref("metrics", ("P3_holdout", "recall"), "pct1"),
    "p3_hold_f1_pct": Ref("metrics", ("P3_holdout", "f1"), "pct1"),
    "p3_hold_auc": Ref("metrics", ("P3_holdout", "roc_auc"), "num3"),
    "p3_xgb_calls_share_pct": Derived(
        "share_of_total",
        (("metrics", ("global_feature_importance", "P3", "xgboost", "numeric__calls_to_closed")),
         ("metrics", ("global_feature_importance", "P3", "xgboost"))), "pct0"),
    "p3_xgb_cac_share_pct": Derived(
        "share_of_total",
        (("metrics", ("global_feature_importance", "P3", "xgboost", "numeric__customer_acquisition_cost")),
         ("metrics", ("global_feature_importance", "P3", "xgboost"))), "pct0"),
    "rule_brief_ltv": Ref("metrics", ("P3_manual_rules", "brief_rule", "thresholds", "ltv_months_gt"), "int"),
    "rule_brief_cac": Ref("metrics", ("P3_manual_rules", "brief_rule", "thresholds", "customer_acquisition_cost_lt"), "comma"),
    "rule_brief_acc_pct": Ref("metrics", ("P3_manual_rules", "brief_rule", "mean_accuracy"), "pct1"),
    "rule_brief_prec_pct": Ref("metrics", ("P3_manual_rules", "brief_rule", "mean_precision"), "pct1"),
    "rule_brief_rec_pct": Ref("metrics", ("P3_manual_rules", "brief_rule", "mean_recall"), "pct1"),
    "rule_op_closed": Ref("metrics", ("P3_manual_rules", "operational_rule", "thresholds", "closed_gt"), "int"),
    "rule_op_cac": Ref("metrics", ("P3_manual_rules", "operational_rule", "thresholds", "customer_acquisition_cost_lt"), "comma"),
    "rule_op_acc_pct": Ref("metrics", ("P3_manual_rules", "operational_rule", "mean_accuracy"), "pct1"),
    "rule_op_prec_pct": Ref("metrics", ("P3_manual_rules", "operational_rule", "mean_precision"), "pct1"),
    "rule_op_rec_pct": Ref("metrics", ("P3_manual_rules", "operational_rule", "mean_recall"), "pct1"),

    # P4 -- referral, and P4S -- the super-customer score
    "p4_logistic_cv_auc": Ref("metrics", ("P4", "logistic", "mean_roc_auc"), "num3"),
    "p4_cat_cv_auc": Ref("metrics", ("P4", "catboost", "mean_roc_auc"), "num3"),
    "p4_hold_auc": Ref("metrics", ("P4_holdout", "roc_auc"), "num3"),
    "p4_hold_acc_pct": Ref("metrics", ("P4_holdout", "accuracy"), "pct1"),
    "p4_majority_cv_pct": Ref("metrics", ("P4", "dummy", "mean_accuracy"), "pct1"),
    "p4_all_auc": Ref("metrics", ("P4_population_sensitivity", "mean_roc_auc"), "num3"),
    "p4_all_n": Ref("metrics", ("P4_population_sensitivity", "population_size"), "comma"),
    "p4_early_auc": Ref("metrics", ("P4_early_funnel", "mean_roc_auc"), "num3"),
    "p4s_logistic_cv_auc": Ref("metrics", ("P4S", "logistic", "mean_roc_auc"), "num3"),
    "p4s_cat_cv_auc": Ref("metrics", ("P4S", "catboost", "mean_roc_auc"), "num3"),
    "p4s_hold_acc_pct": Ref("metrics", ("P4S_holdout", "accuracy"), "pct1"),
    "p4s_hold_majority_pct": Ref("metrics", ("P4S_holdout", "majority_baseline_population_pct"), "pct1"),
    "p4s_hold_recall_pct": Ref("metrics", ("P4S_holdout", "recall"), "pct0"),
    "p4s_mid_auc": Ref("metrics", ("P4S_holdout", "budget_tier", "Mid", "roc_auc"), "num3"),
    "p4s_mid_n": Ref("metrics", ("P4S_holdout", "budget_tier", "Mid", "n"), "comma"),
    "p4s_mid_rate_pct": Ref("metrics", ("P4S_holdout", "budget_tier", "Mid", "base_rate"), "pct1"),
    "p4s_low_n": Ref("metrics", ("P4S_holdout", "budget_tier", "Low", "n"), "comma"),
    "p4s_high_n": Ref("metrics", ("P4S_holdout", "budget_tier", "High", "n"), "comma"),
    "p4s_hold_n": Ref("metrics", ("P4S_holdout", "n_holdout"), "comma"),
    "a2_low_n": Ref("a2", ("tiers", "Low", "n"), "comma"),
    "a2_high_n": Ref("a2", ("tiers", "High", "n"), "comma"),
    "a2_mid_super": Ref("a2", ("tiers", "Mid", "n_super"), "comma"),
    "a2_train_n": Ref("a2", ("n_train",), "comma"),
    "super_n": Ref("business_facts", ("super_customer_profile", "n_super"), "comma"),
    "super_share_of_purchased_pct": Ref("business_facts", ("super_customer_profile", "pct_of_purchased"), "pct1"),
    "super_cac": Ref("business_facts", ("super_customer_profile", "cac_super_mean"), "comma"),
    "all_cac": Ref("business_facts", ("super_customer_profile", "cac_population_mean"), "comma"),
    "super_cac_savings_pct": Ref("business_facts", ("super_customer_profile", "cac_savings_pct"), "pct1"),

    # package 5 -- follow-ups
    "drop_1_pct": Ref("findings", ("funnel_dropoff", "followup_1"), "pct1"),
    "drop_2_pct": Ref("findings", ("funnel_dropoff", "followup_2"), "pct1"),
    "drop_3_pct": Ref("findings", ("funnel_dropoff", "followup_3"), "pct1"),
    "drop_4_pct": Ref("findings", ("funnel_dropoff", "followup_4"), "pct1"),
    "drop_5_pct": Ref("findings", ("funnel_dropoff", "followup_5"), "pct1"),
    "ctc_population_n": Ref("findings", ("calls_to_closed", "population_n"), "comma"),
    "ctc_median": Ref("findings", ("calls_to_closed", "median_calls_to_closed"), "int"),
    "ctc_mode": Ref("findings", ("calls_to_closed", "mode_calls_to_closed", 0), "int"),
    "ctc_mean": Ref("findings", ("calls_to_closed", "mean_calls_to_closed"), "num2"),
    "ctc_ge4_n": Ref("findings", ("calls_to_closed", "n_calls_to_closed_ge_4"), "comma"),
    "ctc_ge4_pct": Ref("findings", ("calls_to_closed", "rate_calls_to_closed_ge_4"), "pct2"),

    # package 6 -- budget
    "p6_linear_rmse": Ref("metrics", ("P6", "linear", "mean_rmse"), "comma"),
    "p6_linear_r2": Ref("metrics", ("P6", "linear", "mean_r2"), "num3"),
    "p6_ref_rmse": Ref("metrics", ("P6", "p6_1_reference", "mean_rmse"), "comma"),
    "p6_ref_r2": Ref("metrics", ("P6", "p6_1_reference", "mean_r2"), "num3"),
    "p6_hold_n": Ref("metrics", ("P6_holdout", "n_holdout"), "comma"),
    "p6_hold_rmse": Ref("metrics", ("P6_holdout", "rmse"), "comma"),
    "p6_hold_r2": Ref("metrics", ("P6_holdout", "r2"), "num3"),
    "p6_top_decile_bias": Ref("metrics", ("P6_holdout", "top_decile", "bias_top10"), "comma"),
    "sim_100x500_point": Ref("p6_simulation", ("100x500", "point"), "comma"),
    "sim_100x500_lower": Ref("p6_simulation", ("100x500", "lower"), "comma"),
    "sim_100x500_upper": Ref("p6_simulation", ("100x500", "upper"), "comma"),
    "sim_25x2000_point": Ref("p6_simulation", ("25x2000", "point"), "comma"),
    "sim_25x2000_lower": Ref("p6_simulation", ("25x2000", "lower"), "comma"),
    "sim_25x2000_upper": Ref("p6_simulation", ("25x2000", "upper"), "comma"),
    "sim_10x5000_point": Ref("p6_simulation", ("10x5000", "point"), "comma"),
    "sim_10x5000_lower": Ref("p6_simulation", ("10x5000", "lower"), "comma"),
    "sim_10x5000_upper": Ref("p6_simulation", ("10x5000", "upper"), "comma"),
    "sim_big_point": Ref("p6_simulation", ("2x20000_1x10000", "point"), "comma"),
    "sim_big_lower": Ref("p6_simulation", ("2x20000_1x10000", "lower"), "comma"),
    "sim_big_upper": Ref("p6_simulation", ("2x20000_1x10000", "upper"), "comma"),
    "bt_500_pred": Ref("metrics", ("P6_backtest", "500", "predicted_per_customer"), "comma"),
    "bt_500_actual": Ref("metrics", ("P6_backtest", "500", "actual_mean_per_customer"), "comma"),
    "bt_500_n": Ref("metrics", ("P6_backtest", "500", "n_holdout_at_level"), "int"),
    "bt_2000_pred": Ref("metrics", ("P6_backtest", "2000", "predicted_per_customer"), "comma"),
    "bt_2000_actual": Ref("metrics", ("P6_backtest", "2000", "actual_mean_per_customer"), "comma"),
    "bt_2000_n": Ref("metrics", ("P6_backtest", "2000", "n_holdout_at_level"), "int"),
    "bt_20000_pred": Ref("metrics", ("P6_backtest", "20000", "predicted_per_customer"), "comma"),
    "bt_20000_actual": Ref("metrics", ("P6_backtest", "20000", "actual_mean_per_customer"), "comma"),
    "bt_20000_n": Ref("metrics", ("P6_backtest", "20000", "n_holdout_at_level"), "int"),
    "profit_mean_low": Ref("findings", ("m4_profit_by_tier", "Low", "mean_cumulative_profit"), "comma"),
    "profit_mean_mid": Ref("findings", ("m4_profit_by_tier", "Mid", "mean_cumulative_profit"), "comma"),
    "profit_mean_high": Ref("findings", ("m4_profit_by_tier", "High", "mean_cumulative_profit"), "comma"),
}


# ---------------------------------------------------------------------------
# Number formatting. Half-up on the exact decimal, never float formatting:
# Python's format() rounds the exact halves 21.25 and 8.75 in opposite
# directions (CP1 finding).
# ---------------------------------------------------------------------------
def _quantize(value: Decimal, decimals: int) -> Decimal:
    return value.quantize(Decimal(1).scaleb(-decimals), rounding=ROUND_HALF_UP)


def format_value(value, fmt: str) -> str:
    """Format a number for the report. A value that is NOT zero but rounds to
    zero in `fmt` raises: printing 0.00 for 0.00004 (or -0.00 for -0.00004)
    states something false. The author must choose a finer format or write an
    explicit threshold phrase ("less than 0.01 points"). A true zero prints
    without a sign, so -0.0 never shows as -0.0."""
    d = _dec(value)
    if fmt == "int":
        if d != d.to_integral_value():
            raise ReportError(f"{value!r} is not an integer but is formatted as int")
        return str(int(d))
    if fmt == "comma":
        scaled, decimals = d, 0
    elif fmt.startswith("pct") and fmt[3:].isdigit():
        scaled, decimals = d * 100, int(fmt[3:])
    elif fmt.startswith("num") and fmt[3:].isdigit():
        scaled, decimals = d, int(fmt[3:])
    else:
        raise ReportError(f"unknown number format {fmt!r}")

    rounded = _quantize(scaled, decimals)
    if rounded == 0:
        if scaled != 0:
            raise ReportError(
                f"{value!r} is not zero but rounds to zero in format {fmt!r}: "
                "use a finer format or write an explicit threshold phrase"
            )
        rounded = abs(rounded)          # a true zero has no sign
    if fmt == "comma":
        return f"{int(rounded):,}"
    if fmt.startswith("pct"):
        return f"{rounded:f}"
    return f"{rounded:,f}"


# ---------------------------------------------------------------------------
# Embedded blocks, cut verbatim from docs/feature_matrix.md (A3.1).
# ---------------------------------------------------------------------------
FEATURE_MATRIX = REPO / "docs" / "feature_matrix.md"
_BLOCK_HEADINGS = {
    "feature_table": "## הטבלה",
    "feature_summary": "## סיכום פיצ'רים בפועל",
}


def table_after_heading(markdown: str, heading: str) -> str:
    """The first contiguous run of markdown table lines (starting with '|')
    after the line that is exactly `heading`, verbatim, joined by LF, with no
    trailing newline."""
    lines = markdown.splitlines()
    try:
        start = lines.index(heading)
    except ValueError:
        raise ReportError(f"heading {heading!r} not found in docs/feature_matrix.md") from None
    i = start + 1
    while i < len(lines) and not lines[i].startswith("|"):
        if lines[i].startswith("## "):
            raise ReportError(f"no table between {heading!r} and the next section")
        i += 1
    run = []
    while i < len(lines) and lines[i].startswith("|"):
        run.append(lines[i])
        i += 1
    if not run:
        raise ReportError(f"no table after {heading!r}")
    return "\n".join(run)


def block_value(name: str, root: Path = REPO) -> str:
    path = Path(root) / "docs" / "feature_matrix.md"
    if not path.is_file():
        raise ReportError("docs/feature_matrix.md is missing")
    return table_after_heading(path.read_text(encoding="utf-8"), _BLOCK_HEADINGS[name])


BLOCKS = tuple(_BLOCK_HEADINGS)


# ---------------------------------------------------------------------------
# Resolving and rendering
# ---------------------------------------------------------------------------
def resolve(name: str, sources: Sources) -> str:
    if name in BLOCKS:
        return block_value(name, sources.root)
    entry = MANIFEST[name]
    if isinstance(entry, Ref):
        return format_value(sources.value(entry.source, entry.path), entry.fmt)
    formula = DERIVED.get(entry.formula)
    if formula is None:
        raise ReportError(f"{name}: unknown derivation {entry.formula!r}")
    inputs = [sources.value(source, path) for source, path in entry.inputs]
    return format_value(formula(*inputs), entry.fmt)


def render_report(template_text: str, sources: Sources | None = None) -> str:
    """Substitute every placeholder from the manifest. Raises ReportError for
    a placeholder that is not declared (in the manifest or as a block)."""
    sources = sources or Sources()
    template = Template(template_text)
    names = template.get_identifiers()
    unknown = sorted(set(names) - set(MANIFEST) - set(BLOCKS))
    if unknown:
        raise ReportError(f"placeholders not declared in the manifest: {unknown}")
    values = {name: resolve(name, sources) for name in names}
    try:
        return template.substitute(values)
    except ValueError as exc:      # a bare or malformed `$` in the template
        raise ReportError(f"malformed placeholder in the template: {exc}") from exc


# ---------------------------------------------------------------------------
# The chart-heading rule (PHASE13.md D8 and appendix A5).
# ---------------------------------------------------------------------------
# Direction-control characters. A heading containing ANY of them fails, anywhere
# in the heading -- nine of them are skipped by a "first strong character" scan
# (they are not classes L/R/AL), so that scan alone would let them through.
DIRECTION_CONTROLS = frozenset(
    [0x200E, 0x200F, 0x061C] + list(range(0x202A, 0x202F)) + list(range(0x2066, 0x206A))
)


# A CommonMark ATX heading: up to 3 spaces of indent, 1-6 '#', then a space or
# tab (or the end of the line). `#text` (no space), 7 '#', and 4 spaces of indent
# (an indented code block) are NOT headings. Setext headings (underlined with
# === or ---) are deliberately not accepted: REPORT.md uses ATX only.
_ATX_HEADING = re.compile(r"^ {0,3}#{1,6}(?=[ \t]|$)")


def is_atx_heading(line: str) -> bool:
    return bool(_ATX_HEADING.match(line))


def rendered_heading_text(heading_line: str) -> str:
    """A markdown heading line as the reader sees it: heading marker and the
    optional closing '#' sequence removed, emphasis markers and code delimiters
    removed (code content kept), link/image URLs removed (label kept), HTML
    tags removed."""
    text = re.sub(r"^ {0,3}#{1,6}(?:[ \t]+|$)", "", heading_line)
    text = re.sub(r"[ \t]+#+[ \t]*$", "", text)
    text = re.sub(r"!?\[([^\]]*)\]\([^)]*\)", r"\1", text)
    text = re.sub(r"<[^>]+>", "", text)
    text = text.replace("**", "").replace("__", "").replace("`", "")
    return " ".join(text.split())


def _is_hebrew_letter(ch: str) -> bool:
    return 0x05D0 <= ord(ch) <= 0x05EA or 0x05F0 <= ord(ch) <= 0x05F2


def heading_rule_violation(rendered: str) -> str | None:
    """None if the rendered heading satisfies the rule, else the reason.
    Step 1: no direction-control character anywhere. Step 2: the first
    strongly directional character (bidi class L, R or AL) is a Hebrew letter;
    spaces, punctuation and digits before it are skipped."""
    for ch in rendered:
        if ord(ch) in DIRECTION_CONTROLS:
            return f"direction-control character U+{ord(ch):04X}"
    for ch in rendered:
        if unicodedata.bidirectional(ch) in ("L", "R", "AL"):
            if _is_hebrew_letter(ch):
                return None
            return f"first strong character {ch!r} is not a Hebrew letter"
    return "no strongly directional character"


# What may appear as an image in REPORT.md: an ALLOW-LIST, not a Markdown parser.
#
# An earlier version re-implemented parts of CommonMark (code fences, reference
# definitions, multi-line HTML) to find the images that hide, and every review
# round found one more way around it (a fence closed by a non-breaking space, an
# <img> tag split over two lines, a definition split over two lines). The rule
# now fails CLOSED instead:
#
#   * An image may be written in exactly two forms, ALONE on its line:
#       chart    ![alt](a.svg)    optionally with a link title ("t", 't' or (t))
#       raster   ![alt](a.png)    png, jpg, jpeg, gif or webp
#     The target is a plain path with no spaces: an <angle-bracket> target would
#     be read as an HTML tag, and file names here have no spaces.
#   * Any other "![" is a violation: inside a sentence, a list, a quote or a table;
#     reference style (![alt][label]); split over lines; with an escaped or
#     entity-encoded target; as a data: URI; wrapped in a link.
#   * Raw HTML is an allow-list too: only <details>, <summary> and <br> (for
#     folding and line breaks) and <!-- comments --> are accepted. Any other tag is
#     a violation wherever its opening tag starts, even when its attributes continue
#     on the next line. (A blocklist of picture elements missed <video poster=...>.)
#
# Code fences, inline code spans and link reference definitions are NOT tracked
# at all. Image syntax or an HTML tag written inside one is refused like any other
# (a conservative false positive), so nothing can hide there. An earlier version
# removed inline code spans before scanning; unequal backtick runs fooled it
# (``![x](a.svg)` renders an image next to literal backticks). Write an example of
# markup in words, not in code.
#
# A heading above a chart may not contain "&", a backslash, "[" or "]". Entities and
# escapes change what the reader sees (&#80;3 is displayed as P3, &#8207; is an
# invisible right-to-left mark), and the heading rule reads the source. Brackets
# are links: a link-looking "[](a b) text" is not a link (a space in the target),
# so GitHub shows it literally, while the rule strips it as if it were one.
# Refusing the characters closes every such form at once instead of emulating a
# decoder or a link parser.
#
# Not covered: a picture whose target does not end in .svg (a URL without an
# extension), and CSS or JavaScript outside an HTML tag (any tag but the three
# above is already refused). A "<" followed by a letter is read as a tag, even
# inside backticks, so write a comparison with a space (n < m) or in words.
_CHART_LINE = re.compile(
    r"""^[ \t]*!\[[^\]]*\]\(\s*[^)\s<>]+\.svg"""
    r"""(?:\s+(?:"[^"]*"|'[^']*'|\([^)]*\)))?\s*\)[ \t]*$""",
    re.IGNORECASE,
)
_RASTER_LINE = re.compile(
    r"""^[ \t]*!\[[^\]]*\]\(\s*[^)\s<>]+\.(?:png|jpe?g|gif|webp)"""
    r"""(?:\s+(?:"[^"]*"|'[^']*'|\([^)]*\)))?\s*\)[ \t]*$""",
    re.IGNORECASE,
)
_HTML_TAG = re.compile(r"<(/?)([A-Za-z][A-Za-z0-9-]*)")
_HTML_OTHER = re.compile(r"<(?:!(?!--)|\?)")      # <!DOCTYPE>, <![CDATA[, <?processing?>
ALLOWED_HTML_TAGS = frozenset({"details", "summary", "br"})


def chart_heading_violations(markdown: str) -> list[str]:
    """Violations of the image rules in a rendered REPORT (see above). Every
    chart must have an ATX heading as the nearest non-blank line above it, and
    that heading must satisfy the heading rule; the number of charts must equal
    the number of headings above them. Raster images need no heading."""
    lines = markdown.splitlines()
    violations: list[str] = []
    n_charts = n_headings = 0
    for i, line in enumerate(lines):
        bad_tags = sorted({m.group(2).lower() for m in _HTML_TAG.finditer(line)} - ALLOWED_HTML_TAGS)
        if bad_tags or _HTML_OTHER.search(line):
            violations.append(
                f"line {i + 1}: raw HTML is limited to <details>, <summary> and <br> "
                f"(found {bad_tags or 'a special tag'}); write images as ![alt](file.svg) alone on their line"
            )
            continue
        if "![" not in line:
            continue
        if _RASTER_LINE.match(line):
            continue
        if not _CHART_LINE.match(line):
            violations.append(
                f"line {i + 1}: an image must be written inline, alone on its line, "
                "with a plain .svg/.png/.jpg/.gif/.webp target"
            )
            continue
        n_charts += 1
        j = i - 1
        while j >= 0 and not lines[j].strip():
            j -= 1
        if j < 0 or not is_atx_heading(lines[j]):
            violations.append(f"line {i + 1}: chart has no heading directly above it")
            continue
        n_headings += 1
        if any(ch in lines[j] for ch in ("&", chr(92), "[", "]")):
            violations.append(
                f"line {j + 1}: a chart heading may not contain '&', a backslash, '[' or ']' "
                f"(entities, escapes and links change what is displayed): {lines[j].strip()!r}"
            )
            continue
        reason = heading_rule_violation(rendered_heading_text(lines[j]))
        if reason:
            violations.append(f"line {j + 1}: {reason}: {lines[j].strip()!r}")
    if n_charts != n_headings:
        violations.append(f"{n_charts} charts but {n_headings} headings above them")
    return violations

# ---------------------------------------------------------------------------
# The digit scan -- INFORMATIONAL, never an assertion (PHASE13.md D2).
# ---------------------------------------------------------------------------
def scan_template_digits(template_text: str) -> dict[str, int]:
    """Every digit run left in a template's literal text, with placeholders
    removed first (their names may contain digits). The output is pasted into
    PHASE13.md with a justification per run; nothing here fails on it."""
    literal = re.sub(r"\$(?:\$|\{\w+\}|\w+)", "", template_text)
    counts: dict[str, int] = {}
    for run in re.findall(r"\d+", literal):
        counts[run] = counts.get(run, 0) + 1
    return dict(sorted(counts.items(), key=lambda kv: (int(kv[0]), kv[0])))


# ---------------------------------------------------------------------------
# Calibration chart from stored data -- no training (PHASE13.md D8).
# ---------------------------------------------------------------------------
def write_calibration_svg(task: str, out_path: Path, sources: Sources | None = None) -> None:
    """Renders `task`'s Holdout calibration chart from models/metrics.json with
    scripts.train's own renderer, so it is the same chart family as the P3/P4
    ones (regenerating those from metrics.json reproduces the committed SVGs
    byte for byte). scripts.train is imported lazily: it pulls in
    catboost/lightgbm/xgboost, which nothing else in this module needs."""
    from scripts import train

    curve = (sources or Sources()).value("metrics", (f"{task}_holdout", "calibration_curve"))
    train._svg_calibration_curve(task, curve, Path(out_path))


# ---------------------------------------------------------------------------
def _display(path: Path) -> str:
    """A path for a message: repo-relative when it is inside the repo, else as given."""
    try:
        return str(Path(path).relative_to(REPO))
    except ValueError:
        return str(path)


def main(argv: list[str]) -> int:
    if argv[:1] == ["--calibration-svg"]:
        if len(argv) != 2:
            print("usage: --calibration-svg <P3|P4|P4S>", file=sys.stderr)
            return 2
        out = REPO / "docs" / f"calibration_curve_{argv[1]}.svg"
        write_calibration_svg(argv[1], out)
        print(f"wrote {out}")
        return 0

    template_path = DEFAULT_TEMPLATE
    if not template_path.is_file():
        print(f"template not found: {_display(template_path)} (written in CP4)", file=sys.stderr)
        return 1
    template_text = template_path.read_text(encoding="utf-8")
    text = render_report(template_text)
    problems = chart_heading_violations(text)
    if problems:
        print("chart rule violations:\n  " + "\n  ".join(problems), file=sys.stderr)
        return 1
    DEFAULT_OUT.write_text(text, encoding="utf-8", newline="\n")
    print(f"wrote {DEFAULT_OUT}")
    print("digit sequences remaining in the literal template text (info only, PHASE13.md D2):")
    for run, count in scan_template_digits(template_text).items():
        print(f"  {run}  (x{count})")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
