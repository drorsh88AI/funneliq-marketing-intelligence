"use strict";

// FunnelIQ hash router (phase 11, checkpoint 1, P11-D6).
//
// Client-side only, by design: the hash fragment is never sent to the
// server, so a page reload or a direct/shared link always requests
// GET / from FastAPI regardless of what hash is in the address bar --
// no server-side fallback route exists or is needed (app/main.py mounts
// StaticFiles(html=True) at "/", which already serves index.html there).

const ROUTES = ["overview", "predict", "super-customer", "budget", "followup"];
const DEFAULT_ROUTE = "overview";

let started = false;
let currentRoute = null;
let onChangeCb = null;

function parseHash() {
  const raw = (location.hash || "").replace(/^#\/?/, "");
  return ROUTES.includes(raw) ? raw : null;
}

function applyRoute() {
  const parsed = parseHash();
  if (parsed === null) {
    // Unknown or empty hash -> #/overview (P11-D6). This function is
    // only ever reached after start(), which itself is only called
    // after a 200 from /api/me -- an unauthenticated visitor never
    // triggers this redirect, regardless of what hash they arrive
    // with (P11-D13).
    if (location.hash !== `#/${DEFAULT_ROUTE}`) {
      location.hash = `#/${DEFAULT_ROUTE}`;
      return; // the hashchange this triggers re-enters applyRoute()
    }
    currentRoute = DEFAULT_ROUTE;
  } else {
    currentRoute = parsed;
  }
  if (onChangeCb) onChangeCb(currentRoute);
}

function onHashChange() {
  applyRoute();
}

/** Starts routing and renders the current (or default) route
 * immediately. Must only be called after a successful (200) bootstrap. */
export function start(onChange) {
  onChangeCb = onChange;
  if (!started) {
    started = true;
    window.addEventListener("hashchange", onHashChange);
  }
  applyRoute();
}

/** Stops listening for hash changes -- called whenever the shell is
 * torn down (401/no-session/sign-out), so a stale route never renders
 * for a visitor who is no longer authorized to see it. */
export function stop() {
  if (started) {
    window.removeEventListener("hashchange", onHashChange);
    started = false;
  }
  currentRoute = null;
}

export function getCurrentRoute() {
  return currentRoute;
}

export function navigate(route) {
  if (!ROUTES.includes(route)) return;
  location.hash = `#/${route}`;
}

export const ROUTE_NAMES = ROUTES;
