#!/usr/bin/env python3
"""Build the manuscript figure set from the canonical tables (never from hard-coded values).

Generator: ``paper/scripts/make_figures.py`` (writes PDF/SVG/PNG + meta.json into artifacts/figures).

Usage:
  python scripts/build_figures.py            # regenerate (in place) and report the hash delta
  python scripts/build_figures.py --check    # do NOT write: verify every figure meta input hash
"""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
GENERATOR = REPO / "paper" / "scripts" / "make_figures.py"
FIGURES = REPO / "artifacts" / "figures"
LOOKUP_DIRS = (REPO / "artifacts" / "tables", REPO / "results" / "canonical")


def sha256_of(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def check_meta_inputs() -> int:
    candidates: dict[str, Path] = {}
    for directory in LOOKUP_DIRS:
        for path in directory.glob("*"):
            if path.is_file():
                candidates.setdefault(path.name, path)
                candidates.setdefault(path.stem, path)
    bad = unresolved = checked = 0
    for meta_path in sorted(FIGURES.glob("*.meta.json")):
        meta = json.loads(meta_path.read_text(encoding="utf-8-sig"))
        for name, digest in (meta.get("input_sha256") or {}).items():
            checked += 1
            target = candidates.get(name) or candidates.get(Path(name).name) or candidates.get(Path(name).stem)
            if target is None:
                unresolved += 1
                print(f"  UNRESOLVED input {name} ({meta_path.name})")
            elif sha256_of(target) != digest:
                bad += 1
                print(f"  HASH MISMATCH {name} ({meta_path.name})")
    print(f"figure metas: checked={checked} unresolved={unresolved} mismatched={bad}")
    return 1 if (bad or unresolved) else 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args(argv)

    if args.check:
        return check_meta_inputs()

    before = {p.name: sha256_of(p) for p in FIGURES.iterdir() if p.is_file()}
    proc = subprocess.run([sys.executable, str(GENERATOR)], cwd=REPO, capture_output=True, text=True, check=False)
    if proc.returncode != 0:
        print(proc.stdout)
        print(proc.stderr, file=sys.stderr)
        return proc.returncode
    same = changed = new = 0
    for path in sorted(FIGURES.iterdir()):
        if not path.is_file():
            continue
        if path.name not in before:
            new += 1
        elif sha256_of(path) == before[path.name]:
            same += 1
        else:
            changed += 1
    print(f"figures regenerated: byte-identical={same} changed={changed} new={new}")
    print("note: PDF/SVG/meta differ only in embedded metadata (creation date, script hash); PNG is bit-stable.")
    print(proc.stdout.strip())
    return 0


if __name__ == "__main__":
    sys.exit(main())
