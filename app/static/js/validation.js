"use strict";

// FunnelIQ shared-form validation (phase 11, checkpoint 4, IA.md §3.1/
// §3.2). Pure functions, no DOM -- five blocking rules, verbatim
// messages from the locked source. This is NOT an OOD check (SPEC.md
// § "מתי לא מציגים מספר") -- malformed input vs. valid-but-far-from-
// training-distribution input are two different things; OOD is
// evaluated server-side, per-panel, in checkpoint 5.

export const EDITABLE_FIELDS = [
  "ad_budget", "num_leads", "leads_answered",
  "followup_1", "followup_2", "followup_3", "followup_4", "followup_5",
  "closed", "calls_to_closed", "calls_to_not_closed", "customer_acquisition_cost",
];

/** followup_5 - closed, IA.md §3.1. Returns null (display: "טרם חושב")
 * if either source value is missing -- never guesses a value. */
export function deriveNotClosed(values) {
  const { followup_5, closed } = values;
  if (followup_5 === null || followup_5 === undefined) return null;
  if (closed === null || closed === undefined) return null;
  return followup_5 - closed;
}

/** Every violated rule, in the table's own order (IA.md §3.2). Each
 * item is {rule, message}; an empty array means the payload may be
 * submitted. `values` holds the 12 editable fields (number or null/
 * undefined for "not yet filled"). */
export function validateSharedForm(values) {
  const violations = [];
  const v = (name) => values[name];
  const isFilled = (name) => v(name) !== null && v(name) !== undefined && v(name) !== "";

  // Rule 5 first (completeness/non-negativity) -- the other four rules
  // compare fields to each other and would be meaningless to evaluate
  // against a missing or negative value.
  const missing = EDITABLE_FIELDS.filter((f) => !isFilled(f));
  // "שלמות" in rule 5's own name (IA.md §3.2 row 5) reuses the "שלם"
  // (integer) root deliberately -- §3.1's own base clause requires
  // every one of the 13 values to be "מספר שלם · סופי · אי-שלילי"
  // (integer, finite, non-negative), not merely present. A decimal
  // like 1.5 or a non-finite value from scientific-notation overflow
  // (e.g. "1e400" -> Infinity) is neither negative nor "missing" by the
  // old check, so it slipped through undetected and would only fail
  // server-side as a generic 422 (found in review; genuine gap, not
  // just a stricter client-side echo of the API's own StrictInt check).
  const malformed = EDITABLE_FIELDS.filter((f) => isFilled(f) && (!Number.isFinite(Number(v(f))) || !Number.isInteger(Number(v(f)))));
  const negative = EDITABLE_FIELDS.filter((f) => isFilled(f) && !malformed.includes(f) && Number(v(f)) < 0);
  if (missing.length > 0 || malformed.length > 0 || negative.length > 0) {
    violations.push({
      rule: 5,
      message: "יש להשלים ערך חוקי בכל שדה; ערך שלילי אינו חוקי",
      fields: [...missing, ...malformed, ...negative],
    });
    // The remaining four rules need every field filled and non-negative
    // to mean anything -- evaluating them against a missing/negative
    // value would produce a confusing SECOND message about the same
    // underlying problem, not a different one.
    return violations;
  }

  if (!(Number(v("num_leads")) > 0)) {
    violations.push({ rule: 1, message: "מספר הלידים חייב להיות גדול מאפס", fields: ["num_leads"] });
  }
  if (!(Number(v("leads_answered")) <= Number(v("num_leads")))) {
    violations.push({ rule: 2, message: "לידים שנענו אינו יכול לעלות על סך הלידים", fields: ["leads_answered", "num_leads"] });
  }
  const chain = ["leads_answered", "followup_1", "followup_2", "followup_3", "followup_4", "followup_5"];
  let chainOk = true;
  for (let i = 1; i < chain.length; i++) {
    if (!(Number(v(chain[i - 1])) >= Number(v(chain[i])))) chainOk = false;
  }
  if (!chainOk) {
    violations.push({ rule: 3, message: "שלבי המשפך חייבים לרדת או להישאר שווים", fields: chain });
  }
  const notClosed = deriveNotClosed(values);
  if (notClosed !== null && notClosed < 0) {
    violations.push({ rule: 4, message: "עסקאות שנסגרו אינן יכולות לעלות על הלידים שנותרו אחרי מעקב 5", fields: ["closed", "followup_5"] });
  }

  return violations;
}

// ---------------------------------------------------------------------
// P4S (checkpoint 6). IA.md §3א.2: the SAME three comparison rules as
// the shared form (num_leads>0 · leads_answered<=num_leads ·
// followup_1<=leads_answered, the first link of the shared chain, no
// further) plus non-negativity -- scoped to only these four fields.
// Rule 4 (closed vs followup_5) is explicitly "אינו ישים" here (no
// `closed`/`followup_5` on this screen at all). Message text reused
// verbatim from the identical shared-form rules above, since the rule
// itself is textually identical, only the field set is narrower.
// ---------------------------------------------------------------------

export const SUPER_CUSTOMER_FIELDS = ["ad_budget", "num_leads", "leads_answered", "followup_1"];

export function validateSuperCustomerForm(values) {
  const violations = [];
  const v = (name) => values[name];
  const isFilled = (name) => v(name) !== null && v(name) !== undefined && v(name) !== "";

  const missing = SUPER_CUSTOMER_FIELDS.filter((f) => !isFilled(f));
  // Same fix as validateSharedForm's own rule 5, same reasoning
  // (IA.md §3א.1: "כולם חובה · מספר שלם · סופי · אי-שלילי").
  const malformed = SUPER_CUSTOMER_FIELDS.filter((f) => isFilled(f) && (!Number.isFinite(Number(v(f))) || !Number.isInteger(Number(v(f)))));
  const negative = SUPER_CUSTOMER_FIELDS.filter((f) => isFilled(f) && !malformed.includes(f) && Number(v(f)) < 0);
  if (missing.length > 0 || malformed.length > 0 || negative.length > 0) {
    violations.push({
      rule: 5,
      message: "יש להשלים ערך חוקי בכל שדה; ערך שלילי אינו חוקי",
      fields: [...missing, ...malformed, ...negative],
    });
    return violations;
  }

  if (!(Number(v("num_leads")) > 0)) {
    violations.push({ rule: 1, message: "מספר הלידים חייב להיות גדול מאפס", fields: ["num_leads"] });
  }
  if (!(Number(v("leads_answered")) <= Number(v("num_leads")))) {
    violations.push({ rule: 2, message: "לידים שנענו אינו יכול לעלות על סך הלידים", fields: ["leads_answered", "num_leads"] });
  }
  if (!(Number(v("leads_answered")) >= Number(v("followup_1")))) {
    violations.push({ rule: 3, message: "שלבי המשפך חייבים לרדת או להישאר שווים", fields: ["leads_answered", "followup_1"] });
  }

  return violations;
}
