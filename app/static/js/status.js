"use strict";

// FunnelIQ shared status primitives (phase 11, checkpoint 2). Pure DOM
// builders -- no fetch, no state. Every screen checkpoint (3-8) renders
// its own content INTO the element one of these returns, instead of
// re-deriving the correct role/class each time.
//
// Roles per DESIGN.md §1.4/§2.1: panel-loading is always role="status";
// panel-error (and its forbidden-notice/auth-redirect variants) is
// always role="alert"; panel-empty carries NEITHER role (DESIGN.md's
// own component table lists "—" for it) -- nothing failed and nothing
// is loading, it just explains what's missing and what to do.

export function loadingElement(message) {
  const el = document.createElement("div");
  el.className = "panel-loading";
  el.setAttribute("role", "status");
  el.textContent = message;
  return el;
}

/** `onRetry`, if given, adds a "ניסיון חוזר" button (DESIGN.md's
 * panel-error/availability pattern). Omit it for a failure state that
 * explicitly forbids retry (e.g. forbidden-notice, IA.md §9.3: "בלי
 * ניסיון חוזר") -- callers build that exact, narrower case themselves
 * rather than passing `onRetry: undefined` here, since forbidden-notice
 * also forbids things (no data, no route back to Login) this generic
 * builder has no opinion on. */
export function errorElement(message, { onRetry } = {}) {
  const el = document.createElement("div");
  el.className = "panel-error";
  el.setAttribute("role", "alert");
  const p = document.createElement("p");
  p.textContent = message;
  el.appendChild(p);
  if (onRetry) {
    const button = document.createElement("button");
    button.type = "button";
    button.textContent = "ניסיון חוזר";
    button.addEventListener("click", onRetry);
    el.appendChild(button);
  }
  return el;
}

export function emptyElement(message) {
  const el = document.createElement("div");
  el.className = "panel-empty";
  el.textContent = message;
  return el;
}
