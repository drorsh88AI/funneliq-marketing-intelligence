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

function block(name) {
  if (!loaded) return null;
  const value = loaded[name];
  return value && typeof value === "object" ? value : null;
}

/** P2's leverage-summary content (`dominant_feature` /
 * `rank_1_by_algorithm`) -- hidden ALONE if `model_versions.P2` does
 * not match the live prediction response's own `model_version`. The
 * P2 prediction result itself is never affected by this. */
export function getLtvLeverage(liveModelVersionP2) {
  const b = block("ltv");
  if (!b) return null;
  if (loaded.model_versions?.P2 !== liveModelVersionP2) return null;
  return b;
}

/** Budget Simulator's backtest + recommendation content -- hidden
 * ALONE if `model_versions.P6` does not match. The four-strategy table
 * itself (from GET /api/simulate/budget) is never affected. */
export function getBudgetBacktest(liveModelVersionP6) {
  const b = block("budget_backtest");
  if (!b) return null;
  if (loaded.model_versions?.P6 !== liveModelVersionP6) return null;
  return b;
}

/** P4S's business-context card. No model_version check -- verified
 * against openapi.json that SuperCustomerPrediction carries no field
 * this could even be compared against; tying it to model_versions.P4S
 * would be a false coupling (P11-D15 מורחב). */
export function getSuperCustomerProfile() {
  return block("super_customer_profile");
}

/** Follow-up's calls_to_closed population averages. Same reasoning --
 * FollowupResponse carries no model_version field to compare against. */
export function getFollowupContext() {
  return block("followup_context");
}

export function isLoaded() {
  return loaded !== null;
}

/** Test-only reset -- not imported by any product code path. */
export function resetForTest() {
  loaded = null;
  loadAttempted = false;
}
