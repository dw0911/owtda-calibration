"""Throughput probe for the compute budget (Plan §9.4 pre-freeze estimate).

Measures representative per-window PH+BPI cost and a short M1 inner-loop cost
on this host, and extrapolates to the formal core budgets.  Numbers are
exploratory (single worker, no parallel scaling yet; G2/G3 will fix worker
behaviour later).  This is L0 instrumentation and never feeds science rows.
"""

from __future__ import annotations

import time

import numpy as np

from .calibrate import calibrate_m1
from .features import (
    SCENARIO_N_AR,
    SCENARIO_N_CIRCLE,
    feature_matrix_for_windows,
)

PH_TOTAL = 8_207_600  # Plan §9.2 total PH windows
H0_PH = 5_750_000
H1_PH = 2_457_600
RESAMPLE_TOTAL = 330_868_800

_ROOT = "cd" * 32  # test-only root key, never used by formal runs


def _n_circle_windows(n=20, w=64):
    rng = np.random.default_rng(7)
    out = []
    for _ in range(n):
        t = np.linspace(0.0, 2 * np.pi, w, endpoint=False)
        out.append(
            np.column_stack([np.cos(t), np.sin(t)]) + 0.05 * rng.standard_normal((w, 2))
        )
    return out


def _n_ar_windows(n=20, w=64):
    rng = np.random.default_rng(8)
    return [rng.standard_normal(w) for _ in range(n)]


def benchmark() -> dict:
    """Measure per-window PH/BPI and a short M1 inner-loop, single worker."""
    results: dict[str, float] = {}

    # BPI matrix throughput per window
    t0 = time.perf_counter()
    m_circle = feature_matrix_for_windows(
        _n_circle_windows(), feature_kind="bpi", scenario=SCENARIO_N_CIRCLE
    )
    dt_circle = time.perf_counter() - t0
    results["bpi_circle_per_window_seconds"] = dt_circle / m_circle.shape[0]

    t0 = time.perf_counter()
    m_ar = feature_matrix_for_windows(
        _n_ar_windows(), feature_kind="bpi", scenario=SCENARIO_N_AR
    )
    dt_ar = time.perf_counter() - t0
    results["bpi_ar_per_window_seconds"] = dt_ar / m_ar.shape[0]

    # M1 inner-loop throughput: run B=30 replicates on a small matrix.
    small = _n_ar_windows(n=48, w=64)
    mat = feature_matrix_for_windows(small, feature_kind="bpi", scenario=SCENARIO_N_AR)
    t0 = time.perf_counter()
    calibrate_m1(
        mat,
        root_key_hex=_ROOT,
        method_generation_id="probe",
        data_unit_id="probe_unit",
        W=64,
        stride=16,
    )
    dt_m1 = time.perf_counter() - t0
    results["m1_full_b999_seconds"] = dt_m1

    # coarse extrapolations (single worker; parallel scaling measured later)
    per_win = 0.5 * (results["bpi_circle_per_window_seconds"] + results["bpi_ar_per_window_seconds"])
    results["extrapolated_h0_wall_hours_1w"] = per_win * H0_PH / 3600.0
    results["extrapolated_h1_wall_hours_1w"] = per_win * H1_PH / 3600.0
    return results


def smoke_independent_root() -> str:
    """Explicitly isolated root hex for smoke probe use (not a formal key)."""
    return _ROOT


__all__ = [
    "PH_TOTAL",
    "H0_PH",
    "H1_PH",
    "RESAMPLE_TOTAL",
    "benchmark",
    "smoke_independent_root",
]
