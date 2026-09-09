"""MOMENTS control representation (Plan §5.3).

Feature vector = [d means, d covariance diagonal, sqrt(2)*S_ab (a<b, lexicographic)]
after dividing the point cloud by the fixed coordinate scale ``a``.  Covariance
denominator is fixed at n (no bias correction).  A constant (single unique
point) cloud returns its actual mean and zero covariance; an empty cloud
returns a zero vector.
"""

from __future__ import annotations

import itertools

import numpy as np


def moments_feature(points: np.ndarray, *, scale: float) -> np.ndarray:
    """5-dim (2-D cloud) or 9-dim (3-D cloud) feature vector."""
    pts = np.asarray(points, dtype=np.float64) / float(scale)
    if pts.ndim != 2:
        raise ValueError("moments_feature requires an (n,d) point cloud")
    n, d = pts.shape
    if n == 0:
        return np.zeros(d + d + d * (d - 1) // 2, dtype=np.float64)
    mean = pts.mean(axis=0)
    centered = pts - mean
    cov = centered.T @ centered / n
    diag = np.diag(cov)
    off = np.array(
        [np.sqrt(2.0) * cov[a, b] for a, b in itertools.combinations(range(d), 2)]
    )
    return np.concatenate([mean, diag, off])


def moments_feature_size(dim: int) -> int:
    return dim + dim + dim * (dim - 1) // 2


__all__ = [
    "moments_feature",
    "moments_feature_size",
]
