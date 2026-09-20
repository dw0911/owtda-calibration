#!/usr/bin/env python3
"""Build ``reproducibility/RELEASE_MANIFEST.json`` — the single identity record of a release.

The manifest is *deterministic for a given commit*: every field comes from git or from file bytes,
never from the wall clock. That lets the release workflow regenerate it and then require
``git diff --exit-code`` to be empty, so a published release can never contain bytes that are not
committed under the tag (2026-09-20 audit finding P0-4).

Fields
  * release: name/version (from CITATION.cff), commit, tree, commit date, tags at HEAD, tracked files
  * artifacts: SHA-256 of the manuscript PDF, the sums file, and tree digests of the canonical
    result / table / figure directories
  * verification: the exact commands a reader can re-run

Usage
  python scripts/build_release_manifest.py            # write the manifest
  python scripts/build_release_manifest.py --check    # fail if the committed manifest is stale
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
OUT = REPO / "reproducibility" / "RELEASE_MANIFEST.json"
CITATION = REPO / "CITATION.cff"

TREES = {
    "results/canonical": REPO / "results" / "canonical",
    "results/bootstrap": REPO / "results" / "bootstrap",
    "artifacts/tables": REPO / "artifacts" / "tables",
    "artifacts/figures": REPO / "artifacts" / "figures",
}
FILES = {
    "paper/main.pdf": REPO / "paper" / "main.pdf",
    "reproducibility/FORMAL_MANIFEST.json": REPO / "reproducibility" / "FORMAL_MANIFEST.json",
    "reproducibility/ARTIFACT_INDEX.csv": REPO / "reproducibility" / "ARTIFACT_INDEX.csv",
    "data/manifests/external_artifacts.json": REPO / "data" / "manifests" / "external_artifacts.json",
}
# NOTE on anchoring direction: ``reproducibility/SHA256SUMS`` covers this manifest (it walks
# ``reproducibility/``), so the manifest must NOT hash SHA256SUMS — that would be circular.
# Run order is therefore: derived artifacts -> build_reproducibility_index.py ->
# build_release_manifest.py -> build_sha256sums.py.

VERIFICATION = [
    "python scripts/verify_release.py --level quick",
    "python scripts/verify_release.py --level analysis",
    "python scripts/bootstrap_primary_contrasts.py --check",
    "python scripts/build_tables.py --check",
    "python paper/scripts/make_tables.py --check",
    "python scripts/build_figures.py --check",
    "python -m pytest tests -q",
]


def sha256_of(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def tree_digest(root: Path) -> str:
    """Deterministic digest of a directory: sha256 over sorted ``<relpath>\\0<sha256>\\n`` lines."""
    digest = hashlib.sha256()
    for path in sorted(p for p in root.rglob("*") if p.is_file()):
        rel = path.relative_to(REPO).as_posix()
        digest.update(f"{rel}\0{sha256_of(path)}\n".encode())
    return digest.hexdigest()


def version_from_citation() -> tuple[str, str]:
    text = CITATION.read_text(encoding="utf-8")
    version = re.search(r"(?m)^version:\s*\"?([^\"\n]+)\"?\s*$", text)
    if not version:
        raise SystemExit("CITATION.cff: cannot read the version field")
    return version.group(1).strip(), f"v{version.group(1).strip()}-paper"


def build() -> dict:
    version, release_name = version_from_citation()
    # Only *content-derived* fields live in this file.
    #
    # A file cannot record the hash/date of the commit that adds it, so commit/tree/branch/tag are
    # deliberately absent: the release workflow regenerates this manifest and then requires
    # ``git diff --exit-code`` to be empty, which is only possible if regeneration is byte-stable
    # at the tagged commit. Commit and tag identity are asserted by the workflow
    # (``git describe --exact-match``) and recorded in the delivered verification report.
    manifest = {
        "schema_version": 1,
        "kind": "RELEASE_MANIFEST",
        "release": {
            "name": release_name,
            "version": version,
        },
        # DOI 槽位（P0-6）：Zenodo 归档闭合前保持 null，禁止填写占位/虚构 DOI。
        # 代码 DOI 由 GitHub release 触发 Zenodo 自动归档得到；数据 DOI 由账本 dataset record 得到。
        "doi": {
            "code": None,
            "data": None,
            "note": "Filled in after both Zenodo deposits are closed (see "
                    "reproducibility/DATA_AVAILABILITY.md §3); null means 'not yet deposited'.",
        },
        "artifacts": {name: sha256_of(path) for name, path in sorted(FILES.items())},
        "tree_digests": {name: tree_digest(path) for name, path in sorted(TREES.items())},
        "verification_commands": VERIFICATION,
        "notes": [
            "Content-derived only: no wall-clock, branch, commit or tag fields, so regenerating "
            "this file at the tagged commit leaves the tree clean (`git diff --exit-code`).",
            "Commit/tag identity: asserted by the release workflow (`git describe --exact-match` "
            "must equal release.name) and recorded in the delivered verification report, which is "
            "generated after the commit exists.",
            "The formal 3.2 GB ledgers are not distributed; see data/manifests/ and "
            "reproducibility/DATA_AVAILABILITY.md for the external archive DOI.",
            "Tree digests cover results/canonical, results/bootstrap, artifacts/tables and "
            "artifacts/figures; every paper number derives from those files.",
        ],
    }
    return manifest


def serialize(manifest: dict) -> str:
    return json.dumps(manifest, indent=2, sort_keys=True, ensure_ascii=False) + "\n"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--check", action="store_true", help="fail if the committed manifest is stale")
    args = parser.parse_args(argv)

    fresh = serialize(build())
    if args.check:
        if not OUT.exists():
            print(f"MISSING {OUT.relative_to(REPO)}")
            return 1
        committed = OUT.read_text(encoding="utf-8")
        if committed != fresh:
            print(f"STALE {OUT.relative_to(REPO)} — regenerate with scripts/build_release_manifest.py")
            return 1
        print(f"release manifest: OK ({json.loads(fresh)['release']['name']})")
        return 0

    OUT.write_text(fresh, encoding="utf-8", newline="\n")
    manifest = json.loads(fresh)
    print(
        f"wrote {OUT.relative_to(REPO)} — {manifest['release']['name']} "
        f"({len(manifest['artifacts'])} artifact hashes, {len(manifest['tree_digests'])} tree digests)"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
