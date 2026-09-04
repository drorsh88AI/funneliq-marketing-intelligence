"""Tests for scripts/data_contract.py.

Layer A (schema) only, for now -- checkpoints 2 fixed four violations that
check_schema() silently let through (found by Codex review); these are the
regression tests proving the fix. Layer B (invariants) and layer C (snapshot
expectations), and the full valid+invalid fixture matrix across all three
layers, are checkpoint 4's scope -- not added here.

Nothing here touches the real funnel_marketing_data.csv or Supabase -- a
tiny two-row fixture CSV, loaded the same way load_data.py loads the real
one, so dtypes match real parsing behaviour (not hand-set via astype()).
Runs in CI with no CSV present, per PHASE5.md D4.
"""
from __future__ import annotations

import hashlib
from pathlib import Path

import pandas as pd
import pytest

from scripts import data_contract as dc
from scripts import load_data as ld

VALID_CSV_TEXT = (
    ",".join(ld.EXPECTED_COLUMNS) + "\n"
    "2500,36,24,12,19,14,11,10,7,5,2,2,4,1250,38.0,1,0,20777.0,No\n"
    "15000,98,55,43,43,32,26,25,18,14,4,5,3,3750,,1,0,,Yes\n"
)


def _load_fixture(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> pd.DataFrame:
    """Write the fixture CSV and load it through load_data, so dtypes match
    real end-to-end parsing (source_row_id included, columns in order)."""
    p = tmp_path / "sample.csv"
    p.write_text(VALID_CSV_TEXT)
    monkeypatch.setattr(ld, "EXPECTED_SHA256", hashlib.sha256(p.read_bytes()).hexdigest())
    return ld.load_and_verify_csv(p)


def test_check_schema_passes_on_a_valid_fixture(tmp_path, monkeypatch):
    df = _load_fixture(tmp_path, monkeypatch)
    assert dc.check_schema(df) == []


def test_check_schema_passes_without_source_row_id(tmp_path, monkeypatch):
    """The only tolerated extra column is source_row_id -- and it's also
    optional: a raw 19-column frame (no derived column at all) is valid."""
    df = _load_fixture(tmp_path, monkeypatch)
    raw = df.drop(columns=["source_row_id"])
    assert dc.check_schema(raw) == []


def test_check_schema_flags_extra_foreign_column(tmp_path, monkeypatch):
    df = _load_fixture(tmp_path, monkeypatch)
    df["bogus_extra"] = 1
    violations = dc.check_schema(df)
    assert any("bogus_extra" in v for v in violations)


def test_check_schema_flags_null_in_not_null_column_even_as_Int64(tmp_path, monkeypatch):
    """dtype alone doesn't prove null-freedom -- pandas' nullable Int64 is
    still an integer dtype while holding an actual null."""
    df = _load_fixture(tmp_path, monkeypatch)
    df["ad_budget"] = df["ad_budget"].astype("Int64")
    df.loc[0, "ad_budget"] = pd.NA
    violations = dc.check_schema(df)
    assert any("ad_budget" in v and "null" in v for v in violations)


def test_check_schema_flags_fractional_value_in_nullable_int_column(tmp_path, monkeypatch):
    """float64 on a nullable-integer column is only legitimate because NaN
    forces it -- a genuine fraction is still a violation."""
    df = _load_fixture(tmp_path, monkeypatch)
    df.loc[0, "cumulative_profit"] = 3.5
    violations = dc.check_schema(df)
    assert any("cumulative_profit" in v and "fractional" in v for v in violations)


def test_check_schema_flags_null_in_referred(tmp_path, monkeypatch):
    df = _load_fixture(tmp_path, monkeypatch)
    df.loc[0, "referred"] = None
    violations = dc.check_schema(df)
    assert any("referred" in v and "null" in v for v in violations)
