"use strict";

// FunnelIQ P4S -- early super-customer score (phase 11, checkpoint 6,
// IA.md §3א). Own controller and local state (P11-D3) -- ⛔ no mutable
// state shared with the shared prediction form (predict.js), including
// its own SEPARATE generation counter (P11-D4/P11-D3א) and its own
// prefill picker instance (IA.md §3א.3: "בורר נפרד").
//
// Structurally different from predict.js by design (IA.md §3א.3, the
// deliberate inversion from §3.3): manual entry is the PRIMARY, complete
// path here -- prefill is an aid, never a precondition for submission.
//
// Content sources, all locked (§ד "כלל תיקון מקור"):
//   - the 4 field labels/units: DESIGN.md §7.2's own table, verbatim.
//     ⚠ followup_1's label here ("לידים שנותרו אחרי המעקב הראשון") is
//     DELIBERATELY DIFFERENT TEXT from predict.js's own §7.1 label
//     ("לידים שנותרו אחרי מעקב 1") for the SAME technical field name --
//     DESIGN.md §7 is explicit that the two rows must never be merged,
//     since the measurement context/timing differs completely.
//   - context-confirmation text: IA.md §3א.3, verbatim.
//   - the input-summary's literal state strings (IA.md §3א.3.1's own
//     quoted examples: "תרחיש עצמאי · 0/4", "דוגמה היסטורית · 4/4",
//     "תרחיש שנערך · 4/4 · 2 שדות שונו") -- reproduced exactly, unlike
//     predict.js's own summary line (composed more freely there because
//     IA.md §3.3.1 gave no equally literal quoted string to match).
//   - the panel's own layers (IA.md §3א.4): primary/secondary/visible
//     definitions/visible disclaimer/business-context-card/<details>.
//   - the D9 four-layer summary-recommendation for the SUCCESS, in-domain
//     state: DESIGN.md §6.1's own matrix row for P4S, verbatim, with
//     only the placeholders filled from the live response + the fixed
//     business_facts.json profile.
//   - the business-context-card's own mandatory sentence: IA.md §3א.6,
//     verbatim, 1-decimal percentages (matches that exact locked text's
//     own rounding -- "16.7%"/"33.6%"/"31.1%", NOT the 2-decimal default
//     elsewhere in this app; the "הערכים" list right below it in IA.md
//     gives the same underlying numbers at 2dp purely for documentation/
//     audit, not as a second literal UI string).
//   - the OOD state's four D9 layers and the plain-language rendering of
//     target_definition/population_definition: NOT locked anywhere --
//     IA.md only requires "בשפה פשוטה" for the definitions and states
//     only structural constraints for OOD ("no score"). This module's
//     own composition, flagged inline.

import * as api from "../api.js";
import * as session from "../session.js";
import * as supabasePrefill from "../supabase-prefill.js";
import * as generation from "../generation.js";
import * as status from "../status.js";
import * as format from "../format.js";
import * as facts from "../facts.js";
import { renderSummaryRecommendation } from "../summary-recommendation.js";
import { SUPER_CUSTOMER_FIELDS, validateSuperCustomerForm } from "../validation.js";

const FIELD_META = {
  ad_budget: { label: "רמת הוצאת פרסום חודשית", unit: "ש\"ח לחודש" },
  num_leads: { label: "מספר הלידים שנוצרו", unit: "לידים" },
  leads_answered: { label: "לידים שענו לטלפון", unit: "לידים" },
  // DESIGN.md §7.2's own label for this row -- distinct from §7.1's
  // "לידים שנותרו אחרי מעקב 1" for the identical technical field name.
  followup_1: { label: "לידים שנותרו אחרי המעקב הראשון", unit: "לידים" },
};

const CONTEXT_CONFIRMATION_TEXT = "אני מאשר/ת שהרכישה ידועה, מעקב 1 הושלם וחלון הגיוס החודשי נסגר.";

const SOURCE_LABELS = {
  independent: "תרחיש עצמאי",
  historical: "דוגמה היסטורית",
  edited: "תרחיש שנערך",
};

const PROPENSITY_BAND_LABELS = {
  below_base: "מתחת לשיעור הבסיס",
  near_base: "סביב שיעור הבסיס",
  above_base: "מעל שיעור הבסיס",
};
const PROPENSITY_BAND_ICONS = { below_base: "▼", near_base: "●", above_base: "▲" };

// This module's own plain-language rendering of the two Literal
// definition strings the live response carries (IA.md §3א.4: "הגדרות
// גלויות... בשפה פשוטה" -- no exact wording is locked). Keyed by the
// literal value itself so an unrecognized future contract value falls
// back to the raw string rather than silently mistranslating it.
// Review-round finding, confirmed against SPEC.md's own field table
// (ltv_months is listed there as an OBSERVED, customer-level historical
// outcome column, not a live model output): the original wording used
// "משך החיים הצפוי" ("his/her EXPECTED lifetime"), forward-looking
// language that risked reading as a restatement of P2's own live
// prediction. ltv_months>=34 here is a threshold on a HISTORICAL,
// already-observed value used only to build this model's training
// label -- unrelated to what P2 forecasts for a NEW scenario. Reworded
// to a plain historical-observation frame, with no "expected"/"צפוי".
const TARGET_DEFINITION_TEXT = {
  "referred=Yes AND upsell=1 AND ltv_months>=34":
    "לקוח-על מוגדר, בנתוני העבר, כרוכש שגם הפנה לקוחות נוספים, גם רכש שוב (אפסייל), וגם משך החיים שנצפה אצלו בפועל הגיע ל-34 חודשים ומעלה. זו הגדרה היסטורית לתיוג, לא תחזית.",
};
const POPULATION_DEFINITION_TEXT = {
  "purchased=1": "המודל אומן על כלל הלקוחות שביצעו רכישה.",
};

const sharedGen = generation.createGenerationCounter(); // P11-D4: fully independent of predict.js's own instance
let prefillGen = 0;

let container = null;
let nodes = null;

function blankValues() {
  const values = {};
  for (const f of SUPER_CUSTOMER_FIELDS) values[f] = null;
  return values;
}

let form = {
  source: "independent", // "independent" | "historical" | "edited"
  values: blankValues(),
  originalValues: null, // snapshot at load time -- only set once a historical example is loaded
  contextConfirmed: false,
  exampleLabel: null,
};

let prefillState = "idle";
let prefillRows = [];
let prefillErrorMessage = "";

let submitState = "idle"; // idle | submitting | done
let submitResult = null; // api.js result for predictSuperCustomer
let confirmingClear = false;

// Mirrors predict.js's own (independently reviewed) session.onSessionEvent
// pattern from the start, since P11-D5 applies identically to every
// screen: stateCleared wipes all local state; epochRaised alone just
// releases this screen's own busy flags so a later show() can retry.
session.onSessionEvent(({ epochRaised, stateCleared }) => {
  if (stateCleared) {
    sharedGen.bump();
    prefillGen += 1;
    form = { source: "independent", values: blankValues(), originalValues: null, contextConfirmed: false, exampleLabel: null };
    prefillState = "idle";
    prefillRows = [];
    submitState = "idle";
    submitResult = null;
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
  const label = el("label", { for: `p4s-field-${name}` });
  label.appendChild(el("span", { className: "field-label-business", text: meta.label }));
  label.appendChild(el("span", { className: "field-label-technical", text: format.ltr(name) }));
  label.appendChild(el("span", { className: "field-label-unit", text: meta.unit }));
  wrap.appendChild(label);

  const inputRow = el("div", { className: "field-input-row" });
  const input = el("input", { id: `p4s-field-${name}`, type: "number", step: "1", min: "0", required: "required" });
  input.addEventListener("focus", () => input.select());
  input.addEventListener("input", () => onFieldInput(name, input.value));
  inputRow.appendChild(input);

  // IA.md §3א.3.1: shown ONLY next to an edited field, and only while a
  // historical example is loaded -- never as a disabled placeholder in
  // an independent scenario (row "בלי דוגמה אין מה להחזיר").
  const revertButton = el("button", { type: "button", className: "revert-field-action", text: "החזר לערך הדוגמה" });
  revertButton.hidden = true;
  revertButton.addEventListener("click", () => revertField(name));
  inputRow.appendChild(revertButton);
  wrap.appendChild(inputRow);

  return { wrap, input, revertButton };
}

function buildOnce() {
  container.replaceChildren();

  // DESIGN.md §3.4's own P4S row, exact order (⚠ explicitly flagged
  // there as DIFFERENT from the shared form's own top-of-screen
  // placement): prefill-picker → input-summary → 4 fields (each with
  // its own revert-field-action) → context-confirmation, "בתחתית, ממש
  // לפני כפתור השליחה" → submit + clear-form-action SIDE BY SIDE →
  // results. Confirmation sits at the bottom here because it is a
  // right-before-submit attestation, not an opening condition the way
  // it is on the shared form (review-round finding: this module
  // originally reused the shared form's own top-of-screen placement
  // verbatim, which is correct THERE but explicitly wrong here).
  const prefillWrap = el("div", { className: "prefill-picker" });
  prefillWrap.appendChild(el("h3", { text: "טעינת דוגמה היסטורית" }));
  const prefillBody = el("div", { className: "prefill-picker-body" });
  prefillWrap.appendChild(prefillBody);
  container.appendChild(prefillWrap);

  const summaryWrap = el("div", { className: "input-summary" });
  container.appendChild(summaryWrap);

  const grid = el("div", { className: "field-grid" });
  const fieldInputs = {};
  const revertButtons = {};
  for (const name of SUPER_CUSTOMER_FIELDS) {
    const { wrap, input, revertButton } = buildFieldNode(name);
    fieldInputs[name] = input;
    revertButtons[name] = revertButton;
    grid.appendChild(wrap);
  }
  container.appendChild(grid);

  const blockedWrap = el("div", { className: "submit-blocked-wrap" });
  container.appendChild(blockedWrap);

  const contextWrap = el("div", { className: "context-confirmation" });
  const contextLabel = el("label");
  const contextCheckbox = el("input", { type: "checkbox" });
  contextCheckbox.addEventListener("change", (e) => {
    const next = e.target.checked;
    if (next === form.contextConfirmed) { updateDynamic(); return; }
    form.contextConfirmed = next;
    sharedGen.bump();
    submitState = "idle";
    submitResult = null;
    updateDynamic();
  });
  contextLabel.appendChild(contextCheckbox);
  contextLabel.appendChild(el("span", { text: CONTEXT_CONFIRMATION_TEXT }));
  contextWrap.appendChild(contextLabel);
  container.appendChild(contextWrap);

  const actionsRow = el("div", { className: "p4s-actions-row" });
  // "הפקת ציון" -- this module's own composition (no button label is
  // locked anywhere for this screen; IA.md §3.3 only names the shared
  // form's own "הפקת תחזיות"). Parallel phrasing: one score, not three
  // predictions.
  const submitButton = el("button", { type: "button", className: "submit-button", text: "הפקת ציון" });
  submitButton.addEventListener("click", submitForm);
  actionsRow.appendChild(submitButton);

  const clearWrap = el("div", { className: "clear-form-action" });
  actionsRow.appendChild(clearWrap);
  container.appendChild(actionsRow);

  const resultsWrap = el("div", { className: "results-wrap" });
  container.appendChild(resultsWrap);

  nodes = { contextCheckbox, prefillBody, summaryWrap, fieldInputs, revertButtons, blockedWrap, submitButton, clearWrap, resultsWrap };
}

function syncFieldValuesToDom() {
  for (const name of SUPER_CUSTOMER_FIELDS) {
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

/** IA.md §3א.3.1's own quoted literal strings, reproduced exactly. */
function renderSummary() {
  const filledCount = SUPER_CUSTOMER_FIELDS.filter((f) => form.values[f] !== null && form.values[f] !== undefined).length;
  let text = `${SOURCE_LABELS[form.source]} · ${filledCount}/4`;
  if (form.source === "edited" && form.originalValues) {
    const changed = SUPER_CUSTOMER_FIELDS.filter((f) => form.values[f] !== form.originalValues[f]).length;
    text += ` · ${changed} שדות שונו`;
  }
  nodes.summaryWrap.replaceChildren(el("span", { text }));
}

/** Each field's own revert button: visible only when a historical
 * example is loaded AND this specific field currently differs from it
 * (IA.md §3א.3.1: never shown as disabled in an independent scenario,
 * and only next to a field that actually changed). */
function renderRevertButtons() {
  for (const name of SUPER_CUSTOMER_FIELDS) {
    const changed = form.originalValues !== null && form.values[name] !== form.originalValues[name];
    nodes.revertButtons[name].hidden = !changed;
  }
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
    SUPER_CUSTOMER_FIELDS.some((f) => form.values[f] !== null) ||
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
// The single P4S result panel.
// ---------------------------------------------------------------------

function panelFailureMessage(result) {
  if (result.reason === "unavailable") return "השירות אינו זמין כרגע. נסו לשלוח את הטופס שוב.";
  if (result.reason === "network") return "שגיאת רשת. נסו לשלוח את הטופס שוב.";
  if (result.reason === "auth") return "פג תוקף ההתחברות.";
  return "אירעה שגיאה. נסו לשלוח את הטופס שוב.";
}

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

function buildEvidenceBadge(evidenceLevel, warnings) {
  if (evidenceLevel !== "low") return null;
  const unobserved = warnings.find((w) => w.code === "unobserved_budget_level");
  const badge = el("div", { className: "evidence-badge evidence-low" }, [
    el("span", { className: "badge-icon", text: "⚠" }),
    el("span", { text: "תמיכה חלקית בנתונים" }),
  ]);
  if (unobserved) badge.appendChild(el("p", { className: "evidence-badge-message", text: unobserved.message }));
  return badge;
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

function buildModelDetails(d) {
  const rows = [
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
  const details = el("details", { className: "model-details" });
  details.appendChild(el("summary", { text: "פרטי המודל" }));
  const dl = el("dl", {});
  for (const [label, value] of rows) {
    dl.appendChild(el("dt", { text: label }));
    dl.appendChild(el("dd", { text: value }));
  }
  details.appendChild(dl);
  return details;
}

/** IA.md §3א.4's own two "הגדרות גלויות" -- driven by the LIVE response,
 * rendered in plain language (this module's own translation, see header
 * comment); an unrecognized future value falls back to the raw string
 * rather than mistranslating it. */
function buildDefinitions(d) {
  const wrap = el("div", { className: "p4s-definitions" });
  wrap.appendChild(el("p", { text: TARGET_DEFINITION_TEXT[d.target_definition] || d.target_definition }));
  wrap.appendChild(el("p", { text: POPULATION_DEFINITION_TEXT[d.population_definition] || d.population_definition }));
  return wrap;
}

/** IA.md §3א.6's own mandatory sentence, verbatim, 1-decimal percentages
 * (matches that literal text's own rounding). Hidden entirely if the
 * asset failed to load -- P11-D15: "אינו fallback לכשל בבקשה הנוכחית",
 * and this card never affects the live score above it either way. */
function buildBusinessContextCard() {
  const profile = facts.getSuperCustomerProfile();
  if (!profile) return null;
  const pct1 = format.formatPercent(profile.pct_of_purchased, { decimals: 1 });
  const pct2 = format.formatPercent(profile.pct_of_total_profit, { decimals: 1 });
  const pct3 = format.formatPercent(profile.cac_savings_pct, { decimals: 1 });
  return el("div", { className: "business-context-card" }, [
    el("p", {
      text: `באוכלוסיית הרוכשים שנבדקה, לקוחות שענו להגדרת לקוח-על היו ${pct1} מהאוכלוסייה ויצרו ${pct2} מהרווח המצטבר. עלות הרכישה הממוצעת שלהם הייתה נמוכה ב-${pct3}. הציון במסך מסייע לזהות דפוס דומה כבר לאחר המעקב הראשון, אך אינו מבטיח שהלקוח יהפוך ללקוח-על.`,
    }),
  ]);
}

/** D9's own "meaning" layer for P4S (DESIGN.md §6.1) needs the SAME
 * business_facts profile as the card above -- unlike the "answer" layer
 * (score + base_rate, both from the live response only), this one has
 * no locked fallback if the asset never loaded. This module's own
 * degraded composition for that case, flagged: no invented numbers,
 * grounded only in the live, always-present target/population
 * definitions. */
function buildD9Meaning() {
  const profile = facts.getSuperCustomerProfile();
  if (!profile) {
    return "היסטורית, לקוחות שעונים להגדרת לקוח-על הניבו רווח גבוה יחסית מתוך עלות רכישה נמוכה יחסית. פרופיל מדויק אינו זמין כרגע.";
  }
  const pct1 = format.formatPercent(profile.pct_of_purchased, { decimals: 1 });
  const pct2 = format.formatPercent(profile.pct_of_total_profit, { decimals: 1 });
  const cacSuper = format.formatCurrency(profile.cac_super_mean, { decimals: 2 });
  const cacPopulation = format.formatCurrency(profile.cac_population_mean, { decimals: 2 });
  const pct3 = format.formatPercent(profile.cac_savings_pct, { decimals: 1 });
  return `היסטורית, לקוחות-על היו ${pct1} מהרוכשים, יצרו ${pct2} מהרווח המצטבר; עלות הרכישה הממוצעת שלהם הייתה ${cacSuper}, לעומת ${cacPopulation}, כלומר נמוכה ב-${pct3}. זהו פרופיל תיאורי`;
}

function buildP4SPanel(result) {
  const panel = el("div", { className: "prediction-panel prediction-panel-p4s" });
  panel.appendChild(el("h3", { text: "ציון לקוח-על מוקדם" }));
  if (!result.ok) {
    // DESIGN.md §2.1's own row for this exact single-panel screen DOES
    // carry "+ ניסיון חוזר" (unlike the shared form's own row -- see
    // predict.js's header comment on that resolved contradiction), so
    // there is no ambiguity to resolve here.
    panel.appendChild(status.errorElement(panelFailureMessage(result), { onRetry: submitForm }));
    return panel;
  }
  const d = result.data;

  const evidenceBadge = buildEvidenceBadge(d.evidence_level, d.warnings);
  if (evidenceBadge) panel.appendChild(evidenceBadge);

  if (!d.in_training_domain) {
    panel.appendChild(buildOodBanner(d.warnings));
    panel.appendChild(buildDefinitions(d));
    panel.appendChild(el("p", {
      className: "model-disclaimer",
      text: "הציון הוא אומדן הסתברותי, לא הבטחה; אינו זהה ל-P4 (נטייה להפניה).",
    }));
    const card = buildBusinessContextCard();
    if (card) panel.appendChild(card);
    panel.appendChild(renderSummaryRecommendation({
      // OOD state -- this module's own composition (see header comment).
      answer: "אין ציון — הקלט הנוכחי מחוץ לתחום שעליו אומן המודל",
      meaning: "המודל יודע להעריך פוטנציאל לקוח-על רק עבור קלט בטווחים שראה באימון; קלט חריג אינו ניתן להערכה אמינה",
      action: "יש לבדוק את השדות המסומנים למטה מול הטווח המאומן, לתקן במידת הצורך ולשלוח שוב",
      caveat: "תקף רק אחרי רכישה ידועה, מעקב 1 וחלון חודשי סגור. CatBoost נמדד ב-Holdout עם ROC-AUC 0.8014 ו-PR-AUC 0.3420, אך Recall 0 בסף ברירת המחדל; לכן הציון הוא אות מסייע בלבד",
    }));
    panel.appendChild(buildModelDetails(d));
    return panel;
  }

  panel.appendChild(buildBandBadge(d.propensity_band));
  panel.appendChild(buildBaseRateLine(d.event_probability, d.base_rate));
  // calibration_status is Literal["calibrated"] on this schema alone
  // (schemas.py:438) -- no "uncalibrated" branch/disclaimer exists here
  // (DESIGN.md §2.4/IA.md §3א.4: "uncalibrated לעולם אינו מופיע").
  panel.appendChild(el("div", { className: "calibration-badge calibrated" }, [
    el("span", { className: "badge-icon", text: "✓" }),
    el("span", { text: "מכויל" }),
  ]));

  // P11-D12: Math.round(p*100), 0-100 integer -- ⛔ no "%" sign, unlike
  // P4's own {X}% (IA.md §3א.5's own distinction table).
  const score = Math.round(d.event_probability * 100);
  panel.appendChild(el("p", { className: "prediction-primary", text: `ציון לקוח-על: ${format.ltr(String(score))}` }));

  panel.appendChild(buildDefinitions(d));
  panel.appendChild(el("p", {
    className: "model-disclaimer",
    text: "הציון הוא אומדן הסתברותי, לא הבטחה; אינו זהה ל-P4 (נטייה להפניה).",
  }));

  const card = buildBusinessContextCard();
  if (card) panel.appendChild(card);

  const pct = format.formatPercent(d.base_rate);
  panel.appendChild(renderSummaryRecommendation({
    answer: `ציון לקוח-על: ${format.ltr(String(score))} מתוך 100, מול שיעור הבסיס שחזר: ${pct}`,
    meaning: buildD9Meaning(),
    action: "רק כשהקלט בתחום, אין סימון תמיכה חלקית והנטייה מעל הבסיס, אפשר להשתמש בציון כאות מסייע לבדיקה ידנית של רוכש ידוע. בכל מצב אחר אין תעדוף לפי המודל",
    caveat: "תקף רק אחרי רכישה ידועה, מעקב 1 וחלון חודשי סגור. CatBoost נמדד ב-Holdout עם ROC-AUC 0.8014 ו-PR-AUC 0.3420, אך Recall 0 בסף ברירת המחדל; לכן הציון הוא אות מסייע בלבד",
  }));

  panel.appendChild(buildModelDetails(d));
  return panel;
}

function renderResults() {
  nodes.resultsWrap.replaceChildren();
  if (submitState === "idle") return;
  if (submitState === "submitting") {
    nodes.resultsWrap.appendChild(status.loadingElement("שולח לחיזוי…"));
    return;
  }
  nodes.resultsWrap.appendChild(buildP4SPanel(submitResult));
}

function updateDynamic() {
  if (!nodes) return;
  nodes.contextCheckbox.checked = form.contextConfirmed;
  renderPrefillBody();
  renderSummary();
  renderRevertButtons();
  const violations = validateSuperCustomerForm(form.values);
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

  // Same fix, unconditional from the start: bump/invalidate on EVERY
  // edit, not just when the prior source was "historical" (predict.js's
  // CP4 review round 2 found this exact bug pattern).
  sharedGen.bump();
  submitState = "idle";
  submitResult = null;

  if (form.source === "historical") {
    form.source = "edited";
    form.contextConfirmed = false;
  }
  updateDynamic();
}

/** IA.md §3א.3.1 "החזרת שדה בודד": restores ONE field from the loaded
 * example. Never re-queries Supabase -- works against the example
 * already held in memory. */
function revertField(name) {
  if (!form.originalValues) return; // "בלי דוגמה אין מה להחזיר" -- button is hidden in this case anyway
  form.values[name] = form.originalValues[name];
  sharedGen.bump();
  submitState = "idle";
  submitResult = null;

  const stillEdited = SUPER_CUSTOMER_FIELDS.some((f) => form.values[f] !== form.originalValues[f]);
  form.source = stillEdited ? "edited" : "historical";
  // Both branches of the IA.md state table reset confirmation here --
  // a single field's own value just changed either way.
  form.contextConfirmed = false;

  nodes.fieldInputs[name].value = String(form.values[name]);
  updateDynamic();
}

function applyExample(row, index) {
  const snapshot = {};
  for (const f of SUPER_CUSTOMER_FIELDS) snapshot[f] = row[f];
  form.values = { ...snapshot };
  form.originalValues = { ...snapshot };
  form.source = "historical";
  form.exampleLabel = `דוגמה ${index}`;
  form.contextConfirmed = false;
  sharedGen.bump();
  submitState = "idle";
  submitResult = null;
  syncFieldValuesToDom();
  updateDynamic();
}

function clearForm() {
  sharedGen.bump();
  form = { source: "independent", values: blankValues(), originalValues: null, contextConfirmed: false, exampleLabel: null };
  submitState = "idle";
  submitResult = null;
  syncFieldValuesToDom();
  updateDynamic();
}

async function submitForm() {
  const violations = validateSuperCustomerForm(form.values);
  const needsConfirmation = form.source !== "historical" && !form.contextConfirmed;
  if (violations.length > 0 || needsConfirmation) return;

  submitState = "submitting";
  const myGen = sharedGen.bump();
  updateDynamic();

  const payload = { ...form.values };
  const [result] = await Promise.all([api.predictSuperCustomer(payload), facts.init()]);

  if (!sharedGen.isCurrent(myGen)) return;

  submitState = "done";
  submitResult = result;
  updateDynamic();
}

async function loadPrefillList() {
  prefillState = "loading";
  const myGen = ++prefillGen;
  if (nodes) updateDynamic();

  const result = await supabasePrefill.fetchSuperCustomerPrefill();
  if (myGen !== prefillGen) return;

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

/** Called by app.js's router every time the super-customer route is shown. */
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
