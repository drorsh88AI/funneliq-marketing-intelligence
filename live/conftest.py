"""Phase 12 checkpoint 1 (PHASE12.md P12-D2-D4, D10) -- the live
acceptance harness. Every test under live/ runs a real Chrome browser
against the REAL deployed service (https://funneliq.onrender.com), with
a real Supabase Auth sign-in and real PostgREST reads under RLS -- the
opposite of e2e/, which mocks the network on purpose (P11-D7). live/
exists to cover only what a mock cannot prove: real Auth, real RLS, real
model numbers, real cold start, real deployed-asset integrity, real
model_version. See PHASE12.md P12-D2's own table for the full list.

This harness is opt-in and interactive by construction (P12-D3):
demo-northbound's and demo-noorg's passwords are read once per session
via getpass, in memory only. Nothing here reads them from disk, from an
environment variable, or from argv, and nothing here ever prints them,
puts them in an assertion message, or lets Playwright capture them into
a trace/video/HAR/storage_state. `PHASE4.md` D5-alef's own local `.env`
comment lines (the demo users' passwords, kept there for the user's own
reference) are not read by this file and are not part of this harness.

Because the whole suite depends on a human typing a password, it must
NEVER run unattended: `pytest.ini`'s `testpaths = tests` already keeps
a bare `pytest`/`pytest -q` from collecting this directory at all (same
isolation as e2e/); on top of that, `pytest_configure` below refuses to
even start collecting live/'s own test files unless an explicit opt-in
environment variable is set -- checked BEFORE any getpass prompt, so a
deliberate-but-unauthorized `pytest live/` fails loud with one clear
message instead of hanging on a prompt no one asked for, or (worse)
silently skipping every test.
"""
from __future__ import annotations

import getpass
import os
from dataclasses import dataclass, field
from functools import lru_cache
from typing import Callable

import httpx
import pytest
from playwright.sync_api import BrowserContext, Page, Route

LIVE_BASE_URL = "https://funneliq.onrender.com"

# P12-D3: the only two accounts this harness is allowed to use --
# already the demo users phase 4 created and phase 9 exercised live.
DEMO_NORTHBOUND_EMAIL = "demo-northbound@funneliq.example.com"
DEMO_NOORG_EMAIL = "demo-noorg@funneliq.example.com"

# The explicit opt-in gate (P12-D3). Deliberately a single exact value,
# not a fuzzy truthy check -- ambiguity here is exactly what P12-D3
# exists to rule out.
OPT_IN_ENV_VAR = "FUNNELIQ_LIVE_ACCEPTANCE"
OPT_IN_ENV_VALUE = "1"


def _opt_in_is_set(env: dict) -> bool:
    """Pure predicate, unit-tested directly in test_00_infrastructure.py
    without going through pytest_configure (which would otherwise abort
    the whole test session that's trying to test it)."""
    return env.get(OPT_IN_ENV_VAR) == OPT_IN_ENV_VALUE


def _opt_in_message() -> str:
    return (
        f"live/ requires explicit opt-in: set {OPT_IN_ENV_VAR}={OPT_IN_ENV_VALUE} "
        "and run `pytest -s live/` yourself, interactively. This suite signs in "
        "with real demo credentials against the deployed service and will prompt "
        "for two passwords at a getpass prompt -- it must never run unattended, "
        "in CI, or from an agent with no human present to answer that prompt."
    )


def pytest_configure(config: pytest.Config) -> None:
    """The opt-in gate itself. Runs at pytest startup, before collection
    -- so an unauthorized `pytest live/` fails immediately, before any
    test file is even imported and long before any getpass prompt could
    appear. `pytest.exit` (not a raised exception) is the right tool
    here: it prints exactly the message below and stops the whole run
    with a non-zero exit code -- never a quiet, green-looking skip."""
    if not _opt_in_is_set(os.environ):
        pytest.exit(_opt_in_message(), returncode=1)


class LiveCredentialError(RuntimeError):
    """Raised by _prompt_password on EOF or an empty answer -- always a
    loud, named failure (pytest reports it as an ERROR on whatever test
    first requested the credentials fixture), never a silent skip."""


def _prompt_password(label: str, prompt: Callable[[str], str] = getpass.getpass) -> str:
    """`prompt` is injectable so test_00_infrastructure.py can exercise
    the EOF/empty-answer failure paths with a fake, without a real
    terminal and without ever needing a real password."""
    try:
        value = prompt(f"Password for {label}: ")
    except EOFError as exc:
        raise LiveCredentialError(
            "stdin is closed -- getpass cannot prompt. Re-run with `pytest -s "
            "live/` so pytest does not capture stdin."
        ) from exc
    if not value:
        raise LiveCredentialError(f"empty password entered for {label} -- refusing to continue")
    return value


@pytest.fixture(scope="session")
def demo_credentials() -> dict[str, str]:
    """P12-D3: prompted once per session, held in memory only. Only
    consumed the first time a test actually depends on this fixture --
    checkpoint 1's own self-checks never do, so running `pytest -s
    live/` today (before checkpoint 2's real sign-in cases exist) never
    prompts for a real password at all."""
    return {
        DEMO_NORTHBOUND_EMAIL: _prompt_password(DEMO_NORTHBOUND_EMAIL),
        DEMO_NOORG_EMAIL: _prompt_password(DEMO_NOORG_EMAIL),
    }


@pytest.fixture(scope="session")
def browser_type_launch_args(browser_type_launch_args: dict) -> dict:
    """Identical override and identical reason as e2e/conftest.py's own
    (PHASE11.md P11-D7's deviation, approved 2026-09-15): Playwright's
    bundled chrome-headless-shell can't be downloaded in this sandbox
    (cdn.playwright.dev is unreachable), so this drives the system's
    already-installed Google Chrome instead. Recorded, not pinned: see
    test_live_environment_is_documented below for the actual version
    used on each run."""
    return {**browser_type_launch_args, "channel": "chrome"}


def _fetch_live_config() -> dict[str, str]:
    """The actual, unmemoized network call. Never called directly by
    test code -- only through live_config()'s retry below."""
    response = httpx.get(f"{LIVE_BASE_URL}/api/config", timeout=30)
    response.raise_for_status()
    return response.json()


@lru_cache(maxsize=1)
def live_config() -> dict[str, str]:
    """A plain GET against the deployed app's own public config endpoint
    -- not Supabase, so P12-D4's guard doesn't apply to it. Used to
    discover supabase_url/supabase_publishable_key without ever putting
    either of them in a local .env: the live service already exposes
    them publicly, exactly as the browser itself does on every page
    load.

    Routed through a bounded, reported retry (P12-D7): a real
    httpx.ReadTimeout hitting this exact call has been observed in
    practice, and every other fixture in this file depends on it, so an
    unretried single attempt here would take the whole harness down on
    one bad round-trip. Memoized with `lru_cache` -- but only AFTER a
    successful call: `lru_cache` never caches a raised exception, so a
    RetryCounter that exhausts every attempt raises here and the next
    call (if any) starts a fresh retry sequence from attempt 1, rather
    than an unrelated recomputation caching a failure by accident."""
    counter = RetryCounter(max_attempts=3)
    config = counter.run(_fetch_live_config)
    print(f"live_config: succeeded after {counter.attempts} attempt(s)")
    return config


@dataclass
class RejectedWrite:
    method: str
    url: str


def install_zero_write_guard(context: BrowserContext, supabase_url: str) -> list[RejectedWrite]:
    """P12-D4 channel 1: a browser-context-level guard. Aborts any
    non-GET/HEAD request this context tries to send to Supabase's
    PostgREST endpoint (`{supabase_url}/rest/v1/**`) BEFORE Chromium
    ever dispatches it to the network -- `route.abort()` happens inside
    Playwright's own request-interception layer, upstream of the actual
    socket write. Returns the list the guard appends every rejection
    to, so a test can assert on it directly; the list stays empty for
    the whole zero-write run this phase requires.

    Deliberately does not special-case OPTIONS for CORS preflight.
    Verified empirically against the real deployment (three separate
    probes, including a third-party cross-origin target) that Chromium
    handles the preflight transparently below Playwright's own
    route()/`context.on("request")` interception layer -- it never
    appears there at all, for either a non-safelisted Content-Type or a
    non-safelisted custom header (e.g. Supabase's own `apikey`). Only
    the actual method-specific request (the one this guard exists to
    gate) reaches route(), and it is provably gated correctly: see
    test_browser_context_guard_rejects_non_get_before_it_reaches_the_network
    and test_browser_context_guard_does_not_block_get, both passing
    against the real deployment. Special-casing OPTIONS here would be an
    unverified guess about behavior this harness never actually
    observes."""
    rejected: list[RejectedWrite] = []

    def _guard(route: Route) -> None:
        request = route.request
        if request.method.upper() not in ("GET", "HEAD"):
            rejected.append(RejectedWrite(request.method, request.url))
            route.abort()
            return
        route.continue_()

    context.route(f"{supabase_url}/rest/v1/**", _guard)
    return rejected


@pytest.fixture
def live_context(browser):
    """A fresh, unrecorded BrowserContext against the live deployment,
    with P12-D4 channel 1 installed. No video, no HAR, no tracing --
    those are exactly the artifacts a leaked password could end up in,
    so this harness never turns them on at all rather than trying to
    scrub them after the fact. See
    test_live_source_never_enables_recording_or_reads_secrets_from_disk_or_env
    for the self-check (a runtime check isn't available -- Playwright's
    Python API doesn't expose whether an existing context has
    tracing/video/HAR enabled, so this is verified by confirming no
    call site in this file ever passes those options in the first
    place).

    `service_workers="block"` is deliberate, not incidental: Playwright
    documents that `route()` does not intercept requests served by an
    already-registered Service Worker, so a guard installed without
    this would be silently bypassable the moment any page here
    registers one. The FunnelIQ frontend does not register a service
    worker today (verified: no `serviceWorker` reference anywhere under
    app/static/), so this is defense in depth for a P12-D4 guarantee
    that must hold regardless of what the frontend does in the future,
    not a fix for an observed bypass."""
    config = live_config()
    context = browser.new_context(service_workers="block")
    context.live_supabase_url = config["supabase_url"]  # type: ignore[attr-defined]
    context.live_rejected_writes = install_zero_write_guard(  # type: ignore[attr-defined]
        context, config["supabase_url"]
    )
    yield context
    context.close()


@pytest.fixture
def live_page(live_context: BrowserContext) -> Page:
    """A convenience fixture for the common case: a page already
    navigated to LIVE_BASE_URL, with no setup needed before that first
    load. The one thing that must never be bypassed is `live_context`
    itself (and the P12-D4 channel-1 guard it installs) -- NOT this
    fixture specifically. A test that needs a listener or other setup
    registered BEFORE the first navigation (e.g. checkpoint 2's network
    assertions, which must not miss a request fired during
    sign_in_via_browser's own initial goto) correctly calls
    `live_context.new_page()` directly instead of using this fixture --
    that page is still guarded, since the guard lives on the context,
    not on how the page was created."""
    page = live_context.new_page()
    page.goto(LIVE_BASE_URL)
    return page


def sign_in_via_browser(page: Page, email: str, password: str) -> None:
    """Fills and submits the REAL login form against the live deployment
    -- the same selectors e2e/conftest.py's own sign_in() uses, since
    it's the same app.js code driving both. Reserved for checkpoint 2's
    real Auth cases; checkpoint 1 never calls this (it has no reason to
    sign in for a harness self-check), so it stays a plain helper here,
    not a fixture."""
    page.goto(LIVE_BASE_URL)
    page.wait_for_selector("#login-section:not([hidden])", timeout=30_000)
    page.fill("#login-form input[name=email]", email)
    page.fill("#login-form input[name=password]", password)
    page.click("#login-form button[type=submit]")


@dataclass
class PostgrestReadOnly:
    """P12-D4 channel 2: the only way live/ test code may talk to
    PostgREST directly, outside the browser (e.g. checkpoint 3's RLS
    checks). There is no method on this class that could send a write
    -- `get()` is the only public entry point, and the one dispatch
    path both `get()` and this class's own self-check share rejects
    anything else before any HTTP request is attempted, not just before
    it succeeds."""

    base_url: str
    publishable_key: str
    access_token: str | None = None
    rejected_attempts: list[str] = field(default_factory=list)

    def _headers(self) -> dict[str, str]:
        headers = {"apikey": self.publishable_key}
        if self.access_token:
            headers["Authorization"] = f"Bearer {self.access_token}"
        return headers

    def get(self, path: str, params: dict[str, str] | None = None) -> httpx.Response:
        return self._request("GET", path, params=params)

    def _request(self, method: str, path: str, **kwargs) -> httpx.Response:
        if method.upper() not in ("GET", "HEAD"):
            self.rejected_attempts.append(f"{method} {path}")
            raise RuntimeError(
                f"P12-D4 zero-write guard: refused to send {method} {path} to "
                "PostgREST -- this wrapper only ever sends GET/HEAD, and never "
                "reached the network for this call."
            )
        url = f"{self.base_url}/rest/v1{path}"
        return httpx.request(method, url, headers=self._headers(), timeout=30, **kwargs)


@pytest.fixture
def postgrest(live_context: BrowserContext) -> PostgrestReadOnly:
    """Session config is shared with live_context so both channels agree
    on the same supabase_url -- but this fixture never touches the
    browser itself, matching P12-D4's point that channel 2 exists
    precisely because channel 1 (browser routing) cannot see calls made
    outside the page."""
    return PostgrestReadOnly(
        base_url=live_context.live_supabase_url,  # type: ignore[attr-defined]
        publishable_key=live_config()["supabase_publishable_key"],
    )


@dataclass
class RetryCounter:
    """P12-D7: retry against a real, sometimes-flaky network is allowed,
    but must be counted and disclosed -- never a silent try/except that
    turns a real failure green. `.attempts` is the evidence a test
    prints/asserts on; there is no retry path here that does not update
    it.

    `retryable` is deliberately narrow: httpx's own transport-level
    errors (connection reset, DNS failure, read/connect timeout) --
    real network flakiness, and exactly the class of failure a real
    ReadTimeout against the live service demonstrated in practice.
    Deliberately NOT `Exception` in general: an `AssertionError` or any
    other exception outside this tuple is a genuine bug (in the harness
    or in what it's testing), not the network's fault, and must
    propagate on the very first attempt -- silently retrying it could
    turn a real, reproducible failure into a coincidental green pass on
    attempt 2 or 3. See
    test_retry_counter_does_not_retry_a_programming_error."""

    max_attempts: int = 3
    retryable: tuple[type[BaseException], ...] = (httpx.TransportError,)
    attempts: int = 0

    def run(self, fn: Callable[[], object]) -> object:
        last_exc: Exception | None = None
        for attempt in range(1, self.max_attempts + 1):
            self.attempts = attempt
            try:
                return fn()
            except self.retryable as exc:
                last_exc = exc
                print(f"live/ retry {attempt}/{self.max_attempts} after: {exc!r}")
        raise RuntimeError(f"exhausted {self.max_attempts} attempts") from last_exc
