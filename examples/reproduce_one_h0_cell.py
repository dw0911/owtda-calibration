#!/usr/bin/env python3
"""Reproduce one H0 evaluation unit from the canonical dataset (and, if present, the ledger).

Usage:
  python examples/reproduce_one_h0_cell.py                # first unit in the canonical file
  python examples/reproduce_one_h0_cell.py --index 7
  python examples/reproduce_one_h0_cell.py --ledger data/external/H0_NULL_evaluation.scientific.jsonl
"""

from __future__ import annotations

import argparse
import json
import math
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
CANON = REPO / "results" / "canonical" / "H0_POINTWISE.json"


def wilson(rejects: int, n: int, z: float = 1.959963984540054) -> tuple[float, float]:
    p = rejects / n
    denominator = 1 + z * z / n
    centre = (p + z * z / (2 * n)) / denominator
    half = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / denominator
    return centre - half, centre + half


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--index", type=int, default=0)
    parser.add_argument("--ledger", type=Path, default=None)
    args = parser.parse_args()

    rows = json.loads(CANON.read_text(encoding="utf-8-sig"))
    row = rows[args.index]
    n, rejects = int(row["n"]), int(row["rejects"])
    lo, hi = wilson(rejects, n)
    print(f"unit        : {row['DGP_family']} rho={row['rho']} s={row['stride']} T={row['T']} M={row['M_expected']}")
    print(f"representation/method: {row['feature_id'][:7]} / {row['method_id'][:6]}")
    print(f"canonical   : n={n} rejects={rejects} rate={row['rejection_rate']:.6f} [{row['classification']}]")
    print(f"recomputed  : rate={rejects / n:.6f} 95% Wilson=[{lo:.10f}, {hi:.10f}]")
    print(f"match       : rate={abs(rejects / n - float(row['rejection_rate'])) < 1e-12} "
          f"interval={abs(lo - row['wilson95'][0]) < 1e-9 and abs(hi - row['wilson95'][1]) < 1e-9}")

    if args.ledger and args.ledger.exists():
        seen = rejects_ledger = 0
        with args.ledger.open(encoding="utf-8") as handle:
            for line in handle:
                objective = json.loads(line)
                if (objective["logical_cell_id"], objective["feature_id"], objective["method_id"]) != (
                    row["logical_cell_id"], row["feature_id"], row["method_id"],
                ):
                    continue
                seen += 1
                rejects_ledger += int(bool(objective["reject"]))
        print(f"from ledger : rows={seen} rejects={rejects_ledger} "
              f"match={seen == n and rejects_ledger == rejects}")
    else:
        print("ledger      : (not provided; Level 2 requires the archived ledger - see reproducibility/RUNBOOK.md)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
