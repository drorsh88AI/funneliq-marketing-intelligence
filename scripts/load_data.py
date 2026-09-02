"""Load funnel_marketing_data.csv into Supabase public.funnel_records.

Idempotent: upserts on source_row_id (unique, 1-based), safe to re-run.
See docs/planning/PHASE3.md §ד (D7) for the full contract this implements.

Usage:
    python scripts/load_data.py [--csv PATH]

Requires SUPABASE_URL and SUPABASE_SECRET_KEY in .env (see .env.example).
Never prints either value.
"""
from __future__ import annotations

import argparse
import hashlib
import os
import sys
from pathlib import Path

import pandas as pd
from dotenv import load_dotenv

# Locks the file identity this script was verified against — see PHASE0.md.
EXPECTED_SHA256 = "8ac67d50a6f96a8ece8abd770a5a1901b34036a5c98656455eb04cee07d707aa"

# Raw CSV contract, in header order — not app/features.py's modeling lists.
EXPECTED_COLUMNS = [
    "ad_budget", "num_leads", "leads_answered", "leads_not_answered",
    "followup_1", "followup_2", "followup_3", "followup_4", "followup_5",
    "not_closed", "closed", "calls_to_closed", "calls_to_not_closed",
    "customer_acquisition_cost", "ltv_months", "purchased", "upsell",
    "cumulative_profit", "referred",
]

# Every integer column except the two nullable ones (checked separately).
NOT_NULL_INT_COLUMNS = [
    "ad_budget", "num_leads", "leads_answered", "leads_not_answered",
    "followup_1", "followup_2", "followup_3", "followup_4", "followup_5",
    "not_closed", "closed", "calls_to_closed", "calls_to_not_closed",
    "customer_acquisition_cost", "purchased", "upsell",
]
NULLABLE_INT_COLUMNS = ["ltv_months", "cumulative_profit"]

BATCH_SIZE = 500
DEFAULT_CSV = Path(__file__).resolve().parent.parent / "funnel_marketing_data.csv"


def sha256_of(path: Path) -> str:
    """Stream the file in chunks — never loads the whole CSV into memory twice."""
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def load_and_verify_csv(csv_path: Path) -> pd.DataFrame:
    """Read the CSV, verify its checksum and header, add source_row_id.

    Exits noisily — never a bare traceback — on any contract violation:
      2 -- file missing
      3 -- checksum mismatch
      4 -- header mismatch
    """
    if not csv_path.exists():
        print(f"ERROR: CSV not found at {csv_path}", file=sys.stderr)
        sys.exit(2)

    actual = sha256_of(csv_path)
    if actual != EXPECTED_SHA256:
        print(
            f"ERROR: checksum mismatch for {csv_path}\n"
            f"  expected {EXPECTED_SHA256}\n"
            f"  actual   {actual}",
            file=sys.stderr,
        )
        sys.exit(3)

    df = pd.read_csv(csv_path)
    if list(df.columns) != EXPECTED_COLUMNS:
        print(
            f"ERROR: header mismatch for {csv_path}\n"
            f"  expected {EXPECTED_COLUMNS}\n"
            f"  actual   {list(df.columns)}",
            file=sys.stderr,
        )
        sys.exit(4)

    # 1-based: the first data row (after the header) is source_row_id = 1.
    df.insert(0, "source_row_id", range(1, len(df) + 1))
    return df


def build_records(df: pd.DataFrame) -> list[dict]:
    """Convert the DataFrame to upsert-ready dicts.

    NaN -> None (Postgres NULL) for the two nullable columns only. pandas
    reads every all-integer column as float64 the moment ANY row has a NaN
    anywhere in the file, so every numeric column is explicitly re-cast to
    int here rather than trusted from df.dtypes.
    """
    records: list[dict] = []
    for row in df.itertuples(index=False):
        d = row._asdict()
        record: dict = {"source_row_id": int(d["source_row_id"])}
        for col in NOT_NULL_INT_COLUMNS:
            record[col] = int(d[col])
        for col in NULLABLE_INT_COLUMNS:
            record[col] = None if pd.isna(d[col]) else int(d[col])
        record["referred"] = str(d["referred"])
        records.append(record)
    return records


def upsert_batches(client, records: list[dict], batch_size: int = BATCH_SIZE) -> int:
    """Upsert records in batches, keyed on source_row_id. Returns rows sent."""
    sent = 0
    for i in range(0, len(records), batch_size):
        batch = records[i : i + batch_size]
        client.table("funnel_records").upsert(batch, on_conflict="source_row_id").execute()
        sent += len(batch)
        print(f"  upserted {sent}/{len(records)}")
    return sent


def make_client():
    """Build the Supabase client from .env. Never prints SUPABASE_SECRET_KEY."""
    load_dotenv()
    url = os.environ.get("SUPABASE_URL")
    secret_key = os.environ.get("SUPABASE_SECRET_KEY")
    if not url or not secret_key:
        print(
            "ERROR: SUPABASE_URL and SUPABASE_SECRET_KEY must be set in .env "
            "(see .env.example)",
            file=sys.stderr,
        )
        sys.exit(5)
    from supabase import create_client

    return create_client(url, secret_key)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--csv", type=Path, default=DEFAULT_CSV, help="Path to the source CSV"
    )
    args = parser.parse_args()

    df = load_and_verify_csv(args.csv)
    records = build_records(df)
    print(f"Loaded and verified {len(records)} rows from {args.csv}")

    client = make_client()
    sent = upsert_batches(client, records)
    print(f"Done: {sent} rows upserted.")


if __name__ == "__main__":
    main()
