#!/usr/bin/env python3
"""H1 layer of the analysis chain.

* ``--check`` (default): verify the committed H1 canonical objects - 16 cell-feature rows,
  ``n = 1600``, ``M = floor((T - W) / s) + 1``, empirical critical rank 2376, and that the
  scenario differences equal the equal-weight BPI minus MOMENTS means over the four conditions.
* ``--from-ledgers``: delegate to the registered ledger-level reanalysis
  ``release/analysis/scripts/reanalyse_h1.py`` (requires ``--delivery --h0-eval --h1-eval --out-dir``).
  This wrapper does not re-implement that chain; it only forwards explicit arguments.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
CANON = REPO / "results" / "canonical"
REGISTERED = REPO / "release" / "analysis" / "scripts" / "reanalyse_h1.py"


def load(path: Path):
    return json.loads(path.read_text(encoding="utf-8-sig"))


def check_canonical() -> int:
    h1 = load(CANON / "H1_REANALYSIS.json")
    cells = h1["percell"]
    problems: list[str] = []
    keys = {(c["scenario_id"], c["feature_id"], int(c["stride"]), str(c["rho"])) for c in cells}
    if len(cells) != 16 or len(keys) != 16:
        problems.append(f"rows={len(cells)} unique_keys={len(keys)}")
    means: dict[tuple[str, str], list[float]] = {}
    for cell in cells:
        w, stride, t = int(cell["W"]), int(cell["stride"]), int(cell["T"])
        if not (w > 0 and stride > 0 and t >= w and (t - w) // stride + 1 >= 1):
            problems.append(f"{cell['logical_cell_id'][:8]}: geometry")
        if int(cell.get("critical_rank", 2376)) != 2376:
            problems.append(f"{cell['logical_cell_id'][:8]}: critical_rank")
        label = "BPI" if cell["feature_id"].startswith("BPI") else "MOMENTS"
        means.setdefault((cell["scenario_id"], label), []).append(float(cell["size_standardized_power"]))

    differences = load(CANON / "H1_SCENARIO_DIFFERENCES.json")
    for row in differences:
        scenario = row["scenario"]
        bpi = means.get((scenario, "BPI"), [])
        moments = means.get((scenario, "MOMENTS"), [])
        if not bpi or not moments:
            problems.append(f"{scenario}: missing scenario means")
            continue
        delta = sum(bpi) / len(bpi) - sum(moments) / len(moments)
        if abs(delta - row["difference"]) > 5e-6:
            problems.append(f"{scenario}: delta {delta} != {row['difference']}")
        if not row["lower95"] <= row["difference"] <= row["upper95"]:
            problems.append(f"{scenario}: CI does not bracket the estimate")

    if problems:
        print(f"H1 canonical: FAIL ({len(problems)} problems)")
        for item in problems[:12]:
            print(f"  - {item}")
        return 1
    print("H1 canonical: OK (16 cell-feature rows / geometry / critical rank / scenario deltas)")
    return 0


def from_ledgers(passthrough: list[str]) -> int:
    if not REGISTERED.exists():
        print(f"registered reanalysis script missing: {REGISTERED}")
        return 1
    argv = [sys.executable, str(REGISTERED), *passthrough]
    print("running:", " ".join(argv))
    return subprocess.run(argv, cwd=REPO, check=False).returncode


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true")
    parser.add_argument("--from-ledgers", action="store_true")
    parser.add_argument("--delivery", type=Path, default=None)
    parser.add_argument("--h0-eval", type=Path, default=None)
    parser.add_argument("--h1-eval", type=Path, default=None)
    parser.add_argument("--out-dir", type=Path, default=None)
    parser.add_argument("--bootstrap-context", type=Path, default=None)
    args = parser.parse_args(argv)

    if args.from_ledgers:
        passthrough: list[str] = []
        for name in ("delivery", "h0_eval", "h1_eval", "out_dir", "bootstrap_context"):
            value = getattr(args, name)
            if value is not None:
                passthrough += ["--" + name.replace("_", "-"), str(value)]
        if not passthrough:
            print("pass --delivery --h0-eval --h1-eval --out-dir (see release/analysis/scripts/reanalyse_h1.py --help)")
            return 2
        return from_ledgers(passthrough)
    return check_canonical()


if __name__ == "__main__":
    sys.exit(main())
