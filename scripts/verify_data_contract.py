"""Checkpoint 8: full Data Contract, CSV vs. the live table.

Read-only against Supabase — no writes, no migrations, no index changes.
Compares every one of the 3,500 rows across all 19 source columns (matched
by source_row_id), and recomputes the known snapshot expectations (missing
values, duplicate groups, edge cases) from the pulled data.

⚠ View parity and EXPLAIN are deliberately NOT done here. `service_role`
has no SELECT grant on the two views by design (D4 in PHASE3.md — the
local scripts never consume them), and PostgREST has no way to impersonate
`authenticated` + `organization=northbound` without a real JWT (no Auth
users exist yet, that's phase 4). Both checks require a direct connection
with role-switching, which only a superuser/db-owner session (e.g. the
Supabase MCP `execute_sql`, or `psql`) can do — see docs/planning/PHASE3.md
§ח for the exact queries run and their results.

Usage:
    python scripts/verify_data_contract.py [--csv PATH]

Requires SUPABASE_URL and SUPABASE_SECRET_KEY in .env. Never prints either.
Exit code 0 = every check passed; 1 = at least one check failed (details
printed, nothing is deleted or modified).
"""
from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from scripts.load_data import (  # noqa: E402
    DEFAULT_CSV,
    NOT_NULL_INT_COLUMNS,
    NULLABLE_INT_COLUMNS,
    build_records,
    load_and_verify_csv,
    make_client,
)

ALL_VALUE_COLUMNS = NOT_NULL_INT_COLUMNS + NULLABLE_INT_COLUMNS + ["referred"]


def fetch_all_rows(client, table: str, order_col: str = "source_row_id") -> list[dict]:
    """Page through PostgREST's default 1000-row cap to get every row."""
    rows: list[dict] = []
    page_size = 1000
    offset = 0
    while True:
        resp = (
            client.table(table)
            .select("*")
            .order(order_col)
            .range(offset, offset + page_size - 1)
            .execute()
        )
        batch = resp.data
        rows.extend(batch)
        if len(batch) < page_size:
            break
        offset += page_size
    return rows


def normalize_supabase_row(row: dict) -> dict:
    """Match build_records()'s output shape so the two sides compare equal."""
    out = {"source_row_id": int(row["source_row_id"])}
    for col in NOT_NULL_INT_COLUMNS:
        out[col] = int(row[col])
    for col in NULLABLE_INT_COLUMNS:
        out[col] = None if row[col] is None else int(row[col])
    out["referred"] = str(row["referred"])
    return out


def full_row_match(csv_records: list[dict], db_rows: list[dict]) -> list[str]:
    """Compare every row by source_row_id across all 19 source columns."""
    problems: list[str] = []

    if len(db_rows) != len(csv_records):
        problems.append(
            f"row count mismatch: CSV has {len(csv_records)}, Supabase has {len(db_rows)}"
        )

    db_by_id = {}
    for raw in db_rows:
        norm = normalize_supabase_row(raw)
        sid = norm["source_row_id"]
        if sid in db_by_id:
            problems.append(f"duplicate source_row_id in Supabase: {sid}")
        db_by_id[sid] = norm

    csv_by_id = {r["source_row_id"]: r for r in csv_records}

    missing_in_db = sorted(set(csv_by_id) - set(db_by_id))
    extra_in_db = sorted(set(db_by_id) - set(csv_by_id))
    if missing_in_db:
        problems.append(f"source_row_id in CSV but not Supabase: {missing_in_db[:10]}"
                         f"{' ...' if len(missing_in_db) > 10 else ''}")
    if extra_in_db:
        problems.append(f"source_row_id in Supabase but not CSV: {extra_in_db[:10]}"
                         f"{' ...' if len(extra_in_db) > 10 else ''}")

    mismatch_count = 0
    for sid in sorted(set(csv_by_id) & set(db_by_id)):
        csv_r, db_r = csv_by_id[sid], db_by_id[sid]
        for col in ALL_VALUE_COLUMNS:
            if csv_r[col] != db_r[col]:
                mismatch_count += 1
                if mismatch_count <= 10:
                    problems.append(
                        f"source_row_id={sid} column={col}: "
                        f"csv={csv_r[col]!r} supabase={db_r[col]!r}"
                    )
    if mismatch_count > 10:
        problems.append(f"... and {mismatch_count - 10} more column mismatches")

    return problems


def snapshot_expectations(records: list[dict], label: str) -> dict:
    """The known checks from PHASE0.md, recomputed generically from any
    record list (used for both the CSV side and the Supabase side)."""
    df = pd.DataFrame(records)
    missing_ltv = df["ltv_months"].isna().sum()
    missing_profit = df["cumulative_profit"].isna().sum()
    any_missing = df[["ltv_months", "cumulative_profit"]].isna().any(axis=1).sum()

    dup_cols = [c for c in ALL_VALUE_COLUMNS]  # excludes source_row_id itself
    dup_mask = df.duplicated(subset=dup_cols, keep=False)
    dup_rows = int(dup_mask.sum())
    dup_groups = df[dup_mask].groupby(dup_cols).ngroups if dup_rows else 0

    edge_a = int(((df["closed"] > 0) & (df["purchased"] == 0)).sum())
    edge_b = int(((df["purchased"] == 0) & (df["ltv_months"] > 0)).sum())

    print(f"  [{label}] missing ltv_months={missing_ltv}, missing cumulative_profit={missing_profit}, "
          f"any-missing rows={any_missing}")
    print(f"  [{label}] duplicate rows={dup_rows} in {dup_groups} groups")
    print(f"  [{label}] closed>0 & purchased=0: {edge_a}   |   purchased=0 & ltv_months>0: {edge_b}")

    return {
        "missing_ltv": missing_ltv, "missing_profit": missing_profit,
        "any_missing": any_missing, "dup_rows": dup_rows, "dup_groups": dup_groups,
        "edge_a": edge_a, "edge_b": edge_b,
    }


def main() -> None:
    csv_path = DEFAULT_CSV
    if "--csv" in sys.argv:
        csv_path = Path(sys.argv[sys.argv.index("--csv") + 1])

    print("== Loading and verifying CSV ==")
    csv_df_raw = load_and_verify_csv(csv_path)
    csv_records = build_records(csv_df_raw)
    print(f"  {len(csv_records)} rows loaded from CSV")

    print("== Fetching all rows from Supabase (read-only) ==")
    client = make_client()
    db_rows = fetch_all_rows(client, "funnel_records")
    print(f"  {len(db_rows)} rows fetched from public.funnel_records")

    all_problems: list[str] = []

    print("== Full row-by-row, column-by-column match (source_row_id, 19 columns) ==")
    row_problems = full_row_match(csv_records, db_rows)
    all_problems.extend(row_problems)
    print(f"  {'PASS — every row and column matches exactly' if not row_problems else 'FAIL'}")

    print("== Snapshot expectations (missing / duplicates / edge cases) ==")
    csv_snap = snapshot_expectations(csv_records, "CSV")
    db_snap = snapshot_expectations(
        [normalize_supabase_row(r) for r in db_rows], "Supabase"
    )
    if csv_snap != db_snap:
        all_problems.append(f"snapshot mismatch: CSV={csv_snap} Supabase={db_snap}")
        print("  FAIL — snapshots differ")
    else:
        print("  PASS — CSV and Supabase snapshots identical")

    print("== View parity + EXPLAIN ==")
    print("  Not run here by design — see module docstring and PHASE3.md §ח")

    print()
    if all_problems:
        print(f"RESULT: FAIL ({len(all_problems)} problem(s))")
        for p in all_problems:
            print(f"  - {p}")
        sys.exit(1)
    print("RESULT: PASS — all checkpoint 8 checks passed")


if __name__ == "__main__":
    main()
