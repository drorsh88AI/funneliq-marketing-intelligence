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

const PREFILL_LIMIT = 1000; // IA.md §11's cap on any single funnel_records query
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

/** Result shape: { ok: true, data: row[] } | { ok: false, reason } */
async function fetchPrefill(columns) {
  if (!client) return { ok: false, reason: "not-initialized" };
  const { data, error } = await client
    .from("funnel_records")
    .select(columns)
    .eq("purchased", 1)
    .order("source_row_id", { ascending: true })
    .limit(PREFILL_LIMIT);
  if (error) return { ok: false, reason: "error", error };
  return { ok: true, data: data ?? [] };
}

/** The shared P2/P3/P4 form's prefill selector -- 12 model-input
 * columns + source_row_id, purchased=1, ordered, capped at 1000
 * (IA.md §11). `not_closed` is NOT a stored column and is not returned
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
