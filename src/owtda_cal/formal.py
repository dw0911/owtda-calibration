"""The formal scientific work-unit domain (re-audit 2026-09-16, Block A).

The audit's one hard gap: TEST and smoke dispatch through the shared work-unit
channel (``workunit.run_units``) but the FORMAL modes are still refused
(``FORMAL_RUNNER_NOT_IMPLEMENTED``).  This module is the *formal* counterpart of
the smoke runner, in the **formal identity domain** (Plan §16: the two namespaces
must never mix).

Everything here reuses the derivations that already exist and are frozen:

* ``cells.master_replicate_id / physical_cell_id / base_series_id / data_unit_id``
* ``scope.logical_cell_id / logical_data_key / logical_feature_key /
  logical_evaluation_key / experiment_id``
* ``formal_ids.feature_sufficient_id / evaluation_id / resampling_stream_id``

It does **not** touch ``smoke_ids``.  The differences from the smoke domain are
real, not cosmetic:

* the formal data streams use ``dgp``'s *default* ``stream_prefix`` (``null_`` /
  ``h1_``) and *default* fields ``{data_generation_id, DGP_family,
  master_replicate_id}`` -- the smoke runner overrides both, the formal runner
  must not;
* the formal resampling streams use ``calibrate``'s *default* ``stream_kind``
  (``M0_permutation`` / ``M1_gaussian_innovation``) with the formal fields
  ``{method_generation_id, data_unit_id, resample_index}`` -- the smoke runner
  overrides both;
* the seed registry gives the formal domain **three root keys per phase**
  (``{null,h1}_data``, ``{null,h1}_M0``, ``{null,h1}_M1``), not one ``smoke`` key;
* ``R0_H0=2500`` / ``R0_H1=1600`` instead of ``R0_SMOKE=32``.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from . import cells, dgp, formal_ids, formal_rows, scope
from .calibrate import M0_STABLE_ID, M1_STABLE_ID, calibrate_m0, calibrate_m1
from .components import method_config_hash
from .features import (
    BPI_STABLE_ID,
    MOMENTS_STABLE_ID,
    SCENARIO_N_AR,
    SCENARIO_N_CIRCLE,
    bpi_feature_spec,
    feature_config_hash,
    feature_matrix_for_windows,
    feature_sufficient_stats,
    moments_feature_spec,
)
from .hashing import array_hash
from .scan import scan_statistic
from .scope import build_null_signature
from .seeding import derive_seed_hex

#: The formal phases (distinct from the smoke ``SMOKE_NULL``/``SMOKE_ALT``).
FORMAL_PHASES = (scope.PHASE_NULL, scope.PHASE_ALT)

#: ``phase -> (data_stream_family, m0_stream_family, m1_stream_family)``.
FORMAL_STREAM_FAMILIES: dict[str, tuple[str, str, str]] = {
    scope.PHASE_NULL: ("null_data", "null_M0", "null_M1"),
    scope.PHASE_ALT: ("h1_data", "h1_M0", "h1_M1"),
}

FEATURE_KIND_BY_STABLE = {BPI_STABLE_ID: "bpi", MOMENTS_STABLE_ID: "moments"}
FEATURE_USES_PH = {BPI_STABLE_ID: True, MOMENTS_STABLE_ID: False}
FEATURE_CONFIG_HASH_BY_STABLE = {
    BPI_STABLE_ID: feature_config_hash(bpi_feature_spec()),
    MOMENTS_STABLE_ID: feature_config_hash(moments_feature_spec()),
}
METHOD_BY_KEY = {
    "M0": (M0_STABLE_ID, calibrate_m0),
    "M1": (M1_STABLE_ID, calibrate_m1),
}
METHOD_CONFIG_HASH_BY_KEY = {
    key: method_config_hash(stable_id) for key, (stable_id, _) in METHOD_BY_KEY.items()
}


def formal_data_generation_id(manifest: dict[str, Any]) -> str:
    """The frozen formal data generation id (``component_generations.data_generation_id``)."""
    generations = manifest.get("component_generations") or {}
    value = generations.get("data_generation_id")
    if not value:
        raise ValueError("the freeze manifest declares no formal data_generation_id")
    return str(value)


def formal_context(manifest: dict[str, Any], phase: str) -> dict[str, Any]:
    """The formal context for one phase (the counterpart of ``smoke_context``).

    Unlike the smoke context there is **no single phase-level experiment id**:
    ``scope.experiment_id`` is scenario-scoped, so the experiment id is derived
    per scenario inside the worker.
    """
    if phase not in FORMAL_PHASES:
        raise ValueError(f"unknown formal phase {phase!r}")
    generations = manifest.get("component_generations") or {}
    method_generation_id = generations.get("method_generation_id") or {}
    feature_generation_id = generations.get("feature_generation_id") or {}
    ctx: dict[str, Any] = {
        "project_id": manifest["project_id"],
        "protocol_id": manifest["protocol_id"],
        "freeze_id": manifest["freeze_id"],
        "evidence_generation_id": manifest["evidence_generation_id"],
        "data_generation_id": formal_data_generation_id(manifest),
        "method_generation_id": dict(method_generation_id),
        "feature_generation_id": dict(feature_generation_id),
        "source_tree_hash": manifest.get("source_tree_hash"),
        "environment_lock_hash": manifest.get("environment_lock_hash"),
        "compute_git_commit": manifest.get("compute_git_commit"),
        "phase": phase,
    }
    if phase == scope.PHASE_NULL:
        starts = sorted(cells.unique_window_start_map())
        ctx["starts"] = starts
        ctx["index_of"] = {k: i for i, k in enumerate(starts)}
    return ctx


def formal_root_keys(seed_registry: dict[str, Any], phase: str) -> dict[str, str]:
    """The phase's three formal root keys ``{data, M0, M1}`` (Plan §15.1)."""
    if phase not in FORMAL_PHASES:
        raise ValueError(f"unknown formal phase {phase!r}")
    families = FORMAL_STREAM_FAMILIES[phase]
    expected_data = "D01"  # the frozen formal data generation id (both phases)
    keys: dict[str, str] = {}
    for name, family in zip(("data", "M0", "M1"), families):
        matches = [
            entry
            for entry in seed_registry["entries"]
            if entry["phase"] == phase and entry["stream_family"] == family
        ]
        if len(matches) != 1:
            raise ValueError(
                f"expected exactly one formal {family!r} root entry for {phase!r}"
            )
        entry = matches[0]
        if name == "data" and entry.get("component_generation_id") != expected_data:
            raise ValueError(
                f"formal data root for {phase!r} carries generation "
                f"{entry.get('component_generation_id')!r}, expected {expected_data!r}"
            )
        key = entry.get("root_key_hex")
        if not key:
            raise ValueError(f"formal {family!r} root entry for {phase!r} has no key")
        keys[name] = key
    return keys


def formal_experiment_id(ctx: dict[str, Any], *, phase: str, scenario_id: str) -> str:
    """The scenario-scoped formal experiment id (``scope.experiment_id``)."""
    return scope.experiment_id(
        project_id=ctx["project_id"],
        protocol_id=ctx["protocol_id"],
        freeze_id=ctx["freeze_id"],
        evidence_generation_id=ctx["evidence_generation_id"],
        phase=phase,
        scenario_id=scenario_id,
    )


def _formal_scenario(family: str) -> str:
    return SCENARIO_N_AR if family == dgp.DGP_FAMILY_N_AR else SCENARIO_N_CIRCLE


def _formal_data_model_hash(
    family: str, rho: str, *, scenario: str | None = None
) -> str:
    """Return the frozen data-model hash for one formal cell.

    H1 alternatives share the ``CIRCLE_BASED_H1`` family name but the two
    registered scenarios have distinct data-model specs.  The scenario must
    therefore participate in the predeclared identity exactly as it does in
    the production worker.
    """
    if family == dgp.DGP_FAMILY_N_AR:
        spec = dgp.n_ar_data_model_spec(rho)
    elif family == dgp.DGP_FAMILY_N_CIRCLE:
        spec = dgp.n_circle_data_model_spec(rho)
    elif family == dgp.DGP_FAMILY_H1:
        if not scenario:
            raise ValueError("formal H1 data-model identity requires scenario")
        spec = dgp.h1_data_model_spec(scenario, rho)
    else:
        raise ValueError(f"unknown formal DGP family {family!r}")
    return dgp.data_model_config_hash(spec)


def formal_cell_identity(
    *,
    ctx: dict[str, Any],
    cell: Any,
    family: str,
    master_replicate_id: str,
    data_model_config_hash: str,
    feature_id: str,
) -> dict[str, str]:
    """The cell/feature-scoped formal identity chain (no method id).

    ``cell`` is a ``NullCell`` or ``AltCell`` (both carry ``rho/W/stride/T/M``;
    ``NullCell`` adds ``family``, ``AltCell`` adds ``scenario`` and its DGP family
    is always ``DGP_FAMILY_H1`` -- so ``family`` is passed explicitly).
    """
    phase = ctx["phase"]
    data_generation_id = ctx["data_generation_id"]
    scenario_id = scope.SCENARIO_NULL if phase == scope.PHASE_NULL else cell.scenario
    physical_cell_id = cells.physical_cell_id(
        protocol_id=ctx["protocol_id"],
        freeze_id=ctx["freeze_id"],
        evidence_generation_id=ctx["evidence_generation_id"],
        phase=phase,
        rho=cell.rho,
        W=cell.W,
        stride=cell.stride,
        T=cell.T,
        M=cell.M,
        data_model_config_hash=data_model_config_hash,
    )
    base_series_id = cells.base_series_id(
        master_replicate_id=master_replicate_id,
        data_generation_id=data_generation_id,
        DGP_family=family,
        rho=cell.rho,
        raw_length=cell.T,  # Plan section 7: the cell prefix, not the master cache
        data_model_config_hash=data_model_config_hash,
    )
    data_unit_id = cells.data_unit_id(
        base_series_id=base_series_id,
        physical_cell_id=physical_cell_id,
        data_generation_id=data_generation_id,
    )
    logical_cell_id = scope.logical_cell_id(
        project_id=ctx["project_id"],
        protocol_id=ctx["protocol_id"],
        freeze_id=ctx["freeze_id"],
        evidence_generation_id=ctx["evidence_generation_id"],
        phase=phase,
        DGP_family=family,
        scenario_id=scenario_id,
        rho=cell.rho,
        W=cell.W,
        stride=cell.stride,
        T=cell.T,
        M=cell.M,
    )
    logical_data_key = scope.logical_data_key(
        logical_cell_id=logical_cell_id, master_replicate_id=master_replicate_id
    )
    logical_feature_key = scope.logical_feature_key(
        logical_data_key=logical_data_key, feature_id=feature_id
    )
    feature_sufficient_id = formal_ids.feature_sufficient_id(
        data_generation_id=data_generation_id,
        data_unit_id=data_unit_id,
        feature_id=feature_id,
        feature_config_hash=FEATURE_CONFIG_HASH_BY_STABLE[feature_id],
    )
    return {
        "physical_cell_id": physical_cell_id,
        "base_series_id": base_series_id,
        "data_unit_id": data_unit_id,
        "logical_cell_id": logical_cell_id,
        "logical_data_key": logical_data_key,
        "logical_feature_key": logical_feature_key,
        "feature_sufficient_id": feature_sufficient_id,
        "scenario_id": scenario_id,
    }


def formal_evaluation_identity(
    *,
    ctx: dict[str, Any],
    data_unit_id: str,
    logical_data_key: str,
    feature_id: str,
    feature_sufficient_id: str,
    method_id: str,
    method_config_hash_value: str,
) -> dict[str, str]:
    """The method-scoped formal identity tail (logical evaluation + evaluation)."""
    logical_evaluation_key = scope.logical_evaluation_key(
        logical_data_key=logical_data_key, feature_id=feature_id, method_id=method_id
    )
    evaluation_id = formal_ids.evaluation_id(
        data_generation_id=ctx["data_generation_id"],
        data_unit_id=data_unit_id,
        feature_sufficient_id=feature_sufficient_id,
        method_id=method_id,
        method_config_hash=method_config_hash_value,
    )
    return {
        "logical_evaluation_key": logical_evaluation_key,
        "evaluation_id": evaluation_id,
    }


def formal_identity_chain(
    *,
    ctx: dict[str, Any],
    cell: Any,
    family: str,
    master_replicate_id: str,
    data_model_config_hash: str,
    feature_id: str,
    feature_config_hash: str,
    method_id: str,
    method_config_hash: str,
) -> dict[str, str]:
    """The full formal identity chain for one (cell, replicate, feature, method).

    Convenience for tests and introspection; the runners split it into the
    cell/feature part and the method part (exactly like the smoke runner).
    """
    del feature_config_hash  # already encoded by FEATURE_CONFIG_HASH_BY_STABLE
    chain = formal_cell_identity(
        ctx=ctx, cell=cell, family=family, master_replicate_id=master_replicate_id,
        data_model_config_hash=data_model_config_hash, feature_id=feature_id,
    )
    chain.update(
        formal_evaluation_identity(
            ctx=ctx, data_unit_id=chain["data_unit_id"],
            logical_data_key=chain["logical_data_key"], feature_id=feature_id,
            feature_sufficient_id=chain["feature_sufficient_id"],
            method_id=method_id, method_config_hash_value=method_config_hash,
        )
    )
    return chain


def _formal_row(
    *,
    ctx: dict[str, Any],
    experiment_id: str,
    logical_cell_id: str,
    logical_data_key: str,
    logical_feature_key: str,
    logical_evaluation_key: str,
    data_unit_id: str,
    feature_sufficient_id: str,
    evaluation_id: str,
    DGP_family: str,
    scenario_id: str,
    rho: str,
    feature_id: str,
    method_id: str,
    out: dict[str, Any],
) -> dict[str, Any]:
    return {
        "phase": ctx["phase"],
        "experiment_id": experiment_id,
        "logical_cell_id": logical_cell_id,
        "logical_data_key": logical_data_key,
        "logical_feature_key": logical_feature_key,
        "logical_evaluation_key": logical_evaluation_key,
        "data_unit_id": data_unit_id,
        "feature_sufficient_id": feature_sufficient_id,
        "evaluation_id": evaluation_id,
        "DGP_family": DGP_family,
        "scenario_id": scenario_id,
        "rho": rho,
        "feature_id": feature_id,
        "method_id": method_id,
        "observed_statistic": float(out["observed_statistic"]),
        "exceed_count": int(out["exceed_count"]),
        "p_value": float(out["p_value"]),
        "reject": bool(out["reject"]),
    }


class FormalWorkUnitError(RuntimeError):
    """Pickle-safe failure carrying an attributable partial, never a success row."""

    def __init__(self, message: str, *, details: dict[str, Any] | None = None,
                 partial_result: dict[str, Any] | None = None) -> None:
        super().__init__(message)
        self.details = details or {}
        self.error_class = self.details.get("error_class", "TASK_EXCEPTION")
        self.partial_result = partial_result or {}


class FormalPhaseError(RuntimeError):
    """The outer supervisor must persist the complete dispatch outcome."""

    def __init__(self, message: str, *, dispatch: Any | None = None) -> None:
        super().__init__(message)
        self.dispatch = dispatch


def _data_stream_fields(
    ctx: dict[str, Any], family: str, master_replicate_id: str
) -> dict[str, Any]:
    """The formal data-stream named fields (dgp default, Plan §15.2)."""
    return {
        "data_generation_id": ctx["data_generation_id"],
        "DGP_family": family,
        "master_replicate_id": master_replicate_id,
    }


def _content_for(
    *,
    master: Any,
    cell: Any,
    sub: Any,
    root_keys: dict[str, str],
    ctx: dict[str, Any],
    family: str,
    master_replicate_id: str,
    is_null: bool,
) -> dict[str, Any]:
    """Content hashes + stream seeds for one (cell, replicate)."""
    fields = _data_stream_fields(ctx, family, master_replicate_id)
    prefix = "null_" if is_null else "h1_"
    return {
        "feature_matrix_hash": array_hash(
            "window_feature_matrix_v1", sub, dtype_code=">f8"
        ),
        # getattr so error-propagation tests can stub a minimal master; the real
        # NullMaster/H1Master always carry these.
        "data_content_hash": (
            master.raw_series_hash(cell.T) if hasattr(master, "raw_series_hash") else None
        ),
        "raw_series_hash": (
            master.raw_series_hash(cell.T) if hasattr(master, "raw_series_hash") else None
        ),
        "innovation_hash": getattr(master, "innovation_hash", None),
        "initial_state_seed": derive_seed_hex(
            root_keys["data"], f"{prefix}initial", **fields
        ),
        "innovation_seed": derive_seed_hex(
            root_keys["data"], f"{prefix}innovation", **fields
        ),
        "observation_noise_seed": (
            derive_seed_hex(root_keys["data"], f"{prefix}observation_noise", **fields)
            if family in (dgp.DGP_FAMILY_N_CIRCLE, dgp.DGP_FAMILY_H1) else None
        ),
    }


_schema_cache: dict[tuple[Any, ...], Any] = {}


def _cached_schema(
    phase: str, family: str, scenario_id: str, feature_id: str, method_id: str
) -> Any:
    key = (phase, family, scenario_id, feature_id, method_id)
    if key not in _schema_cache:
        _schema_cache[key] = formal_rows.load_row_schema(
            phase=phase, DGP_family=family, scenario_id=scenario_id,
            feature_id=feature_id, method_id=method_id,
        )
    return _schema_cache[key]


def process_formal_master_feature(payload: dict[str, Any]) -> dict[str, Any]:
    """Formal worker entry point: one H0 master path x one feature (Plan §9.3)."""
    family = payload["family"]
    rho = payload["rho"]
    replicate = payload["replicate"]
    feature_id = payload["feature_id"]
    root_keys = payload["root_keys"]
    ctx = payload["ctx"]
    phase = ctx["phase"]  # "NULL"
    data_generation_id = ctx["data_generation_id"]
    starts = ctx["starts"]
    index_of = ctx["index_of"]

    scenario = _formal_scenario(family)
    master_replicate_id = cells.master_replicate_id(
        project_id=ctx["project_id"],
        protocol_id=ctx["protocol_id"],
        freeze_id=ctx["freeze_id"],
        evidence_generation_id=ctx["evidence_generation_id"],
        phase=phase,
        DGP_family=family,
        replicate_id=replicate,
    )
    data_model_config_hash = _formal_data_model_hash(family, rho)
    master = dgp.generate_null_master(
        family=family,
        rho=rho,
        root_key_hex=root_keys["data"],
        data_generation_id=data_generation_id,
        master_replicate_id=master_replicate_id,
        # default stream_prefix="null_", stream_fields=None -> formal fields
    )
    if family == dgp.DGP_FAMILY_N_AR:
        raw = master.raw_prefix_1d(cells.L_MASTER)
    else:
        raw = master.raw_prefix(cells.L_MASTER)
    windows = [raw[k : k + cells.W_FIXED] for k in starts]
    matrix = feature_matrix_for_windows(
        windows, feature_kind=FEATURE_KIND_BY_STABLE[feature_id], scenario=scenario
    )

    rows: list[dict[str, Any]] = []
    feature_rows: list[dict[str, Any]] = []
    errors = 0
    data_units = 0
    method_generation_id = ctx["method_generation_id"]
    run_identity = payload.get("run_identity", {})
    for cell in scope.h0_null_cells():
        if cell.family != family or cell.rho != rho:
            continue
        idx = [index_of[k] for k in [(i - 1) * cell.stride for i in range(1, cell.M + 1)]]
        sub = matrix[idx]
        identity = formal_cell_identity(
            ctx=ctx, cell=cell, family=family,
            master_replicate_id=master_replicate_id,
            data_model_config_hash=data_model_config_hash, feature_id=feature_id,
        )
        scan = scan_statistic(sub)
        content = _content_for(
            master=master, cell=cell, sub=sub, root_keys=root_keys, ctx=ctx,
            family=family, master_replicate_id=master_replicate_id, is_null=True,
        )
        sufficient = feature_sufficient_stats(sub)
        null_model_config_hash = build_null_signature(
            rho=cell.rho, W=cell.W, stride=cell.stride, T=cell.T, M=cell.M,
        )
        feature_rows.append(
            formal_rows.build_feature_sufficient_row(
                ctx=ctx, feature_id=feature_id, cell_identity=identity,
                sufficient={"a": sufficient["a"], "q": sufficient["q"]},
                content=content,
                feature_config_hash=FEATURE_CONFIG_HASH_BY_STABLE[feature_id],
                feature_matrix_hash=content["feature_matrix_hash"],
            )
        )
        data_units += 1
        for method_key, (method_id, _) in METHOD_BY_KEY.items():
            evaluation = formal_evaluation_identity(
                ctx=ctx, data_unit_id=identity["data_unit_id"],
                logical_data_key=identity["logical_data_key"], feature_id=feature_id,
                feature_sufficient_id=identity["feature_sufficient_id"],
                method_id=method_id,
                method_config_hash_value=METHOD_CONFIG_HASH_BY_KEY[method_key],
            )
            try:
                if method_key == "M0":
                    out = calibrate_m0(
                        sub,
                        root_key_hex=root_keys["M0"],
                        method_generation_id=method_generation_id.get("M0"),
                        data_unit_id=identity["data_unit_id"],
                    )
                else:
                    out = calibrate_m1(
                        sub,
                        root_key_hex=root_keys["M1"],
                        method_generation_id=method_generation_id.get("M1"),
                        data_unit_id=identity["data_unit_id"],
                        W=cell.W,
                        stride=cell.stride,
                    )
            except Exception as exc:
                from .executor import classify_error
                details = {
                    "evaluation_id": evaluation["evaluation_id"],
                    "data_unit_id": identity["data_unit_id"],
                    "feature_id": feature_id, "method_id": method_id,
                    "error_class": classify_error(exc),
                    "exception_type": type(exc).__name__, "message": str(exc),
                }
                raise FormalWorkUnitError(
                    f"{details['error_class']} at {details['evaluation_id']}: {exc}",
                    details=details, partial_result={"rows": list(rows), "errors": [details]},
                ) from exc
            schema = _cached_schema(
                phase, family, identity["scenario_id"], feature_id, method_id
            )
            rows.append(
                formal_rows.build_formal_row(
                    ctx=ctx, cell=cell, family=family,
                    scenario_id=identity["scenario_id"], replicate_id=replicate,
                    feature_id=feature_id, method_id=method_id, method_key=method_key,
                    cell_identity=identity, eval_identity=evaluation,
                    out=out, scan=scan, content=content,
                    run_identity=_resolve_registry_entry_hashes(
                        run_identity, family=family, feature_id=feature_id,
                        method_id=method_id,
                    ),
                    null_model_config_hash=null_model_config_hash,
                    feature_config_hash=FEATURE_CONFIG_HASH_BY_STABLE[feature_id],
                    method_config_hash=METHOD_CONFIG_HASH_BY_KEY[method_key],
                    schema=schema,
                )
            )
    return {
        "rows": rows,
        "feature_rows": feature_rows,
        "errors": errors,
        "data_units": data_units,
        "ph_windows": len(starts) if FEATURE_USES_PH[feature_id] else 0,
        "feature_windows": len(starts),
    }


def process_formal_alt_feature(payload: dict[str, Any]) -> dict[str, Any]:
    """Formal worker entry point: one H1 alternative replicate x one feature."""
    scenario = payload["scenario"]
    rho = payload["rho"]
    replicate = payload["replicate"]
    feature_id = payload["feature_id"]
    root_keys = payload["root_keys"]
    ctx = payload["ctx"]
    phase = ctx["phase"]  # "ALT"
    data_generation_id = ctx["data_generation_id"]
    family = dgp.DGP_FAMILY_H1

    master_replicate_id = cells.master_replicate_id(
        project_id=ctx["project_id"],
        protocol_id=ctx["protocol_id"],
        freeze_id=ctx["freeze_id"],
        evidence_generation_id=ctx["evidence_generation_id"],
        phase=phase,
        DGP_family=family,
        replicate_id=replicate,
    )
    master = dgp.generate_h1_master(
        scenario=scenario,
        rho=rho,
        root_key_hex=root_keys["data"],
        data_generation_id=data_generation_id,
        master_replicate_id=master_replicate_id,
        # default stream_prefix="h1_", stream_fields=None -> formal fields
    )
    data_model_config_hash = dgp.data_model_config_hash(
        dgp.h1_data_model_spec(scenario, rho)
    )
    raw_cache: dict[int, Any] = {}
    rows: list[dict[str, Any]] = []
    feature_rows: list[dict[str, Any]] = []
    errors = 0
    data_units = 0
    ph_windows = 0
    feature_windows = 0
    method_generation_id = ctx["method_generation_id"]
    run_identity = payload.get("run_identity", {})
    for cell in scope.h1_alt_cells():
        if cell.scenario != scenario or cell.rho != rho:
            continue
        raw = raw_cache.get(cell.T)
        if raw is None:
            raw = master.raw_prefix(cell.T)
            raw_cache[cell.T] = raw
        starts = [(i - 1) * cell.stride for i in range(1, cell.M + 1)]
        windows = [raw[k : k + cell.W] for k in starts]
        matrix = feature_matrix_for_windows(
            windows, feature_kind=FEATURE_KIND_BY_STABLE[feature_id],
            scenario=SCENARIO_N_CIRCLE,
        )
        ph_windows += len(starts) if FEATURE_USES_PH[feature_id] else 0
        feature_windows += len(starts)
        identity = formal_cell_identity(
            ctx=ctx, cell=cell, family=family,
            master_replicate_id=master_replicate_id,
            data_model_config_hash=data_model_config_hash, feature_id=feature_id,
        )
        scan = scan_statistic(matrix)
        content = _content_for(
            master=master, cell=cell, sub=matrix, root_keys=root_keys, ctx=ctx,
            family=family, master_replicate_id=master_replicate_id, is_null=False,
        )
        sufficient = feature_sufficient_stats(matrix)
        # H1 is CIRCLE_BASED_H1: its null-model signature binds the matching
        # N-CIRCLE NULL cell of the same (rho, W, stride, T, M).
        null_model_config_hash = build_null_signature(
            rho=cell.rho, W=cell.W, stride=cell.stride, T=cell.T, M=cell.M,
        )
        feature_rows.append(
            formal_rows.build_feature_sufficient_row(
                ctx=ctx, feature_id=feature_id, cell_identity=identity,
                sufficient={"a": sufficient["a"], "q": sufficient["q"]},
                content=content,
                feature_config_hash=FEATURE_CONFIG_HASH_BY_STABLE[feature_id],
                feature_matrix_hash=content["feature_matrix_hash"],
            )
        )
        data_units += 1
        for method_key, (method_id, _) in METHOD_BY_KEY.items():
            evaluation = formal_evaluation_identity(
                ctx=ctx, data_unit_id=identity["data_unit_id"],
                logical_data_key=identity["logical_data_key"], feature_id=feature_id,
                feature_sufficient_id=identity["feature_sufficient_id"],
                method_id=method_id,
                method_config_hash_value=METHOD_CONFIG_HASH_BY_KEY[method_key],
            )
            try:
                if method_key == "M0":
                    out = calibrate_m0(
                        matrix,
                        root_key_hex=root_keys["M0"],
                        method_generation_id=method_generation_id.get("M0"),
                        data_unit_id=identity["data_unit_id"],
                    )
                else:
                    out = calibrate_m1(
                        matrix,
                        root_key_hex=root_keys["M1"],
                        method_generation_id=method_generation_id.get("M1"),
                        data_unit_id=identity["data_unit_id"],
                        W=cell.W,
                        stride=cell.stride,
                    )
            except Exception as exc:
                from .executor import classify_error
                details = {
                    "evaluation_id": evaluation["evaluation_id"],
                    "data_unit_id": identity["data_unit_id"],
                    "feature_id": feature_id, "method_id": method_id,
                    "error_class": classify_error(exc),
                    "exception_type": type(exc).__name__, "message": str(exc),
                }
                raise FormalWorkUnitError(
                    f"{details['error_class']} at {details['evaluation_id']}: {exc}",
                    details=details, partial_result={"rows": list(rows), "errors": [details]},
                ) from exc
            schema = _cached_schema(
                phase, family, cell.scenario, feature_id, method_id
            )
            rows.append(
                formal_rows.build_formal_row(
                    ctx=ctx, cell=cell, family=family,
                    scenario_id=cell.scenario, replicate_id=replicate,
                    feature_id=feature_id, method_id=method_id, method_key=method_key,
                    cell_identity=identity, eval_identity=evaluation,
                    out=out, scan=scan, content=content,
                    run_identity=_resolve_registry_entry_hashes(
                        run_identity, family=family, feature_id=feature_id,
                        method_id=method_id,
                    ),
                    null_model_config_hash=null_model_config_hash,
                    feature_config_hash=FEATURE_CONFIG_HASH_BY_STABLE[feature_id],
                    method_config_hash=METHOD_CONFIG_HASH_BY_KEY[method_key],
                    schema=schema,
                    source_null_phase_seal_hash=run_identity.get("source_null_phase_seal_hash"),
                    shift_direction_seed=getattr(master, "shift_direction_seed", None),
                )
            )
    return {
        "rows": rows,
        "feature_rows": feature_rows,
        "errors": errors,
        "data_units": data_units,
        "ph_windows": ph_windows,
        "feature_windows": feature_windows,
    }


@dataclass
class FormalResult:
    """The formal run result (the counterpart of ``smoke.SmokeResult``).

    Unlike the blind smoke the formal rows carry the full per-evaluation
    ``reject``/``p_value`` payloads -- but this object only *carries* them; it
    performs no selection, ranking or aggregation (that is the L2 analysis, not
    this adapter).
    """

    phase: str
    wall_seconds: float
    data_units: int
    evaluation_rows: int
    ph_windows: int
    feature_windows: int
    errors: int
    rows: list[dict[str, Any]] = field(default_factory=list)
    feature_rows: list[dict[str, Any]] = field(default_factory=list)


def predeclare_formal_indexes(
    *,
    manifest: dict[str, Any],
    phase: str,
    replicate_limit: int | None = None,
) -> dict[str, Any]:
    """Pre-declare the three expected indexes (and their hashes) before compute.

    Every produced id (data_unit_id / feature_sufficient_id / evaluation_id) is a
    deterministic function of the frozen scope design + identity chain -- none of
    them depend on the resampler -- so the expected indexes can be materialised
    up front.  ``run_instance_id`` (and the run identity carried into every row)
    are then derived from these *pre-declared* hashes, not from post-hoc rows.
    """
    from . import cells, indexes, scope

    ctx = formal_context(manifest, phase)
    replicate_count = scope.R0_H0 if phase == scope.PHASE_NULL else scope.R0_H1
    if replicate_limit is not None:
        replicate_count = replicate_limit

    data_units: dict[str, dict[str, str]] = {}
    feature_index: dict[str, dict[str, str]] = {}
    evaluation_index: dict[str, dict[str, str]] = {}

    cells_iter = scope.h0_null_cells() if phase == scope.PHASE_NULL else scope.h1_alt_cells()
    for cell in cells_iter:
        family = getattr(cell, "family", dgp.DGP_FAMILY_H1)
        rho = cell.rho
        data_model_config_hash = _formal_data_model_hash(
            family, rho, scenario=getattr(cell, "scenario", None)
        )
        for replicate in range(1, replicate_count + 1):
            master_replicate_id = cells.master_replicate_id(
                project_id=ctx["project_id"], protocol_id=ctx["protocol_id"],
                freeze_id=ctx["freeze_id"], evidence_generation_id=ctx["evidence_generation_id"],
                phase=phase, DGP_family=family, replicate_id=replicate,
            )
            for feature_id in scope.FEATURE_IDS:
                identity = formal_cell_identity(
                    ctx=ctx, cell=cell, family=family,
                    master_replicate_id=master_replicate_id,
                    data_model_config_hash=data_model_config_hash, feature_id=feature_id,
                )
                data_units[identity["data_unit_id"]] = {
                    "logical_data_key": identity["logical_data_key"],
                    "data_unit_id": identity["data_unit_id"],
                }
                feature_index[identity["feature_sufficient_id"]] = {
                    "logical_data_key": identity["logical_data_key"],
                    "logical_feature_key": identity["logical_feature_key"],
                    "data_unit_id": identity["data_unit_id"],
                    "feature_sufficient_id": identity["feature_sufficient_id"],
                }
                for method_key, (method_id, _) in METHOD_BY_KEY.items():
                    evaluation = formal_evaluation_identity(
                        ctx=ctx, data_unit_id=identity["data_unit_id"],
                        logical_data_key=identity["logical_data_key"], feature_id=feature_id,
                        feature_sufficient_id=identity["feature_sufficient_id"],
                        method_id=method_id,
                        method_config_hash_value=METHOD_CONFIG_HASH_BY_KEY[method_key],
                    )
                    evaluation_index[evaluation["evaluation_id"]] = {
                        "logical_data_key": identity["logical_data_key"],
                        "logical_feature_key": identity["logical_feature_key"],
                        "logical_evaluation_key": evaluation["logical_evaluation_key"],
                        "data_unit_id": identity["data_unit_id"],
                        "feature_sufficient_id": identity["feature_sufficient_id"],
                        "evaluation_id": evaluation["evaluation_id"],
                    }

    data_rows = indexes.expected_data_index_rows(data_units.values())
    feature_rows = indexes.expected_feature_index_rows(feature_index.values())
    eval_rows = indexes.expected_evaluation_index_rows(evaluation_index.values())
    return {
        "data_rows": data_rows,
        "feature_rows": feature_rows,
        "evaluation_rows": eval_rows,
        "expected_data_index_hash": indexes.index_content_hash(data_rows),
        "expected_index_hash": indexes.index_content_hash(eval_rows),
        "expected_feature_index_hash": indexes.index_content_hash(feature_rows),
    }


def formal_run_identity(
    *,
    component_set: dict[str, Any],
    predeclared: dict[str, Any],
    run_component_set_hash: str,
    run_instance_id: str,
    shard_plan_hash: str,
) -> dict[str, Any]:
    """The run identity carried into every scientific row.

    The run-id / shard-plan / expected-index hashes come from the *pre-declared*
    indexes so they are fixed before compute.  The registry entry hashes are
    per-component (feature/method/data), so the full ``stable_id -> hash`` map is
    carried under ``registry_entry_hash_map``; the flat ``*_registry_entry_hash``
    fields hold a run-level default and are overwritten per row by
    ``_resolve_registry_entry_hashes``.
    """
    registry_map: dict[str, dict[str, str]] = {}
    for r in component_set["component_refs"]:
        registry_map.setdefault(r["role"], {})[r["stable_id"]] = r["hash"]
    roots: dict[str, str] = {}
    for r in component_set["root_refs"]:
        roots[r["stable_id"]] = r["hash"]

    def _default(role: str) -> str | None:
        vals = registry_map.get(role, {})
        return next(iter(vals.values()), None)

    return {
        "compute_git_commit": component_set["compute_git_commit"],
        "run_config_manifest_hash": component_set["run_config_manifest_hash"],
        "registry_snapshot_hash": component_set["registry_snapshot_hash"],
        "run_component_set_hash": run_component_set_hash,
        "run_instance_id": run_instance_id,
        "shard_plan_hash": shard_plan_hash,
        "expected_index_hash": predeclared["expected_index_hash"],
        "expected_feature_index_hash": predeclared["expected_feature_index_hash"],
        "registry_entry_hash_map": registry_map,
        "feature_registry_entry_hash": _default("feature"),
        "method_registry_entry_hash": _default("method"),
        "data_registry_entry_hash": _default("data"),
        "data_root_entry_hash": roots.get("null_data") or roots.get("h1_data"),
        "resampling_root_entry_hash": roots.get("null_M0") or roots.get("h1_M0"),
        # H1 rows carry the authoritative NULL phase seal as their source-null
        # binding (NULL rows leave it absent -> null in the row).
        "source_null_phase_seal_hash": component_set.get("parent_phase_seal_hash"),
    }


def _resolve_registry_entry_hashes(
    run_identity: dict[str, Any],
    *,
    family: str,
    feature_id: str,
    method_id: str,
) -> dict[str, Any]:
    """Overwrite the flat registry-entry-hash fields with the per-component values.

    ``feature_registry_entry_hash`` / ``method_registry_entry_hash`` are keyed by
    ``feature_id`` / ``method_id``; ``data_registry_entry_hash`` is keyed by the
    data generator's stable id for ``family`` (N_AR / N_CIRCLE / CIRCLE_BASED_H1
    are distinct data components).
    """
    registry_map = run_identity.get("registry_entry_hash_map") or {}
    from . import components

    data_stable = components.data_generator_spec(family)["stable_id"]
    resolved = dict(run_identity)
    resolved["feature_registry_entry_hash"] = (
        registry_map.get("feature", {}).get(feature_id)
        or run_identity.get("feature_registry_entry_hash")
    )
    resolved["method_registry_entry_hash"] = (
        registry_map.get("method", {}).get(method_id)
        or run_identity.get("method_registry_entry_hash")
    )
    resolved["data_registry_entry_hash"] = (
        registry_map.get("data", {}).get(data_stable)
        or run_identity.get("data_registry_entry_hash")
    )
    return resolved


def run_formal_h0(
    *,
    manifest: dict[str, Any],
    seed_registry: dict[str, Any],
    workers: int = 1,
    replicate_limit: int | None = None,
    monitor: Any | None = None,
    run_identity: dict[str, Any] | None = None,
) -> FormalResult:
    """Run the H0 NULL phase through the shared work-unit channel."""
    import time

    from .workunit import run_units

    ctx = formal_context(manifest, scope.PHASE_NULL)
    root_keys = formal_root_keys(seed_registry, scope.PHASE_NULL)
    replicates = scope.R0_H0 if replicate_limit is None else replicate_limit
    payloads = [
        {
            "family": family,
            "rho": rho,
            "replicate": replicate,
            "feature_id": feature_id,
            "ctx": ctx,
            "root_keys": root_keys,
            "run_identity": run_identity or {},
        }
        for family in scope.H0_FAMILIES
        for rho in scope.RHO_LEVELS
        for replicate in range(1, replicates + 1)
        for feature_id in scope.FEATURE_IDS
    ]
    start = time.perf_counter()
    dispatch = run_units(payloads, func=process_formal_master_feature,
                         workers=workers, monitor=monitor)
    if not dispatch.is_complete():
        raise FormalPhaseError(
            f"{scope.PHASE_NULL} did not complete: {dispatch.summary()}", dispatch=dispatch
        )
    parts = dispatch.parts
    wall = time.perf_counter() - start
    rows: list[dict[str, Any]] = []
    feature_rows: list[dict[str, Any]] = []
    for part in parts:
        rows.extend(part["rows"])
        feature_rows.extend(part.get("feature_rows", []))
    return FormalResult(
        phase=scope.PHASE_NULL,
        wall_seconds=wall,
        data_units=sum(p["data_units"] for p in parts) // len(scope.FEATURE_IDS),
        evaluation_rows=len(rows),
        ph_windows=sum(p["ph_windows"] for p in parts),
        feature_windows=sum(p["feature_windows"] for p in parts),
        errors=sum(p["errors"] for p in parts),
        rows=rows,
        feature_rows=feature_rows,
    )


def run_formal_h1(
    *,
    manifest: dict[str, Any],
    seed_registry: dict[str, Any],
    workers: int = 1,
    replicate_limit: int | None = None,
    monitor: Any | None = None,
    run_identity: dict[str, Any] | None = None,
) -> FormalResult:
    """Run the H1 ALT phase through the shared work-unit channel."""
    import time

    from .workunit import run_units

    ctx = formal_context(manifest, scope.PHASE_ALT)
    root_keys = formal_root_keys(seed_registry, scope.PHASE_ALT)
    replicates = scope.R0_H1 if replicate_limit is None else replicate_limit
    payloads = [
        {
            "scenario": scenario,
            "rho": rho,
            "replicate": replicate,
            "feature_id": feature_id,
            "ctx": ctx,
            "root_keys": root_keys,
            "run_identity": run_identity or {},
        }
        for scenario in (scope.SCENARIO_ALT_SHAPE, scope.SCENARIO_ALT_MEAN)
        for rho in scope.RHO_LEVELS
        for replicate in range(1, replicates + 1)
        for feature_id in scope.FEATURE_IDS
    ]
    start = time.perf_counter()
    dispatch = run_units(payloads, func=process_formal_alt_feature,
                         workers=workers, monitor=monitor)
    if not dispatch.is_complete():
        raise FormalPhaseError(
            f"{scope.PHASE_ALT} did not complete: {dispatch.summary()}", dispatch=dispatch
        )
    parts = dispatch.parts
    wall = time.perf_counter() - start
    rows: list[dict[str, Any]] = []
    feature_rows: list[dict[str, Any]] = []
    for part in parts:
        rows.extend(part["rows"])
        feature_rows.extend(part.get("feature_rows", []))
    return FormalResult(
        phase=scope.PHASE_ALT,
        wall_seconds=wall,
        data_units=sum(p["data_units"] for p in parts) // len(scope.FEATURE_IDS),
        evaluation_rows=len(rows),
        ph_windows=sum(p["ph_windows"] for p in parts),
        feature_windows=sum(p["feature_windows"] for p in parts),
        errors=sum(p["errors"] for p in parts),
        rows=rows,
        feature_rows=feature_rows,
    )


__all__ = [
    "FORMAL_PHASES",
    "FORMAL_STREAM_FAMILIES",
    "FormalResult",
    "formal_cell_identity",
    "formal_context",
    "formal_data_generation_id",
    "formal_evaluation_identity",
    "formal_experiment_id",
    "formal_identity_chain",
    "formal_root_keys",
    "process_formal_alt_feature",
    "process_formal_master_feature",
    "run_formal_h0",
    "run_formal_h1",
]
