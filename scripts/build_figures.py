#!/usr/bin/env python3
"""Build the manuscript figure set from the canonical tables (never from hard-coded values).

Generator: ``paper/scripts/make_figures.py`` (writes PDF/SVG/PNG + meta.json into artifacts/figures).

Usage:
  python scripts/build_figures.py            # regenerate (in place) and report the hash delta
  python scripts/build_figures.py --check    # do NOT write: verify the figure provenance chain

``--check`` verifies, for every non-legacy figure meta:
  * every recorded input hash resolves inside the repository and matches its file;
  * ``script_sha256`` equals the hash of the *current* ``paper/scripts/make_figures.py``
    (the 2026-09-20 audit flagged stale generator hashes as a provenance gap);
  * every recorded output hash matches the committed PDF/SVG/PNG bytes;
  * the manuscript figure is actually referenced by a ``.tex`` file.
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
LOOKUP_DIRS = (REPO / "artifacts" / "tables", REPO / "results" / "canonical", REPO / "results" / "bootstrap")

MANUSCRIPT_FIGURES = {
    # Figure1_method_schematic moved to TikZ source (paper/figures/) — 2026-09-21 audit.
    "Figure2_alternative_geometry",
    "Figure3_M0_type1_surface",
    "Figure4_M1_deviation_surface",
    "Figure5_H1_power_and_difference",
}


def sha256_of(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load(path: Path):
    return json.loads(path.read_text(encoding="utf-8-sig"))


def check_provenance() -> int:
    candidates: dict[str, Path] = {}
    for directory in LOOKUP_DIRS:
        for path in directory.glob("*"):
            if path.is_file():
                candidates.setdefault(path.name, path)
                candidates.setdefault(path.stem, path)

    generator_sha = sha256_of(GENERATOR)
    checked = unresolved = mismatch = 0
    problems: list[str] = []

    for meta_path in sorted(FIGURES.glob("*.meta.json")):
        meta = load(meta_path)
        stem = meta_path.name[: -len(".meta.json")]

        for name, digest in (meta.get("input_sha256") or {}).items():
            checked += 1
            target = candidates.get(name) or candidates.get(Path(name).name) or candidates.get(Path(name).stem)
            if target is None:
                unresolved += 1
                print(f"  UNRESOLVED input {name} ({meta_path.name})")
            elif sha256_of(target) != digest:
                mismatch += 1
                print(f"  HASH MISMATCH {name} ({meta_path.name})")

        if meta.get("script_sha256") != generator_sha:
            problems.append(f"{meta_path.name}: script_sha256 does not match paper/scripts/make_figures.py")

        outputs = meta.get("outputs") or {}
        if not outputs:
            problems.append(f"{meta_path.name}: outputs missing (regenerate: python scripts/build_figures.py)")
        for out_name, digest in outputs.items():
            target = FIGURES / out_name
            if not target.exists():
                problems.append(f"{meta_path.name}: output {out_name} missing")
            elif sha256_of(target) != digest:
                problems.append(f"{meta_path.name}: output {out_name} hash mismatch")

        if stem in MANUSCRIPT_FIGURES and not meta.get("referenced_by"):
            problems.append(f"{stem}: not referenced by any manuscript .tex file")

    print(
        f"figure provenance: metas={len(list(FIGURES.glob('*.meta.json')))} inputs_checked={checked} "
        f"unresolved={unresolved} mismatched={mismatch}"
    )
    for problem in problems:
        print(f"  PROBLEM {problem}")
    return 1 if (unresolved or mismatch or problems) else 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args(argv)

    if args.check:
        return check_provenance()

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
    print("note: PNG/SVG are byte-stable on a given matplotlib version (SVG dc:date is stripped, "
          "PDF creation/mod dates are suppressed); a different matplotlib version may re-render.")
    print(proc.stdout.strip())
    return 0


if __name__ == "__main__":
    sys.exit(main())
