"""Window-local point-cloud pipeline (Plan §5.1).

Rules, in order:
  1. reject NaN/Inf; cast to float64;
  2. normalise ``-0.0`` to ``+0.0``;
  3. sort rows lexicographically (float64) and de-duplicate by exact bit
     pattern (row permutation therefore cannot change the cloud);
  4. ``point_limit``: more unique points than the frozen limit is a
     configuration error - never downsample randomly;
  5. multivariate windows are used row-wise; single-variable windows get the
     window-local delay embedding (Plan §5.1, implemented in ``dgp``).
"""

from __future__ import annotations

import numpy as np

from .dgp import delay_embedding_3

DEFAULT_POINT_LIMIT = 128


class PointCloudError(ValueError):
    """Invalid point cloud under the window-local contract."""


def clean_and_dedup(points: np.ndarray) -> np.ndarray:
    """float64, reject non-finite, ``-0.0 -> +0.0``, lexsort + bit de-dupe."""
    a = np.asarray(points, dtype=np.float64)
    if a.ndim != 2:
        raise PointCloudError(f"point cloud must be 2-D (n,d), got {a.ndim}-D")
    if a.shape[0] == 0:
        return a.copy()
    if not np.isfinite(a).all():
        raise PointCloudError("point cloud contains NaN/Inf")
    a = np.where(a == 0.0, 0.0, a)  # -0.0 -> +0.0
    # lexicographic row sort with column 0 most significant
    keys = [a[:, j] for j in range(a.shape[1] - 1, -1, -1)]
    order = np.lexsort(keys)
    a = a[order]
    keep = np.ones(a.shape[0], dtype=bool)
    if a.shape[0] > 1:
        keep[1:] = np.any(a[1:] != a[:-1], axis=1)
    return a[keep]


def check_point_limit(n_unique: int, point_limit: int = DEFAULT_POINT_LIMIT) -> None:
    if n_unique > point_limit:
        raise PointCloudError(
            f"unique points {n_unique} exceed frozen point_limit {point_limit}; "
            "config error (random downsampling forbidden)"
        )


def build_point_cloud(
    window_raw: np.ndarray,
    *,
    delay: bool,
    point_limit: int = DEFAULT_POINT_LIMIT,
) -> np.ndarray:
    """Window slice -> canonical point cloud.

    ``delay=False``: multivariate rows used directly (N-CIRCLE, PAMAP2).
    ``delay=True``: 1-D window embedded to ``(x_t,x_{t+3},x_{t+6})`` (N-AR).
    """
    raw = np.asarray(window_raw)
    if delay:
        if raw.ndim != 1:
            raise PointCloudError("delay=True requires a 1-D raw window")
        pts = delay_embedding_3(raw)
    else:
        if raw.ndim != 2:
            raise PointCloudError("delay=False requires a 2-D raw window")
        pts = raw
    out = clean_and_dedup(pts)
    check_point_limit(out.shape[0], point_limit)
    return out


def cloud_dimensionality(*, delay: bool) -> int:
    return 3 if delay else None  # dimension set by raw window at call time


__all__ = [
    "PointCloudError",
    "DEFAULT_POINT_LIMIT",
    "clean_and_dedup",
    "check_point_limit",
    "build_point_cloud",
]
