"use strict";

// FunnelIQ shared prediction form -- INPUT side (phase 11, checkpoint 4).
// Own controller and local state (P11-D3) -- no state shared with any
// other screen, including P4S (P11-D3/P11-D4: separate controllers,
// separate generation counters, separate prefill).
//
// Checkpoint 4 owns: context-confirmation, prefill-picker, input-summary,
// input-details (12 fields + derived not_closed), the five blocking
// validation rules, clear-form with confirmation, and triggering
// submission itself (IA.md §3.3's own state table places "שליחה" in
// the input flow's state machine). The THREE RESULT PANELS' actual
// rendering (prediction-primary, evidence-badge, OOD banners,
// model-details, summary-recommendation) is checkpoint 5's job -- this
// checkpoint renders only a minimal placeholder proving the mechanism
// (request sent, per-panel success/failure captured) works correctly.
//
// Content sources, all locked (§ד "כלל תיקון מקור"):
//   - field labels/units: DESIGN.md §7.1's own table, verbatim.
//   - context-confirmation text: IA.md §3.3 step 1, verbatim.
//   - the five validation messages: IA.md §3.2 (see validation.js).
//   - source-state labels (תרחיש עצמאי / דוגמה היסטורית / תרחיש שנערך)
//     and the clear-form reset text: IA.md §3.3.1 / DESIGN.md's
//     clear-form-action row, verbatim.
//
// DOM architecture note: the 12 field <input> elements (and the
// derived-field's value node) are built EXACTLY ONCE and never torn
// down/recreated on a later render -- only their .value is set, and
// only for bulk operations (loading an example, clearing the form),
// never on every keystroke. Rebuilding a focused <input>'s ancestor
// tree (e.g. via a blanket container.replaceChildren() on every
// keystroke) detaches it from the document, which blurs it -- losing
// focus after every single character typed. Every OTHER part of the
// screen (prefill picker, summary, blocked-message, results) has no
// typing to protect and is freely rebuilt on each update.

import * as api from "../api.js";
import * as session from "../session.js";
import * as supabasePrefill from "../supabase-prefill.js";
import * as generation from "../generation.js";
import * as status from "../status.js";
import * as format from "../format.js";
import * as facts from "../facts.js";
import { renderSummaryRecommendation } from "../summary-recommendation.js";
import { EDITABLE_FIELDS, deriveNotClosed, validateSharedForm } from "../validation.js";

const FIELD_META = {
  ad_budget: { label: "רמת הוצאת פרסום חודשית", unit: "ש\"ח לחודש" },
  num_leads: { label: "מספר הלידים שנוצרו", unit: "לידים" },
  leads_answered: { label: "לידים שענו לטלפון", unit: "לידים" },
  followup_1: { label: "לידים שנותרו אחרי מעקב 1", unit: "לידים" },
  followup_2: { label: "לידים שנותרו אחרי מעקב 2", unit: "לידים" },
  followup_3: { label: "לידים שנותרו אחרי מעקב 3", unit: "לידים" },
  followup_4: { label: "לידים שנותרו אחרי מעקב 4", unit: "לידים" },
  followup_5: { label: "לידים שנותרו אחרי מעקב 5", unit: "לידים" },
  closed: { label: "עסקאות שנסגרו", unit: "עסקאות" },
  calls_to_closed: { label: "ממוצע שיחות עד סגירה", unit: "שיחות (ממוצע)" },
  calls_to_not_closed: { label: "ממוצע שיחות עד ויתור", unit: "שיחות (ממוצע)" },
  customer_acquisition_cost: { label: "עלות ממוצעת לרכישת לקוח", unit: "ש\"ח ללקוח" },
};
const NOT_CLOSED_META = { label: "לידים שלא הומרו", unit: "לידים" };
const FIELD_ORDER_BEFORE_DERIVED = ["ad_budget", "num_leads", "leads_answered", "followup_1", "followup_2", "followup_3", "followup_4", "followup_5"];
const FIELD_ORDER_AFTER_DERIVED = ["closed", "calls_to_closed", "calls_to_not_closed", "customer_acquisition_cost"];

const CONTEXT_CONFIRMATION_TEXT = "אני מאשר/ת שהלקוח כבר רכש ושמחזור הקמפיין הסתיים.";

const SOURCE_LABELS = {
  independent: "תרחיש עצמאי",
  historical: "דוגמה היסטורית",
  edited: "תרחיש שנערך",
};

// checkpoint 5 -- result panels. IA.md §4, verbatim labels.
const PROPENSITY_BAND_LABELS = {
  below_base: "מתחת לשיעור הבסיס",
  near_base: "סביב שיעור הבסיס",
  above_base: "מעל שיעור הבסיס",
};
// Icon glyphs are this module's own choice. DESIGN.md §3.2/IA.md §10
// require every state badge (ood-banner, evidence-badge,
// calibration-badge, propensity-band-badge) to carry BOTH text and an
// icon, never color alone -- but no specific glyph is locked anywhere
// in the source docs. Plain, directional/neutral unicode symbols.
const PROPENSITY_BAND_ICONS = { below_base: "▼", near_base: "●", above_base: "▲" };

const sharedGen = generation.createGenerationCounter(); // P11-D4: ONE generation for all three predict calls
let prefillGen = 0; // local staleness guard for the example-list fetch only

let container = null;
let nodes = null; // persistent DOM references, built once per show()

function blankValues() {
  const values = {};
  for (const f of EDITABLE_FIELDS) values[f] = null;
  return values;
}

let form = {
  source: "independent", // "independent" | "historical" | "edited"
  values: blankValues(),
  contextConfirmed: false,
  exampleLabel: null, // "דוגמה 3" once a historical/edited example is loaded
};

let prefillState = "idle"; // idle | loading | loaded | error
let prefillRows = [];
let prefillErrorMessage = "";

let submitState = "idle"; // idle | submitting | done
let submitResults = null; // { ltv, upsell, referral } -- each api.js result
let confirmingClear = false;

// ---------------------------------------------------------------------
// session.onSessionEvent -- subscribed ONCE at module top level.
// Mirrors overview.js's own (independently reviewed, four rounds)
// pattern, applied here from the start:
//   - stateCleared: wipes ALL form state (P11-D5) and cancels anything
//     in flight via both generation counters.
//   - epochRaised without stateCleared, while a fetch is in flight
//     (prefill list, or a submission): the in-flight request's
//     eventual response is already discarded by api.js's/
//     supabase-prefill.js's own epoch check -- but nothing would
//     otherwise schedule a replacement, so this screen's own local
//     "busy" flags are reset here too. Already-rendered content (a
//     loaded example, prior results) is left untouched.
// ---------------------------------------------------------------------
session.onSessionEvent(({ epochRaised, stateCleared }) => {
  if (stateCleared) {
    sharedGen.bump();
    prefillGen += 1;
    form = { source: "independent", values: blankValues(), contextConfirmed: false, exampleLabel: null };
    prefillState = "idle";
    prefillRows = [];
    submitState = "idle";
    submitResults = null;
    confirmingClear = false;
    if (container) { container.replaceChildren(); nodes = null; }
    return;
  }
  if (epochRaised) {
    if (prefillState === "loading") { prefillGen += 1; prefillState = "idle"; }
    if (submitState === "submitting") { sharedGen.bump(); submitState = "idle"; }
    if (nodes) updateDynamic();
  }
});

// ---------------------------------------------------------------------
// small DOM helper
// ---------------------------------------------------------------------
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

function buildFieldNode(name) {
  const meta = FIELD_META[name];
  const wrap = el("div", { className: "field" });
  const label = el("label", { for: `field-${name}` });
  label.appendChild(el("span", { className: "field-label-business", text: meta.label }));
  label.appendChild(el("span", { className: "field-label-technical", text: format.ltr(name) }));
  label.appendChild(el("span", { className: "field-label-unit", text: meta.unit }));
  wrap.appendChild(label);

  const input = el("input", {
    id: `field-${name}`,
    type: "number",
    step: "1",
    min: "0",
    required: "required",
  });
  input.addEventListener("focus", () => input.select());
  input.addEventListener("input", () => onFieldInput(name, input.value));
  wrap.appendChild(input);
  return { wrap, input };
}

function buildDerivedFieldNode() {
  const wrap = el("div", { className: "field derived-field" });
  const label = el("label");
  label.appendChild(el("span", { className: "field-label-business", text: NOT_CLOSED_META.label }));
  label.appendChild(el("span", { className: "field-label-technical", text: format.ltr("not_closed") }));
  label.appendChild(el("span", { className: "field-label-unit", text: NOT_CLOSED_META.unit }));
  wrap.appendChild(label);
  const valueEl = el("div", { className: "derived-field-value" });
  wrap.appendChild(valueEl);
  return { wrap, valueEl };
}

/** Built exactly once (per show() after a full reset). Field inputs
 * and the derived-field value node persist across every later update. */
function buildOnce() {
  container.replaceChildren();

  const contextWrap = el("div", { className: "context-confirmation" });
  const contextLabel = el("label");
  const contextCheckbox = el("input", { type: "checkbox" });
  contextCheckbox.addEventListener("change", (e) => {
    // IA.md §9.4: "המונה עולה ב: ... שינוי אישור ההקשר ..." -- listed
    // alongside a field edit and requesting a different example
    // (both already fixed in the previous review round). This
    // specific trigger was missed then; same fix, same reasoning.
    const next = e.target.checked;
    if (next === form.contextConfirmed) { updateDynamic(); return; } // no real change -- nothing to invalidate
    form.contextConfirmed = next;
    sharedGen.bump();
    submitState = "idle";
    submitResults = null;
    updateDynamic();
  });
  contextLabel.appendChild(contextCheckbox);
  contextLabel.appendChild(el("span", { text: CONTEXT_CONFIRMATION_TEXT }));
  contextWrap.appendChild(contextLabel);
  container.appendChild(contextWrap);

  const prefillWrap = el("div", { className: "prefill-picker" });
  prefillWrap.appendChild(el("h3", { text: "טעינת דוגמה היסטורית" }));
  const prefillBody = el("div", { className: "prefill-picker-body" });
  prefillWrap.appendChild(prefillBody);
  container.appendChild(prefillWrap);

  const summaryWrap = el("div", { className: "input-summary" });
  container.appendChild(summaryWrap);

  const detailsEl = el("details", {});
  detailsEl.open = true;
  detailsEl.addEventListener("toggle", () => { /* purely visual; no state to persist across a fresh show() */ });
  detailsEl.appendChild(el("summary", { text: "בדיקה ועריכת נתונים" }));
  const grid = el("div", { className: "field-grid" });
  const fieldInputs = {};
  for (const name of FIELD_ORDER_BEFORE_DERIVED) {
    const { wrap, input } = buildFieldNode(name);
    fieldInputs[name] = input;
    grid.appendChild(wrap);
  }
  const derived = buildDerivedFieldNode();
  grid.appendChild(derived.wrap);
  for (const name of FIELD_ORDER_AFTER_DERIVED) {
    const { wrap, input } = buildFieldNode(name);
    fieldInputs[name] = input;
    grid.appendChild(wrap);
  }
  detailsEl.appendChild(grid);
  container.appendChild(detailsEl);

  const blockedWrap = el("div", { className: "submit-blocked-wrap" });
  container.appendChild(blockedWrap);

  const submitButton = el("button", { type: "button", className: "submit-button", text: "הפקת תחזיות" });
  submitButton.addEventListener("click", submitForm);
  container.appendChild(submitButton);

  const clearWrap = el("div", { className: "clear-form-action" });
  container.appendChild(clearWrap);

  const resultsWrap = el("div", { className: "results-wrap" });
  container.appendChild(resultsWrap);

  nodes = { contextCheckbox, prefillBody, summaryWrap, detailsEl, fieldInputs, derivedValueEl: derived.valueEl, blockedWrap, submitButton, clearWrap, resultsWrap };
}

/** Bulk-sets every field input's .value from form.values -- ONLY for
 * whole-form operations (loading an example, clearing). Never called
 * from a single keystroke's own handler. */
function syncFieldValuesToDom() {
  for (const name of EDITABLE_FIELDS) {
    nodes.fieldInputs[name].value = form.values[name] === null ? "" : String(form.values[name]);
  }
}

function renderPrefillBody() {
  nodes.prefillBody.replaceChildren();
  if (prefillState === "loading") {
    nodes.prefillBody.appendChild(status.loadingElement("טוען דוגמאות…"));
    return;
  }
  if (prefillState === "error") {
    nodes.prefillBody.appendChild(status.errorElement(prefillErrorMessage, { onRetry: loadPrefillList }));
    return;
  }
  if (prefillState === "loaded" && prefillRows.length === 0) {
    nodes.prefillBody.appendChild(status.errorElement("אין כרגע דוגמאות זמינות לטעינה.", { onRetry: loadPrefillList }));
    return;
  }
  if (prefillState === "loaded") {
    const list = el("div", { className: "prefill-picker-list" });
    prefillRows.forEach((row, i) => {
      const button = el("button", { type: "button", text: `דוגמה ${i + 1}` });
      button.addEventListener("click", () => applyExample(row, i + 1));
      list.appendChild(button);
    });
    nodes.prefillBody.appendChild(list);
  }
}

function renderSummary() {
  const filledCount = EDITABLE_FIELDS.filter((f) => form.values[f] !== null && form.values[f] !== undefined).length;
  const notClosed = deriveNotClosed(form.values);
  const sourceText = form.exampleLabel ? `${SOURCE_LABELS[form.source]} (${form.exampleLabel})` : SOURCE_LABELS[form.source];
  // "—" here, NOT "טרם חושב" -- that wording belongs to the derived
  // field's own standalone display (IA.md §3.1: "not_closed מוצג כ-
  // 'טרם חושב'"). input-summary's own literal reset text is the em
  // dash (DESIGN.md's clear-form-action row: "לא הומרו: —").
  const notClosedText = notClosed === null ? "—" : format.formatNumber(notClosed);
  nodes.summaryWrap.replaceChildren(el("span", { text: `${sourceText} · ${filledCount}/12 · לא הומרו: ${notClosedText}` }));
}

function renderDerivedValue() {
  const notClosed = deriveNotClosed(form.values);
  nodes.derivedValueEl.classList.remove("derived-field-error");
  if (notClosed === null) {
    nodes.derivedValueEl.textContent = "טרם חושב";
    return;
  }
  nodes.derivedValueEl.textContent = `${format.ltr(`followup_5 (${form.values.followup_5}) − closed (${form.values.closed})`)} = ${format.formatNumber(notClosed)}`;
  if (notClosed < 0) nodes.derivedValueEl.classList.add("derived-field-error");
}

function renderBlockedAndSubmit(violations, needsConfirmation) {
  nodes.blockedWrap.replaceChildren();
  for (const v of violations) {
    nodes.blockedWrap.appendChild(el("p", { className: "submit-blocked-message", role: "alert", text: v.message }));
  }
  if (violations.length === 0 && needsConfirmation) {
    nodes.blockedWrap.appendChild(el("p", { className: "submit-blocked-message", role: "alert", text: "יש לאשר את ההקשר לפני שליחה." }));
  }
  nodes.submitButton.disabled = violations.length > 0 || needsConfirmation || submitState === "submitting";
}

function renderClearFormAction() {
  nodes.clearWrap.replaceChildren();
  const hasSomethingToLose = form.source !== "independent" ||
    EDITABLE_FIELDS.some((f) => form.values[f] !== null) ||
    form.contextConfirmed || submitState !== "idle";

  const button = el("button", { type: "button", text: "נקה טופס" });
  button.addEventListener("click", () => {
    if (!hasSomethingToLose) { clearForm(); return; }
    confirmingClear = true;
    updateDynamic();
  });
  nodes.clearWrap.appendChild(button);

  if (confirmingClear) {
    const confirmWrap = el("div", { className: "clear-form-confirm", role: "alert" });
    confirmWrap.appendChild(el("p", { text: "לנקות את הטופס? כל הנתונים, הדוגמה והתוצאות יימחקו." }));
    const confirmButton = el("button", { type: "button", text: "אישור" });
    confirmButton.addEventListener("click", () => { confirmingClear = false; clearForm(); });
    const cancelButton = el("button", { type: "button", text: "ביטול" });
    cancelButton.addEventListener("click", () => { confirmingClear = false; updateDynamic(); });
    confirmWrap.appendChild(confirmButton);
    confirmWrap.appendChild(cancelButton);
    nodes.clearWrap.appendChild(confirmWrap);
  }
}

// ---------------------------------------------------------------------
// Checkpoint 5 -- the three result panels (P2/P3/P4).
//
// Content sources, all locked unless a comment says otherwise (§ד "כלל
// תיקון מקור"):
//   - panel layer content (primary/range/disclaimer/decision-limit):
//     IA.md §3.4, verbatim.
//   - the D9 four-layer summary-recommendation text (answer/meaning/
//     action/caveat) for the SUCCESS, in-domain state: DESIGN.md §6.1's
//     own matrix row for P2/P3/P4, verbatim, with only the {X}/{Y}/{Z}/
//     {N} numeric placeholders filled from the live response. DESIGN's
//     own action/caveat sentences already embed every branch §6.1א's
//     transition table allows (calibrated/uncalibrated,
//     above_base/near_base/below_base) as internal "אם...אחרת..."
//     clauses -- so ONE fixed sentence per layer covers every non-OOD
//     state without this module branching on calibration_status or
//     propensity_band for the TEXT itself (only for which badges show).
//   - the OOD state's four D9 layers: NOT locked anywhere -- IA.md/
//     DESIGN.md state only constraints for this state ("no number, no
//     segmentation action"), never exact sentences. This module's own
//     composition, flagged inline at each panel below. The caveat layer
//     in that branch reuses the SAME locked success-state sentence,
//     since P2's already explicitly covers OOD ("ב-OOD אין תחזית") and
//     P3/P4's already covers the uncalibrated case the same way calibr-
//     ation does.
//   - field→component mapping (what goes in model-details vs. inline):
//     DESIGN.md §5.1-§5.3, matched field-for-field against the response.
//   - badge display words ("מכויל"/"לא מכויל", "תמיכה חלקית בנתונים")
//     and icon glyphs: this module's own choice -- the LOCKED vocabulary
//     is the underlying token (calibrated/uncalibrated/low), not a
//     specific display string or icon.
// ---------------------------------------------------------------------

// Source contradiction, flagged and resolved by explicit user decision
// (not a silent frontend workaround, per CLAUDE.md's own source-fix
// rule): IA.md's state table promises "ניסיון חוזר" on a per-panel
// prediction failure; DESIGN.md §2.1's parallel row for this same
// screen omits it (unlike every other row in that table). Resolved:
// a failed panel's retry button re-submits ALL THREE predictions
// (submitForm(), the same action as the main button) rather than
// retrying only that one model's own request.
function panelFailureMessage(result) {
  if (result.reason === "unavailable") return "השירות אינו זמין כרגע. נסו לשלוח את הטופס שוב.";
  if (result.reason === "network") return "שגיאת רשת. נסו לשלוח את הטופס שוב.";
  if (result.reason === "auth") return "פג תוקף ההתחברות.";
  return "אירעה שגיאה. נסו לשלוח את הטופס שוב.";
}

/** IA.md §9.2: "בפאנל OOD: 'אין מספיק נתונים לחיזוי אמין' + הסיבה
 * הקונקרטית (איזה שדה, מחוץ לאיזה גבול) + בלי מספר." The concrete
 * per-field reason line's exact wording beyond the server's own
 * `message` is this module's own composition. */
function buildOodBanner(warnings) {
  const banner = el("div", { className: "ood-banner", role: "alert" });
  banner.appendChild(el("p", { className: "ood-banner-title" }, [
    el("span", { className: "badge-icon", text: "⛔" }),
    el("span", { text: "אין מספיק נתונים לחיזוי אמין" }),
  ]));
  for (const w of warnings.filter((x) => x.code === "ood_feature_out_of_range")) {
    const meta = FIELD_META[w.feature];
    const featureLabel = meta ? meta.label : w.feature;
    banner.appendChild(el("p", {
      className: "ood-banner-reason",
      text: `${w.message} — ${featureLabel} (${format.ltr(w.feature)}): ${format.ltr(format.formatNumber(w.value))}, טווח מאומן: ${format.ltr(`${format.formatNumber(w.min)}–${format.formatNumber(w.max)}`)}`,
    }));
  }
  return banner;
}

/** IA.md §5: evidence_level=null -- "המסך אינו מציג דבר". Only "low"
 * renders anything, carrying the UnobservedBudgetWarning's own message
 * (DESIGN.md §1.1). */
function buildEvidenceBadge(evidenceLevel, warnings) {
  if (evidenceLevel !== "low") return null;
  const unobserved = warnings.find((w) => w.code === "unobserved_budget_level");
  const badge = el("div", { className: "evidence-badge evidence-low" }, [
    el("span", { className: "badge-icon", text: "⚠" }),
    el("span", { text: "תמיכה חלקית בנתונים" }), // IA.md's own phrase: "מוצגים עם תמיכה חלקית"
  ]);
  if (unobserved) badge.appendChild(el("p", { className: "evidence-badge-message", text: unobserved.message }));
  return badge;
}

function buildCalibrationBadge(calibrationStatus) {
  const label = calibrationStatus === "calibrated" ? "מכויל" : "לא מכויל";
  const icon = calibrationStatus === "calibrated" ? "✓" : "⚠";
  return el("div", { className: `calibration-badge ${calibrationStatus}` }, [
    el("span", { className: "badge-icon", text: icon }),
    el("span", { text: label }),
  ]);
}

function buildBandBadge(band) {
  return el("div", { className: `propensity-band-badge ${band}` }, [
    el("span", { className: "badge-icon", text: PROPENSITY_BAND_ICONS[band] }),
    el("span", { text: PROPENSITY_BAND_LABELS[band] }),
  ]);
}

function buildBaseRateLine(eventProbability, baseRate) {
  const diffPoints = (eventProbability - baseRate) * 100;
  const direction = diffPoints > 0 ? "מעל" : diffPoints < 0 ? "מתחת ל" : "בדיוק על";
  const magnitude = format.formatNumber(Math.abs(diffPoints), { decimals: 2 });
  return el("div", { className: "base-rate-line", text: `שיעור הבסיס: ${format.formatPercent(baseRate)} (${magnitude} נקודות ${direction})` });
}

function buildModelDetails(rows, extraNote) {
  const details = el("details", { className: "model-details" });
  details.appendChild(el("summary", { text: "פרטי המודל" }));
  const dl = el("dl", {});
  for (const [label, value] of rows) {
    dl.appendChild(el("dt", { text: label }));
    dl.appendChild(el("dd", { text: value }));
  }
  details.appendChild(dl);
  if (extraNote) details.appendChild(el("p", { className: "model-details-note", text: extraNote }));
  return details;
}

function p2DetailRows(d) {
  return [
    ["גרסת מודל", format.ltr(d.model_version)],
    ["אלגוריתם", format.ltr(d.model_algorithm)],
    ["שיטת אינטרוול", format.ltr(d.interval_method)],
    ["כיסוי נומינלי", format.formatPercent(d.interval_details.nominal_coverage)],
    ["כיסוי נמדד", format.formatPercent(d.interval_details.measured_coverage)],
    ["MAE (CV)", format.formatNumber(d.metrics.cv.mean_mae, { decimals: 2 })],
    ["RMSE (CV)", format.formatNumber(d.metrics.cv.mean_rmse, { decimals: 2 })],
    ["R² (CV)", format.formatNumber(d.metrics.cv.mean_r2, { decimals: 3 })],
    ["MAE (Holdout)", format.formatNumber(d.metrics.holdout.mae, { decimals: 2 })],
    ["RMSE (Holdout)", format.formatNumber(d.metrics.holdout.rmse, { decimals: 2 })],
    ["R² (Holdout)", format.formatNumber(d.metrics.holdout.r2, { decimals: 3 })],
  ];
}

// Shared by P3 and P4 -- ClassificationMetrics (app/schemas.py) is the
// SAME schema for both. Deliberately carries only the fields the
// contract actually has: roc_auc/pr_auc/brier/log_loss -- B32's other
// four metrics (Accuracy/Precision/Recall/F1) are never fetched, so
// they can never appear here (IA.md §3.4: "B32 אינו נענה בממשק כלל").
function p3p4DetailRows(d) {
  return [
    ["גרסת מודל", format.ltr(d.model_version)],
    ["אלגוריתם", format.ltr(d.model_algorithm)],
    ["שיטת כיול", format.ltr(d.calibration_method)],
    ["ROC-AUC (CV)", format.formatNumber(d.metrics.cv.mean_roc_auc, { decimals: 3 })],
    ["PR-AUC (CV)", format.formatNumber(d.metrics.cv.mean_pr_auc, { decimals: 3 })],
    ["Brier (CV)", format.formatNumber(d.metrics.cv.mean_brier, { decimals: 3 })],
    ["Log loss (CV)", format.formatNumber(d.metrics.cv.mean_log_loss, { decimals: 3 })],
    ["ROC-AUC (Holdout)", format.formatNumber(d.metrics.holdout.roc_auc, { decimals: 3 })],
    ["PR-AUC (Holdout)", format.formatNumber(d.metrics.holdout.pr_auc, { decimals: 3 })],
    ["Brier (Holdout)", format.formatNumber(d.metrics.holdout.brier, { decimals: 3 })],
    ["Log loss (Holdout)", format.formatNumber(d.metrics.holdout.log_loss, { decimals: 3 })],
  ];
}

function buildP2Panel(result) {
  const panel = el("div", { className: "prediction-panel prediction-panel-p2" });
  panel.appendChild(el("h3", { text: "P2 — משך חיים צפוי" }));
  if (!result.ok) {
    panel.appendChild(status.errorElement(panelFailureMessage(result), { onRetry: submitForm }));
    return panel;
  }
  const d = result.data;
  const evidenceBadge = buildEvidenceBadge(d.evidence_level, d.warnings);
  if (evidenceBadge) panel.appendChild(evidenceBadge);

  if (!d.in_training_domain) {
    panel.appendChild(buildOodBanner(d.warnings));
    panel.appendChild(renderSummaryRecommendation({
      // OOD state -- this module's own composition (see header comment).
      answer: "אין תחזית — הקלט הנוכחי מחוץ לתחום שעליו אומן מודל ה-LTV",
      meaning: "המודל יודע להעריך אורך חיים רק עבור קלט בטווחים שראה באימון; קלט חריג אינו ניתן להערכה אמינה",
      action: "יש לבדוק את השדות המסומנים למטה מול הטווח המאומן, לתקן במידת הצורך ולשלוח שוב",
      caveat: "זהו טווח אי־ודאות, לא הבטחה. ב־OOD אין תחזית; בתמיכה חלקית אין החלטת פילוח לפי המודל בלבד",
    }));
    panel.appendChild(buildModelDetails(p2DetailRows(d)));
    return panel;
  }

  const rounded = Math.round(d.point_estimate);
  const lower = Math.round(d.lower_bound);
  const upper = Math.round(d.upper_bound);
  panel.appendChild(el("p", { className: "prediction-primary", text: `תחזית: ${format.formatNumber(rounded)} חודשים` }));
  panel.appendChild(el("p", { className: "prediction-range", text: `טווח חיזוי משוער: ${format.formatNumber(lower)}–${format.formatNumber(upper)} חודשים` }));

  // P11-D15: hidden ALONE on facts.json load failure or a
  // model_versions.P2 mismatch against this live response's own
  // model_version -- never affects the prediction above.
  const leverage = facts.getLtvLeverage(d.model_version);
  if (leverage && leverage.dominant_feature) {
    const featureMeta = FIELD_META[leverage.dominant_feature];
    const featureLabel = featureMeta ? featureMeta.label : leverage.dominant_feature;
    panel.appendChild(el("p", {
      className: "ltv-leverage-tip",
      text: `לפי שלושת המודלים שנבחנו, הפיצ'ר המשפיע ביותר על אורך חיי הלקוח הוא ${featureLabel} (${format.ltr(leverage.dominant_feature)}).`,
    }));
    panel.appendChild(el("p", {
      className: "model-disclaimer",
      text: "feature importance מתאר על מה המודל נשען, ואינו מוכיח סיבתיות; שינוי הפיצ'ר אינו מבטיח שינוי בתוצאה.",
    }));
  }

  panel.appendChild(renderSummaryRecommendation({
    answer: `תחזית: ${format.formatNumber(rounded)} חודשים, טווח: ${format.formatNumber(lower)}–${format.formatNumber(upper)} חודשים`,
    meaning: "הערכה לאורך החיים הכולל של לקוח שנרכש בקמפיין שהסתיים. במודלים שאומנו על הנתונים ההיסטוריים, מספר השיחות הממוצע עד סגירה היה האות החזק ביותר, אך אינו מוכיח שיותר שיחות מאריכות קשר",
    action: "כשהקלט בתחום ואינו מסומן בתמיכה חלקית, להשתמש באומדן בזהירות לתכנון ופילוח; לבחון שינוי במדיניות השיחות רק בניסוי שמודד שימור בפועל",
    caveat: "זהו טווח אי־ודאות, לא הבטחה. ב־OOD אין תחזית; בתמיכה חלקית אין החלטת פילוח לפי המודל בלבד",
  }));

  panel.appendChild(buildModelDetails(p2DetailRows(d)));
  return panel;
}

function buildP3Panel(result) {
  const panel = el("div", { className: "prediction-panel prediction-panel-p3" });
  panel.appendChild(el("h3", { text: "P3 — נטייה לאפסייל" }));
  if (!result.ok) {
    panel.appendChild(status.errorElement(panelFailureMessage(result), { onRetry: submitForm }));
    return panel;
  }
  const d = result.data;
  const evidenceBadge = buildEvidenceBadge(d.evidence_level, d.warnings);
  if (evidenceBadge) panel.appendChild(evidenceBadge);

  if (!d.in_training_domain) {
    panel.appendChild(buildOodBanner(d.warnings));
    panel.appendChild(renderSummaryRecommendation({
      // OOD state -- this module's own composition (see header comment).
      answer: "אין תוצאה — הקלט הנוכחי מחוץ לתחום שעליו אומן המודל",
      meaning: "המודל יודע להעריך נטייה לאפסייל רק עבור קלט בטווחים שראה באימון; קלט חריג אינו ניתן להערכה אמינה",
      action: "יש לבדוק את השדות המסומנים למטה מול הטווח המאומן, לתקן במידת הצורך ולשלוח שוב",
      caveat: "כשהתוצאה מכוילת, זהו אומדן הסתברותי מנתוני סוף קמפיין; אם אינה מכוילת, אין לפרש אותה כהסתברות ואין לפעול לפיה. אין הבטחה או השפעה סיבתית",
    }));
    panel.appendChild(buildModelDetails(p3p4DetailRows(d), "מגבלה מדווחת: עקומת הכיול אינה מונוטונית באזור האמצע"));
    return panel;
  }

  panel.appendChild(buildBandBadge(d.propensity_band));
  panel.appendChild(buildBaseRateLine(d.event_probability, d.base_rate));
  panel.appendChild(buildCalibrationBadge(d.calibration_status));

  const pct = format.formatPercent(d.event_probability);
  panel.appendChild(el("p", { className: "prediction-primary", text: `נטייה לאפסייל: ${pct}` }));

  if (d.calibration_status === "uncalibrated") {
    panel.appendChild(el("p", { className: "model-disclaimer", text: "הציון אינו מכויל; אין לפרש אותו כהסתברות ואין לפעול לפיו." }));
  }

  const diffPoints = (d.event_probability - d.base_rate) * 100;
  const direction = diffPoints > 0 ? "מעל" : diffPoints < 0 ? "מתחת ל" : "בדיוק על";
  panel.appendChild(renderSummaryRecommendation({
    answer: `נטייה לאפסייל: ${pct}, ${format.formatNumber(Math.abs(diffPoints), { decimals: 2 })} נקודות ${direction} שיעור הבסיס`,
    meaning: "התוצאה מציבה את התרחיש מעל, סביב או מתחת לשיעור האפסייל שנמדד באוכלוסיית האימון",
    action: "רק כשהקלט בתחום, התוצאה מכוילת, אין סימון תמיכה חלקית והנטייה מעל הבסיס, אפשר לשקול פנייה אחרי בדיקה ידנית. בכל מצב אחר אין פעולה מיוחדת לפי המודל",
    caveat: "כשהתוצאה מכוילת, זהו אומדן הסתברותי מנתוני סוף קמפיין; אם אינה מכוילת, אין לפרש אותה כהסתברות ואין לפעול לפיה. אין הבטחה או השפעה סיבתית",
  }));

  panel.appendChild(buildModelDetails(p3p4DetailRows(d), "מגבלה מדווחת: עקומת הכיול אינה מונוטונית באזור האמצע"));
  return panel;
}

function buildP4Panel(result) {
  const panel = el("div", { className: "prediction-panel prediction-panel-p4" });
  panel.appendChild(el("h3", { text: "P4 — נטייה להפניה" }));
  if (!result.ok) {
    panel.appendChild(status.errorElement(panelFailureMessage(result), { onRetry: submitForm }));
    return panel;
  }
  const d = result.data;
  // IA.md §3.4 P4 "הסתייגות גלויה" -- unconditional, shown in every
  // state (unlike the "מגבלת החלטה גלויה" caveat below, which is
  // conditional on calibration_status).
  panel.appendChild(el("p", {
    className: "model-disclaimer",
    text: "התחזית מעריכה את הסיכוי שהלקוח יפנה לקוחות נוספים. ציון לקוח-על, שמשלב הישארות, רכישה נוספת והפניה, מוצג במסך נפרד.",
  }));

  const evidenceBadge = buildEvidenceBadge(d.evidence_level, d.warnings);
  if (evidenceBadge) panel.appendChild(evidenceBadge);

  if (!d.in_training_domain) {
    panel.appendChild(buildOodBanner(d.warnings));
    panel.appendChild(renderSummaryRecommendation({
      // OOD state -- this module's own composition (see header comment).
      answer: "אין תוצאה — הקלט הנוכחי מחוץ לתחום שעליו אומן המודל",
      meaning: "המודל יודע להעריך נטייה להפניה רק עבור קלט בטווחים שראה באימון; קלט חריג אינו ניתן להערכה אמינה",
      action: "יש לבדוק את השדות המסומנים למטה מול הטווח המאומן, לתקן במידת הצורך ולשלוח שוב",
      caveat: "אם התוצאה אינה מכוילת, אין לפרש אותה כהסתברות ואין לפעול לפיה. גם אומדן מכויל אינו הבטחה או השפעה סיבתית; זהו חיזוי הפניה בלבד, לא ציון לקוח-על",
    }));
    panel.appendChild(buildModelDetails(p3p4DetailRows(d), "עקומת הכיול המלאה מתועדת ב-REPORT.md."));
    return panel;
  }

  panel.appendChild(buildBandBadge(d.propensity_band));
  panel.appendChild(buildBaseRateLine(d.event_probability, d.base_rate));
  panel.appendChild(buildCalibrationBadge(d.calibration_status));

  const pct = format.formatPercent(d.event_probability);
  panel.appendChild(el("p", { className: "prediction-primary", text: `נטייה להפניה: ${pct}` }));

  if (d.calibration_status === "uncalibrated") {
    panel.appendChild(el("p", { className: "model-disclaimer", text: "הציון אינו מכויל; אין לפרש אותו כהסתברות ואין לפעול לפיו." }));
  }

  // DESIGN.md §6.1's own template is "..., מול שיעור הבסיס שחזר" --
  // this module reads that as "compared against the base_rate the
  // response carried" and renders the actual figure for clarity; the
  // template itself does not spell out a placeholder for it the way
  // P3's "{N} נקודות" does. Composition choice, flagged.
  panel.appendChild(renderSummaryRecommendation({
    answer: `נטייה להפניה: ${pct}, מול שיעור הבסיס שחזר: ${format.formatPercent(d.base_rate)}`,
    meaning: "התוצאה מציבה את התרחיש מעל, סביב או מתחת לשיעור ההפניה שנמדד באוכלוסיית האימון. ציון לקוח-על מוצג במסך נפרד",
    action: "רק כשהקלט בתחום, התוצאה מכוילת, אין סימון תמיכה חלקית והנטייה מעל הבסיס, אפשר לשקול בקשת הפניה אחרי בדיקה ידנית. בכל מצב אחר אין פעולה מיוחדת לפי המודל",
    caveat: "אם התוצאה אינה מכוילת, אין לפרש אותה כהסתברות ואין לפעול לפיה. גם אומדן מכויל אינו הבטחה או השפעה סיבתית; זהו חיזוי הפניה בלבד, לא ציון לקוח-על",
  }));

  panel.appendChild(buildModelDetails(p3p4DetailRows(d), "עקומת הכיול המלאה מתועדת ב-REPORT.md."));
  return panel;
}

function renderResults() {
  nodes.resultsWrap.replaceChildren();
  if (submitState === "idle") return;
  if (submitState === "submitting") {
    nodes.resultsWrap.appendChild(status.loadingElement("שולח לחיזוי…"));
    return;
  }
  // Per-panel independence (IA.md §3.3 step 5 / DESIGN.md §2.1): each
  // panel renders from its OWN api.js result -- a failure or OOD state
  // in one never removes or blocks the other two.
  nodes.resultsWrap.appendChild(buildP2Panel(submitResults.ltv));
  nodes.resultsWrap.appendChild(buildP3Panel(submitResults.upsell));
  nodes.resultsWrap.appendChild(buildP4Panel(submitResults.referral));
}

/** Refreshes every part of the screen EXCEPT the field <input>
 * elements' own values (those are set only by syncFieldValuesToDom(),
 * called separately for bulk operations) -- safe to call after every
 * keystroke without disturbing focus. */
function updateDynamic() {
  if (!nodes) return;
  nodes.contextCheckbox.checked = form.contextConfirmed;
  renderPrefillBody();
  renderSummary();
  renderDerivedValue();
  const violations = validateSharedForm(form.values);
  const needsConfirmation = form.source !== "historical" && !form.contextConfirmed;
  renderBlockedAndSubmit(violations, needsConfirmation);
  renderClearFormAction();
  renderResults();
}

// ---------------------------------------------------------------------
// Actions
// ---------------------------------------------------------------------

function onFieldInput(name, rawValue) {
  const value = rawValue === "" ? null : Number(rawValue);
  form.values[name] = value;

  // IA.md §9.4: the generation counter rises on "שינוי של אחד מ-12
  // השדות הנערכים" -- UNCONDITIONALLY, for every edit, regardless of
  // the form's current source. Fixed after an independent review found
  // this was wrongly gated behind `source === "historical"`: in the
  // far more common independent/edited cases, editing a field while a
  // submission was in flight never invalidated it (a stale response
  // for the OLD input could still render), and editing after a
  // successful submission left the old result on screen indefinitely.
  sharedGen.bump();
  submitState = "idle";
  submitResults = null;

  if (form.source === "historical") {
    // Only the SOURCE-LABEL transition itself is conditional on having
    // come from "historical" -- IA.md §3.3: first edit of a loaded
    // example turns it into "תרחיש שנערך" and re-requires confirmation.
    form.source = "edited";
    form.contextConfirmed = false;
  }
  updateDynamic(); // never touches the input elements' own .value
}

function applyExample(row, index) {
  for (const f of EDITABLE_FIELDS) form.values[f] = row[f];
  form.source = "historical";
  form.exampleLabel = `דוגמה ${index}`;
  form.contextConfirmed = false;
  sharedGen.bump(); // cancels any prior in-flight/rendered result
  submitState = "idle";
  submitResults = null;
  syncFieldValuesToDom();
  nodes.detailsEl.open = false; // IA.md §3.3: closed by default after a valid example loads
  updateDynamic();
}

function clearForm() {
  sharedGen.bump();
  form = { source: "independent", values: blankValues(), contextConfirmed: false, exampleLabel: null };
  submitState = "idle";
  submitResults = null;
  syncFieldValuesToDom();
  nodes.detailsEl.open = true; // IA.md §3.3.1: "input-details נפתח מחדש"
  updateDynamic();
}

async function submitForm() {
  const violations = validateSharedForm(form.values);
  const needsConfirmation = form.source !== "historical" && !form.contextConfirmed;
  if (violations.length > 0 || needsConfirmation) return;

  submitState = "submitting";
  const myGen = sharedGen.bump();
  updateDynamic();

  const payload = { ...form.values, not_closed: deriveNotClosed(form.values) };
  // facts.init() rides along so P2's optional leverage tip (P11-D15)
  // has business_facts.json ready by the time results render -- it is
  // idempotent and never affects the three predictions themselves.
  const [ltv, upsell, referral] = await Promise.all([
    api.predictLtv(payload),
    api.predictUpsell(payload),
    api.predictReferral(payload),
    facts.init(),
  ]);

  if (!sharedGen.isCurrent(myGen)) return; // superseded (edit/clear/new example/session change) while in flight

  // Same "not a real attempt" treatment loadPrefillList() and every
  // load()-screen already give "blocked"/"stale" (api.js's own contract:
  // "blocked" = businessBlocked was true, refused before sending --
  // reachable here specifically because a mid-session 503/500 re-verify
  // leaves an already-shown shell/screen untouched per app.js, so the
  // form stays fully interactive while submissions are gated; "stale" is
  // normally already caught by the isCurrent(myGen) check above via the
  // proactive epochRaised listener, this is a defensive second layer).
  // Unlike those screens' load(), submitForm() is user-triggered, not
  // re-invoked on route re-entry, so updateDynamic() here is required to
  // clear the "שולח..." spinner and re-enable the button -- otherwise
  // nothing else would ever do it.
  if ([ltv, upsell, referral].some((r) => !r.ok && (r.reason === "blocked" || r.reason === "stale"))) {
    submitState = "idle";
    updateDynamic();
    return;
  }

  submitState = "done";
  submitResults = { ltv, upsell, referral };
  updateDynamic();
}

async function loadPrefillList() {
  prefillState = "loading";
  const myGen = ++prefillGen;
  if (nodes) updateDynamic();

  const result = await supabasePrefill.fetchSharedFormPrefill();
  if (myGen !== prefillGen) return; // superseded

  if (!result.ok) {
    if (result.reason === "blocked" || result.reason === "stale") {
      prefillState = "idle";
      return;
    }
    prefillState = "error";
    prefillErrorMessage = "שגיאה בטעינת הדוגמאות. נסו שוב.";
    if (nodes) updateDynamic();
    return;
  }
  prefillState = "loaded";
  prefillRows = result.data;
  if (nodes) updateDynamic();
}

/** Called by app.js's router every time the predict route is shown. */
export function show(screenContainer) {
  container = screenContainer;
  if (!nodes) {
    buildOnce();
    syncFieldValuesToDom();
    updateDynamic();
  }
  if (prefillState === "idle") {
    loadPrefillList();
  }
}
