"use strict";

// FunnelIQ Budget Simulator screen (phase 11, checkpoint 7, IA.md §6).
// Own controller and local state (P11-D3). No user input at all -- a
// single GET, always the same four fixed strategies (in_training_domain
// is a locked `true`, IA.md §6.1: "מצב ה-OOD אינו נגיש במסך הזה").
//
// Content sources, all locked (§ד "כלל תיקון מקור"):
//   - hierarchy (overlap message -> veto+pilot -> strategy table ->
//     chart -> details) and the overlap/veto rules themselves: IA.md
//     §6, verbatim.
//   - the visible-even-when-details-closed disclaimer (cumulative
//     profit, additivity, "not next month's profit"): IA.md §6,
//     verbatim.
//   - the D9 summary-recommendation: DESIGN.md §6.1's own Budget
//     Simulator row, verbatim -- this row carries NO {X}/{Y}
//     placeholders (unlike P2/P3/P4/P4S's own rows), because it
//     describes the CURRENT, frozen-model state as fixed prose, not a
//     live-response template. The "meaning" and "action" layers'
//     "פי 8.59" / "322 שורות" figures come from business_facts.json
//     (budget_backtest) -- degraded gracefully (P11-D15) if that asset
//     fails to load or model_versions.P6 does not match, same pattern
//     as super-customer.js's own D9 "meaning" fallback. The overlap-
//     alert's OWN separate "וטו + פיילוט" paragraph is gated even more
//     strictly (hidden outright, not degraded) -- IA.md §6 / DESIGN.md's
//     P11-D15-extended note are explicit that a backtest failure hides
//     "המלצת התקציב והמספר 8.59" together and forbids substituting a
//     rank-only recommendation in its place.
//   - model-details rows: DESIGN.md §5.4/§6 (RegressionMetrics + the
//     locked interval_method/bootstrap fields).

import * as api from "../api.js";
import * as session from "../session.js";
import * as generation from "../generation.js";
import * as status from "../status.js";
import * as charts from "../charts.js";
import * as format from "../format.js";
import * as facts from "../facts.js";
import { renderSummaryRecommendation } from "../summary-recommendation.js";

const EVIDENCE_LABELS = { high: "ראיות גבוהות", medium: "ראיות בינוניות", low: "ראיות נמוכות" };

const gen = generation.createGenerationCounter();

let container = null;
let screenState = "idle"; // idle | loading | loaded | error

session.onSessionEvent(({ epochRaised, stateCleared }) => {
  if (stateCleared) {
    gen.bump();
    screenState = "idle";
    if (container) container.replaceChildren();
    return;
  }
  if (epochRaised && screenState === "loading") {
    gen.bump();
    screenState = "idle";
  }
});

function el(tag, props = {}, children = []) {
  const node = document.createElement(tag);
  for (const [key, value] of Object.entries(props)) {
    if (key === "className") node.className = value;
    else if (key === "text") node.textContent = value;
    else if (key.startsWith("on")) node.addEventListener(key.slice(2).toLowerCase(), value);
    else node.setAttribute(key, value);
  }
  for (const child of children) if (child) node.appendChild(child);
  return node;
}

/** "25×₪2,000" style composition strings, built from the LIVE
 * allocations array -- never a hardcoded strategy_id -> label table,
 * so a future contract value is described correctly rather than
 * silently mismatched. */
function compositionText(allocations) {
  return allocations
    .map((a) => `${format.ltr(format.formatNumber(a.count))}×${format.formatCurrency(a.ad_budget)}`)
    .join(" + ");
}

/** The veto+pilot recommendation's quantitative backing (8.59, 322 rows)
 * is business_facts.json's own budget_backtest -- IA.md §6 + DESIGN.md's
 * P11-D15-extended note are explicit that a load failure or
 * model_versions.P6 mismatch hides "המלצת התקציב והמספר 8.59" TOGETHER,
 * "אין להחליפם בהמלצה לפי rank בלבד" (must not substitute a rank-only
 * recommendation). So unlike super-customer.js's/this screen's own D9
 * "meaning" layer (which degrades to a NUMBER-FREE sentence), this
 * specific recommendation is hidden OUTRIGHT when the asset is
 * unavailable -- only the always-present overlap sentence and the
 * general (non-backtest) disclaimer remain. IA.md's own blockquote
 * (§6, "תיקון CP9") is the verbatim source for the available-data text. */
function buildOverlapAlert(sim) {
  const backtest = facts.getBudgetBacktest(sim.model_version);
  const wrap = el("div", { className: "overlap-alert", role: "alert" });

  // Live-driven (top_two_overlap), independent of business_facts.
  if (sim.top_two_overlap) {
    wrap.appendChild(el("p", { text: "ההבדל בין שתי האסטרטגיות המובילות אינו חד-משמעי; אין הכרזה על אסטרטגיה מנצחת." }));
  } else {
    // This module's own composition (see header comment) -- IA.md only
    // permits, not locks, a specific sentence for this branch, which
    // the project's frozen dataset never actually reaches
    // (top_two_overlap is currently true).
    const rank1 = sim.strategies.find((s) => s.rank === 1);
    wrap.appendChild(el("p", { text: `האסטרטגיה המדורגת ראשונה (${compositionText(rank1.allocations)}) מועדפת לפי המודל -- ⛔ אין בכך הבטחת רווח.` }));
  }

  if (backtest && backtest["500"] && backtest["2000"]) {
    const rawRatio = backtest["500"].predicted_per_customer / backtest["500"].actual_mean_per_customer;
    const ratio = format.formatNumber(Math.floor(rawRatio * 100) / 100, { decimals: 2 }); // floor, not round -- see buildD9's own comment
    const n2000 = format.formatNumber(backtest["2000"].n_train_at_level);
    wrap.appendChild(el("p", {
      text: `100×500 מדורגת ראשונה מספרית, אך אינה המלצה: הטווח שלה חופף ל-25×2,000, ובבדיקת עבר רמת 500 הוערכה פי ${format.ltr(ratio)} מהתוצאה בפועל (${format.ltr(n2000)} שורות אימון ב-25×2,000). אין לבצע לפיה הקצאה מלאה; אם בוחנים חלופה, ההמלצה היא פיילוט מבוקר של 25×2,000.`,
    }));
  }
  // Asset unavailable/mismatched: no substitute rank-based
  // recommendation is shown here (explicitly forbidden) -- the always-
  // present disclaimer paragraph (rendered by the caller, right after
  // this component) and the strategy table are all that remain.
  return wrap;
}

function buildStrategyTable(strategies) {
  const wrap = el("div", { className: "strategy-table-wrap" });
  const table = el("table", { className: "strategy-table" });
  const thead = el("thead", {});
  const headRow = el("tr", {});
  for (const heading of ["דירוג", "הרכב", "רווח צפוי", "טווח (2.5%–97.5%)", "ראיות"]) {
    headRow.appendChild(el("th", { text: heading }));
  }
  thead.appendChild(headRow);
  table.appendChild(thead);

  const tbody = el("tbody", {});
  for (const s of strategies) {
    const row = el("tr", { className: "strategy-row" });
    row.appendChild(el("th", { scope: "row", text: format.ltr(String(s.rank)) }));
    row.appendChild(el("td", { text: compositionText(s.allocations) }));
    row.appendChild(el("td", { className: "prediction-primary-cell", text: format.formatCurrency(s.point_estimate) }));
    row.appendChild(el("td", { text: `${format.formatCurrency(s.lower_bound)}–${format.formatCurrency(s.upper_bound)}` }));
    row.appendChild(el("td", {}, [
      el("span", { className: `evidence-badge evidence-${s.evidence_level}`, text: EVIDENCE_LABELS[s.evidence_level] }),
    ]));
    tbody.appendChild(row);
  }
  table.appendChild(tbody);
  wrap.appendChild(table);
  return wrap;
}

function buildChart(strategies) {
  const chartRows = strategies.map((s) => ({
    xHebrew: compositionText(s.allocations),
    xEnglish: s.strategy_id,
    value: s.point_estimate,
    lower: s.lower_bound,
    upper: s.upper_bound,
  }));
  return charts.renderBarChart({
    data: chartRows,
    xLabel: "אסטרטגיה",
    yLabel: "רווח צפוי",
    formatValue: (v, d) => `${format.formatCurrency(v)} (טווח: ${format.formatCurrency(d.lower)}–${format.formatCurrency(d.upper)})`,
    barClassName: "chart-bar-uncertain", // D10: a prediction, never --color-primary
    legend: "הקו האנכי מעל כל עמודה מציג את טווח אי-הוודאות (95% Bootstrap, אחוזון 2.5–97.5) סביב הרווח הצפוי.",
  });
}

function buildModelDetails(sim) {
  const rows = [
    ["גרסת מודל", format.ltr(sim.model_version)],
    ["אלגוריתם", format.ltr(sim.model_algorithm)],
    ["שיטת אינטרוול", format.ltr(sim.interval_method)],
    ["אחוזונים", format.ltr(`${sim.bootstrap_percentiles[0]}–${sim.bootstrap_percentiles[1]}`)],
    ["איטרציות Bootstrap", format.ltr(format.formatNumber(sim.strategies[0].bootstrap_iterations))],
    ["MAE (CV)", format.formatNumber(sim.metrics.cv.mean_mae, { decimals: 2 })],
    ["RMSE (CV)", format.formatNumber(sim.metrics.cv.mean_rmse, { decimals: 2 })],
    ["R² (CV)", format.formatNumber(sim.metrics.cv.mean_r2, { decimals: 3 })],
    ["MAE (Holdout)", format.formatNumber(sim.metrics.holdout.mae, { decimals: 2 })],
    ["RMSE (Holdout)", format.formatNumber(sim.metrics.holdout.rmse, { decimals: 2 })],
    ["R² (Holdout)", format.formatNumber(sim.metrics.holdout.r2, { decimals: 3 })],
  ];
  const details = el("details", { className: "model-details" });
  details.appendChild(el("summary", { text: "פרטי המודל" }));
  const dl = el("dl", {});
  for (const [label, value] of rows) {
    dl.appendChild(el("dt", { text: label }));
    dl.appendChild(el("dd", { text: value }));
  }
  details.appendChild(dl);
  details.appendChild(el("p", {
    className: "model-details-note",
    text: "המודל הנפרס הוא Linear Regression; אין extrapolation מחוץ לטווח 500–20,000.",
  }));
  return details;
}

/** DESIGN.md §6.1's own Budget Simulator row -- fixed prose, no
 * placeholders. Only the "meaning" layer's specific figures (8.59,
 * 322) depend on business_facts.json; degrades gracefully (P11-D15,
 * same pattern as super-customer.js's own D9 "meaning" fallback) if
 * that asset failed to load or model_versions.P6 does not match this
 * response's own model_version. */
function buildD9(sim) {
  const backtest = facts.getBudgetBacktest(sim.model_version);
  let meaning;
  let action;
  if (backtest && backtest["500"] && backtest["2000"]) {
    const b500 = backtest["500"];
    // Found while implementing: standard rounding of this live ratio
    // gives 8.60 (verified: 7895.935916363534 / 918.6470588235294 =
    // 8.595179... -> rounds to 8.60 under both Intl.NumberFormat and
    // Python's own round()), but SPEC.md/IA.md/DESIGN.md all
    // independently cite "8.59" for this exact figure -- three
    // separate locked sources agree with each other but not with
    // standard rounding. Math.floor (truncation) reproduces "8.59"
    // exactly, so that -- not this module's usual round-to-decimals --
    // is used here, deliberately, to match the locked documented value
    // rather than silently drifting from it.
    const rawRatio = b500.predicted_per_customer / b500.actual_mean_per_customer;
    const ratio = format.formatNumber(Math.floor(rawRatio * 100) / 100, { decimals: 2 });
    // "×" used here and in the fixed layers below, in place of DESIGN.md's
    // own code-formatted "100x500"/"25x2000" tokens -- for visual
    // consistency with compositionText()'s own "×" formatting elsewhere
    // on this screen (strategy-table, chart). No wording otherwise
    // deviates from the locked cells (DESIGN.md §6.1's own Budget
    // Simulator row), including their own lack of trailing punctuation.
    meaning = `הדירוג לבדו אינו מכריע: טווחי 100×500 ו־25×2,000 חופפים, ובבדיקת עבר התחזית לרמת 500 הייתה גבוהה פי ${format.ltr(ratio)} מהתוצאה בפועל`;
    const n2000 = format.formatNumber(backtest["2000"].n_train_at_level);
    action = `לא לבצע הקצאה מלאה לפי הדירוג. אם בוחנים אחת מארבע החלופות, לבצע פיילוט מבוקר של 25×2,000, שלה ${format.ltr(n2000)} שורות אימון ובדיקת עבר קרובה יותר`;
  } else {
    meaning = "הדירוג לבדו אינו מכריע: טווחי 100×500 ו־25×2,000 חופפים, ובדיקת עבר על רמת 500 מעלה סימן שאלה על התחזית שם. פירוט מדויק אינו זמין כרגע";
    // Degraded, no invented "322" row count or backtest comparison
    // claim -- same reasoning as buildOverlapAlert's own gated
    // recommendation, applied to this layer instead of hiding it
    // outright (D9's four layers are never optional, DESIGN.md §6).
    action = "לא לבצע הקצאה מלאה לפי הדירוג. אם בוחנים אחת מארבע החלופות, פיילוט מבוקר בהיקף מוגבל עדיף על הקצאה מלאה";
  }
  return renderSummaryRecommendation({
    answer: "100×500 מדורגת ראשונה מספרית, אך אינה המלצה לפעולה; שתי המובילות חופפות ובדיקת העבר של רמת 500 חלשה מאוד",
    meaning,
    action,
    caveat: "הסכומים הם רווח מצטבר צפוי ומניחים רשומות עצמאיות ואדיטיביות; אינם רווח בחודש הבא, אינם השפעה סיבתית ואינם הבטחה",
  });
}

function renderSuccess(sim) {
  container.replaceChildren();
  const sorted = [...sim.strategies].sort((a, b) => a.rank - b.rank);
  container.appendChild(buildOverlapAlert(sim));
  // IA.md §6: visible even when <details> is closed -- only the
  // methodological breakdown itself collapses.
  container.appendChild(el("p", {
    className: "model-disclaimer",
    text: "הסכומים הם רווח מצטבר צפוי, לא רווח בחודש הבא; ההשוואה מניחה רשומות עצמאיות ואדיטיביות ואינה השפעה סיבתית.",
  }));
  container.appendChild(buildStrategyTable(sorted));
  container.appendChild(buildChart(sorted));
  container.appendChild(buildD9(sim));
  container.appendChild(buildModelDetails(sim));
}

function renderLoading() {
  container.replaceChildren();
  container.appendChild(status.loadingElement("טוען את סימולציית התקציב…"));
}

function renderError(message) {
  container.replaceChildren();
  container.appendChild(status.errorElement(message, { onRetry: load }));
}

async function load() {
  screenState = "loading";
  const myGen = gen.bump();
  renderLoading();

  const [result] = await Promise.all([api.simulateBudget(), facts.init()]);
  if (!gen.isCurrent(myGen)) return;

  if (!result.ok) {
    if (result.reason === "blocked" || result.reason === "stale") {
      screenState = "idle";
      return;
    }
    screenState = "error";
    // IA.md §2.2-equivalent for this screen: an empty response is a
    // failure, never "no strategies" -- DESIGN.md §5.4: "⛔ תשובה ריקה
    // = כשל, לא 'אין אסטרטגיות'". The schema itself already guarantees
    // exactly 4 strategies on a 200, so this branch only ever covers a
    // real transport/availability failure.
    renderError("שגיאה בטעינת סימולציית התקציב. נסו שוב.");
    return;
  }

  screenState = "loaded";
  renderSuccess(result.data);
}

/** Called by app.js's router every time the budget route is shown. */
export function show(screenContainer) {
  container = screenContainer;
  if (screenState === "idle") {
    load();
  }
}
