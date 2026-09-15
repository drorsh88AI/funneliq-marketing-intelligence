"""Phase 11 checkpoint 11 -- harness smoke tests. Not one of the 30
falsification cases (§י) -- proves the infrastructure itself (real
server, vendored supabase-js + SRI, default-deny, no session ⇒ Login
only) before any of those cases are layered on top of it.
"""
from __future__ import annotations

import datetime
import importlib.metadata


def test_e2e_environment_is_documented(browser):
    """PHASE11.md CP10/CP11's own acceptance line: "מתועדת עם גרסת
    Playwright, גרסת הדפדפן ותאריך". Printed (pytest -s) and asserted
    non-empty rather than hardcoded, since the whole point of using the
    system's own Chrome (see conftest.py's browser_type_launch_args
    override) is that this value is NOT pinned by us -- it must be read
    from the actual running browser, every run."""
    playwright_version = importlib.metadata.version("playwright")
    browser_version = browser.version
    today = datetime.date.today().isoformat()
    print(f"\ne2e environment: Playwright {playwright_version}, browser {browser_version}, {today}")
    assert playwright_version
    assert browser_version
    assert today


def test_unauthenticated_visitor_sees_login_only(mocked_context):
    """PHASE11.md CP1's own acceptance line: "מבקר לא מאומת רואה רק
    Login". A brand-new BrowserContext has no stored Supabase session,
    so bootstrap.js's own getSession() call resolves from empty local
    storage -- this test's own job is to PROVE whether that resolves
    without a network call at all (no assertion built on an unverified
    assumption): if supabase-js ever does hit the network here, it
    would show up in unexpected_requests and this test fails loudly
    rather than silently mocking something that was never verified
    necessary."""
    page = mocked_context.new_page()
    page.goto(f"{mocked_context.e2e_base_url}/")

    page.wait_for_selector("#login-section:not([hidden])", timeout=10_000)

    assert page.is_hidden("#authenticated-shell")
    assert page.is_hidden("#app-nav")
    assert page.is_hidden("#loading")
    assert page.is_hidden("#config-error")

    assert mocked_context.unexpected_requests == [], (
        f"unexpected network requests reached default_deny: {mocked_context.unexpected_requests}"
    )


def test_default_deny_actually_blocks_an_unmocked_request(mocked_context):
    """Self-check on the harness itself, not the product: proves
    default_deny really aborts a request that matches nothing more
    specific, rather than this whole mechanism being a no-op that
    happens to never get exercised. Uses a page.evaluate fetch to a
    made-up external host no other route() claims."""
    page = mocked_context.new_page()
    page.goto(f"{mocked_context.e2e_base_url}/")
    page.wait_for_load_state("networkidle")

    result = page.evaluate(
        """
        () => fetch('https://example-unmocked-host.invalid/ping')
          .then(() => 'unexpectedly succeeded')
          .catch((e) => 'rejected: ' + e.message)
        """
    )
    assert "rejected" in result
    assert any("example-unmocked-host.invalid" in u for u in mocked_context.unexpected_requests)
