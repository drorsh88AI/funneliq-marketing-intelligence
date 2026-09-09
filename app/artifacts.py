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

# D17 completeness, round 2: metrics.json's and P6_simulation.json's
# INTERNAL structure (not just top-level key presence) is what
# app/predict.py actually reads a request at a time -- metrics[task][algo]
# (_regression_metrics/_classification_metrics), the *_holdout blocks,
# P6_strategy_ranking["ranked"] (indexed per strategy_id), and
# P6_simulation[sid]["levels"][str(ad_budget)]["n"]. None of these were
# schema-checked before; a bad one surfaced as a bare KeyError/TypeError
# on the first request that needed it, not fail-fast at boot.
_REGRESSION_CV_KEYS = {"mean_mae", "mean_rmse", "mean_r2"}
_REGRESSION_HOLDOUT_KEYS = {"mae", "rmse", "r2"}
_CLASSIFIER_CV_KEYS = {"mean_roc_auc", "mean_pr_auc", "mean_brier", "mean_log_loss"}
_CLASSIFIER_HOLDOUT_KEYS = {"roc_auc", "pr_auc", "brier", "log_loss"}


def _is_number(value: Any) -> bool:
    """int/float, excluding bool (bool is an int subclass in Python)."""
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def _require_numeric_subkeys(container: Any, keys: set, path: Path, label: str) -> None:
    if not isinstance(container, dict) or not keys <= container.keys():
        missing = keys - set(container if isinstance(container, dict) else {})
        raise ArtifactStartupError(f"{path}: {label} missing required key(s): {sorted(missing)}")
    bad = {k for k in keys if not _is_number(container[k])}
    if bad:
        raise ArtifactStartupError(f"{path}: {label} has non-numeric value(s) for: {sorted(bad)}")


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
    if not isinstance(observed_values, list) or not all(_is_number(v) for v in observed_values):
        raise ArtifactStartupError(f"{path}: observed_ad_budget_values must be a list of numbers")

    if task == "P2":
        alpha = meta["alpha"]
        if not _is_number(alpha) or not (0 < alpha < 1):
            raise ArtifactStartupError(f"{path}: alpha must be a number in (0, 1)")
        quantile = meta["conformal_quantile"]
        if not _is_number(quantile) or quantile < 0:
            raise ArtifactStartupError(f"{path}: conformal_quantile must be a non-negative number")
    elif task in CLASSIFIER_TASKS:
        base_rate = meta["base_rate"]
        if not _is_number(base_rate) or not (0 <= base_rate <= 1):
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
    # app/inference.py's out_of_range_features reads bounds[col]["min"]/["max"]
    # directly for every feature_columns entry -- validate the shape it
    # actually needs, not just that a key named `col` exists.
    for col in feature_columns:
        bound = ood_bounds[col]
        if not isinstance(bound, dict) or not _is_number(bound.get("min")) or not _is_number(bound.get("max")):
            raise ArtifactStartupError(f"{path}: ood_bounds[{col!r}] must be an object with numeric 'min' and 'max'")
        if bound["min"] > bound["max"]:
            raise ArtifactStartupError(f"{path}: ood_bounds[{col!r}].min must be <= max")

    algo = meta["algo"]
    if task not in metrics or algo not in metrics.get(task, {}):
        raise ArtifactStartupError(
            f"{path}: algo={algo!r} is not a key in metrics[{task!r}]"
        )
    # app/predict.py's _regression_metrics/_classification_metrics read
    # metrics[task][algo]'s CV fields directly, keyed by the SAME algo this
    # just validated -- can only be checked here, after algo is known.
    cv_keys = _CLASSIFIER_CV_KEYS if task in CLASSIFIER_TASKS else _REGRESSION_CV_KEYS
    _require_numeric_subkeys(metrics[task][algo], cv_keys, path, f"metrics[{task!r}][{algo!r}]")


def _validate_metrics(metrics: Any) -> None:
    if not isinstance(metrics, dict):
        raise ArtifactStartupError(f"{_METRICS_PATH}: top-level JSON must be an object")
    for task in TASKS:
        if task not in metrics:
            raise ArtifactStartupError(f"{_METRICS_PATH}: missing required key: {task!r}")
        if f"{task}_holdout" not in metrics:
            raise ArtifactStartupError(f"{_METRICS_PATH}: missing required key: {task + '_holdout'!r}")
        # app/predict.py's _regression_metrics/_classification_metrics read
        # these holdout fields directly -- doesn't depend on `algo`
        # (the winning model is already baked into *_holdout), unlike the
        # per-algo CV check in _validate_meta below.
        holdout_keys = _CLASSIFIER_HOLDOUT_KEYS if task in CLASSIFIER_TASKS else _REGRESSION_HOLDOUT_KEYS
        _require_numeric_subkeys(metrics[f"{task}_holdout"], holdout_keys, _METRICS_PATH, f"{task}_holdout")
    # P2's LtvPrediction.interval_details also reads conformal_coverage
    # off P2_holdout specifically (app/predict.py predict_ltv).
    _require_numeric_subkeys(metrics["P2_holdout"], {"conformal_coverage"}, _METRICS_PATH, "P2_holdout")

    if "P6_strategy_ranking" not in metrics:
        raise ArtifactStartupError(f"{_METRICS_PATH}: missing required key: 'P6_strategy_ranking'")
    ranking = metrics["P6_strategy_ranking"]
    if not isinstance(ranking, dict) or "ranked" not in ranking or "top_two_overlap" not in ranking:
        raise ArtifactStartupError(
            f"{_METRICS_PATH}: P6_strategy_ranking must contain 'ranked' and 'top_two_overlap'"
        )
    # app/predict.py's simulate_budget does ranked.index(strategy_id) for
    # EVERY strategy_id in STRATEGY_ALLOCATIONS -- a ranking missing one,
    # or carrying a duplicate/unknown id, raises ValueError at request
    # time (an id absent from `ranked`) or silently mis-ranks (a dup).
    ranked = ranking["ranked"]
    expected_ids = set(STRATEGY_ALLOCATIONS)
    if not isinstance(ranked, list) or set(ranked) != expected_ids or len(ranked) != len(expected_ids):
        raise ArtifactStartupError(
            f"{_METRICS_PATH}: P6_strategy_ranking.ranked must be exactly "
            f"{sorted(expected_ids)}, no duplicates and no gaps -- got {ranked!r}"
        )
    if not isinstance(ranking["top_two_overlap"], bool):
        raise ArtifactStartupError(f"{_METRICS_PATH}: P6_strategy_ranking.top_two_overlap must be a bool")


def _validate_simulation(simulation: Any) -> None:
    if not isinstance(simulation, dict):
        raise ArtifactStartupError(f"{_SIMULATION_PATH}: top-level JSON must be an object")
    for strategy_id, pairs in STRATEGY_ALLOCATIONS.items():
        if strategy_id not in simulation:
            raise ArtifactStartupError(f"{_SIMULATION_PATH}: missing required key: {strategy_id!r}")
        entry = simulation[strategy_id]
        required = {"point", "lower", "upper", "n_bootstrap_used", "levels"}
        if not isinstance(entry, dict) or not required <= entry.keys():
            raise ArtifactStartupError(
                f"{_SIMULATION_PATH}: {strategy_id!r} missing required key(s): "
                f"{sorted(required - entry.keys()) if isinstance(entry, dict) else sorted(required)}"
            )
        # app/predict.py's simulate_budget reads point/lower/upper and
        # n_bootstrap_used straight into StrategyResult fields, and
        # levels[str(ad_budget)]["n"] for every allocation -- validate the
        # exact shape it consumes, not just that the top-level keys exist.
        _require_numeric_subkeys(entry, {"point", "lower", "upper"}, _SIMULATION_PATH, f"{strategy_id!r}")
        n_bootstrap = entry["n_bootstrap_used"]
        if not isinstance(n_bootstrap, int) or isinstance(n_bootstrap, bool) or n_bootstrap <= 0:
            raise ArtifactStartupError(f"{_SIMULATION_PATH}: {strategy_id!r}.n_bootstrap_used must be a positive int")

        levels = entry["levels"]
        expected_budgets = {str(ad_budget) for ad_budget, _count in pairs}
        if not isinstance(levels, dict) or not expected_budgets <= levels.keys():
            missing_levels = expected_budgets - set(levels if isinstance(levels, dict) else {})
            raise ArtifactStartupError(
                f"{_SIMULATION_PATH}: {strategy_id!r}.levels missing budget level(s): {sorted(missing_levels)}"
            )
        for budget in expected_budgets:
            n = levels[budget].get("n") if isinstance(levels[budget], dict) else None
            if not isinstance(n, int) or isinstance(n, bool) or n <= 0:
                raise ArtifactStartupError(
                    f"{_SIMULATION_PATH}: {strategy_id!r}.levels[{budget!r}].n must be a positive int"
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
