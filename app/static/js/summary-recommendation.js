"use strict";

// FunnelIQ summary-recommendation (phase 11, checkpoint 3, PHASE10.md
// D9 / DESIGN.md's own row: "רכיב D9 בן ארבע שכבות -- תשובה / מה זה
// אומר / מה כדאי לעשות / חשוב לדעת"). Present in all eight targets
// (Overview, P2, P3, P4, P4S, Budget Simulator, and Follow-up's two
// charts) -- one builder here so the four-layer structure and its
// labels are defined in exactly one place.
//
// The fourth layer ("חשוב לדעת") always carries --model-disclaimer
// styling (DESIGN.md's own note on this row: "model-disclaimer לשכבת
// 'חשוב לדעת'"). Deeper methodological detail (metrics, model_version,
// calibration) goes in a screen's own <details>/model-details, never
// here -- this component only ever holds the four layers themselves.

const LAYER_LABELS = {
  answer: "תשובה",
  meaning: "מה זה אומר",
  action: "מה כדאי לעשות",
  caveat: "חשוב לדעת",
};

/** All four strings are REQUIRED -- DESIGN.md: "התשובה, המשמעות
 * העסקית, הפעולה והמגבלה המהותית גלויות" -- there is no optional
 * layer. Each screen checkpoint supplies its own exact wording (a
 * fixed string, or one built from a locked template + live values --
 * never paraphrased). */
export function renderSummaryRecommendation({ answer, meaning, action, caveat }) {
  const el = document.createElement("section");
  el.className = "summary-recommendation";

  const layers = [
    ["answer", answer],
    ["meaning", meaning],
    ["action", action],
    ["caveat", caveat],
  ];

  for (const [key, text] of layers) {
    const layer = document.createElement("div");
    layer.className = `summary-layer summary-layer-${key}`;
    const label = document.createElement("span");
    label.className = "summary-layer-label";
    label.textContent = LAYER_LABELS[key];
    const value = document.createElement("p");
    value.className = "summary-layer-text";
    value.textContent = text;
    layer.appendChild(label);
    layer.appendChild(value);
    el.appendChild(layer);
  }

  return el;
}
