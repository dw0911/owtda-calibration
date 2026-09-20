#!/usr/bin/env python3
"""Level 3 full-reproduction entry point: run the frozen Monte Carlo from scratch.

This script re-runs the H0 (NULL) and H1 (ALT) Monte Carlo directly from the
in-repo code plus the two frozen identity files committed in the repository::

  governance/FREEZE_MANIFEST.json     # frozen identity (project/protocol/freeze ids)
  governance/SEED_REGISTRY_v1.0.json  # frozen data / M0 / M1 root keys

It writes the scientific ledgers and prints the produced counts, so a reviewer
can re-aggregate them and compare against the committed canonical results::

  python scripts/reproduce.py --phase NULL --workers 8 --out ./repro
  python scripts/reproduce.py --phase ALT  --workers 8 --out ./repro
  python scripts/analyse_h0.py --from-ledger ./repro/H0_NULL_evaluation.scientific.jsonl

The "from scratch" path needs no archived ledgers, no G4 certificate and no audit
admission layer. Use ``--replicate-limit`` for a smoke-scale run (32 is the
registered smoke size). Requires ``uv sync --frozen``.

Notes:
  * NULL produces the H0 phase: R0 = 2500 per cell, 280,000 evaluation rows.
  * ALT  produces the H1 phase: R1 = 1600 per cell,  51,200 evaluation rows.
  * The ledgers are plain JSON lines (logical rows with numeric floats), the
    format consumed by ``scripts/analyse_h0.py --from-ledger`` /
    ``scripts/analyse_h1.py``.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path
from typing import Any

import numpy as np

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "src"))

from owtda_cal import formal, scope

FREEZE_MANIFEST = REPO / "governance" / "FREEZE_MANIFEST.json"
SEED_REGISTRY = REPO / "governance" / "SEED_REGISTRY_v1.0.json"

LEDGER_FILENAMES: dict[str, dict[str, str]] = {
    scope.PHASE_NULL: {
        "evaluation": "H0_NULL_evaluation.scientific.jsonl",
        "feature": "H0_NULL_feature.scientific.jsonl",
    },
    scope.PHASE_ALT: {
        "evaluation": "H1_ALT_evaluation.scientific.jsonl",
        "feature": "H1_ALT_feature.scientific.jsonl",
    },
}


def _default(value: Any) -> Any:
    """Coerce numpy scalars/arrays to plain JSON types."""
    if isinstance(value, np.integer):
        return int(value)
    if isinstance(value, np.floating):
        return float(value)
    if isinstance(value, np.bool_):
        return bool(value)
    if isinstance(value, np.ndarray):
        return value.tolist()
    raise TypeError(f"not JSON serializable: {type(value).__name__}")


def write_ledger(path: Path, rows: list[dict[str, Any]]) -> int:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(
                json.dumps(row, default=_default, ensure_ascii=False, separators=(",", ":"))
                + "\n"
            )
    return len(rows)


def run_phase(phase: str, args: argparse.Namespace) -> None:
    manifest = json.loads(FREEZE_MANIFEST.read_text(encoding="utf-8"))
    seeds = json.loads(SEED_REGISTRY.read_text(encoding="utf-8"))

    start = time.perf_counter()
    if phase == scope.PHASE_NULL:
        result = formal.run_formal_h0(
            manifest=manifest,
            seed_registry=seeds,
            workers=args.workers,
            replicate_limit=args.replicate_limit,
        )
    else:
        result = formal.run_formal_h1(
            manifest=manifest,
            seed_registry=seeds,
            workers=args.workers,
            replicate_limit=args.replicate_limit,
        )

    filenames = LEDGER_FILENAMES[phase]
    out = Path(args.out)
    eval_path = out / filenames["evaluation"]
    feat_path = out / filenames["feature"]
    eval_rows = write_ledger(eval_path, result.rows)
    feat_rows = write_ledger(feat_path, result.feature_rows)

    wall = time.perf_counter() - start
    print(
        f"[{phase}] data_units={result.data_units} "
        f"evaluation_rows={eval_rows} feature_rows={feat_rows} "
        f"ph_windows={result.ph_windows} errors={result.errors} "
        f"wall={wall:.1f}s"
    )
    print(f"[{phase}] ledgers written to {out.resolve()}")
    print(f"  evaluation : {eval_path.name} ({eval_rows} rows)")
    print(f"  feature    : {feat_path.name} ({feat_rows} rows)")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--phase",
        choices=[scope.PHASE_NULL, scope.PHASE_ALT, "H0", "H1"],
        default=scope.PHASE_NULL,
        help="NULL/H0 for the null phase, ALT/H1 for the alternative phase",
    )
    parser.add_argument("--workers", type=int, default=1, help="process workers")
    parser.add_argument(
        "--replicate-limit", type=int, default=None,
        help="cap replicates per cell (e.g. 32 for a smoke-scale run)",
    )
    parser.add_argument("--out", type=Path, default=REPO / "data" / "reproduced",
                        help="output directory for the ledgers")
    args = parser.parse_args(argv)

    if args.phase in ("H0",):
        args.phase = scope.PHASE_NULL
    elif args.phase in ("H1",):
        args.phase = scope.PHASE_ALT

    run_phase(args.phase, args)
    return 0


if __name__ == "__main__":
    sys.exit(main())
