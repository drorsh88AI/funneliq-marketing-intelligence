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
import * as session from "../session.js";
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
// "idle": nothing tried yet, or a session/auth transition discarded
//   the last attempt without ever showing the user anything real --
//   a later show() retries.
// "loading" / "loaded" / "error": a real attempt is in flight, or
//   produced content the user has actually seen -- show() does NOT
//   silently re-fetch on a mere revisit; "error" offers its own
//   retry control.
// Fixed after an independent review found the original single
// `attempted` boolean latched permanently true even when the result
// was "blocked"/"stale" (a session transition, not a real answer) --
// leaving Overview stuck on its loading spinner forever after a
// sign-out + sign-in cycle, since no later show() would ever retry.
let screenState = "idle";

// Subscribed exactly ONCE -- this is a top-level (module-evaluation-
// time) statement, and ES modules are singletons, so this never
// double-registers no matter how many times show() itself is called.
//
// Fixed after an independent review found this screen never listened
// to session.onSessionEvent() at all: once loaded, `screenState`
// stayed "loaded" forever, so sign-out/401/403 (which hide the whole
// shell but do not themselves touch this module) followed by a fresh
// sign-in left the OLD session's already-rendered content in the DOM,
// and a later show() -- seeing "loaded" -- never re-fetched. P11-D5 /
// P11-D14 require exactly the opposite: sign-out and 401/403 clear all
// state.
//
// A SECOND review found the first fix still incomplete for
// epochRaised WITHOUT stateCleared (P11-D14's conservative
// same-user/different-token SIGNED_IN case) while a load() is
// in-flight. api.js's own per-call epoch check does discard that
// in-flight request's eventual response -- but discarding a response
// is not the same as SCHEDULING a replacement: the router's own
// show() call, which arrives once the NEW session's /api/me confirms
// 200, finds screenState still "loading" (this module had no reason
// yet to think otherwise) and defers to the doomed in-flight
// request -- only for that request to later resolve "stale" with no
// show() left to trigger a fresh load(). The screen was left on
// "loading" forever with no active request. Fixed by reacting to the
// epoch-raise event ITSELF, synchronously, rather than waiting for
// the eventual stale response: if a load() is currently in flight
// when a conservative epoch-raise happens, this screen's own
// generation is bumped and screenState returns to "idle" right then
// -- so the show() that arrives moments later (once the new session's
// own /api/me succeeds) finds "idle" and starts a fresh load()
// immediately, instead of silently doing nothing.
session.onSessionEvent(({ epochRaised, stateCleared }) => {
  if (stateCleared) {
    gen.bump(); // invalidate any of THIS screen's own in-flight load(), independent of api.js's epoch check
    screenState = "idle";
    if (container) container.replaceChildren();
    return;
  }
  if (epochRaised && screenState === "loading") {
    // Nothing real has been shown yet ("loading" never rendered
    // content) -- no DOM touch here, only state, so the fresh load()
    // the next show() triggers is free to start clean.
    gen.bump();
    screenState = "idle";
  }
  // loaded/error + epochRaised-only: no action -- already-rendered
  // content must survive a conservative epoch raise untouched.
});

function renderCapabilityIndex() {
  // P11A-D9: an h2 must precede the five capability-card h3s below --
  // verbatim from IA.md §2's own hierarchy line ("כותרת → אינדקס חמש
  // היכולות → ..."), not new invented text. Returned as a fragment
  // alongside the existing div so all three call sites (success/
  // loading/error) get it automatically, without each needing its own
  // edit.
  const fragment = document.createDocumentFragment();
  const heading = document.createElement("h2");
  heading.textContent = "אינדקס חמש היכולות";
  fragment.appendChild(heading);

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
  fragment.appendChild(el);
  return fragment;
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

  // Monotonicity across Low->Mid->High can only be judged with all
  // THREE numeric rates present. A missing tier or a null
  // conversion_rate is an absence of evidence, not evidence that the
  // sequence fails to increase -- fixed after an independent review
  // found the original two-branch version treated "incomplete" and
  // "not increasing" as the same thing, which let it declare a
  // "surprising" finding from data that couldn't actually support it.
  const complete = withRate.length === 3;
  const monotonic = complete &&
    withRate[1].conversion_rate >= withRate[0].conversion_rate &&
    withRate[2].conversion_rate >= withRate[1].conversion_rate;

  // The monotonic branch's text is this module's own reasonable
  // composition (not a verbatim doc quote -- none exists for it), for
  // a code path the project's own frozen dataset cannot reach (IA.md
  // §1 example: Low 4.5% / Mid 8.2% / High 5.4% -- verified NOT
  // monotonic). The "insufficient data" branch is likewise this
  // module's own composition, deliberately factual and free of any
  // business conclusion (neither "surprising" nor "not surprising" --
  // there simply isn't enough evidence to say either), per the same
  // review's explicit instruction not to invent a finding here.
  let meaning;
  if (!complete) {
    meaning = "אין מספיק נתונים ברמות Low/Mid/High כדי לקבוע אם שיעור ההמרה עולה עם רמת ההוצאה.";
  } else if (monotonic) {
    meaning = "רצף Low→Mid→High עולה בהתאם לציפייה הפשוטה שהוצאה גבוהה יותר קשורה להמרה גבוהה יותר; אין לטעון להפתעה.";
  } else {
    meaning = "אם רצף Low→Mid→High אינו עולה, הוצאה גבוהה יותר לא הניבה המרה גבוהה יותר — ממצא מפתיע ביחס לציפייה הפשוטה.";
  }

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
    titleEnglish: "Conversion Rate by Ad Budget Level",
    xLabelEnglish: "Ad Budget Level",
    yLabelEnglish: "Conversion Rate",
    formatValue: (v) => (v === null ? "N/A" : format.formatPercent(v, { decimals: 1 })),
  });
}

// P11A-D8/D9: the screen's own sole h1 -- IA.md §2's own hierarchy
// ("כותרת → אינדקס חמש היכולות → ..."), reusing index.html's own
// app-nav label for this route rather than inventing new text. A tiny
// shared helper so all three render states get it identically, instead
// of tripling the same two lines.
function appendScreenHeading() {
  const heading = document.createElement("h1");
  heading.textContent = "סקירה כללית";
  container.appendChild(heading);
}

function renderSuccess(tiers) {
  container.replaceChildren();
  appendScreenHeading();
  container.appendChild(renderCapabilityIndex());
  container.appendChild(renderTierTable(tiers));
  container.appendChild(renderChart(tiers));
  container.appendChild(renderSummaryRecommendation(computeSummary(tiers)));
}

function renderLoading() {
  container.replaceChildren();
  appendScreenHeading();
  container.appendChild(renderCapabilityIndex());
  container.appendChild(status.loadingElement("טוען נתוני המרה…"));
}

function renderError(message) {
  container.replaceChildren();
  appendScreenHeading();
  container.appendChild(renderCapabilityIndex());
  container.appendChild(status.errorElement(message, { onRetry: load }));
}

async function load() {
  screenState = "loading";
  const myGen = gen.bump();
  renderLoading();

  const result = await api.insightsBudgetTiers();
  if (!gen.isCurrent(myGen)) return; // a newer load() call has since started -- it owns screenState now

  if (!result.ok) {
    if (result.reason === "blocked" || result.reason === "stale") {
      // Not a real attempt -- a session/auth transition is already
      // being handled elsewhere (bootstrap.js / api.js's shared
      // handler). Nothing real was ever shown, so back to "idle": a
      // later show() (e.g. after a fresh sign-in reaches 200 again)
      // retries instead of staying stuck on this loading spinner.
      screenState = "idle";
      return;
    }
    screenState = "error";
    renderError("שגיאה בטעינת נתוני ההמרה. נסו שוב.");
    return;
  }

  const tiers = result.data.tiers;
  if (tiers.length === 0) {
    // IA.md §2.2: 200 with zero rows is a data-availability error, NOT
    // an authorization problem and NOT a legitimate "empty" state.
    screenState = "error";
    renderError("אין כרגע נתוני המרה זמינים. נסו שוב.");
    return;
  }

  screenState = "loaded";
  renderSuccess(tiers);
}

/** Called by app.js's router the first time (and every time) the
 * overview route is shown. `navigateFn` is router.navigate, injected
 * so this screen module never imports router.js directly. Re-fetches
 * only from "idle" -- a repeat visit to an already-loaded (or already-
 * errored, with its own retry control) Overview does not silently
 * re-query the server; a repeat visit after a discarded blocked/stale
 * attempt does. */
export function show(screenContainer, navigateFn) {
  container = screenContainer;
  navigate = navigateFn;
  if (screenState === "idle") {
    load();
  }
}
