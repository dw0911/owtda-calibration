#!/usr/bin/env python3
"""Reproduce one H1 cell-feature from the canonical objects, plus the scenario difference.

Usage:
  python examples/reproduce_one_h1_cell.py                 # first cell-feature
  python examples/reproduce_one_h1_cell.py --scenario mean_shift
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
CANON = REPO / "results" / "canonical"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--scenario", default="shape_change")
    args = parser.parse_args()

    h1 = json.loads((CANON / "H1_REANALYSIS.json").read_text(encoding="utf-8-sig"))
    differences = json.loads((CANON / "H1_SCENARIO_DIFFERENCES.json").read_text(encoding="utf-8-sig"))

    cell = next(c for c in h1["percell"] if c["scenario_id"] == args.scenario)
    label = "BPI" if cell["feature_id"].startswith("BPI") else "MOMENTS"
    print(f"scenario    : {args.scenario}")
    print(f"geometry    : W={cell['W']} s={cell['stride']} T={cell['T']} "
          f"M={(int(cell['T']) - int(cell['W'])) // int(cell['stride']) + 1}")
    print(f"representation: {label}")
    for key in ("size_standardized_power", "raw_mae", "normalized_mae", "tau_true", "critical_rank"):
        if key in cell:
            print(f"  {key:<26} {cell[key]}")

    powers: dict[str, list[float]] = {}
    for candidate in h1["percell"]:
        if candidate["scenario_id"] != args.scenario:
            continue
        tag = "BPI" if candidate["feature_id"].startswith("BPI") else "MOMENTS"
        powers.setdefault(tag, []).append(float(candidate["size_standardized_power"]))
    delta = sum(powers["BPI"]) / len(powers["BPI"]) - sum(powers["MOMENTS"]) / len(powers["MOMENTS"])
    registered = next(r for r in differences if r["scenario"] == args.scenario)
    print()
    print(f"scenario delta (equal-weight over 4 conditions): {delta:.8f}")
    print(f"registered canonical difference               : {registered['difference']:.8f} "
          f"[{registered['lower95']:.6f}, {registered['upper95']:.6f}]")
    print(f"match: {abs(delta - registered['difference']) < 5e-6}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
