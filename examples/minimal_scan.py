#!/usr/bin/env python3
"""Minimal demonstration of the window geometry and the registered calibration rule.

Reads nothing but the frozen design values; prints the quantities the paper's protocol section
defines. This is an *illustration*, not a result: paper numbers come from results/canonical/.
"""

from __future__ import annotations

import math

W = 64            # window length
B = 999           # resamples
ALPHA = 0.05

GEOMETRIES = (  # (s, T, label) as registered: fixed-M keeps M = 192, fixed-T keeps T = 3120
    (64, 12288, "fixed-M s=64"),
    (64, 3120, "fixed-T s=64"),
    (32, 6176, "fixed-M s=32"),
    (32, 3120, "fixed-T s=32"),
    (16, 3120, "fixed-M = fixed-T (shared configuration)"),
    (8, 1592, "fixed-M s=8"),
    (8, 3120, "fixed-T s=8"),
)


def windows(T: int, s: int) -> int:
    return (T - W) // s + 1


def overlap_ratio(s: int) -> float:
    return 1 - s / W


def p_value(exceed: int) -> float:
    return (exceed + 1) / (B + 1)


def main() -> int:
    print(f"W = {W}, B = {B}, alpha = {ALPHA}")
    print(f"{'geometry':<42} {'M':>5} {'overlap':>8} {'K*':>5} {'p(K*)':>10}")
    k_star = math.floor(ALPHA * (B + 1)) - 1          # reject iff exceed <= k_star
    for s, T, label in GEOMETRIES:
        print(f"{label:<42} {windows(T, s):>5} {overlap_ratio(s):>8.3f} {k_star:>5} {p_value(k_star):>10.6f}")
    print()
    print(f"reject rule: reject iff exceed <= {k_star}  (equivalently p <= {p_value(k_star):.6f} <= {ALPHA})")
    print("note: the shared s=16 configuration satisfies both budget definitions; it is one scientific cell.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
