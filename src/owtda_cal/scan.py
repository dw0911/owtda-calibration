"""Maximum scan statistic (Plan §3.3-§3.4).

Candidate set K_M = [ceil(0.15M), M - ceil(0.15M)]; for a candidate k the
statistic is the weighted squared mean difference

    T_M(k) = (n_L n_R / M) * || Ybar_1:k - Ybar_{k+1:M} ||_2^2.

The change index uses the longest qualifying plateau of candidates within
``64*eps64*max(1,|T_max|)`` of the max; ties pick the left-most plateau, and
inside it the lower median is used.  Location then maps to raw time via
``tau_hat = (k_hat - 1/2)*s + (W+1)/2``.
"""

from __future__ import annotations

import math

import numpy as np

EPS64 = 2.0**-52


def candidate_bounds(M: int) -> tuple[int, int]:
    """Inclusive candidate endpoints (low, high)."""
    if not isinstance(M, int) or M <= 0:
        raise ValueError(f"M must be a positive int, got {M!r}")
    low = math.ceil(0.15 * M)
    high = M - low
    if high < low:
        raise ValueError(f"no candidate left for M={M}")
    return low, high


def candidate_indices(M: int) -> np.ndarray:
    lo, hi = candidate_bounds(M)
    return np.arange(lo, hi + 1, dtype=np.int64)


def _t_curve(matrix: np.ndarray, ks: np.ndarray) -> np.ndarray:
    """Fast path: prefix sums, one pass over the candidate set."""
    a = np.asarray(matrix, dtype=np.float64)
    M, p = a.shape
    cum = np.zeros((M + 1, p), dtype=np.float64)
    np.cumsum(a, axis=0, out=cum[1:])
    total = cum[M]
    vals = np.empty(ks.shape[0], dtype=np.float64)
    for idx, k in enumerate(ks):
        k = int(k)
        left = cum[k]
        right = total - cum[k]
        mean_l = left / k
        mean_r = right / (M - k)
        diff = mean_l - mean_r
        vals[idx] = (k * (M - k) / M) * np.dot(diff, diff)
    return vals


def _t_curve_slow(matrix: np.ndarray, ks: np.ndarray) -> np.ndarray:
    """Slow reference path: re-computes means by slicing (Plan §3.4)."""
    a = np.asarray(matrix, dtype=np.float64)
    M = a.shape[0]
    vals = np.empty(ks.shape[0], dtype=np.float64)
    for idx, k in enumerate(ks):
        k = int(k)
        mean_l = a[:k].mean(axis=0)
        mean_r = a[k:].mean(axis=0)
        diff = mean_l - mean_r
        vals[idx] = (k * (M - k) / M) * np.dot(diff, diff)
    return vals


def is_degenerate_constant(a: np.ndarray) -> bool:
    """True iff every row is *exactly* equal to the first row.

    Plan §3.3 / SAP: for a fully constant feature the frozen answer is
    ``T_obs = 0``, ``p = 1``, ``reject = 0``.  Detecting it by exact equality (not
    a tolerance) keeps genuinely small but non-constant signals untouched.
    """
    return bool(a.shape[0] > 1 and np.all(a == a[0]))


def statistic_curve(matrix: np.ndarray, *, reference: bool = False) -> dict:
    """T(k) over the candidate set.  ``reference=True`` uses the slow path.

    Degenerate inputs are handled **exactly** (audit A03): a constant feature
    returns an exactly zero curve instead of ~1e-30 floating-point residue, since
    the residue is what turned a p-value of 1 into 0.001 downstream.  Non-finite
    input and an empty feature dimension are rejected rather than propagated.
    """
    a = np.asarray(matrix, dtype=np.float64)
    if a.ndim != 2:
        raise ValueError("feature matrix must be [M,p]")
    if a.shape[1] == 0:
        raise ValueError("feature matrix must have at least one column")
    if not np.all(np.isfinite(a)):
        raise ValueError("feature matrix must be finite (no NaN/Inf)")
    M = a.shape[0]
    ks = candidate_indices(M)
    if is_degenerate_constant(a):
        return {
            "M": M,
            "ks": ks,
            "values": np.zeros(ks.shape[0], dtype=np.float64),
            "degenerate_constant": True,
        }
    vals = _t_curve_slow(a, ks) if reference else _t_curve(a, ks)
    return {"M": M, "ks": ks, "values": vals, "degenerate_constant": False}


def plateau_selection(ks: np.ndarray, values: np.ndarray) -> dict:
    """Longest qualifying plateau -> left-most on ties -> lower median index."""
    ks = np.asarray(ks, dtype=np.int64)
    values = np.asarray(values, dtype=np.float64)
    if ks.shape[0] != values.shape[0] or ks.shape[0] == 0:
        raise ValueError("plateau_selection needs non-empty aligned inputs")
    t_max = float(values.max())
    tol = 64.0 * EPS64 * max(1.0, abs(t_max))
    qual = values >= t_max - tol
    # find longest contiguous run of qualifying candidates; left-most on ties
    best_len = 0
    best_start = -1
    i = 0
    n = qual.shape[0]
    while i < n:
        if qual[i]:
            j = i
            while j < n and qual[j]:
                j += 1
            if j - i > best_len:
                best_len = j - i
                best_start = i
            i = j
        else:
            i += 1
    if best_start < 0:
        raise ValueError("no qualifying candidate plateau found")
    seg = ks[best_start : best_start + best_len]
    # lower median of the segment (0-based): floor((len-1)/2)
    khat = int(seg[(best_len - 1) // 2])
    return {
        "khat": khat,
        "plateau_left_index": int(best_start),
        "plateau_length": int(best_len),
        "qualifying_count": int(qual.sum()),
        "t_max": t_max,
    }


def scan_statistic(matrix: np.ndarray, *, reference: bool = False) -> dict:
    """Full scan result on the natural (observed) order."""
    a = np.asarray(matrix, dtype=np.float64)
    if a.ndim != 2:
        raise ValueError("feature matrix must be [M,p]")
    curve = statistic_curve(a, reference=reference)
    sel = plateau_selection(curve["ks"], curve["values"])
    M = curve["M"]
    lo, hi = candidate_bounds(M)
    out = {
        "M": M,
        "candidate_first": lo,
        "candidate_last": hi,
        "candidate_count": int(hi - lo + 1),
        "observed_statistic": sel["t_max"],
        **sel,
    }
    return out


def estimated_change_raw_time(khat: int, *, stride: int, W: int) -> float:
    """tau_hat = (k_hat - 1/2)*s + (W+1)/2 (Plan §12.4)."""
    return (khat - 0.5) * stride + (W + 1) / 2.0


__all__ = [
    "EPS64",
    "candidate_bounds",
    "candidate_indices",
    "is_degenerate_constant",
    "statistic_curve",
    "plateau_selection",
    "scan_statistic",
    "estimated_change_raw_time",
]
