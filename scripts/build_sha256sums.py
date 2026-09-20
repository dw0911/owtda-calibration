#!/usr/bin/env python3
"""Write ``reproducibility/SHA256SUMS`` for the distributed (small) artifacts.

Covered trees: ``results/``, ``artifacts/{figures,tables,seals,preflight}``, ``data/manifests/``
and ``reproducibility/`` itself (excluding ``SHA256SUMS``). Large external artifacts are covered
by ``data/manifests/external_artifacts.json`` instead (they are not distributed).

Run after any change to the covered trees; ``scripts/verify_release.py`` verifies every line.
"""

from __future__ import annotations

import hashlib
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
TARGETS = (
    "results",
    "artifacts/figures",
    "artifacts/tables",
    "data/manifests",
    "reproducibility",
)
EXCLUDE_NAMES = {"SHA256SUMS"}


def sha256_of(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(8 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def main() -> int:
    lines: list[str] = []
    for rel in TARGETS:
        base = REPO / rel
        if not base.exists():
            continue
        for path in sorted(base.rglob("*")):
            if path.is_file() and path.name not in EXCLUDE_NAMES:
                lines.append(f"{sha256_of(path)}  {path.relative_to(REPO).as_posix()}")
    target = REPO / "reproducibility" / "SHA256SUMS"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"wrote reproducibility/SHA256SUMS ({len(lines)} entries)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
