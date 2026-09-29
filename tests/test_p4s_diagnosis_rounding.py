"""Phase 12A, CP1 (docs/planning/PHASE12A.md §ג): boundary test for
scripts/p4s_diagnosis.py's js_math_round, the Python translation of JS
`Math.round` used to compute A1's displayed P4S score.

Codex's second review round (27.09.2026) found the first version
(`math.floor(x + 0.5)`) unsafe: adding 0.5 in IEEE-754 double
arithmetic can itself round the sum up to the next representable
double before `floor` ever runs, at values just below 0.5 --
`0.49999999999999994` is exactly such a case. Every reference value
below was read directly from a real V8 (`node -e
"console.log(Math.round(...))"`, Node v24), not derived from the
Python implementation under test -- this is a check against the
external spec, not a tautology."""
from __future__ import annotations

from scripts.p4s_diagnosis import js_math_round

# (input, Node's own Math.round output) -- verified live, not assumed.
NODE_MATH_ROUND_REFERENCE = [
    (0.49999999999999994, 0),  # the failure case: floor(x+0.5) wrongly gave 1
    (0.5, 1),
    (0.5000000000000001, 1),
    (1.5, 2),
    (2.5, 3),
    (0.0, 0),
    (21.681597964758982, 22),  # a real A1 event_probability * 100
    (1.0241033056231081, 1),
]


def test_matches_math_round_at_the_0_5_boundary_from_below():
    """The specific case Codex found: strictly less than 0.5 must
    round DOWN, even though naive floor(x+0.5) rounds it up."""
    assert js_math_round(0.49999999999999994) == 0


def test_matches_node_math_round_reference_values():
    for x, expected in NODE_MATH_ROUND_REFERENCE:
        assert js_math_round(x) == expected, f"js_math_round({x!r}) != Math.round({x!r}) ({expected})"
