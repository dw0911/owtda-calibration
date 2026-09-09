"""Feature specs, config hashes and feature matrix computation (Plan §5, §10).

Scenario-level frozen coordinate scales (Plan §5.2/§5.3):
  * BPI coordinate cap c: N-AR delay cloud 6.0; N-CIRCLE / figure-eight 2.5;
    PAMAP2 chest acceleration 6 g.
  * MOMENTS scale a: N-AR/N-CIRCLE 1.0; PAMAP2 6 g.

The ``stable_id`` is unique per frozen parameter set; scenario scale is a
compute-time argument supplied by the data family (its effect is captured in
the resulting feature vectors / matrix hashes).
"""

from __future__ import annotations

from typing import Literal

import numpy as np

from . import bpi, moments, ph, pointcloud
from .identity import config_hash

FeatureKind = Literal["bpi", "moments"]
Scenario = Literal["N_AR", "N_CIRCLE", "PAMAP2"]

SCENARIO_N_AR = "N_AR"
SCENARIO_N_CIRCLE = "N_CIRCLE"
SCENARIO_PAMAP2 = "PAMAP2"

BPI_STABLE_ID = "BPI_FIXED20_H01_SIGMA005_GAMMA1_V1"
MOMENTS_STABLE_ID = "MOMENTS_MEAN_COV_FROB_V1"

MATRIX_OBJECT_KIND = "window_feature_matrix_v1"
SUFFICIENT_OBJECT_KIND = "feature_sufficient_vector_v1"


def bpi_feature_spec() -> dict:
    return {
        "schema_version": 1,
        "config_kind": "feature",
        "stable_id": BPI_STABLE_ID,
        "feature_kind": "bpi",
        "generator_version": "V1",
        "grid_rows": bpi.N_GRID,
        "grid_cols": bpi.N_GRID,
        "sigma": "0.05",
        "weight": "lifetime",
        "homology_channels": ["H0", "H1"],
        "sqrt2_normalize": True,
    }


def moments_feature_spec() -> dict:
    return {
        "schema_version": 1,
        "config_kind": "feature",
        "stable_id": MOMENTS_STABLE_ID,
        "feature_kind": "moments",
        "generator_version": "V1",
        "components": ["mean", "cov_diag", "cov_offdiag_sqrt2"],
        "cov_denominator": "n",
    }


def feature_config_hash(spec: dict) -> str:
    return config_hash("feature", spec["schema_version"], spec)


def scenario_bpi_cap(scenario: str) -> float:
    return {SCENARIO_N_AR: 6.0, SCENARIO_N_CIRCLE: 2.5, SCENARIO_PAMAP2: 6.0}[scenario]


def scenario_moments_scale(scenario: str) -> float:
    return {SCENARIO_N_AR: 1.0, SCENARIO_N_CIRCLE: 1.0, SCENARIO_PAMAP2: 6.0}[scenario]


def _window_feature(
    window_raw: np.ndarray,
    *,
    feature_kind: FeatureKind,
    scenario: str,
) -> np.ndarray:
    delay = scenario == SCENARIO_N_AR
    cloud = pointcloud.build_point_cloud(window_raw, delay=delay)
    if feature_kind == "bpi":
        if cloud.shape[0] < 2:
            return np.zeros(800, dtype=np.float64)
        h0, h1 = ph.h0h1(cloud)
        return bpi.bpi_from_diagrams(h0, h1, cap=scenario_bpi_cap(scenario))
    if feature_kind == "moments":
        return moments.moments_feature(
            cloud, scale=scenario_moments_scale(scenario)
        )
    raise ValueError(f"unknown feature_kind {feature_kind!r}")


def feature_matrix_for_windows(
    windows_raw: list[np.ndarray],
    *,
    feature_kind: FeatureKind,
    scenario: str,
) -> np.ndarray:
    """[M,p] feature matrix (window x feature coordinate), C order float64."""
    rows = [_window_feature(w, feature_kind=feature_kind, scenario=scenario) for w in windows_raw]
    p = rows[0].shape[0] if rows else 0
    if any(r.shape[0] != p for r in rows):
        raise ValueError("inconsistent feature dimension across windows")
    return np.ascontiguousarray(np.vstack(rows) if rows else np.zeros((0, p)))


def feature_sufficient_stats(feature_matrix: np.ndarray) -> dict[str, np.ndarray]:
    """Plan §11 per-unit sufficient stats: a_r, q_r over the M windows."""
    m = np.asarray(feature_matrix, dtype=np.float64)
    if m.ndim != 2:
        raise ValueError("feature_matrix must be [M,p]")
    a = m.mean(axis=0)
    q = np.einsum("ij,ij->i", m, m).mean()
    return {"a": a, "q": q}


def feature_dimensionality(feature_kind: FeatureKind, *, cloud_dim: int) -> int:
    if feature_kind == "bpi":
        return 800
    return moments.moments_feature_size(cloud_dim)


__all__ = [
    "FeatureKind",
    "Scenario",
    "SCENARIO_N_AR",
    "SCENARIO_N_CIRCLE",
    "SCENARIO_PAMAP2",
    "BPI_STABLE_ID",
    "MOMENTS_STABLE_ID",
    "MATRIX_OBJECT_KIND",
    "SUFFICIENT_OBJECT_KIND",
    "bpi_feature_spec",
    "moments_feature_spec",
    "feature_config_hash",
    "scenario_bpi_cap",
    "scenario_moments_scale",
    "feature_matrix_for_windows",
    "feature_sufficient_stats",
    "feature_dimensionality",
]
