"""PHASE11.md §י, cases 21 and 24 -- Budget Simulator screen:
business_facts.json P6 model_version mismatch hides only the
backtest-backed recommendation (never the strategy table), and a live
top_two_overlap=true blocks any winning-strategy declaration."""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import fixtures as fx
from conftest import route_json, sign_in_and_wait


def _facts(p6_model_version: str) -> dict:
    return {
        "budget_backtest": {
            "2000": {"actual_mean_per_customer": 20650.88, "n_holdout_at_level": 85, "n_train_at_level": 322, "predicted_per_customer": 21238.12},
            "500": {"actual_mean_per_customer": 918.65, "n_holdout_at_level": 17, "n_train_at_level": 92, "predicted_per_customer": 7895.94},
        },
        "followup_context": {"mean_calls_closed_eq_1": 5.65, "mean_calls_closed_ge_2": 3.35, "population_definition": "closed>0"},
        "ltv": {"dominant_feature": "calls_to_closed", "rank_1_by_algorithm": {"catboost": {"feature": "calls_to_closed", "importance": 96.0}}},
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
