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
// Four correctness properties, fixed across three independent reviews
// of this file (a7695db, then its own fix 75aa03c, then checkpoint 2's
// first real consumer -- api.js in 8ebbd5e -- exposing a fourth gap):
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
//   3. A late-resolving getSession() snapshot never overrides a real
//      event. Property 2's `generation` orders verify() calls by when
//      they STARTED -- but getSession()'s own value is a snapshot from
//      BEFORE it was even called, so a real event that arrives while
//      it is still pending is newer information despite starting its
//      own verify() call earlier (and so getting a LOWER generation).
//      init() tracks this directly with `sessionEventSeen`: once any
//      real event has been delivered, getSession()'s eventual result
//      (success or failure) is discarded outright, never applied to
//      session.js and never hitting verify() at all. See init()'s own
//      docstring for the full failure trace this closes.
//   4. businessBlocked is true for the ENTIRE duration of any
//      verification of a non-null session, not just while a request is
//      actually in flight. Set synchronously at the top of every
//      verify() call (before any await), and only cleared after a 200
//      AND its body has been parsed AND the generation check confirms
//      this call is still current. See verify()'s own docstring for
//      the exact cross-session reproduction this closes.

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
 * docstring, property 2.
 *
 * A FOURTH property, fixed after an independent review of 8ebbd5e
 * (api.js's own first behavioral test suite) found it violated:
 *
 *   4. businessBlocked is true for the ENTIRE duration of any
 *      verification of a non-null session -- from the synchronous
 *      instant verify() is called, until a 200 for that SAME,
 *      still-current call has both arrived AND had its body parsed.
 *      Properties 1-3 correctly stop a stale RESPONSE from ever being
 *      rendered or from reverting session.current -- but they said
 *      nothing about the SEPARATE businessBlocked flag api.js gates
 *      on, which stayed false from an OLDER session's 200 straight
 *      through a sign-out and into a brand-new session's own
 *      not-yet-verified verify() call. Reproduced exactly as
 *      described: session A gets 200 (businessBlocked=false) -> SIGNED_OUT
 *      -> SIGNED_IN as a different session B -> B's own /api/me is
 *      still in flight, but businessBlocked is STILL false from A, so
 *      a business call fires with B's token before B has ever been
 *      confirmed. Fixed by setting businessBlocked = true
 *      SYNCHRONOUSLY at the top of every non-null verify() call
 *      (before any `await`, so no window exists where it reads stale),
 *      and moving businessBlocked = false to AFTER both awaits (the
 *      fetch AND the body parse) and the final generation check --
 *      never earlier, or a newer verify() starting during THIS call's
 *      own json() parse could still see the gate open. */
async function verify(supaSession, eventName) {
  const myGen = ++generation;
  lastSession = supaSession;

  if (supaSession === null) {
    // IA.md §9.3: no token exists to send, and calling anyway would
    // only produce a confusing, unrequested 401 in the network log.
    // No `await` has happened yet in this call, so `myGen` cannot be
    // stale here -- nothing else could have incremented `generation`
    // between the two synchronous lines above.
    session.setBusinessBlocked(true);
    onState({ kind: "no-session", session: null, user: null });
    return;
  }

  // Synchronous, before any await (property 4) -- true for the whole
  // lifetime of this verification, regardless of what session or
  // response it turns out to belong to.
  session.setBusinessBlocked(true);

  let response;
  try {
    response = await callMe(supaSession.access_token);
  } catch {
    if (myGen !== generation) return; // superseded while the request was in flight
    onState({ kind: "503", session: supaSession, user: null });
    return;
  }

  if (myGen !== generation) return; // superseded while the request was in flight

  if (response.status === 200) {
    const user = await response.json();
    if (myGen !== generation) return; // superseded while parsing the body
    // Only now -- current AND successful AND body-parsed -- is the
    // gate allowed to open. A newer verify() that started during this
    // json() parse already re-set businessBlocked=true synchronously
    // at ITS own start, so there is no window where a stale call's
    // late-running continuation can still open the gate for it.
    session.setBusinessBlocked(false);
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
 * subscribe to onAuthStateChange, THEN run the first check against
 * getSession() -- in that order, so no session change delivered while
 * getSession() is in flight is ever missed (module docstring,
 * property 1). Returns the Supabase client so app.js can wire the
 * login form and sign-out button to it, or null if /api/config, client
 * creation, or the initial getSession() failed.
 *
 * A THIRD property, fixed after an independent review of the
 * generation-guard fix (75aa03c) found it insufficient on its own:
 *
 *   3. getSession()'s return value is a SNAPSHOT taken at the moment it
 *      was called -- not "the current session" by the time it resolves.
 *      If a real onAuthStateChange event (SIGNED_IN, SIGNED_OUT, a
 *      token refresh) arrives while that call is still pending, the
 *      event is strictly newer information, even though the pending
 *      getSession() call's own verify() would start LATER (and so get
 *      a HIGHER `generation`) than the event's. The `generation` guard
 *      alone does not distinguish "started later" from "describes
 *      newer reality" -- it would let this late-arriving, stale
 *      snapshot win and silently revert both session.current and the
 *      rendered state back to a session that had already been
 *      superseded. Fixed with a boolean, `sessionEventSeen`, set the
 *      instant any real event is delivered: once true, getSession()'s
 *      own result (success OR failure) is discarded outright -- never
 *      applied to session.js, never handed to verify() -- because a
 *      real event is always trusted over a snapshot taken before it. */
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

  // `window.supabase` is undefined if the CDN request failed or its
  // SRI hash didn't match -- createClient() then throws a TypeError.
  // The original phase-4 app.js guarded exactly this (its own comment:
  // "without this, stuck on loading forever with no visible error");
  // that guarantee is restored here after being dropped in this
  // checkpoint's first draft. Nothing else has happened yet at this
  // point (no subscription exists), so any failure here is
  // unconditionally fatal.
  try {
    client = window.supabase.createClient(
      config.supabase_url,
      config.supabase_publishable_key
    );
  } catch {
    onState({ kind: "config-error", session: null, user: null });
    return null;
  }

  // Subscribed before the getSession() call below -- see module
  // docstring, property 1.
  let sessionEventSeen = false;
  client.auth.onAuthStateChange((event, nextSession) => {
    sessionEventSeen = true;
    session.applySessionChange(event, nextSession);
    verify(nextSession, event);
  });

  try {
    const { data } = await client.auth.getSession();
    if (!sessionEventSeen) {
      session.applySessionChange("INITIAL", data.session);
      await verify(data.session, "INITIAL");
    }
    // else: a real event already fired and is already being (or has
    // already been) verified -- this snapshot predates it and is
    // discarded whole, per property 3 above.
  } catch {
    if (!sessionEventSeen) {
      onState({ kind: "config-error", session: null, user: null });
      return null;
    }
    // else: a real event already gave a better answer than this
    // failed, now-irrelevant snapshot attempt.
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
