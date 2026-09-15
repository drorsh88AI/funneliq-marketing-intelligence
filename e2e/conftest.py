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


@pytest.fixture(scope="session")
def app_server():
    """Session-scoped: one real `sys.executable -m uvicorn app.main:app`
    subprocess (⛔ never the bare `python` off PATH -- PHASE11.md §ו),
    dummy Supabase env (⛔ zero real secrets), polled on /health until
    200. Serves the REAL, unmodified static frontend for every test in
    this run; torn down once at the end of the session."""
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
