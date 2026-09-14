"use strict";

// FunnelIQ session manager (phase 11, checkpoint 1, P11-D14).
//
// Tracks a global, monotonically increasing "epoch" used to discard
// stale in-flight responses, and decides -- from two documented
// top-level Session fields only (`user.id` + `access_token`), never
// from an unverified JWT claim or from an event name alone -- when a
// session change is real enough to raise it. See docs/planning/PHASE11.md
// P11-D14 for the full decision table this implements verbatim,
// including the "שני צירים נפרדים" split this module is built around:
// raising the epoch (cancels in-flight requests) and clearing state
// (wipes form data) are separate operations with separate triggers --
// every state-clear also raises the epoch, but not every epoch raise
// clears state.

let epoch = 0;
let current = null; // the last known Supabase Session, or null
let businessBlocked = false;
const listeners = new Set();

/** Same session, by the two documented top-level fields this whole
 * module is deliberately built around -- not by object identity, and
 * not by any JWT claim (P11-D14, "תלות בעובדות לא-מאומתות"). */
export function isSameSession(a, b) {
  if (a === b) return true;
  if (!a || !b) return false;
  return a.user?.id === b.user?.id && a.access_token === b.access_token;
}

function notify(detail) {
  for (const fn of listeners) fn(detail);
}

/** Subscribe to session-relevant transitions. Callback receives
 * {session, epoch, epochRaised, stateCleared, reason}. Returns an
 * unsubscribe function. */
export function onSessionEvent(fn) {
  listeners.add(fn);
  return () => listeners.delete(fn);
}

export function getEpoch() {
  return epoch;
}

export function getSession() {
  return current;
}

/** True if `responseEpoch` (captured by the caller at request-send
 * time) is still the current epoch. Callers use this to decide whether
 * a response that just arrived may still be rendered. */
export function isCurrentEpoch(responseEpoch) {
  return responseEpoch === epoch;
}

/** Set by bootstrap.js on every /api/me result: true on 503/500 (new
 * business calls wait for a successful retry), false on 200. Read by
 * the future api.js module (checkpoint 2) before firing a business
 * request -- checkpoint 1 only owns the flag itself, not a consumer. */
export function isBusinessBlocked() {
  return businessBlocked;
}

export function setBusinessBlocked(value) {
  businessBlocked = Boolean(value);
}

/** Explicit transition driven by OUR OWN /api/me result, not by
 * supabase-js's onAuthStateChange -- there is no Session-object change
 * to compare here, just an authorization outcome:
 *   - 401: no/invalid/expired token -> epoch raise + state clear
 *     (IA.md §9.3; the form content is explicitly NOT kept).
 *   - 403: valid token, wrong/missing organization -> epoch raise +
 *     state clear (forbidden-notice shows no data at all, so any
 *     stale form state is moot, but the epoch still must rise to
 *     cancel whatever business request was in flight).
 * 503/500 never call this -- see P11-D14 "שני צירים נפרדים": neither
 * flag is set for infra/config trouble, on purpose. */
export function applyAuthResult(kind) {
  if (kind === "401" || kind === "403") {
    epoch += 1;
    notify({ session: current, epoch, epochRaised: true, stateCleared: true, reason: kind });
  }
}

/** Called for every Supabase session delivery -- the first getSession()
 * check and every later onAuthStateChange event alike. Implements the
 * P11-D14 table exactly:
 *   - null <-> session, in either direction: epoch raise + state clear.
 *   - same non-null-ness, `user.id` changes: epoch raise + state clear
 *     (a different person; content is never carried across identities).
 *   - same `user.id`, `access_token` changes, event is TOKEN_REFRESHED:
 *     neither flag -- this is that event's documented job (PHASE11.md
 *     "TOKEN_REFRESHED — ארבעה כללים"), and the JWT itself is still
 *     updated in memory by the caller reading `getSession()` fresh.
 *   - same `user.id`, `access_token` changes, any OTHER event (e.g. a
 *     SIGNED_IN delivered on an already-open tab): epoch raises --
 *     conservative, "might be a new session" -- but state is NOT
 *     cleared. This only cancels an in-flight response; it does not
 *     wipe 12 filled-in fields over what may just be a routine token
 *     rotation delivered under a different event name.
 *   - same `user.id`, same `access_token`: neither flag -- this is the
 *     same session (e.g. SIGNED_IN re-delivered on tab focus).
 * The event name is consulted only inside the one branch above where
 * the mandatory data-based checks (null-transition, user.id-change)
 * have already both come back negative -- it never overrides them,
 * consistent with P11-D14's "אין להעלות epoch לפי שם האירוע" principle.
 */
export function applySessionChange(eventName, nextSession) {
  const prev = current;
  current = nextSession;

  const prevNull = prev === null;
  const nextNull = nextSession === null;

  let epochRaised = false;
  let stateCleared = false;

  if (prevNull !== nextNull) {
    epochRaised = true;
    stateCleared = true;
  } else if (!prevNull && !nextNull && prev.user?.id !== nextSession.user?.id) {
    epochRaised = true;
    stateCleared = true;
  } else if (!prevNull && !nextNull && prev.access_token !== nextSession.access_token) {
    if (eventName !== "TOKEN_REFRESHED") {
      epochRaised = true; // conservative: might be a new session
      // stateCleared stays false -- see docstring above.
    }
    // TOKEN_REFRESHED with the same user.id and a session before and
    // after: neither flag, by design.
  }
  // else: identical session (same user.id + same access_token) -- no-op.

  if (epochRaised) epoch += 1;
  notify({ session: current, epoch, epochRaised, stateCleared, reason: eventName });
  return { epochRaised, stateCleared };
}

/** Test-only reset -- not imported by any product code path. */
export function resetForTest() {
  epoch = 0;
  current = null;
  businessBlocked = false;
  listeners.clear();
}
