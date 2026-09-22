"""Phase 12 checkpoint 2 (PHASE12.md CP2, falsification case 1 in §ז) --
live authorization on the deployed service: demo-northbound reaches the
authenticated shell, demo-noorg gets a 403 with zero business data ever
reaching the browser, an anonymous caller gets 401, sign-out clears the
session, and the browser's back button cannot resurrect protected
content after sign-out.

Only test_no_token_returns_401 is credential-free. Every other test in
this file depends on demo_credentials and therefore prompts for the two
real demo passwords the first time pytest resolves that fixture -- per
P12-D3's own division of labor, Claude prepares and reviews this file
but does not run the credentialed tests; the user runs `pytest -s
live/test_01_permissions.py` and provides the (censored) output as
evidence.
"""
from __future__ import annotations

import httpx

from conftest import (
    DEMO_NOORG_EMAIL,
    DEMO_NORTHBOUND_EMAIL,
    LIVE_BASE_URL,
    sign_in_via_browser,
)

# The seven business routes (P12-D14), the Supabase prefill target, and
# business_facts.json -- PHASE12.md §ז case 1's exact claim is that NONE
# of these ever answers with a successful (2xx) response for demo-noorg,
# whether or not a request was even attempted.
#
# business_facts.json deserves its own explicit place here, not just
# membership in "business resources in general": it is a public static
# file (app/main.py's StaticFiles mount, same as style.css) with NO
# server-side auth gate at all -- unlike the seven API routes, which
# return 401/403 themselves if wrongly called, a request to this one
# URL succeeds with 200 unconditionally the moment it's sent. The only
# thing standing between demo-noorg and this data is that app.js's
# facts.init() is called solely from the "200" branch of onAuthState
# (app/static/app.js) -- a frontend-only gate this test must prove
# holds, since the server will never refuse the request itself.
BUSINESS_ROUTE_PATTERNS = (
    "/api/predict/ltv",
    "/api/predict/upsell",
    "/api/predict/referral",
    "/api/predict/super-customer",
    "/api/simulate/budget",
    "/api/insights/budget-tiers",
    "/api/insights/followup",
    "/rest/v1/funnel_records",
    "/business_facts.json",
)


def test_no_token_returns_401():
    """No browser, no credentials -- a plain anonymous GET against the
    live deployment's own /api/me. The one test in this file safe to
    run without a human present; it depends on nothing from
    demo_credentials."""
    response = httpx.get(f"{LIVE_BASE_URL}/api/me", timeout=30)
    assert response.status_code == 401


def test_demo_northbound_reaches_authenticated_shell(live_context, demo_credentials):
    """PHASE12.md CP2: 'demo-northbound ⇒ shell'.

    Uses live_context.new_page() directly, not the live_page fixture --
    sign_in_via_browser() already performs its own page.goto(), so
    live_page's own navigation would just be a redundant extra load
    against the live service."""
    page = live_context.new_page()
    sign_in_via_browser(page, DEMO_NORTHBOUND_EMAIL, demo_credentials[DEMO_NORTHBOUND_EMAIL])

    page.wait_for_selector("#authenticated-shell:not([hidden])", timeout=30_000)
    page.wait_for_selector("#app-nav:not([hidden])", timeout=30_000)
    assert page.is_hidden("#login-section")
    assert page.is_hidden("#forbidden-notice")


def test_demo_noorg_gets_403_with_no_business_data_over_the_network(live_context, demo_credentials):
    """PHASE12.md §ז case 1, verbatim: '⛔ אף נתון עסקי אינו מגיע לדפדפן
    אפילו לרגע... נמדד ברמת הרשת... ⛔ לא בבדיקת DOM בסוף'. The response
    listener is registered on a page created directly from live_context
    -- BEFORE sign_in_via_browser's own first goto() -- so no window,
    however short, is left unwatched. Matches
    e2e/test_01_bootstrap_auth.py's own test_case_9's precedent for
    exactly this timing concern (mocked_page there navigates before the
    test body runs; a page built fresh from the context does not)."""
    business_responses: list[tuple[str, str, int]] = []

    page = live_context.new_page()
    api_me_responses: list[int] = []

    def _track(response):
        if "/api/me" in response.url:
            api_me_responses.append(response.status)
        if any(pattern in response.url for pattern in BUSINESS_ROUTE_PATTERNS):
            business_responses.append((response.request.method, response.url, response.status))

    page.on("response", _track)

    sign_in_via_browser(page, DEMO_NOORG_EMAIL, demo_credentials[DEMO_NOORG_EMAIL])
    page.wait_for_selector("#forbidden-notice:not([hidden])", timeout=30_000)

    # forbidden-notice is a UI symptom, not proof of the HTTP status that
    # caused it -- app.js's own "403" case is the only code path that
    # shows it, but asserting on the DOM alone leaves that link implicit.
    # The real claim this checkpoint makes is about the network exchange
    # itself: /api/me actually answered 403 for this user.
    assert 403 in api_me_responses, f"/api/me never returned 403 for demo-noorg: {api_me_responses}"

    successful = [r for r in business_responses if 200 <= r[2] < 300]
    assert successful == [], f"business data reached the browser for demo-noorg: {successful}"

    # Supplementary DOM check -- not the falsification proof itself
    # (an empty DOM at the end doesn't prove nothing was shown along the
    # way, per §ז's own wording), but confirms the visible symptom
    # matches the network-level guarantees above.
    assert page.is_hidden("#app-nav")
    assert page.is_hidden("#app-main")
    assert "גישה" in page.text_content("#forbidden-notice")


def test_sign_out_returns_to_login_and_clears_session(live_context, demo_credentials):
    """PHASE12.md CP2: 'sign-out מנקה'.

    Self-review finding: asserting on the DOM right after sign-out only
    proves the in-memory JS state changed -- it says nothing about
    whether the persisted Supabase session (the thing a page reload
    actually rehydrates from) was really cleared. A page.reload() after
    sign-out is the real behavioral proof: if signOut() left a stale
    session behind, reload would sign the user straight back into the
    shell with no form to fill in."""
    page = live_context.new_page()
    sign_in_via_browser(page, DEMO_NORTHBOUND_EMAIL, demo_credentials[DEMO_NORTHBOUND_EMAIL])
    page.wait_for_selector("#authenticated-shell:not([hidden])", timeout=30_000)

    page.click("#signout-button")
    page.wait_for_selector("#login-section:not([hidden])", timeout=30_000)
    assert page.is_hidden("#authenticated-shell")

    page.reload()
    page.wait_for_selector("#login-section:not([hidden])", timeout=30_000)
    assert page.is_hidden("#authenticated-shell"), (
        "authenticated-shell reappeared after reload -- the session "
        "was not actually cleared, only the UI was"
    )


def test_back_button_after_sign_out_does_not_expose_protected_content(live_context, demo_credentials):
    """PHASE12.md CP2: 'חזרה אחורה בדפדפן ⛔ אינה חושפת תוכן מוגן'.

    router.js's own stop() (P11-D6) removes the hashchange listener
    entirely on sign-out.

    Self-review finding: checking only #login-section/#authenticated-
    shell visibility after go_back() cannot actually detect a
    regression in that removal. app.js's hideTopLevel() -- called from
    the UNRELATED 'no-session' auth-state branch that sign-out itself
    triggers -- already hides #authenticated-shell and shows
    #login-section the moment sign-out completes, independent of the
    router entirely. showRoute() (the router's own callback) never
    touches either of those elements -- it only toggles [data-screen]
    hidden attributes and nav aria-current, nested inside an
    already-hidden #authenticated-shell either way. So those two
    assertions would pass identically whether or not a stray
    hashchange fired after sign-out, giving false confidence about the
    exact guarantee this test exists to check.

    The real, observable signal is whether ANY such router-driven
    mutation happens at all after sign-out -- watched directly via
    MutationObserver, the same technique
    e2e/test_01_bootstrap_auth.py's own test_case_9b uses for an
    equivalent 'never became active' claim."""
    page = live_context.new_page()
    sign_in_via_browser(page, DEMO_NORTHBOUND_EMAIL, demo_credentials[DEMO_NORTHBOUND_EMAIL])
    page.wait_for_selector("#authenticated-shell:not([hidden])", timeout=30_000)

    page.click('a[data-route="budget"]')
    page.wait_for_selector("#screen-budget:not([hidden])", timeout=30_000)

    page.click("#signout-button")
    page.wait_for_selector("#login-section:not([hidden])", timeout=30_000)

    page.evaluate(
        """() => {
            window.__routerMutatedAfterSignout = false;
            const onMutate = () => { window.__routerMutatedAfterSignout = true; };
            const mainObserver = new MutationObserver(onMutate);
            mainObserver.observe(document.getElementById('app-main'), {
                attributes: true, subtree: true, attributeFilter: ['hidden'],
            });
            const navObserver = new MutationObserver(onMutate);
            navObserver.observe(document.getElementById('app-nav'), {
                attributes: true, subtree: true, attributeFilter: ['aria-current'],
            });
        }"""
    )

    page.go_back()
    page.wait_for_timeout(500)  # let any stray hashchange/render settle

    assert page.evaluate("() => window.__routerMutatedAfterSignout") is False, (
        "the router reacted to a hash change after sign-out -- its "
        "hashchange listener was not actually removed"
    )
    # Supplementary: the visible symptom still matches, though (per the
    # finding above) this alone cannot prove the router-level claim.
    assert page.is_visible("#login-section")
    assert page.is_hidden("#authenticated-shell")
