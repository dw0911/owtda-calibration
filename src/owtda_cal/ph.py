"""VR persistent homology wrapper (Plan §5.1).

Frozen settings: Vietoris-Rips, F2, H0+H1, maxdim=1, no data-driven thresh,
euclidean, ``distance_matrix=False`` always (avoids the square-matrix heuristic).

Precision is **layered**, and the layers must not be conflated (audit A09):

* the raw series, point clouds, diagrams and everything downstream (features,
  scan, calibration) are ``float64``;
* the PH engine is fixed to ``ripser`` 0.6.15, whose ``ripser()`` casts the dense
  lower-triangular distances to ``float32`` before calling the C++ backend, so the
  filtration *inside* the engine is float32.  Input and output ndarrays being
  float64 does not make the backend float64.

On topology: in a finite Euclidean point cloud the Vietoris-Rips filtration forms
the full simplex once the filtration value reaches the diameter, so every H1 class
has died by then; only the final H0 component is reported with ``death=inf``.  We
therefore drop only explicit ``inf`` deaths and keep all finite classes, which then
hit the winsor cap.  Clouds with fewer than 2 unique points are handled upstream
(zero vectors).
"""

from __future__ import annotations

import warnings

import numpy as np


def ripser(*args, **kwargs):
    """Load the genuine backend on computation; never return a placeholder."""
    from ripser import ripser as implementation
    return implementation(*args, **kwargs)



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
