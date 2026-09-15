"use strict";

// FunnelIQ Follow-up screen (phase 11, checkpoint 8, IA.md §7). Own
// controller and local state (P11-D3). No user input -- a single GET
// whose response carries TWO independently-available parts (`stages`,
// `calls_to_closed`), each its own discriminated union on `status`
// (schemas.py's StagesPart/CallsPart | PartUnavailable) -- one fetch,
// two independent render branches, not two separate requests.
//
// Content sources, all locked (§ד "כלל תיקון מקור"):
//   - layout: DESIGN.md §3.4's own Follow-up row -- "שתי קבוצות פריסה
//     זו-לצד-זו; בכל קבוצה הגרף למעלה ו-summary-recommendation שלו מיד
//     מתחתיו".
//   - the D9 summary-recommendation for BOTH groups: DESIGN.md §6.1's
//     own נשירה/calls_to_closed rows, verbatim, with the answer/meaning
//     placeholders filled from values THIS module computes live from
//     the response's own data (never hardcoded, even though the
//     project's frozen dataset means they should coincidentally match
//     the reference numbers documented in SPEC.md/IA.md).
//   - the four calls_to_closed summary statistics' own formulas (mean,
//     count>=4/rate, weighted median, mode with ties): DESIGN.md's own
//     "6.1א" note, verbatim -- "ארבעת סיכומי calls_to_closed נגזרים רק
//     לאחר status='available'... אינן נשמרות כעובדות נפרדות ואינן
//     מחושבות מפלט חלקי".
//   - the CP4-D recommendation paragraph: SPEC.md's own "הכרעת CP4-D"
//     section, verbatim, word for word, per IA.md §7.1's explicit
//     instruction ("הנוסח זהה בשלושת המקומות... אין לנסח מחדש ואין
//     לקצר") -- shown ONLY when BOTH parts are available (IA.md §7.2:
//     "נתונים מלאים" is the one state that includes it; a partial
//     failure marks "התשובה המשולבת" unavailable too, since the
//     recommendation itself draws on both the dropout pattern and the
//     calls_to_closed pattern together).
//   - partial-failure behavior: IA.md §7.2's own state table -- the
//     working part stays fully visible, the failed part (and the
//     combined recommendation) are marked unavailable, ⛔ never a
//     stored fallback number.

import * as api from "../api.js";
import * as session from "../session.js";
import * as generation from "../generation.js";
import * as status from "../status.js";
import * as charts from "../charts.js";
import * as format from "../format.js";
import { renderSummaryRecommendation } from "../summary-recommendation.js";

const STAGE_LABELS_HE = { followup_1: "שלב 1", followup_2: "שלב 2", followup_3: "שלב 3", followup_4: "שלב 4", followup_5: "שלב 5" };
const STAGE_LABELS_EN = { followup_1: "Stage 1", followup_2: "Stage 2", followup_3: "Stage 3", followup_4: "Stage 4", followup_5: "Stage 5" };

// SPEC.md's own "הכרעת CP4-D — תשובת P5 המחייבת" section, verbatim,
// word for word -- IA.md §7.1 explicitly forbids rewording or
// shortening it, "בשלושת המקומות" (facts/package-5/business
// recommendation) alike.
const CP4D_RECOMMENDATION =
  "לא. אין לאמץ עצירה אוטומטית אחרי המעקב השלישי. שיעור הנשירה לאחר המעקב " +
  "הרביעי הוא הנמוך בשרשרת (10.4%). מבין 3,318 הרשומות שבהן נסגרה עסקה " +
  "(closed>0), הקובץ אינו מאפשר למנות סבבי מעקב לעסקה בודדת. במדד הקרוב, " +
  "התפלגות calls_to_closed ברמת הרשומה, החציון הוא 3, הערך " +
  "השכיח הוא 2 והממוצע 3.706; ב־1,595 רשומות (48.07%) הממוצע הוא 4 שיחות ומעלה. " +
  "חמשת שלבי המעקב מתארים כמה לידים נותרו אחרי כל סבב, ואילו " +
  "calls_to_closed הוא ממוצע שיחות ברמת רשומה שיכול להגיע עד 9. לכן אי אפשר " +
  "לומר ש־48.07% מהעסקאות הבודדות דרשו 4+ שיחות, או שהשיחות המאוחרות גרמו " +
  "לסגירה. ההמלצה היא להמשיך מעקבים אחרי השלישי באופן מבוקר ולמדוד בכל שלב " +
  "את שיעור הסגירה השולי, זמן העבודה והעלות לפני שינוי קבוע במדיניות.";

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

/** Same helper as overview.js's own (duplicated, not imported -- pure
 * formatting logic, no shared state, P11-D3 governs state independence
 * between screens, not small local utility functions). Proper Hebrew
 * list grammar for 3+ items ("א, ב וג") -- a plain repeated " ו-" join
 * between every pair reads wrong once there are more than two ties. */
function joinHebrewList(items) {
  if (items.length <= 1) return items.join("");
  if (items.length === 2) return `${items[0]} ו${items[1]}`;
  return `${items.slice(0, -1).join(", ")} ו${items[items.length - 1]}`;
}

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

// ---------------------------------------------------------------------
// Group 1 -- dropout (stages)
// ---------------------------------------------------------------------

function buildStagesGroup(stagesPart) {
  const group = el("div", { className: "followup-group" });
  if (stagesPart.status !== "available") {
    group.appendChild(el("h3", { text: "נשירה" }));
    // DESIGN.md line 119: "panel-error + ניסיון חוזר" -- both parts come
    // from the SAME single GET, so retry re-fetches the whole endpoint
    // (same shape as predict.js's own resolved per-panel retry, which
    // re-submits all three predictions together rather than one alone).
    group.appendChild(status.errorElement(stagesPart.error.message, { onRetry: load }));
    return group;
  }
  const rows = stagesPart.data; // 5 rows, fixed order (schema-guaranteed)

  const chartRows = rows.map((r) => ({
    xHebrew: STAGE_LABELS_HE[r.stage],
    xEnglish: STAGE_LABELS_EN[r.stage],
    value: r.drop_rate,
  }));
  group.appendChild(el("h3", { text: "נשירה" }));
  group.appendChild(charts.renderBarChart({
    data: chartRows,
    xLabel: "שלב מעקב",
    yLabel: "שיעור נשירה",
    formatValue: (v) => (v === null ? "N/A" : format.formatPercent(v, { decimals: 1 })),
  }));
  group.appendChild(renderSummaryRecommendation(computeStagesD9(rows)));
  return group;
}

/** DESIGN.md §6.1's own "נשירה" row -- answer/meaning filled from the
 * live 5 rows; action/caveat are fixed. drop_rate is null only when
 * from_leads=0 (schema invariant) -- excluded from the "lowest stage"
 * comparison the same way Overview excludes a null conversion_rate. */
function computeStagesD9(rows) {
  const withRate = rows.filter((r) => r.drop_rate !== null);
  const ratesText = rows
    .map((r) => `${STAGE_LABELS_HE[r.stage]}: ${r.drop_rate === null ? "N/A" : format.formatPercent(r.drop_rate, { decimals: 1 })}`)
    .join(" · ");
  let answer = `שיעורי הנשירה הם ${ratesText}`;
  if (withRate.length > 0) {
    const minRate = Math.min(...withRate.map((r) => r.drop_rate));
    const lowest = withRate.filter((r) => r.drop_rate === minRate);
    const lowestLabel = joinHebrewList(lowest.map((r) => STAGE_LABELS_HE[r.stage]));
    answer += `; ${lowestLabel} הוא הנמוך`;
  }
  return {
    answer,
    meaning: "אם השיעורים אינם עולים ברצף, הנתונים אינם תומכים בעצירה אוטומטית רק מפני שהתקדם מספר השלב",
    action: "ההמלצה היא להמשיך מעקבים אחרי השלישי באופן מבוקר ולמדוד בכל שלב את שיעור הסגירה השולי, זמן העבודה והעלות לפני שינוי קבוע במדיניות",
    caveat: "הנתונים מתארים מה קרה בפועל בכל שלב, ⛔ ואינם מסבירים מדוע",
  };
}

// ---------------------------------------------------------------------
// Group 2 -- calls_to_closed distribution
// ---------------------------------------------------------------------

/** DESIGN.md's own "6.1א" formulas, verbatim -- computed live from the
 * response's own distribution[], never stored as a separate fact and
 * never computed from a partial/failed response. */
function computeCallsStats(dist) {
  const sorted = [...dist.distribution].sort((a, b) => a.calls - b.calls);
  const populationN = dist.population_n;

  const mean = sorted.reduce((sum, b) => sum + b.calls * b.n, 0) / populationN;

  const countGe4 = sorted.filter((b) => b.calls >= 4).reduce((sum, b) => sum + b.n, 0);
  const rateGe4 = countGe4 / populationN;

  const medianPositions = populationN % 2 === 0 ? [populationN / 2, populationN / 2 + 1] : [(populationN + 1) / 2];
  const medianValues = medianPositions.map((pos) => {
    let cumulative = 0;
    for (const b of sorted) {
      cumulative += b.n;
      if (cumulative >= pos) return b.calls;
    }
    return sorted[sorted.length - 1].calls;
  });
  const median = medianValues.reduce((a, b) => a + b, 0) / medianValues.length;

  const maxN = Math.max(...sorted.map((b) => b.n));
  const modes = sorted.filter((b) => b.n === maxN).map((b) => b.calls);

  return { sorted, populationN, mean, countGe4, rateGe4, median, modes };
}

function buildCallsGroup(callsPart) {
  const group = el("div", { className: "followup-group" });
  if (callsPart.status !== "available") {
    group.appendChild(el("h3", { text: "מספר שיחות עד סגירה" }));
    group.appendChild(status.errorElement(callsPart.error.message, { onRetry: load }));
    return group;
  }
  const stats = computeCallsStats(callsPart.data);

  const chartRows = stats.sorted.map((b) => ({
    xHebrew: format.formatNumber(b.calls),
    xEnglish: String(b.calls),
    value: b.n,
  }));
  group.appendChild(el("h3", { text: "מספר שיחות עד סגירה" }));
  group.appendChild(charts.renderBarChart({
    data: chartRows,
    xLabel: "מספר שיחות",
    yLabel: "מספר רשומות",
    formatValue: (v) => format.formatNumber(v),
  }));
  group.appendChild(renderSummaryRecommendation(computeCallsD9(stats)));
  return group;
}

function computeCallsD9(stats) {
  const modeText = stats.modes.length === 1
    ? format.ltr(format.formatNumber(stats.modes[0]))
    : format.ltr(stats.modes.map((m) => format.formatNumber(m)).join(" / "));
  return {
    answer: `אין בקובץ מניין מעקבים לעסקה בודדת. במדד הקרוב, ${format.ltr("calls_to_closed")}, ב־${format.ltr(format.formatNumber(stats.populationN))} רשומות שנסגרו: חציון ${format.ltr(format.formatNumber(stats.median))}, שכיח ${modeText} וממוצע ${format.ltr(format.formatNumber(stats.mean, { decimals: 3 }))}`,
    meaning: `ב־${format.ltr(format.formatNumber(stats.countGe4))} רשומות (${format.ltr(format.formatPercent(stats.rateGe4, { decimals: 2 }))}) ממוצע השיחות עד סגירה הוא 4 ומעלה. יחד עם דפוס הנשירה, אין בסיס לעצירה אוטומטית אחרי המעקב השלישי`,
    action: "ההמלצה היא להמשיך מעקבים אחרי השלישי באופן מבוקר ולמדוד בכל שלב את שיעור הסגירה השולי, זמן העבודה והעלות לפני שינוי קבוע במדיניות",
    caveat: "calls_to_closed הוא ממוצע ברמת רשומה ולא היסטוריה לעסקה; חמשת שלבי המעקב אינם מספר השיחות, שמגיע עד 9; אין הוכחה סיבתית או כלכלית",
  };
}

// ---------------------------------------------------------------------

function renderSuccess(resp) {
  container.replaceChildren();

  const layout = el("div", { className: "followup-layout" });
  layout.appendChild(buildStagesGroup(resp.stages));
  layout.appendChild(buildCallsGroup(resp.calls_to_closed));
  container.appendChild(layout);

  const bothAvailable = resp.stages.status === "available" && resp.calls_to_closed.status === "available";
  const recWrap = el("div", { className: "followup-recommendation" });
  if (bothAvailable) {
    recWrap.appendChild(el("h3", { text: "המלצה" }));
    recWrap.appendChild(el("p", { text: CP4D_RECOMMENDATION }));
  } else {
    // IA.md §7.2: a partial failure marks "התשובה המשולבת" (the
    // combined answer) unavailable too -- ⛔ never a stored fallback
    // number in its place.
    recWrap.appendChild(el("p", { className: "followup-recommendation-unavailable", role: "status", text: "ההמלצה המשולבת אינה זמינה כרגע -- אחד משני חלקי הנתונים חסר." }));
  }
  container.appendChild(recWrap);
}

function renderLoading() {
  container.replaceChildren();
  container.appendChild(status.loadingElement("טוען נתוני מעקב…"));
}

function renderError(message) {
  container.replaceChildren();
  container.appendChild(status.errorElement(message, { onRetry: load }));
}

async function load() {
  screenState = "loading";
  const myGen = gen.bump();
  renderLoading();

  const result = await api.insightsFollowup();
  if (!gen.isCurrent(myGen)) return;

  if (!result.ok) {
    if (result.reason === "blocked" || result.reason === "stale") {
      screenState = "idle";
      return;
    }
    screenState = "error";
    renderError("שגיאה בטעינת נתוני המעקב. נסו שוב.");
    return;
  }

  screenState = "loaded";
  renderSuccess(result.data);
}

/** Called by app.js's router every time the followup route is shown. */
export function show(screenContainer) {
  container = screenContainer;
  if (screenState === "idle") {
    load();
  }
}
