"""Phase 9 -- static asset loading and lazy joblib artifacts.

See docs/planning/PHASE9.md D2/D3/D17. Two loading tiers, deliberately
different in when they run and how they fail:

  * The seven static JSON assets (metrics.json, the five *.meta.json,
    P6_simulation.json) -- read, parsed, and schema-checked once, via
    get_assets() below. Schema/parse/existence failure is FAIL-FAST: it
    raises ArtifactStartupError, which app/main.py's lifespan lets
    propagate so the process refuses to start (D2 -- never a per-request
    500 for a broken static asset).

  * The five .joblib model artifacts -- never unpickled here. Each is
    loaded lazily, once, on the first request that actually needs it
    (get_artifact()), guarded by a per-task lock so two concurrent
    requests for the same task share one load instead of racing. A
    pickling/library-incompatibility failure here IS a 500 (D2/D3) --
    the process already started successfully; this is a per-request
    failure, not a startup one. get_assets() DOES read each .joblib
    file's raw bytes to verify its SHA-256 against the matching meta's
    checksums.artifact_sha256 (D17) -- hashing, never joblib.load.

get_assets() is safe to call from anywhere (route dependencies included):
it is idempotent and lazily self-populates on first call, so nothing
breaks if the caller didn't go through app/main.py's lifespan first (e.g.
a bare TestClient(app) with no `with` block, per this project's existing
test convention in tests/test_auth.py). lifespan's only job is to force
that first call to happen BEFORE the app starts accepting requests, so a
broken asset kills the deploy instead of degrading to per-request 500s.
"""
from __future__ import annotations

import hashlib
import json
import threading
from pathlib import Path
from typing import Any

from app.features import MODEL_INPUT_FEATURES, STRATEGY_ALLOCATIONS

MODELS_DIR = Path(__file__).resolve().parent.parent / "models"

TASKS = ("P2", "P3", "P4", "P4S", "P6")
CLASSIFIER_TASKS = ("P3", "P4", "P4S")  # classes_ == [0, 1] is checked for these

_META_PATHS = {task: MODELS_DIR / f"{task}.meta.json" for task in TASKS}
_METRICS_PATH = MODELS_DIR / "metrics.json"
_SIMULATION_PATH = MODELS_DIR / "P6_simulation.json"
JOBLIB_PATHS = {task: MODELS_DIR / f"{task}.joblib" for task in TASKS}

_COMMON_META_KEYS = {
    "task", "algo", "target", "snapshot", "feature_columns", "feature_dtypes",
    "population_n", "seed", "cv_folds", "ood_bounds",
    "observed_ad_budget_values", "fit_sources", "artifact_role",
    "training_date", "model_version", "checksums",
}
_SUPPORTED_DTYPES = {"int64"}

# D17: beyond _COMMON_META_KEYS, app/predict.py reads several task-specific
# meta fields directly (meta["alpha"], meta["base_rate"], ...) that were
# NOT in the common set and had no startup check at all -- a missing one
# would only surface as a bare KeyError on the first real request, not
# fail-fast at boot. P2 (conformal regression) and the three classifier
# tasks each need their own extra required keys.
_P2_ONLY_META_KEYS = {"alpha", "conformal_quantile", "interval_method"}
_CLASSIFIER_META_KEYS = {"base_rate", "calibration_status", "calibration_method"}


class ArtifactStartupError(RuntimeError):
    """A static asset (JSON) is missing, malformed, or fails schema
    validation -- fail-fast (D2). Never caught and mapped to a 500;
    letting it propagate is the point."""


class ArtifactLoadError(RuntimeError):
    """A .joblib artifact failed to unpickle, or unpickled into something
    that fails its own runtime contract (e.g. classes_ != [0, 1]).
    Route handlers catch this and map it to 500 ErrorDetail (D2/D3) --
    unlike ArtifactStartupError, this happens per-request, after the
    process already started successfully."""


def _read_json(path: Path) -> Any:
    if not path.exists():
        raise ArtifactStartupError(f"missing required asset: {path}")
    try:
        with path.open("r", encoding="utf-8") as f:
            return json.load(f)
    except json.JSONDecodeError as e:
        raise ArtifactStartupError(f"malformed JSON in {path}: {e}") from e


def _sha256_file(path: Path) -> str:
    if not path.exists():
        raise ArtifactStartupError(f"missing required asset: {path}")
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _validate_meta(task: str, meta: Any, metrics: dict) -> None:
    path = _META_PATHS[task]
    if not isinstance(meta, dict):
        raise ArtifactStartupError(f"{path}: top-level JSON must be an object")

    extra_required = _P2_ONLY_META_KEYS if task == "P2" else (
        _CLASSIFIER_META_KEYS if task in CLASSIFIER_TASKS else set()
    )
    missing = (_COMMON_META_KEYS | extra_required) - meta.keys()
    if missing:
        raise ArtifactStartupError(f"{path}: missing required key(s): {sorted(missing)}")

    checksums = meta["checksums"]
    if not isinstance(checksums, dict) or "artifact_sha256" not in checksums:
        raise ArtifactStartupError(f"{path}: checksums.artifact_sha256 missing")

    model_version = meta["model_version"]
    if not isinstance(model_version, str) or not model_version:
        raise ArtifactStartupError(f"{path}: model_version must be a non-empty string")

    observed_values = meta["observed_ad_budget_values"]
    if not isinstance(observed_values, list) or not all(
        isinstance(v, (int, float)) and not isinstance(v, bool) for v in observed_values
    ):
        raise ArtifactStartupError(f"{path}: observed_ad_budget_values must be a list of numbers")

    if task == "P2":
        alpha = meta["alpha"]
        if not isinstance(alpha, (int, float)) or isinstance(alpha, bool) or not (0 < alpha < 1):
            raise ArtifactStartupError(f"{path}: alpha must be a number in (0, 1)")
        quantile = meta["conformal_quantile"]
        if not isinstance(quantile, (int, float)) or isinstance(quantile, bool) or quantile < 0:
            raise ArtifactStartupError(f"{path}: conformal_quantile must be a non-negative number")
    elif task in CLASSIFIER_TASKS:
        base_rate = meta["base_rate"]
        if not isinstance(base_rate, (int, float)) or isinstance(base_rate, bool) or not (0 <= base_rate <= 1):
            raise ArtifactStartupError(f"{path}: base_rate must be a number in [0, 1]")
        for key in ("calibration_status", "calibration_method"):
            value = meta[key]
            if not isinstance(value, str) or not value:
                raise ArtifactStartupError(f"{path}: {key} must be a non-empty string")

    feature_columns = meta["feature_columns"]
    if feature_columns != MODEL_INPUT_FEATURES[task]:
        raise ArtifactStartupError(
            f"{path}: feature_columns must equal MODEL_INPUT_FEATURES[{task!r}] "
            f"exactly, in order -- got {feature_columns!r}"
        )

    feature_dtypes = meta["feature_dtypes"]
    if not isinstance(feature_dtypes, dict) or set(feature_dtypes) != set(feature_columns):
        raise ArtifactStartupError(
            f"{path}: feature_dtypes keys must exactly match feature_columns "
            f"(no missing, no extra)"
        )
    unsupported = {v for v in feature_dtypes.values() if v not in _SUPPORTED_DTYPES}
    if unsupported:
        raise ArtifactStartupError(f"{path}: unsupported feature_dtypes value(s): {sorted(unsupported)}")

    ood_bounds = meta["ood_bounds"]
    if not isinstance(ood_bounds, dict) or not set(feature_columns) <= set(ood_bounds):
        missing_bounds = set(feature_columns) - set(ood_bounds if isinstance(ood_bounds, dict) else {})
        raise ArtifactStartupError(f"{path}: ood_bounds missing feature(s): {sorted(missing_bounds)}")

    algo = meta["algo"]
    if task not in metrics or algo not in metrics.get(task, {}):
        raise ArtifactStartupError(
            f"{path}: algo={algo!r} is not a key in metrics[{task!r}]"
        )


def _validate_metrics(metrics: Any) -> None:
    if not isinstance(metrics, dict):
        raise ArtifactStartupError(f"{_METRICS_PATH}: top-level JSON must be an object")
    for task in TASKS:
        if task not in metrics:
            raise ArtifactStartupError(f"{_METRICS_PATH}: missing required key: {task!r}")
        if f"{task}_holdout" not in metrics:
            raise ArtifactStartupError(f"{_METRICS_PATH}: missing required key: {task + '_holdout'!r}")
    if "P6_strategy_ranking" not in metrics:
        raise ArtifactStartupError(f"{_METRICS_PATH}: missing required key: 'P6_strategy_ranking'")
    ranking = metrics["P6_strategy_ranking"]
    if not isinstance(ranking, dict) or "ranked" not in ranking or "top_two_overlap" not in ranking:
        raise ArtifactStartupError(
            f"{_METRICS_PATH}: P6_strategy_ranking must contain 'ranked' and 'top_two_overlap'"
        )


def _validate_simulation(simulation: Any) -> None:
    if not isinstance(simulation, dict):
        raise ArtifactStartupError(f"{_SIMULATION_PATH}: top-level JSON must be an object")
    for strategy_id in STRATEGY_ALLOCATIONS:
        if strategy_id not in simulation:
            raise ArtifactStartupError(f"{_SIMULATION_PATH}: missing required key: {strategy_id!r}")
        entry = simulation[strategy_id]
        required = {"point", "lower", "upper", "n_bootstrap_used", "levels"}
        if not isinstance(entry, dict) or not required <= entry.keys():
            raise ArtifactStartupError(
                f"{_SIMULATION_PATH}: {strategy_id!r} missing required key(s): "
                f"{sorted(required - entry.keys()) if isinstance(entry, dict) else sorted(required)}"
            )


def load_static_assets() -> dict:
    """Reads, parses, and schema-checks all seven JSON assets, and
    verifies the five .joblib files' SHA-256 against their meta's
    checksums.artifact_sha256 -- by hashing raw bytes only, never
    joblib.load (D17). Raises ArtifactStartupError on the first problem
    found; never partially succeeds."""
    metrics = _read_json(_METRICS_PATH)
    _validate_metrics(metrics)

    meta = {}
    for task in TASKS:
        task_meta = _read_json(_META_PATHS[task])
        _validate_meta(task, task_meta, metrics)
        meta[task] = task_meta

    simulation = _read_json(_SIMULATION_PATH)
    _validate_simulation(simulation)

    for task in TASKS:
        expected = meta[task]["checksums"]["artifact_sha256"]
        actual = _sha256_file(JOBLIB_PATHS[task])
        if actual != expected:
            raise ArtifactStartupError(
                f"{JOBLIB_PATHS[task]}: SHA-256 mismatch -- expected {expected}, got {actual}"
            )

    return {"metrics": metrics, "meta": meta, "simulation": simulation}


_assets: dict | None = None
_assets_lock = threading.Lock()


def get_assets() -> dict:
    """Lazy, single-flight, memoized: the first caller (lifespan, or a
    route dependency if lifespan never ran) pays for load_static_assets();
    everyone after gets the cached bundle."""
    global _assets
    if _assets is not None:
        return _assets
    with _assets_lock:
        if _assets is None:
            _assets = load_static_assets()
        return _assets


def reset_assets_cache_for_tests() -> None:
    """Test-only escape hatch -- clears the module-level cache so a test
    can force a fresh load_static_assets() call (e.g. against a
    monkeypatched path). Never called from application code."""
    global _assets
    _assets = None


_joblib_cache: dict[str, Any] = {}
_joblib_locks: dict[str, threading.Lock] = {task: threading.Lock() for task in TASKS}


def get_artifact(task: str) -> Any:
    """Lazy, single-flight, per-task, memoized joblib load (D3). Never
    called with task="P6" by route code -- P6's simulator is a lookup
    over already-loaded JSON (D11), and P6.joblib is never unpickled on
    any request path (criterion 43).

    Raises ArtifactLoadError -- callers map this to 500 ErrorDetail -- on
    an unpickling failure, a library-version incompatibility, or (for
    P3/P4/P4S) classes_ != [0, 1]."""
    if task in _joblib_cache:
        return _joblib_cache[task]
    with _joblib_locks[task]:
        if task in _joblib_cache:
            return _joblib_cache[task]
        import joblib  # local import: keeps `import app.artifacts` itself light

        try:
            obj = joblib.load(JOBLIB_PATHS[task])
        except Exception as e:  # noqa: BLE001 -- any unpickling failure maps to 500
            raise ArtifactLoadError(f"{task}: failed to load artifact: {e}") from e

        if task in CLASSIFIER_TASKS:
            classes = list(getattr(obj, "classes_", []))
            if classes != [0, 1]:
                raise ArtifactLoadError(
                    f"{task}: unexpected classes_ {classes!r}, expected [0, 1]"
                )

        _joblib_cache[task] = obj
        return obj


def reset_artifact_cache_for_tests() -> None:
    """Test-only escape hatch, mirroring reset_assets_cache_for_tests()."""
    _joblib_cache.clear()
