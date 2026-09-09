"""Fixed persistence-intensity (BPI) mapping (Plan §5.2).

For classes (b,d): u=min(b/c,1), v=min((d-b)/c,1) where c is the frozen
scenario coordinate cap.  On a 20x20 grid with centers g_r=(r+1/2)/20,
sigma=0.05 and lifetime weight w(v)=v:

    Z_{r,l} = sqrt(Delta^2) * sum_p v_p * (1/(2*pi*sigma^2))
                        * exp(-((g_r-u_p)^2 + (g_l-v_p)^2) / (2*sigma^2))

H0 and H1 channels each map to 400 coordinates, concatenated H0 then H1 and
divided by sqrt(2) -> 800 dimensions.  Empty channels stay 400 zeros.
"""

from __future__ import annotations

import numpy as np

N_GRID = 20
SIGMA = 0.05
GRID_DELTA = 1.0 / N_GRID


def _grid_centers(n_grid: int = N_GRID) -> np.ndarray:
    return (np.arange(n_grid) + 0.5) * GRID_DELTA


def intensity_channel(classes: np.ndarray, *, cap: float) -> np.ndarray:
    """400-dim vector for one homology channel."""
    g = np.asarray(classes, dtype=np.float64).reshape(-1, 2)
    if g.shape[0] == 0:
        return np.zeros(N_GRID * N_GRID, dtype=np.float64)
    birth = g[:, 0]
    death = g[:, 1]
    if not np.isfinite(g).all():
        raise ValueError("intensity_channel requires finite classes")
    if np.any(death <= birth):
        raise ValueError("classes must have death > birth")
    u = np.minimum(birth / cap, 1.0)
    v = np.minimum((death - birth) / cap, 1.0)
    centers = _grid_centers()
    eu = np.exp(-0.5 * ((centers[:, None] - u[None, :]) / SIGMA) ** 2)
    el = np.exp(-0.5 * ((centers[:, None] - v[None, :]) / SIGMA) ** 2)
    # Z[r, l] = sum_p w(v_p) eu[r,p] el[l,p]
    pre = eu[:, None, :] * el[None, :, :]
    acc = (pre * v).sum(axis=2)
    kernel_norm = 1.0 / (2.0 * np.pi * SIGMA * SIGMA)
    return (GRID_DELTA * kernel_norm * acc).reshape(-1)


def bpi_from_diagrams(h0: np.ndarray, h1: np.ndarray, *, cap: float) -> np.ndarray:
    """Concatenate H0 then H1 channels and divide by sqrt(2): 800 dims."""
    z0 = intensity_channel(h0, cap=cap)
    z1 = intensity_channel(h1, cap=cap)
    return np.concatenate([z0, z1]) / np.sqrt(2.0)


__all__ = [
    "N_GRID",
    "SIGMA",
    "GRID_DELTA",
    "intensity_channel",
    "bpi_from_diagrams",
]
