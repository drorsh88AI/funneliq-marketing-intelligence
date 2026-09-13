"""Automated design-token checks (docs/planning/PHASE10.md D3-a,
checkpoint 4). Nine tests, reading two files directly off disk with no
new dependency and no CSS parser library:

  app/static/tokens.css  -- the values (checkpoint 3)
  docs/DESIGN.md          -- the rules: which token goes where, and why
                             (checkpoint 1/2)

These tests read the actual files, not a hardcoded copy of their
content -- a future edit to either file is checked against the other
automatically.
"""
from __future__ import annotations

import ast
import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
TOKENS_CSS = ROOT / "app" / "static" / "tokens.css"
DESIGN_MD = ROOT / "docs" / "DESIGN.md"
IA_MD = ROOT / "docs" / "IA.md"
SCHEMAS_PY = ROOT / "app" / "schemas.py"

# ---------------------------------------------------------------------------
# tokens.css parsing -- comments stripped, then every `--name: value;`
# line under :root becomes one dict entry. No CSS library: the file's
# own canonical-format rule (one declaration per line, always `;`
# terminated) is exactly what makes a two-line regex sufficient.
# ---------------------------------------------------------------------------


def _extract_tokens(css_text: str) -> dict[str, str]:
    no_comments = re.sub(r"/\*.*?\*/", "", css_text, flags=re.S)
    root_match = re.search(r":root\s*\{(.*)\}", no_comments, re.S)
    assert root_match, "tokens.css has no :root block"
    tokens: dict[str, str] = {}
    for line in root_match.group(1).split("\n"):
        line = line.strip()
        if not line:
            continue
        m = re.match(r"^(--[a-z0-9-]+):\s*(.+);$", line)
        assert m, f"tokens.css: malformed declaration (not `--name: value;`): {line!r}"
        assert m.group(1) not in tokens, f"tokens.css: duplicate token {m.group(1)}"
        tokens[m.group(1)] = m.group(2).strip()
    return tokens


def _resolve_hex(value: str, tokens: dict[str, str], _seen: frozenset[str] = frozenset()) -> str:
    """Follow one or more var(--x) hops down to a literal #rrggbb."""
    m = re.match(r"^var\((--[a-z0-9-]+)\)$", value)
    if not m:
        return value
    ref = m.group(1)
    assert ref not in _seen, f"tokens.css: circular var() reference at {ref}"
    assert ref in tokens, f"tokens.css: var() references undefined token {ref}"
    return _resolve_hex(tokens[ref], tokens, _seen | {ref})


def _relative_luminance(hex_color: str) -> float:
    hex_color = hex_color.lstrip("#")
    r, g, b = (int(hex_color[i : i + 2], 16) for i in (0, 2, 4))

    def channel(c: int) -> float:
        c = c / 255
        return c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4

    return 0.2126 * channel(r) + 0.7152 * channel(g) + 0.0722 * channel(b)


def contrast_ratio(hex_a: str, hex_b: str) -> float:
    """WCAG 2.1 contrast ratio between two #rrggbb colors."""
    l1, l2 = _relative_luminance(hex_a), _relative_luminance(hex_b)
    lighter, darker = (l1, l2) if l1 >= l2 else (l2, l1)
    return (lighter + 0.05) / (darker + 0.05)


def _declared_fg_bg_pairs(tokens: dict[str, str]) -> list[tuple[str, str, str]]:
    """Every (-fg, -bg) pair found by tokens.css's own naming convention."""
    bases = sorted(
        {re.sub(r"-(fg|bg)$", "", name) for name in tokens if name.endswith(("-fg", "-bg"))}
    )
    return [
        (base, tokens[base + "-fg"], tokens[base + "-bg"])
        for base in bases
        if base + "-fg" in tokens and base + "-bg" in tokens
    ]


@pytest.fixture(scope="module")
def tokens() -> dict[str, str]:
    return _extract_tokens(TOKENS_CSS.read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def design_md_text() -> str:
    return DESIGN_MD.read_text(encoding="utf-8")


@pytest.fixture(scope="module")
def ia_md_text() -> str:
    return IA_MD.read_text(encoding="utf-8")


# ---------------------------------------------------------------------------
# Test 1 -- WCAG AA (>=4.5:1) for every declared fg/bg pair. Pairs are
# discovered by naming convention, not a maintained list, so a new pair
# added later is checked automatically without touching this test.
# ---------------------------------------------------------------------------


def test_1_declared_fg_bg_pairs_meet_normal_text_contrast(tokens):
    pairs = _declared_fg_bg_pairs(tokens)
    assert pairs, "no declared -fg/-bg pairs found in tokens.css"
    failures = []
    for base, fg, bg in pairs:
        fg_hex, bg_hex = _resolve_hex(fg, tokens), _resolve_hex(bg, tokens)
        ratio = contrast_ratio(fg_hex, bg_hex)
        if ratio < 4.5:
            failures.append(f"{base}: {fg_hex} on {bg_hex} = {ratio:.2f} (< 4.5)")
    assert not failures, "\n".join(failures)


# ---------------------------------------------------------------------------
# Test 2 -- >=3:1 for the interface-critical graphical fills named in
# DESIGN.md's D10 palette (docs/DESIGN.md SS3.1): the four
# prediction/observed-outcome colors, plus the darkest tier step used
# as a solid fill in the tier table.
# ---------------------------------------------------------------------------

GRAPHICAL_ROLE_TOKENS = (
    "--color-primary",
    "--color-positive",
    "--color-negative",
    "--color-uncertain",
    "--color-tier-3-bg",
)


def test_2_graphical_role_tokens_meet_large_element_contrast(tokens):
    bg = _resolve_hex(tokens["--color-bg"], tokens)
    failures = []
    for name in GRAPHICAL_ROLE_TOKENS:
        assert name in tokens, f"{name} is missing from tokens.css"
        fg_hex = _resolve_hex(tokens[name], tokens)
        ratio = contrast_ratio(fg_hex, bg)
        if ratio < 3.0:
            failures.append(f"{name}: {fg_hex} vs page bg {bg} = {ratio:.2f} (< 3.0)")
    assert not failures, "\n".join(failures)


# ---------------------------------------------------------------------------
# Test 3 -- chart-eligible colors vs background, >=3:1. DESIGN.md SS4
# ("up to five semantic colors") reuses the same semantic palette for
# charts rather than defining a separate chart-only set -- per-chart
# assignment is checkpoint 5's job, not this one's. This test verifies
# every color DESIGN.md permits for chart use already clears the bar,
# so whichever one checkpoint 5 assigns to which chart, it qualifies.
# ---------------------------------------------------------------------------

CHART_ELIGIBLE_TOKENS = (
    "--color-primary",
    "--color-positive",
    "--color-negative",
    "--color-uncertain",
)


def test_3_chart_eligible_colors_meet_contrast_vs_background(tokens):
    bg = _resolve_hex(tokens["--color-bg"], tokens)
    failures = []
    for name in CHART_ELIGIBLE_TOKENS:
        fg_hex = _resolve_hex(tokens[name], tokens)
        ratio = contrast_ratio(fg_hex, bg)
        if ratio < 3.0:
            failures.append(f"{name}: {fg_hex} vs {bg} = {ratio:.2f} (< 3.0)")
    assert not failures, "\n".join(failures)


# ---------------------------------------------------------------------------
# Test 4 -- structural comparison of the per-screen state matrix: every
# screen row IA.md SS9.1 defines must have a matching row in DESIGN.md
# SS2.1 with all four state columns (loading/empty/error/OOD) non-empty.
# Both tables share the header `| מסך | loading | empty | error | OOD |`
# (DESIGN.md SS2.1 cites IA.md SS9.1 as its source) -- parsed as markdown
# tables and compared cell-by-cell, not by scanning for loose keywords.
# ---------------------------------------------------------------------------

_STATE_TABLE_HEADER = re.compile(
    r"\|\s*מסך\s*\|\s*`loading`\s*\|\s*`empty`\s*\|\s*`error`\s*\|\s*`OOD`\s*\|"
)

# Substrings that identify the same screen across both documents, even
# though the two documents don't use identical row labels verbatim
# (e.g. IA.md's "טופס החיזוי" vs DESIGN.md's "טופס חיזוי משותף").
_SCREEN_MARKERS = ("Login", "Overview", "טופס", "P4S", "Follow-up", "Budget Simulator")


def _extract_markdown_table(text: str, header_pattern: re.Pattern) -> list[list[str]]:
    """Return the data rows (list of cell strings) of the first markdown
    table whose header line matches header_pattern. Stops at the first
    blank line or non-`|`-prefixed line after the header/separator."""
    lines = text.split("\n")
    for i, line in enumerate(lines):
        if header_pattern.search(line):
            rows = []
            # lines[i] = header, lines[i+1] = |---|---|... separator
            for row_line in lines[i + 2 :]:
                stripped = row_line.strip()
                if not stripped.startswith("|"):
                    break
                cells = [c.strip() for c in stripped.strip("|").split("|")]
                rows.append(cells)
            return rows
    raise AssertionError(f"no markdown table found with header matching {header_pattern.pattern!r}")


def _row_by_marker(rows: list[list[str]], doc_label: str) -> dict[str, list[str]]:
    """Map every row in `rows` to exactly one of _SCREEN_MARKERS -- not
    just look up the six known markers and ignore anything else. A row
    matching zero markers (a screen the fixed list doesn't know about
    yet) or more than one (an ambiguous label) fails loudly here instead
    of being silently skipped, which is what let an extra IA.md row slip
    past unnoticed before this fix."""
    by_marker: dict[str, list[str]] = {}
    for row in rows:
        matches = [marker for marker in _SCREEN_MARKERS if marker in row[0]]
        assert len(matches) == 1, (
            f"{doc_label} row {row[0]!r} matches {len(matches)} screen markers "
            f"(expected exactly 1): {matches}"
        )
        marker = matches[0]
        assert marker not in by_marker, f"{doc_label}: two rows both match marker {marker!r}"
        by_marker[marker] = row
    return by_marker


def test_4_every_ia_section_9_state_has_a_component(ia_md_text, design_md_text):
    ia_rows = _extract_markdown_table(ia_md_text, _STATE_TABLE_HEADER)
    design_rows = _extract_markdown_table(design_md_text, _STATE_TABLE_HEADER)
    assert ia_rows, "docs/IA.md: state matrix (SS9.1) has no data rows"
    assert design_rows, "docs/DESIGN.md: state matrix (SS2.1) has no data rows"

    ia_by_marker = _row_by_marker(ia_rows, "docs/IA.md SS9.1")
    design_by_marker = _row_by_marker(design_rows, "docs/DESIGN.md SS2.1")

    # every row in EITHER table must be one of the known screens, and the
    # known screen set must be covered exactly -- not just "each of the
    # six known markers appears somewhere", which is silent about a
    # screen IA.md adds that isn't one of the six yet.
    assert set(ia_by_marker) == set(_SCREEN_MARKERS), (
        f"docs/IA.md SS9.1 screens {sorted(ia_by_marker)} don't match the known "
        f"set {sorted(_SCREEN_MARKERS)} exactly"
    )
    assert set(design_by_marker) == set(_SCREEN_MARKERS), (
        f"docs/DESIGN.md SS2.1 screens {sorted(design_by_marker)} don't match the "
        f"known set {sorted(_SCREEN_MARKERS)} exactly"
    )

    failures = []
    for marker in _SCREEN_MARKERS:
        ia_row = ia_by_marker[marker]
        design_row = design_by_marker[marker]
        assert len(ia_row) == 5, f"IA.md row for {marker!r} does not have 5 columns: {ia_row}"
        assert len(design_row) == 5, f"DESIGN.md row for {marker!r} does not have 5 columns: {design_row}"
        # all four state columns (loading/empty/error/OOD) must be
        # non-empty in DESIGN.md for every screen IA.md defines
        for col_name, cell in zip(("loading", "empty", "error", "OOD"), design_row[1:]):
            if not cell:
                failures.append(f"DESIGN.md row {marker!r}, column {col_name!r} is empty")
    assert not failures, "\n".join(failures)


# ---------------------------------------------------------------------------
# Test 5 -- every field on the six live contract schemas maps to a
# displayed component or an explicit non-display justification (F2),
# checked against its OWN docs/DESIGN.md SS5.x subsection ONLY -- not
# Section 5 as one pooled set. Pooling let a field deleted from one
# schema's table (e.g. SuperCustomerPrediction's `event_probability` row
# missing from SS5.3) still pass because the SAME bare name is
# documented for a DIFFERENT schema in SS5.2 -- each schema's fields are
# independent facts about that schema, not interchangeable. Nested
# sub-model fields (interval_details.*, metrics.cv.*/.holdout.*) are
# flattened to their real leaf paths, the two container fields Section 5
# documents as "decomposed into their own class's rows instead of an
# independent row" (StrategyResult.allocations, BudgetSimulation.strategies)
# are skipped in favor of walking their nested class directly, and the
# `warnings` field expects one row per ACTUAL discriminated-union member
# name declared in app/schemas.py for that field's own warning type --
# not merely "some bracket-suffixed row exists" (which let a wrong
# member name, e.g. warnings[OODWarning] on SuperCustomerPrediction
# instead of warnings[SuperCustomerOODWarning], go unnoticed).
# ---------------------------------------------------------------------------

SCHEMA_CLASSES = (
    "LtvPrediction",
    "PropensityPrediction",
    "SuperCustomerPrediction",
    "BudgetSimulation",
    "StrategyResult",
    "BudgetAllocation",
)

# Which SS5.x subsection documents each schema's fields -- BudgetSimulation,
# StrategyResult and BudgetAllocation all share SS5.4.
_SUBSECTION_FOR_CLASS = {
    "LtvPrediction": "5.1",
    "PropensityPrediction": "5.2",
    "SuperCustomerPrediction": "5.3",
    "BudgetSimulation": "5.4",
    "StrategyResult": "5.4",
    "BudgetAllocation": "5.4",
}

# Sub-models that Section 5 documents as dotted leaf paths under their
# parent field (e.g. `interval_details.nominal_coverage`) rather than as
# a bare field name -- recursed into instead of treated as one leaf.
_SUBMODEL_TYPES = {
    "IntervalDetails",
    "RegressionMetrics",
    "ClassificationMetrics",
    "_CvRegression",
    "_HoldoutRegression",
    "_CvClassification",
    "_HoldoutClassification",
}

# list[X] fields where X is itself one of SCHEMA_CLASSES: Section 5's own
# note says these containers are "decomposed into their nested fields in
# the table below" under X's own class-prefixed rows, not an independent
# row for the container field itself.
_DECOMPOSED_ELSEWHERE = ("StrategyResult", "BudgetAllocation")
_DECOMPOSED_LIST_TYPES = {f"list[{c}]" for c in _DECOMPOSED_ELSEWHERE}

# P2/P3/P4S are documented with bare field names; P6's three classes are
# documented with a `ClassName.` prefix on every field (docs/DESIGN.md SS5.4).
_TOP_LEVEL_PREFIX = {
    "LtvPrediction": "",
    "PropensityPrediction": "",
    "SuperCustomerPrediction": "",
    "BudgetSimulation": "BudgetSimulation.",
    "StrategyResult": "StrategyResult.",
    "BudgetAllocation": "BudgetAllocation.",
}


def _schema_field_defs(schemas_src: str, class_name: str) -> list[tuple[str, str, str]]:
    """(name, bare_type, full_definition_text) for each annotated field
    declared directly in the class body -- via ast.parse, not a regex
    that stops at the class's first blank line. That regex previously
    returned [] for IntervalDetails/RegressionMetrics/ClassificationMetrics:
    each has a docstring followed by a blank line BEFORE its fields, so
    `(.*?)\\n\\n` matched only the docstring and never reached a single
    field -- silently making every nested nominal_coverage/mean_mae/etc.
    path unchecked by test 5 (they were skipped, not verified)."""
    tree = ast.parse(schemas_src)
    class_node = next(
        (n for n in ast.walk(tree) if isinstance(n, ast.ClassDef) and n.name == class_name),
        None,
    )
    assert class_node is not None, f"app/schemas.py: class {class_name} not found"
    fields = []
    for stmt in class_node.body:
        if isinstance(stmt, ast.AnnAssign) and isinstance(stmt.target, ast.Name):
            type_str = ast.unparse(stmt.annotation)
            full_def = type_str if stmt.value is None else f"{type_str} = {ast.unparse(stmt.value)}"
            fields.append((stmt.target.id, type_str, full_def))
    return fields


def _warning_union_members(schemas_src: str, alias_name: str) -> tuple[str, ...]:
    """The member type names of a module-level `X = Annotated[Union[A, B],
    Field(discriminator=...)]` alias (ContractWarning / SuperCustomer-
    ContractWarning) -- read from app/schemas.py itself via ast, not
    hardcoded, so a future warning type added to the union is picked up
    automatically. ast.unparse normalizes the assignment to one line
    first, so the alias's own multi-line source formatting doesn't matter."""
    tree = ast.parse(schemas_src)
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign) and any(
            isinstance(t, ast.Name) and t.id == alias_name for t in node.targets
        ):
            unparsed = ast.unparse(node.value)
            m = re.search(r"Union\[([^\]]+)\]", unparsed)
            assert m, f"app/schemas.py: {alias_name} is not a Union[...] alias: {unparsed}"
            return tuple(name.strip() for name in m.group(1).split(","))
    raise AssertionError(f"app/schemas.py: module-level assignment {alias_name} not found")


def _flatten_expected_paths(schemas_src: str, class_name: str, prefix: str) -> list[str]:
    """Every leaf field path Section 5 is expected to document for
    class_name, recursing into known sub-models. The `warnings` field
    expands to one exact path per discriminated-union member declared
    for THIS field's own warning-union alias (e.g. `warnings[OODWarning]`
    and `warnings[UnobservedBudgetWarning]` for ContractWarning) -- a
    schema whose warnings type is a different alias (SuperCustomer-
    ContractWarning) gets that alias's own member names, not a generic
    "any bracket suffix" pass."""
    expected = []
    for name, type_str, full_def in _schema_field_defs(schemas_src, class_name):
        path = prefix + name
        if type_str in _SUBMODEL_TYPES:
            expected.extend(_flatten_expected_paths(schemas_src, type_str, path + "."))
        elif type_str in _DECOMPOSED_LIST_TYPES:
            continue
        elif name == "warnings":
            if "max_length=0" in full_def:
                expected.append(path)  # always empty in practice -- documented as a bare field
            else:
                m = re.match(r"^list\[(\w+)\]$", type_str)
                assert m, f"app/schemas.py: unexpected `warnings` type shape: {type_str!r}"
                for member in _warning_union_members(schemas_src, m.group(1)):
                    expected.append(f"{path}[{member}]")
        else:
            expected.append(path)
    return expected


def _extract_subsection_rows(design_md_text: str, subsection: str) -> list[list[str]]:
    """Field rows from exactly one SS5.x subsection (e.g. "5.1"), not
    Section 5 as a whole -- SS5.4 is shared by three schema classes, so
    it's returned once per lookup, not merged across all four."""
    pattern = rf"### {re.escape(subsection)} .*?\n(.*?)(?=\n### |\n## 6\.)"
    m = re.search(pattern, design_md_text, re.S)
    assert m, f"docs/DESIGN.md: subsection SS{subsection} not found"
    rows = []
    for line in m.group(1).split("\n"):
        stripped = line.strip()
        if not stripped.startswith("|"):
            continue
        cells = [c.strip() for c in stripped.strip("|").split("|")]
        if len(cells) >= 3 and cells[0].startswith("`"):
            rows.append(cells)
    return rows


def _field_paths_in_cell(cell: str) -> list[str]:
    """Expand a Section 5 field cell into full dotted paths. A segment
    starting with "." is shorthand for "same parent as the previous
    segment, different last component" (e.g. `` `a.b` · `.c` `` means
    `a.b` and `a.c`) -- Section 5's own compact-but-literal convention,
    distinct from the wildcard/parenthetical notation that was removed
    from it in this fix round."""
    segments = re.findall(r"`([^`]+)`", cell)
    paths: list[str] = []
    prev = None
    for seg in segments:
        if seg.startswith("."):
            assert prev is not None, f"leading-dot continuation with no preceding field: {cell!r}"
            full = prev.rsplit(".", 1)[0] + seg
        else:
            full = seg
        paths.append(full)
        prev = full
    return paths


def test_5_every_schema_field_maps_to_a_component_or_justification(design_md_text):
    schemas_src = SCHEMAS_PY.read_text(encoding="utf-8")
    failures = []

    # one pass per subsection (not per class) -- SS5.4 is shared by three
    # classes and should only be parsed/duplicate-checked once
    documented_by_subsection: dict[str, set[str]] = {}
    for subsection in sorted(set(_SUBSECTION_FOR_CLASS.values())):
        rows = _extract_subsection_rows(design_md_text, subsection)
        assert rows, f"docs/DESIGN.md SS{subsection} has no field rows"
        seen: set[str] = set()
        for row in rows:
            assert row[2], f"docs/DESIGN.md SS{subsection}: row {row[0]!r} has an empty mapping/justification cell"
            for path in _field_paths_in_cell(row[0]):
                if path in seen:
                    failures.append(f"docs/DESIGN.md SS{subsection}: {path!r} is documented more than once")
                seen.add(path)
        documented_by_subsection[subsection] = seen

    for cls in SCHEMA_CLASSES:
        subsection = _SUBSECTION_FOR_CLASS[cls]
        documented = documented_by_subsection[subsection]
        for expected in _flatten_expected_paths(schemas_src, cls, _TOP_LEVEL_PREFIX[cls]):
            if expected not in documented:
                failures.append(f"{cls} (docs/DESIGN.md SS{subsection}): field with no mapping: {expected}")
    assert not failures, "\n".join(failures)


# ---------------------------------------------------------------------------
# Test 6 -- no orphan token: every value tokens.css defines is cited
# somewhere in DESIGN.md. `-fg`/`-bg`/`-color`/`-font-size` are
# implementation-detail suffixes on one conceptual token (DESIGN.md
# names the concept; tokens.css gives it CSS-level shape), so the
# suffix is stripped before checking. Matching is backtick-exact
# (`` `name` `` as a whole word in markdown), not substring -- a plain
# `in` check false-positives whenever a token's stripped base is itself
# a substring of unrelated text (e.g. base "color" trivially matches
# inside "color-primary" elsewhere in the doc even when "color" alone
# was never documented).
# ---------------------------------------------------------------------------

_SUFFIXES = ("-fg", "-bg", "-color", "-font-size")


def _base_name(token: str) -> str:
    bare = token[2:]  # drop leading "--"
    for suffix in _SUFFIXES:
        if bare.endswith(suffix):
            return bare[: -len(suffix)]
    return bare


def _backtick_exact(name: str, text: str) -> bool:
    return re.search(r"`" + re.escape(name) + r"`", text) is not None


def test_6_no_orphan_tokens(tokens, design_md_text):
    orphans = [
        name
        for name in tokens
        if not _backtick_exact(name, design_md_text)
        and not _backtick_exact(_base_name(name), design_md_text)
    ]
    assert not orphans, f"tokens.css tokens not referenced anywhere in docs/DESIGN.md: {orphans}"


# ---------------------------------------------------------------------------
# Test 7 -- the reverse of test 6: no component in DESIGN.md points at
# a token that doesn't exist in tokens.css. Only literal, backtick-
# quoted `--name` references count (CSS custom-property syntax) -- a
# bare conceptual name like `evidence-high` is covered by test 6, not
# this one.
# ---------------------------------------------------------------------------


_FAMILY_WILDCARD = re.compile(r"`[a-z][a-z0-9-]*-\*`")


def test_7_no_dangling_token_references(tokens, design_md_text):
    referenced = set(re.findall(r"`(--[a-z][a-z0-9-]*)`", design_md_text))
    dangling = sorted(name for name in referenced if name not in tokens)
    assert not dangling, f"docs/DESIGN.md references tokens missing from tokens.css: {dangling}"

    # A "family" shorthand like `evidence-*` names no single token, so
    # neither this test nor test 6 can verify it exists or catch a typo
    # in it (a stray `evidnce-*` would pass both silently) -- explicit
    # token names, one per row cell, are the only form these two tests
    # can actually check.
    wildcards = _FAMILY_WILDCARD.findall(design_md_text)
    assert not wildcards, (
        f"docs/DESIGN.md uses family-wildcard token notation instead of explicit "
        f"names (neither test 6 nor test 7 can verify these): {wildcards}"
    )


# ---------------------------------------------------------------------------
# Test 8 -- canonical value format AND type, by token name: colors must
# resolve to a valid hex; font-size/space/radius must be non-negative;
# grid-columns must be a positive integer; shadow values must be within
# legal ranges (0-255 channels, alpha in [0,1]); and a var() reference is
# followed to its literal value with `_resolve_hex` (which itself
# asserts the referenced token exists and that there is no circular
# chain) before that literal is checked against the shape the
# REFERENCING token's own name demands -- `--focus-outline: var(--color-
# primary)` must resolve to a hex color, not merely "be a var()".
# ---------------------------------------------------------------------------

_LENGTH_NONNEG = r"(?:0|\d+(?:\.\d+)?(?:px|rem))"  # no leading "-": sizes/spacing/radius can't be negative
_HEX = re.compile(r"^#[0-9a-f]{6}$")
_LENGTH_ONLY = re.compile(rf"^{_LENGTH_NONNEG}$")
_UNITLESS_INT = re.compile(r"^\d+$")
_POSITIVE_INT = re.compile(r"^[1-9]\d*$")  # grid-columns: 0 columns is not a legal grid
_FONT_STACK = re.compile(r'^([a-zA-Z0-9\- ]+|"[^"]*")(,\s*([a-zA-Z0-9\- ]+|"[^"]*"))*$')
_SHADOW_LAYER = re.compile(
    rf"(?:{_LENGTH_NONNEG}\s+){{2,3}}rgba\((\d+),\s*(\d+),\s*(\d+),\s*([\d.]+)\)"
)


def _shadow_value_ok(value: str) -> bool:
    # A plain comma-split breaks each layer apart at the commas INSIDE
    # its own rgba(...) too -- consume the string layer by layer instead,
    # each match starting exactly where the previous one (plus its ", "
    # separator) ended, so nothing is silently skipped or double-counted.
    pos = 0
    matched_any = False
    for m in _SHADOW_LAYER.finditer(value):
        if m.start() != pos:
            return False
        r, g, b, a = m.groups()
        if not all(0 <= int(ch) <= 255 for ch in (r, g, b)):
            return False
        if not (0.0 <= float(a) <= 1.0):
            return False
        pos = m.end()
        matched_any = True
        if value[pos : pos + 2] == ", ":
            pos += 2
    return matched_any and pos == len(value)


# Dispatch by token NAME, not "does any shape match" -- a global
# whitelist would let the permissive font-stack pattern accept garbage
# meant to be a color or a length. Each name pattern below owns exactly
# one expected value shape; a color or length token must look like one.
_NAME_TO_CHECKER: tuple[tuple[re.Pattern, object], ...] = (
    (re.compile(r"^--font-family$"), lambda v: bool(_FONT_STACK.match(v))),
    (re.compile(r"^--(font-size|space|radius)-"), lambda v: bool(_LENGTH_ONLY.match(v))),
    # suffix form -- a role-derived name like --model-disclaimer-font-size
    # doesn't start with "font-size-" (the prefix rule above misses it)
    # but is still a length, not a color; a bare hex value for it must fail.
    (re.compile(r".*-font-size$"), lambda v: bool(_LENGTH_ONLY.match(v))),
    (re.compile(r"^--grid-gap$"), lambda v: bool(_LENGTH_ONLY.match(v))),
    (re.compile(r"^--grid-columns-"), lambda v: bool(_POSITIVE_INT.match(v))),
    (re.compile(r"^--shadow-"), _shadow_value_ok),
    # every color-role token, not just the ones with a -fg/-bg/-color
    # suffix -- --focus-outline and the bare --color-primary/positive/
    # negative/uncertain/muted/text tokens are colors too, and a var()
    # pointing one of them at a non-color token (e.g. a length) must be
    # caught here, not waved through by the permissive default below.
    (
        re.compile(r"^--.*-(fg|bg|color)$|^--focus-outline$|^--color-(primary|positive|negative|uncertain|muted|text)$"),
        lambda v: bool(_HEX.match(v)),
    ),
)


def _default_checker(v: str) -> bool:
    # names with no specific rule (e.g. --grid-gap, a length) still
    # must be a recognized primitive shape -- never free-form text
    return bool(_HEX.match(v) or _LENGTH_ONLY.match(v) or _UNITLESS_INT.match(v))


def _expected_shape_ok(name: str, value: str, tokens: dict[str, str]) -> bool:
    resolved = _resolve_hex(value, tokens)  # follows var() chains; asserts they exist and don't cycle
    for name_pattern, checker in _NAME_TO_CHECKER:
        if name_pattern.match(name):
            return checker(resolved)
    return _default_checker(resolved)


def test_8_every_value_is_one_canonical_recognized_format(tokens):
    failures = []
    for name, value in tokens.items():
        try:
            ok = _expected_shape_ok(name, value, tokens)
        except AssertionError as exc:
            failures.append(f"{name}: {exc}")
            continue
        if not ok:
            failures.append(f"{name}: {value!r} does not resolve to its expected shape")
    assert not failures, "\n".join(failures)


# ---------------------------------------------------------------------------
# Test 9 -- D9's six-column matrix closure (question / answer / meaning
# / action / limitation / evidence-source) for every panel and chart.
# ⛔ That matrix is checkpoint 6's deliverable and does not exist yet --
# this test is written now so it activates automatically the moment
# checkpoint 6 adds the matrix, rather than being invented after the
# fact to match whatever gets written.
# ---------------------------------------------------------------------------

# A markdown table *header row* carrying all six column names together
# is the actual matrix -- not a mention of it in a "not written yet"
# list (both current mentions in docs/DESIGN.md are exactly that kind
# of mention, which must NOT trigger this test's real check).
_D9_MATRIX_HEADER_ROW = re.compile(
    r"\|.*שאלת.*\|.*תשובה.*\|.*משמעות.*\|.*פעולה.*\|.*מגבלה.*\|.*מקור ראיה.*\|"
)


_D9_COLUMNS = ("שאלה", "תשובה", "משמעות", "פעולה", "מגבלה", "מקור ראיה")

# The exact eight panels/charts PHASE10.md D9 locks (docs/planning/PHASE10.md,
# D9: "מכוסים: Overview · P2 · P3 · P4 · P4S · Budget Simulator · שני גרפי
# Follow-up (נשירה, calls_to_closed)") -- Login is explicitly excluded (no
# result, no chart). Matched ONLY against the row's first cell (the
# question column) -- not the whole row -- because a legitimate answer,
# meaning, action or limitation cell may need to reference a DIFFERENT
# target (e.g. Overview's answer pointing a reader to "see P2 for detail",
# or the P4/P4S panels each needing to explain their difference from the
# other) without that being mistaken for a second target on the same row.
# Each pattern must match the first cell and not overlap another target's
# pattern (P4 vs P4S needs the negative lookahead below).
_D9_TARGET_PATTERNS: tuple[tuple[str, re.Pattern], ...] = (
    ("Overview", re.compile(r"Overview")),
    ("P2", re.compile(r"\bP2\b")),
    ("P3", re.compile(r"\bP3\b")),
    ("P4", re.compile(r"\bP4(?!S)\b")),
    ("P4S", re.compile(r"\bP4S\b")),
    ("Budget Simulator", re.compile(r"Budget Simulator")),
    ("Follow-up/dropoff", re.compile(r"נשירה")),
    ("Follow-up/calls_to_closed", re.compile(r"calls_to_closed")),
)


def test_9_d9_six_column_matrix_closure(design_md_text):
    if not _D9_MATRIX_HEADER_ROW.search(design_md_text):
        pytest.skip(
            "D9's six-column matrix is checkpoint 6's deliverable and is not "
            "written yet (docs/DESIGN.md Section 6 lists it as pending) -- "
            "this test will activate once a table with all six column "
            "headers (question/answer/meaning/action/limitation/evidence-"
            "source) actually exists."
        )
    rows = _extract_markdown_table(design_md_text, _D9_MATRIX_HEADER_ROW)
    assert rows, "docs/DESIGN.md: D9 six-column matrix has a header but no data rows"

    failures = []
    matched_targets: dict[str, list[str]] = {}
    for row in rows:
        if len(row) != 6:
            failures.append(f"row does not have exactly 6 columns: {row}")
            continue
        for col_name, cell in zip(_D9_COLUMNS, row):
            # An explicit "no unambiguous recommendation" statement is
            # itself non-empty content and satisfies this check -- only a
            # truly blank cell fails it.
            if not cell:
                failures.append(f"row {row[0]!r}: column {col_name!r} is empty")

        targets_hit = [name for name, pattern in _D9_TARGET_PATTERNS if pattern.search(row[0])]
        if len(targets_hit) != 1:
            failures.append(
                f"row {row[0]!r} (first cell) matches {len(targets_hit)} of the 8 "
                f"locked D9 targets (expected exactly 1): {targets_hit}"
            )
            continue
        target = targets_hit[0]
        if target in matched_targets:
            failures.append(f"D9 target {target!r} has more than one row: {matched_targets[target]!r} and {row[0]!r}")
        else:
            matched_targets[target] = row

    expected_targets = {name for name, _ in _D9_TARGET_PATTERNS}
    missing_targets = expected_targets - set(matched_targets)
    if missing_targets:
        failures.append(f"D9 matrix is missing rows for: {sorted(missing_targets)}")

    assert not failures, "\n".join(failures)
