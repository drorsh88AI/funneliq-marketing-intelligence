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
    form.contextConfirmed = e.target.checked;
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

  const resultsWrap = el("div", { className: "results-placeholder-wrap" });
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

function renderResults() {
  nodes.resultsWrap.replaceChildren();
  if (submitState === "idle") return;
  if (submitState === "submitting") {
    nodes.resultsWrap.appendChild(status.loadingElement("שולח לחיזוי…"));
    return;
  }
  // Checkpoint 5 replaces this with the real three prediction-panel
  // components. This checkpoint only proves the request mechanism --
  // per-panel success/failure genuinely captured and independent
  // (IA.md §3.3 step 5).
  for (const [key, labelHe] of [["ltv", "P2"], ["upsell", "P3"], ["referral", "P4"]]) {
    const r = submitResults[key];
    const row = el("div", { className: "results-placeholder-row" });
    row.appendChild(el("strong", { text: `${labelHe}: ` }));
    row.appendChild(el("span", { text: r.ok ? "התקבלה תשובה" : `כשל (${r.reason})` }));
    nodes.resultsWrap.appendChild(row);
  }
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
  const [ltv, upsell, referral] = await Promise.all([
    api.predictLtv(payload),
    api.predictUpsell(payload),
    api.predictReferral(payload),
  ]);

  if (!sharedGen.isCurrent(myGen)) return; // superseded (edit/clear/new example/session change) while in flight

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
