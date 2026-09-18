"""PHASE11.md §י, cases 6-9ב -- bootstrap/auth falsification cases."""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import fixtures as fx
from conftest import install_auth_mocks, route_json, route_status, sign_in, sign_in_and_wait


def test_case_6_forbidden_no_data_no_retry_signout_available(mocked_page, mocked_context):
    """6. 403 ⇒ ללא נתונים, ללא ניסיון חוזר, ללא הפניה ל-Login, פקד יציאה זמין."""
    install_auth_mocks(mocked_context)
    route_status(mocked_context, "**/api/me", 403)
    sign_in(mocked_page)

    mocked_page.wait_for_selector("#forbidden-notice:not([hidden])", timeout=10_000)
    assert mocked_page.is_hidden("#login-section")
    assert mocked_page.is_hidden("#app-main")
    text = mocked_page.text_content("#forbidden-notice")
    assert "גישה" in text  # index.html's own literal text: "אין לכם הרשאת גישה למערכת הזו"
    # ⛔ no retry control inside forbidden-notice
    assert mocked_page.query_selector("#forbidden-notice button") is None
    # sign-out stays available (inside authenticated-shell, which 403 still shows)
    assert mocked_page.is_visible("#signout-button")
    assert mocked_context.unexpected_requests == []


def test_case_7_401_mid_session_shows_login_form_not_preserved(mocked_page, mocked_context):
    """7. 401 באמצע session ⇒ מסך התחברות; תוכן הטופס אינו נשמר."""
    route_json(mocked_context, "**/api/me", fx.api_me())
    route_json(mocked_context, "**/api/insights/budget-tiers", fx.budget_tiers_response())
    route_json(mocked_context, "**/rest/v1/funnel_records*", [])
    sign_in_and_wait(mocked_page, mocked_context)

    mocked_page.click('a[data-route="predict"]')
    mocked_page.wait_for_selector("#field-ad_budget")
    # All 12 fields, valid per the five rules (IA.md §3.2), so the submit
    # button is actually enabled -- a disabled-button click would fire no
    # request at all and prove nothing about the 401 path.
    values = {
        "ad_budget": "5000", "num_leads": "100", "leads_answered": "80",
        "followup_1": "70", "followup_2": "60", "followup_3": "50",
        "followup_4": "40", "followup_5": "30", "closed": "10",
        "calls_to_closed": "3", "calls_to_not_closed": "2",
        "customer_acquisition_cost": "500",
    }
    for field, value in values.items():
        mocked_page.fill(f"#field-{field}", value)
    mocked_page.check(".context-confirmation input[type=checkbox]")
    assert mocked_page.input_value("#field-ad_budget") == "5000"
    assert not mocked_page.is_disabled(".submit-button")

    # A business call 401ing mid-session -- routed through the SAME
    # handler as bootstrap's own onAuthState (api.js's own design).
    route_status(mocked_context, "**/api/predict/ltv", 401)
    route_status(mocked_context, "**/api/predict/upsell", 401)
    route_status(mocked_context, "**/api/predict/referral", 401)
    mocked_page.click(".submit-button")

    mocked_page.wait_for_selector("#login-section:not([hidden])", timeout=10_000)
    assert mocked_page.is_hidden("#authenticated-shell")
    # Revisiting predict after a fresh (still-401ing in this test) sign-in
    # attempt is out of scope here -- the content-not-preserved claim is
    # checked structurally: the field input node itself was torn down
    # with the rest of authenticated-shell, not merely visually hidden.
    assert mocked_page.query_selector("#field-ad_budget") is None


def test_case_8_bootstrap_503_then_retry_succeeds(mocked_page, mocked_context):
    """8. /api/me מחזיר 503 ⇒ שגיאת זמינות + ניסיון חוזר; session נשמר,
    shell חסום עד Retry מוצלח."""
    install_auth_mocks(mocked_context)
    route_status(mocked_context, "**/api/me", 503)
    sign_in(mocked_page)

    mocked_page.wait_for_selector("#availability-error:not([hidden])", timeout=10_000)
    # Bootstrap-time failure: minimal blocked shell, sign-out only, no app-nav.
    assert mocked_page.is_hidden("#app-nav")
    assert mocked_page.is_visible("#signout-button")
    assert mocked_page.is_visible("#availability-retry")

    route_json(mocked_context, "**/api/me", fx.api_me())
    mocked_page.click("#availability-retry")
    mocked_page.wait_for_selector("#authenticated-shell:not([hidden])", timeout=10_000)
    # Self-review finding: asserting is_hidden() on a DIFFERENT element
    # immediately after wait_for_selector() resolved on authenticated-shell
    # was flaky -- both are set hidden/unhidden synchronously in the same
    # app.js case block (confirmed via a direct getComputedStyle check:
    # 'display: none', not a real product bug), but is_hidden() called
    # right after an unrelated selector's own wait occasionally raced
    # Playwright's own snapshot. Waiting on availability-error's OWN
    # hidden state directly is the correct, non-flaky check.
    mocked_page.wait_for_selector("#availability-error", state="hidden", timeout=10_000)
    assert mocked_page.is_visible("#app-nav")


def test_case_9_config_failure_no_login_no_shell(mocked_context):
    """9. כשל /api/config ⇒ הודעת טעינת הגדרות; אין Login פעיל ואין shell.

    Self-review finding: the `mocked_page` fixture navigates the moment
    it is created, BEFORE this test's own body ever runs -- so a route()
    registered afterward (as the first version of this test did) misses
    the real, already-in-flight /api/config request entirely, and the
    app boots normally into "no session" instead of config-error. Any
    test that needs to control a request fired during the VERY FIRST
    page load must build its own page from `mocked_context` directly,
    registering routes before navigating -- not use `mocked_page`."""
    route_status(mocked_context, "**/api/config", 500)
    page = mocked_context.new_page()
    page.goto(mocked_context.e2e_base_url)  # type: ignore[attr-defined]
    page.wait_for_selector("#config-error:not([hidden])", timeout=10_000)
    assert page.is_hidden("#login-section")
    assert page.is_hidden("#authenticated-shell")
    assert page.is_hidden("#loading")


def test_case_9a_no_session_zero_api_me_requests(mocked_context):
    """9א. getSession() מחזיר null ⇒ Login, ואפס בקשות ל-/api/me."""
    me_calls = []
    mocked_context.route("**/api/me", lambda route: (me_calls.append(1), route.abort("failed")))
    page = mocked_context.new_page()
    page.goto(mocked_context.e2e_base_url)  # type: ignore[attr-defined]
    page.wait_for_selector("#login-section:not([hidden])", timeout=10_000)
    page.wait_for_timeout(500)  # let any stray async call surface
    assert me_calls == []
    assert mocked_context.unexpected_requests == []


def test_case_9b_signed_in_wrong_organization_never_shows_shell(mocked_page, mocked_context):
    """9ב. SIGNED_IN עם session תקין אך organization ≠ northbound ⇒ 403;
    authenticated-shell לא הוצג לרגע.

    Self-review finding: #authenticated-shell is the SHARED wrapper for
    BOTH the authenticated nav/content AND #forbidden-notice itself
    (forbidden-notice is a CHILD of authenticated-shell in index.html) --
    app.js's own "403" case deliberately unhides the wrapper (so
    forbidden-notice can be seen at all) while keeping #app-main hidden.
    An earlier version of this test watched #authenticated-shell's own
    hidden attribute and failed on that intentional, correct behavior.
    The falsification case's real claim -- authenticated CONTENT
    (app-nav, app-main) is never shown -- is checked on THOSE elements
    instead."""
    install_auth_mocks(mocked_context, user=fx.supabase_user(organization="acme-other"))
    route_status(mocked_context, "**/api/me", 403)

    watch_ever_visible = mocked_page.evaluate(
        """
        () => {
          window.__navOrMainSeenVisible = false;
          const check = () => {
            const nav = document.getElementById('app-nav');
            const main = document.getElementById('app-main');
            if (!nav.hasAttribute('hidden') || !main.hasAttribute('hidden')) {
              window.__navOrMainSeenVisible = true;
            }
          };
          new MutationObserver(check).observe(document.getElementById('app-nav'), { attributes: true, attributeFilter: ['hidden'] });
          new MutationObserver(check).observe(document.getElementById('app-main'), { attributes: true, attributeFilter: ['hidden'] });
          return true;
        }
        """
    )
    assert watch_ever_visible

    sign_in(mocked_page)
    mocked_page.wait_for_selector("#forbidden-notice:not([hidden])", timeout=10_000)
    assert mocked_page.evaluate("() => window.__navOrMainSeenVisible") is False
    assert mocked_page.is_hidden("#app-nav")
    assert mocked_page.is_hidden("#app-main")
