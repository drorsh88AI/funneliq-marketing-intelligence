"""schema.sql must stay derivable from supabase/migrations/ (PHASE13.md D4, B6).

STATIC check -- it runs no SQL and needs no database (there is no Postgres in
CI). It proves one thing: every statement in schema.sql, INCLUDING the whole
guarded `do $$ ... $$` block, matches what is derived from the migrations,
with exactly two documented differences:

  1. the RLS policy is created in its FINAL form (migration 20260901172942's
     `alter policy` is folded into the `create policy`), and
  2. that migration's bare `revoke execute on function public.rls_auto_enable()`
     is wrapped in an existence check (`do $$ ... if exists ... $$`), because
     the function comes from a Supabase project setting, not from a migration.

The guard block is compared IN FULL against a form built from the migration's
own revoke (schema, function name and argument count are parsed from it), so
changing the catalog filter, the target, or adding a statement inside the block
fails the test.

It does NOT prove the file RUNS or that the catalog query is semantically
right. That is verified by running it on a clean Supabase project
(PHASE13.md CP6). A new migration file, a change to a migration's statements,
or a change to the revoke signature fails this test until schema.sql is
reviewed -- that is the point. A change to a comment or to formatting does not
necessarily fail it: statements are compared after comments and whitespace are
stripped.
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
SCHEMA = REPO / "schema.sql"
MIGRATIONS = REPO / "supabase" / "migrations"

PINNED_MIGRATIONS = [
    "20260901164903_schema.sql",
    "20260901164904_views.sql",
    "20260901172942_fix_advisors.sql",
]


# ---------------------------------------------------------------------------
# A tiny SQL statement splitter -- enough for these files, not a parser.
# ---------------------------------------------------------------------------
def _norm(text: str) -> str:
    return " ".join(text.split())


def _canon(text: str) -> str:
    """_norm, plus no whitespace around ( ) , ; -- so a harmless reformat of
    the guard block (where the parentheses sit) does not fail the comparison
    while a changed condition or statement still does."""
    return re.sub(r"\s*([(),;])\s*", r"\1", _norm(text))


def sql_statements(sql: str) -> list[str]:
    """Statements of `sql`, comments removed, whitespace collapsed. A `;`
    inside a $$ ... $$ dollar-quoted block does not end a statement. No file
    here has `--` inside a string literal, so line comments are stripped by
    cutting at `--`."""
    text = "\n".join(line.split("--", 1)[0] for line in sql.splitlines())
    out: list[str] = []
    buf: list[str] = []
    in_dollar = False
    i = 0
    while i < len(text):
        if text.startswith("$$", i):
            in_dollar = not in_dollar
            buf.append("$$")
            i += 2
            continue
        ch = text[i]
        if ch == ";" and not in_dollar:
            statement = _norm("".join(buf))
            if statement:
                out.append(statement)
            buf = []
        else:
            buf.append(ch)
        i += 1
    tail = _norm("".join(buf))
    if tail:
        out.append(tail)
    return out


def derive_expected(m1: str, m2: str, m3: str) -> tuple[list[str], str]:
    """(statements schema.sql must contain BEFORE its guarded block, the
    revoke statement the guarded block must wrap), derived only from the
    three migrations' text."""
    s1, s2, s3 = sql_statements(m1), sql_statements(m2), sql_statements(m3)

    alters = [s for s in s3 if s.startswith("alter policy ")]
    revokes = [s for s in s3 if s.startswith("revoke execute on function ")]
    assert len(s3) == 2 and len(alters) == 1 and len(revokes) == 1, (
        "the third migration is expected to hold exactly one `alter policy` and "
        "one `revoke execute on function`; review schema.sql and this test"
    )

    policy_at = [i for i, s in enumerate(s1) if s.startswith("create policy ")]
    assert len(policy_at) == 1
    create_head, _, _ = s1[policy_at[0]].partition(" using ")
    alter_head, _, alter_using = alters[0].partition(" using ")
    name_table = re.compile(r"policy (\S+) on (\S+)")
    assert name_table.search(create_head).groups() == name_table.search(alter_head).groups(), (
        "the alter policy targets a different policy or table than the create policy"
    )

    folded = list(s1)
    folded[policy_at[0]] = f"{create_head} using {alter_using}"
    return folded + s2, revokes[0]


def expected_guard(revoke: str) -> str:
    """The whole guarded block, built from the migration's revoke: the
    function's schema, name and input-argument count come from the revoke
    itself, so the existence check cannot drift from what is revoked."""
    parsed = re.fullmatch(r"revoke execute on function (\w+)\.(\w+)\(([^)]*)\) from .+", revoke)
    assert parsed, f"unexpected revoke statement: {revoke!r}"
    schema, name, args = parsed.groups()
    n_args = len([a for a in args.split(",") if a.strip()])
    return (
        "do $$ begin if exists ( select 1 from pg_proc p "
        "join pg_namespace n on n.oid = p.pronamespace "
        f"where n.nspname = '{schema}' and p.proname = '{name}' "
        f"and p.pronargs = {n_args} and p.prokind = 'f' ) "
        f"then {revoke}; end if; end $$"
    )


def check_schema_matches_migrations(schema_text: str, m1: str, m2: str, m3: str) -> None:
    """Raises AssertionError unless `schema_text` is exactly what the three
    migrations derive: the statements before the guard, then the whole guard
    block, and nothing else."""
    expected_before_guard, revoke = derive_expected(m1, m2, m3)
    actual = sql_statements(schema_text)
    assert actual[:-1] == expected_before_guard, "statements before the guard differ from the migrations"
    assert _canon(actual[-1]) == _canon(expected_guard(revoke)), "the guard block differs from the expected form"


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _migration_texts() -> tuple[str, str, str]:
    m1, m2, m3 = (_read(MIGRATIONS / name) for name in PINNED_MIGRATIONS)
    return m1, m2, m3


# ---------------------------------------------------------------------------
# The splitter
# ---------------------------------------------------------------------------
def test_splitter_strips_comments_and_collapses_whitespace():
    assert sql_statements("-- header\ncreate   table t (a int);  -- trailing\n") == [
        "create table t (a int)"
    ]


def test_splitter_keeps_semicolons_inside_dollar_quotes():
    sql = "do $$ begin perform 1; perform 2; end $$; select 1;"
    assert sql_statements(sql) == ["do $$ begin perform 1; perform 2; end $$", "select 1"]


def test_splitter_keeps_a_final_statement_without_a_semicolon():
    assert sql_statements("select 1; select 2") == ["select 1", "select 2"]


def test_canonical_form_ignores_spacing_around_punctuation_only():
    assert _canon("exists (  select 1 ) then") == _canon("exists(select 1)then")
    assert _canon("p.pronargs = 0") != _canon("p.pronargs = 1")


# ---------------------------------------------------------------------------
# schema.sql against the migrations
# ---------------------------------------------------------------------------
def test_the_migration_set_is_exactly_the_one_this_schema_was_derived_from():
    """A new migration must force a review of schema.sql, not slip past it."""
    assert sorted(p.name for p in MIGRATIONS.glob("*.sql")) == PINNED_MIGRATIONS


def test_schema_sql_exists_at_the_repo_root():
    assert SCHEMA.is_file()


def test_schema_sql_matches_the_migrations_including_the_whole_guard_block():
    check_schema_matches_migrations(_read(SCHEMA), *_migration_texts())


def test_the_guard_is_the_last_statement_and_is_the_only_one_naming_the_function():
    statements = sql_statements(_read(SCHEMA))
    assert statements[-1].startswith("do $$") and statements[-1].endswith("$$")
    assert [s for s in statements[:-1] if "rls_auto_enable" in s] == []


def test_the_policy_is_created_in_its_final_initplan_form():
    statements = sql_statements(_read(SCHEMA))
    policy = next(s for s in statements if s.startswith("create policy "))
    assert "using ((select auth.jwt()) -> 'app_metadata' ->> 'organization' = 'northbound')" in policy
    assert not any(s.startswith("alter policy ") for s in statements)


def test_the_header_says_snapshot_and_that_it_runs_no_sql_check():
    header = _read(SCHEMA).split("create table", 1)[0]
    assert "SNAPSHOT" in header and "NOT a concatenation" in header
    assert "does NOT execute" in header


# ---------------------------------------------------------------------------
# The comparison itself must be able to fail -- one mutation per case, applied
# to schema.sql's own text. Each must make check_schema_matches_migrations
# raise; a mutation that did not change the text would not count.
# ---------------------------------------------------------------------------
_GUARD_END = "  end if;\nend\n$$;"

SCHEMA_MUTATIONS = {
    # --- outside the guard
    "policy back to the slow per-row form": lambda s: s.replace("using ((select auth.jwt())", "using (auth.jwt()"),
    "a column loses not null": lambda s: s.replace("ad_budget                 integer not null", "ad_budget                 integer"),
    "service_role loses insert and update": lambda s: s.replace(
        "grant select, insert, update\n  on public.funnel_records\n  to service_role;",
        "grant select\n  on public.funnel_records\n  to service_role;",
    ),
    "an extra statement after the guard": lambda s: s + "\ngrant select on public.funnel_records to anon;\n",
    "bare revoke instead of the guard": lambda s: s[: s.index("do $$")]
    + "revoke execute on function public.rls_auto_enable() from public, anon, authenticated;\n",
    # --- inside the guard
    "guard: pronargs 0 -> 1": lambda s: s.replace("p.pronargs = 0", "p.pronargs = 1"),
    "guard: prokind filter removed": lambda s: s.replace("      and p.prokind = 'f'\n", ""),
    "guard: prokind 'f' -> 'p'": lambda s: s.replace("p.prokind = 'f'", "p.prokind = 'p'"),
    "guard: another function name": lambda s: s.replace("p.proname = 'rls_auto_enable'", "p.proname = 'rls_auto_enabl'"),
    "guard: another schema": lambda s: s.replace("n.nspname = 'public'", "n.nspname = 'private'"),
    "guard: an extra grant inside the block": lambda s: s.replace(
        _GUARD_END, "    grant select on public.funnel_records to anon;\n" + _GUARD_END
    ),
    "guard: revoke no longer covers authenticated": lambda s: s.replace(
        "from public, anon, authenticated;\n  end if;", "from public, anon;\n  end if;"
    ),
    "guard: a second revoke inside the block": lambda s: s.replace(
        _GUARD_END, "    revoke all on public.funnel_records from authenticated;\n" + _GUARD_END
    ),
}


@pytest.mark.parametrize("name", sorted(SCHEMA_MUTATIONS))
def test_a_mutation_of_schema_sql_is_detected(name):
    original = _read(SCHEMA)
    mutated = SCHEMA_MUTATIONS[name](original)
    assert mutated != original, f"mutation {name!r} did not change schema.sql -- fix the test"
    with pytest.raises(AssertionError):
        check_schema_matches_migrations(mutated, *_migration_texts())


def test_harmless_reformatting_of_the_guard_is_not_a_mutation():
    """The canonical comparison tolerates whitespace around punctuation, so
    reformatting the block does not fail the test (a changed condition or
    statement still does)."""
    original = _read(SCHEMA)
    reformatted = original.replace("exists (\n    select 1", "exists(select 1").replace("  ) then", ") then")
    assert reformatted != original
    check_schema_matches_migrations(reformatted, *_migration_texts())


# --- the migrations changing underneath a fixed schema.sql ------------------
def test_drift_in_a_view_definition_is_detected():
    m1, m2, m3 = _migration_texts()
    assert "'Low'" in m2
    with pytest.raises(AssertionError):
        check_schema_matches_migrations(_read(SCHEMA), m1, m2.replace("'Low'", "'Lowest'"), m3)


def test_drift_in_a_grant_is_detected():
    m1, m2, m3 = _migration_texts()
    assert "grant select, insert, update" in m1
    with pytest.raises(AssertionError):
        check_schema_matches_migrations(
            _read(SCHEMA), m1.replace("grant select, insert, update", "grant select, insert"), m2, m3
        )


def test_a_changed_policy_fix_is_detected():
    m1, m2, m3 = _migration_texts()
    assert "'northbound'" in m3
    with pytest.raises(AssertionError):
        check_schema_matches_migrations(_read(SCHEMA), m1, m2, m3.replace("'northbound'", "'someone-else'"))


def test_a_changed_revoke_signature_changes_the_expected_guard():
    """The guard is derived from the migration's revoke, so a revoke with an
    argument expects pronargs = 1 and the existing guard (0) fails."""
    m1, m2, m3 = _migration_texts()
    assert "rls_auto_enable()" in m3
    with pytest.raises(AssertionError):
        check_schema_matches_migrations(_read(SCHEMA), m1, m2, m3.replace("rls_auto_enable()", "rls_auto_enable(text)"))


def test_a_third_migration_with_a_different_shape_fails_loudly():
    m1, m2, _ = _migration_texts()
    with pytest.raises(AssertionError):
        derive_expected(m1, m2, "alter table public.funnel_records add column x integer;")
