# `supabase.min.js` — vendored copy, source and provenance

Phase 11 checkpoint 11 (`P11-D7`/§ו). This file exists so `e2e/`'s own
network-mocking harness can serve `supabase-js` from `e2e/vendor/`
instead of the real `cdn.jsdelivr.net`, while the browser's own SRI
check (already locked in `app/static/index.html`) still verifies the
bytes are the exact, unmodified library — a deliberate self-check, not
a bypass: if this file ever drifted from the real 2.58.0 release, the
browser would reject it and the E2E run would fail loudly, not
silently serve something else.

- **Downloaded from:** `https://cdn.jsdelivr.net/npm/@supabase/supabase-js@2.58.0/dist/umd/supabase.min.js`
- **Version:** `2.58.0` (same version `index.html:93` already pins)
- **SHA-384 (base64):** `WmjsOVSSw3JNqIKfmDU35+uddOzBdP9PlYIWCg7xdnVOesjWVGpRcooOVheFFwH4`
  — verified to match `index.html`'s own `integrity="sha384-..."`
  attribute byte-for-byte before this file was committed (`openssl
  dgst -sha384` on the downloaded file).
- **License:** MIT (`@supabase/supabase-js`, https://github.com/supabase/supabase-js/blob/master/LICENSE).
  Per CLAUDE.md's own locked "Credit what you borrow" decision (`B65`):
  this notice, the upstream repository link, the exact version, and the
  verified hash together constitute that credit for this borrowed file.
- **Why vendored instead of fetched live in tests:** PHASE11.md §ו's
  own "zero external network" rule for the E2E harness -- a real fetch
  to jsdelivr.net during a test run would be exactly the kind of
  external dependency the harness exists to eliminate (flaky on
  network conditions, and a real request to a third party on every
  local test run).
