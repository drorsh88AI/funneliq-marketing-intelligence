"use strict";

// FunnelIQ static business-facts accessor (phase 11, checkpoint 2,
// P11-D15). Loads /business_facts.json ONCE, validates schema_version
// and top-level structure, and exposes ONE accessor per content block
// -- each hidden independently on its OWN failure/mismatch, never as
// an all-or-nothing switch. That is P11-D15's whole point: a stale
// model_version on one block never disables the other three, and NEVER
// disables a live API result (IA.md §11: this asset "אינו fallback
// לכשל בבקשה הנוכחית").
//
// Per-block dependency (PHASE11.md P11-D15 מורחב, verified against
// docs/api/openapi.json's actual schemas -- BudgetSimulation carries
// model_version, FollowupResponse/BudgetTiersResponse do not):
//   ltv                     -> depends on model_versions.P2
//   budget_backtest         -> depends on model_versions.P6
//   super_customer_profile  -> NO model dependency (a CSV population
//                              aggregate, not a model output)
//   followup_context        -> NO model dependency (same reasoning)

const KNOWN_SCHEMA_VERSION = 1;
const EXPECTED_KEYS = [
  "budget_backtest", "followup_context", "ltv", "metrics_sha256",
  "model_versions", "schema_version", "source_csv_sha256", "source_keys",
  "super_customer_profile",
];

let loaded = null; // the parsed, validated JSON -- or null if unavailable
let loadAttempted = false;

async function ensureLoaded() {
  if (loadAttempted) return;
  loadAttempted = true;
  try {
    const response = await fetch("/business_facts.json");
    if (!response.ok) return; // stays null -- every accessor treats that as "hide"
    const data = await response.json();
    if (data.schema_version !== KNOWN_SCHEMA_VERSION) return;
    if (!EXPECTED_KEYS.every((key) => key in data)) return;
    loaded = data;
  } catch {
    // Load failure (network, malformed JSON) -- stays null, same as above.
  }
}

/** Must be awaited once (app startup is fine) before any accessor is
 * trusted to return real data on a first render. Safe to call more
 * than once -- only the first call actually fetches. */
export async function init() {
  await ensureLoaded();
}

// P11A-D2: per-block typed validation. `block()`'s PREVIOUS check
// (`typeof value === "object"`) accepted arrays (`typeof [] ===
// "object"` is true) and any object shape at all -- a block present
// but malformed in a way JSON itself allows (a JSON number can parse
// to `Infinity` in JS, e.g. `1e400`; `actual_mean_per_customer: 0` is
// syntactically ordinary JSON) would flow straight through to a
// consumer's division/formatPercent/formatCurrency call unchecked.
// D2 is necessary but not sufficient on its own (a degraded fallback
// string written by hand can still leak an asset-dependent claim --
// that is D4-D6's job, not this one's) -- this only closes the NaN/
// Infinity/wrong-type class of leak, at the boundary where the asset
// is parsed, once, for every consumer.
function isPlainObject(value) {
  return value !== null && typeof value === "object" && !Array.isArray(value);
}

function isFiniteNumber(value) {
  return typeof value === "number" && Number.isFinite(value);
}

// Only for a value used as a DIVISOR downstream (budget.js's own
// `predicted_per_customer / actual_mean_per_customer`) -- a plain
// finite check would accept 0, and `x / 0` is `Infinity`, not `NaN`,
// so it would never be caught by a NaN-only guard either.
function isPositiveFiniteNumber(value) {
  return isFiniteNumber(value) && value > 0;
}

function isNonEmptyString(value) {
  return typeof value === "string" && value.length > 0;
}

const BUDGET_LEVEL_NUMERIC_FIELDS = {
  actual_mean_per_customer: isFiniteNumber,
  predicted_per_customer: isFiniteNumber,
  n_train_at_level: isFiniteNumber,
  n_holdout_at_level: isFiniteNumber,
};

// scripts/business_facts.py's own shape (the only writer of this
// file): exactly the "500"/"2000" levels, each with these four fields.
//
// ⚠ Code-review finding, 2026-09-21: only budget.js's OWN divisor --
// backtest["500"].actual_mean_per_customer, the denominator of
// `predicted_per_customer / actual_mean_per_customer` in buildD9()/
// buildModelDetails() -- needs the stricter positive-and-finite guard
// (x/0 is Infinity, not NaN, so a plain finite check would not catch
// it). backtest["2000"].actual_mean_per_customer is never divided by
// anywhere in budget.js (only .n_train_at_level is read from "2000");
// requiring it positive too rejected the WHOLE block -- degrading a
// perfectly valid "500" comparison -- on a level whose own zero/
// negative mean is a legitimate small-holdout-sample outcome, not a
// malformed asset. Scoped the positivity requirement to the one field
// that is actually a divisor, instead of applying it uniformly.
function isValidBudgetBacktest(value) {
  if (!isPlainObject(value)) return false;
  const validLevel = (level) => {
    const entry = value[level];
    return isPlainObject(entry) && Object.entries(BUDGET_LEVEL_NUMERIC_FIELDS).every(([key, check]) => check(entry[key]));
  };
  if (!["500", "2000"].every(validLevel)) return false;
  return isPositiveFiniteNumber(value["500"].actual_mean_per_customer);
}

// `dominant_feature` is legitimately `null` (scripts/business_facts.py:
// only set when all three algorithms agree on one feature) -- callers
// already treat "leverage present but dominant_feature falsy" as "no
// lever" (predict.js's own `if (leverage && leverage.dominant_feature)`),
// so this validator allows null there without treating the whole block
// as invalid.
//
// scripts/business_facts.py's own P2_ALGORITHMS -- the writer ALWAYS
// produces exactly these three keys, one entry per model actually
// compared for agreement (dominant_feature is only non-null when all
// three agree). A `rank_1_by_algorithm` with fewer than all three keys
// present is a partial block, not a smaller-but-complete one -- P11A-D2
// requires it be treated as null like any other partial block, so
// checking "non-empty" alone (accepting e.g. just {catboost: ...}) was
// still a gap the same class of validator should have closed.
const LTV_RANK_ALGORITHMS = ["catboost", "lightgbm", "xgboost"];

function isValidLtv(value) {
  if (!isPlainObject(value)) return false;
  if (value.dominant_feature !== null && !isNonEmptyString(value.dominant_feature)) return false;
  if (!isPlainObject(value.rank_1_by_algorithm)) return false;
  if (Object.keys(value.rank_1_by_algorithm).length !== LTV_RANK_ALGORITHMS.length) return false;
  return LTV_RANK_ALGORITHMS.every((algorithm) => {
    const entry = value.rank_1_by_algorithm[algorithm];
    return isPlainObject(entry) && isNonEmptyString(entry.feature) && isFiniteNumber(entry.importance);
  });
}

const SUPER_CUSTOMER_PROFILE_NUMERIC_FIELDS = [
  "n_purchased", "n_super", "pct_of_purchased", "pct_of_total_profit",
  "cac_super_mean", "cac_population_mean", "cac_savings_pct",
];

function isValidSuperCustomerProfile(value) {
  if (!isPlainObject(value)) return false;
  if (!isNonEmptyString(value.population_definition)) return false;
  return SUPER_CUSTOMER_PROFILE_NUMERIC_FIELDS.every((key) => isFiniteNumber(value[key]));
}

function isValidFollowupContext(value) {
  if (!isPlainObject(value)) return false;
  if (!isNonEmptyString(value.population_definition)) return false;
  return isFiniteNumber(value.mean_calls_closed_eq_1) && isFiniteNumber(value.mean_calls_closed_ge_2);
}

// A malformed block makes `block()` return null -- indistinguishable
// from a MISSING block to every accessor below (D2: "בלוק חלקי ⇒ null
// כמו חסר"), so no caller needs its own defensive field-by-field check.
function block(name, isValid) {
  if (!loaded) return null;
  const value = loaded[name];
  return isValid(value) ? value : null;
}

/** P2's leverage-summary content (`dominant_feature` /
 * `rank_1_by_algorithm`) -- hidden ALONE if `model_versions.P2` does
 * not match the live prediction response's own `model_version`. The
 * P2 prediction result itself is never affected by this. */
export function getLtvLeverage(liveModelVersionP2) {
  const b = block("ltv", isValidLtv);
  if (!b) return null;
  if (loaded.model_versions?.P2 !== liveModelVersionP2) return null;
  return b;
}

/** Budget Simulator's backtest + recommendation content -- hidden
 * ALONE if `model_versions.P6` does not match. The four-strategy table
 * itself (from GET /api/simulate/budget) is never affected. */
export function getBudgetBacktest(liveModelVersionP6) {
  const b = block("budget_backtest", isValidBudgetBacktest);
  if (!b) return null;
  if (loaded.model_versions?.P6 !== liveModelVersionP6) return null;
  return b;
}

/** P4S's business-context card. No model_version check -- verified
 * against openapi.json that SuperCustomerPrediction carries no field
 * this could even be compared against; tying it to model_versions.P4S
 * would be a false coupling (P11-D15 מורחב). */
export function getSuperCustomerProfile() {
  return block("super_customer_profile", isValidSuperCustomerProfile);
}

/** Follow-up's calls_to_closed population averages. Same reasoning --
 * FollowupResponse carries no model_version field to compare against. */
export function getFollowupContext() {
  return block("followup_context", isValidFollowupContext);
}

export function isLoaded() {
  return loaded !== null;
}

/** Test-only reset -- not imported by any product code path. */
export function resetForTest() {
  loaded = null;
  loadAttempted = false;
}
