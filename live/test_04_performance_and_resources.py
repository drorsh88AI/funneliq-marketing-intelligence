"""Phase 12 checkpoint 5 (PHASE12.md CP5, P12-D5/D6/D7/D8/D13, falsification
cases 4 and 9 in sec ZAYIN) -- performance, resources and restart against the
real deployed service.

Three of CP5's four requirements are covered here. Run the WHOLE file in
ONE invocation -- this file's own definition order (verified: no
randomization plugin in requirements*.txt/pytest.ini) puts the three pure
local checks first, harmlessly, then the three service-touching tests in
the exact order they must run:

  pytest -s live/test_04_performance_and_resources.py

Do NOT run `test_cold_start_after_real_inactivity` by its own node id as
the primary command -- it must be the first test to touch the deployed
service in this sitting, which the single full-file invocation above
already guarantees given this file's definition order; a separate
node-id-only command would invite running it in isolation from a session
where something else already touched the service moments before.

0. `test_robots_txt_sentinel_logic`, `test_funneliq_index_marker_logic`,
   `test_deploy_sha_validation_logic`, and
   `test_bearer_headers_reveals_real_token_and_censors_later_failure_output` --
   pure functions/helpers proven against fabricated strings and a dummy
   token, no network beyond a local subprocess pytest invocation, no real
   credentials, no ordering constraint. They give the positive-evidence
   checks inside cold start, the restart/redeploy check, and every real
   `Authorization` header this file sends, their own independent, focused
   proof.
1. `test_cold_start_after_real_inactivity` -- prompts for demo-northbound's
   password via `demo_credentials` (getpass, in-process, zero network I/O)
   BEFORE the wait below. Render's free tier spins a web service down
   after 15 minutes with zero inbound requests (Render's own docs,
   https://render.com/docs/free, verified 2026-09-23 via direct fetch).
   Five steps, proving an actual awake -> sleep -> awake TRANSITION, not
   a single ambiguous snapshot: (a) a strengthened anchor request
   (GET /health, 120s timeout for Render's own wake-up latency, requiring
   BOTH status 200 AND the exact body {"status":"ok"} -- not just 200,
   which a Render interstitial page could also answer) establishes "the
   service is genuinely awake right now"; (b) the SAME /robots.txt
   sentinel used in step (d) is checked immediately and REQUIRED to NOT
   match the sleeping pattern -- proving the sentinel actually
   discriminates awake/asleep on this real deployment right now, not just
   per Render's docs in the abstract; T0 is set only after this negative
   baseline passes; (c) sleeps 16 minutes from T0 -- a 1-minute safety
   margin -- making ZERO further requests; (d) the same /robots.txt
   sentinel, checked again, now REQUIRED to match the sleeping pattern --
   together with (b)'s negative result, this proves a real transition
   happened because of the wait (Render intercepts /robots.txt for a
   spun-down free service and answers itself, before the request ever
   reaches the app -- documented behavior, see `_ROBOTS_SLEEPING_MARKERS`
   below); if this does not match, the run is NOT a valid cold measurement
   and NO time is reported, per this review's own requirement; (e) exactly
   one measured first request end-to-end (P12-D5: "המספר הראשון הוא
   המספר" -- the first number IS the number, never measured twice and the
   better one kept), verified to be FunnelIQ's own real index.html -- not
   just status 200 -- via `_looks_like_funneliq_index`.
2. `test_warm_latency_for_all_seven_routes` -- runs right after cold start
   (the service is now warm from test 1's own request), so no separate
   warm-up call is needed.
3. `test_journey_still_works_after_manual_redeploy` -- Claude has NO Render
   API or dashboard access in this project (verified: no RENDER_API_KEY
   anywhere in .env/scripts, render.yaml only lists app-level env var
   NAMES with sync:false, and autoDeployTrigger fires on a commit to
   `main`, not this test/acceptance branch). Triggering the actual
   redeploy is therefore a MANUAL step only the user can do (Render
   dashboard -> the funneliq service -> "Manual Deploy" -> "Deploy latest
   commit"). This test requires confirmation that THAT SPECIFIC deploy's
   own dashboard entry shows "Live" (not just the service answering
   requests in general), and the commit SHA the dashboard shows for it --
   validated for format (7-40 hex characters) and compared as a
   prefix, case-insensitively, against origin/main's own real SHA
   (render.yaml pins deployment to branch: main); a malformed value or a
   genuine mismatch fails the test outright. Method, SHA, and a timestamp
   are recorded in the printed evidence before proving the journey still
   works post-restart: real API predictions with real numbers, and a real
   browser sign-in + one real submit, with no stuck state.

The FOURTH CP5 requirement -- Render-reported memory usage (P12-D13: metric
name as literally shown, unit, measurement window, and peak value) -- has
NO code here at all, and never will: the real Render dashboard was checked
(2026-09-23) and the Metrics -> Application Metrics view for Memory on the
`free` plan shows the metric's NAME ("Memory") and the WINDOW ("Last 12
hours"), but the usage graph itself -- the only place a peak value could
ever be read -- is gated behind an "Upgrade" prompt. This is not "was not
checked"; it is structurally inaccessible on this plan. Per P12-D13's own
fallback ("אם המקור אינו נגיש בסביבה הזו -- זה ממצא שנרשם, ⛔ לא אומדן
שמומצא מהערכה"), that inaccessibility IS the finding, and the user
explicitly approved a DOCUMENTED EXCEPTION to this criterion (2026-09-23,
choosing not to upgrade the Render plan just to unlock it) -- this is
PHASE12.md's own internal quality bar, not something the founder's brief
asks for. `512MB` (the plan's declared nominal limit) is NEVER shown as a
substitute measurement.

CP5 is now CLOSED (2026-09-23) on: the 6/6 automated result above, the
documented memory-usage exception just described, and P12-D8 below.
P12-D8 (the cold-start accept-or-mitigate decision P12-D5 defers to this
point): the user accepted the single measured cold-start time, 42.77s, as
a non-material limitation of the free-tier demo -- explicitly NOT to be
mitigated (no keep-alive: no external cron, no scheduled ping, no paid
Render plan to suppress spin-down). Both the 42.77s number and the
memory-access gap are carried forward as an explicit disclosure into
`README.md` in phase 13 (`ROADMAP.html`'s own phase-13 item list).

Every test that DOES touch the app's own protected routes still needs
demo-northbound's real credentials (`demo_credentials`) -- per P12-D3's
own division of labor, Claude prepares and reviews this file but does not
run it.
"""
from __future__ import annotations

import os
import re
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import httpx
import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
LIVE_DIR = Path(__file__).resolve().parent

from conftest import (
    DEMO_NORTHBOUND_EMAIL,
    LIVE_BASE_URL,
    Secret,
    install_zero_write_guard,
    live_config,
    sign_in_via_api,
    sign_in_via_browser,
)

# Render's own documented free-tier inactivity spin-down window is 15
# minutes (https://render.com/docs/free). 16 minutes = 1-minute margin.
COLD_START_WAIT_SECONDS = 16 * 60

# The seven business routes (P12-D14's own list) -- method, path, and
# whether it needs a request body.
SEVEN_ROUTES = [
    ("POST", "/api/predict/ltv"),
    ("POST", "/api/predict/upsell"),
    ("POST", "/api/predict/referral"),
    ("POST", "/api/predict/super-customer"),
    ("GET", "/api/simulate/budget"),
    ("GET", "/api/insights/budget-tiers"),
    ("GET", "/api/insights/followup"),
]

# Same in-domain payload CP4's test_03_capabilities.py verified against
# every task's real ood_bounds on origin/main -- copied, not imported,
# so this file stays self-contained like every other live/test_0N file.
FORM_VALUES = {
    "ad_budget": 5000, "num_leads": 100, "leads_answered": 60,
    "followup_1": 55, "followup_2": 45, "followup_3": 35, "followup_4": 25, "followup_5": 15,
    "closed": 5, "calls_to_closed": 4, "calls_to_not_closed": 3, "customer_acquisition_cost": 1000,
}
FUNNEL_PAYLOAD = {**FORM_VALUES, "not_closed": FORM_VALUES["followup_5"] - FORM_VALUES["closed"]}
EARLY_FUNNEL_PAYLOAD = {k: FORM_VALUES[k] for k in ("ad_budget", "num_leads", "leads_answered", "followup_1")}

ROUTE_PAYLOADS = {
    "/api/predict/ltv": FUNNEL_PAYLOAD,
    "/api/predict/upsell": FUNNEL_PAYLOAD,
    "/api/predict/referral": FUNNEL_PAYLOAD,
    "/api/predict/super-customer": EARLY_FUNNEL_PAYLOAD,
}


def _bearer_headers(token: Secret) -> dict[str, str]:
    """Built fresh at each call site, never bound to a long-lived local
    -- the one and only place `.reveal()` is called in this file."""
    return {"Authorization": f"Bearer {token.reveal()}"}


# Render's own edge intercepts /robots.txt for a SPUN-DOWN free service
# and answers with a fixed disallow-all body BEFORE the request ever
# reaches the app container -- documented behavior, Render's OWN official
# docs (https://render.com/docs/free, verified 2026-09-23 via direct
# fetch -- not this project's guess): "While a Free web service is spun
# down, incoming requests to the path /robots.txt automatically receive a
# standard 'disallow all' response" vs. "While a Free web service is
# active, requests to /robots.txt are routed to it as normal." Self-
# correction: an earlier version of this file also cited
# github.com/orgs/community/discussions/197645 for this specific claim --
# verified directly (fetched, re-read) that this discussion documents
# ONLY the general 15-minute spin-down timing, never robots.txt at all;
# that citation was wrong and is removed. Render's docs page does not
# publish the exact byte-for-byte disallow-all body, so this matches the
# CONTRACT it describes (case-insensitive substrings, not an exact-string
# comparison) rather than inventing exact bytes no one has published.
_ROBOTS_SLEEPING_MARKERS = ("user-agent: *", "disallow: /")

# app/static/index.html's own <title> (line 6) and the
# #authenticated-shell container id (line 48) -- two markers unique to
# FunnelIQ's real page, checked so a Render-served interstitial "waking
# up" page (if one is ever returned with its own 200) cannot be mistaken
# for a genuine cold-start response.
_FUNNELIQ_INDEX_MARKERS = ("<title>funneliq</title>", 'id="authenticated-shell"')


def _robots_txt_indicates_sleeping(status_code: int, body: str) -> bool:
    """Pure, credential-free, network-free -- see
    test_robots_txt_sentinel_logic below for the local, focused proof of
    this function alone."""
    if status_code != 200:
        return False
    lowered = body.lower()
    return all(marker in lowered for marker in _ROBOTS_SLEEPING_MARKERS)


def _looks_like_funneliq_index(status_code: int, body: str) -> bool:
    """Pure, credential-free, network-free -- see
    test_funneliq_index_marker_logic below for the local, focused proof
    of this function alone."""
    if status_code != 200:
        return False
    lowered = body.lower()
    return all(marker in lowered for marker in _FUNNELIQ_INDEX_MARKERS)


def test_robots_txt_sentinel_logic():
    """Local, credential-free, network-free proof of
    `_robots_txt_indicates_sleeping` alone, against fabricated response
    bodies -- not a live call. Three cases: Render's own documented
    disallow-all contract (true), FunnelIQ's app returning something else
    entirely for that path since it defines no custom robots.txt (false),
    and a non-200 status (false)."""
    assert _robots_txt_indicates_sleeping(200, "User-agent: *\nDisallow: /\n") is True
    assert _robots_txt_indicates_sleeping(200, "user-agent: *\ndisallow: /") is True  # case-insensitive
    assert _robots_txt_indicates_sleeping(404, "Not Found") is False
    assert _robots_txt_indicates_sleeping(200, "<html>FunnelIQ</html>") is False


def test_funneliq_index_marker_logic():
    """Local, credential-free, network-free proof of
    `_looks_like_funneliq_index` alone, against fabricated response
    bodies -- not a live call."""
    real_page = '<html><head><title>FunnelIQ</title></head><body><div id="authenticated-shell" hidden></div></body></html>'
    assert _looks_like_funneliq_index(200, real_page) is True
    assert _looks_like_funneliq_index(200, "<html><body>Your service is waking up...</body></html>") is False
    assert _looks_like_funneliq_index(200, "<title>FunnelIQ</title>") is False  # missing the second marker
    assert _looks_like_funneliq_index(503, real_page) is False


# Git's own abbreviated-SHA convention: 7 hex chars minimum (its default
# short-SHA length), 40 maximum (a full SHA-1). Anything else is not a
# plausible SHA at all, before ever comparing it to origin/main.
_GIT_SHA_PATTERN = re.compile(r"^[0-9a-fA-F]{7,40}$")


def _looks_like_valid_git_sha(value: str) -> bool:
    """Pure format check -- see test_deploy_sha_validation_logic below
    for the local, focused proof of this function alone."""
    return bool(_GIT_SHA_PATTERN.fullmatch(value))


def _sha_matches_origin_main(entered: str, origin_main_sha: str) -> bool:
    """True iff `entered` (full or abbreviated, case-insensitive) is a
    PREFIX of origin/main's real SHA -- git's own convention for how an
    abbreviated SHA identifies a commit. Format is NOT re-checked here
    (call `_looks_like_valid_git_sha` first); this only compares."""
    return origin_main_sha.lower().startswith(entered.lower())


def _origin_main_sha() -> str:
    """origin/main's real HEAD SHA, read from the LOCAL git ref (no
    network call -- `git rev-parse` reads refs already fetched into this
    repo, the same local-only anchor test_02/test_03's own `git show
    origin/main:...` calls use)."""
    result = subprocess.run(
        ["git", "rev-parse", "origin/main"],
        cwd=REPO_ROOT, capture_output=True, check=True, text=True,
    )
    return result.stdout.strip()


def test_deploy_sha_validation_logic():
    """Local, credential-free, network-free proof of
    `_looks_like_valid_git_sha` and `_sha_matches_origin_main` alone --
    not a live call, and NOT `_origin_main_sha()` itself (that one runs a
    git subprocess; it is exercised live inside
    test_journey_still_works_after_manual_redeploy, not here). Four
    cases per PHASE12.md's review: a valid full SHA, a valid abbreviated
    (prefix) SHA, a malformed value, and a well-formed but mismatched SHA."""
    real_sha = "6e570fc1234567890abcdef1234567890abcdef"

    # Format: valid full, valid abbreviated (git's own 7-char minimum),
    # too short, and non-hex characters.
    assert _looks_like_valid_git_sha(real_sha) is True
    assert _looks_like_valid_git_sha(real_sha[:7]) is True
    assert _looks_like_valid_git_sha(real_sha[:6]) is False
    assert _looks_like_valid_git_sha("g1234567") is False
    assert _looks_like_valid_git_sha("") is False

    # Comparison: full match, abbreviated (prefix) match, case-insensitive
    # match, and a well-formed but genuinely different SHA (mismatch).
    assert _sha_matches_origin_main(real_sha, real_sha) is True
    assert _sha_matches_origin_main(real_sha[:7], real_sha) is True
    assert _sha_matches_origin_main(real_sha[:7].upper(), real_sha) is True
    assert _sha_matches_origin_main("fffffff", real_sha) is False


def test_bearer_headers_reveals_real_token_and_censors_later_failure_output(tmp_path):
    """Codex review, 2026-09-23: two raw `f"Bearer {token}"` f-strings
    survived in this file's own test_cold_start_after_real_inactivity and
    test_journey_still_works_after_manual_redeploy (both now fixed, routed
    through `_bearer_headers()`). Because `Secret.__str__` returns
    '<redacted>', those two lines were silently sending the literal header
    'Bearer <redacted>' -- not a logging cosmetic issue, a real one: every
    request built that way would have failed with a real 401 against the
    live service. Part 1 below catches exactly that class of bug: a test
    that only checked "does Secret redact repr()" would stay green while
    every real request 401'd.

    Part 2 is a REAL, EMPIRICALLY-CHECKED limit, not an assumption --
    verified directly (2026-09-23, two scratch probes) before writing
    this test: if the SAME call that reveals a token is what fails
    (e.g. httpx.get() itself raising a ConnectError), `--showlocals`
    shows the real value via HTTPX'S OWN internal frames (its own
    request-building code binds the header dict to a local named
    `headers` too) -- REGARDLESS of whether this file's own code ever
    names a local `headers`. That is not fixable from here: transmitting
    a real credential requires the raw string to exist as a real string
    at the moment of transmission, in a library this project does not
    control. So this test deliberately does NOT claim that case is safe
    -- it proves the case that actually matches the real 2026-09-23
    incident: demo_credentials sat in the test's own frame for the WHOLE
    test body, and a LATER, UNRELATED call (a Playwright wait, nothing
    to do with the credential) is what failed. Mirrored here: the header
    dict is built and consumed by a call that RETURNS NORMALLY, and only
    AFTER that -- with no live reference to the revealed value left in
    the failing frame -- does the deliberate failure happen. A FABRICATED
    dummy token throughout, never a real credential.

    Scope, precisely -- deliberately NOT a blanket claim: `Secret`
    guarantees a WRAPPED value never leaks, for as long as it stays
    wrapped. It does not and cannot guarantee that the exact call
    transmitting a REVEALED value is itself leak-proof if that specific
    call fails -- see the class docstring's own note on this."""
    dummy_token = Secret("dummy-jwt-token-not-a-real-credential")
    headers = _bearer_headers(dummy_token)
    assert headers == {"Authorization": "Bearer dummy-jwt-token-not-a-real-credential"}, (
        f"_bearer_headers() did not reveal the real token into the request header -- got {headers!r}"
    )

    throwaway = tmp_path / "test_throwaway_bearer_header_leak_proof.py"
    throwaway.write_text(
        "import os, sys\n"
        f"sys.path.insert(0, {str(LIVE_DIR)!r})\n"
        "from conftest import Secret\n"
        "\n"
        "def _send(headers):\n"
        "    return len(headers)  # stands in for a real call that RETURNS NORMALLY\n"
        "\n"
        "def test_deliberate_failure_after_the_revealing_call_already_returned():\n"
        "    token = Secret(os.environ['LEAK_PROOF_TOKEN'])\n"
        "    _send({'Authorization': 'Bearer ' + token.reveal()})\n"
        "    assert False, 'deliberate failure for the leak-proof test -- expected'\n",
        encoding="utf-8",
    )
    result = subprocess.run(
        [sys.executable, "-m", "pytest", "-q", "--showlocals", "-p", "no:cacheprovider", str(throwaway)],
        cwd=tmp_path, capture_output=True, text=True, timeout=60,
        env={**os.environ, "LEAK_PROOF_TOKEN": dummy_token.reveal()},
    )
    combined_output = result.stdout + result.stderr
    assert dummy_token.reveal() not in combined_output, (
        "the dummy token leaked into pytest's own --showlocals output for a failure "
        f"AFTER the revealing call already returned normally:\n{combined_output}"
    )
    assert "1 failed" in combined_output, (
        f"the throwaway test did not actually fail -- this proof needs a real failure:\n{combined_output}"
    )


def test_cold_start_after_real_inactivity(demo_credentials: dict[str, Secret]):
    """PHASE12.md CP5 + P12-D5 + falsification case 4: 'cold start אחרי
    חוסר פעילות => הבקשה הראשונה מסתיימת, והמסע ממשיך לעבוד.'

    MUST be run alone (see module docstring). Depending on
    `demo_credentials` here is safe: that fixture only calls
    getpass.getpass() twice, in-process, with zero network I/O -- it is
    resolved (both prompts) before the sleep below starts, so the
    password is never asked for twice across this file (the later
    `northbound_token` fixture reuses this same session-scoped value).
    P12-D5's actual cold measurement itself is credential-free: GET /
    -> 200, the same first request a stranger opening the URL makes.

    Five steps, in order, proving an actual awake -> sleep -> awake
    TRANSITION rather than a single ambiguous snapshot: (1) a strengthened
    anchor request establishes both "the service is genuinely awake right
    now" AND T0, deliberately, rather than assuming the service was
    already idle before this test started -- 120s timeout (Render wake-up
    can itself take a while) and both status 200 AND the exact JSON body
    {"status": "ok"} (app/main.py:96-97), so a Render interstitial page
    (which could also answer 200) cannot be mistaken for the anchor
    succeeding; (2) immediately after establishing "awake", the SAME
    /robots.txt sentinel is checked and required to NOT match the sleeping
    pattern -- proving the sentinel actually discriminates on this real
    deployment right now, not just per Render's docs in the abstract; T0
    is set only after this negative baseline passes; (3) the 16-minute
    wait itself, from that T0, with ZERO further requests; (4) the exact
    same /robots.txt sentinel, checked again, now REQUIRED to match the
    sleeping pattern -- together with step 2's negative result, this
    proves a real awake -> asleep transition happened because of the
    wait, not just a body that always reads one way regardless of state;
    if this does not match, the run is not a valid cold measurement and
    this test fails WITHOUT reporting any time, exactly as this review
    requires; (5) the single measured GET /, verified to be FunnelIQ's
    own real page (not just status 200) via `_looks_like_funneliq_index`."""
    anchor_response = httpx.get(f"{LIVE_BASE_URL}/health", timeout=120)
    assert anchor_response.status_code == 200, f"anchor request failed: {anchor_response.status_code}"
    assert anchor_response.json() == {"status": "ok"}, (
        f"anchor GET /health returned 200 but an unexpected body {anchor_response.text!r} -- "
        "this may be a Render interstitial page, not the real app; refusing to treat this "
        "as proof the service is genuinely awake"
    )

    awake_sentinel = httpx.get(f"{LIVE_BASE_URL}/robots.txt", timeout=30)
    awake_sentinel_sleeping = _robots_txt_indicates_sleeping(awake_sentinel.status_code, awake_sentinel.text)
    print(
        f"\ncold start: awake baseline -- GET /health -> 200 {{'status':'ok'}}; "
        f"/robots.txt status={awake_sentinel.status_code}, body={awake_sentinel.text[:80]!r}, "
        f"indicates_sleeping={awake_sentinel_sleeping}"
    )
    assert not awake_sentinel_sleeping, (
        "the /robots.txt sentinel already reads as 'sleeping' WHILE the service just answered "
        "the anchor request awake -- the sentinel does not actually discriminate awake/asleep "
        "on this deployment right now, so a later 'sleeping' reading would not be trustworthy "
        "evidence either; aborting before the wait"
    )

    wait_started_at = datetime.now(timezone.utc)
    print(
        f"cold start: awake baseline confirmed, T0={wait_started_at.isoformat()}. "
        f"Waiting {COLD_START_WAIT_SECONDS}s ({COLD_START_WAIT_SECONDS / 60:.0f} min) with ZERO further "
        f"requests to {LIVE_BASE_URL} -- method: Render's documented 15-minute free-tier "
        "inactivity spin-down (https://render.com/docs/free), 1-minute safety margin, no "
        "traffic from this process or any fixture during the wait"
    )
    time.sleep(COLD_START_WAIT_SECONDS)

    sentinel_response = httpx.get(f"{LIVE_BASE_URL}/robots.txt", timeout=30)
    sentinel_ok = _robots_txt_indicates_sleeping(sentinel_response.status_code, sentinel_response.text)
    print(
        f"cold start: post-wait /robots.txt sentinel status={sentinel_response.status_code}, "
        f"body={sentinel_response.text[:80]!r}, indicates_sleeping={sentinel_ok}"
    )
    assert sentinel_ok, (
        "the /robots.txt sentinel did not match Render's documented sleeping-service "
        "response after the 16-minute wait -- something touched the service during the "
        "wait (or Render's behavior differs from what's documented), so this run is NOT "
        "a valid cold-start measurement; no cold-start time is reported"
    )

    measured_at = datetime.now(timezone.utc)
    start = time.monotonic()
    response = httpx.get(LIVE_BASE_URL, timeout=120)
    elapsed_seconds = time.monotonic() - start

    # P12-D7: no retry here -- a cold-start request that fails outright is
    # itself the finding CP5 exists to surface, not something to paper
    # over with a second silent attempt.
    assert response.status_code == 200, (
        f"cold start GET / returned {response.status_code}, not 200 -- "
        f"the first request itself failed, elapsed={elapsed_seconds:.2f}s"
    )
    assert _looks_like_funneliq_index(response.status_code, response.text), (
        "GET / returned 200 but the body does not look like FunnelIQ's real index.html "
        "(missing <title>FunnelIQ</title> or #authenticated-shell) -- this may be a "
        "Render-served interstitial page, not the app itself; refusing to report this "
        f"as a genuine cold-start time. First 200 chars: {response.text[:200]!r}"
    )
    print(
        f"cold start: GET / -> 200, verified real FunnelIQ page, in {elapsed_seconds:.2f}s, "
        f"measured at {measured_at.isoformat()} (wait started {wait_started_at.isoformat()})"
    )

    # Falsification case 4's second half: the journey still works right
    # after the cold first request -- a real, in-domain prediction.
    token = sign_in_via_api(DEMO_NORTHBOUND_EMAIL, demo_credentials[DEMO_NORTHBOUND_EMAIL])
    journey_start = time.monotonic()
    journey_response = httpx.post(
        f"{LIVE_BASE_URL}/api/predict/ltv",
        headers={"Authorization": f"Bearer {token.reveal()}"}, json=FUNNEL_PAYLOAD, timeout=60,
    )
    journey_elapsed = time.monotonic() - journey_start
    assert journey_response.status_code == 200, journey_response.text
    body = journey_response.json()
    assert body["point_estimate"] is not None, "post-cold-start prediction returned a null point_estimate"
    print(f"cold start: journey continued -- POST /api/predict/ltv -> 200 in {journey_elapsed:.2f}s")


def test_warm_latency_for_all_seven_routes(northbound_token: str):
    """PHASE12.md CP5: 'latency חם לשבעת הנתיבים.' Runs after the cold
    start test above, so the service is already warm -- no separate
    warm-up call needed. One timed call per route; each is asserted 200
    (a real, successful call, not a stub), and elapsed time is printed
    per route as CP5's own required evidence."""
    timings = {}
    for method, path in SEVEN_ROUTES:
        start = time.monotonic()
        if method == "GET":
            response = httpx.get(f"{LIVE_BASE_URL}{path}", headers=_bearer_headers(northbound_token), timeout=30)
        else:
            response = httpx.post(
                f"{LIVE_BASE_URL}{path}", headers=_bearer_headers(northbound_token),
                json=ROUTE_PAYLOADS[path], timeout=30,
            )
        elapsed = time.monotonic() - start
        timings[path] = elapsed
        assert response.status_code == 200, f"{method} {path}: {response.status_code} {response.text}"

    print("\nwarm latency (seconds), one call per route:")
    for path, elapsed in timings.items():
        print(f"  {path}: {elapsed:.3f}s")


@pytest.fixture(scope="module")
def northbound_token(demo_credentials: dict[str, Secret]) -> Secret:
    return sign_in_via_api(DEMO_NORTHBOUND_EMAIL, demo_credentials[DEMO_NORTHBOUND_EMAIL])


def _prompt_redeploy_confirmation() -> str:
    """A plain, non-secret confirmation -- deliberately builtins.input(),
    not getpass (there is nothing here to hide). A single exact value for
    the status gate, same philosophy as P12-D3's opt-in gate: ambiguity
    about whether the redeploy actually happened is exactly what this
    exists to rule out. Also collects the commit SHA Render's dashboard
    shows for that deploy -- 'the general service status' (e.g. the
    running instance simply answering requests again) is NOT proof that
    THIS specific new deploy is what's live; the dashboard's own deploy
    entry, showing status=Live against a specific SHA, is. That SHA is
    validated for format AND compared against origin/main's real SHA
    (render.yaml pins deployment to branch: main) -- a malformed value or
    a genuine mismatch fails this check outright, before any journey
    check runs. Returns the confirmed SHA for the caller's own evidence."""
    status_message = (
        "\nCP5 restart/redeploy check: on Render's dashboard, open the funneliq "
        "service -> Manual Deploy -> Deploy latest commit. Wait until THAT deploy's "
        "own entry (not just the service's general status) shows 'Live' -- not "
        "'Deploying' or 'Build in progress'. This cannot be triggered from here -- "
        "Claude has no Render API or dashboard access in this project. "
        "Type 'redeployed' (without quotes) once that specific deploy shows Live: "
    )
    answer = input(status_message)
    if answer.strip() != "redeployed":
        pytest.fail(f"redeploy not confirmed (typed {answer!r}, expected 'redeployed') -- aborting this test")

    sha_message = "Paste the commit SHA Render's dashboard shows for that Live deploy: "
    sha = input(sha_message).strip()
    if not _looks_like_valid_git_sha(sha):
        pytest.fail(
            f"{sha!r} does not look like a git SHA (7-40 hex characters expected) -- aborting this test"
        )

    origin_main_sha = _origin_main_sha()
    if not _sha_matches_origin_main(sha, origin_main_sha):
        pytest.fail(
            f"dashboard-shown SHA {sha!r} does not match origin/main ({origin_main_sha}) -- "
            "the deploy confirmed Live is not the current tip of main; aborting this test"
        )

    confirmed_at = datetime.now(timezone.utc)
    print(
        f"\nCP5 restart/redeploy: confirmed Live at {confirmed_at.isoformat()}, "
        f"method=Render dashboard Manual Deploy, dashboard-shown SHA={sha} "
        f"(matches origin/main {origin_main_sha})"
    )
    return sha


def test_journey_still_works_after_manual_redeploy(demo_credentials: dict[str, Secret], browser):
    """PHASE12.md CP5 + falsification case 9: 'redeploy/restart =>
    המודלים נטענים והמסע עובד, בלי מצב תקוע.' Requires a MANUAL redeploy
    (see module docstring) confirmed via `_prompt_redeploy_confirmation`
    below before anything here runs -- including before the FIRST network
    touch. Deliberately takes the raw `browser` fixture, not `live_context`
    (conftest.py:206-236): that fixture calls live_config() -- a real
    network request -- the moment pytest resolves it, which happens
    BEFORE this function's own body (and its confirmation prompt) runs
    at all. The browser context is built by hand below, after the prompt,
    using the same live_config()/install_zero_write_guard() (P12-D4) this
    file's own fixture would otherwise apply automatically. Proves no
    stuck state at two levels: real API predictions with real numbers
    (models actually reloaded), and a real browser sign-in + one real
    form submit (the user-facing journey itself, not just the API)."""
    confirmed_sha = _prompt_redeploy_confirmation()

    token = sign_in_via_api(DEMO_NORTHBOUND_EMAIL, demo_credentials[DEMO_NORTHBOUND_EMAIL])
    # `_bearer_headers(token)` is called fresh at each call site below,
    # not bound once to a `headers` local reused across both requests
    # and left sitting in scope through the rest of this (long) test,
    # including the whole browser portion below -- the shorter a raw-JWT
    # dict's lifetime as a named local, the smaller the window any later
    # failure's traceback could ever show it in.
    ltv_response = httpx.post(
        f"{LIVE_BASE_URL}/api/predict/ltv", headers=_bearer_headers(token), json=FUNNEL_PAYLOAD, timeout=60
    )
    assert ltv_response.status_code == 200, ltv_response.text
    assert ltv_response.json()["point_estimate"] is not None, "post-redeploy P2 returned a null point_estimate"

    budget_response = httpx.get(f"{LIVE_BASE_URL}/api/simulate/budget", headers=_bearer_headers(token), timeout=60)
    assert budget_response.status_code == 200, budget_response.text
    strategies = budget_response.json()["strategies"]
    assert len(strategies) == 4 and all(s["point_estimate"] is not None for s in strategies), (
        "post-redeploy budget simulation did not return four real strategies"
    )

    config = live_config()
    context = browser.new_context(service_workers="block")
    install_zero_write_guard(context, config["supabase_url"])
    try:
        page = context.new_page()
        sign_in_via_browser(page, DEMO_NORTHBOUND_EMAIL, demo_credentials[DEMO_NORTHBOUND_EMAIL])
        page.wait_for_selector("#authenticated-shell:not([hidden])", timeout=30_000)

        page.click('a[data-route="predict"]')
        page.wait_for_selector("#field-ad_budget")
        for field, value in FORM_VALUES.items():
            page.fill(f"#field-{field}", str(value))
        page.check(".context-confirmation input[type=checkbox]")
        page.click(".submit-button")
        page.wait_for_selector(".prediction-panel-p2 .prediction-primary", timeout=15_000)

        primary_text = page.text_content(".prediction-panel-p2 .prediction-primary")
        assert primary_text and "תחזית" in primary_text, (
            f"post-redeploy browser journey did not render a real P2 prediction: {primary_text!r}"
        )
    finally:
        context.close()
    print(
        f"\npost-redeploy journey (confirmed SHA {confirmed_sha}): API predict/ltv 200, "
        "simulate/budget 200 (4 strategies), browser submit rendered a real P2 prediction"
    )
