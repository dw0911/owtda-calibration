"""PAMAP2 Protocol importer (Plan §13.2).

Frozen rules implemented here:
  * every row has exactly 54 tokens; timestamp/activityID finite; sensor tokens
    finite or the literal ``NaN`` (case-sensitive); ``Inf``/spelling variants fail;
  * activityID must be an exact integer in the allowed set (+ transient 0);
  * timestamps strictly increasing (Delta t <= 0 -> DATA_IDENTITY_FAIL);
  * provisional clock segments split on gaps > 0.5 s; half-up 100 Hz grid
    mapping ``j = floor(100*(t-t0)+0.5)`` with tolerance 1e-4 and strictly
    increasing j (duplicate grid index / out-of-tolerance -> DATA_TIMEBASE_FAIL);
  * missing grid rows are never filled; provisional grid-contiguous segments
    split on missing grid indices;
  * chest +/-16 g channels (columns 22-24) with NaN runs of length r in 1..50
    interpolated by the fixed four-step binary64 sequence; runs > 50 or
    unbounded mark the whole row bad (three-axis union); bad rows are dropped;
  * the final analysis segment is the largest remaining grid-contiguous run;
  * after interpolation the three channels are divided by 9.80665 exactly once.

Columns 25-27 (chest +/-6 g) are explicitly disabled.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field

import numpy as np

N_COLUMNS = 54
TIMESTAMP_COL = 0  # 1-based 1
ACTIVITY_COL = 1  # 1-based 2
CHEST_16G_COLS = (21, 22, 23)  # 1-based 22-24
CHEST_6G_COLS = (24, 25, 26)  # 1-based 25-27 (disabled)
ACTIVITY_ALLOWED = frozenset({0, 1, 2, 3, 4, 5, 6, 7, 12, 13, 16, 17, 24})
CLOCK_GAP_SECONDS = 0.5
GRID_TOLERANCE = 1e-4
MAX_INTERP_RUN = 50
GRAVITY = 9.80665


class Pamap2Error(Exception):
    """Base error with a frozen reason code."""

    code = "PAMAP2_ERROR"


class DataIdentityFail(Pamap2Error):
    code = "DATA_IDENTITY_FAIL"


class DataTimebaseFail(Pamap2Error):
    code = "DATA_TIMEBASE_FAIL"


@dataclass
class ImportResult:
    subject: str
    final_timestamps: np.ndarray
    final_grid_index: np.ndarray
    final_activity: np.ndarray
    final_chest_g: np.ndarray  # [n,3] in g units
    provisional_clock_segments: int
    provisional_grid_segments: int
    dropped_bad_rows: int
    original_entrywise_missing_rate: float
    original_rowwise_missing_rate: float
    final_segment_count: int
    diagnostics: dict = field(default_factory=dict)


def _parse_token(token: str, *, allow_nan: bool, what: str) -> float:
    if token == "NaN":
        if not allow_nan:
            raise DataIdentityFail(f"{what}: literal NaN not allowed")
        return math.nan
    try:
        value = float(token)
    except ValueError as exc:
        raise DataIdentityFail(f"{what}: malformed token {token!r}") from exc
    if not math.isfinite(value):
        raise DataIdentityFail(f"{what}: non-finite token {token!r}")
    return value


def parse_rows(lines) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Parse raw lines into (timestamps, activity, chest16 [n,3] with NaN)."""
    ts, act, chest = [], [], []
    for lineno, raw in enumerate(lines, start=1):
        tokens = raw.split()
        if len(tokens) != N_COLUMNS:
            raise DataIdentityFail(f"line {lineno}: expected 54 columns, got {len(tokens)}")
        t = _parse_token(tokens[TIMESTAMP_COL], allow_nan=False, what=f"line {lineno} timestamp")
        a = _parse_token(tokens[ACTIVITY_COL], allow_nan=False, what=f"line {lineno} activityID")
        if a != int(a):
            raise DataIdentityFail(f"line {lineno}: activityID not an exact integer: {a}")
        if int(a) not in ACTIVITY_ALLOWED:
            raise DataIdentityFail(f"line {lineno}: activityID {int(a)} not in allowed set")
        row = [
            _parse_token(tokens[c], allow_nan=True, what=f"line {lineno} chest col {c + 1}")
            for c in CHEST_16G_COLS
        ]
        # remaining tokens must still be parseable numbers or literal NaN
        for idx, tok in enumerate(tokens):
            if idx in (TIMESTAMP_COL, ACTIVITY_COL, *CHEST_16G_COLS):
                continue
            _parse_token(tok, allow_nan=True, what=f"line {lineno} col {idx + 1}")
        ts.append(t)
        act.append(int(a))
        chest.append(row)
    if not ts:
        raise DataIdentityFail("empty file")
    return np.asarray(ts, dtype=np.float64), np.asarray(act, dtype=np.int64), np.asarray(
        chest, dtype=np.float64
    )


def check_strictly_increasing(ts: np.ndarray) -> None:
    if np.any(np.diff(ts) <= 0.0):
        raise DataIdentityFail("timestamps must be globally strictly increasing")


def clock_segments(ts: np.ndarray) -> list[tuple[int, int]]:
    """Split on gaps > 0.5 s (inclusive start, exclusive end)."""
    gaps = np.where(np.diff(ts) > CLOCK_GAP_SECONDS)[0]
    bounds = [0, *(gaps + 1), ts.shape[0]]
    return [(bounds[i], bounds[i + 1]) for i in range(len(bounds) - 1)]


def grid_map(ts_segment: np.ndarray) -> np.ndarray:
    """Half-up 100 Hz mapping with tolerance; strictly increasing j required."""
    t0 = ts_segment[0]
    j = np.floor(100.0 * (ts_segment - t0) + 0.5).astype(np.int64)
    residual = np.abs(ts_segment - (t0 + j / 100.0))
    if np.any(residual > GRID_TOLERANCE):
        raise DataTimebaseFail("timestamp off the 100 Hz grid beyond tolerance")
    if np.any(np.diff(j) <= 0):
        raise DataTimebaseFail("grid indices must be strictly increasing")
    return j


def grid_contiguous_segments(j: np.ndarray) -> list[tuple[int, int]]:
    """Split a segment where grid indices are not consecutive."""
    breaks = np.where(np.diff(j) != 1)[0]
    bounds = [0, *(breaks + 1), j.shape[0]]
    return [(bounds[i], bounds[i + 1]) for i in range(len(bounds) - 1)]


def interpolate_run(x0: float, x1: float, r: int) -> np.ndarray:
    """Fixed four-step binary64 interpolation for a NaN run of length r."""
    delta = np.subtract(x1, x0, dtype=np.float64)
    out = np.empty(r, dtype=np.float64)
    for k in range(1, r + 1):
        lam = np.divide(float(k), float(r + 1))
        prod = np.multiply(lam, delta, dtype=np.float64)
        out[k - 1] = np.add(x0, prod, dtype=np.float64)
    return out


def interpolate_axis(values: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Interpolate NaN runs of length 1..50; longer/unbounded runs are bad rows."""
    v = values.astype(np.float64, copy=True)
    n = v.shape[0]
    bad = np.zeros(n, dtype=bool)
    i = 0
    while i < n:
        if math.isnan(v[i]):
            j = i
            while j < n and math.isnan(v[j]):
                j += 1
            r = j - i
            left_ok = i > 0
            right_ok = j < n
            if r > MAX_INTERP_RUN or not (left_ok and right_ok):
                bad[i:j] = True
            else:
                v[i:j] = interpolate_run(v[i - 1], v[j], r)
            i = j
        else:
            i += 1
    return v, bad


def convert_to_g(chest: np.ndarray) -> np.ndarray:
    return chest / GRAVITY


def import_subject(path: str, *, subject: str | None = None) -> ImportResult:
    """Full Protocol import for one subject file."""
    with open(path, "r", encoding="ascii", errors="strict") as fh:
        ts, act, chest = parse_rows(fh)
    check_strictly_increasing(ts)

    entrywise = float(np.isnan(chest).sum()) / float(chest.size)
    rowwise = float(np.isnan(chest).any(axis=1).sum()) / float(chest.shape[0])

    clocks = clock_segments(ts)
    n_grid_segments = 0
    dropped = 0
    final_segment_count = 0
    best: tuple[int, np.ndarray, np.ndarray, np.ndarray, np.ndarray] | None = None

    for (c0, c1) in clocks:
        j = grid_map(ts[c0:c1])
        for (g0, g1) in grid_contiguous_segments(j):
            n_grid_segments += 1
            seg = slice(c0 + g0, c0 + g1)
            seg_chest = chest[seg]
            filled = np.empty_like(seg_chest)
            bad = np.zeros(seg_chest.shape[0], dtype=bool)
            for axis in range(3):
                col, col_bad = interpolate_axis(seg_chest[:, axis])
                filled[:, axis] = col
                bad |= col_bad
            dropped += int(bad.sum())
            keep = ~bad
            if not keep.any():
                continue
            seg_g = convert_to_g(filled[keep])
            seg_j = j[g0:g1][keep]
            seg_ts = ts[seg][keep]
            seg_act = act[seg][keep]
            # after dropping bad rows, keep every grid-contiguous run; the
            # largest non-empty run is the final analysis segment.
            runs = grid_contiguous_segments(seg_j)
            final_segment_count += len(runs)
            for (r0, r1) in runs:
                cand = (r1 - r0, seg_ts[r0:r1], seg_j[r0:r1], seg_act[r0:r1], seg_g[r0:r1])
                if best is None or cand[0] > best[0]:
                    best = cand

    if best is None:
        raise DataIdentityFail("no usable analysis segment")
    f_ts, f_j, f_act, f_g = best[1], best[2], best[3], best[4]
    return ImportResult(
        subject=subject or path,
        final_timestamps=f_ts,
        final_grid_index=f_j,
        final_activity=f_act,
        final_chest_g=f_g,
        provisional_clock_segments=len(clocks),
        provisional_grid_segments=n_grid_segments,
        dropped_bad_rows=dropped,
        original_entrywise_missing_rate=entrywise,
        original_rowwise_missing_rate=rowwise,
        final_segment_count=final_segment_count,
        diagnostics={"rows_parsed": int(ts.shape[0])},
    )


__all__ = [
    "N_COLUMNS",
    "ACTIVITY_ALLOWED",
    "CLOCK_GAP_SECONDS",
    "GRID_TOLERANCE",
    "MAX_INTERP_RUN",
    "GRAVITY",
    "Pamap2Error",
    "DataIdentityFail",
    "DataTimebaseFail",
    "ImportResult",
    "parse_rows",
    "check_strictly_increasing",
    "clock_segments",
    "grid_map",
    "grid_contiguous_segments",
    "interpolate_run",
    "interpolate_axis",
    "convert_to_g",
    "import_subject",
]
