"""Tests that docs/planning/REQUIREMENTS.md -- the brief's atomic
requirement registry (B1-B65, with splits) -- stays honest against two
things: the brief itself (FunnelIQ_Assignment.html) and its own internal
bookkeeping rules.

Every test here PARSES the real files -- it does not re-assert what the
registry already claims. If a source_quote drifts from the brief, or a
row is marked done without evidence, this must fail, not pass on a vibe.
See docs/planning/REQUIREMENTS.md's own header for the status legend and
docs/planning/codex-review.md for why this registry exists: six review
rounds on phase 9 checked the plan against SPEC.md, never against the
brief SPEC.md was derived from.
"""
from __future__ import annotations

import html as html_lib
import re
from collections import Counter
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
REQUIREMENTS_MD = REPO_ROOT / "docs" / "planning" / "REQUIREMENTS.md"
BRIEF_HTML = REPO_ROOT / "FunnelIQ_Assignment.html"
ROADMAP_HTML = REPO_ROOT / "ROADMAP.html"

# The exact 73 ids the registry is expected to hold right now (B1-B65,
# with a/b/c/d splits where one brief sentence carries several distinct
# obligations, minus B47 which was retracted -- see REQUIREMENTS.md's own
# "B47 -- הוסר" section). This is a deliberate snapshot, not a formula: it
# exists so that deleting -- or silently renaming -- a requirement fails
# a test instead of just shrinking a count nobody is watching. Update it,
# in the same commit as REQUIREMENTS.md, whenever a requirement is
# legitimately added, split, or retracted.
_EXPECTED_IDS = frozenset({
    "B1", "B2", "B3", "B4", "B5",
    "B6", "B7", "B8",
    "B9", "B10", "B11",
    "B12", "B13", "B14", "B15", "B16",
    "B17", "B18", "B19", "B20", "B21", "B22", "B23", "B24",
    "B25", "B26", "B27", "B28", "B29a", "B29b", "B29c",
    "B30", "B31", "B32", "B33", "B34", "B35", "B36",
    "B37a", "B37b", "B37c", "B37d",
    "B38", "B39", "B40", "B41", "B42", "B43",
    "B44", "B45", "B46a", "B46b", "B46c",
    "B48", "B49", "B50", "B51", "B52", "B53a", "B53b",
    "B54", "B55a", "B55b", "B56", "B57", "B58", "B59",
    "B60", "B61", "B62", "B63", "B64", "B65",
})

# Same idea for the status distribution: a snapshot, not a formula. If a
# requirement's status legitimately changes (e.g. a "gap" gets written up
# in phase 13 and becomes "done"), update this dict in that same commit --
# a test that never needs updating as work actually happens isn't testing
# anything.
_EXPECTED_STATUS_COUNTS = {
    "done": 49,
    "planned": 12,
    "gap": 10,
    "N/A": 1,
    "parent": 1,
}

# Block-level tags that must not glue adjacent text together when stripped
# (e.g. two separate <li> items). Everything else (a, b, code, em, span,
# ...) is inline and collapses with no separating space, matching how a
# browser actually renders it. Getting this wrong silently inserts spaces
# mid-phrase around a <code> span (e.g. "(schema.sql)" -> "( schema.sql )")
# and breaks every quote check that happens to span one -- verified
# empirically against this exact brief while building the registry.
_BLOCK_TAGS = (
    r"(?:p|div|li|tr|td|th|br|h[1-6]|ul|ol|blockquote|header|footer"
    r"|section|table|tbody|thead|body|html)"
)

_STATUSES = {"done", "planned", "gap", "N/A", "parent"}


def _brief_visible_text() -> str:
    """The brief's rendered text, whitespace-collapsed to one line -- the
    same shape a person reading the page in a browser sees, so a quote
    copied by eye matches a quote checked by code."""
    raw = BRIEF_HTML.read_text(encoding="utf-8")
    raw = re.sub(r"<(script|style|head)[^>]*>.*?</\1>", " ", raw, flags=re.S | re.I)
    raw = re.sub(rf"</?{_BLOCK_TAGS}(?:\s[^>]*)?>", " ", raw, flags=re.I)
    raw = re.sub(r"<[^>]+>", "", raw)  # remaining (inline) tags: no space inserted
    raw = html_lib.unescape(raw)
    return re.sub(r"\s+", " ", raw).strip()


def _parse_requirements() -> list[dict[str, str]]:
    """Parse every data row out of REQUIREMENTS.md's markdown tables.
    A data row is any line shaped "| **Bxx** | ... |" with exactly 9
    cells -- headers and "|---|...|" separators don't match that shape
    and are silently skipped, the same convention as
    tests/test_features.py's docs/feature_matrix.md parser."""
    text = REQUIREMENTS_MD.read_text(encoding="utf-8")
    rows: list[dict[str, str]] = []
    for line in text.splitlines():
        line = line.strip()
        if not line.startswith("| **B"):
            continue
        cells = [c.strip() for c in line.strip("|").split("|")]
        if len(cells) != 9:
            continue
        rows.append({
            "id": cells[0].strip("*"),
            "source": cells[1],
            "quote": cells[2].strip('"'),
            "obligation": cells[3],
            "owner": cells[4],
            "contributors": cells[5],
            "verifier": cells[6],
            "status": cells[7],
            "evidence": cells[8],
        })
    return rows


@pytest.fixture(scope="module")
def requirements() -> list[dict[str, str]]:
    rows = _parse_requirements()
    assert rows, "parsed zero rows -- REQUIREMENTS.md table shape must have changed"
    return rows


@pytest.fixture(scope="module")
def brief_text() -> str:
    return _brief_visible_text()


def test_every_id_is_well_formed_and_unique(requirements):
    ids = [r["id"] for r in requirements]
    malformed = [i for i in ids if not re.fullmatch(r"B\d+[a-z]?", i)]
    assert malformed == [], f"malformed requirement ids: {malformed}"
    dupes = sorted(i for i, n in Counter(ids).items() if n > 1)
    assert dupes == [], f"duplicate requirement ids: {dupes}"


def test_every_source_quote_is_verbatim_in_the_brief(requirements, brief_text):
    """The whole point of the registry: a quote that isn't actually in the
    brief (typo, paraphrase, stray backslash from markdown escaping) means
    the requirement it grounds might not be real."""
    missing = [
        r["id"] for r in requirements
        if re.sub(r"\s+", " ", r["quote"]).strip() not in brief_text
    ]
    assert missing == [], (
        f"source_quote not found verbatim in FunnelIQ_Assignment.html for: {missing}"
    )


def test_every_status_value_is_one_of_the_five_known_ones(requirements):
    bad = {r["id"]: r["status"] for r in requirements if r["status"] not in _STATUSES}
    assert bad == {}, f"unknown status values: {bad}"


def test_every_non_parent_non_optional_requirement_has_exactly_one_owner(requirements):
    """A requirement can be tracked by several contributing phases, but it
    must have exactly one owner -- otherwise "who closes this" has no
    answer. parent rows (B54) and N/A rows (B58, declined in the brief
    itself) are exempt by design."""
    bad = [
        r["id"] for r in requirements
        if r["status"] not in ("parent", "N/A")
        and (not r["owner"] or r["owner"] in ("—", "-") or "," in r["owner"])
    ]
    assert bad == [], f"requirements without exactly one owner: {bad}"


def test_every_done_requirement_has_evidence(requirements):
    bad = [
        r["id"] for r in requirements
        if r["status"] == "done" and r["evidence"] in ("", "—", "-")
    ]
    assert bad == [], f"'done' requirements with no evidence: {bad}"


def test_parent_requirement_points_at_real_children(requirements):
    """B54 ('parent') doesn't close on its own -- its evidence cell names
    the children that do. Every one of those must actually exist in the
    table, or the parent points at nothing."""
    ids = {r["id"] for r in requirements}
    parents = [r for r in requirements if r["status"] == "parent"]
    assert parents, "expected at least one parent requirement (B54)"
    for p in parents:
        children = re.findall(r"\bB\d+[a-z]?\b", p["evidence"])
        assert children, f"{p['id']}: parent row names no child ids in its evidence cell"
        missing = [c for c in children if c not in ids]
        assert missing == [], f"{p['id']}: children not present in the table: {missing}"


def test_registry_contains_exactly_the_expected_73_ids(requirements):
    """Six passing tests above only check the SHAPE of whatever rows
    happen to be in the table -- they say nothing if a row is quietly
    deleted, since a smaller table with well-formed rows still passes all
    of them. This is the test that would have caught that: it locks the
    exact id set, not just its size, so both a deletion and a silent
    rename fail loudly instead of just shrinking a count nobody watches."""
    actual = {r["id"] for r in requirements}
    missing = sorted(_EXPECTED_IDS - actual)
    extra = sorted(actual - _EXPECTED_IDS)
    assert not missing and not extra, (
        f"requirement id set drifted from the expected snapshot -- "
        f"missing: {missing}, unexpected/new: {extra}. If this is a "
        f"legitimate addition/split/retraction, update _EXPECTED_IDS in "
        f"this file in the same commit as REQUIREMENTS.md."
    )


def test_status_counts_match_expected_snapshot(requirements):
    """Same rationale as the id-set lock, for status drift: a requirement
    silently flipping from 'done' to 'gap' (or vice versa) doesn't break
    any structural check above, but it does mean someone's claim about
    what's actually finished just changed underneath the registry."""
    actual = dict(Counter(r["status"] for r in requirements))
    assert actual == _EXPECTED_STATUS_COUNTS, (
        f"status counts drifted from the expected snapshot -- "
        f"expected {_EXPECTED_STATUS_COUNTS}, got {actual}. If this is a "
        f"legitimate status change, update _EXPECTED_STATUS_COUNTS in "
        f"this file in the same commit as REQUIREMENTS.md."
    )


def _roadmap_b_registry_status_counts() -> dict[str, int]:
    """Parse the five (status, count) rows out of ROADMAP.html's own
    'עקיבות מלאה לדרישות הבריף' summary card -- the one human-facing
    place that restates REQUIREMENTS.md's counts by hand. It is
    documented there as a summary, not a second source of truth; this
    test is what keeps that true instead of aspirational."""
    html = ROADMAP_HTML.read_text(encoding="utf-8")
    marker = "עקיבות מלאה לדרישות הבריף"
    start = html.find(marker)
    assert start != -1, "ROADMAP.html no longer contains the B-registry summary card"
    table_start = html.find("<table", start)
    table_end = html.find("</table>", table_start)
    table_html = html[table_start:table_end]
    rows = re.findall(
        r"<tr><td>([^<]+)</td><td>[^<]*</td><td>(\d+)</td></tr>", table_html
    )
    assert rows, "could not parse any (status, count) rows out of the B-registry card"
    return {status: int(count) for status, count in rows}


def test_roadmap_b_registry_summary_matches_the_real_counts(requirements):
    """ROADMAP.html's summary card is hand-written HTML, not generated
    from REQUIREMENTS.md -- nothing stops it from drifting the moment
    either file is edited alone. This closes that gap: the counts shown
    to a human in ROADMAP.html must match what's actually in the
    registry, every time either one changes."""
    actual = dict(Counter(r["status"] for r in requirements))
    shown = _roadmap_b_registry_status_counts()
    assert shown == actual, (
        f"ROADMAP.html's B-registry summary card ({shown}) has drifted "
        f"from docs/planning/REQUIREMENTS.md's real status counts "
        f"({actual}) -- update the card's hardcoded numbers to match."
    )
