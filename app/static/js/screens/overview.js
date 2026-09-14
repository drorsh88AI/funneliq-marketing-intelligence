"use strict";

// FunnelIQ Overview screen (phase 11, checkpoint 3). Own controller and
// local state (P11-D3) -- no state shared with any other screen.
//
// Content sources, all locked (§ד "כלל תיקון מקור" -- nothing here is
// invented):
//   - capability-index: IA.md §2 "מיפוי חמש היכולות" table (D8) --
//     five card titles/bodies/limitations verbatim, mapped to their
//     four target routes.
//   - tier-table: IA.md §2.1 (the gap row, "gap (1501–1999)" literal
//     label, budget_tier=null vs zero-rows-for-a-tier distinction).
//   - summary-recommendation: DESIGN.md §6.1's Overview row (PHASE10.md
//     D9) -- the answer template, the conditional meaning sentence
//     (both branches quoted verbatim; see computeSummary()'s own
//     comment for the one branch that is currently unreachable with
//     this project's frozen dataset), and the fixed action/caveat text.

import * as api from "../api.js";
import * as generation from "../generation.js";
import * as status from "../status.js";
import * as charts from "../charts.js";
import * as format from "../format.js";
import { renderSummaryRecommendation } from "../summary-recommendation.js";

const CAPABILITIES = [
  {
    title: "תחזית אורך חיי לקוח",
    body: "כמה זמן צפוי לקוח חדש להישאר",
    limitation:
      "התחזית מתייחסת ללקוח שנרכש בקמפיין שהסתיים, ומבוססת על נתוני סוף הקמפיין. זו אינה תחזית בשלב מוקדם של המשפך.",
    route: "predict",
  },
  {
    title: "תחזית רכישה נוספת",
    body: "מי צפוי לקנות יותר",
    // IA.md §2 D8 table, row 2: "אותה מגבלה -- אותו snapshot" -- the
    // identical limitation sentence as row 1, reused verbatim.
    limitation:
      "התחזית מתייחסת ללקוח שנרכש בקמפיין שהסתיים, ומבוססת על נתוני סוף הקמפיין. זו אינה תחזית בשלב מוקדם של המשפך.",
    route: "predict",
  },
  {
    title: "ציון פוטנציאל לקוח־על",
    body: "מי מבין הרוכשים עשוי להפוך ללקוח־על",
    limitation: "לרוכש ידוע, לאחר מעקב 1 וסגירת חלון גיוס חודשי; מוקדם ביחס לתוצאות היעד.",
    route: "super-customer",
  },
  {
    title: "הקצאת תקציב פרסום",
    body: "לאן להקצות את תקציב הפרסום",
    limitation: null,
    route: "budget",
  },
  {
    title: "יעילות מעקב שיחות",
    body: "האם נכון להפסיק מעקבים אחרי השלב השלישי",
    limitation: "ממצא תיאורי, לא סיבתי.",
    route: "followup",
  },
];

const TIER_LABELS = {
  Low: "נמוכה",
  Mid: "בינונית",
  High: "גבוהה",
};
const TIER_LABELS_EN = { Low: "Low", Mid: "Mid", High: "High" };
const GAP_LABEL_HE = "gap (1501–1999)";
const GAP_LABEL_EN = "gap (1501-1999)";

const gen = generation.createGenerationCounter();

let container = null;
let navigate = null; // router.navigate -- injected so this module never imports router.js directly
let attempted = false; // true once a fetch has ever been started

function renderCapabilityIndex() {
  const el = document.createElement("div");
  el.className = "capability-index";
  for (const cap of CAPABILITIES) {
    const card = document.createElement("button");
    card.type = "button";
    card.className = "capability-card";
    card.addEventListener("click", () => navigate(cap.route));

    const h = document.createElement("h3");
    h.textContent = cap.title;
    card.appendChild(h);

    const body = document.createElement("p");
    body.textContent = cap.body;
    card.appendChild(body);

    if (cap.limitation) {
      const lim = document.createElement("p");
      lim.className = "capability-limitation";
      lim.textContent = cap.limitation;
      card.appendChild(lim);
    }

    el.appendChild(card);
  }
  return el;
}

function tierLabelHe(row) {
  return row.budget_tier ? TIER_LABELS[row.budget_tier] : GAP_LABEL_HE;
}

function renderTierTable(tiers) {
  const wrap = document.createElement("div");
  wrap.className = "tier-table-wrap";
  const table = document.createElement("table");
  table.className = "tier-table";

  const thead = document.createElement("thead");
  const headRow = document.createElement("tr");
  for (const heading of ["רמת הוצאה חודשית", "מספר רשומות", "שיעור המרה"]) {
    const th = document.createElement("th");
    th.textContent = heading;
    headRow.appendChild(th);
  }
  thead.appendChild(headRow);
  table.appendChild(thead);

  const tbody = document.createElement("tbody");
  for (const row of tiers) {
    const tr = document.createElement("tr");
    if (row.budget_tier === null) tr.classList.add("tier-row-gap");

    const tierCell = document.createElement("th");
    tierCell.setAttribute("scope", "row");
    tierCell.textContent = tierLabelHe(row);
    tr.appendChild(tierCell);

    const nCell = document.createElement("td");
    nCell.textContent = format.formatNumber(row.n_records);
    tr.appendChild(nCell);

    const rateCell = document.createElement("td");
    // IA.md §2.1: conversion_rate null -> "N/A", never a zero column.
    rateCell.textContent = row.conversion_rate === null ? "N/A" : format.formatPercent(row.conversion_rate, { decimals: 1 });
    tr.appendChild(rateCell);

    tbody.appendChild(tr);
  }
  table.appendChild(tbody);
  wrap.appendChild(table);
  return wrap;
}

function joinHebrewList(items) {
  if (items.length <= 1) return items.join("");
  if (items.length === 2) return `${items[0]} ו${items[1]}`;
  return `${items.slice(0, -1).join(", ")} ו${items[items.length - 1]}`;
}

/** DESIGN.md §6.1's Overview row, PHASE10 D9. The answer/meaning
 * template is filled from live data; action/caveat are fixed. */
function computeSummary(tiers) {
  const ordered = ["Low", "Mid", "High"]
    .map((name) => tiers.find((t) => t.budget_tier === name))
    .filter(Boolean);
  const withRate = ordered.filter((t) => t.conversion_rate !== null);

  const ratesText = ordered
    .map((t) => `${TIER_LABELS[t.budget_tier]} ${t.conversion_rate === null ? "N/A" : format.formatPercent(t.conversion_rate, { decimals: 1 })}`)
    .join(" · ");

  let answer = `אין נתוני שיעור המרה זמינים ברמות Low/Mid/High — ${ratesText}`;
  if (withRate.length > 0) {
    const maxRate = Math.max(...withRate.map((t) => t.conversion_rate));
    const topTiers = withRate.filter((t) => t.conversion_rate === maxRate);
    const topLabel = topTiers.length === 1
      ? `רמת ${TIER_LABELS[topTiers[0].budget_tier]}`
      : `שוויון בין ${joinHebrewList(topTiers.map((t) => `רמת ${TIER_LABELS[t.budget_tier]}`))}`;
    answer = `${topLabel} — ${ratesText}`;
  }

  // Monotonic non-decreasing across Low->Mid->High, using only tiers
  // that are actually present with a real (non-null) rate. Verified
  // against the project's own frozen dataset (IA.md §1 example: Low
  // 4.5% / Mid 8.2% / High 5.4%) -- NOT monotonic, so in practice the
  // "surprising" branch below is what this project's data always
  // produces. The monotonic branch's text is therefore this module's
  // own reasonable composition (not a verbatim doc quote -- none
  // exists for it) for a code path the current dataset cannot reach;
  // flagged here rather than silently invented.
  const monotonic = withRate.length === 3 &&
    withRate[1].conversion_rate >= withRate[0].conversion_rate &&
    withRate[2].conversion_rate >= withRate[1].conversion_rate;

  const meaning = monotonic
    ? "רצף Low→Mid→High עולה בהתאם לציפייה הפשוטה שהוצאה גבוהה יותר קשורה להמרה גבוהה יותר; אין לטעון להפתעה."
    : "אם רצף Low→Mid→High אינו עולה, הוצאה גבוהה יותר לא הניבה המרה גבוהה יותר — ממצא מפתיע ביחס לציפייה הפשוטה.";

  const action = "להשוות את רמת ההוצאה הנוכחית לטבלה לפני שמזיזים כסף, ולבחון את החלופות בסימולטור.";
  const caveat = "ההשוואה מתארת קבוצות בנתונים ההיסטוריים ואינה מוכיחה שהזזת תקציב תשנה את ההמרה.";

  return { answer, meaning, action, caveat };
}

function renderChart(tiers) {
  const chartRows = ["Low", "Mid", "High"]
    .map((name) => tiers.find((t) => t.budget_tier === name))
    .filter(Boolean)
    .map((t) => ({
      xHebrew: TIER_LABELS[t.budget_tier],
      xEnglish: TIER_LABELS_EN[t.budget_tier],
      value: t.conversion_rate,
    }));
  return charts.renderBarChart({
    data: chartRows,
    xLabel: "רמת הוצאה חודשית",
    yLabel: "שיעור המרה",
    formatValue: (v) => (v === null ? "N/A" : format.formatPercent(v, { decimals: 1 })),
  });
}

function renderSuccess(tiers) {
  container.replaceChildren();
  container.appendChild(renderCapabilityIndex());
  container.appendChild(renderTierTable(tiers));
  container.appendChild(renderChart(tiers));
  container.appendChild(renderSummaryRecommendation(computeSummary(tiers)));
}

function renderLoading() {
  container.replaceChildren();
  container.appendChild(renderCapabilityIndex());
  container.appendChild(status.loadingElement("טוען נתוני המרה…"));
}

function renderError(message) {
  container.replaceChildren();
  container.appendChild(renderCapabilityIndex());
  container.appendChild(status.errorElement(message, { onRetry: load }));
}

async function load() {
  attempted = true;
  const myGen = gen.bump();
  renderLoading();

  const result = await api.insightsBudgetTiers();
  if (!gen.isCurrent(myGen)) return; // a newer load() call has since started

  if (!result.ok) {
    if (result.reason === "blocked" || result.reason === "stale") return; // a session/auth transition is already being handled elsewhere
    renderError("שגיאה בטעינת נתוני ההמרה. נסו שוב.");
    return;
  }

  const tiers = result.data.tiers;
  if (tiers.length === 0) {
    // IA.md §2.2: 200 with zero rows is a data-availability error, NOT
    // an authorization problem and NOT a legitimate "empty" state.
    renderError("אין כרגע נתוני המרה זמינים. נסו שוב.");
    return;
  }

  renderSuccess(tiers);
}

/** Called by app.js's router the first time (and every time) the
 * overview route is shown. `navigateFn` is router.navigate, injected
 * so this screen module never imports router.js directly. Re-fetches
 * only if it has never successfully attempted before -- a repeat visit
 * to an already-loaded Overview does not re-query the server. */
export function show(screenContainer, navigateFn) {
  container = screenContainer;
  navigate = navigateFn;
  if (!attempted) {
    load();
  }
}
