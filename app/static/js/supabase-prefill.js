"use strict";

// FunnelIQ Supabase prefill module (phase 11, checkpoint 2). Reads
// public.funnel_records DIRECTLY through supabase-js with the CALLER'S
// OWN JWT -- RLS enforced server-side by Supabase itself, not by this
// module (CLAUDE.md locked decision: "קריאות נתונים למשתמש נושאות את
// ה-JWT שלו כדי ש-RLS תיאכף בפועל"). This is a SEPARATE data source
// from the seven business routes (api.js): a PREFILL SELECTOR, never
// an aggregate -- IA.md §11's own table draws this line explicitly:
// "בורר ה-prefill: מבחר מוגבל ומסודר מותר... ⛔ אין להציגו כרשימה מלאה".
// Any aggregate over funnel_records (e.g. Follow-up's calls_to_closed
// distribution) is computed server-side, behind api.js, not here.
//
// Fixed after an independent review of 903a217 found this module
// bypassed BOTH of api.js's own safety gates entirely -- it is a
// second door into session-scoped data and must respect the exact
// same two invariants api.js does, not a weaker version of them:
//   - "no business call before a 200 from /api/me": refuses to query
//     at all while session.isBusinessBlocked() is true or there is no
//     session, exactly like api.js's own call().
//   - P11-D14: "כל בקשה לוכדת epoch... תוצאה מיושנת אינה מרונדרת" --
//     captures session.getEpoch() before querying, and discards
//     (reason: "stale") whatever Supabase returns -- data OR error
//     alike -- if the epoch has moved on by the time it resolves. A
//     sign-out or session-change firing while a prefill query is still
//     in flight must never let a PREVIOUS session's rows reach a form
//     after the user is no longer that session.

import * as session from "./session.js";

// Phase 12A, §ו.2: the prefill picker no longer reads "up to 1000 rows
// ordered by source_row_id" (audit finding F2/S2 -- "very inconvenient").
// It reads exactly these 10 frozen historical examples instead, via
// `.in("source_row_id", ...)`. This does NOT bypass RLS (IA.md §3.3):
// the query still runs through the caller's own client/JWT, so an
// unauthorized organization's session still gets zero rows back, and
// `anon` (no JWT at all) is still refused before RLS is even reached.
// Single source of truth for WHICH 10 ids: docs/frozen_examples.json,
// committed by scripts/select_examples.py (requires the frozen CSV,
// local-only -- CI never runs that script). This list is a COPY of
// that manifest's own `source_row_id` values, kept in sync structurally
// by tests/test_frozen_examples.py (10 unique ids, 2/5/3 tier
// composition) -- never edit one without the other.
const FROZEN_EXAMPLE_IDS = [358, 552, 833, 1086, 1774, 1776, 2463, 2595, 2914, 3160];
const SHARED_FORM_COLUMNS = [
  "source_row_id", "ad_budget", "num_leads", "leads_answered", "closed",
  "followup_1", "followup_2", "followup_3", "followup_4", "followup_5",
  "calls_to_closed", "calls_to_not_closed", "customer_acquisition_cost",
].join(",");
// P4S's own, separate prefill -- only its four input fields (IA.md
// §3א.3: "בורר נפרד"). Never shares a picker, a row set, or a
// generation counter with the shared form's prefill (P11-D3/P11-D4).
const P4S_COLUMNS = ["source_row_id", "ad_budget", "num_leads", "leads_answered", "followup_1"].join(",");

let client = null;

/** Must be called once with the SAME Supabase client bootstrap.js
 * already created (bootstrapAuth.getClient()) -- never a second
 * client, and there is no service key in the browser to build one
 * with even if that were wanted. */
export function init(supabaseClient) {
  client = supabaseClient;
}

/** Result shape:
 *   { ok: true, data: row[] }
 *   { ok: false, reason: "not-initialized" }  -- init() never called
 *   { ok: false, reason: "blocked" }           -- refused before querying
 *   { ok: false, reason: "stale" }             -- discarded (epoch moved on)
 *   { ok: false, reason: "error", error }      -- Supabase itself returned an error
 */
async function fetchPrefill(columns) {
  if (!client) return { ok: false, reason: "not-initialized" };
  if (!session.getSession() || session.isBusinessBlocked()) {
    return { ok: false, reason: "blocked" };
  }

  const epochAtSend = session.getEpoch();
  const { data, error } = await client
    .from("funnel_records")
    .select(columns)
    .eq("purchased", 1)
    .in("source_row_id", FROZEN_EXAMPLE_IDS)
    .order("source_row_id", { ascending: true });

  if (!session.isCurrentEpoch(epochAtSend)) {
    return { ok: false, reason: "stale" };
  }
  if (error) return { ok: false, reason: "error", error };
  return { ok: true, data: data ?? [] };
}

/** The shared P2/P3/P4 form's prefill selector -- 12 model-input
 * columns + source_row_id, purchased=1, restricted to the 10 frozen
 * example ids (§ו.2). `not_closed` is NOT a stored column and is not returned
 * here -- callers derive it themselves (`followup_5 - closed`, IA.md
 * §3.1) the same way manual entry does; that derivation belongs to the
 * form checkpoint (4), not this generic reader. */
export function fetchSharedFormPrefill() {
  return fetchPrefill(SHARED_FORM_COLUMNS);
}

/** P4S's own, separate prefill selector. */
export function fetchSuperCustomerPrefill() {
  return fetchPrefill(P4S_COLUMNS);
}
