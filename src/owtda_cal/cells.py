"""H0 cell geometry, window-start map and synthetic IDs (Plan §8, §15.3).

Fixed-M matrix: W=64, M=192, T = W + s*(M-1) = 64 + 191*s.
Fixed-T matrix: T=3120, W=64, M = floor((T-W)/s)+1.
The shared geometry (s=16, T=3120, M=192) is one physical/logical cell with
``budget_membership = ["FIXED_M", "FIXED_T"]``; across the two DGP families and
two rho levels this gives 28 unique H0 cells.  Per transformed master path the
union of raw-window starts is 575 (Plan §8.3).
"""

from __future__ import annotations

from dataclasses import dataclass

from .canonical import canonical_decimal_text
from .identity import H

BUDGET_FIXED_M = "FIXED_M"
BUDGET_FIXED_T = "FIXED_T"

W_FIXED = 64
M_FIXED_M = 192
T_FIXED_T = 3120
STRIDES = (64, 32, 16, 8)
L_MASTER = 12288  # maximum formal prefix length (Plan §7)
L_BURN_IN = 1000
# innovations cover t=-999..12288 -> 12288 + 1000 burn-in innovations
L_LATENT = L_MASTER + L_BURN_IN  # 13288

WINDOW_START_OBJECT = "raw_window_start"


def fixed_m_raw_length(stride: int) -> int:
    """T = W + s*(M-1) for the Fixed-M matrix."""
    return W_FIXED + stride * (M_FIXED_M - 1)


def window_count(T: int, W: int = W_FIXED, stride: int = 1) -> int:
    """M = floor((T-W)/s) + 1 (Plan §3.1)."""
    if T < W:
        raise ValueError(f"T must be >= W: T={T}, W={W}")
    return (T - W) // stride + 1


def fixed_t_window_count(stride: int) -> int:
    return window_count(T_FIXED_T, W_FIXED, stride)


@dataclass(frozen=True)
class CellGeometry:
    """One unique H0 (stride,T,M,budget-membership) geometry."""

    stride: int
    T: int
    M: int
    budget_membership: tuple[str, ...]

    def raw_starts(self) -> list[int]:
        """0-based window start offsets within the raw series (X_1..X_T)."""
        return [(i - 1) * self.stride for i in range(1, self.M + 1)]


def h0_geometry_cells() -> list[CellGeometry]:
    """The 7 unique H0 geometries (budget union applied)."""
    cells: dict[tuple[int, int], set[str]] = {}
    for s in STRIDES:
        cells[(s, fixed_m_raw_length(s))] = {BUDGET_FIXED_M}
    for s in STRIDES:
        m = fixed_t_window_count(s)
        key = (s, T_FIXED_T)
        if key in cells:
            cells[key].add(BUDGET_FIXED_T)
        else:
            cells[key] = {BUDGET_FIXED_T}
        assert window_count(T_FIXED_T, W_FIXED, s) == m
    out = []
    for (s, t), members in sorted(cells.items()):
        m = fixed_t_window_count(s) if t == T_FIXED_T else M_FIXED_M
        out.append(
            CellGeometry(
                stride=s,
                T=t,
                M=m,
                budget_membership=tuple(sorted(members)),
            )
        )
    return out


def unique_window_start_map() -> dict[int, list[str]]:
    """575 unique raw starts -> contributing budget memberships (Plan §8.3).

    The per-master-path union of raw-window starts is exactly the set union of
    the stride-8 fixed-T cell (0..3056 step 8, 383) with the fixed-M stride-32
    cell (0..6112 step 32, 192) and the fixed-M stride-64 cell (0..12224
    step 64, 192).  Distinct count 575; membership is informational
    (FIXED_T when a fixed-T cell uses the start, FIXED_M for fixed-M cells).
    """
    s8 = {(i - 1) * 8 for i in range(1, fixed_t_window_count(8) + 1)}
    s32m = {(i - 1) * 32 for i in range(1, M_FIXED_M + 1)}
    s64m = {(i - 1) * 64 for i in range(1, M_FIXED_M + 1)}
    union = sorted(s8 | s32m | s64m)
    result: dict[int, list[str]] = {}
    for k in union:
        members: set[str] = set()
        if k in s8:
            members.add(BUDGET_FIXED_T)
        if k in s32m or k in s64m:
            members.add(BUDGET_FIXED_M)
        result[k] = sorted(members)
    return result


def verify_h0_counts() -> dict[str, int]:
    """Contract snapshot used by G1 and B04 tests."""
    geom = h0_geometry_cells()
    starts = unique_window_start_map()
    return {
        "unique_geometries": len(geom),
        "geometry_s16_membership": next(
            len(g.budget_membership) for g in geom if g.stride == 16 and g.T == T_FIXED_T
        ),
        "unique_starts": len(starts),
        "fixed_m_cells": sum(1 for g in geom if BUDGET_FIXED_M in g.budget_membership),
        "fixed_t_cells": sum(1 for g in geom if BUDGET_FIXED_T in g.budget_membership),
    }


def physical_cell_id(
    *,
    protocol_id: str,
    freeze_id: str,
    evidence_generation_id: str,
    phase: str,
    rho: str | float,
    W: int,
    stride: int,
    T: int,
    M: int,
    data_model_config_hash: str,
) -> str:
    """physical_cell_id = H("synthetic_physical_cell", ...) (Plan §15.3)."""
    return H(
        "synthetic_physical_cell",
        protocol_id=protocol_id,
        freeze_id=freeze_id,
        evidence_generation_id=evidence_generation_id,
        phase=phase,
        rho=canonical_decimal_text(rho),
        W=W,
        stride=stride,
        T=T,
        M=M,
        data_model_config_hash=data_model_config_hash,
    )


def base_series_id(
    *,
    master_replicate_id: str,
    data_generation_id: str,
    DGP_family: str,
    rho: str | float,
    raw_length: int,
    data_model_config_hash: str,
) -> str:
    return H(
        "synthetic_base_series",
        master_replicate_id=master_replicate_id,
        data_generation_id=data_generation_id,
        DGP_family=DGP_family,
        rho=canonical_decimal_text(rho),
        raw_length=raw_length,
        data_model_config_hash=data_model_config_hash,
    )


def data_unit_id(
    *,
    base_series_id: str,
    physical_cell_id: str,
    data_generation_id: str,
) -> str:
    return H(
        "synthetic_data_unit",
        base_series_id=base_series_id,
        physical_cell_id=physical_cell_id,
        data_generation_id=data_generation_id,
    )


def master_replicate_id(
    *,
    project_id: str,
    protocol_id: str,
    freeze_id: str,
    evidence_generation_id: str,
    phase: str,
    DGP_family: str,
    replicate_id: int,
) -> str:
    return H(
        "master_replicate",
        project_id=project_id,
        protocol_id=protocol_id,
        freeze_id=freeze_id,
        evidence_generation_id=evidence_generation_id,
        phase=phase,
        DGP_family=DGP_family,
        replicate_id=replicate_id,
    )


def cluster_id(*, phase: str, DGP_stratum: str, master_replicate_id: str) -> str:
    return H(
        "cluster",
        phase=phase,
        DGP_stratum=DGP_stratum,
        master_replicate_id=master_replicate_id,
    )


__all__ = [
    "BUDGET_FIXED_M",
    "BUDGET_FIXED_T",
    "W_FIXED",
    "M_FIXED_M",
    "T_FIXED_T",
    "STRIDES",
    "L_MASTER",
    "L_LATENT",
    "CellGeometry",
    "fixed_m_raw_length",
    "window_count",
    "fixed_t_window_count",
    "h0_geometry_cells",
    "unique_window_start_map",
    "verify_h0_counts",
    "physical_cell_id",
    "base_series_id",
    "data_unit_id",
    "master_replicate_id",
    "cluster_id",
]
