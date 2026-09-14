"use strict";

// FunnelIQ SPA entry point (phase 11, checkpoint 1, P11-D2). Wires the
// seven-branch auth bootstrap (./js/bootstrap.js, P11-D13) and the hash
// router (./js/router.js, P11-D6) to the DOM. No business data is
// fetched from here -- screens 2-6 are empty placeholders until
// checkpoints 3-8 fill them in.

import * as bootstrapAuth from "./js/bootstrap.js";
import * as router from "./js/router.js";

const els = {
  loading: document.getElementById("loading"),
  configError: document.getElementById("config-error"),
  loginSection: document.getElementById("login-section"),
  loginForm: document.getElementById("login-form"),
  loginError: document.getElementById("login-error"),
  sessionExpiredNotice: document.getElementById("session-expired-notice"),
  shell: document.getElementById("authenticated-shell"),
  appNav: document.getElementById("app-nav"),
  userEmail: document.getElementById("user-email"),
  signoutButton: document.getElementById("signout-button"),
  forbiddenNotice: document.getElementById("forbidden-notice"),
  availabilityError: document.getElementById("availability-error"),
  availabilityErrorText: document.getElementById("availability-error-text"),
  availabilityRetry: document.getElementById("availability-retry"),
  appMain: document.getElementById("app-main"),
};

const AVAILABILITY_TEXT = {
  "503": "שירות ההתחברות אינו זמין כרגע. נסו שוב בעוד רגע.",
  "500": "אירעה שגיאה בבדיקת ההרשאה. נסו שוב; אם התקלה נמשכת, פנו לתמיכה.",
};

const SCREEN_ID_BY_ROUTE = {
  overview: "screen-overview",
  predict: "screen-predict",
  "super-customer": "screen-super-customer",
  budget: "screen-budget",
  followup: "screen-followup",
};

// Distinguishes "never signed in" from "was signed in, then 401'd" --
// only the latter shows the session-expired banner on the Login screen.
let hadSessionBefore = false;
// True once a 200 has ever been reached -- decides whether a later
// 503/500 replaces app-main (nothing to preserve, still bootstrapping)
// or layers alongside it (content is already on screen -- falsification
// case 9ו: a TOKEN_REFRESHED re-verify failure must not tear it down).
let hasEverShownShell = false;

function hideTopLevel() {
  els.loading.hidden = true;
  els.configError.hidden = true;
  els.loginSection.hidden = true;
  els.shell.hidden = true;
  els.appNav.hidden = true;
  els.forbiddenNotice.hidden = true;
  els.availabilityError.hidden = true;
}

function showRoute(route) {
  const activeId = SCREEN_ID_BY_ROUTE[route];
  for (const link of els.appNav.querySelectorAll("a[data-route]")) {
    if (link.dataset.route === route) {
      link.setAttribute("aria-current", "page");
    } else {
      link.removeAttribute("aria-current");
    }
  }
  for (const section of els.appMain.querySelectorAll("[data-screen]")) {
    section.hidden = section.id !== activeId;
  }
}

function onAuthState(state) {
  switch (state.kind) {
    case "config-error":
      hideTopLevel();
      els.configError.hidden = false;
      break;

    case "no-session":
      router.stop();
      hideTopLevel();
      els.loginSection.hidden = false;
      els.sessionExpiredNotice.hidden = true;
      hadSessionBefore = false;
      break;

    case "200":
      hasEverShownShell = true;
      hadSessionBefore = true;
      hideTopLevel();
      els.shell.hidden = false;
      els.appNav.hidden = false;
      els.appMain.hidden = false;
      els.userEmail.textContent = state.user.email;
      router.start(showRoute);
      break;

    case "401":
      router.stop();
      hideTopLevel();
      els.loginSection.hidden = false;
      els.sessionExpiredNotice.hidden = !hadSessionBefore;
      hadSessionBefore = false;
      hasEverShownShell = false;
      break;

    case "403":
      router.stop();
      hideTopLevel();
      els.shell.hidden = false;
      els.appMain.hidden = true;
      els.forbiddenNotice.hidden = false;
      hasEverShownShell = false;
      break;

    case "503":
    case "500":
      els.availabilityErrorText.textContent = AVAILABILITY_TEXT[state.kind];
      if (hasEverShownShell) {
        // Content is already rendered (a later re-verify, e.g. after
        // TOKEN_REFRESHED) -- leave the shell/nav/screens exactly as
        // they are (app-nav included -- it was already shown by the
        // prior "200") and only add the notice alongside them.
        els.shell.hidden = false;
        els.availabilityError.hidden = false;
      } else {
        // Bootstrap-time failure: we do not yet know whether this
        // visitor is even authorized, so the BLOCKED authenticated-shell
        // is a minimal one -- sign-out only, ⛔ no app-nav (IA.md §9.3:
        // "authenticated-shell... חסומים", and nav links to five
        // screens nobody has confirmed access to would be misleading).
        hideTopLevel();
        els.shell.hidden = false;
        els.availabilityError.hidden = false;
      }
      break;

    default:
      break;
  }
}

async function main() {
  els.availabilityRetry.addEventListener("click", () => {
    bootstrapAuth.retry();
  });

  const client = await bootstrapAuth.init(onAuthState);
  if (!client) return; // config-error already shown by onAuthState

  els.loginForm.addEventListener("submit", async (event) => {
    event.preventDefault();
    els.loginError.hidden = true;
    const email = els.loginForm.elements.email.value;
    const password = els.loginForm.elements.password.value;
    const { error } = await client.auth.signInWithPassword({ email, password });
    if (error) {
      els.loginError.textContent = "מייל או סיסמה שגויים";
      els.loginError.hidden = false;
    }
  });

  els.signoutButton.addEventListener("click", async () => {
    await client.auth.signOut();
  });
}

main();
