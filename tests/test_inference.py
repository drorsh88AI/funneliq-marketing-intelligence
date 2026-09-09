"""Tests for app/inference.py's DataFrame-building and OOD-gating helpers
(PHASE9.md D9/D17, checkpoint 3, criteria 44 and 74).
"""
from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import pytest

from app import inference as inf

REPO_ROOT = Path(__file__).resolve().parent.parent
REAL_MODELS_DIR = REPO_ROOT / "models"


def _real_meta(task: str) -> dict:
    return json.loads((REAL_MODELS_DIR / f"{task}.meta.json").read_text(encoding="utf-8"))


# A fixture in-domain for P2's ood_bounds -- ad_budget=2000 is an observed
# level, every other field sits well inside its [min, max] (see PHASE9.md
# mצב מאומת 16/46).
_P2_IN_DOMAIN_VALUES = {
    "ad_budget": 2000, "num_leads": 50, "leads_answered": 40,
    "followup_1": 30, "followup_2": 25, "followup_3": 20, "followup_4": 15,
    "followup_5": 10, "not_closed": 6, "closed": 4, "calls_to_closed": 3,
    "calls_to_not_closed": 2, "customer_acquisition_cost": 500,
}


# ---------------------------------------------------------------------------
# Criterion 74 -- build_input_frame(): exact columns, exact order, dtypes
# from feature_dtypes. Casting failure raises ValueError.
# ---------------------------------------------------------------------------


def test_build_input_frame_has_exact_columns_order_and_dtypes():
    meta = _real_meta("P2")
    frame = inf.build_input_frame(meta, _P2_IN_DOMAIN_VALUES)
    assert list(frame.columns) == meta["feature_columns"]
    for col in meta["feature_columns"]:
        assert str(frame[col].dtype) == meta["feature_dtypes"][col]
    assert len(frame) == 1


def test_build_input_frame_p4s_uses_its_own_four_columns():
    meta = _real_meta("P4S")
    values = {"ad_budget": 2000, "num_leads": 50, "leads_answered": 40, "followup_1": 30}
    frame = inf.build_input_frame(meta, values)
    assert list(frame.columns) == ["ad_budget", "num_leads", "leads_answered", "followup_1"]
    assert list(frame.columns) == meta["feature_columns"]


def test_build_input_frame_casting_failure_raises_value_error():
    meta = _real_meta("P2")
    bad_meta = dict(meta, feature_dtypes=dict(meta["feature_dtypes"]))
    bad_meta["feature_dtypes"]["ad_budget"] = "not_a_real_dtype"
    with pytest.raises(ValueError, match="ad_budget"):
        inf.build_input_frame(bad_meta, _P2_IN_DOMAIN_VALUES)


def test_build_input_frame_column_order_survives_shuffled_input_dict():
    """The frame's column order comes from meta["feature_columns"], not
    from dict insertion order of `values` -- shuffling the input dict
    must not change the frame's column order."""
    meta = _real_meta("P2")
    shuffled = dict(reversed(list(_P2_IN_DOMAIN_VALUES.items())))
    frame = inf.build_input_frame(meta, shuffled)
    assert list(frame.columns) == meta["feature_columns"]


# ---------------------------------------------------------------------------
# Criterion 74 -- the DataFrame that ACTUALLY reaches predict()/
# predict_proba(), captured with a spy, not just the frame build_input_frame
# happens to construct in isolation.
# ---------------------------------------------------------------------------


class _SpyArtifact:
    def __init__(self):
        self.predict_calls: list[pd.DataFrame] = []
        self.predict_proba_calls: list[pd.DataFrame] = []

    def predict(self, frame):
        self.predict_calls.append(frame)
        return [42.0]

    def predict_proba(self, frame):
        self.predict_proba_calls.append(frame)
        return [[0.3, 0.7]]


def test_predict_if_in_domain_passes_the_exact_frame_to_predict(monkeypatch):
    meta = _real_meta("P2")
    spy = _SpyArtifact()
    monkeypatch.setattr(inf, "get_artifact", lambda task: spy)

    out_of_range, result = inf.predict_if_in_domain("P2", meta, _P2_IN_DOMAIN_VALUES, method="predict")

    assert out_of_range == []
    assert result == [42.0]
    assert len(spy.predict_calls) == 1
    frame = spy.predict_calls[0]
    assert list(frame.columns) == meta["feature_columns"]
    for col in meta["feature_columns"]:
        assert str(frame[col].dtype) == meta["feature_dtypes"][col]


def test_predict_if_in_domain_uses_predict_proba_when_asked(monkeypatch):
    meta = _real_meta("P3")
    spy = _SpyArtifact()
    monkeypatch.setattr(inf, "get_artifact", lambda task: spy)

    values = dict(_P2_IN_DOMAIN_VALUES)  # P3 shares the same 13 input features
    out_of_range, result = inf.predict_if_in_domain("P3", meta, values, method="predict_proba")

    assert out_of_range == []
    assert result == [[0.3, 0.7]]
    assert len(spy.predict_proba_calls) == 1
    assert spy.predict_calls == []


# ---------------------------------------------------------------------------
# Criterion 44 -- OOD input short-circuits BEFORE get_artifact is called
# at all, measured (not assumed).
# ---------------------------------------------------------------------------


def test_out_of_range_features_detects_a_single_violation():
    meta = _real_meta("P2")
    values = dict(_P2_IN_DOMAIN_VALUES, ad_budget=25000)  # above P2's 500-20000 bound
    assert inf.out_of_range_features(meta, values) == ["ad_budget"]


def test_out_of_range_features_empty_for_in_domain_input():
    meta = _real_meta("P2")
    assert inf.out_of_range_features(meta, _P2_IN_DOMAIN_VALUES) == []


def test_out_of_range_features_detects_multiple_violations_in_column_order():
    meta = _real_meta("P2")
    values = dict(_P2_IN_DOMAIN_VALUES, ad_budget=25000, closed=999)
    result = inf.out_of_range_features(meta, values)
    assert result == [c for c in meta["feature_columns"] if c in ("ad_budget", "closed")]


def test_predict_if_in_domain_never_calls_get_artifact_when_out_of_range(monkeypatch):
    meta = _real_meta("P2")
    calls = []
    monkeypatch.setattr(inf, "get_artifact", lambda task: calls.append(task) or _SpyArtifact())

    values = dict(_P2_IN_DOMAIN_VALUES, ad_budget=25000)
    out_of_range, result = inf.predict_if_in_domain("P2", meta, values)

    assert out_of_range == ["ad_budget"]
    assert result is None
    assert calls == [], "get_artifact must not be called for an out-of-range input"


def test_boundary_values_are_in_domain_not_ood():
    """min and max themselves are in-domain (inclusive bounds) -- only
    strictly outside [min, max] counts as OOD."""
    meta = _real_meta("P2")
    bounds = meta["ood_bounds"]["ad_budget"]
    values = dict(_P2_IN_DOMAIN_VALUES, ad_budget=int(bounds["min"]))
    assert "ad_budget" not in inf.out_of_range_features(meta, values)
    values = dict(_P2_IN_DOMAIN_VALUES, ad_budget=int(bounds["max"]))
    assert "ad_budget" not in inf.out_of_range_features(meta, values)
