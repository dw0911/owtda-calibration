"""M0 naive permutation and M1 frozen-DMB resamplers (Plan §6).

Common inner contract: B=999, p=(1+exceed)/1000, reject <=> p<=0.05
<=> exceed<=49, ties use ``>=``.  Observed statistic is computed once by
``scan.statistic_curve`` for the natural order and is identical for M0 and M1.
RNG consumption follows Plan §15.2/§15.4:
  * M0: one Generator per (data_unit_id, resample_index), one
    ``rng.permutation(M)`` call;
  * M1: one Generator per (data_unit_id, resample_index), one
    ``rng.standard_normal(M+b-1)`` call; the triangular multiplier and bridge
    are deterministic transforms of those draws.
"""

from __future__ import annotations

import numpy as np

from .scan import statistic_curve
from .seeding import make_rng

B = 999
M0_STABLE_ID = "M0_NAIVE_PERM_B999_V1"
M1_STABLE_ID = "M1_DMB_R1_TRI_EXTIID_B999_V1"
EPS64 = 2.0**-52


def integer_cuberoot_ceil(M: int) -> int:
    """Smallest j with j^3 >= M (integer arithmetic, no float cube root)."""
    if not isinstance(M, int) or M <= 0:
        raise ValueError(f"M must be a positive int, got {M!r}")
    j = 1
    while j**3 < M:
        j += 1
    return j


def dmb_block_length(*, W: int, stride: int, M: int) -> int:
    """b_R1 = max(floor(W/s)+1, ceil(M^(1/3))) (Plan §6 M1)."""
    if stride <= 0 or W <= 0:
        raise ValueError("W and stride must be positive")
    q0 = W // stride + 1
    return max(q0, integer_cuberoot_ceil(M))


def m0_permutation(root_key_hex: str, *, method_generation_id: str,
                   data_unit_id: str, resample_index: int, M: int) -> np.ndarray:
    rng = make_rng(
        root_key_hex,
        "M0_permutation",
        method_generation_id=method_generation_id,
        data_unit_id=data_unit_id,
        resample_index=resample_index,
    )
    perm = rng.permutation(M)
    if perm.shape != (M,) or perm.dtype != np.int64:
        raise RuntimeError("M0 permutation contract violated")
    return perm


def calibrate_m0(
    feature_matrix: np.ndarray,
    *,
    root_key_hex: str,
    method_generation_id: str,
    data_unit_id: str,
) -> dict:
    a = np.asarray(feature_matrix, dtype=np.float64)
    if a.ndim != 2:
        raise ValueError("feature matrix must be [M,p]")
    M = a.shape[0]
    curve_obs = statistic_curve(a)
    t_obs = float(curve_obs["values"].max())
    exceed = 0
    for r in range(1, B + 1):
        perm = m0_permutation(
            root_key_hex,
            method_generation_id=method_generation_id,
            data_unit_id=data_unit_id,
            resample_index=r,
            M=M,
        )
        row = statistic_curve(a[perm])
        t_r = float(row["values"].max())
        exceed += int(t_r >= t_obs)
    p = (1 + exceed) / 1000.0
    return {
        "M": M,
        "B": B,
        "observed_statistic": t_obs,
        "exceed_count": exceed,
        "p_value": p,
        "reject": bool(p <= 0.05),
    }


def dmb_multiplier_series(e: np.ndarray, *, b: int) -> np.ndarray:
    """xi_i = b^(-1/2) * sum_{j<b} e_{i+j}, no circular wrap/trimming."""
    if e.ndim != 1:
        raise ValueError("innovation draw must be 1-D")
    conv = np.convolve(e, np.ones(b, dtype=np.float64), mode="valid")
    return conv / np.sqrt(float(b))


def m1_gaussian_draw(root_key_hex: str, *, method_generation_id: str,
                     data_unit_id: str, resample_index: int, size: int) -> np.ndarray:
    rng = make_rng(
        root_key_hex,
        "M1_gaussian_innovation",
        method_generation_id=method_generation_id,
        data_unit_id=data_unit_id,
        resample_index=resample_index,
    )
    e = rng.standard_normal(size, dtype=np.float64)
    if e.shape != (size,):
        raise RuntimeError("M1 draw contract violated")
    return e


def calibrate_m1(
    feature_matrix: np.ndarray,
    *,
    root_key_hex: str,
    method_generation_id: str,
    data_unit_id: str,
    W: int,
    stride: int,
) -> dict:
    a = np.asarray(feature_matrix, dtype=np.float64)
    if a.ndim != 2:
        raise ValueError("feature matrix must be [M,p]")
    M = a.shape[0]
    b = dmb_block_length(W=W, stride=stride, M=M)
    curve_obs = statistic_curve(a)
    t_obs = float(curve_obs["values"].max())
    # centered rows Z_i = Y_i - Ybar (bridge weights act on centered values)
    z = a - a.mean(axis=0, keepdims=True)
    exceed = 0
    for r in range(1, B + 1):
        e = m1_gaussian_draw(
            root_key_hex,
            method_generation_id=method_generation_id,
            data_unit_id=data_unit_id,
            resample_index=r,
            size=M + b - 1,
        )
        xi = dmb_multiplier_series(e, b=b)
        weighted = xi[:, None] * z
        row = statistic_curve(weighted)
        t_r = float(row["values"].max())
        exceed += int(t_r >= t_obs)
    p = (1 + exceed) / 1000.0
    return {
        "M": M,
        "B": B,
        "b": b,
        "observed_statistic": t_obs,
        "exceed_count": exceed,
        "p_value": p,
        "reject": bool(p <= 0.05),
    }


__all__ = [
    "B",
    "M0_STABLE_ID",
    "M1_STABLE_ID",
    "EPS64",
    "integer_cuberoot_ceil",
    "dmb_block_length",
    "m0_permutation",
    "calibrate_m0",
    "dmb_multiplier_series",
    "m1_gaussian_draw",
    "calibrate_m1",
]
