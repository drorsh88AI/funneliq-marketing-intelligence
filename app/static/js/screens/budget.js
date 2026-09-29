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
//     live-response template. The "meaning"/"action" layers' "פי 8.60"
//     / "322 שורות" figures come from business_facts.json
//     (budget_backtest) -- degraded gracefully (P11-D15) if that asset
//     fails to load or model_versions.P6 does not match, same pattern
//     as super-customer.js's own D9 "meaning" fallback. The overlap-
//     alert's OWN separate "וטו + פיילוט" paragraph is gated even more
//     strictly (hidden outright, not degraded) -- IA.md §6 / DESIGN.md's
//     P11-D15-extended note are explicit that a backtest failure hides
//     that whole recommendation and forbids substituting a rank-only
//     one in its place.
//   ⚠ RESOLVED (review round, 2026-09-15, explicit user decision): the
//     overestimate-ratio figure was originally documented everywhere as
//     "8.59", but standard rounding of the live ratio
//     (predicted_per_customer/actual_mean_per_customer at level 500) --
//     and of SPEC.md's own stated inputs for it -- both give 8.60, a
//     pre-existing documentation arithmetic error, not a frontend bug
//     (PHASE11.md §ב forbids resolving such a thing silently in this
//     module, which an earlier Math.floor "fix" had wrongly done). The
//     user's decision: show whatever the real calculation produces.
//     SPEC.md/IA.md/DESIGN.md were corrected from "8.59" to "8.60" to
//     match. See buildOverlapAlert()'s own comment for the derivation.
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
// Icon glyphs are this module's own choice (no specific glyph is locked
// anywhere in the source docs, same as predict.js's own PROPENSITY_BAND
// icons) -- but DESIGN.md lines 223-225 are UNCONDITIONAL ("בשום מצב")
// that evidence-badge always carries both text AND an icon, never text
// alone. Self-review finding, 2026-09-15: the original strategy-table
// badge had text only -- missed entirely, since predict.js's own
// evidence-badge only ever renders the "low" state and this file copied
// just its CSS class naming, not its icon-building structure.
const EVIDENCE_ICONS = { high: "●", medium: "◐", low: "○" };

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

/** "100 קמפיינים × ₪500" style composition strings, built from the LIVE
 * allocations array -- never a hardcoded strategy_id -> label table, so
 * a future contract value is described correctly rather than silently
 * mismatched. `PHASE12A.md` §ז1's own approved chart-value wording is
 * "100 קמפיינים × ₪500" (spelled-out "קמפיינים"), not the bare
 * "100×₪500" a prior version of this function rendered -- a real gap
 * `e2e/test_11_chart_english_chrome.py` never asserted on (it only
 * checks chart title/subtitle/axis names, not Budget's per-bar tick
 * text), found by re-reading the approved table directly against the
 * live chart rather than trusting that test's silence.
 *
 * Self-review finding, 2026-09-15: the original version wrapped only
 * the count in format.ltr() and left "×" and the currency figure bare
 * -- inconsistent with IA.md line 956 ("מספרים... וסימני מטבע ב-LTR
 * בתוך container של RTL"). Now that a Hebrew word sits between the two
 * numeric tokens, they can no longer share one isolate the way
 * predict.js's own all-numeric "followup_5 (13) − closed (2)" does --
 * count and currency are wrapped SEPARATELY, with "קמפיינים" and "×"
 * left as plain (direction-neutral/Hebrew) text between them. */
function compositionText(allocations) {
  return allocations
    .map((a) => `${format.ltr(format.formatNumber(a.count))} קמפיינים × ${format.ltr(format.formatCurrency(a.ad_budget))}`)
    .join(" + ");
}

/** §יג-6 (PHASE12A.md, ביקורת Codex, 28.09.2026): the box used to name
 * hardcoded strategies ("100×500"/"25×2,000") and carry the full
 * backtest-backed recommendation paragraph itself -- duplicating the
 * bottom D9 section's own "חשוב לדעת"/meaning content, and depending on
 * business_facts.json for a component DESIGN.md §1.4 locks as "הרכיב
 * הבולט ביותר במסך" (so it must not disappear just because that asset
 * failed to load). Shortened to a pure `top_two_overlap`-driven pointer
 * -- no strategy names, no business_facts dependency, no duplicated
 * explanation; the full explanation lives ONLY in buildD9() below.
 * Renders nothing at all when `top_two_overlap` is false (the project's
 * frozen dataset never actually reaches that branch; IA.md only
 * permits, not locks, wording for it, and no test exercises it). */
function buildOverlapAlert(sim) {
  if (!sim.top_two_overlap) return null;
  // Review finding, CP6 round 2 (29.09.2026): "ר' הסבר מלא למטה" is a
  // promise -- buildD9()'s own degraded branch (business_facts.json
  // missing/mismatched) does NOT actually explain the overlap at all,
  // it only says the comparison itself is unavailable. Same gating
  // condition and same wording ("בדיקת העבר... חסרה") as that branch,
  // so the two halves of the screen never contradict each other.
  const backtest = facts.getBudgetBacktest(sim.model_version);
  const hasFullExplanation = Boolean(backtest && backtest["500"] && backtest["2000"]);
  const wrap = el("div", { className: "overlap-alert", role: "alert" });
  wrap.appendChild(el("p", {
    text: hasFullExplanation
      ? "טווחי האומדן של שתי דרכי החלוקה המובילות חופפים — ר' הסבר מלא למטה."
      : "טווחי האומדן של שתי דרכי החלוקה המובילות חופפים; ההסבר המלא אינו זמין כרגע, כי בדיקת העבר הדרושה לו חסרה.",
  }));
  return wrap;
}

/** BudgetAllocation.sample_size, DESIGN.md line 394: "n לכל רמה" -- its
 * OWN field, distinct from the ad_budget×count composition. A
 * multi-level strategy (2x20000_1x10000) shows BOTH values, never a
 * single min (that reduction is a SERVER-side detail of how
 * evidence_level itself gets computed, IA.md §5 -- not a display rule). */
function sampleSizeText(allocations) {
  return allocations.map((a) => format.ltr(format.formatNumber(a.sample_size))).join(" / ");
}

function buildStrategyTable(strategies) {
  const wrap = el("div", { className: "strategy-table-wrap" });
  const table = el("table", { className: "strategy-table" });
  const thead = el("thead", {});
  const headRow = el("tr", {});
  for (const heading of ["דירוג", "הרכב", "רווח צפוי", "טווח (2.5%–97.5%)", "n", "ראיות"]) {
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
    row.appendChild(el("td", { text: sampleSizeText(s.allocations) }));
    row.appendChild(el("td", {}, [
      el("span", { className: `evidence-badge evidence-${s.evidence_level}` }, [
        el("span", { className: "badge-icon", text: EVIDENCE_ICONS[s.evidence_level] }),
        el("span", { text: EVIDENCE_LABELS[s.evidence_level] }),
      ]),
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
    title: "רווח מצטבר צפוי לפי אופן חלוקת התקציב",
    titleEnglish: "Expected Profit by Allocation Strategy",
    xLabel: "אופן החלוקה (קמפיינים × תקציב לקמפיין)",
    yLabel: "רווח מצטבר צפוי (₪)",
    formatValue: (v, d) => `${format.formatCurrency(v)} (טווח: ${format.formatCurrency(d.lower)}–${format.formatCurrency(d.upper)})`,
    barClassName: "chart-bar-uncertain", // D10: a prediction, never --color-primary
    // 12A, 27.09.2026 (overturns P11A-D7's English-legend rule for
    // chart chrome -- §ז1, "✅ הוכרע: הכול בעברית"): Hebrew legend,
    // spelling out what the whisker range is (bootstrap resampling
    // uncertainty) and, per §ז1's own note, that it is NOT a
    // prediction interval for the actual future profit.
    legend: "הקו האנכי בכל עמודה מראה את טווח האומדן (95%, דגימה חוזרת של נתוני האימון): עד כמה האומדן משתנה כשחוזרים על החישוב. הקו יכול לרדת גם מתחת לראש העמודה. זה אינו טווח לרווח שיתקבל בפועל.",
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

/** DESIGN.md §6.1's own Budget Simulator row (§יג-6/§ט-4, approved
 * 24.09.2026 -- replaces the pre-approval "100x500"/"25x2000" draft
 * wording this function used to carry). Only the "meaning"/"caveat"
 * layers' specific figures (789,594 / 530,953 point estimates, 8.60
 * ratio) depend on live `sim.strategies`/business_facts.json; the
 * caveat's ratio sentence degrades gracefully (P11-D15, same pattern as
 * super-customer.js's own D9 "meaning" fallback) if that asset failed
 * to load or model_versions.P6 does not match this response's own
 * model_version -- ALL FOUR layers then switch to the DEGRADED,
 * genuinely different wording below (DESIGN.md §6.1ג), never a
 * word-for-word copy of the healthy one. */
function buildD9(sim) {
  const backtest = facts.getBudgetBacktest(sim.model_version);
  let answer;
  let meaning;
  let action;
  let caveat;
  if (backtest && backtest["500"] && backtest["2000"]) {
    // Resolved by explicit user decision (2026-09-15) -- see
    // buildOverlapAlert()'s own comment for the full derivation.
    // Standard rounding, no Math.floor: gives 8.60, matching
    // SPEC.md/IA.md/DESIGN.md after their own correction from "8.59".
    answer = "הדירוג לבדו אינו מכריע בין שתי דרכי החלוקה המובילות (100×500 ו-25×2,000)";
    const s100x500 = sim.strategies.find((s) => s.strategy_id === "100x500");
    const s25x2000 = sim.strategies.find((s) => s.strategy_id === "25x2000");
    // Review finding, CP6 round 2: this sentence used to assert
    // "overlap" unconditionally on backtest availability alone, so a
    // live `top_two_overlap=false` (never seen on the frozen dataset,
    // but not schema-impossible either) would have the overlap-alert
    // box correctly disappear while THIS text still claimed the ranges
    // overlap -- a direct contradiction between the two halves of the
    // screen. Only this one factual clause is now conditional; the
    // "answer"/"action" layers below stay as approved regardless of
    // overlap -- DESIGN.md's own action-gating table is explicit that
    // "rank 1 אינו אישור להקצאה מלאה" (no full allocation) holds "גם אם
    // החפיפה false", so no other wording here depends on this flag.
    const overlapClause = sim.top_two_overlap
      ? "אבל טווחי האומדן של שתיהן חופפים — אין כאן מבחן שמוכיח הבדל או שוויון"
      : "וטווחי האומדן של שתיהן אינם חופפים";
    meaning = `בתחזית המודל, 100 קמפיינים של ₪500 (${format.formatCurrency(s100x500.point_estimate)}) מדורגים לפני 25 קמפיינים של ₪2,000 (${format.formatCurrency(s25x2000.point_estimate)}); ${overlapClause}`;
    action = "לא להעביר את מלוא ה-₪50,000 לפי הדירוג. אם בוחנים שינוי, להתחיל בניסוי בהיקף מוגבל, בקמפיינים של ₪2,000, ולמדוד את הרווח המצטבר בפועל לפני שמרחיבים";
    const ratio = format.formatNumber(backtest["500"].predicted_per_customer / backtest["500"].actual_mean_per_customer, { decimals: 2 });
    // Three sentences, all visible (§ט-4, approved 24.09.2026) -- joined
    // into this component's own single "caveat" paragraph slot.
    caveat = `למה לא פשוט לבחור בדרך הראשונה? החישוב שלה לא יציב. כשחוזרים עליו, התוצאה משתנה מאוד, ולפעמים יוצאת נמוכה כמו של הדרך השנייה. לכן אי אפשר לקבוע שהיא באמת טובה יותר. בדקנו את המודל על נתוני עבר: בתקציב של ₪500 הוא חזה רווח ממוצע גבוה פי ${format.ltr(ratio)} ממה שהיה בפועל. בתקציב של ₪2,000 התחזית הייתה קרובה למציאות. המספרים הם הערכה של הרווח הכולל שהלקוחות יביאו לאורך זמן. זה לא הרווח של החודש הבא, וזו לא הבטחה.`;
  } else {
    // P11A-D6/DESIGN.md §6.1ג's own Budget Simulator rows, verbatim.
    // The PREVIOUS degraded wording here still named the two specific
    // strategies (100×500/25×2,000) and still recommended a controlled
    // pilot -- exactly the two things D6/D1 forbid without the missing
    // backtest evidence: `answer` used the HEALTHY text unconditionally
    // (never gated at all, DESIGN.md §6.1's own row, not §6.1ג's), and
    // `action` kept "פיילוט מבוקר בהיקף מוגבל עדיף" even with no
    // evidence backing which alternative that pilot should be. §יג-6
    // (סבב ביקורת Codex, 28.09.2026): `answer` also called the model's
    // own estimates "נתונים גולמיים בלבד" -- misleading (these are model
    // forecasts, not raw observations) and repeated "אינה זמינה" twice;
    // fixed without touching `meaning` (already correct -- P11-D6 נעל).
    answer = "השוואה מלאה בין ארבע אסטרטגיות ההקצאה אינה זמינה כרגע — בדיקת העבר הדרושה להמלצה חסרה; אומדני המודל עדיין מוצגים בטבלה שלמטה";
    meaning = "אין בסיס להכריע בין האסטרטגיות ללא ההשוואה המלאה; פירוט מדויק על ביצוע בפועל אינו זמין כרגע";
    action = "לא לבצע הקצאה מלאה לפי הדירוג בלבד. אין בסיס מספיק להמליץ על חלופה מסוימת ללא הראיה החסרה";
    caveat = "הסכומים הם רווח מצטבר צפוי ומניחים רשומות עצמאיות ואדיטיביות; אינם רווח בחודש הבא, אינם השפעה סיבתית ואינם הבטחה";
  }
  return renderSummaryRecommendation({
    answer,
    meaning,
    action,
    caveat,
  });
}

// P11A-D8/D9: the screen's OWN sole h1 carries `total_budget`'s
// display value (DESIGN.md:403/:457 both map the RESPONSE field
// `BudgetSimulation.total_budget` to this heading, not a hand-typed
// constant) -- this screen had NO heading of any level before this
// checkpoint. In the success state it is read from the live `sim`
// (a Codex review round correctly rejected an earlier draft that
// hardcoded "₪50,000" even here, unconditionally on the schema's
// current `Literal[50000]` -- the schema locks the VALUE, not this
// screen's obligation to read it from the response rather than
// duplicate it). loading/error render before any `sim` exists, so
// they fall back to that same, currently-correct literal value --
// never claiming a live figure that hasn't arrived yet. Also satisfies
// D9's own explicit lock against two competing headings here: exactly
// this one h1, nothing else.
// §יג-6 (PHASE12A.md): "₪50,000" alone didn't say what the number WAS --
// no other word on the screen named it either at that point in the DOM.
function appendScreenHeading(totalBudget) {
  const amount = typeof totalBudget === "number" ? totalBudget : 50000;
  container.appendChild(el("h1", { text: `תקציב פרסום חודשי: ${format.formatCurrency(amount)}` }));
}

function renderSuccess(sim) {
  container.replaceChildren();
  appendScreenHeading(sim.total_budget);
  const sorted = [...sim.strategies].sort((a, b) => a.rank - b.rank);
  const overlapAlert = buildOverlapAlert(sim);
  if (overlapAlert) container.appendChild(overlapAlert);
  // IA.md §6: visible even when <details> is closed -- only the
  // methodological breakdown itself collapses.
  container.appendChild(el("p", {
    className: "model-disclaimer",
    text: "הסכומים הם רווח מצטבר צפוי, לא רווח בחודש הבא; ההשוואה מניחה רשומות עצמאיות ואדיטיביות ואינה השפעה סיבתית.",
  }));
  // P11A-D8: DESIGN.md:273's own layout -- "שתי עמודות בלבד: הטבלה
  // בעמודה 1, הגרף (עם ההסבר -- הלגנד -- שלו) בעמודה 2", not stacked.
  const resultsColumns = el("div", { className: "budget-results-columns" });
  resultsColumns.appendChild(buildStrategyTable(sorted));
  resultsColumns.appendChild(buildChart(sorted));
  container.appendChild(resultsColumns);
  container.appendChild(buildD9(sim));
  container.appendChild(buildModelDetails(sim));
}

function renderLoading() {
  container.replaceChildren();
  appendScreenHeading();
  container.appendChild(status.loadingElement("טוען את סימולציית התקציב…"));
}

function renderError(message) {
  container.replaceChildren();
  appendScreenHeading();
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
