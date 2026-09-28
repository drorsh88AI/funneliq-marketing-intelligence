"""Phase 12A, checkpoint 4 -- structural checks for the 10 frozen
historical examples (PHASE12A.md §ו.2).

These are the checks CI *can* run without the frozen CSV (which is not
in the repo, PHASE0.md's own frozen-file decision): that the committed
manifest itself has 10 unique ids and the locked 2/5/3 tier composition
(re-derived from `app.features.budget_tier`, a pure function -- never
the CSV), and that `supabase-prefill.js`'s own hardcoded id list is a
byte-for-byte copy of that manifest's ids. What CI CANNOT check --
that the selection rule (§ו.2 stage 0/1) was applied correctly, or that
the stored values equal the real CSV/Supabase row -- is verified
locally by scripts/select_examples.py and live by live/test_02, per
§ו.2's own documented split.
"""
from __future__ import annotations

import json
import re
from collections import Counter
from pathlib import Path

from app.features import budget_tier

REPO_ROOT = Path(__file__).resolve().parent.parent
MANIFEST_PATH = REPO_ROOT / "docs" / "frozen_examples.json"
PREFILL_JS = REPO_ROOT / "app" / "static" / "js" / "supabase-prefill.js"


def _load_manifest() -> list[dict]:
    return json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))["examples"]


def test_manifest_has_10_unique_source_row_ids():
    examples = _load_manifest()
    ids = [e["source_row_id"] for e in examples]
    assert len(ids) == 10, f"expected exactly 10 frozen examples, got {len(ids)}"
    assert len(set(ids)) == 10, f"duplicate source_row_id in manifest: {ids}"


def test_manifest_tier_composition_is_2_low_5_mid_3_high():
    examples = _load_manifest()
    tiers = [budget_tier(e["ad_budget"]) for e in examples]
    counts = Counter(tiers)
    assert None not in counts, (
        f"a frozen example's ad_budget falls in the 1501-1999 gap (no tier): {examples}"
    )
    assert counts == Counter({"Low": 2, "Mid": 5, "High": 3}), (
        f"expected 2 Low / 5 Mid / 3 High, got {dict(counts)}"
    )


def test_prefill_js_ids_match_the_committed_manifest_exactly():
    """§ו.2: the browser cannot read docs/ (only app/static/ is served),
    so supabase-prefill.js carries its own copy of the 10 ids as a JS
    array literal. This is the anti-drift check for that copy -- the
    manifest is the single source of truth, and this fails loudly the
    moment someone edits one without the other."""
    manifest_ids = sorted(e["source_row_id"] for e in _load_manifest())

    source = PREFILL_JS.read_text(encoding="utf-8")
    match = re.search(r"FROZEN_EXAMPLE_IDS\s*=\s*\[([^\]]*)\]", source)
    assert match, "supabase-prefill.js: FROZEN_EXAMPLE_IDS constant not found"
    js_ids = sorted(int(x) for x in match.group(1).split(","))

    assert js_ids == manifest_ids, (
        f"supabase-prefill.js's FROZEN_EXAMPLE_IDS {js_ids} != "
        f"docs/frozen_examples.json's ids {manifest_ids}"
    )


def test_prefill_js_queries_by_id_list_not_a_row_limit():
    """§ו.2: the audit finding (F2/S2, 'up to 1000 rows -- very
    inconvenient') is fixed by filtering on the 10 fixed ids, not by
    lowering the limit. Guards against a regression back to `.limit(`."""
    source = PREFILL_JS.read_text(encoding="utf-8")
    assert '.in("source_row_id", FROZEN_EXAMPLE_IDS)' in source
    assert ".limit(" not in source
