"use strict";

// FunnelIQ business-call wrapper (phase 11, checkpoint 2). The ONE
// place every one of the seven locked business routes
// (docs/api/openapi.json) is called from:
//   - always attaches the CALLER'S OWN Bearer JWT (session.getSession()
//     .access_token) -- never a service key, there is none in the
//     browser to use (CLAUDE.md locked decision).
//   - refuses to send at all before bootstrap has ever reached a 200
//     (session.isBusinessBlocked() defaults true -- checkpoint 2 fix to
//     session.js) or while there is currently no session.
//   - discards a response that arrives after the GLOBAL session epoch
//     (P11-D14) has moved on -- a signed-out or session-changed user
//     never sees a response addressed to the identity they no longer
//     are. This does NOT check any per-screen `generation` counter
//     (./generation.js) -- that is the calling screen's own
//     responsibility, since only the screen knows which of its own
//     instances applies to a given request.
//
// On 401/403 from ANY business call (current_user is the SAME shared
// dependency /api/me uses -- app/auth.py's own docstring: "Business
// endpoints reuse current_user as their own dependency" -- so a token
// that expired mid-session can 401 from any of these routes, not just
// the bootstrap check): reuses session.applyAuthResult() (epoch raise +
// state clear, P11-D14) and reports the SAME {kind, session, user}
// shape bootstrap.js's onState already uses, through a separately
// registered handler -- so app.js can drive Login/forbidden-notice
// from a business-call failure exactly the way it already does for a
// bootstrap one, with no second code path to keep in sync.
//
// 500/503 from an individual business call is deliberately NOT routed
// through that global handler and does NOT touch
// session.setBusinessBlocked() -- unlike the bootstrap /api/me check,
// a single endpoint's own hiccup (e.g. Budget Simulator's model
// artifact) is a PER-SCREEN concern (DESIGN.md §2.1's own
// panel-error/ניסיון חוזר pattern), and must never cascade into
// blocking an unrelated screen's calls.

import * as session from "./session.js";

let authFailureHandler = null;

/** Registered once by app.js -- reuses the same onAuthState shape
 * bootstrap.js already drives. */
export function setAuthFailureHandler(fn) {
  authFailureHandler = fn;
}

function reportAuthEvent(state) {
  if (authFailureHandler) authFailureHandler(state);
}

/** Result shape every call resolves to -- always check `ok` first:
 *   { ok: true, data }                            -- 200, still current
 *   { ok: false, reason: "blocked" }               -- refused before sending
 *   { ok: false, reason: "stale" }                 -- discarded (epoch moved on)
 *   { ok: false, reason: "network" }                -- fetch itself threw
 *   { ok: false, reason: "auth", status }           -- 401/403 (already reported)
 *   { ok: false, reason: "unavailable", status }    -- 500/503 (caller's own retry)
 */
async function call(path, options = {}) {
  const supaSession = session.getSession();
  if (!supaSession || session.isBusinessBlocked()) {
    return { ok: false, reason: "blocked" };
  }

  const epochAtSend = session.getEpoch();
  let response;
  try {
    response = await fetch(path, {
      ...options,
      headers: {
        ...(options.headers || {}),
        Authorization: `Bearer ${supaSession.access_token}`,
      },
    });
  } catch {
    if (!session.isCurrentEpoch(epochAtSend)) return { ok: false, reason: "stale" };
    return { ok: false, reason: "network" };
  }

  if (!session.isCurrentEpoch(epochAtSend)) {
    return { ok: false, reason: "stale" };
  }

  if (response.status === 200) {
    const data = await response.json();
    if (!session.isCurrentEpoch(epochAtSend)) return { ok: false, reason: "stale" };
    return { ok: true, data };
  }
  if (response.status === 401) {
    session.applyAuthResult("401");
    reportAuthEvent({ kind: "401", session: null, user: null });
    return { ok: false, reason: "auth", status: 401 };
  }
  if (response.status === 403) {
    session.applyAuthResult("403");
    reportAuthEvent({ kind: "403", session: supaSession, user: null });
    return { ok: false, reason: "auth", status: 403 };
  }
  // 500 and 503 (and anything else unexpected) land here together --
  // a per-call availability failure. The caller renders its own
  // panel-error + "ניסיון חוזר" (DESIGN.md §2.1); nothing global changes.
  return { ok: false, reason: "unavailable", status: response.status };
}

function postJson(path, payload) {
  return call(path, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
}

function getJson(path) {
  return call(path, { method: "GET" });
}

// The seven locked business routes (docs/api/openapi.json) -- one
// named function per route, so a caller never hand-types a path.
export const predictLtv = (payload) => postJson("/api/predict/ltv", payload);
export const predictUpsell = (payload) => postJson("/api/predict/upsell", payload);
export const predictReferral = (payload) => postJson("/api/predict/referral", payload);
export const predictSuperCustomer = (payload) => postJson("/api/predict/super-customer", payload);
export const simulateBudget = () => getJson("/api/simulate/budget");
export const insightsBudgetTiers = () => getJson("/api/insights/budget-tiers");
export const insightsFollowup = () => getJson("/api/insights/followup");
