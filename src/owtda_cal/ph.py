"""VR persistent homology wrapper (Plan §5.1).

Frozen settings: Vietoris-Rips, F2, H0+H1, maxdim=1, no data-driven thresh,
euclidean, ``distance_matrix=False`` always (avoids the square-matrix
heuristic).  ``ripser`` 0.6.15 caps the death of a never-dying H1 class at the
point-cloud diameter, and reports the final H0 class with ``death=inf``; we
therefore drop only explicit ``inf`` deaths and keep finite classes (including
the diameter-capped H1 class, which later hits the winsor cap).  Clouds with
fewer than 2 unique points are handled upstream (zero vectors).
"""

from __future__ import annotations

import warnings

import numpy as np
from ripser import ripser


class PersistentHomologyError(ValueError):
    """Invalid PH input under the frozen contract."""


def vr_diagrams(points: np.ndarray, *, maxdim: int = 1) -> list[np.ndarray]:
    """Return finite, positive-length persistence classes per dimension.

    ``diagrams[0]`` = H0, ``diagrams[1]`` = H1.  Infinite deaths are dropped.
    ``thresh=inf`` means no data-driven cut-off (Plan §5.1 forbids a
    data-driven threshold); the ripser wrapper heuristic warnings (square
    input / more columns than rows) are suppressed -- the point cloud is
    passed row-wise with ``distance_matrix=False`` by design.
    """
    pts = np.asarray(points, dtype=np.float64)
    if pts.ndim != 2 or pts.shape[0] < 2:
        raise PersistentHomologyError(
            "vr_diagrams needs >= 2 unique points (n,d); handle degenerates upstream"
        )
    if not np.isfinite(pts).all():
        raise PersistentHomologyError("point cloud contains NaN/Inf")
    with warnings.catch_warnings():
        warnings.filterwarnings("ignore", category=UserWarning)
        res = ripser(
            pts,
            maxdim=maxdim,
            thresh=np.inf,
            coeff=2,
            distance_matrix=False,
            do_cocycles=False,
        )
    dgms = res["dgms"]
    out: list[np.ndarray] = []
    for dim in range(maxdim + 1):
        g = np.asarray(dgms[dim], dtype=np.float64)
        keep = np.isfinite(g[:, 1]) & (g[:, 0] < g[:, 1])
        out.append(g[keep].reshape(-1, 2))
    return out


def h0h1(points: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Convenience: (H0 classes, H1 classes) after dropping infinite deaths."""
    dg = vr_diagrams(points, maxdim=1)
    return dg[0], dg[1]


__all__ = [
    "PersistentHomologyError",
    "vr_diagrams",
    "h0h1",
]
