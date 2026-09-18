"use strict";

// FunnelIQ per-screen generation counter (phase 11, checkpoint 2,
// IA.md §9.4 / §9.4א).
//
// A SEPARATE primitive from session.js's `epoch` (checkpoint 1,
// P11-D14): epoch tracks SESSION-IDENTITY changes (sign-out, 401/403,
// a different user) and is ONE global instance shared by the whole
// app. A generation counter tracks UI-DRIVEN invalidation -- one of
// the 12 edited fields changed, a different example was requested,
// "נקה טופס" was confirmed -- and gets its OWN independent instance
// per screen: ONE shared by all three panels of the P2/P3/P4 form
// (P11-D3/P11-D4 -- never per-panel, or one panel's request would
// invalidate the other two's already-rendered answers), and a fully
// SEPARATE one for P4S (§9.4א). A response is only rendered if BOTH
// its generation and the epoch captured at send time are still
// current when it arrives -- this module owns only the generation
// half; api.js (and session.js) own the epoch half.

export function createGenerationCounter() {
  let value = 0;
  return {
    /** Call on every UI-driven invalidation event (IA.md §9.4/§9.4א's
     * own trigger lists). Returns the new value -- callers capture it
     * at request-send time, not at bump() time itself, if a request is
     * about to be issued in the same action. */
    bump() {
      value += 1;
      return value;
    },
    /** The current value, to capture alongside a request about to be sent. */
    current() {
      return value;
    },
    /** True if `captured` (from current(), at send time) is still the
     * counter's value -- false means something invalidated it since,
     * and the response it belongs to must be discarded silently, not
     * rendered (IA.md §9.4: "נזרקת בשקט, לא מרונדרת"). */
    isCurrent(captured) {
      return captured === value;
    },
  };
}
