"use strict";

// FunnelIQ Overview screen (phase 11, checkpoint 3). Own controller and
// local state (P11-D3) -- no state shared with any other screen.
//
// Content sources, all locked (§ד "כלל תיקון מקור" -- nothing here is
// invented):
//   - capability-index: IA.md §2 "מיפוי חמש היכולות" table (D8) --
//     five card titles/bodies/limitations verbatim, mapped to their
//     four target routes.
//   - the chart's own accessible fallback table carries the gap row
//     (IA.md §2.1: "gap (1501–1999)" literal label, budget_tier=null
//     vs zero-rows-for-a-tier distinction) since 12A removed this
//     screen's separate tier-table (tester finding O4: duplicated the
//     same data, with less detail, right next to the chart).
//   - summary-recommendation: DESIGN.md §6.1's Overview row (PHASE10.md
//     D9, amended by 12A for O5) -- the answer template, three
//     definite-statement meaning branches (never a conditional "if" --
//     see computeSummary()'s own comment for the one branch that is
//     currently unreachable with this project's frozen dataset), and
//     the fixed action/caveat text.

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
// 12A, 27.09.2026 (tester finding: "לא מבינים מה זה mid, high ו-low,
// אין הסבר לא בעברית וגם לא באנגלית"). Used only where the tier is
// shown as a standalone label (table row header, chart category axis)
// -- prose sentences in computeSummary() keep the short TIER_LABELS,
// so "רמת נמוכה — 4.5%..." doesn't turn into a run-on.
const TIER_LABELS_WITH_RANGE = {
  Low: "נמוכה (עד ₪1,500)",
  Mid: "בינונית (₪2,000–5,000)",
  High: "גבוהה (מעל ₪5,000)",
};
const TIER_LABELS_EN = { Low: "Low", Mid: "Mid", High: "High" };

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

// O2 (tester finding: "לא ברור מה הטבלה מנסה להציג ועל סמך מה, הרי לא
// בוצע שום חישוב") + explanations for both column headers (tester:
// "לא מבינים מה זה מספר רשומות ושיעור המרה") + O4 (tester: "עוד טבלה
// אחרי הגרף שמראה בדיוק את אותם נתונים, כפילות מיותרת" -- fixed by
// removing this screen's own separate tier-table entirely; the single
// remaining table is the chart's own mandatory accessible fallback,
// now carrying both columns via extraColumn, see renderChart() below).
// 27.09.2026: four sentences (three explanation + the O4 accessibility
// caption), each its own <p> -- one line per idea, not one long
// run-on paragraph (user feedback on this exact caption). §יג-2
// (28.09.2026 DOM-order fix): these render INSIDE the chart's own
// .chart-live wrapper, between the SVG and the fallback table --
// passed to charts.renderBarChart() as `midCaptions`, not appended
// here directly, so the table stays glued to the SVG as one component
// (charts.js's own invariant) while still landing below this text.
function tierSectionCaptions() {
  return [
    "הטבלה שלהלן והגרף שלמעלה מציגים נתוני עבר של Northbound, לפי רמת הוצאת הפרסום החודשית — לא תוצאה של קלט שהזנתם.",
    "מספר רשומות הוא כמה שורות בנתוני העבר (כל שורה היא מקרה, לא בהכרח לקוח נפרד) נכללות בכל רמת הוצאה.",
    // §יב-2 R1 (final approved wording, 24.09.2026): "ליד"/"המרה"
    // defined in plain language, and the metric spelled out as an
    // average of a per-case ratio -- ⛔ not a global sum-over-sum.
    "ליד הוא פנייה של לקוח פוטנציאלי. המרה היא ליד שהפך לעסקה סגורה. לכל מקרה בנתוני העבר בדקנו איזה אחוז מהלידים הפכו לעסקה, ואז חישבנו את הממוצע בכל רמת תקציב.",
    // O4 (tester finding: "אותם נתונים פעמיים"; PHASE12A.md §ב3 O4's
    // planned fix): the fallback table right after this line is the
    // SAME data as the chart, on purpose -- an accessible equivalent
    // (DESIGN.md §4.1), not a second, redundant data display.
    "הטבלה מתחת לגרף מציגה את אותם נתונים כטבלה, לנגישות.",
  ];
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

  // 12A, 27.09.2026 (fixes O5, tester finding: "'אם רצף...' -- אין
  // רצף של כלום, רק הצגת נתונים שאף אחד לא מבין"). The non-monotonic
  // branch used to phrase a fact the code had ALREADY determined as a
  // hypothetical "if" sentence -- a real content bug, not a wording
  // preference (DESIGN.md:452's own fix note). All three branches are
  // now definite statements about the one state that actually holds;
  // ⛔ none of them is ever an "if". The monotonic branch's text is
  // this module's own reasonable composition (not a verbatim doc quote
  // -- none exists for it), for a code path the project's own frozen
  // dataset cannot reach (IA.md §1 example: Low 4.5% / Mid 8.2% / High
  // 5.4% -- verified NOT monotonic, so this is the branch actually
  // rendered today). The "insufficient data" branch is likewise this
  // module's own composition, deliberately factual and free of any
  // business conclusion (neither "surprising" nor "not surprising" --
  // there simply isn't enough evidence to say either), per an earlier
  // review's explicit instruction not to invent a finding here.
  let meaning;
  if (!complete) {
    // §יג-2 follow-up (28.09.2026): same Low/Mid/High -> Hebrew-name
    // fix, extended to this third branch (the first round only covered
    // the two "רצף" branches below).
    meaning = "אין מספיק נתונים ברמות נמוכה/בינונית/גבוהה כדי לקבוע אם שיעור ההמרה עולה עם רמת ההוצאה.";
  } else if (monotonic) {
    // §יג-2 (approved 28.09.2026): מונחי הטייר בפרוזה בעברית, ⛔ לא
    // שמות אנגליים גולמיים -- אותו תוכן עובדתי, ניסוח בלבד השתנה.
    meaning = "הרצף נמוכה ← בינונית ← גבוהה עולה בהתאם לציפייה הפשוטה שהוצאה גבוהה יותר קשורה להמרה גבוהה יותר; אין לטעון להפתעה.";
  } else {
    meaning = "הרצף נמוכה ← בינונית ← גבוהה אינו עולה בנתונים האלה: הוצאה גבוהה יותר לא הניבה המרה גבוהה יותר — ממצא מפתיע ביחס לציפייה הפשוטה.";
  }

  // O6 (tester finding: "'מה כדאי לעשות' מיותר, עוד לא הוזנו נתונים"):
  // made explicit that this is a historical-data comparison available
  // BEFORE any input, not a response to something the user just did.
  const action = "עוד לפני הזנת נתונים: להשוות את רמת ההוצאה הנוכחית של הארגון לטבלה שלמעלה, ולבחון את החלופות בסימולטור.";
  const caveat = "ההשוואה מתארת קבוצות בנתונים ההיסטוריים ואינה מוכיחה שהזזת תקציב תשנה את ההמרה.";

  return { answer, meaning, action, caveat };
}

function renderChart(tiers) {
  // 12A, 27.09.2026 (tester finding: "לא מבינים מה זה mid, high ו-low
  // -- אין הסבר"): every category label now carries its ₪ range
  // (TIER_LABELS_WITH_RANGE), so the meaning is visible on the chart
  // itself and in the table row headers, not left to a separate
  // legend the reader has to connect back to the bars.
  //
  // Iterates ALL rows the API returned, in the tier_order-ascending
  // order app/insights.py already guarantees (D15) -- not a hardcoded
  // ["Low","Mid","High"] filter. That filter used to silently drop
  // the null-tier "gap (1501-1999)" row from the chart entirely (it
  // only ever appeared in the tier-table this screen removed, per O4)
  // -- IA.md §2.1 requires that row be shown, never dropped, whenever
  // the API actually returns it (today's frozen dataset never does:
  // gap n=0, so this is dormant, not exercised, but real).
  const chartRows = tiers.map((t) => ({
    xHebrew: t.budget_tier ? TIER_LABELS_WITH_RANGE[t.budget_tier] : "gap (1501–1999)",
    xEnglish: t.budget_tier ? TIER_LABELS_EN[t.budget_tier] : "gap (1501-1999)",
    value: t.conversion_rate,
    n_records: t.n_records,
  }));
  // §יג-2 (28.09.2026 DOM-order fix): SVG -> tierSectionCaptions() ->
  // fallback table, all inside charts.js's own single .chart-live
  // wrapper (via `midCaptions`) -- one node, table still glued to the
  // SVG as one component, matching budget.js/followup.js's own shape.
  return charts.renderBarChart({
    data: chartRows,
    title: "שיעור ההמרה לפי רמת הוצאת הפרסום",
    titleEnglish: "Conversion Rate by Ad Budget Level",
    xLabel: "רמת הוצאה חודשית על פרסום",
    // §יב-2 R1 (Codex round, approved by the user 24.09.2026): the
    // axis name itself carries the plain-language definition, not
    // just the statistical term -- the tester's own complaint about
    // this exact chart was "לא מובן בכלל, אין הסבר".
    yLabel: "שיעור המרה — כמה מהלידים הפכו לעסקה (%)",
    formatValue: (v) => (v === null ? "N/A" : format.formatPercent(v, { decimals: 1 })),
    // O2 (tester finding: "לא מבינים מה זה מספר רשומות"): the
    // record-count column that used to live only in the removed
    // tier-table, now folded into the chart's own mandatory fallback
    // table -- one table, not two.
    extraColumn: { label: "מספר רשומות", formatValue: (d) => format.formatNumber(d.n_records) },
    midCaptions: tierSectionCaptions(),
  });
}

// P11A-D8/D9: the screen's own sole h1 -- IA.md §2's own hierarchy
// ("כותרת → אינדקס חמש היכולות → ..."), reusing index.html's own
// app-nav label for this route rather than inventing new text. A tiny
// shared helper so all three render states get it identically, instead
// of tripling the same two lines.
function appendScreenHeading() {
  // G1 (PHASE12A.md §יג-1, approved 28.09.2026): "מה המסך עונה" ואחריו
  // "מה עושים כאן", לפני כל תוכן אחר -- כולל לפני ה-h1 עצמו, ⛔ לא
  // אחריו. גם מזכיר במפורש את שאלת ההמרה לפי תקציב, לא רק את אינדקס
  // היכולות (§יג-1 דורש זאת עבור Overview ספציפית).
  const intro = document.createElement("p");
  intro.className = "screen-intro screen-intro-end";
  intro.textContent = "המסך עונה מה FunnelIQ יכול לעשות עבורכם, ואיך ההמרה משתנה לפי תקציב הפרסום. לחצו על כרטיס לתשובה המתאימה.";
  container.appendChild(intro);

  const heading = document.createElement("h1");
  heading.textContent = "סקירה כללית";
  container.appendChild(heading);
}

function renderSuccess(tiers) {
  container.replaceChildren();
  appendScreenHeading();
  container.appendChild(renderCapabilityIndex());
  // §יג-2 (28.09.2026, DOM-order fix): renderChart() returns ONE
  // .chart-live node -- SVG, tierSectionCaptions() paragraphs (incl.
  // the O4 caption), and the fallback table, all inside it, in that
  // order (see charts.js's `midCaptions`).
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
