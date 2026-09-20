#!/usr/bin/env python3
"""Level 3 entry point for a formal phase (H0/NULL by default; H1/ALT via scripts/run_h1.py).

This script does **not** re-implement the formal run. It validates the frozen prerequisites
and then delegates to the single authorised runner ``scripts/run_formal.py``:

  scripts/run_formal.py --plan <dir> --certificate <json> --seed-registry <json> --out <dir>

Prerequisites (fail-closed): the plan directory must contain ``PLAN_SUMMARY.json``; the
certificate and the seed registry must exist when given; ``--out`` must not exist. Use
``--dry-run`` to print the resolved command and the prerequisite report without running.

A full phase is a multi-hour computation - see reproducibility/COMPUTE_REQUIREMENTS.md.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
RUNNER = REPO / "scripts" / "run_formal.py"


def prerequisites(plan: Path, certificate: Path | None, seed_registry: Path | None, out: Path) -> list[str]:
    problems: list[str] = []
    if not (plan / "PLAN_SUMMARY.json").exists():
        problems.append(f"plan summary missing: {plan / 'PLAN_SUMMARY.json'}")
    if certificate is not None and not certificate.exists():
        problems.append(f"certificate missing: {certificate}")
    if seed_registry is not None and not seed_registry.exists():
        problems.append(f"seed registry missing: {seed_registry}")
    if out.exists():
        problems.append(f"evidence dir must not exist: {out}")
    return problems


def main(argv: list[str] | None = None, default_phase: str = "NULL") -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--plan", type=Path, required=True, help="frozen plan directory (PLAN_SUMMARY.json)")
    parser.add_argument("--certificate", type=Path, default=None)
    parser.add_argument("--seed-registry", type=Path, default=None)
    parser.add_argument("--out", type=Path, required=True, help="evidence directory (must not exist)")
    parser.add_argument("--phase", default=default_phase)
    parser.add_argument("--workers", type=int, default=1)
    parser.add_argument("--replicate-limit", type=int, default=None)
    parser.add_argument("--config", type=Path, default=None, help="configs/formal/<phase>.json (recorded only)")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args(argv)

    problems = prerequisites(args.plan, args.certificate, args.seed_registry, args.out)
    if args.config is not None and not args.config.exists():
        problems.append(f"config missing: {args.config}")
    if args.config is not None and args.config.exists():
        json.loads(args.config.read_text(encoding="utf-8-sig"))  # fail-closed on broken config

    command = [
        sys.executable, str(RUNNER),
        "--plan", str(args.plan),
        "--out", str(args.out),
        "--phase", args.phase,
        "--workers", str(args.workers),
    ]
    if args.certificate is not None:
        command += ["--certificate", str(args.certificate)]
    if args.seed_registry is not None:
        command += ["--seed-registry", str(args.seed_registry)]
    if args.replicate_limit is not None:
        command += ["--replicate-limit", str(args.replicate_limit)]

    print("resolved command:", " ".join(command))
    if problems:
        for item in problems:
            print(f"BLOCKED: {item}")
        return 2
    print("prerequisites: OK")
    if args.dry_run:
        return 0
    return subprocess.run(command, cwd=REPO, check=False).returncode


if __name__ == "__main__":
    sys.exit(main())
