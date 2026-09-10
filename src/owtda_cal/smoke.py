"""G3 blind smoke runner (Plan §9.3-§9.4).

SMOKE_NULL: 28 cells x 32 replicates = 896 data units, 3,584 evaluation rows and
128 master paths x 575 unique windows = 73,600 PH windows.

The runner is *blind*: it may report wall time, row/field counts and error
counts, but never rejection rates, method rankings or any aggregate that could
feed parameter selection.  All streams use the phase's ``stream_family=smoke``
root entry with ``smoke_``-prefixed stream kinds, so formal root entries can
never be consumed by a smoke executor.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from . import cells, dgp, scope
from .calibrate import M0_STABLE_ID, M1_STABLE_ID, calibrate_m0, calibrate_m1
from .features import (
    BPI_STABLE_ID,
    MOMENTS_STABLE_ID,
    SCENARIO_N_AR,
    SCENARIO_N_CIRCLE,
    feature_matrix_for_windows,
)

SMOKE_STREAM_PREFIX = "smoke_"
SMOKE_GENERATION_ID = "S01"
SMOKE_METHOD_GENERATION_ID = "S01"
FEATURE_KIND_BY_STABLE = {BPI_STABLE_ID: "bpi", MOMENTS_STABLE_ID: "moments"}
METHOD_BY_KEY = {"M0": (M0_STABLE_ID, calibrate_m0), "M1": (M1_STABLE_ID, calibrate_m1)}
ROW_FIELDS = (
    "phase",
    "logical_cell_id",
    "logical_data_key",
    "logical_feature_key",
    "logical_evaluation_key",
    "data_unit_id",
    "DGP_family",
    "rho",
    "feature_id",
    "method_id",
    "observed_statistic",
    "exceed_count",
    "p_value",
    "reject",
)


@dataclass
class SmokeResult:
    phase: str
    wall_seconds: float
    data_units: int
    evaluation_rows: int
    ph_windows: int
    errors: int
    rows: list[dict[str, Any]] = field(default_factory=list)

    def report(self) -> dict[str, Any]:
        """Blind summary: counts and wall time only (Plan §9.3)."""
        return {
            "phase": self.phase,
            "wall_seconds": self.wall_seconds,
            "data_units": self.data_units,
            "evaluation_rows": self.evaluation_rows,
            "ph_windows": self.ph_windows,
            "errors": self.errors,
            "forbidden_aggregates_emitted": False,
        }


def _scenario(family: str) -> str:
    return SCENARIO_N_AR if family == dgp.DGP_FAMILY_N_AR else SCENARIO_N_CIRCLE


def _data_model_hash(family: str, rho: str) -> str:
    spec = (
        dgp.n_ar_data_model_spec(rho)
        if family == dgp.DGP_FAMILY_N_AR
        else dgp.n_circle_data_model_spec(rho)
    )
    return dgp.data_model_config_hash(spec)


def process_master_feature(payload: dict[str, Any]) -> dict[str, Any]:
    """Worker entry point: one master path x one feature (Plan §9.3).

    One item computes the 575 unique windows of its master path exactly once and
    then calibrates the 7 cells (x M0/M1) that belong to that (family, rho), so
    the union over all items is exactly 128 x 575 = 73,600 unique PH windows.
    """
    family = payload["family"]
    rho = payload["rho"]
    replicate = payload["replicate"]
    feature_id = payload["feature_id"]
    root_key_hex = payload["root_key_hex"]
    ctx = payload["ctx"]
    project_id = ctx["project_id"]
    protocol_id = ctx["protocol_id"]
    freeze_id = ctx["freeze_id"]
    evidence_generation_id = ctx["evidence_generation_id"]
    phase = ctx["phase"]
    starts = ctx["starts"]
    index_of = ctx["index_of"]

    scenario = _scenario(family)
    master_replicate_id = cells.master_replicate_id(
        project_id=project_id,
        protocol_id=protocol_id,
        freeze_id=freeze_id,
        evidence_generation_id=evidence_generation_id,
        phase=phase,
        DGP_family=family,
        replicate_id=replicate,
    )
    data_model_config_hash = _data_model_hash(family, rho)
    master = dgp.generate_null_master(
        family=family,
        rho=rho,
        root_key_hex=root_key_hex,
        data_generation_id=SMOKE_GENERATION_ID,
        master_replicate_id=master_replicate_id,
    )
    # N-AR is univariate: the delay embedding needs a 1-D raw window.
    if family == dgp.DGP_FAMILY_N_AR:
        raw = master.raw_prefix_1d(cells.L_MASTER)
    else:
        raw = master.raw_prefix(cells.L_MASTER)
    windows = [raw[k : k + cells.W_FIXED] for k in starts]
    matrix = feature_matrix_for_windows(
        windows, feature_kind=FEATURE_KIND_BY_STABLE[feature_id], scenario=scenario
    )
    base_series_id = cells.base_series_id(
        master_replicate_id=master_replicate_id,
        data_generation_id=SMOKE_GENERATION_ID,
        DGP_family=family,
        rho=rho,
        raw_length=cells.L_MASTER,
        data_model_config_hash=data_model_config_hash,
    )

    rows: list[dict[str, Any]] = []
    errors = 0
    data_units = 0
    for cell in scope.h0_null_cells():
        if cell.family != family or cell.rho != rho:
            continue
        idx = [index_of[k] for k in [(i - 1) * cell.stride for i in range(1, cell.M + 1)]]
        sub = matrix[idx]
        logical_cell_id = scope.logical_cell_id(
            project_id=project_id,
            protocol_id=protocol_id,
            freeze_id=freeze_id,
            evidence_generation_id=evidence_generation_id,
            phase=phase,
            DGP_family=family,
            scenario_id=scope.SCENARIO_NULL,
            rho=rho,
            W=cell.W,
            stride=cell.stride,
            T=cell.T,
            M=cell.M,
        )
        physical_cell_id = cells.physical_cell_id(
            protocol_id=protocol_id,
            freeze_id=freeze_id,
            evidence_generation_id=evidence_generation_id,
            phase=phase,
            rho=rho,
            W=cell.W,
            stride=cell.stride,
            T=cell.T,
            M=cell.M,
            data_model_config_hash=data_model_config_hash,
        )
        data_unit_id = cells.data_unit_id(
            base_series_id=base_series_id,
            physical_cell_id=physical_cell_id,
            data_generation_id=SMOKE_GENERATION_ID,
        )
        logical_data_key = scope.logical_data_key(
            logical_cell_id=logical_cell_id, master_replicate_id=master_replicate_id
        )
        logical_feature_key = scope.logical_feature_key(
            logical_data_key=logical_data_key, feature_id=feature_id
        )
        data_units += 1
        for method_key, (method_id, _) in METHOD_BY_KEY.items():
            logical_evaluation_key = scope.logical_evaluation_key(
                logical_data_key=logical_data_key,
                feature_id=feature_id,
                method_id=method_id,
            )
            try:
                if method_key == "M0":
                    out = calibrate_m0(
                        sub,
                        root_key_hex=root_key_hex,
                        method_generation_id=SMOKE_METHOD_GENERATION_ID,
                        data_unit_id=data_unit_id,
                        stream_kind=f"{SMOKE_STREAM_PREFIX}M0_permutation",
                    )
                else:
                    out = calibrate_m1(
                        sub,
                        root_key_hex=root_key_hex,
                        method_generation_id=SMOKE_METHOD_GENERATION_ID,
                        data_unit_id=data_unit_id,
                        W=cell.W,
                        stride=cell.stride,
                        stream_kind=f"{SMOKE_STREAM_PREFIX}M1_gaussian_innovation",
                    )
            except Exception:  # noqa: BLE001 - counted, never silently dropped
                errors += 1
                continue
            rows.append(
                {
                    "phase": phase,
                    "logical_cell_id": logical_cell_id,
                    "logical_data_key": logical_data_key,
                    "logical_feature_key": logical_feature_key,
                    "logical_evaluation_key": logical_evaluation_key,
                    "data_unit_id": data_unit_id,
                    "DGP_family": family,
                    "rho": rho,
                    "feature_id": feature_id,
                    "method_id": method_id,
                    "observed_statistic": float(out["observed_statistic"]),
                    "exceed_count": int(out["exceed_count"]),
                    "p_value": float(out["p_value"]),
                    "reject": bool(out["reject"]),
                }
            )
    return {"rows": rows, "errors": errors, "data_units": data_units, "ph_windows": len(starts)}


def smoke_context(manifest: dict[str, Any]) -> dict[str, Any]:
    starts_map = cells.unique_window_start_map()
    starts = sorted(starts_map)
    return {
        "project_id": manifest["project_id"],
        "protocol_id": manifest["protocol_id"],
        "freeze_id": manifest["freeze_id"],
        "evidence_generation_id": manifest["evidence_generation_id"],
        "phase": scope.PHASE_SMOKE_NULL,
        "starts": starts,
        "index_of": {k: i for i, k in enumerate(starts)},
        "geometries": cells.h0_geometry_cells(),
    }


def smoke_root_key(seed_registry: dict[str, Any], phase: str) -> str:
    """The phase's unique ``stream_family=smoke`` root key (Plan §9.3)."""
    matches = [
        entry
        for entry in seed_registry["entries"]
        if entry["phase"] == phase and entry["stream_family"] == "smoke"
    ]
    if len(matches) != 1:
        raise ValueError(f"expected exactly one smoke root entry for {phase!r}")
    key = matches[0].get("root_key_hex")
    if not key:
        raise ValueError(f"smoke root entry for {phase!r} has no plaintext key")
    return key


def run_smoke_null(
    *,
    manifest: dict[str, Any],
    seed_registry: dict[str, Any],
    workers: int = 1,
    replicate_limit: int | None = None,
) -> SmokeResult:
    """Run the H0 blind smoke; returns counts only (never aggregates)."""
    import time

    from .parallel import ordered_map

    ctx = smoke_context(manifest)
    root_key_hex = smoke_root_key(seed_registry, scope.PHASE_SMOKE_NULL)
    replicates = scope.R0_SMOKE if replicate_limit is None else replicate_limit
    payloads = [
        {
            "family": family,
            "rho": rho,
            "replicate": replicate,
            "feature_id": feature_id,
            "ctx": ctx,
            "root_key_hex": root_key_hex,
        }
        for family in scope.H0_FAMILIES
        for rho in scope.RHO_LEVELS
        for replicate in range(replicates)
        for feature_id in scope.FEATURE_IDS
    ]
    start = time.perf_counter()
    parts = ordered_map(process_master_feature, payloads, workers=workers)
    wall = time.perf_counter() - start
    rows: list[dict[str, Any]] = []
    for part in parts:
        rows.extend(part["rows"])
    return SmokeResult(
        phase=scope.PHASE_SMOKE_NULL,
        wall_seconds=wall,
        data_units=sum(p["data_units"] for p in parts) // len(scope.FEATURE_IDS),
        evaluation_rows=len(rows),
        ph_windows=sum(p["ph_windows"] for p in parts) // len(scope.FEATURE_IDS),
        errors=sum(p["errors"] for p in parts),
        rows=rows,
    )


def expected_smoke_counts() -> dict[str, int]:
    """Frozen G3 counts (Plan §9.3)."""
    return {
        "data_units": len(scope.h0_null_cells()) * scope.R0_SMOKE,
        "evaluation_rows": len(scope.h0_null_cells()) * scope.R0_SMOKE * len(scope.FEATURE_IDS) * len(scope.METHOD_IDS),
        "ph_windows": (len(scope.H0_FAMILIES) * len(scope.RHO_LEVELS) * scope.R0_SMOKE)
        * len(cells.unique_window_start_map()),
    }


def assert_row_fields(rows: list[dict[str, Any]]) -> int:
    """Return the number of rows missing a required field."""
    missing = 0
    for row in rows:
        if set(row) != set(ROW_FIELDS):
            missing += 1
    return missing


__all__ = [
    "SMOKE_STREAM_PREFIX",
    "SMOKE_GENERATION_ID",
    "ROW_FIELDS",
    "SmokeResult",
    "process_master_feature",
    "smoke_context",
    "smoke_root_key",
    "run_smoke_null",
    "expected_smoke_counts",
    "assert_row_fields",
]
