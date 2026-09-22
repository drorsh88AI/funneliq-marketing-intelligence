"""P11A checkpoint 3 (docs/planning/PHASE11A.md P11A-D5) -- P4S
(super-customer.js)'s own two business_facts.json-dependent pieces:
`buildBusinessContextCard()` (IA.md sec 3a.6's mandatory sentence,
hidden alone on asset failure) and the D9 "meaning" layer built by
`buildD9Meaning()`, which -- before this checkpoint -- asserted the
profile's own profit/CAC conclusion even with the asset unavailable.
Mirrors e2e/test_05_predict_form_and_facts.py's own case 20/20b
structure and its lessons: the business_facts.json mock MUST be
registered before sign_in_and_wait() (app.js's bootstrap calls
facts.init() right when #authenticated-shell mounts, not lazily at
submit time), and the canonical wording is bridged from docs/DESIGN.md
directly, not hand-copied from super-customer.js a second time."""
from __future__ import annotations

import importlib.util
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import fixtures as fx
from conftest import route_json, sign_in_and_wait

REPO_ROOT = Path(__file__).resolve().parent.parent

# Same private-module-name load as test_05's own bridge -- avoids
# colliding with pytest's collection of tests/test_design_tokens.py as
# the top-level module "test_design_tokens" when both suites run
# together.
_design_tokens_spec = importlib.util.spec_from_file_location(
    "_design_tokens_bridge_p4s", REPO_ROOT / "tests" / "test_design_tokens.py"
)
_design_tokens_bridge = importlib.util.module_from_spec(_design_tokens_spec)
_design_tokens_spec.loader.exec_module(_design_tokens_bridge)

_design_md_text = (REPO_ROOT / "docs" / "DESIGN.md").read_text(encoding="utf-8")


def _open_p4s(page):
    page.click('a[data-route="super-customer"]')
    page.wait_for_selector("#p4s-field-ad_budget")


def _fill_p4s(page, row):
    for field in ("ad_budget", "num_leads", "leads_answered", "followup_1"):
        page.fill(f"#p4s-field-{field}", str(row[field]))


P4S_ROW = {"ad_budget": 5000, "num_leads": 100, "leads_answered": 80, "followup_1": 70}

# `fx.super_customer_prediction_success()`'s own defaults (event_probability,
# base_rate) -- all three tests below use them unmodified, so the
# rendered `answer` layer is pinned to one literal string, not just
# checked for a substring.
_P4S_SCORE = 20  # round(event_probability=0.2 * 100)
_P4S_BASE_RATE_PCT = "16.72%"  # formatPercent(0.1672, decimals=2 default)

# Deliberately NOT "CatBoost"/0.8014-ish values -- those were the OLD
# hardcoded caveat text this checkpoint removed. Using them here would
# let a test pass even if buildCaveatText() were still reading a
# constant instead of `d.model_algorithm`/`d.metrics.holdout`, since the
# "live" value would coincidentally match the stale one. Every test
# below overrides the fixture's own default with THESE via
# _p4s_prediction_payload(), so a literal match can only mean the
# caveat is actually wired to the response.
_P4S_MODEL_ALGORITHM = "XGBoost"
_P4S_HOLDOUT_ROC_AUC_RAW = 0.612
_P4S_HOLDOUT_PR_AUC_RAW = 0.234
_P4S_HOLDOUT_ROC_AUC = "0.612"  # formatNumber(0.612, decimals=3)
_P4S_HOLDOUT_PR_AUC = "0.234"  # formatNumber(0.234, decimals=3)
_LTR_ISOLATE_START, _LTR_ISOLATE_END = chr(0x2066), chr(0x2069)


def _p4s_prediction_payload(ood=False, **kwargs):
    """SuperCustomerPrediction payload with model_algorithm/holdout
    metrics overridden to the deliberately-distinct values above --
    see the comment on them for why."""
    payload = fx.super_customer_prediction_ood(**kwargs) if ood else fx.super_customer_prediction_success(**kwargs)
    payload["model_algorithm"] = _P4S_MODEL_ALGORITHM
    payload["metrics"]["holdout"]["roc_auc"] = _P4S_HOLDOUT_ROC_AUC_RAW
    payload["metrics"]["holdout"]["pr_auc"] = _P4S_HOLDOUT_PR_AUC_RAW
    return payload

_D9_EXPECTED_KEYS = ["answer", "meaning", "action", "caveat"]
_D9_EXPECTED_LABELS = ["תשובה", "מה זה אומר", "מה כדאי לעשות", "חשוב לדעת"]


def _assert_well_formed_d9_layers(layers):
    assert [layer["key"] for layer in layers] == _D9_EXPECTED_KEYS
    assert [layer["label"] for layer in layers] == _D9_EXPECTED_LABELS
    for layer in layers:
        assert layer["text"], f"layer {layer['key']!r} has empty text"


def _read_p4s_d9_layers(page):
    return page.eval_on_selector_all(
        ".prediction-panel-p4s .summary-recommendation .summary-layer",
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


_P4S_ROW_LABEL_TO_D9_KEY = {
    "תשובה פשוטה": "answer",
    "משמעות עסקית": "meaning",
    "פעולה מומלצת": "action",
    "מגבלה": "caveat",
}

# Falsification case 8, bridged: the degraded P4S wording is EXTRACTED
# from docs/DESIGN.md's own sec 6.1c table, not hand-copied from
# super-customer.js a second time.
_degradation_rows = _design_tokens_bridge._extract_markdown_table(
    _design_md_text, _design_tokens_bridge._DEGRADATION_TABLE_HEADER_ROW
)
_P4S_DEGRADED_LAYERS = {}
for _target_cell, _layer_cell, _wording_cell, _source_cell in _degradation_rows:
    if _target_cell.strip("*") != "P4S":
        continue
    _P4S_DEGRADED_LAYERS[_P4S_ROW_LABEL_TO_D9_KEY[_layer_cell.strip()]] = _wording_cell.strip()
assert set(_P4S_DEGRADED_LAYERS) == set(_D9_EXPECTED_KEYS), (
    f"docs/DESIGN.md sec 6.1c: expected exactly the 4 P4S rows "
    f"{sorted(_P4S_ROW_LABEL_TO_D9_KEY)}, got {sorted(_P4S_DEGRADED_LAYERS)} -- "
    f"table structure changed, update this bridge"
)
# "answer" and "caveat" are the only rows carrying placeholders here,
# each occurring exactly once with a distinct name -- substituted with
# this file's own fixture values above.
_P4S_DEGRADED_LAYERS["answer"] = (
    _P4S_DEGRADED_LAYERS["answer"]
    .replace("{p4s_score}", f"{_LTR_ISOLATE_START}{_P4S_SCORE}{_LTR_ISOLATE_END}")
    .replace("{p4s_base_rate}", _P4S_BASE_RATE_PCT)
)
_P4S_DEGRADED_LAYERS["caveat"] = (
    _P4S_DEGRADED_LAYERS["caveat"]
    .replace("{p4s_model_algorithm}", f"{_LTR_ISOLATE_START}{_P4S_MODEL_ALGORITHM}{_LTR_ISOLATE_END}")
    .replace("{p4s_holdout_roc_auc}", _P4S_HOLDOUT_ROC_AUC)
    .replace("{p4s_holdout_pr_auc}", _P4S_HOLDOUT_PR_AUC)
)

# The live (non-degraded) wording for "answer"/"action"/"caveat" is
# bridged the same way, from DESIGN.md sec 6.1's own D9 six-column
# matrix. "meaning" is left out of this dict on purpose -- see the
# regex bridge below, needed because its template repeats the SAME
# placeholder name ({אחוז}) three times for three DIFFERENT values,
# which a simple named .replace() can't disambiguate.
_p4s_matrix_pattern = dict(_design_tokens_bridge._D9_TARGET_PATTERNS)["P4S"]
_healthy_matrix_rows = _design_tokens_bridge._extract_markdown_table(
    _design_md_text, _design_tokens_bridge._D9_MATRIX_HEADER_ROW
)
_p4s_healthy_rows = [row for row in _healthy_matrix_rows if _p4s_matrix_pattern.search(row[0])]
assert len(_p4s_healthy_rows) == 1, (
    f"docs/DESIGN.md sec 6.1: expected exactly 1 P4S row in the D9 "
    f"six-column matrix, found {len(_p4s_healthy_rows)} -- table "
    f"structure changed, update this bridge"
)
_p4s_healthy_row = _p4s_healthy_rows[0]
_P4S_HEALTHY_LAYERS = {
    "answer": (
        _p4s_healthy_row[1].strip()
        .replace("{X}", f"{_LTR_ISOLATE_START}{_P4S_SCORE}{_LTR_ISOLATE_END}")
        .replace("{Y}", _P4S_BASE_RATE_PCT)
    ),
    "action": _p4s_healthy_row[3].strip(),
    "caveat": (
        _p4s_healthy_row[4].strip()
        .replace("{p4s_model_algorithm}", f"{_LTR_ISOLATE_START}{_P4S_MODEL_ALGORITHM}{_LTR_ISOLATE_END}")
        .replace("{p4s_holdout_roc_auc}", _P4S_HOLDOUT_ROC_AUC)
        .replace("{p4s_holdout_pr_auc}", _P4S_HOLDOUT_PR_AUC)
    ),
}
for _key in ("answer", "action", "caveat"):
    assert _P4S_HEALTHY_LAYERS[_key] == _P4S_DEGRADED_LAYERS[_key], (
        f"docs/DESIGN.md's two P4S {_key!r} rows (sec 6.1 and sec 6.1c) no "
        f"longer agree once both are filled with the same live values: "
        f"{_P4S_HEALTHY_LAYERS[_key]!r} != {_P4S_DEGRADED_LAYERS[_key]!r}"
    )


def _fill_ordered_placeholders(template, values):
    """Fills a DESIGN.md wording cell's `{...}` placeholders IN ORDER
    with `values`, whatever their names -- needed for the P4S healthy
    "meaning" row specifically, whose {אחוז}/{עלות} placeholder names
    repeat for different values, so a named .replace() can't disambiguate
    them. This is still a full, exact substitution (unlike a wildcard
    regex, which would let ANY value -- including a wrong one -- pass);
    only the ORDER is inferred, not the content."""
    parts = re.split(r"\{[^{}]*\}", template)
    assert len(parts) == len(values) + 1, (
        f"template has {len(parts) - 1} placeholders, expected {len(values)}: {template!r}"
    )
    result = parts[0]
    for value, part in zip(values, parts[1:]):
        result += value + part
    return result


# _MATCHING_SUPER_CUSTOMER_PROFILE's own 5 values, formatted exactly as
# buildD9Meaning()/format.js render them, in the template's own
# left-to-right order: pct_of_purchased, pct_of_total_profit,
# cac_super_mean, cac_population_mean, cac_savings_pct.
_P4S_HEALTHY_MEANING = _fill_ordered_placeholders(
    _p4s_healthy_row[2].strip(),
    ["16.0%", "33.0%", "₪990.00", "₪1,437.00", "31.0%"],
)


def _p4s_business_facts(super_customer_profile):
    return {
        "budget_backtest": {"500": {"actual_mean_per_customer": 918.65, "n_holdout_at_level": 17, "n_train_at_level": 92, "predicted_per_customer": 7895.94}},
        "followup_context": {"mean_calls_closed_eq_1": 5.65, "mean_calls_closed_ge_2": 3.35, "population_definition": "closed>0"},
        "ltv": {"dominant_feature": "calls_to_closed", "rank_1_by_algorithm": {"catboost": {"feature": "calls_to_closed", "importance": 96.0}, "lightgbm": {"feature": "calls_to_closed", "importance": 90.0}, "xgboost": {"feature": "calls_to_closed", "importance": 88.0}}},
        "metrics_sha256": "8af98f45f595a830b26055be5eab053c85c43c6fc6d97732c45b34b9f3166723",
        "model_versions": {
            "P2": "P2-catboost-e2e", "P3": "P3-xgboost-e2e", "P4": "P4-logistic-e2e",
            "P4S": "P4S-catboost-e2e", "P6": "P6-linear-e2e",
        },
        "schema_version": 1,
        "source_csv_sha256": "8ac67d50a6f96a8ece8abd770a5a1901b34036a5c98656455eb04cee07d707aa",
        "source_keys": {"budget_backtest": "x", "followup_context": "x", "ltv": "x", "super_customer_profile": "x"},
        "super_customer_profile": super_customer_profile,
    }


_MATCHING_SUPER_CUSTOMER_PROFILE = {
    "cac_population_mean": 1437.0, "cac_savings_pct": 0.31, "cac_super_mean": 990.0,
    "n_purchased": 3163, "n_super": 529, "pct_of_purchased": 0.16, "pct_of_total_profit": 0.33,
    "population_definition": "x",
}

# Falsification case 9's three anchors for THIS screen -- the profit/CAC
# conclusion (a direction, not a specific number, since the degraded row
# carries none) must be absent from all four D9 layers jointly.
_LEAKED_PROFIT_CAC_STRINGS = ("רווח גבוה", "עלות רכישה נמוכה", "לקוחות-על הניבו")


def test_p4s_business_facts_unavailable_degrades_meaning_only(mocked_page, mocked_context):
    """P11A-D5, falsification cases 2/7/8/9: `super_customer_profile`
    missing (asset present, this ONE block absent -- facts.js's own
    per-block independence, P11-D15) hides the business-context card
    entirely and degrades ONLY the D9 "meaning" layer to the canonical
    wording -- "answer"/"action"/"caveat" are untouched (they never
    depended on this asset), and no profit/CAC conclusion leaks into
    any of the four layers."""
    route_json(mocked_context, "**/api/me", fx.api_me())
    route_json(mocked_context, "**/api/insights/budget-tiers", fx.budget_tiers_response())
    route_json(mocked_context, "**/rest/v1/funnel_records*", [])
    # Must be registered before sign_in_and_wait() -- see module header.
    route_json(mocked_context, "**/business_facts.json", _p4s_business_facts(None))
    sign_in_and_wait(mocked_page, mocked_context)

    route_json(mocked_context, "**/api/predict/super-customer", _p4s_prediction_payload())
    _open_p4s(mocked_page)
    _fill_p4s(mocked_page, P4S_ROW)
    mocked_page.check(".context-confirmation input[type=checkbox]")
    mocked_page.click(".submit-button")

    mocked_page.wait_for_selector(".prediction-panel-p4s .prediction-primary", timeout=10_000)
    assert mocked_page.query_selector(".prediction-panel-p4s .business-context-card") is None

    layers = _read_p4s_d9_layers(mocked_page)
    _assert_well_formed_d9_layers(layers)
    rendered = {layer["key"]: layer["text"] for layer in layers}
    assert rendered["meaning"] == _P4S_DEGRADED_LAYERS["meaning"]
    assert rendered["answer"] == _P4S_DEGRADED_LAYERS["answer"]
    assert rendered["action"] == _P4S_DEGRADED_LAYERS["action"]
    assert rendered["caveat"] == _P4S_DEGRADED_LAYERS["caveat"]

    combined_text = " ".join(rendered.values())
    for leaked in _LEAKED_PROFIT_CAC_STRINGS:
        assert leaked not in combined_text, f"{leaked!r} leaked into a degraded D9 layer: {rendered!r}"


def test_p4s_business_facts_available_shows_full_profile_and_live_caveat(mocked_page, mocked_context):
    """Falsification case 11's companion for this screen: a valid
    fixture must return the full profile-derived "meaning" text (bridged
    to DESIGN.md sec 6.1's own template) AND the live model_algorithm/
    Holdout metrics in "caveat" -- not the old hardcoded CatBoost/
    0.8014/0.3420/Recall text this checkpoint removed."""
    route_json(mocked_context, "**/api/me", fx.api_me())
    route_json(mocked_context, "**/api/insights/budget-tiers", fx.budget_tiers_response())
    route_json(mocked_context, "**/rest/v1/funnel_records*", [])
    route_json(mocked_context, "**/business_facts.json", _p4s_business_facts(_MATCHING_SUPER_CUSTOMER_PROFILE))
    sign_in_and_wait(mocked_page, mocked_context)

    route_json(mocked_context, "**/api/predict/super-customer", _p4s_prediction_payload())
    _open_p4s(mocked_page)
    _fill_p4s(mocked_page, P4S_ROW)
    mocked_page.check(".context-confirmation input[type=checkbox]")
    mocked_page.click(".submit-button")

    mocked_page.wait_for_selector(".prediction-panel-p4s .prediction-primary", timeout=10_000)
    card_text = mocked_page.text_content(".prediction-panel-p4s .business-context-card")
    assert "16.0%" in card_text
    assert "NaN" not in card_text

    layers = _read_p4s_d9_layers(mocked_page)
    _assert_well_formed_d9_layers(layers)
    rendered = {layer["key"]: layer["text"] for layer in layers}
    # Exact match, with the profile's 5 values substituted in the
    # template's own order -- not a wildcard shape check, so a wrong
    # value (not just wrong wording) would fail this.
    assert rendered["meaning"] == _P4S_HEALTHY_MEANING
    assert rendered["answer"] == _P4S_HEALTHY_LAYERS["answer"]
    assert rendered["action"] == _P4S_HEALTHY_LAYERS["action"]
    assert rendered["caveat"] == _P4S_HEALTHY_LAYERS["caveat"]


def test_p4s_ood_caveat_still_built_from_response_without_recall(mocked_page, mocked_context):
    """buildCaveatText(d) is called from BOTH the OOD branch and the
    healthy branch of buildP4SPanel() -- this test exercises the OOD
    one specifically (neither test_08's existing coverage nor this
    file's other two tests ever reach it). `in_training_domain=false`
    comes straight from the mocked response, so this needs no special
    field values to actually trigger OOD server-side -- the frontend
    branches on `d.in_training_domain` alone."""
    route_json(mocked_context, "**/api/me", fx.api_me())
    route_json(mocked_context, "**/api/insights/budget-tiers", fx.budget_tiers_response())
    route_json(mocked_context, "**/rest/v1/funnel_records*", [])
    # app.js's bootstrap fetches business_facts.json unconditionally
    # regardless of screen (see module header) -- routed even though
    # this OOD branch never reads super_customer_profile itself.
    route_json(mocked_context, "**/business_facts.json", _p4s_business_facts(_MATCHING_SUPER_CUSTOMER_PROFILE))
    sign_in_and_wait(mocked_page, mocked_context)

    route_json(mocked_context, "**/api/predict/super-customer", _p4s_prediction_payload(ood=True))
    _open_p4s(mocked_page)
    _fill_p4s(mocked_page, P4S_ROW)
    mocked_page.check(".context-confirmation input[type=checkbox]")
    mocked_page.click(".submit-button")

    mocked_page.wait_for_selector(".prediction-panel-p4s .ood-banner", timeout=10_000)
    layers = _read_p4s_d9_layers(mocked_page)
    _assert_well_formed_d9_layers(layers)
    rendered = {layer["key"]: layer["text"] for layer in layers}
    # "זהה למצב תקין" (DESIGN.md's own note on this row) -- the OOD
    # caveat is the identical literal text, built from the SAME
    # deliberately-distinct model_algorithm/holdout values.
    assert rendered["caveat"] == _P4S_DEGRADED_LAYERS["caveat"]
    assert "Recall" not in rendered["caveat"]
    assert "CatBoost" not in rendered["caveat"]
    assert "0.8014" not in rendered["caveat"] and "0.3420" not in rendered["caveat"]
