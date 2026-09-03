"use strict";

// FunnelIQ login shell (phase 4, D3). No business data is fetched from the
// browser here -- that starts in phase 11. This file only: loads Supabase
// config, checks/watches session state, and drives login/signout.

const els = {
  loading: document.getElementById("loading"),
  configError: document.getElementById("config-error"),
  loginSection: document.getElementById("login-section"),
  loginForm: document.getElementById("login-form"),
  loginError: document.getElementById("login-error"),
  shellSection: document.getElementById("shell-section"),
  userEmail: document.getElementById("user-email"),
  signoutButton: document.getElementById("signout-button"),
};

function show(el) {
  el.hidden = false;
}
function hide(el) {
  el.hidden = true;
}

function showLogin() {
  hide(els.loading);
  hide(els.shellSection);
  show(els.loginSection);
}

function showShell(email) {
  hide(els.loading);
  hide(els.loginSection);
  els.userEmail.textContent = email;
  show(els.shellSection);
}

async function init() {
  // One try/catch covers config fetch AND client creation: if the
  // supabase-js CDN script was blocked or its SRI hash didn't match,
  // window.supabase is undefined and createClient() throws -- without this,
  // the page was stuck on "loading" forever with no visible error (A2).
  let client;
  try {
    const response = await fetch("/api/config");
    if (!response.ok) throw new Error("config request failed");
    const config = await response.json();
    client = window.supabase.createClient(
      config.supabase_url,
      config.supabase_publishable_key
    );
  } catch (err) {
    hide(els.loading);
    show(els.configError);
    return;
  }

  client.auth.onAuthStateChange((_event, session) => {
    if (session) {
      showShell(session.user.email);
    } else {
      showLogin();
    }
  });

  const { data } = await client.auth.getSession();
  if (data.session) {
    showShell(data.session.user.email);
  } else {
    showLogin();
  }

  els.loginForm.addEventListener("submit", async (event) => {
    event.preventDefault();
    hide(els.loginError);
    const email = els.loginForm.elements.email.value;
    const password = els.loginForm.elements.password.value;
    const { error } = await client.auth.signInWithPassword({ email, password });
    if (error) {
      els.loginError.textContent = "מייל או סיסמה שגויים";
      show(els.loginError);
    }
  });

  els.signoutButton.addEventListener("click", async () => {
    await client.auth.signOut();
  });
}

init();
