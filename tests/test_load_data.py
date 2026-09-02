"""Local-only tests for scripts/load_data.py.

Nothing here touches Supabase, SUPABASE_SECRET_KEY, or the network — every
Supabase interaction is a hand-rolled fake object. See docs/planning/PHASE3.md
§ד (D7) for what the script itself is supposed to do.
"""
from __future__ import annotations

import hashlib
import subprocess
import sys
from pathlib import Path

import pytest

from scripts import load_data as ld

REPO_ROOT = Path(__file__).resolve().parent.parent

VALID_CSV_TEXT = (
    ",".join(ld.EXPECTED_COLUMNS) + "\n"
    "2500,36,24,12,19,14,11,10,7,5,2,2,4,1250,38.0,1,0,20777.0,No\n"
    "15000,98,55,43,43,32,26,25,18,14,4,5,3,3750,,1,0,,Yes\n"
)


def _write_valid_csv(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Write the fixture CSV and point EXPECTED_SHA256 at its real hash."""
    p = tmp_path / "sample.csv"
    p.write_text(VALID_CSV_TEXT)
    monkeypatch.setattr(ld, "EXPECTED_SHA256", hashlib.sha256(p.read_bytes()).hexdigest())
    return p


def test_script_compiles():
    """Syntax/import check, run out-of-process so a failure can't crash the suite."""
    result = subprocess.run(
        [sys.executable, "-m", "py_compile", "scripts/load_data.py"],
        cwd=REPO_ROOT,
        capture_output=True,
    )
    assert result.returncode == 0, result.stderr.decode()


def test_sha256_of_matches_hashlib(tmp_path):
    p = tmp_path / "sample.csv"
    p.write_text(VALID_CSV_TEXT)
    expected = hashlib.sha256(p.read_bytes()).hexdigest()
    assert ld.sha256_of(p) == expected


def test_load_and_verify_csv_missing_file_exits_2(tmp_path):
    with pytest.raises(SystemExit) as exc:
        ld.load_and_verify_csv(tmp_path / "does_not_exist.csv")
    assert exc.value.code == 2


def test_load_and_verify_csv_checksum_mismatch_exits_3(tmp_path, monkeypatch):
    p = tmp_path / "sample.csv"
    p.write_text(VALID_CSV_TEXT)
    monkeypatch.setattr(ld, "EXPECTED_SHA256", "0" * 64)  # deliberately wrong
    with pytest.raises(SystemExit) as exc:
        ld.load_and_verify_csv(p)
    assert exc.value.code == 3


def test_load_and_verify_csv_header_mismatch_exits_4(tmp_path, monkeypatch):
    bad_header = ",".join(ld.EXPECTED_COLUMNS[:-1] + ["extra_column"])
    text = bad_header + "\n" + "1,2,3,4,5,6,7,8,9,10,11,12,13,14,15,16,17,18,19\n"
    p = tmp_path / "sample.csv"
    p.write_text(text)
    monkeypatch.setattr(ld, "EXPECTED_SHA256", hashlib.sha256(p.read_bytes()).hexdigest())
    with pytest.raises(SystemExit) as exc:
        ld.load_and_verify_csv(p)
    assert exc.value.code == 4


def test_load_and_verify_csv_adds_1_based_source_row_id(tmp_path, monkeypatch):
    p = _write_valid_csv(tmp_path, monkeypatch)
    df = ld.load_and_verify_csv(p)
    assert list(df["source_row_id"]) == [1, 2]
    assert df.columns[0] == "source_row_id"


def test_build_records_types_and_nulls(tmp_path, monkeypatch):
    p = _write_valid_csv(tmp_path, monkeypatch)
    df = ld.load_and_verify_csv(p)
    records = ld.build_records(df)

    assert len(records) == 2
    r1, r2 = records

    # row 1: fully populated
    assert r1["source_row_id"] == 1
    assert r1["ltv_months"] == 38
    assert type(r1["ltv_months"]) is int
    assert r1["cumulative_profit"] == 20777
    assert r1["referred"] == "No"

    # row 2: NaN in the CSV -> None (Postgres NULL), not NaN and not 0
    assert r2["source_row_id"] == 2
    assert r2["ltv_months"] is None
    assert r2["cumulative_profit"] is None

    # every not-null column is a plain int -- pandas reads the whole column
    # as float64 the moment any row anywhere has a NaN, so this checks the
    # per-value re-cast actually happened rather than trusting df.dtypes
    for col in ld.NOT_NULL_INT_COLUMNS:
        assert type(r1[col]) is int, f"{col} was {type(r1[col])}"


def test_upsert_batches_uses_mock_only_and_batches_correctly():
    """No network, no Supabase key -- a fake client just records its calls."""
    calls: list[tuple[list[dict], str]] = []

    class FakeTable:
        def upsert(self, batch, on_conflict):
            calls.append((list(batch), on_conflict))
            return self

        def execute(self):
            return self

    class FakeClient:
        def table(self, name):
            assert name == "funnel_records"
            return FakeTable()

    records = [{"source_row_id": i} for i in range(1, 6)]  # 5 records
    sent = ld.upsert_batches(FakeClient(), records, batch_size=2)

    assert sent == 5
    assert [len(batch) for batch, _ in calls] == [2, 2, 1]
    assert all(on_conflict == "source_row_id" for _, on_conflict in calls)
    flat = [rec for batch, _ in calls for rec in batch]
    assert flat == records  # every record in exactly one batch, in order


def test_make_client_exits_5_without_credentials(monkeypatch):
    monkeypatch.delenv("SUPABASE_URL", raising=False)
    monkeypatch.delenv("SUPABASE_SECRET_KEY", raising=False)
    monkeypatch.setattr(ld, "load_dotenv", lambda: None)  # never read the real .env
    with pytest.raises(SystemExit) as exc:
        ld.make_client()
    assert exc.value.code == 5
