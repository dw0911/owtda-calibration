"""Scope specification and logical identity layer (Plan §15.3, §16.2).

Implements the scope-spec hash, the freeze-id chain, H0/H1 logical-cell
enumeration and the logical data/feature/evaluation keys.  ``SCOPE_SPEC``
objects carry only scientific factors and repeat counts (no derived/freeze
IDs); the frozen ``SCOPE_DESIGN`` CSVs binding ``freeze_id`` are emitted after
the 2026-09-23 freeze (B14), and ``scope_design_rows`` is the deterministic
row builder they consume.

Naming decisions to be reviewed at freeze (flagged in B07 report):
  * NULL-phase ``scenario_id`` = ``"h0"``; ALT-phase scenario ids are
    ``"shape_change"`` / ``"mean_shift"`` (Plan §12);
  * scenario ids never carry budget tags (budget lives in
    ``budget_membership``).
"""

from __future__ import annotations

from dataclasses import dataclass

from . import cells
from .calibrate import M0_STABLE_ID, M1_STABLE_ID
from .canonical import canonical_decimal_text
from .dgp import (
    DGP_FAMILY_H1,
    DGP_FAMILY_N_AR,
    DGP_FAMILY_N_CIRCLE,
    H1_SCENARIO_MEAN,
    H1_SCENARIO_SHAPE,
)
from .features import BPI_STABLE_ID, MOMENTS_STABLE_ID
from .identity import H

PHASE_NULL = "NULL"
PHASE_ALT = "ALT"
PHASE_SMOKE_NULL = "SMOKE_NULL"
PHASE_SMOKE_ALT = "SMOKE_ALT"

SCENARIO_NULL = "h0"
SCENARIO_ALT_SHAPE = H1_SCENARIO_SHAPE
SCENARIO_ALT_MEAN = H1_SCENARIO_MEAN

RHO_LEVELS = ("0", "0.8")
H1_FAMILY = DGP_FAMILY_H1
H0_FAMILIES = (DGP_FAMILY_N_AR, DGP_FAMILY_N_CIRCLE)
H1_GEOMETRIES = (64, 16)  # W=64, M=192, s in {64,16} (Plan §12.1)

FEATURE_IDS = (BPI_STABLE_ID, MOMENTS_STABLE_ID)
METHOD_IDS = (M0_STABLE_ID, M1_STABLE_ID)

R0_H0 = 2500
R0_H1 = 1600
# G3 blind smoke: 32 replicates per cell -> H0 896 data units / 3,584 rows /
# 73,600 PH windows (128 master paths x 575), H1 256 / 1,024 / 49,152 (Plan §9.3).
R0_SMOKE = 32
SMOKE_PHASES = (PHASE_SMOKE_NULL, PHASE_SMOKE_ALT)
# Plan §9.3 umbrella generation: any DGP/feature/method/schema/RNG-consumption/
# runner/reference-environment change bumps this monotonically and forces both
# smoke phases to be re-run, so one generation never spans two implementations.
# S01 was superseded by the B15c H1 DGP addition.
SMOKE_GENERATION_ID = "S02"
SMOKE_GENERATIONS_SUPERSEDED = ("S01",)


def scope_spec_h0() -> dict:
    return {
        "schema_version": 1,
        "config_kind": "scope_spec",
        "phase": PHASE_NULL,
        "synthetic": {
            "DGP_families": sorted(H0_FAMILIES),
            "rho_levels": list(RHO_LEVELS),
            "budget_matrices": {
                "FIXED_M": {"W": cells.W_FIXED, "M": cells.M_FIXED_M},
                "FIXED_T": {"T": cells.T_FIXED_T, "W": cells.W_FIXED},
            },
            "strides": list(cells.STRIDES),
            "features": list(FEATURE_IDS),
            "methods": list(METHOD_IDS),
            "replicate_count": R0_H0,
        },
    }


def scope_spec_h1() -> dict:
    return {
        "schema_version": 1,
        "config_kind": "scope_spec",
        "phase": PHASE_ALT,
        "synthetic": {
            "DGP_family": H1_FAMILY,
            "alternatives": [SCENARIO_ALT_SHAPE, SCENARIO_ALT_MEAN],
            "rho_levels": list(RHO_LEVELS),
            "geometry": {
                "W": cells.W_FIXED,
                "M": cells.M_FIXED_M,
                "strides": list(H1_GEOMETRIES),
            },
            "features": list(FEATURE_IDS),
            "methods": list(METHOD_IDS),
            "replicate_count": R0_H1,
        },
    }


def scope_spec_hash(spec: dict) -> str:
    return H("scope_spec", schema_version=spec["schema_version"], spec=spec)


def freeze_id(
    *,
    project_id: str,
    protocol_id: str,
    protocol_content_hash: str,
    scope_spec_hash: str,
    analysis_spec_hash: str,
    compute_spec_hash: str,
) -> str:
    return H(
        "freeze",
        project_id=project_id,
        protocol_id=protocol_id,
        protocol_content_hash=protocol_content_hash,
        scope_spec_hash=scope_spec_hash,
        analysis_spec_hash=analysis_spec_hash,
        compute_spec_hash=compute_spec_hash,
    )


def experiment_id(
    *,
    project_id: str,
    protocol_id: str,
    freeze_id: str,
    evidence_generation_id: str,
    phase: str,
    scenario_id: str,
) -> str:
    return H(
        "experiment",
        project_id=project_id,
        protocol_id=protocol_id,
        freeze_id=freeze_id,
        evidence_generation_id=evidence_generation_id,
        phase=phase,
        scenario_id=scenario_id,
    )


def logical_cell_id(
    *,
    project_id: str,
    protocol_id: str,
    freeze_id: str,
    evidence_generation_id: str,
    phase: str,
    DGP_family: str,
    scenario_id: str,
    rho: str | float,
    W: int,
    stride: int,
    T: int,
    M: int,
) -> str:
    return H(
        "logical_synthetic_cell",
        project_id=project_id,
        protocol_id=protocol_id,
        freeze_id=freeze_id,
        evidence_generation_id=evidence_generation_id,
        phase=phase,
        DGP_family=DGP_family,
        scenario_id=scenario_id,
        rho=canonical_decimal_text(rho),
        W=W,
        stride=stride,
        T=T,
        M=M,
    )


def logical_data_key(*, logical_cell_id: str, master_replicate_id: str) -> str:
    return H("logical_synthetic_data", logical_cell_id=logical_cell_id,
             master_replicate_id=master_replicate_id)


def logical_feature_key(*, logical_data_key: str, feature_id: str) -> str:
    return H("logical_feature", logical_data_key=logical_data_key, feature_id=feature_id)


def logical_evaluation_key(*, logical_data_key: str, feature_id: str, method_id: str) -> str:
    return H("logical_evaluation", logical_data_key=logical_data_key,
             feature_id=feature_id, method_id=method_id)


@dataclass(frozen=True)
class NullCell:
    """One H0 logical-cell factor combination (family x rho x geometry)."""

    family: str
    rho: str
    stride: int
    T: int
    M: int
    budget_membership: tuple[str, ...]
    W: int = cells.W_FIXED


@dataclass(frozen=True)
class AltCell:
    """One ALT logical-cell factor combination (scenario x rho x stride)."""

    scenario: str
    rho: str
    stride: int
    T: int
    M: int
    W: int = cells.W_FIXED


def h0_null_cells() -> list[NullCell]:
    """28 H0 cells: 7 geometries x 2 DGP x 2 rho."""
    out = []
    for family in H0_FAMILIES:
        for rho in RHO_LEVELS:
            for geom in cells.h0_geometry_cells():
                out.append(
                    NullCell(
                        family=family,
                        rho=rho,
                        stride=geom.stride,
                        T=geom.T,
                        M=geom.M,
                        budget_membership=geom.budget_membership,
                    )
                )
    return out


def h1_alt_cells() -> list[AltCell]:
    """8 ALT cells: 2 alternatives x 2 rho x 2 strides."""
    out = []
    for scenario in (SCENARIO_ALT_SHAPE, SCENARIO_ALT_MEAN):
        for rho in RHO_LEVELS:
            for s in H1_GEOMETRIES:
                out.append(
                    AltCell(scenario=scenario, rho=rho, stride=s,
                            T=cells.fixed_m_raw_length(s), M=cells.M_FIXED_M)
                )
    return out


class _Ctx:
    """Common frozen identity parameters passed through enumeration."""

    def __init__(self, *, project_id, protocol_id, freeze_id,
                 evidence_generation_id):
        self.project_id = project_id
        self.protocol_id = protocol_id
        self.freeze_id = freeze_id
        self.evidence_generation_id = evidence_generation_id

    def cell_id(self, *, phase, DGP_family, scenario_id, rho, W, stride, T, M):
        return logical_cell_id(
            project_id=self.project_id,
            protocol_id=self.protocol_id,
            freeze_id=self.freeze_id,
            evidence_generation_id=self.evidence_generation_id,
            phase=phase,
            DGP_family=DGP_family,
            scenario_id=scenario_id,
            rho=rho,
            W=W,
            stride=stride,
            T=T,
            M=M,
        )

    def experiment(self, *, phase, scenario_id):
        return experiment_id(
            project_id=self.project_id,
            protocol_id=self.protocol_id,
            freeze_id=self.freeze_id,
            evidence_generation_id=self.evidence_generation_id,
            phase=phase,
            scenario_id=scenario_id,
        )


def scope_design_rows(
    *,
    project_id: str,
    protocol_id: str,
    freeze_id: str,
    evidence_generation_id: str,
    phase: str,
    replicate_count: int | None = None,
) -> list[dict]:
    """SCOPE_DESIGN rows (Plan §16.2).

    NULL 112 rows / ALT 32 rows; SMOKE_NULL / SMOKE_ALT share the same cell
    geometry but carry their own phase identity and 128 replicates.  Primary key
    ``(phase, logical_cell_id, feature_id, method_id)`` is unique; every row has
    ``expected_logical_evaluations == replicate_count``.  ALT rows bind
    ``source_null_logical_cell_id`` to the matching N-CIRCLE null cell of the
    same generation (NULL for ALT, SMOKE_NULL for SMOKE_ALT).
    """
    ctx = _Ctx(project_id=project_id, protocol_id=protocol_id,
               freeze_id=freeze_id, evidence_generation_id=evidence_generation_id)
    rows: list[dict] = []
    if phase in (PHASE_NULL, PHASE_SMOKE_NULL):
        count = replicate_count if replicate_count is not None else (
            R0_SMOKE if phase == PHASE_SMOKE_NULL else R0_H0
        )
        for cell in h0_null_cells():
            cell_id = ctx.cell_id(
                phase=phase, DGP_family=cell.family,
                scenario_id=SCENARIO_NULL, rho=cell.rho, W=cell.W,
                stride=cell.stride, T=cell.T, M=cell.M,
            )
            exp_id = ctx.experiment(phase=phase, scenario_id=SCENARIO_NULL)
            for feature in FEATURE_IDS:
                for method in METHOD_IDS:
                    rows.append(
                        {
                            "phase": phase,
                            "experiment_id": exp_id,
                            "logical_cell_id": cell_id,
                            "budget_membership": list(cell.budget_membership),
                            "feature_id": feature,
                            "method_id": method,
                            "replicate_count": count,
                            "expected_logical_evaluations": count,
                            "required": True,
                            "source_null_logical_cell_id": None,
                            "null_model_config_hash": None,
                        }
                    )
    elif phase in (PHASE_ALT, PHASE_SMOKE_ALT):
        count = replicate_count if replicate_count is not None else (
            R0_SMOKE if phase == PHASE_SMOKE_ALT else R0_H1
        )
        source_phase = PHASE_SMOKE_NULL if phase == PHASE_SMOKE_ALT else PHASE_NULL
        for cell in h1_alt_cells():
            cell_id = ctx.cell_id(
                phase=phase, DGP_family=H1_FAMILY,
                scenario_id=cell.scenario, rho=cell.rho, W=cell.W,
                stride=cell.stride, T=cell.T, M=cell.M,
            )
            exp_id = ctx.experiment(phase=phase, scenario_id=cell.scenario)
            src_id = ctx.cell_id(
                phase=source_phase, DGP_family=DGP_FAMILY_N_CIRCLE,
                scenario_id=SCENARIO_NULL, rho=cell.rho, W=cell.W,
                stride=cell.stride, T=cell.T, M=cell.M,
            )
            for feature in FEATURE_IDS:
                for method in METHOD_IDS:
                    rows.append(
                        {
                            "phase": phase,
                            "experiment_id": exp_id,
                            "logical_cell_id": cell_id,
                            "budget_membership": [],
                            "feature_id": feature,
                            "method_id": method,
                            "replicate_count": count,
                            "expected_logical_evaluations": count,
                            "required": True,
                            "source_null_logical_cell_id": src_id,
                            "null_model_config_hash": None,
                        }
                    )
    else:
        raise ValueError(
            f"scope_design_rows supports NULL/ALT/SMOKE_NULL/SMOKE_ALT, got {phase!r}"
        )
    return rows


def scope_counts_summary() -> dict:
    """Contract snapshot for G1/scope tests (Plan §9)."""
    n_h0 = len(h0_null_cells())
    n_h1 = len(h1_alt_cells())
    return {
        "h0_logical_cells": n_h0,
        "h1_logical_cells": n_h1,
        "h0_data_units": n_h0 * R0_H0,
        "h1_data_units": n_h1 * R0_H1,
        "h0_evaluation_rows": n_h0 * len(FEATURE_IDS) * len(METHOD_IDS) * R0_H0,
        "h1_evaluation_rows": n_h1 * len(FEATURE_IDS) * len(METHOD_IDS) * R0_H1,
        "h0_feature_rows": n_h0 * len(FEATURE_IDS) * R0_H0,
        "h1_feature_rows": n_h1 * len(FEATURE_IDS) * R0_H1,
    }


__all__ = [
    "PHASE_NULL",
    "PHASE_ALT",
    "PHASE_SMOKE_NULL",
    "PHASE_SMOKE_ALT",
    "SCENARIO_NULL",
    "SCENARIO_ALT_SHAPE",
    "SCENARIO_ALT_MEAN",
    "RHO_LEVELS",
    "H1_FAMILY",
    "H0_FAMILIES",
    "H1_GEOMETRIES",
    "FEATURE_IDS",
    "METHOD_IDS",
    "R0_H0",
    "R0_H1",
    "R0_SMOKE",
    "SMOKE_PHASES",
    "scope_spec_h0",
    "scope_spec_h1",
    "scope_spec_hash",
    "freeze_id",
    "experiment_id",
    "logical_cell_id",
    "logical_data_key",
    "logical_feature_key",
    "logical_evaluation_key",
    "NullCell",
    "AltCell",
    "h0_null_cells",
    "h1_alt_cells",
    "scope_design_rows",
    "scope_counts_summary",
]
