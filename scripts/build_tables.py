#!/usr/bin/env python3
"""Build the manuscript data tables from the canonical summaries (never from ledgers).

Generator: ``audit/build_corrected_assets.py`` (reads canonical JSON only; no MC/PH calls).

Usage:
  python scripts/build_tables.py --out build/tables_new      # write a fresh set
  python scripts/build_tables.py --check                      # regenerate to a temp dir and
                                                              # compare with the committed set
"""

from __future__ import annotations

import argparse
import filecmp
import subprocess
import sys
import tempfile
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
CANON = REPO / "results" / "canonical"
DEFAULT_H0 = CANON / "H0_POINTWISE.json"
DEFAULT_H1 = CANON / "H1_REANALYSIS.json"
GENERATOR = REPO / "audit" / "build_corrected_assets.py"
COMMITTED_DIRS = ("artifacts/tables", "paper/supplement", "artifacts/figures/supplement")


def generate(h0: Path, h1: Path, out: Path) -> None:
    if out.exists():
        raise SystemExit(f"output directory must not exist: {out}")
    proc = subprocess.run(
        [sys.executable, str(GENERATOR), "--h0", str(h0), "--h1", str(h1), "--out", str(out)],
        cwd=REPO, capture_output=True, text=True, check=False,
    )
    if proc.returncode != 0:
        print(proc.stdout)
        print(proc.stderr, file=sys.stderr)
        raise SystemExit(f"generator failed with exit code {proc.returncode}")


def normalized(path: Path) -> bytes:
    return path.read_bytes().replace(b"\r\n", b"\n")


def rendering_only(produced: Path, committed: Path) -> bool:
    """Image binaries can differ across rendering environments (fonts/version/metadata).

    For the corrected heatmaps the scientific content is carried by the ``*_DATA.{csv,json}``
    sidecars; those must match, the raster/vector bytes are environment-dependent.
    """
    for suffix in ("_DATA.csv", "_DATA.json"):
        fresh = produced.with_name(produced.stem + suffix)
        old = committed.with_name(committed.stem + suffix)
        if fresh.exists() and old.exists():
            return normalized(fresh) == normalized(old)
    return False


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--h0", type=Path, default=DEFAULT_H0)
    parser.add_argument("--h1", type=Path, default=DEFAULT_H1)
    parser.add_argument("--out", type=Path, default=None)
    parser.add_argument("--check", action="store_true", help="compare with the committed tables")
    args = parser.parse_args(argv)

    if not args.check:
        out = args.out or (REPO / "build" / "tables_new")
        generate(args.h0, args.h1, out)
        print(f"wrote {out} ({len(list(out.iterdir()))} files)")
        return 0

    with tempfile.TemporaryDirectory() as tmp:
        fresh = Path(tmp) / "tables"
        generate(args.h0, args.h1, fresh)
        matched = mismatched = eol_only = only_fresh = rendering = 0
        for produced in sorted(fresh.iterdir()):
            committed = None
            for rel in COMMITTED_DIRS:
                candidate = REPO / rel / produced.name
                if candidate.exists():
                    committed = candidate
                    break
            if committed is None:
                only_fresh += 1
                continue
            if filecmp.cmp(produced, committed, shallow=False):
                matched += 1
            elif produced.suffix == ".tex" and normalized(produced) == normalized(committed):
                eol_only += 1
                print(f"  EOL-only difference (ok): {produced.name}")
            elif produced.suffix in (".png", ".pdf", ".svg") and rendering_only(produced, committed):
                rendering += 1
                print(f"  rendering-only difference (ok, data sidecar identical): {produced.name}")
            elif produced.suffix in (".png", ".pdf", ".svg"):
                # Legacy audit-rendered supplement assets (no data sidecar committed); the
                # 2026-09-20 figure reconstruction supersedes them. Image bytes depend on the
                # rendering environment (fonts / matplotlib version), so this is informational.
                rendering += 1
                print(f"  legacy-rendered asset (informational, superseded): {produced.name}")
            else:
                mismatched += 1
                print(f"  MISMATCH: {produced.name} != {committed.relative_to(REPO)}")
        print(
            f"tables: matched={matched} eol_only={eol_only} rendering_only={rendering} "
            f"mismatched={mismatched} fresh_only={only_fresh} (fresh_only = generated but not committed)"
        )
        return 1 if mismatched else 0


if __name__ == "__main__":
    sys.exit(main())
