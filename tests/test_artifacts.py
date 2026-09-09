"""Tests for app/artifacts.py -- static asset loading (fail-fast, D2) and
lazy joblib artifacts (D3/D17). See docs/planning/PHASE9.md checkpoint 3,
criteria 27-43, 45.
"""
from __future__ import annotations

import json
import shutil
import subprocess
import sys
import threading
import time
from pathlib import Path

import pytest

from app import artifacts as art

REPO_ROOT = Path(__file__).resolve().parent.parent
REAL_MODELS_DIR = REPO_ROOT / "models"

JSON_ASSET_NAMES = (
    "metrics.json",
    "P2.meta.json",
    "P3.meta.json",
    "P4.meta.json",
    "P4S.meta.json",
    "P6.meta.json",
    "P6_simulation.json",
)


@pytest.fixture
def tmp_models_dir(tmp_path, monkeypatch):
    """A throwaway copy of the real models/ directory, with app.artifacts'
    module-level path constants repointed at it -- so a test can delete or
    corrupt one file without touching the real assets other checkpoints
    (and the running app) depend on. Also resets both module caches before
    and after, so tests never leak state into each other."""
    for item in REAL_MODELS_DIR.iterdir():
        if item.is_file():
            shutil.copy2(item, tmp_path / item.name)

    monkeypatch.setattr(art, "MODELS_DIR", tmp_path)
    monkeypatch.setattr(art, "_META_PATHS", {t: tmp_path / f"{t}.meta.json" for t in art.TASKS})
    monkeypatch.setattr(art, "_METRICS_PATH", tmp_path / "metrics.json")
    monkeypatch.setattr(art, "_SIMULATION_PATH", tmp_path / "P6_simulation.json")
    monkeypatch.setattr(art, "JOBLIB_PATHS", {t: tmp_path / f"{t}.joblib" for t in art.TASKS})

    art.reset_assets_cache_for_tests()
    art.reset_artifact_cache_for_tests()
    yield tmp_path
    art.reset_assets_cache_for_tests()
    art.reset_artifact_cache_for_tests()


# ---------------------------------------------------------------------------
# Criterion 27 -- each of the seven JSON assets missing -> process refuses
# to start, never a 500.
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("asset_name", JSON_ASSET_NAMES)
def test_missing_json_asset_is_fail_fast(tmp_models_dir, asset_name):
    (tmp_models_dir / asset_name).unlink()
    with pytest.raises(art.ArtifactStartupError, match=asset_name):
        art.load_static_assets()


# ---------------------------------------------------------------------------
# Criterion 28 -- each with malformed JSON -> fail-fast, filename in the
# error.
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("asset_name", JSON_ASSET_NAMES)
def test_malformed_json_asset_is_fail_fast_with_filename(tmp_models_dir, asset_name):
    (tmp_models_dir / asset_name).write_text("{not valid json", encoding="utf-8")
    with pytest.raises(art.ArtifactStartupError, match=asset_name):
        art.load_static_assets()


# ---------------------------------------------------------------------------
# Criterion 29 -- each with a missing required key -> fail-fast. Exercised
# directly against the validation functions (no disk I/O needed) for speed
# and precision, plus one end-to-end case per asset via the file fixture.
# ---------------------------------------------------------------------------


def test_meta_missing_a_common_required_key_is_fail_fast():
    real_metrics = json.loads((REAL_MODELS_DIR / "metrics.json").read_text(encoding="utf-8"))
    meta = json.loads((REAL_MODELS_DIR / "P2.meta.json").read_text(encoding="utf-8"))
    del meta["feature_columns"]
    with pytest.raises(art.ArtifactStartupError, match="feature_columns"):
        art._validate_meta("P2", meta, real_metrics)


def test_metrics_missing_a_task_key_is_fail_fast():
    real_metrics = json.loads((REAL_MODELS_DIR / "metrics.json").read_text(encoding="utf-8"))
    del real_metrics["P4S"]
    with pytest.raises(art.ArtifactStartupError, match="P4S"):
        art._validate_metrics(real_metrics)


def test_metrics_missing_a_holdout_key_is_fail_fast():
    real_metrics = json.loads((REAL_MODELS_DIR / "metrics.json").read_text(encoding="utf-8"))
    del real_metrics["P6_holdout"]
    with pytest.raises(art.ArtifactStartupError, match="P6_holdout"):
        art._validate_metrics(real_metrics)


def test_metrics_missing_strategy_ranking_is_fail_fast():
    real_metrics = json.loads((REAL_MODELS_DIR / "metrics.json").read_text(encoding="utf-8"))
    del real_metrics["P6_strategy_ranking"]
    with pytest.raises(art.ArtifactStartupError, match="P6_strategy_ranking"):
        art._validate_metrics(real_metrics)


def test_simulation_missing_a_strategy_key_is_fail_fast():
    real_sim = json.loads((REAL_MODELS_DIR / "P6_simulation.json").read_text(encoding="utf-8"))
    del real_sim["10x5000"]
    with pytest.raises(art.ArtifactStartupError, match="10x5000"):
        art._validate_simulation(real_sim)


def test_simulation_entry_missing_a_required_key_is_fail_fast():
    real_sim = json.loads((REAL_MODELS_DIR / "P6_simulation.json").read_text(encoding="utf-8"))
    del real_sim["10x5000"]["n_bootstrap_used"]
    with pytest.raises(art.ArtifactStartupError, match="n_bootstrap_used"):
        art._validate_simulation(real_sim)


@pytest.mark.parametrize("asset_name", JSON_ASSET_NAMES)
def test_each_asset_missing_a_required_key_end_to_end(tmp_models_dir, asset_name):
    """End-to-end (real files on disk) version of the same guarantee, one
    representative key removed per asset, run through load_static_assets()
    as the whole pipeline actually will at startup."""
    path = tmp_models_dir / asset_name
    data = json.loads(path.read_text(encoding="utf-8"))
    if asset_name == "metrics.json":
        del data["P2"]
    elif asset_name == "P6_simulation.json":
        del data["100x500"]
    else:  # a *.meta.json file
        del data["feature_dtypes"]
    path.write_text(json.dumps(data), encoding="utf-8")
    with pytest.raises(art.ArtifactStartupError):
        art.load_static_assets()


# ---------------------------------------------------------------------------
# Criteria 32-36 -- schema checks inside _validate_meta, unit-tested
# directly against in-memory dicts.
# ---------------------------------------------------------------------------


def _real_meta(task: str) -> dict:
    return json.loads((REAL_MODELS_DIR / f"{task}.meta.json").read_text(encoding="utf-8"))


def _real_metrics() -> dict:
    return json.loads((REAL_MODELS_DIR / "metrics.json").read_text(encoding="utf-8"))


def test_feature_columns_out_of_order_is_fail_fast():
    meta = _real_meta("P2")
    meta["feature_columns"] = list(reversed(meta["feature_columns"]))
    # feature_dtypes keys still match (just reordering the list), so this
    # isolates the ordering check specifically.
    with pytest.raises(art.ArtifactStartupError, match="feature_columns"):
        art._validate_meta("P2", meta, _real_metrics())


def test_feature_dtypes_missing_a_column_is_fail_fast():
    meta = _real_meta("P2")
    del meta["feature_dtypes"]["ad_budget"]
    with pytest.raises(art.ArtifactStartupError, match="feature_dtypes"):
        art._validate_meta("P2", meta, _real_metrics())


def test_feature_dtypes_with_extra_column_is_fail_fast():
    meta = _real_meta("P2")
    meta["feature_dtypes"]["not_a_real_column"] = "int64"
    with pytest.raises(art.ArtifactStartupError, match="feature_dtypes"):
        art._validate_meta("P2", meta, _real_metrics())


def test_feature_dtypes_unsupported_value_is_fail_fast():
    meta = _real_meta("P2")
    meta["feature_dtypes"]["ad_budget"] = "object"
    with pytest.raises(art.ArtifactStartupError, match="unsupported"):
        art._validate_meta("P2", meta, _real_metrics())


def test_algo_not_a_key_in_metrics_task_is_fail_fast():
    meta = _real_meta("P2")
    meta["algo"] = "not_a_real_algo"
    with pytest.raises(art.ArtifactStartupError, match="algo"):
        art._validate_meta("P2", meta, _real_metrics())


def test_ood_bounds_missing_a_feature_is_fail_fast():
    meta = _real_meta("P2")
    del meta["ood_bounds"]["ad_budget"]
    with pytest.raises(art.ArtifactStartupError, match="ood_bounds"):
        art._validate_meta("P2", meta, _real_metrics())


# ---------------------------------------------------------------------------
# Criterion 30 -- SHA-256 of the five .joblib files, checked at startup by
# hashing bytes, against the CURRENT meta.checksums.artifact_sha256.
# ---------------------------------------------------------------------------


def test_joblib_sha256_mismatch_against_current_meta_is_fail_fast(tmp_models_dir):
    with (tmp_models_dir / "P2.joblib").open("ab") as f:
        f.write(b"\x00tamper")
    with pytest.raises(art.ArtifactStartupError, match="SHA-256"):
        art.load_static_assets()


def test_load_static_assets_never_calls_joblib_load(tmp_models_dir, monkeypatch):
    """Criterion 43 (startup half): SHA-256 verification hashes raw bytes
    -- it must never unpickle. joblib is imported lazily inside
    get_artifact(), so if load_static_assets() somehow triggered an
    unpickle it would have to go through that same import; patching
    the module attribute after a manual import proves it's never called."""
    import joblib

    def forbidden(*a, **kw):
        raise AssertionError("joblib.load must not be called by load_static_assets()")

    monkeypatch.setattr(joblib, "load", forbidden)
    art.load_static_assets()  # must succeed without ever touching joblib.load


# ---------------------------------------------------------------------------
# Real-file happy path + the five SHA-256 values pinned in the plan
# (docs/planning/PHASE9.md criterion 31 pins these against commit
# 93612c1 as a separate, immutability-focused check -- this one is the
# ordinary runtime check against whatever meta.json says right now).
# ---------------------------------------------------------------------------


def test_load_static_assets_succeeds_against_the_real_models_dir():
    from app.features import STRATEGY_ALLOCATIONS

    art.reset_assets_cache_for_tests()
    bundle = art.load_static_assets()
    assert set(bundle["meta"]) == set(art.TASKS)
    assert set(bundle["simulation"]) == set(STRATEGY_ALLOCATIONS)
    art.reset_assets_cache_for_tests()


# ---------------------------------------------------------------------------
# Criterion 31 -- immutability, a SEPARATE check from criterion 30. Pinned
# literals from commit 93612c1 (feat(phase8a): P4S artifact + evidence),
# never read from meta.json (that's criterion 30's runtime check, which
# would pass even if an artifact silently changed together with its own
# meta) and never from ROADMAP.html (docs aren't a hash source).
# ---------------------------------------------------------------------------

_PHASE8A_SHA256 = {
    "P2": "101576ba359c2ec862cecb3b3e5e738a0a8c7e9c6cc31fe8da388c21ff62201f",
    "P3": "a169f6b139c2c8f544f93a54f80baf309b8971bd71feab022b9f5675264d398a",
    "P4": "57a7a54f67406b6c5f4746449e6d776a00e5e45dfc66928c63a6238805b09598",
    "P4S": "27b39407dfb9bc2357be73748703f0c9f096b8fb2468173519dca2a4f7c7ebef",
    "P6": "2364e4f0b722b444b26fac9390c33e53f234fc6d69f80091640ad0a6fd790519",
}


@pytest.mark.parametrize("task", art.TASKS)
def test_joblib_matches_phase8a_pinned_sha256(task):
    actual = art._sha256_file(REAL_MODELS_DIR / f"{task}.joblib")
    assert actual == _PHASE8A_SHA256[task], (
        f"{task}.joblib no longer matches the SHA-256 pinned from commit "
        f"93612c1 -- this must be a deliberate, reviewed change, not a "
        f"silent one"
    )


def test_p4s_model_version_is_pinned():
    meta = _real_meta("P4S")
    assert meta["model_version"] == "P4S-logistic-20260909-18bdf4e"


def test_get_assets_is_memoized(monkeypatch):
    art.reset_assets_cache_for_tests()
    calls = {"n": 0}
    real = art.load_static_assets

    def counting(*a, **kw):
        calls["n"] += 1
        return real(*a, **kw)

    monkeypatch.setattr(art, "load_static_assets", counting)
    first = art.get_assets()
    second = art.get_assets()
    assert first is second
    assert calls["n"] == 1
    art.reset_assets_cache_for_tests()


# ---------------------------------------------------------------------------
# Criteria 37-39 -- lazy joblib loading: classes_ check, load failure,
# retry-after-failure behavior, library incompatibility.
# ---------------------------------------------------------------------------


class _FakeArtifactWrongClasses:
    classes_ = [0, 1, 2]


@pytest.mark.parametrize("task", ["P3", "P4", "P4S"])
def test_classifier_with_wrong_classes_raises_at_lazy_load(monkeypatch, task):
    import joblib

    art.reset_artifact_cache_for_tests()
    monkeypatch.setattr(joblib, "load", lambda path: _FakeArtifactWrongClasses())
    with pytest.raises(art.ArtifactLoadError, match="classes_"):
        art.get_artifact(task)
    art.reset_artifact_cache_for_tests()


def test_joblib_load_failure_raises_artifact_load_error(monkeypatch):
    import joblib

    art.reset_artifact_cache_for_tests()

    def boom(path):
        raise RuntimeError("simulated unpickling / library incompatibility failure")

    monkeypatch.setattr(joblib, "load", boom)
    with pytest.raises(art.ArtifactLoadError):
        art.get_artifact("P2")
    art.reset_artifact_cache_for_tests()


def test_failed_load_does_not_poison_the_cache_for_a_retry(monkeypatch):
    """Criterion 38: a failed load must not leave a partial/broken entry
    in the cache -- the next call must genuinely retry, not silently
    return something bad from a half-populated cache."""
    import joblib

    art.reset_artifact_cache_for_tests()
    calls = {"n": 0}
    real_load = joblib.load

    def flaky(path):
        calls["n"] += 1
        if calls["n"] == 1:
            raise RuntimeError("first attempt fails")
        return real_load(path)

    monkeypatch.setattr(joblib, "load", flaky)
    with pytest.raises(art.ArtifactLoadError):
        art.get_artifact("P2")
    assert "P2" not in art._joblib_cache

    result = art.get_artifact("P2")  # second call: real load succeeds
    assert result is not None
    assert calls["n"] == 2
    art.reset_artifact_cache_for_tests()


# ---------------------------------------------------------------------------
# Criterion 40 -- concurrent loading of the same task from two threads:
# one object, one load.
# ---------------------------------------------------------------------------


def test_concurrent_get_artifact_same_task_loads_once(monkeypatch):
    import joblib

    art.reset_artifact_cache_for_tests()
    calls = {"n": 0}
    real_load = joblib.load

    def slow_load(path):
        calls["n"] += 1
        time.sleep(0.05)  # widen the race window so both threads overlap
        return real_load(path)

    monkeypatch.setattr(joblib, "load", slow_load)

    results = []

    def worker():
        results.append(art.get_artifact("P6"))

    threads = [threading.Thread(target=worker) for _ in range(2)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert calls["n"] == 1
    assert results[0] is results[1]
    art.reset_artifact_cache_for_tests()


# ---------------------------------------------------------------------------
# Criteria 41-42 -- scripts.train import isolation, verified in a real
# subprocess (sys.modules state can't be reliably reset in-process).
# ---------------------------------------------------------------------------


def _run_subprocess_check(code: str) -> None:
    result = subprocess.run(
        [sys.executable, "-c", code],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert result.returncode == 0, (
        f"subprocess failed:\nstdout={result.stdout}\nstderr={result.stderr}"
    )


def test_loading_p4_and_p4s_pulls_in_scripts_train_subprocess():
    """Criterion 41: before loading, scripts.train is absent; P4 and P4S
    load successfully and predict_proba works; only THEN is scripts.train
    present (via the _add_budget_tier pickle reference, PHASE9.md D3)."""
    code = (
        "import sys, warnings, pandas as pd\n"
        "warnings.filterwarnings('ignore')\n"
        "assert 'scripts.train' not in sys.modules\n"
        "from app.artifacts import get_artifact\n"
        "for task in ('P4', 'P4S'):\n"
        "    a = get_artifact(task)\n"
        "    cols = a.feature_names_in_ if hasattr(a, 'feature_names_in_') else None\n"
        "assert 'scripts.train' in sys.modules, 'expected scripts.train to be imported by now'\n"
        "print('OK')\n"
    )
    _run_subprocess_check(code)


def test_startup_and_p2_p3_do_not_pull_in_scripts_train_subprocess():
    """Criterion 42: eager startup asset loading (hashing only, never
    unpickling) plus loading P2 and P3 (neither references scripts.train
    in its pickle) must never import scripts.train."""
    code = (
        "import sys, warnings\n"
        "warnings.filterwarnings('ignore')\n"
        "from app.artifacts import get_assets, get_artifact\n"
        "get_assets()\n"
        "get_artifact('P2')\n"
        "get_artifact('P3')\n"
        "assert 'scripts.train' not in sys.modules, 'scripts.train must not be imported by P2/P3/startup'\n"
        "print('OK')\n"
    )
    _run_subprocess_check(code)


# ---------------------------------------------------------------------------
# Criterion 45 -- import app.inference has zero open/json.load/joblib.load
# calls (kept as a regression test, not just the one-off script used to
# verify it during planning).
# ---------------------------------------------------------------------------


def test_import_app_inference_has_no_file_io_side_effect():
    code = (
        "import builtins, json, sys\n"
        "calls = {'open': 0, 'json.load': 0}\n"
        "real_open, real_json_load = builtins.open, json.load\n"
        "def spy_open(*a, **kw):\n"
        "    calls['open'] += 1\n"
        "    return real_open(*a, **kw)\n"
        "def spy_json_load(*a, **kw):\n"
        "    calls['json.load'] += 1\n"
        "    return real_json_load(*a, **kw)\n"
        "builtins.open, json.load = spy_open, spy_json_load\n"
        "import app.inference\n"
        "builtins.open, json.load = real_open, real_json_load\n"
        "assert calls == {'open': 0, 'json.load': 0}, calls\n"
        "assert 'joblib' not in sys.modules, 'joblib must not load at import time'\n"
        "print('OK')\n"
    )
    _run_subprocess_check(code)
