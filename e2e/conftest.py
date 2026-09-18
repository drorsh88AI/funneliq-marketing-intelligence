"""Phase 11 checkpoint 11 (PHASE11.md §ו) -- the zero-external-network
E2E harness. A REAL uvicorn subprocess serves the REAL, unmodified
frontend files (and /health, /api/config); EVERY other network request
the browser makes -- supabase-js itself, Supabase Auth, Supabase REST
(prefill), Google Fonts, and (except in the one happy-path case that
deliberately hits the real local /api/config) /api/me and the seven
business routes -- is intercepted at the BrowserContext level and
either mocked or blocked. Nothing in this file, or in any e2e/test_*.py
built on it, ever reaches the real internet.

Why the app itself never needs a live Supabase to validate a JWT in
these tests: /api/me and the seven business routes are intercepted and
answered by our OWN route() mocks before they ever reach the real
FastAPI process -- so app/auth.py's own `client.auth.get_user(token)`
(a real call to Supabase's Auth API) is never exercised here. That
server-side path already has its own coverage in tests/test_auth.py
(mocked at the Python level). This harness tests the FRONTEND's actual
behavior in a real browser against controlled, deterministic backend
responses -- not backend logic, which the rest of tests/ already owns.
"""
from __future__ import annotations

import contextlib
import json
import socket
import subprocess
import sys
import time
from pathlib import Path

import pytest
from playwright.sync_api import BrowserContext, Route

REPO_ROOT = Path(__file__).resolve().parent.parent
VENDOR_SUPABASE_JS = Path(__file__).resolve().parent / "vendor" / "supabase.min.js"

# Deliberately non-resolving (RFC 2606-style reserved-looking, though
# .invalid is the actual IANA-reserved TLD for exactly this purpose):
# PHASE11.md §ו's own safety net -- if a route() mock is ever missed,
# the backend subprocess's or a stray browser request's own attempt to
# reach this host fails at DNS resolution, not by silently reaching a
# real Supabase project.
DUMMY_SUPABASE_URL = "https://supabase.invalid"
DUMMY_PUBLISHABLE_KEY = "e2e-dummy-publishable-key"


@pytest.fixture(scope="session")
def browser_type_launch_args(browser_type_launch_args: dict) -> dict:
    """Overrides pytest-playwright's own default (no channel -> its
    bundled "chrome-headless-shell", which `playwright install
    chromium` could not download in this environment --
    cdn.playwright.dev is unreachable from this sandbox, confirmed by
    two independent timeouts).

    ⚠ NOT the same as overriding the `browser_channel` fixture: that
    fixture only reads `pytestconfig.getoption("--browser-channel")`
    and is never actually consulted by browser_type_launch_args itself
    (verified by reading pytest_playwright's own source after an
    override of THAT fixture silently had no effect -- the failure was
    still launching chrome-headless-shell). This is the fixture that
    actually feeds BrowserType.launch()'s kwargs.

    Deviation from PHASE11.md §ו's own literal "פקודת Chromium" wording,
    approved explicitly by the user, 2026-09-15: drives the system's
    already-installed Google Chrome instead
    (C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe, verified
    present and functional before this was written). Trade-off, stated
    plainly: this is NOT a version Playwright pins for us -- it is
    whatever Chrome happens to be installed on the machine running these
    tests, which updates itself independently. CP11's own acceptance
    criterion ("מתועדת עם גרסת Playwright, גרסת הדפדפן ותאריך") is met by
    RECORDING the actual browser version used (see
    test_e2e_environment_is_documented in test_00_infrastructure.py),
    not by pinning the download."""
    return {**browser_type_launch_args, "channel": "chrome"}


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


@pytest.fixture
def app_server():
    """Function-scoped (⚠ NOT session-scoped -- see the finding below):
    one real `sys.executable -m uvicorn app.main:app` subprocess (⛔ never
    the bare `python` off PATH -- PHASE11.md §ו), dummy Supabase env (⛔
    zero real secrets), polled on /health until 200. Serves the REAL,
    unmodified static frontend; torn down at the end of EACH test.

    ⚠ Diagnostic finding, 2026-09-18: a session-scoped app_server (one
    uvicorn subprocess shared for the whole file) made the THIRD real
    Chrome full-page navigation in a run hang forever on `page.goto()`,
    stuck waiting for "load" (every navigation after the 2nd, too).
    Isolated via direct experiment, not assumed -- ruled out one cause at
    a time:
      1. A fresh Browser/BrowserContext per attempt (browser.new_context()
         isolation) did NOT help -- still hung on attempt 3.
      2. A fresh Playwright Node driver process per attempt did NOT help
         either -- still hung on attempt 3, so it wasn't the driver.
      3. Plain `urllib` GETs against the SAME server, interleaved right
         before the 3rd browser attempt, succeeded instantly -- so the
         server wasn't globally wedged for every client, only for a new
         real-Chrome full page load (many keep-alive connections opened,
         then abruptly severed by `browser.close()`).
      4. A FRESH uvicorn subprocess per attempt (this fixture's current
         shape), even with the SAME Browser instance reused across all
         attempts, passed every time, in ~0.5s each -- proving the shared
         uvicorn subprocess itself, not the browser, was accumulating the
         bad state (almost certainly Windows' asyncio Proactor loop +
         uvicorn's keep-alive connection handling degrading after two
         full sets of connections get severed by an abruptly-closed real
         Chrome process, rather than being closed gracefully).
    A fresh uvicorn subprocess per test costs ~0.5-0.9s of extra startup
    (verified above) -- cheap next to a suite that was hanging solid
    after two tests, and e2e/ already isn't part of the CI-gating
    `pytest -q` (pytest.ini's testpaths=tests), so this only affects the
    manual e2e run's own wall-clock time."""
    port = _free_port()
    base_url = f"http://127.0.0.1:{port}"
    env = {
        "SUPABASE_URL": DUMMY_SUPABASE_URL,
        "SUPABASE_PUBLISHABLE_KEY": DUMMY_PUBLISHABLE_KEY,
    }
    import os
    full_env = os.environ.copy()
    full_env.update(env)

    proc = subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "app.main:app", "--host", "127.0.0.1", "--port", str(port)],
        cwd=str(REPO_ROOT),
        env=full_env,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
    )
    try:
        deadline = time.time() + 20
        last_error = None
        import urllib.request
        import urllib.error
        while time.time() < deadline:
            if proc.poll() is not None:
                out = proc.stdout.read() if proc.stdout else ""
                raise RuntimeError(f"uvicorn exited early (code {proc.returncode}):\n{out}")
            try:
                with urllib.request.urlopen(f"{base_url}/health", timeout=1) as resp:
                    if resp.status == 200:
                        break
            except (urllib.error.URLError, ConnectionError) as e:
                last_error = e
            time.sleep(0.2)
        else:
            raise RuntimeError(f"uvicorn never became healthy on {base_url}: {last_error}")

        yield base_url
    finally:
        proc.terminate()
        with contextlib.suppress(subprocess.TimeoutExpired):
            proc.wait(timeout=10)
        if proc.poll() is None:
            proc.kill()
            proc.wait(timeout=10)


def _serve_vendored_supabase_js(route: Route) -> None:
    """PHASE11.md §ו's own table: Content-Type text/javascript +
    Access-Control-Allow-Origin: * are BOTH required -- without CORS the
    browser refuses to run SRI verification on a crossorigin="anonymous"
    <script>, per the fetch/SRI spec (opaque-vs-cors response distinction).
    The SRI hash already locked in index.html then verifies these exact
    bytes -- a self-check, not a bypass (see e2e/vendor/SOURCE.md)."""
    body = VENDOR_SUPABASE_JS.read_bytes()
    route.fulfill(
        status=200,
        headers={
            "Content-Type": "text/javascript",
            "Access-Control-Allow-Origin": "*",
        },
        body=body,
    )


SUPABASE_JS_CDN_URL = "https://cdn.jsdelivr.net/npm/@supabase/supabase-js@2.58.0/dist/umd/supabase.min.js"


def install_network_mocks(context: BrowserContext, *, unexpected_requests: list[str]) -> None:
    """Registers exactly ONE route() handler covering `**/*` -- the
    order-independent single-dispatcher shape PHASE11.md §ו itself
    recommends ("מומלץ — חסין לסדר").

    ⚠ Self-review finding, 2026-09-16, caught by actually running this
    against the real app before writing a single falsification-case
    test on top of it: an EARLIER version of this function registered
    the fonts/supabase-js mocks FIRST and a `**/*` catch-all LAST,
    reasoning (in a comment, never verified) that "a test's own later
    route naturally overrides an earlier one". That is backwards.
    PHASE11.md §ו's own text already says the opposite -- "ה-route
    שנרשם אחרון מקבל קדימות" (the LAST-registered route wins) -- and a
    live diagnostic run proved it concretely: supabase-js and Google
    Fonts both fell through to default-deny even though their own
    specific route() calls were registered, because the catch-all
    registered after them matched `**/*` and won every time. Rewritten
    as one function so there is only one place precedence can be wrong,
    and individual tests' own later context.route(...) calls (added
    AFTER this fixture-installed dispatcher) correctly override it for
    the specific URLs they claim -- the same last-registered-wins rule,
    now used in the direction that actually works.
    """

    def _dispatch(route: Route) -> None:
        url = route.request.url

        if "fonts.googleapis.com" in url or "fonts.gstatic.com" in url:
            route.abort("failed")
            return

        if url == SUPABASE_JS_CDN_URL:
            _serve_vendored_supabase_js(route)
            return

        # The real local server's own origin is never blocked -- tests
        # rely on the actual uvicorn process for static files, /health,
        # and (in the happy path only) /api/config. A test that wants a
        # SPECIFIC local-server API path mocked instead (e.g. /api/me,
        # one of the seven business routes) registers its own
        # context.route() for that exact path AFTER this fixture runs,
        # which -- being registered later -- takes precedence over this
        # dispatcher for that one URL, without needing this function to
        # know about it.
        if url.startswith("http://127.0.0.1:"):
            route.continue_()
            return

        unexpected_requests.append(url)
        route.abort("failed")

    context.route("**/*", _dispatch)


@pytest.fixture
def mocked_context(app_server, browser):
    """One BrowserContext per test (⛔ never Page-level routing --
    PHASE11.md §ו), service workers blocked at creation, the
    always-mocked externals installed. `unexpected_requests` is a list
    the test can assert is empty at the end -- any URL that fell through
    to default_deny lands here, turning a missed mock into a loud
    assertion failure instead of a silently-aborted request nobody
    noticed."""
    context = browser.new_context(service_workers="block")
    unexpected_requests: list[str] = []
    install_network_mocks(context, unexpected_requests=unexpected_requests)
    context.unexpected_requests = unexpected_requests  # type: ignore[attr-defined]
    context.e2e_base_url = app_server  # type: ignore[attr-defined]
    yield context
    context.close()


@pytest.fixture
def mocked_page(mocked_context: BrowserContext):
    """The common case: one page, already navigated to `/`. Falsification
    cases needing multiple tabs (none of the 30 do) would use
    mocked_context.new_page() directly instead."""
    page = mocked_context.new_page()
    page.goto(mocked_context.e2e_base_url)  # type: ignore[attr-defined]
    return page


def route_json(context: BrowserContext, url_pattern: str, payload: dict | list, *, status: int = 200) -> None:
    """Registers a JSON response for one URL pattern. Added AFTER
    install_network_mocks's own dispatcher (every test calls this from
    inside its own body, which runs after the mocked_context/mocked_page
    fixture already installed that dispatcher) -- Playwright's
    last-registered-wins rule then correctly makes THIS the winning
    handler for this one URL, same mechanism install_network_mocks's
    own docstring explains."""
    body = json.dumps(payload)
    context.route(url_pattern, lambda route: route.fulfill(status=status, content_type="application/json", body=body))


def route_status(context: BrowserContext, url_pattern: str, status: int, *, body: str = "") -> None:
    """A bare status code with no JSON body -- 401/403/500/503 fixtures
    that carry no response shape the frontend reads beyond the code
    itself (app/auth.py's own error responses aren't part of the
    Contract app/schemas.py owns)."""
    context.route(url_pattern, lambda route: route.fulfill(status=status, body=body))


def install_auth_mocks(
    context: BrowserContext,
    *,
    sign_in_ok: bool = True,
    user: dict | None = None,
    access_token: str = "fake-access-token-1",
    refresh_token: str = "fake-refresh-token-1",
) -> None:
    """Auth/v1/token (sign-in) and auth/v1/logout, in the EXACT shapes
    verified empirically against the real, unmodified supabase-js
    2.58.0 (not assumed from memory or docs) -- see the commit history
    for the diagnostic runs that established these. `sign_in_ok=False`
    mocks the real 400 invalid_grant shape GoTrue returns for a wrong
    password."""
    import fixtures as fx

    if sign_in_ok:
        body = json.dumps(fx.supabase_token_response(access_token=access_token, refresh_token=refresh_token, user=user or fx.supabase_user()))
        context.route("**/auth/v1/token?grant_type=password", lambda route: route.fulfill(status=200, content_type="application/json", body=body))
    else:
        err_body = json.dumps({"error": "invalid_grant", "error_description": "Invalid login credentials"})
        context.route("**/auth/v1/token?grant_type=password", lambda route: route.fulfill(status=400, content_type="application/json", body=err_body))

    context.route("**/auth/v1/logout*", lambda route: route.fulfill(status=204, body=""))


def sign_in(page, email: str = "demo@example.com", password: str = "rightpass") -> None:
    """Fills and submits the real login-form -- never a shortcut that
    bypasses app.js's own signInWithPassword() call, since several
    falsification cases care about exactly what happens around that
    call (timing, event ordering)."""
    page.wait_for_selector("#login-section:not([hidden])", timeout=10_000)
    page.fill("#login-form input[name=email]", email)
    page.fill("#login-form input[name=password]", password)
    page.click("#login-form button[type=submit]")


def sign_in_and_wait(page, context: BrowserContext, **kwargs) -> None:
    """install_auth_mocks + sign_in + wait for the shell -- the common
    setup path most falsification cases start from. Callers that need
    to control auth mocks more precisely (e.g. a wrong password, or a
    session that starts already-authenticated on page load) call the
    pieces directly instead."""
    install_auth_mocks(context, **kwargs)
    sign_in(page)
    page.wait_for_selector("#authenticated-shell:not([hidden])", timeout=10_000)


# ---------------------------------------------------------------------
# 9c/9d/9f's mechanism: a REAL TOKEN_REFRESHED or SIGNED_IN event, fired
# by the real vendored supabase-js client -- not simulated by hand.
#
# bootstrap.js's `client` (the object onAuthStateChange is actually
# subscribed on) is a module-private variable, never exposed on
# `window` by app code, and shouldn't be for production reasons. The
# capture below is a test-only shim at the SDK boundary: it wraps
# `window.supabase.createClient` (the ONE function app code actually
# calls) so that whatever client bootstrap.js creates is ALSO stashed
# on `window.__testClient` -- the real client, the real subscription,
# nothing about app.js/bootstrap.js touched or bypassed.
#
# Read directly out of e2e/vendor/supabase.min.js's own
# `_setSession()`: calling `client.auth.setSession({access_token,
# refresh_token})` decodes access_token's `exp` claim and picks one of
# two REAL code paths -- exp in the future calls `GET /auth/v1/user`
# and emits `SIGNED_IN` with that exact session; exp in the past calls
# `POST /auth/v1/token?grant_type=refresh_token` and emits
# `TOKEN_REFRESHED`. Both go through the SAME onAuthStateChange
# subscription bootstrap.js itself registered -- these are genuine
# events indistinguishable, from app.js's perspective, from a second
# tab signing in or a real background token rotation. Verified
# empirically before writing a single falsification-case test on top
# of it (see the commit history for the diagnostic run).
_CAPTURE_CLIENT_INIT_SCRIPT = """
(() => {
  let realSupabase;
  Object.defineProperty(window, 'supabase', {
    configurable: true,
    get() { return realSupabase; },
    set(value) {
      const originalCreateClient = value.createClient;
      value.createClient = (...args) => {
        const client = originalCreateClient(...args);
        window.__testClient = client;
        return client;
      };
      realSupabase = value;
    },
  });
})();
"""


def capture_supabase_client(context: BrowserContext) -> None:
    """Must be called BEFORE the page navigates (context-level init
    script -- applies to every page/navigation in this context), so it
    is in place before bootstrap.js's own `window.supabase.createClient`
    call runs. After the page loads, `window.__testClient` is the real
    client bootstrap.js is using."""
    context.add_init_script(_CAPTURE_CLIENT_INIT_SCRIPT)


def _set_session(page, *, access_token: str, refresh_token: str) -> dict:
    return page.evaluate(
        """async ({access_token, refresh_token}) => {
             const { data, error } = await window.__testClient.auth.setSession({access_token, refresh_token});
             return { error: error ? error.message : null, hasSession: !!data.session };
           }""",
        {"access_token": access_token, "refresh_token": refresh_token},
    )


def deliver_signed_in(context: BrowserContext, page, *, user: dict, access_token: str | None = None) -> dict:
    """Fires a REAL `SIGNED_IN` event carrying `user`/`access_token` --
    requires `capture_supabase_client(context)` to have run before the
    page navigated. Registers the `GET /auth/v1/user` mock this path
    needs (see module docstring above) and calls the real
    `setSession()` with a future-`exp` JWT, which is what makes
    supabase-js take the SIGNED_IN branch instead of the refresh one."""
    import fixtures as fx

    if access_token is None:
        access_token = fx.fake_jwt(sub=user["id"])
    context.route("**/auth/v1/user", lambda route: route.fulfill(status=200, content_type="application/json", body=json.dumps(user)))
    return _set_session(page, access_token=access_token, refresh_token="irrelevant-not-decoded")


def deliver_token_refreshed(context: BrowserContext, page, *, user: dict, new_access_token: str | None = None, new_refresh_token: str = "refreshed-refresh-token") -> dict:
    """Fires a REAL `TOKEN_REFRESHED` event carrying `new_access_token`
    -- requires `capture_supabase_client(context)` to have run before
    the page navigated. Registers the
    `POST /auth/v1/token?grant_type=refresh_token` mock this path
    needs, and calls the real `setSession()` with a PAST-`exp` JWT
    (any structurally-valid one -- its claims are never used once
    expired, only its expiry decides the branch), which is what makes
    supabase-js call the refresh endpoint instead of GET /auth/v1/user."""
    import fixtures as fx

    if new_access_token is None:
        new_access_token = fx.fake_jwt(sub=user["id"])
    refreshed_body = json.dumps({
        "access_token": new_access_token,
        "token_type": "bearer",
        "expires_in": 3600,
        "expires_at": int(time.time()) + 3600,
        "refresh_token": new_refresh_token,
        "user": user,
    })
    context.route("**/auth/v1/token?grant_type=refresh_token", lambda route: route.fulfill(status=200, content_type="application/json", body=refreshed_body))
    expired_token = fx.fake_jwt(sub=user["id"], exp=int(time.time()) - 3600)
    return _set_session(page, access_token=expired_token, refresh_token="some-refresh-token")


class DeferredRoute:
    """One in-flight HTTP request, held open until the test explicitly
    releases it -- the mechanism every falsification case whose whole
    point is "while a request is in flight" (1-5, 9c, 9d, 9f, 10, 11)
    needs: Playwright's route() handler itself becomes the pause point,
    since it is not required to call fulfill()/abort() synchronously."""

    def __init__(self) -> None:
        self._routes: list[Route] = []

    def _capture(self, route: Route) -> None:
        self._routes.append(route)

    def wait_for_capture(self, page, *, timeout: float = 5.0) -> None:
        deadline = time.time() + timeout
        while not self._routes:
            if time.time() > deadline:
                raise TimeoutError("no request arrived at the deferred route in time")
            page.wait_for_timeout(50)

    def release(self, *, status: int = 200, payload: dict | list | None = None, body: str = "") -> None:
        route = self._routes.pop(0)
        if payload is not None:
            route.fulfill(status=status, content_type="application/json", body=json.dumps(payload))
        else:
            route.fulfill(status=status, body=body)


def route_deferred(context: BrowserContext, url_pattern: str) -> DeferredRoute:
    """Registers a route that captures the Route object instead of
    resolving it -- .wait_for_capture() blocks until the request
    arrives, .release() resolves it whenever the test is ready."""
    deferred = DeferredRoute()
    context.route(url_pattern, deferred._capture)
    return deferred


def install_prefill_mock(context: BrowserContext, rows: list[dict], *, status: int = 200) -> None:
    """Mocks supabase-prefill.js's own REST call -- read directly out of
    that file: `client.from("funnel_records").select(columns).eq(...)
    .order(...).limit(...)`, which supabase-js's PostgREST client turns
    into `GET {supabase_url}/rest/v1/funnel_records?...`. Matches BOTH
    the shared form's and P4S's own separate prefill (different
    `select=` columns, same table/path) -- callers needing to
    distinguish them would register a narrower pattern afterward
    (last-registered-wins, same mechanism as every other route() in
    this file). PostgREST returns the row array directly as the body,
    not wrapped in an envelope."""
    context.route(
        "**/rest/v1/funnel_records*",
        lambda route: route.fulfill(status=status, content_type="application/json", body=json.dumps(rows)),
    )
