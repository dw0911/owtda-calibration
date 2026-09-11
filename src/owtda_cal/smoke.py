"""G3 blind smoke runner (Plan §9.3-§9.4).

SMOKE_NULL: 28 cells x 32 replicates = 896 data units, 3,584 evaluation rows and
128 master paths x 575 unique windows = 73,600 PH windows.
SMOKE_ALT:   8 cells x 32 replicates = 256 data units, 1,024 evaluation rows and
128 master replicates x 2 strides x 192 windows = 49,152 PH windows.

The runner is *blind*: it may report wall time, row/field counts and error
counts, but never rejection rates, method rankings or any aggregate that could
feed parameter selection.

Identity/stream isolation (Plan §9.3, §15.2, §16): smoke artefacts use the
dedicated ``smoke_*`` identity domain from :mod:`owtda_cal.smoke_ids` -- never
the formal ``cells``/``scope`` IDs -- and every stream is consumed from the
phase's ``stream_family=smoke`` root entry with a ``smoke_``-prefixed stream kind
and smoke-only named fields, so formal root entries and formal logical IDs can
never enter a smoke ledger.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from . import cells, dgp, scope, smoke_ids
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
    moments_feature_spec,
)

SMOKE_STREAM_PREFIX = smoke_ids.SMOKE_ID_PREFIX
SMOKE_GENERATION_ID = scope.SMOKE_GENERATION_ID
FEATURE_KIND_BY_STABLE = {BPI_STABLE_ID: "bpi", MOMENTS_STABLE_ID: "moments"}
#: Audit A10: only the BPI feature calls the persistence engine.  Counting both
#: features as "PH windows" inflated PH/s by exactly 2x; the work is reported as
#: ``ph_windows`` (real PH calls) and ``feature_windows`` (all feature work).
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
ROW_FIELDS = (
    "phase",
    "experiment_id",
    "logical_cell_id",
    "logical_data_key",
    "logical_feature_key",
    "logical_evaluation_key",
    "data_unit_id",
    "feature_sufficient_id",
    "evaluation_id",
    "DGP_family",
    "scenario_id",
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
    feature_windows: int = 0
    rows: list[dict[str, Any]] = field(default_factory=list)

    def report(self) -> dict[str, Any]:
        """Blind summary: counts and wall time only (Plan §9.3)."""
        return {
            "phase": self.phase,
            "wall_seconds": self.wall_seconds,
            "data_units": self.data_units,
            "evaluation_rows": self.evaluation_rows,
            "ph_windows": self.ph_windows,
            "feature_windows": self.feature_windows,
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


def _smoke_row(
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


@dataclass(frozen=True)
class ExpectedCell:
    """One expected smoke cell, in the **smoke** identity domain."""

    DGP_family: str
    scenario_id: str
    rho: str
    W: int
    stride: int
    T: int
    M: int
    logical_cell_id: str
    physical_cell_id: str


@dataclass(frozen=True)
class SmokeExpected:
    """The complete expected identity set of one smoke phase (audit A01).

    One traversal produces the SCOPE_DESIGN rows, the expected (ID-only)
    evaluation rows and the runner worklist, so the plan cannot describe a
    different identity domain than the ledger.  Nothing here depends on the
    runner: this is the specification side.
    """

    phase: str
    smoke_generation_id: str
    replicate_count: int
    experiment_id: str
    cells: tuple[ExpectedCell, ...]
    rows: tuple[dict[str, Any], ...]

    def evaluation_ids(self) -> frozenset[str]:
        return frozenset(r["evaluation_id"] for r in self.rows)

    def data_unit_ids(self) -> frozenset[str]:
        return frozenset(r["data_unit_id"] for r in self.rows)

    def feature_sufficient_ids(self) -> frozenset[str]:
        return frozenset(r["feature_sufficient_id"] for r in self.rows)

    def logical_cell_ids(self) -> frozenset[str]:
        return frozenset(r["logical_cell_id"] for r in self.rows)

    def units(self) -> frozenset[tuple[str, int, str, str]]:
        """``(logical_cell_id, replicate_id, feature_id, method_id)`` tuples."""
        return frozenset(
            (r["logical_cell_id"], r["replicate_id"], r["feature_id"], r["method_id"])
            for r in self.rows
        )

    def replicates_per_cell(self) -> dict[str, frozenset[int]]:
        acc: dict[str, set[int]] = {}
        for row in self.rows:
            acc.setdefault(row["logical_cell_id"], set()).add(row["replicate_id"])
        return {key: frozenset(v) for key, v in acc.items()}

    def index(self) -> dict[tuple[Any, ...], dict[str, str]]:
        """Lookup by ``(family, scenario, rho, stride, replicate, feature, method)``."""
        return {
            (
                r["DGP_family"], r["scenario_id"], r["rho"], r["stride"],
                r["replicate_id"], r["feature_id"], r["method_id"],
            ): r
            for r in self.rows
        }


def enumerate_smoke_expected(
    *, ctx: dict[str, Any], replicate_count: int
) -> SmokeExpected:
    """The single source of truth for a smoke phase's expected identities (A01).

    ``ctx`` is the smoke context (project/protocol/freeze/evidence ids, the active
    ``smoke_generation_id``, the phase and its experiment id).  Replicates are
    numbered ``1..replicate_count`` (Plan §9.3, audit A02).
    """
    phase = ctx["phase"]
    gen = ctx["smoke_generation_id"]
    if phase not in scope.SMOKE_PHASES:
        raise ValueError(f"not a smoke phase: {phase!r}")
    if replicate_count < 1:
        raise ValueError("replicate_count must be >= 1")
    common = {
        "project_id": ctx["project_id"],
        "protocol_id": ctx["protocol_id"],
        "freeze_id": ctx["freeze_id"],
        "evidence_generation_id": ctx["evidence_generation_id"],
        "smoke_generation_id": gen,
        "phase": phase,
    }
    experiment_id = ctx["experiment_id"]
    cell_by_key: dict[tuple[Any, ...], ExpectedCell] = {}
    rows: list[dict[str, Any]] = []

    def cell_for(
        *, DGP_family: str, scenario_id: str, rho: str, W: int, stride: int, T: int,
        M: int, data_model_config_hash: str,
    ) -> ExpectedCell:
        key = (DGP_family, scenario_id, rho, W, stride, T, M)
        cell = cell_by_key.get(key)
        if cell is None:
            cell = ExpectedCell(
                DGP_family=DGP_family, scenario_id=scenario_id, rho=rho, W=W,
                stride=stride, T=T, M=M,
                logical_cell_id=smoke_ids.smoke_logical_cell_id(
                    smoke_experiment_id=experiment_id, smoke_generation_id=gen,
                    DGP_family=DGP_family, scenario_id=scenario_id, rho=rho, W=W,
                    stride=stride, T=T, M=M,
                ),
                physical_cell_id=smoke_ids.smoke_physical_cell_id(
                    **common, DGP_family=DGP_family, rho=rho, W=W, stride=stride,
                    T=T, M=M, data_model_config_hash=data_model_config_hash,
                ),
            )
            cell_by_key[key] = cell
        return cell

    def rows_for(
        cell: ExpectedCell, *, replicate: int, base_series_id: str,
        master_replicate_id: str,
    ) -> None:
        data_unit_id = smoke_ids.smoke_data_unit_id(
            smoke_base_series_id=base_series_id,
            smoke_physical_cell_id=cell.physical_cell_id,
            smoke_generation_id=gen,
        )
        logical_data_key = smoke_ids.smoke_logical_data_key(
            smoke_generation_id=gen, smoke_logical_cell_id=cell.logical_cell_id,
            smoke_master_replicate_id=master_replicate_id,
        )
        for feature_id in scope.FEATURE_IDS:
            logical_feature_key = smoke_ids.smoke_logical_feature_key(
                smoke_generation_id=gen, smoke_logical_data_key=logical_data_key,
                feature_id=feature_id,
            )
            feature_sufficient_id = smoke_ids.smoke_feature_sufficient_id(
                smoke_generation_id=gen, smoke_data_unit_id=data_unit_id,
                feature_id=feature_id,
                feature_config_hash=FEATURE_CONFIG_HASH_BY_STABLE[feature_id],
            )
            for method_key in ("M0", "M1"):
                method_id = METHOD_BY_KEY[method_key][0]
                rows.append({
                    "phase": phase,
                    "smoke_generation_id": gen,
                    "experiment_id": experiment_id,
                    "logical_cell_id": cell.logical_cell_id,
                    "physical_cell_id": cell.physical_cell_id,
                    "logical_data_key": logical_data_key,
                    "logical_feature_key": logical_feature_key,
                    "logical_evaluation_key": smoke_ids.smoke_logical_evaluation_key(
                        smoke_generation_id=gen,
                        smoke_logical_data_key=logical_data_key,
                        feature_id=feature_id, method_id=method_id,
                    ),
                    "data_unit_id": data_unit_id,
                    "feature_sufficient_id": feature_sufficient_id,
                    "evaluation_id": smoke_ids.smoke_evaluation_id(
                        smoke_generation_id=gen, smoke_data_unit_id=data_unit_id,
                        smoke_feature_sufficient_id=feature_sufficient_id,
                        method_id=method_id,
                        method_config_hash=METHOD_CONFIG_HASH_BY_KEY[method_key],
                    ),
                    "DGP_family": cell.DGP_family,
                    "scenario_id": cell.scenario_id,
                    "rho": cell.rho,
                    "replicate_id": replicate,
                    "W": cell.W,
                    "stride": cell.stride,
                    "T": cell.T,
                    "M": cell.M,
                    "feature_id": feature_id,
                    "method_id": method_id,
                })

    if phase == scope.PHASE_SMOKE_NULL:
        for family in scope.H0_FAMILIES:
            for rho in scope.RHO_LEVELS:
                dmh = _data_model_hash(family, rho)
                for replicate in range(1, replicate_count + 1):
                    master_replicate_id = smoke_ids.smoke_master_replicate_id(
                        **common, DGP_family=family, replicate_id=replicate
                    )
                    base_series_id = smoke_ids.smoke_base_series_id(
                        smoke_master_replicate_id=master_replicate_id,
                        smoke_generation_id=gen, rho=rho,
                        raw_length=cells.L_MASTER, data_model_config_hash=dmh,
                    )
                    for h0_cell in scope.h0_null_cells():
                        if h0_cell.family != family or h0_cell.rho != rho:
                            continue
                        cell = cell_for(
                            DGP_family=family, scenario_id=scope.SCENARIO_NULL,
                            rho=rho, W=h0_cell.W, stride=h0_cell.stride,
                            T=h0_cell.T, M=h0_cell.M, data_model_config_hash=dmh,
                        )
                        rows_for(
                            cell, replicate=replicate,
                            base_series_id=base_series_id,
                            master_replicate_id=master_replicate_id,
                        )
    else:
        for cell_def in scope.h1_alt_cells():
            dmh = dgp.data_model_config_hash(
                dgp.h1_data_model_spec(cell_def.scenario, cell_def.rho)
            )
            for replicate in range(1, replicate_count + 1):
                master_replicate_id = smoke_ids.smoke_master_replicate_id(
                    **common, DGP_family=dgp.DGP_FAMILY_H1, replicate_id=replicate
                )
                base_series_id = smoke_ids.smoke_base_series_id(
                    smoke_master_replicate_id=master_replicate_id,
                    smoke_generation_id=gen, rho=cell_def.rho,
                    raw_length=cell_def.T, data_model_config_hash=dmh,
                )
                cell = cell_for(
                    DGP_family=dgp.DGP_FAMILY_H1, scenario_id=cell_def.scenario,
                    rho=cell_def.rho, W=cell_def.W, stride=cell_def.stride,
                    T=cell_def.T, M=cell_def.M, data_model_config_hash=dmh,
                )
                rows_for(
                    cell, replicate=replicate, base_series_id=base_series_id,
                    master_replicate_id=master_replicate_id,
                )

    ordered = tuple(
        sorted(cell_by_key.values(), key=lambda c: (c.DGP_family, c.scenario_id, c.rho, c.stride))
    )
    return SmokeExpected(
        phase=phase, smoke_generation_id=gen, replicate_count=replicate_count,
        experiment_id=experiment_id, cells=ordered,
        rows=tuple(sorted(rows, key=lambda r: (
            r["logical_cell_id"], r["replicate_id"], r["feature_id"], r["method_id"],
        ))),
    )


def smoke_scope_rows(
    *,
    project_id: str,
    protocol_id: str,
    freeze_id: str,
    evidence_generation_id: str,
    smoke_generation_id: str,
    phase: str,
    replicate_count: int,
) -> list[dict[str, Any]]:
    """SCOPE_DESIGN rows for a smoke phase, in the **smoke** identity domain (A01).

    The smoke scope must be generated from the same domain as the ledger; the
    previous formal-domain rows shared no cell/experiment id with the executed
    rows, so the seal could not connect plan and execution.
    """
    ctx = {
        "project_id": project_id, "protocol_id": protocol_id, "freeze_id": freeze_id,
        "evidence_generation_id": evidence_generation_id,
        "smoke_generation_id": smoke_generation_id, "phase": phase,
        "experiment_id": smoke_ids.smoke_experiment_id(
            project_id=project_id, protocol_id=protocol_id, freeze_id=freeze_id,
            evidence_generation_id=evidence_generation_id,
            smoke_generation_id=smoke_generation_id, phase=phase,
        ),
    }
    expected = enumerate_smoke_expected(ctx=ctx, replicate_count=replicate_count)
    by_cell: dict[str, dict[str, Any]] = {}
    for row in expected.rows:
        entry = by_cell.setdefault(row["logical_cell_id"], {
            "phase": phase,
            "experiment_id": row["experiment_id"],
            "logical_cell_id": row["logical_cell_id"],
            "budget_membership": [],
            "feature_id": row["feature_id"],
            "method_id": row["method_id"],
            "replicate_count": replicate_count,
            "expected_logical_evaluations": replicate_count,
            "required": True,
            "source_null_logical_cell_id": None,
            "null_model_config_hash": None,
            "_features": set(),
            "_methods": set(),
        })
        entry["_features"].add(row["feature_id"])
        entry["_methods"].add(row["method_id"])
    out: list[dict[str, Any]] = []
    for cell_id in sorted(by_cell):
        base = by_cell[cell_id]
        features = sorted(base.pop("_features"))
        methods = sorted(base.pop("_methods"))
        for feature_id in features:
            for method_id in methods:
                out.append({**base, "feature_id": feature_id, "method_id": method_id})
    return out


#: Identity fields a smoke ledger row must agree on with the expectation.
SMOKE_IDENTITY_FIELDS = (
    "phase",
    "smoke_generation_id",
    "experiment_id",
    "logical_cell_id",
    "logical_data_key",
    "logical_feature_key",
    "logical_evaluation_key",
    "data_unit_id",
    "feature_sufficient_id",
    "DGP_family",
    "scenario_id",
    "rho",
    "feature_id",
    "method_id",
)


def assert_smoke_ledger_matches_expected(
    *,
    ctx: dict[str, Any],
    replicate_count: int,
    ledger_rows: list[dict[str, Any]],
) -> dict[str, Any]:
    """Fail closed unless the ledger is exactly the expected identity set (A01/A05).

    Two independent checks, neither of which can be satisfied by a count:

    1. **set equality** of the evaluation ids built from the specification;
    2. **row-by-row foreign keys** — every other identity field of every ledger row
       must equal the expected row's value (looked up by evaluation id).

    The expectation comes from :func:`enumerate_smoke_expected`, i.e. from the
    frozen specification, never from a runner-produced ID column.  A 0-based
    replicate numbering is rejected by the same equality (its ids are disjoint).
    """
    expected = enumerate_smoke_expected(ctx=ctx, replicate_count=replicate_count)
    expected_ids = expected.evaluation_ids()
    actual_ids = {row["evaluation_id"] for row in ledger_rows}
    if actual_ids != expected_ids:
        missing = sorted(expected_ids - actual_ids)[:3]
        unexpected = sorted(actual_ids - expected_ids)[:3]
        raise ValueError(
            "smoke ledger does not match the expected identity set: "
            f"missing={missing} unexpected={unexpected} "
            f"(expected {len(expected_ids)}, got {len(actual_ids)})"
        )
    by_id = {row["evaluation_id"]: row for row in expected.rows}
    for row in ledger_rows:
        reference = by_id[row["evaluation_id"]]
        for name in SMOKE_IDENTITY_FIELDS:
            if row.get(name) != reference[name]:
                raise ValueError(
                    f"identity mismatch in {name!r} for evaluation "
                    f"{row['evaluation_id'][:12]}: {row.get(name)!r} != "
                    f"{reference[name]!r}"
                )
    per_cell = expected.replicates_per_cell()
    wanted = frozenset(range(1, replicate_count + 1))
    bad = {cell: sorted(v) for cell, v in per_cell.items() if v != wanted}
    if bad:
        raise ValueError(f"replicate numbering is not 1..{replicate_count}: {bad}")
    return {
        "phase": ctx["phase"],
        "smoke_generation_id": ctx["smoke_generation_id"],
        "evaluation_rows": len(ledger_rows),
        "cells": len(per_cell),
        "replicate_count": replicate_count,
        "data_units": len(expected.data_unit_ids()),
        "feature_sufficient_ids": len(expected.feature_sufficient_ids()),
    }


def process_master_feature(payload: dict[str, Any]) -> dict[str, Any]:
    """Worker entry point: one H0 master path x one feature (Plan §9.3).

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
    phase = ctx["phase"]
    smoke_generation_id = ctx["smoke_generation_id"]
    starts = ctx["starts"]
    index_of = ctx["index_of"]

    scenario = _scenario(family)
    experiment_id = ctx["experiment_id"]
    master_replicate_id = smoke_ids.smoke_master_replicate_id(
        project_id=ctx["project_id"],
        protocol_id=ctx["protocol_id"],
        freeze_id=ctx["freeze_id"],
        evidence_generation_id=ctx["evidence_generation_id"],
        smoke_generation_id=smoke_generation_id,
        phase=phase,
        DGP_family=family,
        replicate_id=replicate,
    )
    data_model_config_hash = _data_model_hash(family, rho)
    master = dgp.generate_null_master(
        family=family,
        rho=rho,
        root_key_hex=root_key_hex,
        data_generation_id=smoke_generation_id,
        master_replicate_id=master_replicate_id,
        stream_prefix=SMOKE_STREAM_PREFIX,
        stream_fields=smoke_ids.smoke_data_stream_fields(
            smoke_generation_id=smoke_generation_id,
            phase=phase,
            DGP_family=family,
            replicate_id=replicate,
        ),
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
    base_series_id = smoke_ids.smoke_base_series_id(
        smoke_master_replicate_id=master_replicate_id,
        smoke_generation_id=smoke_generation_id,
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
        logical_cell_id = smoke_ids.smoke_logical_cell_id(
            smoke_experiment_id=experiment_id,
            smoke_generation_id=smoke_generation_id,
            DGP_family=family,
            scenario_id=scope.SCENARIO_NULL,
            rho=rho,
            W=cell.W,
            stride=cell.stride,
            T=cell.T,
            M=cell.M,
        )
        physical_cell_id = smoke_ids.smoke_physical_cell_id(
            project_id=ctx["project_id"],
            protocol_id=ctx["protocol_id"],
            freeze_id=ctx["freeze_id"],
            evidence_generation_id=ctx["evidence_generation_id"],
            smoke_generation_id=smoke_generation_id,
            phase=phase,
            DGP_family=family,
            rho=rho,
            W=cell.W,
            stride=cell.stride,
            T=cell.T,
            M=cell.M,
            data_model_config_hash=data_model_config_hash,
        )
        data_unit_id = smoke_ids.smoke_data_unit_id(
            smoke_base_series_id=base_series_id,
            smoke_physical_cell_id=physical_cell_id,
            smoke_generation_id=smoke_generation_id,
        )
        logical_data_key = smoke_ids.smoke_logical_data_key(
            smoke_generation_id=smoke_generation_id,
            smoke_logical_cell_id=logical_cell_id,
            smoke_master_replicate_id=master_replicate_id,
        )
        logical_feature_key = smoke_ids.smoke_logical_feature_key(
            smoke_generation_id=smoke_generation_id,
            smoke_logical_data_key=logical_data_key,
            feature_id=feature_id,
        )
        feature_sufficient_id = smoke_ids.smoke_feature_sufficient_id(
            smoke_generation_id=smoke_generation_id,
            smoke_data_unit_id=data_unit_id,
            feature_id=feature_id,
            feature_config_hash=FEATURE_CONFIG_HASH_BY_STABLE[feature_id],
        )
        stream_fields = smoke_ids.smoke_method_stream_fields(
            smoke_generation_id=smoke_generation_id,
            phase=phase,
            smoke_data_unit_id=data_unit_id,
        )
        data_units += 1
        for method_key, (method_id, _) in METHOD_BY_KEY.items():
            logical_evaluation_key = smoke_ids.smoke_logical_evaluation_key(
                smoke_generation_id=smoke_generation_id,
                smoke_logical_data_key=logical_data_key,
                feature_id=feature_id,
                method_id=method_id,
            )
            evaluation_id = smoke_ids.smoke_evaluation_id(
                smoke_generation_id=smoke_generation_id,
                smoke_data_unit_id=data_unit_id,
                smoke_feature_sufficient_id=feature_sufficient_id,
                method_id=method_id,
                method_config_hash=METHOD_CONFIG_HASH_BY_KEY[method_key],
            )
            try:
                if method_key == "M0":
                    out = calibrate_m0(
                        sub,
                        root_key_hex=root_key_hex,
                        stream_kind=f"{SMOKE_STREAM_PREFIX}M0_permutation",
                        stream_fields=stream_fields,
                    )
                else:
                    out = calibrate_m1(
                        sub,
                        root_key_hex=root_key_hex,
                        W=cell.W,
                        stride=cell.stride,
                        stream_kind=f"{SMOKE_STREAM_PREFIX}M1_gaussian_innovation",
                        stream_fields=stream_fields,
                    )
            except Exception:  # noqa: BLE001 - counted, never silently dropped
                errors += 1
                continue
            rows.append(
                _smoke_row(
                    ctx=ctx,
                    experiment_id=experiment_id,
                    logical_cell_id=logical_cell_id,
                    logical_data_key=logical_data_key,
                    logical_feature_key=logical_feature_key,
                    logical_evaluation_key=logical_evaluation_key,
                    data_unit_id=data_unit_id,
                    feature_sufficient_id=feature_sufficient_id,
                    evaluation_id=evaluation_id,
                    DGP_family=family,
                    scenario_id=scope.SCENARIO_NULL,
                    rho=rho,
                    feature_id=feature_id,
                    method_id=method_id,
                    out=out,
                )
            )
    return {
        "rows": rows,
        "errors": errors,
        "data_units": data_units,
        # A10: only the BPI feature actually runs the persistence engine.
        "ph_windows": len(starts) if FEATURE_USES_PH[feature_id] else 0,
        "feature_windows": len(starts),
    }


def process_alt_feature(payload: dict[str, Any]) -> dict[str, Any]:
    """Worker entry point: one H1 alternative replicate x one feature (Plan §9.3).

    One item generates the shared latent/noise draws of one (scenario, rho,
    replicate) exactly once and calibrates the two strides (x M0/M1); the change
    point ``tau = floor(T/2)`` is applied per cell, so no window cache is shared
    across the two H1 strides (Plan §9.2).
    """
    scenario = payload["scenario"]
    rho = payload["rho"]
    replicate = payload["replicate"]
    feature_id = payload["feature_id"]
    root_key_hex = payload["root_key_hex"]
    ctx = payload["ctx"]
    phase = ctx["phase"]
    smoke_generation_id = ctx["smoke_generation_id"]
    family = dgp.DGP_FAMILY_H1

    experiment_id = ctx["experiment_id"]
    master_replicate_id = smoke_ids.smoke_master_replicate_id(
        project_id=ctx["project_id"],
        protocol_id=ctx["protocol_id"],
        freeze_id=ctx["freeze_id"],
        evidence_generation_id=ctx["evidence_generation_id"],
        smoke_generation_id=smoke_generation_id,
        phase=phase,
        DGP_family=family,
        replicate_id=replicate,
    )
    master = dgp.generate_h1_master(
        scenario=scenario,
        rho=rho,
        root_key_hex=root_key_hex,
        data_generation_id=smoke_generation_id,
        master_replicate_id=master_replicate_id,
        stream_prefix=SMOKE_STREAM_PREFIX,
        stream_fields=smoke_ids.smoke_data_stream_fields(
            smoke_generation_id=smoke_generation_id,
            phase=phase,
            DGP_family=family,
            replicate_id=replicate,
        ),
    )
    data_model_config_hash = dgp.data_model_config_hash(
        dgp.h1_data_model_spec(scenario, rho)
    )
    raw_cache: dict[int, Any] = {}
    rows: list[dict[str, Any]] = []
    errors = 0
    data_units = 0
    ph_windows = 0
    feature_windows = 0
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
        base_series_id = smoke_ids.smoke_base_series_id(
            smoke_master_replicate_id=master_replicate_id,
            smoke_generation_id=smoke_generation_id,
            rho=rho,
            raw_length=cell.T,
            data_model_config_hash=data_model_config_hash,
        )
        logical_cell_id = smoke_ids.smoke_logical_cell_id(
            smoke_experiment_id=experiment_id,
            smoke_generation_id=smoke_generation_id,
            DGP_family=family,
            scenario_id=cell.scenario,
            rho=rho,
            W=cell.W,
            stride=cell.stride,
            T=cell.T,
            M=cell.M,
        )
        physical_cell_id = smoke_ids.smoke_physical_cell_id(
            project_id=ctx["project_id"],
            protocol_id=ctx["protocol_id"],
            freeze_id=ctx["freeze_id"],
            evidence_generation_id=ctx["evidence_generation_id"],
            smoke_generation_id=smoke_generation_id,
            phase=phase,
            DGP_family=family,
            rho=rho,
            W=cell.W,
            stride=cell.stride,
            T=cell.T,
            M=cell.M,
            data_model_config_hash=data_model_config_hash,
        )
        data_unit_id = smoke_ids.smoke_data_unit_id(
            smoke_base_series_id=base_series_id,
            smoke_physical_cell_id=physical_cell_id,
            smoke_generation_id=smoke_generation_id,
        )
        logical_data_key = smoke_ids.smoke_logical_data_key(
            smoke_generation_id=smoke_generation_id,
            smoke_logical_cell_id=logical_cell_id,
            smoke_master_replicate_id=master_replicate_id,
        )
        logical_feature_key = smoke_ids.smoke_logical_feature_key(
            smoke_generation_id=smoke_generation_id,
            smoke_logical_data_key=logical_data_key,
            feature_id=feature_id,
        )
        feature_sufficient_id = smoke_ids.smoke_feature_sufficient_id(
            smoke_generation_id=smoke_generation_id,
            smoke_data_unit_id=data_unit_id,
            feature_id=feature_id,
            feature_config_hash=FEATURE_CONFIG_HASH_BY_STABLE[feature_id],
        )
        stream_fields = smoke_ids.smoke_method_stream_fields(
            smoke_generation_id=smoke_generation_id,
            phase=phase,
            smoke_data_unit_id=data_unit_id,
        )
        data_units += 1
        for method_key, (method_id, _) in METHOD_BY_KEY.items():
            logical_evaluation_key = smoke_ids.smoke_logical_evaluation_key(
                smoke_generation_id=smoke_generation_id,
                smoke_logical_data_key=logical_data_key,
                feature_id=feature_id,
                method_id=method_id,
            )
            evaluation_id = smoke_ids.smoke_evaluation_id(
                smoke_generation_id=smoke_generation_id,
                smoke_data_unit_id=data_unit_id,
                smoke_feature_sufficient_id=feature_sufficient_id,
                method_id=method_id,
                method_config_hash=METHOD_CONFIG_HASH_BY_KEY[method_key],
            )
            try:
                if method_key == "M0":
                    out = calibrate_m0(
                        matrix,
                        root_key_hex=root_key_hex,
                        stream_kind=f"{SMOKE_STREAM_PREFIX}M0_permutation",
                        stream_fields=stream_fields,
                    )
                else:
                    out = calibrate_m1(
                        matrix,
                        root_key_hex=root_key_hex,
                        W=cell.W,
                        stride=cell.stride,
                        stream_kind=f"{SMOKE_STREAM_PREFIX}M1_gaussian_innovation",
                        stream_fields=stream_fields,
                    )
            except Exception:  # noqa: BLE001 - counted, never silently dropped
                errors += 1
                continue
            rows.append(
                _smoke_row(
                    ctx=ctx,
                    experiment_id=experiment_id,
                    logical_cell_id=logical_cell_id,
                    logical_data_key=logical_data_key,
                    logical_feature_key=logical_feature_key,
                    logical_evaluation_key=logical_evaluation_key,
                    data_unit_id=data_unit_id,
                    feature_sufficient_id=feature_sufficient_id,
                    evaluation_id=evaluation_id,
                    DGP_family=family,
                    scenario_id=cell.scenario,
                    rho=rho,
                    feature_id=feature_id,
                    method_id=method_id,
                    out=out,
                )
            )
    return {
        "rows": rows,
        "errors": errors,
        "data_units": data_units,
        "ph_windows": ph_windows,
        "feature_windows": feature_windows,
    }


def smoke_context(
    manifest: dict[str, Any], phase: str = scope.PHASE_SMOKE_NULL
) -> dict[str, Any]:
    if phase not in scope.SMOKE_PHASES:
        raise ValueError(f"unknown smoke phase {phase!r}")
    ctx: dict[str, Any] = {
        "project_id": manifest["project_id"],
        "protocol_id": manifest["protocol_id"],
        "freeze_id": manifest["freeze_id"],
        "evidence_generation_id": manifest["evidence_generation_id"],
        "smoke_generation_id": SMOKE_GENERATION_ID,
        "phase": phase,
        "experiment_id": smoke_ids.smoke_experiment_id(
            project_id=manifest["project_id"],
            protocol_id=manifest["protocol_id"],
            freeze_id=manifest["freeze_id"],
            evidence_generation_id=manifest["evidence_generation_id"],
            smoke_generation_id=SMOKE_GENERATION_ID,
            phase=phase,
        ),
    }
    if phase == scope.PHASE_SMOKE_NULL:
        starts = sorted(cells.unique_window_start_map())
        ctx["starts"] = starts
        ctx["index_of"] = {k: i for i, k in enumerate(starts)}
    return ctx


def smoke_root_key(seed_registry: dict[str, Any], phase: str) -> str:
    """The phase's unique ``stream_family=smoke`` root key (Plan §9.3).

    The entry's ``component_generation_id`` must equal the active
    ``smoke_generation_id``: a stale registry is rejected instead of silently
    mixing two smoke implementations in one generation.
    """
    matches = [
        entry
        for entry in seed_registry["entries"]
        if entry["phase"] == phase and entry["stream_family"] == smoke_ids.SMOKE_STREAM_FAMILY
    ]
    if len(matches) != 1:
        raise ValueError(f"expected exactly one smoke root entry for {phase!r}")
    entry = matches[0]
    if entry.get("component_generation_id") != SMOKE_GENERATION_ID:
        raise ValueError(
            f"smoke root entry for {phase!r} carries generation "
            f"{entry.get('component_generation_id')!r}, expected {SMOKE_GENERATION_ID!r}"
        )
    key = entry.get("root_key_hex")
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

    ctx = smoke_context(manifest, scope.PHASE_SMOKE_NULL)
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
        # Audit A02: Plan §9.3 numbers smoke replicates 1..R, and the replicate id
        # feeds both the seed payload and the derived identities, so a 0-based
        # loop produced a worklist disjoint from the protocol's expectation.
        for replicate in range(1, replicates + 1)
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
        # A10: each part already reports real PH work only (no feature division),
        # and the all-feature work is reported separately.
        ph_windows=sum(p["ph_windows"] for p in parts),
        feature_windows=sum(p["feature_windows"] for p in parts),
        errors=sum(p["errors"] for p in parts),
        rows=rows,
    )


def run_smoke_alt(
    *,
    manifest: dict[str, Any],
    seed_registry: dict[str, Any],
    workers: int = 1,
    replicate_limit: int | None = None,
) -> SmokeResult:
    """Run the H1 blind smoke; returns counts only (never aggregates)."""
    import time

    from .parallel import ordered_map

    ctx = smoke_context(manifest, scope.PHASE_SMOKE_ALT)
    root_key_hex = smoke_root_key(seed_registry, scope.PHASE_SMOKE_ALT)
    replicates = scope.R0_SMOKE if replicate_limit is None else replicate_limit
    payloads = [
        {
            "scenario": scenario,
            "rho": rho,
            "replicate": replicate,
            "feature_id": feature_id,
            "ctx": ctx,
            "root_key_hex": root_key_hex,
        }
        for scenario in (scope.SCENARIO_ALT_SHAPE, scope.SCENARIO_ALT_MEAN)
        for rho in scope.RHO_LEVELS
        # Audit A02: replicates are numbered 1..R (see the NULL builder).
        for replicate in range(1, replicates + 1)
        for feature_id in scope.FEATURE_IDS
    ]
    start = time.perf_counter()
    parts = ordered_map(process_alt_feature, payloads, workers=workers)
    wall = time.perf_counter() - start
    rows: list[dict[str, Any]] = []
    for part in parts:
        rows.extend(part["rows"])
    return SmokeResult(
        phase=scope.PHASE_SMOKE_ALT,
        wall_seconds=wall,
        data_units=sum(p["data_units"] for p in parts) // len(scope.FEATURE_IDS),
        evaluation_rows=len(rows),
        # A10: each part already reports real PH work only (no feature division),
        # and the all-feature work is reported separately.
        ph_windows=sum(p["ph_windows"] for p in parts),
        feature_windows=sum(p["feature_windows"] for p in parts),
        errors=sum(p["errors"] for p in parts),
        rows=rows,
    )


def expected_smoke_counts(phase: str = scope.PHASE_SMOKE_NULL) -> dict[str, int]:
    """Frozen G3 counts (Plan §9.3)."""
    if phase == scope.PHASE_SMOKE_NULL:
        cells_n = len(scope.h0_null_cells())
        ph_windows = (
            len(scope.H0_FAMILIES) * len(scope.RHO_LEVELS) * scope.R0_SMOKE
        ) * len(cells.unique_window_start_map())
    elif phase == scope.PHASE_SMOKE_ALT:
        cells_n = len(scope.h1_alt_cells())
        ph_windows = (
            len(dgp.H1_SCENARIOS) * len(scope.RHO_LEVELS) * scope.R0_SMOKE
        ) * (len(scope.H1_GEOMETRIES) * cells.M_FIXED_M)
    else:
        raise ValueError(f"unknown smoke phase {phase!r}")
    return {
        "data_units": cells_n * scope.R0_SMOKE,
        "evaluation_rows": cells_n
        * scope.R0_SMOKE
        * len(scope.FEATURE_IDS)
        * len(scope.METHOD_IDS),
        "ph_windows": ph_windows,
        # A10: the all-feature window work (both features process the same windows).
        "feature_windows": ph_windows * len(scope.FEATURE_IDS),
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
    "FEATURE_KIND_BY_STABLE",
    "SmokeResult",
    "ExpectedCell",
    "SmokeExpected",
    "enumerate_smoke_expected",
    "smoke_scope_rows",
    "process_master_feature",
    "process_alt_feature",
    "smoke_context",
    "smoke_root_key",
    "run_smoke_null",
    "run_smoke_alt",
    "expected_smoke_counts",
    "assert_row_fields",
]
