"""Phase 12 checkpoint 1 -- harness self-checks. These are not
falsification cases against the product (that's checkpoints 2-8); they
prove the live/ harness itself does what PHASE12.md's CP1 row requires
before any real acceptance test is layered on top of it: the opt-in
gate fires before any prompt, a bad credential prompt fails loud, both
P12-D4 zero-write channels reject a write before it reaches the
network, retries are counted rather than swallowed, and nothing here
records to disk in a way that could leak a password.

None of these tests sign in with the real demo accounts -- they either
exercise pure logic with injected fakes, or touch only the live
service's public /api/config and Supabase's PostgREST endpoint
anonymously. Running `pytest -s live/` today therefore never prompts
for a real password: demo_credentials is only consumed once a
checkpoint-2+ test actually depends on it.
"""
from __future__ import annotations

import datetime
import importlib.metadata
import re
from pathlib import Path

import httpx
import pytest

from conftest import (
    DEMO_NOORG_EMAIL,
    DEMO_NORTHBOUND_EMAIL,
    OPT_IN_ENV_VAR,
    OPT_IN_ENV_VALUE,
    LiveCredentialError,
    PostgrestReadOnly,
    RetryCounter,
    _opt_in_is_set,
    _opt_in_message,
    _prompt_password,
    live_config,
)

LIVE_DIR = Path(__file__).resolve().parent


def test_live_environment_is_documented(browser):
    """PHASE12.md CP1's own harness must be reproducible evidence, not a
    black box: same convention as e2e/test_00_infrastructure.py's own
    test -- printed (pytest -s), asserted non-empty rather than
    hardcoded, since the whole point of driving the system's own Chrome
    (conftest.py's browser_type_launch_args override) is that this
    value is not pinned by us."""
    playwright_version = importlib.metadata.version("playwright")
    browser_version = browser.version
    today = datetime.date.today().isoformat()
    print(f"\nlive/ environment: Playwright {playwright_version}, browser {browser_version}, {today}")
    assert playwright_version
    assert browser_version
    assert today


# ---------------------------------------------------------------------------
# P12-D3 -- opt-in gate, checked before any getpass prompt.
# ---------------------------------------------------------------------------


def test_opt_in_rejects_missing_env():
    assert _opt_in_is_set({}) is False
    assert _opt_in_is_set({OPT_IN_ENV_VAR: "0"}) is False
    assert _opt_in_is_set({OPT_IN_ENV_VAR: "true"}) is False
    assert _opt_in_is_set({OPT_IN_ENV_VAR: "yes"}) is False


def test_opt_in_accepts_only_the_exact_value():
    assert _opt_in_is_set({OPT_IN_ENV_VAR: OPT_IN_ENV_VALUE}) is True


def test_opt_in_message_names_the_env_var_and_pytest_dash_s():
    message = _opt_in_message()
    assert OPT_IN_ENV_VAR in message
    assert "pytest -s live/" in message
    assert "credentials" in message


# ---------------------------------------------------------------------------
# P12-D3 -- credential prompt fails loud, never silently.
# ---------------------------------------------------------------------------


def test_credential_prompt_fails_loud_on_eof():
    def fake_prompt(_label: str) -> str:
        raise EOFError

    with pytest.raises(LiveCredentialError, match="stdin is closed"):
        _prompt_password(DEMO_NORTHBOUND_EMAIL, prompt=fake_prompt)


def test_credential_prompt_fails_loud_on_empty_answer():
    with pytest.raises(LiveCredentialError, match="empty password"):
        _prompt_password(DEMO_NOORG_EMAIL, prompt=lambda _label: "")


def test_credential_prompt_returns_the_typed_value_and_prompts_with_the_label():
    seen_prompts = []

    def fake_prompt(prompt_text: str) -> str:
        seen_prompts.append(prompt_text)
        return "a-fake-password-never-real"

    value = _prompt_password(DEMO_NORTHBOUND_EMAIL, prompt=fake_prompt)
    assert value == "a-fake-password-never-real"
    assert DEMO_NORTHBOUND_EMAIL in seen_prompts[0]


# ---------------------------------------------------------------------------
# P12-D4 channel 1 -- browser-context guard rejects a write before the
# network, without needing real credentials (anonymous is enough to
# prove the guard fires -- RLS deciding the outcome is CP3's job).
#
# These go through the REAL live_context/live_page fixtures, not a
# bare browser.new_context() of their own: that would exercise only the
# bare install_zero_write_guard() function, never proving the fixture
# wiring itself (service_workers="block", context.live_supabase_url,
# context.live_rejected_writes) is actually correct end to end.
# ---------------------------------------------------------------------------


def test_browser_context_guard_rejects_non_get_before_it_reaches_the_network(live_context, live_page):
    result = live_page.evaluate(
        """(supabaseUrl) => fetch(supabaseUrl + '/rest/v1/funnel_records', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: '{}',
        }).then(() => 'unexpectedly succeeded').catch((e) => 'rejected: ' + e.message)""",
        live_context.live_supabase_url,
    )

    assert "rejected" in result
    assert len(live_context.live_rejected_writes) == 1
    assert live_context.live_rejected_writes[0].method == "POST"
    assert "/rest/v1/funnel_records" in live_context.live_rejected_writes[0].url


def test_browser_context_guard_does_not_block_get(live_context, live_page):
    """The guard must be selective, not a blanket block on the endpoint
    -- otherwise checkpoint 3's real RLS reads through the browser would
    be impossible. A GET is allowed to actually reach the network here;
    an anonymous request answering at all (even with an RLS-denied body)
    proves it was never aborted."""
    result = live_page.evaluate(
        """(args) => fetch(args.url + '/rest/v1/funnel_records?select=source_row_id&limit=1', {
            method: 'GET',
            headers: {apikey: args.key},
        }).then((r) => ({ok: true, status: r.status})).catch((e) => ({ok: false, message: e.message}))""",
        {"url": live_context.live_supabase_url, "key": live_config()["supabase_publishable_key"]},
    )

    assert result["ok"] is True, result
    assert live_context.live_rejected_writes == []


# ---------------------------------------------------------------------------
# P12-D4 channel 2 -- the read-only PostgREST wrapper for direct calls.
# ---------------------------------------------------------------------------


def test_postgrest_wrapper_rejects_write_before_any_http_call(monkeypatch):
    """Pure unit test on the class's own dispatch logic -- no live
    dependency needed here, since this is testing internal behavior,
    not fixture wiring (that's test_postgrest_fixture_is_wired_to_live_context)."""
    called = []
    monkeypatch.setattr(httpx, "request", lambda *a, **k: called.append((a, k)) or (_ for _ in ()).throw(AssertionError("must not be called")))

    client = PostgrestReadOnly(base_url="https://example.invalid", publishable_key="anon-key")
    with pytest.raises(RuntimeError, match="zero-write guard"):
        client._request("POST", "/funnel_records", json={})

    assert called == []
    assert client.rejected_attempts == ["POST /funnel_records"]


def test_postgrest_fixture_is_wired_to_live_context(postgrest, live_context):
    """Exercises the REAL `postgrest` fixture, not a manually-constructed
    PostgrestReadOnly -- proves the fixture actually shares live_context's
    supabase_url (both channels must agree on the same target) and that
    its publishable_key is genuinely usable against the live service."""
    assert postgrest.base_url == live_context.live_supabase_url
    response = postgrest.get("/funnel_records", params={"select": "source_row_id", "limit": "1"})
    assert response.status_code < 500
    assert postgrest.rejected_attempts == []


# ---------------------------------------------------------------------------
# P12-D7 -- retries are counted, never silent.
# ---------------------------------------------------------------------------


def test_retry_counter_records_attempts_on_success_after_failures():
    """Uses httpx.ConnectError -- a real RetryCounter.retryable member --
    to simulate transient network flakiness, not a bare RuntimeError
    (which, after this checkpoint's own fix, is no longer retried at
    all)."""
    counter = RetryCounter(max_attempts=3)
    calls = {"n": 0}

    def flaky():
        calls["n"] += 1
        if calls["n"] < 3:
            raise httpx.ConnectError("simulated transient failure")
        return "ok"

    result = counter.run(flaky)
    assert result == "ok"
    assert counter.attempts == 3


def test_retry_counter_raises_after_exhausting_and_still_reports_attempts():
    counter = RetryCounter(max_attempts=2)

    def always_fails():
        raise httpx.ReadTimeout("simulated permanent failure")

    with pytest.raises(RuntimeError, match="exhausted 2 attempts"):
        counter.run(always_fails)
    assert counter.attempts == 2


def test_retry_counter_does_not_retry_a_programming_error():
    """P12-D7: retry exists for real network flakiness, never to hide a
    genuine bug. An AssertionError (or anything outside
    RetryCounter.retryable) must propagate on the very first attempt --
    not get silently retried into a coincidental pass on attempt 2 or 3."""
    counter = RetryCounter(max_attempts=3)
    calls = {"n": 0}

    def buggy():
        calls["n"] += 1
        assert False, "this is a real bug, not network flakiness"

    with pytest.raises(AssertionError, match="real bug"):
        counter.run(buggy)

    assert calls["n"] == 1
    assert counter.attempts == 1


def test_live_config_retries_through_a_transient_failure_and_reports_attempts(monkeypatch, capsys):
    """Functional-level proof that live_config() itself -- not just
    RetryCounter in isolation -- recovers from exactly the failure class
    observed in practice (a real httpx.ReadTimeout hitting /api/config).
    Clears live_config's cache before and after: this test's
    monkeypatched, fake result must never leak into any other test that
    depends on the REAL live config."""
    import conftest as live_conftest

    real_result = {"supabase_url": "https://fake.supabase.co", "supabase_publishable_key": "fake-key"}
    calls = {"n": 0}

    def flaky_fetch():
        calls["n"] += 1
        if calls["n"] < 2:
            raise httpx.ReadTimeout("simulated timeout hitting /api/config")
        return real_result

    monkeypatch.setattr(live_conftest, "_fetch_live_config", flaky_fetch)
    live_conftest.live_config.cache_clear()
    try:
        result = live_conftest.live_config()
        assert result == real_result
        assert calls["n"] == 2
        assert "live_config: succeeded after 2 attempt(s)" in capsys.readouterr().out
    finally:
        live_conftest.live_config.cache_clear()


# ---------------------------------------------------------------------------
# Structural self-checks: isolation from bare `pytest`, and no recording
# artifact that a password could end up in.
# ---------------------------------------------------------------------------


def test_pytest_ini_excludes_live_from_bare_collection():
    repo_root = LIVE_DIR.parent
    pytest_ini = (repo_root / "pytest.ini").read_text(encoding="utf-8")
    assert re.search(r"^testpaths\s*=\s*tests\s*$", pytest_ini, re.MULTILINE), (
        "pytest.ini must restrict bare collection to tests/ only -- live/ (and e2e/) "
        "must never be picked up by an unfocused `pytest`/`pytest -q`"
    )


_RECORDING_PATTERN = re.compile(r"record_video_dir|record_har_path|tracing\.start")
_SECRET_ENV_PATTERN = re.compile(
    r'os\.environ(\[|\.get\()\s*["\']SUPABASE_SECRET_KEY["\']|os\.getenv\(\s*["\']SUPABASE_SECRET_KEY["\']'
)
_PASSWORD_FROM_ENV_OR_FILE_PATTERN = re.compile(
    r'os\.environ.*password'
    r'|os\.getenv\([^)]*password'
    r'|open\([^)]*\.env[^)]*\)'
    r'|\.env["\'][^)]*\)\s*\.\s*read_(text|bytes)\s*\('
    r'|load_dotenv\s*\(',
    re.IGNORECASE,
)


def test_live_source_never_enables_recording_or_reads_secrets_from_disk_or_env():
    """Scans every live/*.py file except this one -- this file's own
    source necessarily contains the literal pattern strings below (to
    define them), which would otherwise make this test fail against
    itself. Future live/test_*.py files (checkpoint 2+) ARE scanned, so
    this stays a real guard against a future harness regression, not
    just a check on conftest.py today.

    A heuristic, not a proof -- same honest limitation as
    tests/test_supabase_client.py's own equivalent check for
    SUPABASE_SECRET_KEY. Self-review finding: the original patterns
    caught `open(...)`-style disk reads and `os.environ`/`os.getenv`
    idioms, but missed `pathlib.Path(...).read_text()`/`.read_bytes()`
    on a `.env`-referencing path and python-dotenv's own
    `load_dotenv()` -- both now covered."""
    offenders = []
    for path in LIVE_DIR.glob("*.py"):
        if path.name == Path(__file__).name:
            continue
        text = path.read_text(encoding="utf-8")
        if _RECORDING_PATTERN.search(text):
            offenders.append(f"{path.name}: recording artifact (video/HAR/trace)")
        if _SECRET_ENV_PATTERN.search(text):
            offenders.append(f"{path.name}: reads SUPABASE_SECRET_KEY")
        if _PASSWORD_FROM_ENV_OR_FILE_PATTERN.search(text):
            offenders.append(f"{path.name}: reads a password from env/file")
    assert offenders == [], offenders
