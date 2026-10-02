"""REPORT.md builder -- PHASE13.md D2 (numbers), D8 (charts), A3.1 (feature
table), A3.2 (three majority rates).

REPORT.md is rendered from a template (string.Template, the pattern
scripts/analysis.py's render_findings_md already uses). Every quantitative
claim in the template is a $placeholder that must be declared in MANIFEST: a
source file, a path inside it, an optional derivation, and a number format.
A placeholder that is not in the manifest fails the render, and so does a
path that does not resolve, so no number can reach REPORT.md without a
declared origin.

SOURCES is a CLOSED list of committed JSON files. It deliberately does NOT
include the CSV, so the manifest can be checked in CI, where the CSV does not
exist.

Embedded blocks (BLOCKS) are cut verbatim from docs/feature_matrix.md, never
retyped.

This module also holds the chart-heading rule (D8 / PHASE13.md A5) and the
INFORMATIONAL digit scan of a template (PHASE5.md D6 section 5: a scan whose
output is reviewed, never an assertion).

CLI:
  python -m scripts.build_report                     render the template to REPORT.md
  python -m scripts.build_report --calibration-svg P4S
                                                     render docs/calibration_curve_P4S.svg
                                                     from models/metrics.json (no training)
"""
from __future__ import annotations

import json
import re
import sys
import unicodedata
from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal
from pathlib import Path
from string import Template

REPO = Path(__file__).resolve().parent.parent
DEFAULT_TEMPLATE = REPO / "docs" / "report_template.md"
DEFAULT_OUT = REPO / "REPORT.md"


class ReportError(Exception):
    """A manifest, source, block or chart-rule violation."""


# ---------------------------------------------------------------------------
# Sources -- the closed list (PHASE13.md D2).
# ---------------------------------------------------------------------------
SOURCES: dict[str, str] = {
    "metrics": "models/metrics.json",
    "findings": "docs/findings.json",
    "p6_simulation": "models/P6_simulation.json",
    "business_facts": "app/static/business_facts.json",
    "meta_P2": "models/P2.meta.json",
    "meta_P3": "models/P3.meta.json",
    "meta_P4": "models/P4.meta.json",
    "meta_P4S": "models/P4S.meta.json",
    "meta_P6": "models/P6.meta.json",
    "a2": "docs/p4s_a2_train_tiers.json",
}


class Sources:
    """Reads the closed source list from `root`, once each."""

    def __init__(self, root: Path = REPO) -> None:
        self.root = Path(root)
        self._cache: dict[str, object] = {}

    def get(self, name: str):
        if name not in SOURCES:
            raise ReportError(f"source {name!r} is not in the closed source list")
        if name not in self._cache:
            path = self.root / SOURCES[name]
            if not path.is_file():
                raise ReportError(f"source file missing: {SOURCES[name]}")
            self._cache[name] = json.loads(path.read_text(encoding="utf-8"))
        return self._cache[name]

    def value(self, source: str, path: tuple):
        node = self.get(source)
        walked = []
        for key in path:
            walked.append(key)
            try:
                node = node[key]
            except (KeyError, IndexError, TypeError):
                raise ReportError(f"path {list(walked)!r} does not resolve in {SOURCES[source]}") from None
        return node


# ---------------------------------------------------------------------------
# Manifest
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class Ref:
    """A number taken as-is from a source."""
    source: str
    path: tuple
    fmt: str


@dataclass(frozen=True)
class Derived:
    """A number computed from declared inputs by a NAMED formula, so the
    derivation is part of the manifest and not hidden in the template."""
    formula: str
    inputs: tuple          # ((source, path), ...), in the formula's argument order
    fmt: str


def _dec(value) -> Decimal:
    """Exact decimal of a JSON number: Decimal(repr(x)) is the shortest
    decimal that round-trips the float, so 1 - 0.4635 is exactly 0.5365
    instead of 0.5365000000000001."""
    if isinstance(value, bool) or not isinstance(value, (int, float, Decimal)):
        raise ReportError(f"not a number: {value!r}")
    number = value if isinstance(value, Decimal) else Decimal(repr(value))
    if not number.is_finite():
        # json.loads accepts NaN and Infinity, and Decimal formats them as text;
        # a report must never print "Accuracy: NaN%".
        raise ReportError(f"not a finite number: {value!r}")
    return number


DERIVED: dict[str, object] = {
    # 1 - x, e.g. the majority-class rate from the positive-class rate.
    "one_minus": lambda x: Decimal(1) - _dec(x),
    # (accuracy - majority) in percentage points, majority = 1 - base_rate.
    "accuracy_minus_majority_pp": lambda accuracy, base_rate: (_dec(accuracy) - (Decimal(1) - _dec(base_rate))) * 100,
}

MANIFEST: dict[str, Ref | Derived] = {
    # --- A3.2: three majority rates, each tied to ITS population -------------
    # all purchasers, before any split
    "n_purchasers_all": Ref("business_facts", ("super_customer_profile", "n_purchased"), "comma"),
    "majority_all_pct": Derived("one_minus", (("meta_P3", ("base_rate",)),), "pct2"),
    # the 5 cross-validation folds of the TRAINING split
    "n_train_p3": Ref("meta_P3", ("population_n", "train"), "comma"),
    "majority_cv_pct": Ref("metrics", ("P3", "dummy", "mean_accuracy"), "pct2"),
    # the Holdout
    "n_holdout_p3": Ref("metrics", ("P3_holdout", "n_holdout"), "comma"),
    "majority_holdout_pct": Derived("one_minus", (("metrics", ("P3_holdout", "lift_at_10", "base_rate")),), "pct2"),
    "p3_holdout_accuracy_pct": Ref("metrics", ("P3_holdout", "accuracy"), "pct2"),
    "p3_gain_over_majority_pp": Derived(
        "accuracy_minus_majority_pp",
        (("metrics", ("P3_holdout", "accuracy")), ("metrics", ("P3_holdout", "lift_at_10", "base_rate"))),
        "num2",
    ),
    # --- one entry per remaining source, so every source is exercised --------
    "missing_rows": Ref("findings", ("missing_values", "missing_any"), "int"),
    "leads_per_1000_lowest": Ref("findings", ("budget_leads_per_1000", "summary", "leads_per_1000_lowest"), "num1"),
    "super_share_of_total_profit_pct": Ref("business_facts", ("super_customer_profile", "pct_of_total_profit"), "pct1"),
    "p6_point_100x500": Ref("p6_simulation", ("100x500", "point"), "comma"),
    "p4s_holdout_roc_auc": Ref("metrics", ("P4S_holdout", "roc_auc"), "num3"),
    "p4s_train_n": Ref("meta_P4S", ("population_n", "train"), "comma"),
    "p6_train_n": Ref("meta_P6", ("population_n", "train"), "comma"),
    "p2_train_n": Ref("meta_P2", ("population_n", "train"), "comma"),
    "p4_train_n": Ref("meta_P4", ("population_n", "train"), "comma"),
    "a2_mid_n": Ref("a2", ("tiers", "Mid", "n"), "comma"),
    "a2_mid_super_rate_pct": Ref("a2", ("tiers", "Mid", "rate"), "pct1"),
}


# ---------------------------------------------------------------------------
# Number formatting. Half-up on the exact decimal, never float formatting:
# Python's format() rounds the exact halves 21.25 and 8.75 in opposite
# directions (CP1 finding).
# ---------------------------------------------------------------------------
def _quantize(value: Decimal, decimals: int) -> Decimal:
    return value.quantize(Decimal(1).scaleb(-decimals), rounding=ROUND_HALF_UP)


def format_value(value, fmt: str) -> str:
    """Format a number for the report. A value that is NOT zero but rounds to
    zero in `fmt` raises: printing 0.00 for 0.00004 (or -0.00 for -0.00004)
    states something false. The author must choose a finer format or write an
    explicit threshold phrase ("less than 0.01 points"). A true zero prints
    without a sign, so -0.0 never shows as -0.0."""
    d = _dec(value)
    if fmt == "int":
        if d != d.to_integral_value():
            raise ReportError(f"{value!r} is not an integer but is formatted as int")
        return str(int(d))
    if fmt == "comma":
        scaled, decimals = d, 0
    elif fmt.startswith("pct") and fmt[3:].isdigit():
        scaled, decimals = d * 100, int(fmt[3:])
    elif fmt.startswith("num") and fmt[3:].isdigit():
        scaled, decimals = d, int(fmt[3:])
    else:
        raise ReportError(f"unknown number format {fmt!r}")

    rounded = _quantize(scaled, decimals)
    if rounded == 0:
        if scaled != 0:
            raise ReportError(
                f"{value!r} is not zero but rounds to zero in format {fmt!r}: "
                "use a finer format or write an explicit threshold phrase"
            )
        rounded = abs(rounded)          # a true zero has no sign
    if fmt == "comma":
        return f"{int(rounded):,}"
    if fmt.startswith("pct"):
        return f"{rounded:f}"
    return f"{rounded:,f}"


# ---------------------------------------------------------------------------
# Embedded blocks, cut verbatim from docs/feature_matrix.md (A3.1).
# ---------------------------------------------------------------------------
FEATURE_MATRIX = REPO / "docs" / "feature_matrix.md"
_BLOCK_HEADINGS = {
    "feature_table": "## הטבלה",
    "feature_summary": "## סיכום פיצ'רים בפועל",
}


def table_after_heading(markdown: str, heading: str) -> str:
    """The first contiguous run of markdown table lines (starting with '|')
    after the line that is exactly `heading`, verbatim, joined by LF, with no
    trailing newline."""
    lines = markdown.splitlines()
    try:
        start = lines.index(heading)
    except ValueError:
        raise ReportError(f"heading {heading!r} not found in docs/feature_matrix.md") from None
    i = start + 1
    while i < len(lines) and not lines[i].startswith("|"):
        if lines[i].startswith("## "):
            raise ReportError(f"no table between {heading!r} and the next section")
        i += 1
    run = []
    while i < len(lines) and lines[i].startswith("|"):
        run.append(lines[i])
        i += 1
    if not run:
        raise ReportError(f"no table after {heading!r}")
    return "\n".join(run)


def block_value(name: str, root: Path = REPO) -> str:
    path = Path(root) / "docs" / "feature_matrix.md"
    if not path.is_file():
        raise ReportError("docs/feature_matrix.md is missing")
    return table_after_heading(path.read_text(encoding="utf-8"), _BLOCK_HEADINGS[name])


BLOCKS = tuple(_BLOCK_HEADINGS)


# ---------------------------------------------------------------------------
# Resolving and rendering
# ---------------------------------------------------------------------------
def resolve(name: str, sources: Sources) -> str:
    if name in BLOCKS:
        return block_value(name, sources.root)
    entry = MANIFEST[name]
    if isinstance(entry, Ref):
        return format_value(sources.value(entry.source, entry.path), entry.fmt)
    formula = DERIVED.get(entry.formula)
    if formula is None:
        raise ReportError(f"{name}: unknown derivation {entry.formula!r}")
    inputs = [sources.value(source, path) for source, path in entry.inputs]
    return format_value(formula(*inputs), entry.fmt)


def render_report(template_text: str, sources: Sources | None = None) -> str:
    """Substitute every placeholder from the manifest. Raises ReportError for
    a placeholder that is not declared (in the manifest or as a block)."""
    sources = sources or Sources()
    template = Template(template_text)
    names = template.get_identifiers()
    unknown = sorted(set(names) - set(MANIFEST) - set(BLOCKS))
    if unknown:
        raise ReportError(f"placeholders not declared in the manifest: {unknown}")
    values = {name: resolve(name, sources) for name in names}
    try:
        return template.substitute(values)
    except ValueError as exc:      # a bare or malformed `$` in the template
        raise ReportError(f"malformed placeholder in the template: {exc}") from exc


# ---------------------------------------------------------------------------
# The chart-heading rule (PHASE13.md D8 and appendix A5).
# ---------------------------------------------------------------------------
# Direction-control characters. A heading containing ANY of them fails, anywhere
# in the heading -- nine of them are skipped by a "first strong character" scan
# (they are not classes L/R/AL), so that scan alone would let them through.
DIRECTION_CONTROLS = frozenset(
    [0x200E, 0x200F, 0x061C] + list(range(0x202A, 0x202F)) + list(range(0x2066, 0x206A))
)


# A CommonMark ATX heading: up to 3 spaces of indent, 1-6 '#', then a space or
# tab (or the end of the line). `#text` (no space), 7 '#', and 4 spaces of indent
# (an indented code block) are NOT headings. Setext headings (underlined with
# === or ---) are deliberately not accepted: REPORT.md uses ATX only.
_ATX_HEADING = re.compile(r"^ {0,3}#{1,6}(?=[ \t]|$)")


def is_atx_heading(line: str) -> bool:
    return bool(_ATX_HEADING.match(line))


def rendered_heading_text(heading_line: str) -> str:
    """A markdown heading line as the reader sees it: heading marker and the
    optional closing '#' sequence removed, emphasis markers and code delimiters
    removed (code content kept), link/image URLs removed (label kept), HTML
    tags removed."""
    text = re.sub(r"^ {0,3}#{1,6}(?:[ \t]+|$)", "", heading_line)
    text = re.sub(r"[ \t]+#+[ \t]*$", "", text)
    text = re.sub(r"!?\[([^\]]*)\]\([^)]*\)", r"\1", text)
    text = re.sub(r"<[^>]+>", "", text)
    text = text.replace("**", "").replace("__", "").replace("`", "")
    return " ".join(text.split())


def _is_hebrew_letter(ch: str) -> bool:
    return 0x05D0 <= ord(ch) <= 0x05EA or 0x05F0 <= ord(ch) <= 0x05F2


def heading_rule_violation(rendered: str) -> str | None:
    """None if the rendered heading satisfies the rule, else the reason.
    Step 1: no direction-control character anywhere. Step 2: the first
    strongly directional character (bidi class L, R or AL) is a Hebrew letter;
    spaces, punctuation and digits before it are skipped."""
    for ch in rendered:
        if ord(ch) in DIRECTION_CONTROLS:
            return f"direction-control character U+{ord(ch):04X}"
    for ch in rendered:
        if unicodedata.bidirectional(ch) in ("L", "R", "AL"):
            if _is_hebrew_letter(ch):
                return None
            return f"first strong character {ch!r} is not a Hebrew letter"
    return "no strongly directional character"


# What may appear as an image in REPORT.md: an ALLOW-LIST, not a Markdown parser.
#
# An earlier version re-implemented parts of CommonMark (code fences, reference
# definitions, multi-line HTML) to find the images that hide, and every review
# round found one more way around it (a fence closed by a non-breaking space, an
# <img> tag split over two lines, a definition split over two lines). The rule
# now fails CLOSED instead:
#
#   * An image may be written in exactly two forms, ALONE on its line:
#       chart    ![alt](a.svg)    optionally with a link title ("t", 't' or (t))
#       raster   ![alt](a.png)    png, jpg, jpeg, gif or webp
#     The target is a plain path with no spaces: an <angle-bracket> target would
#     be read as an HTML tag, and file names here have no spaces.
#   * Any other "![" is a violation: inside a sentence, a list, a quote or a table;
#     reference style (![alt][label]); split over lines; with an escaped or
#     entity-encoded target; as a data: URI; wrapped in a link.
#   * Raw HTML is an allow-list too: only <details>, <summary> and <br> (for
#     folding and line breaks) and <!-- comments --> are accepted. Any other tag is
#     a violation wherever its opening tag starts, even when its attributes continue
#     on the next line. (A blocklist of picture elements missed <video poster=...>.)
#
# Code fences, inline code spans and link reference definitions are NOT tracked
# at all. Image syntax or an HTML tag written inside one is refused like any other
# (a conservative false positive), so nothing can hide there. An earlier version
# removed inline code spans before scanning; unequal backtick runs fooled it
# (``![x](a.svg)` renders an image next to literal backticks). Write an example of
# markup in words, not in code.
#
# A heading above a chart may not contain "&", a backslash, "[" or "]". Entities and
# escapes change what the reader sees (&#80;3 is displayed as P3, &#8207; is an
# invisible right-to-left mark), and the heading rule reads the source. Brackets
# are links: a link-looking "[](a b) text" is not a link (a space in the target),
# so GitHub shows it literally, while the rule strips it as if it were one.
# Refusing the characters closes every such form at once instead of emulating a
# decoder or a link parser.
#
# Not covered: a picture whose target does not end in .svg (a URL without an
# extension), and CSS or JavaScript outside an HTML tag (any tag but the three
# above is already refused). A "<" followed by a letter is read as a tag, even
# inside backticks, so write a comparison with a space (n < m) or in words.
_CHART_LINE = re.compile(
    r"""^[ \t]*!\[[^\]]*\]\(\s*[^)\s<>]+\.svg"""
    r"""(?:\s+(?:"[^"]*"|'[^']*'|\([^)]*\)))?\s*\)[ \t]*$""",
    re.IGNORECASE,
)
_RASTER_LINE = re.compile(
    r"""^[ \t]*!\[[^\]]*\]\(\s*[^)\s<>]+\.(?:png|jpe?g|gif|webp)"""
    r"""(?:\s+(?:"[^"]*"|'[^']*'|\([^)]*\)))?\s*\)[ \t]*$""",
    re.IGNORECASE,
)
_HTML_TAG = re.compile(r"<(/?)([A-Za-z][A-Za-z0-9-]*)")
_HTML_OTHER = re.compile(r"<(?:!(?!--)|\?)")      # <!DOCTYPE>, <![CDATA[, <?processing?>
ALLOWED_HTML_TAGS = frozenset({"details", "summary", "br"})


def chart_heading_violations(markdown: str) -> list[str]:
    """Violations of the image rules in a rendered REPORT (see above). Every
    chart must have an ATX heading as the nearest non-blank line above it, and
    that heading must satisfy the heading rule; the number of charts must equal
    the number of headings above them. Raster images need no heading."""
    lines = markdown.splitlines()
    violations: list[str] = []
    n_charts = n_headings = 0
    for i, line in enumerate(lines):
        bad_tags = sorted({m.group(2).lower() for m in _HTML_TAG.finditer(line)} - ALLOWED_HTML_TAGS)
        if bad_tags or _HTML_OTHER.search(line):
            violations.append(
                f"line {i + 1}: raw HTML is limited to <details>, <summary> and <br> "
                f"(found {bad_tags or 'a special tag'}); write images as ![alt](file.svg) alone on their line"
            )
            continue
        if "![" not in line:
            continue
        if _RASTER_LINE.match(line):
            continue
        if not _CHART_LINE.match(line):
            violations.append(
                f"line {i + 1}: an image must be written inline, alone on its line, "
                "with a plain .svg/.png/.jpg/.gif/.webp target"
            )
            continue
        n_charts += 1
        j = i - 1
        while j >= 0 and not lines[j].strip():
            j -= 1
        if j < 0 or not is_atx_heading(lines[j]):
            violations.append(f"line {i + 1}: chart has no heading directly above it")
            continue
        n_headings += 1
        if any(ch in lines[j] for ch in ("&", chr(92), "[", "]")):
            violations.append(
                f"line {j + 1}: a chart heading may not contain '&', a backslash, '[' or ']' "
                f"(entities, escapes and links change what is displayed): {lines[j].strip()!r}"
            )
            continue
        reason = heading_rule_violation(rendered_heading_text(lines[j]))
        if reason:
            violations.append(f"line {j + 1}: {reason}: {lines[j].strip()!r}")
    if n_charts != n_headings:
        violations.append(f"{n_charts} charts but {n_headings} headings above them")
    return violations

# ---------------------------------------------------------------------------
# The digit scan -- INFORMATIONAL, never an assertion (PHASE13.md D2).
# ---------------------------------------------------------------------------
def scan_template_digits(template_text: str) -> dict[str, int]:
    """Every digit run left in a template's literal text, with placeholders
    removed first (their names may contain digits). The output is pasted into
    PHASE13.md with a justification per run; nothing here fails on it."""
    literal = re.sub(r"\$(?:\$|\{\w+\}|\w+)", "", template_text)
    counts: dict[str, int] = {}
    for run in re.findall(r"\d+", literal):
        counts[run] = counts.get(run, 0) + 1
    return dict(sorted(counts.items(), key=lambda kv: (int(kv[0]), kv[0])))


# ---------------------------------------------------------------------------
# Calibration chart from stored data -- no training (PHASE13.md D8).
# ---------------------------------------------------------------------------
def write_calibration_svg(task: str, out_path: Path, sources: Sources | None = None) -> None:
    """Renders `task`'s Holdout calibration chart from models/metrics.json with
    scripts.train's own renderer, so it is the same chart family as the P3/P4
    ones (regenerating those from metrics.json reproduces the committed SVGs
    byte for byte). scripts.train is imported lazily: it pulls in
    catboost/lightgbm/xgboost, which nothing else in this module needs."""
    from scripts import train

    curve = (sources or Sources()).value("metrics", (f"{task}_holdout", "calibration_curve"))
    train._svg_calibration_curve(task, curve, Path(out_path))


# ---------------------------------------------------------------------------
def _display(path: Path) -> str:
    """A path for a message: repo-relative when it is inside the repo, else as given."""
    try:
        return str(Path(path).relative_to(REPO))
    except ValueError:
        return str(path)


def main(argv: list[str]) -> int:
    if argv[:1] == ["--calibration-svg"]:
        if len(argv) != 2:
            print("usage: --calibration-svg <P3|P4|P4S>", file=sys.stderr)
            return 2
        out = REPO / "docs" / f"calibration_curve_{argv[1]}.svg"
        write_calibration_svg(argv[1], out)
        print(f"wrote {out}")
        return 0

    template_path = DEFAULT_TEMPLATE
    if not template_path.is_file():
        print(f"template not found: {_display(template_path)} (written in CP4)", file=sys.stderr)
        return 1
    template_text = template_path.read_text(encoding="utf-8")
    text = render_report(template_text)
    problems = chart_heading_violations(text)
    if problems:
        print("chart rule violations:\n  " + "\n  ".join(problems), file=sys.stderr)
        return 1
    DEFAULT_OUT.write_text(text, encoding="utf-8", newline="\n")
    print(f"wrote {DEFAULT_OUT}")
    print("digit sequences remaining in the literal template text (info only, PHASE13.md D2):")
    for run, count in scan_template_digits(template_text).items():
        print(f"  {run}  (x{count})")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
