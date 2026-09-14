"use strict";

// FunnelIQ display formatting (phase 11, checkpoint 2). Pure functions,
// no DOM, no fetch -- every screen checkpoint (3-8) formats through
// this module so a locale/precision choice lives in exactly one place.
//
// `he-IL` per SPEC.md's own RTL conventions ("פורמט מטבע ₪ ב-he-IL עם
// מפרידי אלפים"). Verified in this runtime, not assumed:
//   Intl.NumberFormat("he-IL").format(50000)      -> "50,000"
//   Intl.NumberFormat("he-IL", 2dp).format(990.71) -> "990.71"
// -- exactly the digit grouping/decimal style every example in
// IA.md/DESIGN.md/SPEC.md already shows (₪50,000; ₪990.71; 46.35%).
// {style:"currency"} was tried and REJECTED: it renders the symbol
// AFTER the number with embedded RTL marks ("‏50,000 ‏₪"), contradicting
// the "₪50,000" placement used everywhere in the docs -- so currency
// values are built manually, `₪` prefixed onto a plain grouped number.

const GROUPED = (decimals) =>
  new Intl.NumberFormat("he-IL", {
    minimumFractionDigits: decimals,
    maximumFractionDigits: decimals,
  });

/** A plain number, he-IL grouped. `decimals` is the caller's own
 * choice -- each screen checkpoint grounds its precision in whatever
 * IA.md/DESIGN.md/SPEC.md precedent exists for that specific field
 * (this module does not guess a business rounding rule per field). */
export function formatNumber(value, { decimals = 0 } = {}) {
  return GROUPED(decimals).format(value);
}

/** `₪` + he-IL grouped number, matching "₪50,000" / "₪990.71" as shown
 * throughout the docs -- never Intl's {style:"currency"} (see header). */
export function formatCurrency(value, { decimals = 0 } = {}) {
  return `₪${GROUPED(decimals).format(value)}`;
}

/** `{X}%` from a 0-1 fraction (matches how every percentage-bearing
 * API field -- event_probability, base_rate -- is documented: a 0-1
 * float the UI multiplies by 100). Default 2 decimals: the only
 * concrete precision precedent anywhere in the docs is the base_rate
 * reference constants (46.35%, 42.71%, 53.65%) -- P4S's own score is
 * NOT built through this function at all (it has its own locked
 * Math.round(p*100) integer rule, PHASE8A.md D15ב); a screen that
 * wants a different precision passes its own `decimals`. */
export function formatPercent(fraction, { decimals = 2 } = {}) {
  return `${GROUPED(decimals).format(fraction * 100)}%`;
}

/** Wraps LTR content (a number, a currency figure, a model_version
 * string) for correct rendering inside RTL text, per IA.md §10 /
 * DESIGN.md: "מספרים... וסימני מטבע ב-LTR בתוך container של RTL".
 * Unicode directional isolate characters (U+2066/U+2069) -- correct
 * regardless of whether the caller inserts via textContent or
 * innerHTML, unlike a <span dir="ltr"> wrapper which only helps for
 * the innerHTML path. */
export function ltr(text) {
  return `⁦${text}⁩`;
}
