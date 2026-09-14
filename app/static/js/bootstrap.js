"use strict";

// FunnelIQ auth bootstrap (phase 11, checkpoint 1, P11-D13).
//
// Implements the seven branches in docs/IA.md §9.3 / PHASE11.md §ד1:
// config failure, no session, 200, 401, 403, 503, 500. A valid Supabase
// session is necessary but never sufficient to show product content --
// that is exactly the difference between "no session"/401 and 403.
// Every session change, from the very first load through every later
// sign-in/sign-out/token-refresh, goes through verify() before any
// authenticated content is shown.

import * as session from "./session.js";

let client = null;
let onState = null; // supplied by app.js: (state) => void
let lastSession = undefined; // sentinel: bootstrap has not run yet

async function callMe(token) {
  return fetch("/api/me", {
    headers: { Authorization: `Bearer ${token}` },
  });
}

/** Runs GET /api/me for a given Supabase session (or reports
 * "no-session" directly, without calling it, when there is none). */
async function verify(supaSession, eventName) {
  lastSession = supaSession;

  if (supaSession === null) {
    // IA.md §9.3: no token exists to send, and calling anyway would
    // only produce a confusing, unrequested 401 in the network log.
    onState({ kind: "no-session", session: null, user: null });
    return;
  }

  let response;
  try {
    response = await callMe(supaSession.access_token);
  } catch {
    // Network failure reaching our own API -- grouped with 503: infra
    // trouble, not the caller's fault; session stays, retry is offered.
    session.setBusinessBlocked(true);
    onState({ kind: "503", session: supaSession, user: null });
    return;
  }

  if (response.status === 200) {
    session.setBusinessBlocked(false);
    const user = await response.json();
    onState({ kind: "200", session: supaSession, user });
    return;
  }
  if (response.status === 401) {
    session.applyAuthResult("401");
    onState({ kind: "401", session: null, user: null });
    return;
  }
  if (response.status === 403) {
    session.applyAuthResult("403");
    onState({ kind: "403", session: supaSession, user: null });
    return;
  }
  if (response.status === 500) {
    // Our own config bug, not a momentary blip -- a distinct message
    // from 503, but the same session-kept/shell-blocked handling.
    session.setBusinessBlocked(true);
    onState({ kind: "500", session: supaSession, user: null });
    return;
  }
  // 503 and any other unexpected status land here, grouped with 503 --
  // both are "infrastructure, not the caller's credentials" (IA.md §9.3).
  session.setBusinessBlocked(true);
  onState({ kind: "503", session: supaSession, user: null });
}

/** One-time init: fetch /api/config, build the Supabase client, run the
 * first verify() against getSession(), then subscribe to
 * onAuthStateChange for every later session change (sign-in, sign-out,
 * token refresh, tab-focus re-delivery -- IA.md §9.3's "כלל האירועים").
 * Returns the Supabase client so app.js can wire the login form and
 * sign-out button to it, or null if /api/config itself failed. */
export async function init(handler) {
  onState = handler;

  let config;
  try {
    const response = await fetch("/api/config");
    if (!response.ok) throw new Error("config request failed");
    config = await response.json();
  } catch {
    // Before there is a session at all -- no Login screen, no shell.
    onState({ kind: "config-error", session: null, user: null });
    return null;
  }

  client = window.supabase.createClient(
    config.supabase_url,
    config.supabase_publishable_key
  );

  // getSession() runs first, unconditionally, so the very first check
  // never depends on assuming a particular onAuthStateChange delivery
  // pattern on subscribe (supabase-js's exact replay behavior across
  // versions is not something this design pins down as fact -- see
  // PHASE11.md P11-D14, "תלות בעובדות לא-מאומתות"). The subscription
  // below is only wired up afterward, and its own de-dupe guard makes
  // this correct even if a replay of the same session does happen.
  const { data } = await client.auth.getSession();
  session.applySessionChange("INITIAL", data.session);
  await verify(data.session, "INITIAL");

  client.auth.onAuthStateChange((event, nextSession) => {
    if (session.isSameSession(lastSession, nextSession)) return;
    session.applySessionChange(event, nextSession);
    verify(nextSession, event);
  });

  return client;
}

/** Re-runs verify() against the last known session -- wired to the
 * availability-error "ניסיון חוזר" control for 503/500. A no-op if
 * bootstrap never ran or the session is currently null (there would be
 * nothing to retry: "no-session" doesn't call /api/me in the first
 * place). */
export function retry() {
  if (lastSession) return verify(lastSession, "RETRY");
}

export function getClient() {
  return client;
}
