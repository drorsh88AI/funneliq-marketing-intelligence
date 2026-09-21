"""PHASE11.md §י, cases 17, 18, 20 -- shared-form validation (closed vs
followup_5), the clear-form confirm/cancel flow, and business_facts.json
model_version-mismatch hiding only the dependent content.

Case 18 here covers the SHARED FORM only (predict.js) -- the P4S
(super-customer.js) side of "בשני המסכים" is left for a follow-up batch,
not silently skipped."""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import fixtures as fx
from conftest import route_deferred, route_json, sign_in_and_wait

REPO_ROOT = Path(__file__).resolve().parent.parent

# Loaded by file path under a private module name (NOT a plain `import
# test_design_tokens`) so it never collides with pytest's own collection
# of tests/test_design_tokens.py as the top-level module "test_design_tokens"
# when the two suites run in the same session -- only its two markdown-table
# helpers are used, to read docs/DESIGN.md's own degradation table directly
# rather than hand-copying its wording into a second, driftable literal.
_design_tokens_spec = importlib.util.spec_from_file_location(
    "_design_tokens_bridge", REPO_ROOT / "tests" / "test_design_tokens.py"
)
_design_tokens_bridge = importlib.util.module_from_spec(_design_tokens_spec)
_design_tokens_spec.loader.exec_module(_design_tokens_bridge)

PREDICT_VALUES = {
    "ad_budget": "5000", "num_leads": "100", "leads_answered": "80",
    "followup_1": "70", "followup_2": "60", "followup_3": "50",
    "followup_4": "40", "followup_5": "30", "closed": "10",
    "calls_to_closed": "3", "calls_to_not_closed": "2",
    "customer_acquisition_cost": "500",
}


def _open_predict(page):
    page.click('a[data-route="predict"]')
    page.wait_for_selector("#field-ad_budget")


def _fill(page, values):
    for field, value in values.items():
        page.fill(f"#field-{field}", value)


def test_case_17_closed_gt_followup5_blocks_no_clamp_no_silent_change(mocked_page, mocked_context):
    """17. closed > followup_5 ⇒ שגיאה חוסמת; אין חיתוך לאפס ואין שינוי שקט ב-closed."""
    route_json(mocked_context, "**/api/me", fx.api_me())
    route_json(mocked_context, "**/api/insights/budget-tiers", fx.budget_tiers_response())
    route_json(mocked_context, "**/rest/v1/funnel_records*", [])
    sign_in_and_wait(mocked_page, mocked_context)
    _open_predict(mocked_page)

    values = dict(PREDICT_VALUES)
    values["followup_5"] = "30"
    values["closed"] = "999"  # far more "closed" than remain after followup 5
    _fill(mocked_page, values)
    mocked_page.check(".context-confirmation input[type=checkbox]")

    assert mocked_page.is_disabled(".submit-button")
    blocked_text = mocked_page.text_content(".submit-blocked-wrap")
    assert "עסקאות שנסגרו אינן יכולות לעלות על הלידים שנותרו אחרי מעקב 5" in blocked_text

    # The derived value shows the REAL (negative) number -- not clamped
    # to zero -- and `closed` itself keeps the value the user typed.
    derived_text = mocked_page.text_content(".derived-field-value")
    assert "-969" in derived_text
    assert mocked_page.input_value("#field-closed") == "999"


def test_case_18_clear_form_cancel_is_a_no_op_confirm_bumps_generation_first(mocked_page, mocked_context):
    """18 (טופס משותף). נקה טופס → ביטול ⇒ אפס שינוי; → אישור ⇒ מונה
    הדור עולה לפני האיפוס (הבקשה הישנה שבאוויר נזרקת בשקט, לא מרונדרת)."""
    route_json(mocked_context, "**/api/me", fx.api_me())
    route_json(mocked_context, "**/api/insights/budget-tiers", fx.budget_tiers_response())
    route_json(mocked_context, "**/rest/v1/funnel_records*", [])
    sign_in_and_wait(mocked_page, mocked_context)
    _open_predict(mocked_page)
    _fill(mocked_page, PREDICT_VALUES)
    mocked_page.check(".context-confirmation input[type=checkbox]")

    # -- Cancel path: zero change. --
    mocked_page.click(".clear-form-action >> text=נקה טופס")
    mocked_page.wait_for_selector(".clear-form-confirm")
    mocked_page.click(".clear-form-confirm >> text=ביטול")
    assert mocked_page.query_selector(".clear-form-confirm") is None
    assert mocked_page.input_value("#field-ad_budget") == PREDICT_VALUES["ad_budget"]
    assert mocked_page.is_checked(".context-confirmation input[type=checkbox]")

    # -- Confirm path, with a submission in flight: the stale response
    # must never render, and the form resets to blank. --
    ltv_route = route_deferred(mocked_context, "**/api/predict/ltv")
    upsell_route = route_deferred(mocked_context, "**/api/predict/upsell")
    referral_route = route_deferred(mocked_context, "**/api/predict/referral")
    mocked_page.click(".submit-button")
    ltv_route.wait_for_capture(mocked_page)
    upsell_route.wait_for_capture(mocked_page)
    referral_route.wait_for_capture(mocked_page)

    mocked_page.click(".clear-form-action >> text=נקה טופס")
    mocked_page.wait_for_selector(".clear-form-confirm")
    mocked_page.click(".clear-form-confirm >> text=אישור")

    assert mocked_page.input_value("#field-ad_budget") == ""
    assert not mocked_page.is_checked(".context-confirmation input[type=checkbox]")

    ltv_route.release(payload=fx.ltv_prediction_success())
    upsell_route.release(payload=fx.propensity_prediction_success())
    referral_route.release(payload=fx.propensity_prediction_success())
    import time
    deadline = time.time() + 1.5
    while time.time() < deadline:
        assert mocked_page.query_selector(".prediction-panel-p2 .prediction-primary") is None
        mocked_page.wait_for_timeout(100)


# P11A-D4 / PHASE11A.md §ז falsification cases 7-9-11 -- shared fixture
# and DOM-reading helpers for the two model_versions.P2 states below.
# The two facts payloads differ ONLY in model_versions.P2; everything
# else (ltv.dominant_feature=calls_to_closed) is identical -- it is the
# match/mismatch against the live response's own model_version that
# flips leverage.getLtvLeverage() between returning the block and null,
# not the presence of the block itself.
def _p2_business_facts(p2_model_version):
    return {
        "budget_backtest": {"500": {"actual_mean_per_customer": 918.65, "n_holdout_at_level": 17, "n_train_at_level": 92, "predicted_per_customer": 7895.94}},
        "followup_context": {"mean_calls_closed_eq_1": 5.65, "mean_calls_closed_ge_2": 3.35, "population_definition": "closed>0"},
        "ltv": {"dominant_feature": "calls_to_closed", "rank_1_by_algorithm": {"catboost": {"feature": "calls_to_closed", "importance": 96.0}, "lightgbm": {"feature": "calls_to_closed", "importance": 90.0}, "xgboost": {"feature": "calls_to_closed", "importance": 88.0}}},
        "metrics_sha256": "8af98f45f595a830b26055be5eab053c85c43c6fc6d97732c45b34b9f3166723",
        "model_versions": {
            "P2": p2_model_version,
            "P3": "P3-xgboost-e2e", "P4": "P4-logistic-e2e",
            "P4S": "P4S-catboost-e2e", "P6": "P6-linear-e2e",
        },
        "schema_version": 1,
        "source_csv_sha256": "8ac67d50a6f96a8ece8abd770a5a1901b34036a5c98656455eb04cee07d707aa",
        "source_keys": {"budget_backtest": "x", "followup_context": "x", "ltv": "x", "super_customer_profile": "x"},
        "super_customer_profile": {"cac_population_mean": 1437.0, "cac_savings_pct": 0.31, "cac_super_mean": 990.0, "n_purchased": 3163, "n_super": 529, "pct_of_purchased": 0.16, "pct_of_total_profit": 0.33, "population_definition": "x"},
    }


# Falsification case 7: "בדיוק ארבע שכבות, ארבע התוויות, אף ערך אינו
# ריק" -- read structurally (key/label/text per DOM element), not just
# grepped as flat text, so a missing/duplicated/empty layer is caught
# regardless of which one it is.
def _read_p2_d9_layers(page):
    return page.eval_on_selector_all(
        ".prediction-panel-p2 .summary-recommendation .summary-layer",
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


# summary-recommendation.js's own LAYER_LABELS, in DOM order -- checked
# verbatim, not just "is non-empty", so a mislabeled or reordered layer
# (e.g. "action" rendered under the "caveat" label) is caught too.
_D9_EXPECTED_KEYS = ["answer", "meaning", "action", "caveat"]
_D9_EXPECTED_LABELS = ["תשובה", "מה זה אומר", "מה כדאי לעשות", "חשוב לדעת"]


def _assert_well_formed_d9_layers(layers):
    """Falsification case 7 in full: exactly the four layers, in order,
    each under its correct UI label (not just present-and-non-empty),
    and no layer's text is empty."""
    assert [layer["key"] for layer in layers] == _D9_EXPECTED_KEYS
    assert [layer["label"] for layer in layers] == _D9_EXPECTED_LABELS
    for layer in layers:
        assert layer["text"], f"layer {layer['key']!r} has empty text"


# `fx.ltv_prediction_success()`'s own defaults (point=24.0, lower=18.0,
# upper=30.0) -- both tests below use them unmodified, so the rendered
# `answer` layer is pinned to one literal string, not just checked for
# a substring.
_P2_ROUNDED, _P2_LOWER, _P2_UPPER = 24, 18, 30

# Falsification case 8, bridged to its actual source: the degraded P2
# wording is EXTRACTED from docs/DESIGN.md's own §6.1ג table (the same
# `_extract_markdown_table` + `_DEGRADATION_TABLE_HEADER_ROW` checkpoint
# 1's own test 10 uses), not hand-copied from predict.js a second time.
# A future edit that changes predict.js's degraded wording without
# updating DESIGN.md (or vice versa) fails HERE, not just an "is the
# code internally consistent with itself" check.
_P2_ROW_LABEL_TO_D9_KEY = {
    "תשובה פשוטה": "answer",
    "משמעות עסקית": "meaning",
    "פעולה מומלצת": "action",
    "מגבלה": "caveat",
}
_design_md_text = (REPO_ROOT / "docs" / "DESIGN.md").read_text(encoding="utf-8")
_degradation_rows = _design_tokens_bridge._extract_markdown_table(
    _design_md_text, _design_tokens_bridge._DEGRADATION_TABLE_HEADER_ROW
)
_P2_DEGRADED_LAYERS = {}
for _target_cell, _layer_cell, _wording_cell, _source_cell in _degradation_rows:
    if _target_cell.strip("*") != "P2":
        continue
    _P2_DEGRADED_LAYERS[_P2_ROW_LABEL_TO_D9_KEY[_layer_cell.strip()]] = _wording_cell.strip()
assert set(_P2_DEGRADED_LAYERS) == set(_D9_EXPECTED_KEYS), (
    f"docs/DESIGN.md sec 6.1c: expected exactly the 4 P2 rows "
    f"{sorted(_P2_ROW_LABEL_TO_D9_KEY)}, got {sorted(_P2_DEGRADED_LAYERS)} -- "
    f"table structure changed, update this bridge"
)
# Only the "answer" row carries placeholders (the closed vocabulary from
# test_design_tokens.py's own test 10) -- substituted with this file's
# own fixture values, the same live numbers predict.js's
# format.formatNumber() renders for point=24.0/lower=18.0/upper=30.0.
_P2_DEGRADED_LAYERS["answer"] = (
    _P2_DEGRADED_LAYERS["answer"]
    .replace("{ltv_months}", str(_P2_ROUNDED))
    .replace("{ltv_lower}", str(_P2_LOWER))
    .replace("{ltv_upper}", str(_P2_UPPER))
)

# The live (non-degraded) wording -- bridged to its own canonical
# source the same way as the degraded table above: EXTRACTED from
# docs/DESIGN.md §6.1's own D9 six-column matrix (checkpoint 6's
# deliverable -- test_design_tokens.py's own test 9 validates this same
# table), not hand-copied from predict.js a second time. Used by case
# 20b as the literal match for falsification case 11's "התוכן הקנוני
# התלוי בנכס חוזר במלואו".
_p2_matrix_pattern = dict(_design_tokens_bridge._D9_TARGET_PATTERNS)["P2"]
_healthy_matrix_rows = _design_tokens_bridge._extract_markdown_table(
    _design_md_text, _design_tokens_bridge._D9_MATRIX_HEADER_ROW
)
_p2_healthy_rows = [row for row in _healthy_matrix_rows if _p2_matrix_pattern.search(row[0])]
assert len(_p2_healthy_rows) == 1, (
    f"docs/DESIGN.md sec 6.1: expected exactly 1 P2 row in the D9 six-column "
    f"matrix, found {len(_p2_healthy_rows)} -- table structure changed, "
    f"update this bridge"
)
_p2_healthy_row = _p2_healthy_rows[0]
# Row layout (test_design_tokens.py's own _D9_COLUMNS): question/target,
# answer, meaning, action, caveat, evidence-source (ignored here).
_P2_HEALTHY_LAYERS = {
    "answer": _p2_healthy_row[1].strip(),
    "meaning": _p2_healthy_row[2].strip(),
    "action": _p2_healthy_row[3].strip(),
    "caveat": _p2_healthy_row[4].strip(),
}
# Only "answer" carries placeholders here -- the success matrix's OWN
# vocabulary (PHASE11A.md: "{X} הוא חודשים ב-P2, אחוז ב-P3..."), a
# DIFFERENT closed vocabulary from the degraded table's {ltv_months}
# etc. above, deliberately not shared (PHASE11A.md D3: "אין לרשת את
# מוסכמת ה-placeholders של מטריצת ההצלחה").
_P2_HEALTHY_LAYERS["answer"] = (
    _P2_HEALTHY_LAYERS["answer"]
    .replace("{X}", str(_P2_ROUNDED))
    .replace("{Y}", str(_P2_LOWER))
    .replace("{Z}", str(_P2_UPPER))
)
# Cross-check against the OTHER extracted table directly -- not via a
# third, hand-maintained constant that both would independently be
# compared to (that would let the two tables drift from EACH OTHER
# while each still matched the stale constant). DESIGN.md's own "זהה
# למצב תקין" note on both rows means these two live-extracted values
# must be equal to each other, not just individually well-formed.
assert _P2_HEALTHY_LAYERS["answer"] == _P2_DEGRADED_LAYERS["answer"], (
    f"docs/DESIGN.md sec 6.1's P2 answer row (with {{X}}/{{Y}}/{{Z}} "
    f"substituted) no longer matches sec 6.1c's degraded P2 answer row "
    f"(with {{ltv_months}}/{{ltv_lower}}/{{ltv_upper}} substituted): "
    f"{_P2_HEALTHY_LAYERS['answer']!r} != {_P2_DEGRADED_LAYERS['answer']!r}"
)
assert _P2_HEALTHY_LAYERS["caveat"] == _P2_DEGRADED_LAYERS["caveat"], (
    f"docs/DESIGN.md sec 6.1's own P2 caveat row no longer matches sec "
    f"6.1c's degraded table -- both must stay identical (DESIGN.md's own "
    f"'זהה למצב תקין' note on that row): "
    f"{_P2_HEALTHY_LAYERS['caveat']!r} != {_P2_DEGRADED_LAYERS['caveat']!r}"
)

# B29c's two halves, in full -- the lever tip (`FIELD_META.calls_to_closed
# .label` + the raw field name, `format.ltr`-wrapped with the actual
# U+2066/U+2069 isolate characters, not a stand-in) and the call-policy
# sentence already captured whole inside `_P2_HEALTHY_LAYERS["action"]`.
_LTR_ISOLATE_START, _LTR_ISOLATE_END = chr(0x2066), chr(0x2069)
_P2_LEVERAGE_TIP = (
    "לפי שלושת המודלים שנבחנו, הפיצ'ר המשפיע ביותר על אורך חיי הלקוח הוא "
    f"ממוצע שיחות עד סגירה ({_LTR_ISOLATE_START}calls_to_closed{_LTR_ISOLATE_END})."
)

# Falsification case 9: these three anchors (the raw field name, its
# Hebrew label, and the call-policy phrase) must be absent from ALL
# FOUR D9 layers jointly in the degraded state -- not just grepped out
# of "meaning"/"action" individually, since a future refactor could
# just as easily move the leak into "answer" or "caveat".
_LEAKED_LEVERAGE_STRINGS = ("calls_to_closed", "ממוצע שיחות עד סגירה", "מדיניות השיחות")


def test_case_20_p2_model_version_mismatch_degrades_leverage_tip_and_d9_layers(mocked_page, mocked_context):
    """20. model_versions.P2 אינו תואם ⇒ תמצית המנוף מוסתרת, ושכבות
    "מה זה אומר"/"מה כדאי לעשות" עוברות לנוסח מושפל קנוני (P11A-D4);
    תוצאת P2 וכל שאר המסכים נשארים פעילים. מקרי הפרכה 7-9."""
    route_json(mocked_context, "**/api/me", fx.api_me())
    route_json(mocked_context, "**/api/insights/budget-tiers", fx.budget_tiers_response())
    route_json(mocked_context, "**/rest/v1/funnel_records*", [])
    # app.js's own bootstrap calls facts.init() immediately after
    # router.start() -- right when #authenticated-shell mounts, NOT
    # lazily at predict's own submit time. The mock MUST be registered
    # before sign_in_and_wait() returns, or that first, real fetch
    # (against app/static/business_facts.json's actual on-disk content)
    # latches into facts.js's one-shot `loadAttempted` forever, and this
    # test would silently degrade for the wrong reason regardless of
    # model_versions.P2 below -- caught by running this against the
    # real app, not from reading the diff.
    route_json(mocked_context, "**/business_facts.json", _p2_business_facts("P2-DOES-NOT-MATCH-LIVE"))
    sign_in_and_wait(mocked_page, mocked_context)

    route_json(mocked_context, "**/api/predict/ltv", fx.ltv_prediction_success(model_version="P2-catboost-e2e"))
    route_json(mocked_context, "**/api/predict/upsell", fx.propensity_prediction_success())
    route_json(mocked_context, "**/api/predict/referral", fx.propensity_prediction_success())
    _open_predict(mocked_page)
    _fill(mocked_page, PREDICT_VALUES)
    mocked_page.check(".context-confirmation input[type=checkbox]")
    mocked_page.click(".submit-button")

    mocked_page.wait_for_selector(".prediction-panel-p2 .prediction-primary", timeout=10_000)
    # The result itself renders normally -- only the leverage-dependent
    # content (the tip, and the two D9 layers below) is gone/degraded.
    assert mocked_page.query_selector(".prediction-panel-p2 .ltv-leverage-tip") is None
    assert mocked_page.query_selector(".prediction-panel-p3 .prediction-primary") is not None
    assert mocked_page.query_selector(".prediction-panel-p4 .prediction-primary") is not None

    # Case 7: exactly the four layers, correct keys AND correct labels,
    # in order, nothing empty.
    layers = _read_p2_d9_layers(mocked_page)
    _assert_well_formed_d9_layers(layers)

    # Case 8: literal match to DESIGN.md §6.1ג's degraded P2 rows, not `in`.
    rendered = {layer["key"]: layer["text"] for layer in layers}
    assert rendered == _P2_DEGRADED_LAYERS

    # Case 9: none of the three leverage-only anchors survive in ANY of
    # the four layers jointly (scoped to `.summary-recommendation` only --
    # not the whole DOM, so budget.js's legitimate `rank` column in a
    # DIFFERENT screen is never in scope here regardless).
    combined_text = " ".join(rendered.values())
    for leaked in _LEAKED_LEVERAGE_STRINGS:
        assert leaked not in combined_text, f"{leaked!r} leaked into a degraded D9 layer: {rendered!r}"


def test_case_20b_p2_matching_model_version_shows_both_halves_of_b29c(mocked_page, mocked_context):
    """B29c ("what's the strongest lever on customer longevity, and what
    should Northbound do about it?") has two halves -- the lever (the
    leverage tip) and the recommendation derived from it (the call-policy
    sentence inside the D9 "action" layer). Falsification case 11: a
    valid, model_version-matching fixture must return the canonical,
    asset-dependent content IN FULL, not just a fragment of it -- the
    cheap way to pass cases 1-10 is to always degrade, and this is the
    test that would catch exactly that."""
    route_json(mocked_context, "**/api/me", fx.api_me())
    route_json(mocked_context, "**/api/insights/budget-tiers", fx.budget_tiers_response())
    route_json(mocked_context, "**/rest/v1/funnel_records*", [])
    # See test_case_20's own comment: this MUST be registered before
    # sign_in_and_wait() -- app.js's bootstrap calls facts.init() right
    # when the shell mounts, well before predict.js is ever opened.
    # Matches fx.ltv_prediction_success()'s own default model_version.
    route_json(mocked_context, "**/business_facts.json", _p2_business_facts("P2-catboost-e2e"))
    sign_in_and_wait(mocked_page, mocked_context)

    route_json(mocked_context, "**/api/predict/ltv", fx.ltv_prediction_success())
    route_json(mocked_context, "**/api/predict/upsell", fx.propensity_prediction_success())
    route_json(mocked_context, "**/api/predict/referral", fx.propensity_prediction_success())
    _open_predict(mocked_page)
    _fill(mocked_page, PREDICT_VALUES)
    mocked_page.check(".context-confirmation input[type=checkbox]")
    mocked_page.click(".submit-button")

    mocked_page.wait_for_selector(".prediction-panel-p2 .prediction-primary", timeout=10_000)

    # Half 1 of B29c: the lever, verified in full (not `in`).
    tip_text = mocked_page.text_content(".prediction-panel-p2 .ltv-leverage-tip")
    assert tip_text == _P2_LEVERAGE_TIP

    # Half 2 of B29c, plus the rest of the four-layer invariant: the
    # call-policy action sentence, and the other three layers, all
    # verified as full literal matches to the live wording, under their
    # correct keys AND labels.
    layers = _read_p2_d9_layers(mocked_page)
    _assert_well_formed_d9_layers(layers)
    rendered = {layer["key"]: layer["text"] for layer in layers}
    assert rendered == _P2_HEALTHY_LAYERS
