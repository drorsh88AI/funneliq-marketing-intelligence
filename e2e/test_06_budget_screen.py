"""PHASE11.md §י, cases 21 and 24 -- Budget Simulator screen:
business_facts.json P6 model_version mismatch hides only the
backtest-backed recommendation (never the strategy table), and a live
top_two_overlap=true blocks any winning-strategy declaration.

Also P11A checkpoint 4 (docs/planning/PHASE11A.md P11A-D6): buildD9()'s
own four-layer content, degraded and healthy."""
from __future__ import annotations

import importlib.util
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import fixtures as fx
from conftest import route_json, sign_in_and_wait

REPO_ROOT = Path(__file__).resolve().parent.parent

# Same private-module-name load as test_05/test_09's own bridge.
_design_tokens_spec = importlib.util.spec_from_file_location(
    "_design_tokens_bridge_budget", REPO_ROOT / "tests" / "test_design_tokens.py"
)
_design_tokens_bridge = importlib.util.module_from_spec(_design_tokens_spec)
_design_tokens_spec.loader.exec_module(_design_tokens_bridge)

_design_md_text = (REPO_ROOT / "docs" / "DESIGN.md").read_text(encoding="utf-8")


def _facts(p6_model_version: str) -> dict:
    return {
        "budget_backtest": {
            "2000": {"actual_mean_per_customer": 20650.88, "n_holdout_at_level": 85, "n_train_at_level": 322, "predicted_per_customer": 21238.12},
            "500": {"actual_mean_per_customer": 918.65, "n_holdout_at_level": 17, "n_train_at_level": 92, "predicted_per_customer": 7895.94},
        },
        "followup_context": {"mean_calls_closed_eq_1": 5.65, "mean_calls_closed_ge_2": 3.35, "population_definition": "closed>0"},
        "ltv": {"dominant_feature": "calls_to_closed", "rank_1_by_algorithm": {"catboost": {"feature": "calls_to_closed", "importance": 96.0}, "lightgbm": {"feature": "calls_to_closed", "importance": 90.0}, "xgboost": {"feature": "calls_to_closed", "importance": 88.0}}},
        "metrics_sha256": "8af98f45f595a830b26055be5eab053c85c43c6fc6d97732c45b34b9f3166723",
        "model_versions": {
            "P2": "P2-catboost-e2e", "P3": "P3-xgboost-e2e", "P4": "P4-logistic-e2e",
            "P4S": "P4S-catboost-e2e", "P6": p6_model_version,
        },
        "schema_version": 1,
        "source_csv_sha256": "8ac67d50a6f96a8ece8abd770a5a1901b34036a5c98656455eb04cee07d707aa",
        "source_keys": {"budget_backtest": "x", "followup_context": "x", "ltv": "x", "super_customer_profile": "x"},
        "super_customer_profile": {"cac_population_mean": 1437.0, "cac_savings_pct": 0.31, "cac_super_mean": 990.0, "n_purchased": 3163, "n_super": 529, "pct_of_purchased": 0.16, "pct_of_total_profit": 0.33, "population_definition": "x"},
    }


def test_case_21_p6_model_version_mismatch_hides_recommendation_keeps_table(mocked_page, mocked_context):
    """21. model_versions.P6 אינו תואם ⇒ מוסתרים ההמלצה וה-backtest;
    הטבלה נשארת."""
    route_json(mocked_context, "**/api/me", fx.api_me())
    route_json(mocked_context, "**/api/insights/budget-tiers", fx.budget_tiers_response())
    route_json(mocked_context, "**/business_facts.json", _facts("P6-DOES-NOT-MATCH-LIVE"))
    route_json(mocked_context, "**/api/simulate/budget", fx.budget_simulation(model_version="P6-linear-e2e"))
    sign_in_and_wait(mocked_page, mocked_context)

    mocked_page.click('a[data-route="budget"]')
    mocked_page.wait_for_selector(".strategy-table", timeout=10_000)
    overlap_text = mocked_page.text_content(".overlap-alert")
    assert "8.6" not in overlap_text  # the backtest-backed ratio sentence is gone
    assert "100×500 מדורגת ראשונה" not in overlap_text
    # The always-present strategy table survives untouched.
    rows = mocked_page.query_selector_all(".strategy-row")
    assert len(rows) == 4


def test_case_24_top_two_overlap_blocks_winner_declaration(mocked_page, mocked_context):
    """24. top_two_overlap=true ⇒ אין הכרזה על אסטרטגיה מנצחת ואין
    100x500 כהמלצה."""
    route_json(mocked_context, "**/api/me", fx.api_me())
    route_json(mocked_context, "**/api/insights/budget-tiers", fx.budget_tiers_response())
    route_json(mocked_context, "**/business_facts.json", _facts("P6-linear-e2e"))
    route_json(mocked_context, "**/api/simulate/budget", fx.budget_simulation(top_two_overlap=True, model_version="P6-linear-e2e"))
    sign_in_and_wait(mocked_page, mocked_context)

    mocked_page.click('a[data-route="budget"]')
    mocked_page.wait_for_selector(".overlap-alert", timeout=10_000)
    overlap_text = mocked_page.text_content(".overlap-alert")
    assert "אין הכרזה על אסטרטגיה מנצחת" in overlap_text
    # The backtest sentence, when present, explicitly disclaims itself
    # as a recommendation ("אינה המלצה") -- never framed as a winner.
    assert "100×500 מדורגת ראשונה מספרית, אך אינה המלצה" in overlap_text
    assert "האסטרטגיה המדורגת ראשונה" not in overlap_text  # the OTHER (non-overlap) branch's own wording


# ---------------------------------------------------------------------------
# P11A checkpoint 4 (P11A-D6): buildD9()'s own four layers, degraded and
# healthy.
# ---------------------------------------------------------------------------

_D9_EXPECTED_KEYS = ["answer", "meaning", "action", "caveat"]
_D9_EXPECTED_LABELS = ["תשובה", "מה זה אומר", "מה כדאי לעשות", "חשוב לדעת"]


def _assert_well_formed_d9_layers(layers):
    assert [layer["key"] for layer in layers] == _D9_EXPECTED_KEYS
    assert [layer["label"] for layer in layers] == _D9_EXPECTED_LABELS
    for layer in layers:
        assert layer["text"], f"layer {layer['key']!r} has empty text"


def _read_budget_d9_layers(page):
    return page.eval_on_selector_all(
        "#screen-budget .summary-recommendation .summary-layer",
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


_BUDGET_ROW_LABEL_TO_D9_KEY = {
    "תשובה פשוטה": "answer",
    "משמעות עסקית": "meaning",
    "פעולה מומלצת": "action",
    "מגבלה": "caveat",
}

# Falsification case 8, bridged: none of the four degraded Budget cells
# carry a `{placeholder}` at all (unlike P2/P4S's own rows) -- this is a
# direct, unmodified equality check against docs/DESIGN.md sec 6.1c.
_degradation_rows = _design_tokens_bridge._extract_markdown_table(
    _design_md_text, _design_tokens_bridge._DEGRADATION_TABLE_HEADER_ROW
)
_BUDGET_DEGRADED_LAYERS = {}
for _target_cell, _layer_cell, _wording_cell, _source_cell in _degradation_rows:
    if _target_cell.strip("*") != "Budget Simulator":
        continue
    _BUDGET_DEGRADED_LAYERS[_BUDGET_ROW_LABEL_TO_D9_KEY[_layer_cell.strip()]] = _wording_cell.strip()
assert set(_BUDGET_DEGRADED_LAYERS) == set(_D9_EXPECTED_KEYS), (
    f"docs/DESIGN.md sec 6.1c: expected exactly the 4 Budget Simulator "
    f"rows, got {sorted(_BUDGET_DEGRADED_LAYERS)} -- table structure "
    f"changed, update this bridge"
)

# The healthy "answer"/"meaning"/"action" cells are bridged from
# DESIGN.md sec 6.1's own D9 six-column matrix -- NOT extracted from
# budget.js (an earlier draft of this bridge did that; a Codex review
# round correctly rejected it: if budget.js regressed, that same
# regression would flow into the "oracle" and the test would stay
# green, exactly the failure mode CP2/CP3's own bridges to DESIGN.md
# were built to prevent). The row's markdown, unlike the degraded
# table, needs a genuine DISPLAY transform before it's comparable to
# rendered text -- but every step is deterministic and independently
# justified, not a copy of the code's own wording:
#   1. strip markdown backticks (`100x500` -> 100x500)
#   2. map each raw strategy_id to IA.md sec 6's own LOCKED display
#      form (IA.md:633-634 -- "100x500 -> 100×500", "25x2000 -> 25×2,000")
#   3. drop the inline historical-correction footnote verbatim -- it is
#      explicitly a documentation-only note ("תוקן מ-8.59...", citing a
#      past phase/checkpoint), never product text shown to a user
#   4. wrap the two LIVE, fixture-derived numbers (the ratio, n_train_
#      at_level) in the same U+2066/U+2069 isolate characters
#      format.ltr() uses -- both computed from _facts()'s own dict
#      below, never hand-typed, so a wrong fixture value would also
#      change what this bridge expects
_p6_matrix_pattern = dict(_design_tokens_bridge._D9_TARGET_PATTERNS)["Budget Simulator"]
_healthy_matrix_rows = _design_tokens_bridge._extract_markdown_table(
    _design_md_text, _design_tokens_bridge._D9_MATRIX_HEADER_ROW
)
_budget_healthy_rows = [row for row in _healthy_matrix_rows if _p6_matrix_pattern.search(row[0])]
assert len(_budget_healthy_rows) == 1, (
    f"docs/DESIGN.md sec 6.1: expected exactly 1 Budget Simulator row in "
    f"the D9 six-column matrix, found {len(_budget_healthy_rows)} -- "
    f"table structure changed, update this bridge"
)
_budget_healthy_row = _budget_healthy_rows[0]

_STRATEGY_ID_DISPLAY_FORM = {"100x500": "100×500", "25x2000": "25×2,000"}  # IA.md:633-634, locked
_LTR_ISOLATE_START, _LTR_ISOLATE_END = chr(0x2066), chr(0x2069)


def _budget_matrix_cell_to_display_text(cell):
    text = cell.replace("`", "")
    for raw_id, display_id in _STRATEGY_ID_DISPLAY_FORM.items():
        text = text.replace(raw_id, display_id)
    # The historical-correction footnote: "(תוקן מ-8.59 בפאזה 11
    # checkpoint 7 — עיגול סטנדרטי, ר' §6.1א)" -- documentation-only,
    # never rendered in the live UI.
    text = re.sub(r"\s*\(תוקן מ-8\.59.*?\)", "", text)
    return text


# _facts()'s own dict -- the SAME one test_case_21/24 above and the
# degraded test below all route -- read directly, not retyped as
# separate float literals, so a wrong fixture value changes this
# bridge's expectation too, not just the rendered page's.
_matching_facts = _facts("P6-linear-e2e")
_budget_500 = _matching_facts["budget_backtest"]["500"]
_budget_2000 = _matching_facts["budget_backtest"]["2000"]
_BUDGET_RATIO = f"{_budget_500['predicted_per_customer'] / _budget_500['actual_mean_per_customer']:.2f}"
_BUDGET_N2000 = str(_budget_2000["n_train_at_level"])
assert _BUDGET_RATIO == "8.60" and _BUDGET_N2000 == "322", (
    f"_facts()'s own backtest numbers changed (ratio={_BUDGET_RATIO!r}, "
    f"n2000={_BUDGET_N2000!r}) -- update the values this bridge and "
    f"DESIGN.md's own row both assume, or investigate why they moved"
)

_BUDGET_HEALTHY_LAYERS = {
    "answer": _budget_matrix_cell_to_display_text(_budget_healthy_row[1].strip()),
    "meaning": _budget_matrix_cell_to_display_text(_budget_healthy_row[2].strip()).replace(
        _BUDGET_RATIO, f"{_LTR_ISOLATE_START}{_BUDGET_RATIO}{_LTR_ISOLATE_END}"
    ),
    "action": _budget_matrix_cell_to_display_text(_budget_healthy_row[3].strip()).replace(
        _BUDGET_N2000, f"{_LTR_ISOLATE_START}{_BUDGET_N2000}{_LTR_ISOLATE_END}"
    ),
    "caveat": _BUDGET_DEGRADED_LAYERS["caveat"],  # DESIGN.md's own "זהה למצב תקין" note on this row
}

# Falsification case 9's anchors for THIS screen: no ranking claim, no
# overvaluation ratio, no pilot recommendation may survive in the
# degraded D9 layers, jointly.
_LEAKED_RANKING_STRINGS = ("100×500", "25×2,000", "פיילוט", _BUDGET_RATIO)


def test_p11a_cp4_p6_mismatch_degrades_all_four_layers_no_ranking_or_pilot(mocked_page, mocked_context):
    """P11A-D6, falsification cases 7-9: model_versions.P6 mismatch
    degrades ALL FOUR D9 layers to the canonical DESIGN.md sec 6.1c
    wording -- "answer" (previously the HEALTHY text shown unguarded,
    D6's own finding) and "action" (previously still recommending a
    controlled pilot with no evidence backing it) are the two D6
    specifically flags; "meaning" and "caveat" verified alongside for
    completeness. The strategy table (case 9's own carve-out) is
    untouched."""
    route_json(mocked_context, "**/api/me", fx.api_me())
    route_json(mocked_context, "**/api/insights/budget-tiers", fx.budget_tiers_response())
    route_json(mocked_context, "**/business_facts.json", _facts("P6-DOES-NOT-MATCH-LIVE"))
    route_json(mocked_context, "**/api/simulate/budget", fx.budget_simulation(model_version="P6-linear-e2e"))
    sign_in_and_wait(mocked_page, mocked_context)

    mocked_page.click('a[data-route="budget"]')
    mocked_page.wait_for_selector(".strategy-table", timeout=10_000)
    assert len(mocked_page.query_selector_all(".strategy-row")) == 4  # untouched, case 9's own carve-out

    layers = _read_budget_d9_layers(mocked_page)
    _assert_well_formed_d9_layers(layers)
    rendered = {layer["key"]: layer["text"] for layer in layers}
    assert rendered == _BUDGET_DEGRADED_LAYERS

    combined_text = " ".join(rendered.values())
    for leaked in _LEAKED_RANKING_STRINGS:
        assert leaked not in combined_text, f"{leaked!r} leaked into a degraded D9 layer: {rendered!r}"


def test_p11a_cp4_p6_matching_shows_full_backtest_in_all_four_layers(mocked_page, mocked_context):
    """Falsification case 11's companion for this screen: a valid,
    model_version-matching fixture must return the full backtest-backed
    content in ALL FOUR D9 layers, not just the (already-covered)
    overlap-alert paragraph."""
    route_json(mocked_context, "**/api/me", fx.api_me())
    route_json(mocked_context, "**/api/insights/budget-tiers", fx.budget_tiers_response())
    route_json(mocked_context, "**/business_facts.json", _facts("P6-linear-e2e"))
    route_json(mocked_context, "**/api/simulate/budget", fx.budget_simulation(model_version="P6-linear-e2e"))
    sign_in_and_wait(mocked_page, mocked_context)

    mocked_page.click('a[data-route="budget"]')
    mocked_page.wait_for_selector(".strategy-table", timeout=10_000)

    layers = _read_budget_d9_layers(mocked_page)
    _assert_well_formed_d9_layers(layers)
    rendered = {layer["key"]: layer["text"] for layer in layers}
    assert rendered == _BUDGET_HEALTHY_LAYERS
    # Falsification case 9's negative check, in the OTHER direction --
    # the healthy state must not have accidentally kept the degraded
    # wording (a "cheap way to pass 1-10 is to always degrade" style bug
    # would also fail here, since degraded rows never mention the ratio).
    assert rendered["caveat"] == _BUDGET_DEGRADED_LAYERS["caveat"]
