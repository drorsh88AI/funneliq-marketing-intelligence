"""PHASE12A.md sec-vav-7 -- the desktop four-width acceptance matrix
(1920/1366/1280/1024), required once at CP8, before commit. Reuses the
same zero-external-network harness as capture_state_matrix.py (real
uvicorn, real Chromium, route()-level mocking) and follows its own
kept-not-deleted convention: this file documents ITS OWN evidence the
same way that file documents the screen x state matrix, so a later
reader (or a future width-matrix re-check) has the exact reproduction
steps, not just a one-time claim in PHASE12A.md's own checkpoint table.

⚠ NOT a falsification-case test file, same reasoning as
capture_state_matrix.py's own header: run explicitly --
    python -m pytest e2e/capture_width_matrix.py -s -v

CP8 round-2 (Codex finding, relayed by the user, 2026-09-29): the first
CP8 pass verified layout via live bounding-box measurements in a
throwaway script it then DELETED, and verified D9 layer "visibility" by
reading summary-recommendation.js's/style.css's source rather than
checking the actual rendered page -- exactly the anti-pattern this
project's own e2e harness otherwise avoids everywhere else (per
test_13_desktop_layout.py's own header: "a CSS-only regression would
NOT be caught by any selector-presence assertion, only by actually
measuring position"). Also, sec-vav-7 explicitly requires "צילום בכל
אחד" (a screenshot at each width) as part of the acceptance criterion,
which the deleted script never produced. This file fixes both: it is
kept (not deleted), and it asserts real getComputedStyle/offsetParent/
bounding-rect visibility on the "answer"/"action" D9 layers (not
textContent presence, which a hidden or collapsed element would still
have) alongside the four saved screenshots per screen.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import fixtures as fx
from conftest import route_json, sign_in_and_wait

WIDTH_MATRIX_DIR = Path(__file__).resolve().parent.parent / "docs" / "design" / "states" / "width-matrix"
WIDTH_MATRIX_DIR.mkdir(parents=True, exist_ok=True)

WIDTHS = [1920, 1366, 1280, 1024]


def shoot(page, name: str) -> None:
    page.screenshot(path=str(WIDTH_MATRIX_DIR / f"{name}.jpg"), type="jpeg", quality=90, full_page=True)


def _assert_layer_actually_visible(page, scope_selector: str, layer_key: str, context: str) -> None:
    """Real rendered-DOM visibility, per sec-tet-5 point 2 ("גלויים,
    ⛔ לא textContent") -- getComputedStyle + offsetParent + a non-zero
    bounding rect, not just that the node exists with non-empty text
    (which a `display:none` or collapsed-and-closed <details> ancestor
    would still satisfy)."""
    result = page.eval_on_selector(
        f"{scope_selector} .summary-layer-{layer_key}",
        """(el) => {
            const cs = getComputedStyle(el);
            const rect = el.getBoundingClientRect();
            return {
                display: cs.display,
                visibility: cs.visibility,
                hasOffsetParent: el.offsetParent !== null,
                width: rect.width,
                height: rect.height,
            };
        }""",
    )
    assert result is not None, f"{context}: .summary-layer-{layer_key} not found at all"
    assert result["display"] != "none", f"{context}: {layer_key} has display:none -- {result}"
    assert result["visibility"] != "hidden", f"{context}: {layer_key} has visibility:hidden -- {result}"
    assert result["hasOffsetParent"], f"{context}: {layer_key} has no offsetParent (itself or an ancestor is not rendered) -- {result}"
    assert result["width"] > 0 and result["height"] > 0, f"{context}: {layer_key} has a zero-size box -- {result}"


_BUSINESS_FACTS = {
    "budget_backtest": {
        "2000": {"actual_mean_per_customer": 20650.88, "n_holdout_at_level": 85, "n_train_at_level": 322, "predicted_per_customer": 21238.12},
        "500": {"actual_mean_per_customer": 918.65, "n_holdout_at_level": 17, "n_train_at_level": 92, "predicted_per_customer": 7895.94},
    },
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
    "super_customer_profile": {"cac_population_mean": 1437.0, "cac_savings_pct": 0.31, "cac_super_mean": 990.0, "n_purchased": 3163, "n_super": 529, "pct_of_purchased": 0.16, "pct_of_total_profit": 0.33, "population_definition": "x"},
}


def _check_width(mocked_page, mocked_context, width: int) -> None:
    mocked_page.set_viewport_size({"width": width, "height": 900})
    route_json(mocked_context, "**/api/me", fx.api_me())
    route_json(mocked_context, "**/api/insights/budget-tiers", fx.budget_tiers_response())
    # test_06_budget_screen.py's own `_facts("P6-linear-e2e")` -- matches
    # fx.budget_simulation()'s default model_version, so the screenshots
    # show the HEALTHY backtest-backed state, not a version-mismatch
    # degradation (a missed route here silently fell back to whatever
    # model_version the real on-disk business_facts.json happens to
    # carry, which is what round 1's un-mocked capture actually showed).
    route_json(mocked_context, "**/business_facts.json", _BUSINESS_FACTS)
    route_json(mocked_context, "**/api/simulate/budget", fx.budget_simulation())
    route_json(
        mocked_context, "**/api/insights/followup",
        fx.followup_response(stages=fx.followup_stages_available(), calls=fx.followup_calls_available()),
    )
    sign_in_and_wait(mocked_page, mocked_context)

    # --- Overview: 5 cards one row, equal height, real visibility on
    # its own D9 block, screenshot. ---
    mocked_page.wait_for_selector("#screen-overview .capability-index", timeout=10_000)
    tops = mocked_page.eval_on_selector_all("#screen-overview .capability-card", "(els) => els.map(e => e.getBoundingClientRect().top)")
    heights = mocked_page.eval_on_selector_all("#screen-overview .capability-card", "(els) => els.map(e => e.getBoundingClientRect().height)")
    assert len(tops) == 5, f"[{width}px] overview: expected 5 cards, got {len(tops)}"
    assert max(tops) - min(tops) < 2, f"[{width}px] overview: cards not on one row: {tops}"
    assert max(heights) - min(heights) < 2, f"[{width}px] overview: unequal heights: {heights}"
    overflow = mocked_page.evaluate("document.documentElement.scrollWidth > document.documentElement.clientWidth + 1")
    assert not overflow, f"[{width}px] overview: horizontal page scroll"
    _assert_layer_actually_visible(mocked_page, "#screen-overview", "answer", f"[{width}px] overview")
    _assert_layer_actually_visible(mocked_page, "#screen-overview", "action", f"[{width}px] overview")
    shoot(mocked_page, f"overview-{width}")

    # --- Budget: table + chart one row, D9 visibility, screenshot. ---
    mocked_page.click('a[data-route="budget"]')
    mocked_page.wait_for_selector("#screen-budget .strategy-table", timeout=10_000)
    table_top = mocked_page.eval_on_selector("#screen-budget .strategy-table-wrap", "(el) => el.getBoundingClientRect().top")
    chart_top = mocked_page.eval_on_selector("#screen-budget .chart-live", "(el) => el.getBoundingClientRect().top")
    assert abs(table_top - chart_top) < 2, f"[{width}px] budget: table/chart not one row (table={table_top}, chart={chart_top})"
    overflow = mocked_page.evaluate("document.documentElement.scrollWidth > document.documentElement.clientWidth + 1")
    assert not overflow, f"[{width}px] budget: horizontal page scroll"
    _assert_layer_actually_visible(mocked_page, "#screen-budget", "answer", f"[{width}px] budget")
    _assert_layer_actually_visible(mocked_page, "#screen-budget", "action", f"[{width}px] budget")
    shoot(mocked_page, f"budget-{width}")

    # --- Follow-up: two groups side by side, D9 visibility (all three
    # blocks -- K1/U3 in the two groups, U4 in the combined block),
    # screenshot. ---
    mocked_page.click('a[data-route="followup"]')
    mocked_page.wait_for_selector(".followup-layout", timeout=10_000)
    group_tops = mocked_page.eval_on_selector_all(".followup-group", "(els) => els.map(e => e.getBoundingClientRect().top)")
    assert len(group_tops) == 2, f"[{width}px] followup: expected 2 groups, got {len(group_tops)}"
    assert abs(group_tops[0] - group_tops[1]) < 2, f"[{width}px] followup: groups not side by side: {group_tops}"
    overflow = mocked_page.evaluate("document.documentElement.scrollWidth > document.documentElement.clientWidth + 1")
    assert not overflow, f"[{width}px] followup: horizontal page scroll"
    _assert_layer_actually_visible(mocked_page, ".followup-group:nth-child(1)", "answer", f"[{width}px] followup stages")
    _assert_layer_actually_visible(mocked_page, ".followup-group:nth-child(2)", "action", f"[{width}px] followup calls")
    _assert_layer_actually_visible(mocked_page, ".followup-recommendation", "answer", f"[{width}px] followup combined")
    shoot(mocked_page, f"followup-{width}")

    print(f"[{width}px]: OK (layout + real visibility + screenshots saved)")


def test_width_matrix_1920(mocked_page, mocked_context):
    _check_width(mocked_page, mocked_context, 1920)


def test_width_matrix_1366(mocked_page, mocked_context):
    _check_width(mocked_page, mocked_context, 1366)


def test_width_matrix_1280(mocked_page, mocked_context):
    _check_width(mocked_page, mocked_context, 1280)


def test_width_matrix_1024(mocked_page, mocked_context):
    _check_width(mocked_page, mocked_context, 1024)
