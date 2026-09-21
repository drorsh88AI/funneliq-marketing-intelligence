"""PHASE11.md §י, cases 22 and 23. Also P11A checkpoint 5's own
falsification case 5 (docs/planning/PHASE11A.md §ז): a TOTAL
business_facts.json failure (500 status here) must degrade P2/Budget/
P4S -- the three screens with a live consumer -- to the exact
DESIGN.md §6.1c wording in all four D9 layers, with no pilot
recommendation and no ranking claim, not just "the tip/recommendation
paragraph disappears" (test_case_22's own original assertions, before
this round, only checked that).

⚠ Finding, 2026-09-18: `facts.getFollowupContext()` is exported by
facts.js but never called anywhere in app/static/js/ (grepped the
whole tree) -- followup.js's own D9 "answer" text is a hardcoded
constant (CP4D_RECOMMENDATION), not a runtime read of the
`followup_context` block PHASE11.md's own ד3 table lists as that
block's consumer. So there is no live UI path on the Follow-up screen
for business_facts.json's degradation to affect -- case 22's own claim
about this specific block has no code to falsify on THIS screen, and
this file's own test_case_22 only exercises the three blocks that do
have a real runtime consumer (P2/Budget/P4S). getFollowupContext()'s
own contract is instead exercised directly in
e2e/test_10_facts_validation.py (P11A checkpoint 5)."""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import fixtures as fx
from conftest import route_json, route_status, sign_in_and_wait

REPO_ROOT = Path(__file__).resolve().parent.parent

# Same private-module-name load as test_05/06/09/10's own bridge.
_design_tokens_spec = importlib.util.spec_from_file_location(
    "_design_tokens_bridge_facts07", REPO_ROOT / "tests" / "test_design_tokens.py"
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
        f"docs/DESIGN.md sec 6.1c: expected exactly the 4 {target!r} rows, got {sorted(layers)}"
    )
    return layers


_LTR_ISOLATE_START, _LTR_ISOLATE_END = chr(0x2066), chr(0x2069)

# fx.ltv_prediction_success()'s own defaults.
_P2_ROUNDED, _P2_LOWER, _P2_UPPER = 24, 18, 30
_P2_DEGRADED_LAYERS = _degraded_layers_for("P2")
_P2_DEGRADED_LAYERS["answer"] = (
    _P2_DEGRADED_LAYERS["answer"]
    .replace("{ltv_months}", str(_P2_ROUNDED))
    .replace("{ltv_lower}", str(_P2_LOWER))
    .replace("{ltv_upper}", str(_P2_UPPER))
)

# fx.super_customer_prediction_success()'s own defaults.
_P4S_SCORE = 20
_P4S_BASE_RATE_PCT = "16.72%"
_P4S_MODEL_ALGORITHM = "CatBoost"
_P4S_HOLDOUT_ROC_AUC = "0.800"
_P4S_HOLDOUT_PR_AUC = "0.370"
_P4S_DEGRADED_LAYERS = _degraded_layers_for("P4S")
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

# No placeholders in Budget Simulator's degraded rows at all.
_BUDGET_DEGRADED_LAYERS = _degraded_layers_for("Budget Simulator")

_P2_LEAKED_STRINGS = ("calls_to_closed", "ממוצע שיחות עד סגירה", "מדיניות השיחות")
_P4S_LEAKED_STRINGS = ("רווח גבוה", "עלות רכישה נמוכה", "לקוחות-על הניבו")
_BUDGET_LEAKED_STRINGS = ("100×500", "25×2,000", "פיילוט")


def test_case_22_business_facts_load_failure_hides_only_dependent_content(mocked_page, mocked_context):
    """22. business_facts.json נכשל בטעינה ⇒ מוסתר רק התוכן התלוי בנכס;
    אפס השבתה של תוצאות API. Tested on predict.js's P2 leverage tip,
    budget.js's backtest recommendation, and super-customer.js's P4S
    profile card -- the three live consumers. Each screen's full D9
    four-layer content is checked against docs/DESIGN.md sec 6.1c
    directly (falsification cases 7-9), not just "the extra paragraph
    disappeared" -- Budget's own check in particular proves NO pilot
    recommendation survives (DESIGN.md:547-548's own explicit rule)."""
    route_json(mocked_context, "**/api/me", fx.api_me())
    route_json(mocked_context, "**/api/insights/budget-tiers", fx.budget_tiers_response())
    route_json(mocked_context, "**/rest/v1/funnel_records*", [])
    route_status(mocked_context, "**/business_facts.json", 500)
    route_json(mocked_context, "**/api/predict/ltv", fx.ltv_prediction_success())
    route_json(mocked_context, "**/api/predict/upsell", fx.propensity_prediction_success())
    route_json(mocked_context, "**/api/predict/referral", fx.propensity_prediction_success())
    route_json(mocked_context, "**/api/simulate/budget", fx.budget_simulation())
    route_json(mocked_context, "**/api/predict/super-customer", fx.super_customer_prediction_success())
    sign_in_and_wait(mocked_page, mocked_context)

    mocked_page.click('a[data-route="predict"]')
    mocked_page.wait_for_selector("#field-ad_budget")
    for field, value in PREDICT_VALUES.items():
        mocked_page.fill(f"#field-{field}", value)
    mocked_page.check("#screen-predict .context-confirmation input[type=checkbox]")
    mocked_page.click("#screen-predict .submit-button")

    mocked_page.wait_for_selector(".prediction-panel-p2 .prediction-primary", timeout=10_000)
    assert mocked_page.query_selector(".prediction-panel-p2 .ltv-leverage-tip") is None
    assert mocked_page.query_selector(".prediction-panel-p3 .prediction-primary") is not None
    assert mocked_page.query_selector(".prediction-panel-p4 .prediction-primary") is not None
    p2_layers = _read_d9_layers(mocked_page, ".prediction-panel-p2")
    _assert_well_formed_d9_layers(p2_layers)
    p2_rendered = {layer["key"]: layer["text"] for layer in p2_layers}
    assert p2_rendered == _P2_DEGRADED_LAYERS
    p2_combined = " ".join(p2_rendered.values())
    for leaked in _P2_LEAKED_STRINGS:
        assert leaked not in p2_combined, f"{leaked!r} leaked into a degraded P2 D9 layer: {p2_rendered!r}"

    mocked_page.click('a[data-route="super-customer"]')
    mocked_page.wait_for_selector("#p4s-field-ad_budget")
    for field in ("ad_budget", "num_leads", "leads_answered", "followup_1"):
        mocked_page.fill(f"#p4s-field-{field}", str(P4S_ROW[field]))
    mocked_page.check("#screen-super-customer .context-confirmation input[type=checkbox]")
    mocked_page.click("#screen-super-customer .submit-button")

    mocked_page.wait_for_selector(".prediction-panel-p4s .prediction-primary", timeout=10_000)
    assert mocked_page.query_selector(".prediction-panel-p4s .business-context-card") is None
    p4s_layers = _read_d9_layers(mocked_page, ".prediction-panel-p4s")
    _assert_well_formed_d9_layers(p4s_layers)
    p4s_rendered = {layer["key"]: layer["text"] for layer in p4s_layers}
    assert p4s_rendered == _P4S_DEGRADED_LAYERS
    p4s_combined = " ".join(p4s_rendered.values())
    for leaked in _P4S_LEAKED_STRINGS:
        assert leaked not in p4s_combined, f"{leaked!r} leaked into a degraded P4S D9 layer: {p4s_rendered!r}"

    mocked_page.click('a[data-route="budget"]')
    mocked_page.wait_for_selector(".strategy-table", timeout=10_000)
    overlap_text = mocked_page.text_content(".overlap-alert")
    assert "8.6" not in overlap_text
    assert len(mocked_page.query_selector_all(".strategy-row")) == 4
    budget_layers = _read_d9_layers(mocked_page, "#screen-budget")
    _assert_well_formed_d9_layers(budget_layers)
    budget_rendered = {layer["key"]: layer["text"] for layer in budget_layers}
    assert budget_rendered == _BUDGET_DEGRADED_LAYERS
    budget_combined = " ".join(budget_rendered.values())
    for leaked in _BUDGET_LEAKED_STRINGS:
        assert leaked not in budget_combined, f"{leaked!r} leaked into a degraded Budget D9 layer: {budget_rendered!r}"


def test_case_23_followup_partial_failure_shows_available_marks_missing_no_number(mocked_page, mocked_context):
    """23. followup מחזיר חלק אחד תקין וחלק אחד כושל ⇒ התקין מוצג, החסר
    מסומן, אין מספר שמור."""
    route_json(mocked_context, "**/api/me", fx.api_me())
    route_json(mocked_context, "**/api/insights/budget-tiers", fx.budget_tiers_response())
    route_json(mocked_context, "**/rest/v1/funnel_records*", [])
    route_json(
        mocked_context, "**/api/insights/followup",
        fx.followup_response(stages=fx.followup_stages_available(), calls=fx.followup_calls_unavailable()),
    )
    sign_in_and_wait(mocked_page, mocked_context)

    mocked_page.click('a[data-route="followup"]')
    mocked_page.wait_for_selector(".followup-layout", timeout=10_000)

    groups = mocked_page.query_selector_all(".followup-group")
    assert len(groups) == 2
    # Stages (available) rendered a real chart -- no panel-error inside it.
    # Self-review finding: an earlier version of this assertion OR'd the
    # chart-element check with "נשירה" in the group's text -- but that
    # heading is appended in BOTH the success and the panel-error
    # branches (buildStagesGroup's own code), so the OR made this
    # tautologically true regardless of whether a chart ever rendered.
    stages_group = groups[0]
    assert stages_group.query_selector(".panel-error") is None
    assert stages_group.query_selector(".chart-live") is not None
    # Calls (unavailable) is explicitly marked, not silently blank or zeroed.
    calls_group = groups[1]
    assert calls_group.query_selector(".panel-error") is not None

    # No invented/leftover combined number -- the joint recommendation
    # explicitly says it is unavailable instead.
    rec_text = mocked_page.text_content(".followup-recommendation")
    assert "אינה זמינה" in rec_text
    assert mocked_page.query_selector(".followup-recommendation h3") is None
