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
//
// Two correctness properties, fixed after an independent review of the
// first draft (a7695db) found both violated:
//
//   1. No dropped events. onAuthStateChange is subscribed BEFORE the
//      initial getSession() is awaited, so there is no window --
//      however short -- with zero listener where a real session change
//      (a token refresh, a forced sign-out from another tab) could
//      fire and be silently missed.
//   2. No stale /api/me response ever wins. Because that subscription
//      now runs concurrently with the initial check, and because two
//      later verify() calls (e.g. two TOKEN_REFRESHED deliveries close
//      together) can themselves resolve in either order, every
//      verify() call is tagged with a monotonic `generation` at the
//      moment it STARTS; a response is only acted on if its generation
//      is still the latest when the response arrives -- checked again
//      after every `await` inside verify(), including the second one
//      (parsing a 200 body) a first pass missed. `session epoch`
//      (P11-D14) is a DIFFERENT counter for a different job (staleness
//      of BUSINESS responses across explicit resets like sign-out) and
//      does not by itself solve this -- TOKEN_REFRESHED specifically
//      never raises it, so two overlapping /api/me calls around a
//      token refresh would otherwise share one epoch and have no way
//      to tell which response is newer.

import * as session from "./session.js";

let client = null;
let onState = null; // supplied by app.js: (state) => void
let lastSession = null; // target for retry() -- always the most
                         // recently STARTED verify()'s input, set
                         // synchronously so call-order (not completion
                         // order) decides it.
let generation = 0;

async function callMe(token) {
  return fetch("/api/me", {
    headers: { Authorization: `Bearer ${token}` },
  });
}

/** Runs GET /api/me for a given Supabase session (or reports
 * "no-session" directly, without calling it, when there is none).
 * Discards its own result if a newer verify() call has started before
 * this one's response (or response body) arrives -- see module
 * docstring, property 2. */
async function verify(supaSession, eventName) {
  const myGen = ++generation;
  lastSession = supaSession;

  if (supaSession === null) {
    // IA.md §9.3: no token exists to send, and calling anyway would
    // only produce a confusing, unrequested 401 in the network log.
    // No `await` has happened yet in this call, so `myGen` cannot be
    // stale here -- nothing else could have incremented `generation`
    // between the two synchronous lines above.
    onState({ kind: "no-session", session: null, user: null });
    return;
  }

  let response;
  try {
    response = await callMe(supaSession.access_token);
  } catch {
    if (myGen !== generation) return; // superseded while the request was in flight
    session.setBusinessBlocked(true);
    onState({ kind: "503", session: supaSession, user: null });
    return;
  }

  if (myGen !== generation) return; // superseded while the request was in flight

  if (response.status === 200) {
    session.setBusinessBlocked(false);
    const user = await response.json();
    if (myGen !== generation) return; // superseded while parsing the body
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

/** One-time init: fetch /api/config, build the Supabase client,
 * subscribe to onAuthStateChange, THEN run the first verify() against
 * getSession() -- in that order, so no session change delivered while
 * the initial /api/me call is in flight is ever missed (module
 * docstring, property 1). Returns the Supabase client so app.js can
 * wire the login form and sign-out button to it, or null if
 * /api/config, client creation, or the initial getSession() failed. */
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

  try {
    // `window.supabase` is undefined if the CDN request failed or its
    // SRI hash didn't match -- createClient() then throws a
    // TypeError. The original phase-4 app.js guarded exactly this
    // (its own comment: "without this, stuck on loading forever with
    // no visible error"); that guarantee is restored here after being
    // dropped in this checkpoint's first draft.
    client = window.supabase.createClient(
      config.supabase_url,
      config.supabase_publishable_key
    );

    // Subscribed before the getSession() await below -- see module
    // docstring, property 1. verify() is safe to call more than once
    // or out of order (property 2), so a possible duplicate initial
    // delivery from supabase-js costs at most one redundant /api/me
    // call, never a correctness bug; this design does not need to
    // assume any specific replay behavior from the library either way
    // (PHASE11.md P11-D14, "תלות בעובדות לא-מאומתות").
    client.auth.onAuthStateChange((event, nextSession) => {
      session.applySessionChange(event, nextSession);
      verify(nextSession, event);
    });

    const { data } = await client.auth.getSession();
    session.applySessionChange("INITIAL", data.session);
    await verify(data.session, "INITIAL");
  } catch {
    onState({ kind: "config-error", session: null, user: null });
    return null;
  }

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
