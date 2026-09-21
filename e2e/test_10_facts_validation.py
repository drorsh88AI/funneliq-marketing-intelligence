"""P11A checkpoint 5 (docs/planning/PHASE11A.md P11A-D2): facts.js's own
per-block typed validation. `block()`'s PREVIOUS check (`typeof value
=== "object"`) accepted a malformed-but-present block -- an empty
object, an array, a numeric field replaced by `0` (a legitimate divisor
elsewhere), or a missing field -- and let it flow straight through to
a consumer's arithmetic/formatPercent/formatCurrency call, producing
NaN or Infinity in the DOM instead of the block degrading to "null,
same as missing" the way D2 requires.

PHASE11A.md sec ז falsification cases 1, 3, 4, 6, 7, 8, 9 -- case 2's
own screen (P4S) and case 5 (total asset failure) are covered
elsewhere (this file and test_07 respectively). Every degraded-state
assertion below is bridged to docs/DESIGN.md directly (cases 7-9's own
rigor, matching test_05/test_06/test_09's established pattern), not a
substring check -- a prior round of this checkpoint used weaker
substring assertions that a Codex review correctly rejected."""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import fixtures as fx
from conftest import route_json, sign_in_and_wait

REPO_ROOT = Path(__file__).resolve().parent.parent

# Same private-module-name load as test_05/06/09's own bridge.
_design_tokens_spec = importlib.util.spec_from_file_location(
    "_design_tokens_bridge_facts10", REPO_ROOT / "tests" / "test_design_tokens.py"
)
_design_tokens_bridge = importlib.util.module_from_spec(_design_tokens_spec)
_design_tokens_spec.loader.exec_module(_design_tokens_bridge)

_design_md_text = (REPO_ROOT / "docs" / "DESIGN.md").read_text(encoding="utf-8")

PREDICT_VALUES = {
    "ad_budget": "5000", "num_leads": "100", "leads_answered": "80",
    "followup_1": "70", "followup_2": "60", "followup_3": "50",
    "followup_4": "40", "followup_5": "30", "closed": "10",
    "calls_to_closed": "3", "calls_to_not_closed": "2",
    "customer_acquisition_cost": "500",
}
P4S_ROW = {"ad_budget": 5000, "num_leads": 100, "leads_answered": 80, "followup_1": 70}


def _open_predict(page):
    page.click('a[data-route="predict"]')
    page.wait_for_selector("#field-ad_budget")


def _fill_predict(page):
    for field, value in PREDICT_VALUES.items():
        page.fill(f"#field-{field}", value)


def _open_p4s(page):
    page.click('a[data-route="super-customer"]')
    page.wait_for_selector("#p4s-field-ad_budget")


def _fill_p4s(page):
    for field in ("ad_budget", "num_leads", "leads_answered", "followup_1"):
        page.fill(f"#p4s-field-{field}", str(P4S_ROW[field]))


# ---------------------------------------------------------------------------
# Shared D9 four-layer structural helpers (test_05/06/09's own pattern).
# ---------------------------------------------------------------------------

_D9_EXPECTED_KEYS = ["answer", "meaning", "action", "caveat"]
_D9_EXPECTED_LABELS = ["תשובה", "מה זה אומר", "מה כדאי לעשות", "חשוב לדעת"]


def _assert_well_formed_d9_layers(layers):
    assert [layer["key"] for layer in layers] == _D9_EXPECTED_KEYS
    assert [layer["label"] for layer in layers] == _D9_EXPECTED_LABELS
    for layer in layers:
        assert layer["text"], f"layer {layer['key']!r} has empty text"


def _read_d9_layers(page, scope_selector):
    return page.eval_on_selector_all(
        f"{scope_selector} .summary-recommendation .summary-layer",
        """(elements) => elements.map((element) => {
            const keyClass = [...element.classList].find(
                (c) => c.startsWith("summary-layer-")
            );
            return {
                key: keyClass ? keyClass.replace("summary-layer-", "") : null,
                label: element.querySelector(".summary-layer-label")?.textContent ?? "",
                text: element.querySelector(".summary-layer-text")?.textContent ?? "",
            };
        })""",
    )


_ROW_LABEL_TO_D9_KEY = {
    "תשובה פשוטה": "answer",
    "משמעות עסקית": "meaning",
    "פעולה מומלצת": "action",
    "מגבלה": "caveat",
}
_degradation_rows = _design_tokens_bridge._extract_markdown_table(
    _design_md_text, _design_tokens_bridge._DEGRADATION_TABLE_HEADER_ROW
)


def _degraded_layers_for(target):
    layers = {}
    for target_cell, layer_cell, wording_cell, _source_cell in _degradation_rows:
        if target_cell.strip("*") != target:
            continue
        layers[_ROW_LABEL_TO_D9_KEY[layer_cell.strip()]] = wording_cell.strip()
    assert set(layers) == set(_D9_EXPECTED_KEYS), (
        f"docs/DESIGN.md sec 6.1c: expected exactly the 4 {target!r} rows, "
        f"got {sorted(layers)}"
    )
    return layers


_LTR_ISOLATE_START, _LTR_ISOLATE_END = chr(0x2066), chr(0x2069)

# --- P2 (predict.js) degraded bridge, fx.ltv_prediction_success()'s own
# defaults (point=24.0, lower=18.0, upper=30.0). ---
_P2_ROUNDED, _P2_LOWER, _P2_UPPER = 24, 18, 30
_P2_DEGRADED_LAYERS = _degraded_layers_for("P2")
_P2_DEGRADED_LAYERS["answer"] = (
    _P2_DEGRADED_LAYERS["answer"]
    .replace("{ltv_months}", str(_P2_ROUNDED))
    .replace("{ltv_lower}", str(_P2_LOWER))
    .replace("{ltv_upper}", str(_P2_UPPER))
)
_P2_LEAKED_STRINGS = ("calls_to_closed", "ממוצע שיחות עד סגירה", "מדיניות השיחות")

# --- P4S (super-customer.js) degraded bridge, fx.super_customer_prediction_success()'s
# own defaults (event_probability=0.2, base_rate=0.1672). ---
_P4S_SCORE = 20
_P4S_BASE_RATE_PCT = "16.72%"
_P4S_DEGRADED_LAYERS = _degraded_layers_for("P4S")
_P4S_DEGRADED_LAYERS["answer"] = (
    _P4S_DEGRADED_LAYERS["answer"]
    .replace("{p4s_score}", f"{_LTR_ISOLATE_START}{_P4S_SCORE}{_LTR_ISOLATE_END}")
    .replace("{p4s_base_rate}", _P4S_BASE_RATE_PCT)
)
# fx.super_customer_prediction_success()'s own defaults, used UNMODIFIED
# in this file (unlike test_09, which deliberately injects a distinct
# model_algorithm/holdout pair to prove live-wiring -- that proof
# already exists there; this file's own job is the D2 block-validation
# contract, not re-proving D5's caveat wiring).
_P4S_MODEL_ALGORITHM = "CatBoost"
_P4S_HOLDOUT_ROC_AUC = "0.800"  # formatNumber(0.8, decimals=3)
_P4S_HOLDOUT_PR_AUC = "0.370"  # formatNumber(0.37, decimals=3)
_P4S_DEGRADED_LAYERS["caveat"] = (
    _P4S_DEGRADED_LAYERS["caveat"]
    .replace("{p4s_model_algorithm}", f"{_LTR_ISOLATE_START}{_P4S_MODEL_ALGORITHM}{_LTR_ISOLATE_END}")
    .replace("{p4s_holdout_roc_auc}", _P4S_HOLDOUT_ROC_AUC)
    .replace("{p4s_holdout_pr_auc}", _P4S_HOLDOUT_PR_AUC)
)
_P4S_LEAKED_STRINGS = ("רווח גבוה", "עלות רכישה נמוכה", "לקוחות-על הניבו")

# --- Budget Simulator (budget.js) degraded bridge -- no placeholders at
# all in these 4 cells. ---
_BUDGET_DEGRADED_LAYERS = _degraded_layers_for("Budget Simulator")
_BUDGET_LEAKED_STRINGS = ("100×500", "25×2,000", "פיילוט")


# ---------------------------------------------------------------------------
# Base fixture blocks. scripts/business_facts.py's own exact shape --
# `ltv.rank_1_by_algorithm` ALWAYS carries all three P2_ALGORITHMS keys.
# ---------------------------------------------------------------------------

_VALID_LTV = {
    "dominant_feature": "calls_to_closed",
    "rank_1_by_algorithm": {
        "catboost": {"feature": "calls_to_closed", "importance": 96.0},
        "lightgbm": {"feature": "calls_to_closed", "importance": 90.0},
        "xgboost": {"feature": "calls_to_closed", "importance": 88.0},
    },
}
_VALID_BUDGET_BACKTEST = {
    "500": {"actual_mean_per_customer": 918.65, "n_holdout_at_level": 17, "n_train_at_level": 92, "predicted_per_customer": 7895.94},
    "2000": {"actual_mean_per_customer": 20650.88, "n_holdout_at_level": 85, "n_train_at_level": 322, "predicted_per_customer": 21238.12},
}
_VALID_SUPER_CUSTOMER_PROFILE = {
    "cac_population_mean": 1437.0, "cac_savings_pct": 0.31, "cac_super_mean": 990.0,
    "n_purchased": 3163, "n_super": 529, "pct_of_purchased": 0.16, "pct_of_total_profit": 0.33,
    "population_definition": "x",
}
_VALID_FOLLOWUP_CONTEXT = {
    "mean_calls_closed_eq_1": 5.65, "mean_calls_closed_ge_2": 3.35, "population_definition": "closed>0",
}


def _business_facts(*, schema_version=1, ltv=_VALID_LTV, budget_backtest=_VALID_BUDGET_BACKTEST,
                     super_customer_profile=_VALID_SUPER_CUSTOMER_PROFILE, followup_context=_VALID_FOLLOWUP_CONTEXT):
    return {
        "budget_backtest": budget_backtest,
        "followup_context": followup_context,
        "ltv": ltv,
        "metrics_sha256": "8af98f45f595a830b26055be5eab053c85c43c6fc6d97732c45b34b9f3166723",
        "model_versions": {
            "P2": "P2-catboost-e2e", "P3": "P3-xgboost-e2e", "P4": "P4-logistic-e2e",
            "P4S": "P4S-catboost-e2e", "P6": "P6-linear-e2e",
        },
        "schema_version": schema_version,
        "source_csv_sha256": "8ac67d50a6f96a8ece8abd770a5a1901b34036a5c98656455eb04cee07d707aa",
        "source_keys": {"budget_backtest": "x", "followup_context": "x", "ltv": "x", "super_customer_profile": "x"},
        "super_customer_profile": super_customer_profile,
    }


def _assert_p2_degrades(mocked_page):
    mocked_page.wait_for_selector(".prediction-panel-p2 .prediction-primary", timeout=10_000)
    assert mocked_page.query_selector(".prediction-panel-p2 .ltv-leverage-tip") is None
    layers = _read_d9_layers(mocked_page, ".prediction-panel-p2")
    _assert_well_formed_d9_layers(layers)
    rendered = {layer["key"]: layer["text"] for layer in layers}
    assert rendered == _P2_DEGRADED_LAYERS
    combined = " ".join(rendered.values())
    for leaked in _P2_LEAKED_STRINGS:
        assert leaked not in combined, f"{leaked!r} leaked into a degraded P2 D9 layer: {rendered!r}"


def _assert_budget_degrades(mocked_page):
    mocked_page.wait_for_selector(".strategy-table", timeout=10_000)
    assert len(mocked_page.query_selector_all(".strategy-row")) == 4  # untouched (case 9's own carve-out)
    layers = _read_d9_layers(mocked_page, "#screen-budget")
    _assert_well_formed_d9_layers(layers)
    rendered = {layer["key"]: layer["text"] for layer in layers}
    assert rendered == _BUDGET_DEGRADED_LAYERS
    combined = " ".join(rendered.values())
    for leaked in _BUDGET_LEAKED_STRINGS:
        assert leaked not in combined, f"{leaked!r} leaked into a degraded Budget D9 layer: {rendered!r}"


# ---------------------------------------------------------------------------
# Case 1 -- ltv.
# ---------------------------------------------------------------------------

def test_case_1_literal_empty_ltv_block_degrades_fully(mocked_page, mocked_context):
    """Falsification case 1, literal: `"ltv": {}`."""
    route_json(mocked_context, "**/api/me", fx.api_me())
    route_json(mocked_context, "**/api/insights/budget-tiers", fx.budget_tiers_response())
    route_json(mocked_context, "**/rest/v1/funnel_records*", [])
    route_json(mocked_context, "**/business_facts.json", _business_facts(ltv={}))
    sign_in_and_wait(mocked_page, mocked_context)

    route_json(mocked_context, "**/api/predict/ltv", fx.ltv_prediction_success())
    route_json(mocked_context, "**/api/predict/upsell", fx.propensity_prediction_success())
    route_json(mocked_context, "**/api/predict/referral", fx.propensity_prediction_success())
    _open_predict(mocked_page)
    _fill_predict(mocked_page)
    mocked_page.check(".context-confirmation input[type=checkbox]")
    mocked_page.click(".submit-button")
    _assert_p2_degrades(mocked_page)


def test_case_1_mutation_wrong_typed_dominant_feature_degrades_fully(mocked_page, mocked_context):
    """Mutation-sensitive companion to case 1: predict.js's own guard
    (`if (leverage && leverage.dominant_feature)`) already tolerates a
    literally empty `ltv` (dominant_feature is `undefined`, falsy) --
    so the literal case above would NOT have caught a regression in
    facts.js's own validation, only in predict.js's. A `dominant_feature`
    that is present AND truthy but the wrong type (a number, not
    `null`/a string) is not caught by that guard: pre-D2,
    `FIELD_META[42]` is `undefined`, so `featureLabel` falls back to the
    raw number and the tip renders "...הוא 42 (42)." verbatim. Verified
    this fixture actually fails against the pre-CP5 facts.js."""
    route_json(mocked_context, "**/api/me", fx.api_me())
    route_json(mocked_context, "**/api/insights/budget-tiers", fx.budget_tiers_response())
    route_json(mocked_context, "**/rest/v1/funnel_records*", [])
    route_json(mocked_context, "**/business_facts.json", _business_facts(ltv={"dominant_feature": 42, "rank_1_by_algorithm": _VALID_LTV["rank_1_by_algorithm"]}))
    sign_in_and_wait(mocked_page, mocked_context)

    route_json(mocked_context, "**/api/predict/ltv", fx.ltv_prediction_success())
    route_json(mocked_context, "**/api/predict/upsell", fx.propensity_prediction_success())
    route_json(mocked_context, "**/api/predict/referral", fx.propensity_prediction_success())
    _open_predict(mocked_page)
    _fill_predict(mocked_page)
    mocked_page.check(".context-confirmation input[type=checkbox]")
    mocked_page.click(".submit-button")
    _assert_p2_degrades(mocked_page)
    # Belt-and-suspenders on top of the full-layer equality above: "42"
    # itself must not appear anywhere in the D9 layers.
    d9_text = mocked_page.text_content(".prediction-panel-p2 .summary-recommendation")
    assert "42" not in d9_text


def test_case_1_mutation_partial_rank_algorithms_direct(mocked_page, mocked_context):
    """A third mutation, targeting the specific gap a Codex review round
    found in isValidLtv(): `rank_1_by_algorithm` with only ONE of the
    three keys scripts/business_facts.py always writes together
    (catboost/lightgbm/xgboost) is a PARTIAL block, not a smaller-but-
    complete one -- P11A-D2's own "בלוק חלקי ⇒ null כמו חסר" applies
    here exactly as much as to a missing key elsewhere.

    Exercised via the DIRECT accessor, not a screen: predict.js never
    reads `rank_1_by_algorithm` at all (only `dominant_feature`), so a
    DOM-level test of this exact mutation would pass identically against
    the OLD, unfixed validator too -- verified empirically before
    writing this test this way, not assumed. `dominant_feature` is left
    `null` (independently valid) so only the partial
    `rank_1_by_algorithm` is under test."""
    partial_ltv = {"dominant_feature": None, "rank_1_by_algorithm": {"catboost": {"feature": "calls_to_closed", "importance": 96.0}}}
    route_json(mocked_context, "**/business_facts.json", _business_facts(ltv=partial_ltv))
    result = mocked_page.evaluate("""
        (async () => {
            const facts = await import('/js/facts.js');
            facts.resetForTest();
            await facts.init();
            return facts.getLtvLeverage('P2-catboost-e2e');
        })()
    """)
    assert result is None, f"a partial rank_1_by_algorithm (1 of 3 keys) should be rejected, got {result!r}"


# ---------------------------------------------------------------------------
# Case 2 -- super_customer_profile.
# ---------------------------------------------------------------------------

def test_case_2_super_customer_profile_missing_one_field_degrades_fully(mocked_page, mocked_context):
    """Falsification case 2: `super_customer_profile` present but
    missing ONE numeric field (`cac_savings_pct`) -- the business-context
    card must be hidden ENTIRELY (IA.md sec 3a.6's own mandatory
    sentence is all-or-nothing, never a NaN%), and the D9 "meaning"
    layer degrades exactly like a missing block; "answer"/"action"/
    "caveat" (never dependent on this asset) render their live values
    untouched. Verified this fixture actually fails against the
    pre-CP5 facts.js."""
    broken_profile = {k: v for k, v in _VALID_SUPER_CUSTOMER_PROFILE.items() if k != "cac_savings_pct"}
    route_json(mocked_context, "**/api/me", fx.api_me())
    route_json(mocked_context, "**/api/insights/budget-tiers", fx.budget_tiers_response())
    route_json(mocked_context, "**/rest/v1/funnel_records*", [])
    route_json(mocked_context, "**/business_facts.json", _business_facts(super_customer_profile=broken_profile))
    sign_in_and_wait(mocked_page, mocked_context)

    route_json(mocked_context, "**/api/predict/super-customer", fx.super_customer_prediction_success())
    _open_p4s(mocked_page)
    _fill_p4s(mocked_page)
    mocked_page.check(".context-confirmation input[type=checkbox]")
    mocked_page.click(".submit-button")

    mocked_page.wait_for_selector(".prediction-panel-p4s .prediction-primary", timeout=10_000)
    assert mocked_page.query_selector(".prediction-panel-p4s .business-context-card") is None
    layers = _read_d9_layers(mocked_page, ".prediction-panel-p4s")
    _assert_well_formed_d9_layers(layers)
    rendered = {layer["key"]: layer["text"] for layer in layers}
    assert rendered["meaning"] == _P4S_DEGRADED_LAYERS["meaning"]
    assert rendered["answer"] == _P4S_DEGRADED_LAYERS["answer"]
    assert rendered["action"] == _P4S_DEGRADED_LAYERS["action"]
    assert rendered["caveat"] == _P4S_DEGRADED_LAYERS["caveat"]
    combined = " ".join(rendered.values())
    for leaked in _P4S_LEAKED_STRINGS:
        assert leaked not in combined, f"{leaked!r} leaked into a degraded P4S D9 layer: {rendered!r}"


# ---------------------------------------------------------------------------
# Case 3 -- budget_backtest.
# ---------------------------------------------------------------------------

def test_case_3_literal_missing_2000_level_degrades_fully(mocked_page, mocked_context):
    """Falsification case 3, literal: `budget_backtest: {"500": {}}`."""
    route_json(mocked_context, "**/api/me", fx.api_me())
    route_json(mocked_context, "**/api/insights/budget-tiers", fx.budget_tiers_response())
    route_json(mocked_context, "**/business_facts.json", _business_facts(budget_backtest={"500": {}}))
    route_json(mocked_context, "**/api/simulate/budget", fx.budget_simulation(model_version="P6-linear-e2e"))
    sign_in_and_wait(mocked_page, mocked_context)

    mocked_page.click('a[data-route="budget"]')
    _assert_budget_degrades(mocked_page)


def test_case_3_mutation_missing_predicted_field_degrades_fully(mocked_page, mocked_context):
    """Mutation-sensitive companion to case 3: budget.js's own defensive
    check (`if (backtest && backtest["500"] && backtest["2000"])`)
    already tolerates the "2000" level being absent entirely -- so the
    literal case above would NOT have caught a regression in facts.js's
    own validation, only in budget.js's. BOTH levels present and
    otherwise well-formed, but "500" missing `predicted_per_customer`
    specifically, passes that defensive check (both truthy objects) and
    reaches the ratio division itself: `undefined / 918.65` is `NaN`,
    rendered as the literal string "NaN" by Intl.NumberFormat --
    "...גבוהה פי NaN מהתוצאה בפועל". Verified this fixture actually
    fails against the pre-CP5 facts.js."""
    broken_500 = {k: v for k, v in _VALID_BUDGET_BACKTEST["500"].items() if k != "predicted_per_customer"}
    route_json(mocked_context, "**/api/me", fx.api_me())
    route_json(mocked_context, "**/api/insights/budget-tiers", fx.budget_tiers_response())
    route_json(mocked_context, "**/business_facts.json", _business_facts(budget_backtest={"500": broken_500, "2000": _VALID_BUDGET_BACKTEST["2000"]}))
    route_json(mocked_context, "**/api/simulate/budget", fx.budget_simulation(model_version="P6-linear-e2e"))
    sign_in_and_wait(mocked_page, mocked_context)

    mocked_page.click('a[data-route="budget"]')
    _assert_budget_degrades(mocked_page)


def test_case_4_budget_backtest_zero_actual_mean_degrades_fully(mocked_page, mocked_context):
    """Falsification case 4: `actual_mean_per_customer: 0` at the "500"
    level -- a legitimate-looking JSON number, and both levels otherwise
    structurally complete, so budget.js's own defensive truthiness check
    does not catch this either. Dividing `predicted_per_customer` by
    zero produces `Infinity`, which `Intl.NumberFormat` renders as the
    "∞" glyph -- NOT the literal word "Infinity" (verified directly:
    `new Intl.NumberFormat().format(Infinity)` -> "∞"; an earlier draft
    of this test asserted the wrong string and would have passed
    silently even with the bug present). Verified this fixture actually
    fails against the pre-CP5 facts.js."""
    zero_denominator_backtest = {
        "500": {**_VALID_BUDGET_BACKTEST["500"], "actual_mean_per_customer": 0},
        "2000": _VALID_BUDGET_BACKTEST["2000"],
    }
    route_json(mocked_context, "**/api/me", fx.api_me())
    route_json(mocked_context, "**/api/insights/budget-tiers", fx.budget_tiers_response())
    route_json(mocked_context, "**/business_facts.json", _business_facts(budget_backtest=zero_denominator_backtest))
    route_json(mocked_context, "**/api/simulate/budget", fx.budget_simulation(model_version="P6-linear-e2e"))
    sign_in_and_wait(mocked_page, mocked_context)

    mocked_page.click('a[data-route="budget"]')
    _assert_budget_degrades(mocked_page)
    screen_text = mocked_page.text_content("#screen-budget")
    assert "∞" not in screen_text  # the "∞" glyph Intl.NumberFormat renders Infinity as


def test_case_4b_budget_backtest_zero_actual_mean_at_2000_stays_healthy(mocked_page, mocked_context):
    """Code-review finding, 2026-09-21: `actual_mean_per_customer` is
    never divided by at the "2000" level anywhere in budget.js (only
    `.n_train_at_level` is read from "2000") -- only "500"'s own value
    is a divisor (`predicted_per_customer / actual_mean_per_customer`).
    An earlier draft of `isValidBudgetBacktest` required positivity at
    BOTH levels uniformly, degrading the entire block -- and hiding a
    perfectly valid "500" comparison -- whenever "2000" alone reported
    a non-positive mean, a legitimate small-holdout-sample outcome, not
    a malformed asset. Verified this fixture actually fails (block
    treated as absent, healthy text never renders) against facts.js
    before this fix."""
    zero_at_2000_only = {
        "500": _VALID_BUDGET_BACKTEST["500"],
        "2000": {**_VALID_BUDGET_BACKTEST["2000"], "actual_mean_per_customer": 0},
    }
    route_json(mocked_context, "**/api/me", fx.api_me())
    route_json(mocked_context, "**/api/insights/budget-tiers", fx.budget_tiers_response())
    route_json(mocked_context, "**/business_facts.json", _business_facts(budget_backtest=zero_at_2000_only))
    route_json(mocked_context, "**/api/simulate/budget", fx.budget_simulation(model_version="P6-linear-e2e"))
    sign_in_and_wait(mocked_page, mocked_context)

    mocked_page.click('a[data-route="budget"]')
    mocked_page.wait_for_selector(".strategy-table", timeout=10_000)
    screen_text = mocked_page.text_content("#screen-budget")
    for expected in _BUDGET_LEAKED_STRINGS:  # present here == healthy, NOT degraded
        assert expected in screen_text, f"{expected!r} missing -- block treated as invalid solely due to 2000's non-divisor field"


# ---------------------------------------------------------------------------
# Case 6 -- schema_version.
# ---------------------------------------------------------------------------

def test_case_6_unrecognized_schema_version_degrades_like_total_failure(mocked_page, mocked_context):
    """Falsification case 6: an unrecognized `schema_version` is
    rejected by `ensureLoaded()` itself (checkpoint 2's own pre-existing
    gate, before ANY per-block validator runs) -- `loaded` stays `null`
    entirely, identical to a load failure or a 500 response. Exercised
    on P2 as the representative consumer (the same code path degrades
    every block identically, since none of them are reached at all)."""
    route_json(mocked_context, "**/api/me", fx.api_me())
    route_json(mocked_context, "**/api/insights/budget-tiers", fx.budget_tiers_response())
    route_json(mocked_context, "**/rest/v1/funnel_records*", [])
    route_json(mocked_context, "**/business_facts.json", _business_facts(schema_version=2))
    sign_in_and_wait(mocked_page, mocked_context)

    route_json(mocked_context, "**/api/predict/ltv", fx.ltv_prediction_success())
    route_json(mocked_context, "**/api/predict/upsell", fx.propensity_prediction_success())
    route_json(mocked_context, "**/api/predict/referral", fx.propensity_prediction_success())
    _open_predict(mocked_page)
    _fill_predict(mocked_page)
    mocked_page.check(".context-confirmation input[type=checkbox]")
    mocked_page.click(".submit-button")
    _assert_p2_degrades(mocked_page)


# ---------------------------------------------------------------------------
# followup_context has no UI consumer at all (test_07's own 2026-09-18
# finding) -- exercised directly against the accessor via a dynamic
# `import()` of facts.js in the page, so a regression here isn't
# invisible just because nothing renders it yet. No sign-in needed:
# /js/facts.js and /business_facts.json are both unauthenticated static
# routes.
# ---------------------------------------------------------------------------

def test_followup_context_accessor_contract_direct(mocked_page, mocked_context):
    scenarios = [
        (_business_facts(followup_context=_VALID_FOLLOWUP_CONTEXT), _VALID_FOLLOWUP_CONTEXT, "valid fixture must return the block in full"),
        (
            _business_facts(followup_context={k: v for k, v in _VALID_FOLLOWUP_CONTEXT.items() if k != "mean_calls_closed_eq_1"}),
            None,
            "missing numeric field must return null",
        ),
        (_business_facts(followup_context=["not", "an", "object"]), None, "an array must be rejected (Array.isArray), not accepted as \"an object\""),
    ]
    for business_facts, expected, description in scenarios:
        route_json(mocked_context, "**/business_facts.json", business_facts)
        result = mocked_page.evaluate("""
            (async () => {
                const facts = await import('/js/facts.js');
                facts.resetForTest();
                await facts.init();
                return facts.getFollowupContext();
            })()
        """)
        assert result == expected, description


def test_all_four_blocks_reject_arrays_directly(mocked_page, mocked_context):
    """P11A-D2: `typeof [] === "object"` is `true` -- every block's
    validator must reject an array explicitly (`Array.isArray`), not
    accept it as "an object". Verified directly against each accessor,
    not inferred from a screen's own downstream behavior (which, for
    ltv/budget_backtest, would otherwise mask this the same way the
    mutation tests above found their OWN screens' defensive checks do)."""
    cases = [
        # `_business_facts()`'s own default model_versions.P2/P6 --
        # NOT a mismatched value. getLtvLeverage/getBudgetBacktest check
        # validity FIRST and only fall through to the model_version
        # compare if the block passed -- but with the OLD, unfixed
        # facts.js, an array WAS accepted as valid (`typeof [] ===
        # "object"`), so a mismatched model_version would ALSO return
        # null there, for the WRONG reason, masking the exact gap this
        # test exists to catch. A Codex review caught this precisely:
        # verified empirically that 'anything' let the old code's bug
        # hide behind a version-mismatch null for these two blocks.
        ("ltv", "facts.getLtvLeverage('P2-catboost-e2e')", _business_facts(ltv=[])),
        ("budget_backtest", "facts.getBudgetBacktest('P6-linear-e2e')", _business_facts(budget_backtest=[])),
        ("super_customer_profile", "facts.getSuperCustomerProfile()", _business_facts(super_customer_profile=[])),
        ("followup_context", "facts.getFollowupContext()", _business_facts(followup_context=[])),
    ]
    for block_name, accessor_expr, business_facts in cases:
        route_json(mocked_context, "**/business_facts.json", business_facts)
        result = mocked_page.evaluate(f"""
            (async () => {{
                const facts = await import('/js/facts.js');
                facts.resetForTest();
                await facts.init();
                return {accessor_expr};
            }})()
        """)
        assert result is None, f"{block_name} as an array should be rejected, got {result!r}"
