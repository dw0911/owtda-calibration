#!/usr/bin/env python3
"""Fetch and verify the archived large artifacts (formal ledgers, large indices).

The archives are *not* distributed with the repository. They are listed in
``data/manifests/external_artifacts.json`` with size and SHA-256; this script verifies a local
copy, downloads from a URL when one is registered, and refuses anything whose hash differs.

Usage:
  python scripts/fetch_archived_data.py --list
  python scripts/fetch_archived_data.py --verify-only
  python scripts/fetch_archived_data.py --report-only    # same, but always exit 0 (informational)
  python scripts/fetch_archived_data.py                 # fetch into data/external/
  python scripts/fetch_archived_data.py --only H0_EVALUATION_LEDGER

Exit codes (2026-09-20 audit finding P0-6)
  0  every requested artifact was fetched/verified locally
  1  a fetched artifact failed its size/SHA-256 check
  2  at least one requested artifact is still unavailable (no DOI/URL registered, no local copy)

Level 2 (ledger-level) reproduction needs those artifacts, so an unavailable archive must not be
reported as success. The formal ledgers are not distributed; the synthetic experiment is fully
reproducible without them (Level 1 verification + Level 3 from-scratch reproduction via
``scripts/reproduce.py``).
"""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import sys
import urllib.request
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
MANIFEST = REPO / "data" / "manifests" / "external_artifacts.json"
DEFAULT_DEST = REPO / "data" / "external"


def sha256_of(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(8 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def resolve_source(entry: dict, target: Path) -> Path | None:
    """A registered ``local_source`` may be the archive file itself or the directory holding it.

    Treating a directory as a file made ``stat().st_size`` compare a directory entry against the
    registered byte count and report a bogus SIZE MISMATCH (2026-09-20 audit finding P0-6).
    """
    candidates: list[Path] = [target]
    if entry.get("local_source"):
        candidates.append(Path(entry["local_source"]))
    for candidate in candidates:
        if candidate.is_file():
            return candidate
        if candidate.is_dir():
            inner = candidate / entry["filename"]
            if inner.is_file():
                return inner
    return None


def verify(path: Path, entry: dict) -> bool:
    size = entry.get("size_bytes")
    if size is not None and path.stat().st_size != int(size):
        print(f"  SIZE MISMATCH {path.name}: {path.stat().st_size} != {size}")
        return False
    digest = sha256_of(path)
    if digest != entry.get("sha256"):
        print(f"  SHA256 MISMATCH {path.name}: {digest[:16]}... != {entry.get('sha256', '')[:16]}...")
        return False
    return True


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dest", type=Path, default=DEFAULT_DEST)
    parser.add_argument("--list", action="store_true")
    parser.add_argument("--verify-only", action="store_true",
                        help="verify a local copy; exit 2 when a requested artifact is unavailable")
    parser.add_argument("--report-only", action="store_true",
                        help="report the manifest status but always exit 0 (informational)")
    parser.add_argument("--only", default=None)
    args = parser.parse_args(argv)

    if not MANIFEST.exists():
        print(f"manifest missing: {MANIFEST}")
        return 1
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8-sig"))
    entries = [e for e in manifest["artifacts"] if args.only is None or e["name"] == args.only]
    if not entries:
        print("no matching artifact")
        return 1

    if args.list:
        for entry in entries:
            print(
                f"{entry['name']:<28} {entry.get('size_bytes', 0):>13,} B  "
                f"sha256={entry['sha256'][:16]}...  doi={entry.get('doi') or 'PENDING'}  {entry.get('filename')}"
            )
        return 0

    failures = verified = pending = 0
    unavailable: list[str] = []
    for entry in entries:
        target = args.dest / entry["filename"]
        source = resolve_source(entry, target)
        if source is None and entry.get("url"):
            if args.verify_only:
                pending += 1
                print(f"{entry['name']}: not downloaded yet (url registered)")
                continue
            target.parent.mkdir(parents=True, exist_ok=True)
            print(f"{entry['name']}: downloading {entry['url']}")
            with urllib.request.urlopen(entry["url"]) as response, target.open("wb") as out:
                shutil.copyfileobj(response, out)
            source = target
        if source is None:
            pending += 1
            unavailable.append(entry["name"])
            print(f"{entry['name']}: NOT AVAILABLE (DOI/url pending; {entry.get('note', 'see manifest')})")
            continue
        if verify(source, entry):
            verified += 1
            print(f"{entry['name']}: verified ({source})")
        else:
            failures += 1
    print(f"fetched/verified={verified} pending={pending} failures={failures}")
    if failures:
        return 1
    if pending and not args.report_only:
        print(
            f"\n{pending} requested artifact(s) are unavailable: {', '.join(unavailable)}\n"
            "  -> Level 2 (ledger-level) reproduction cannot run to completion.\n"
            "  -> Level 1 remains fully verifiable:  python scripts/verify_release.py --level quick\n"
            "  -> Archive status: reproducibility/DATA_AVAILABILITY.md\n"
            "  -> Use --report-only to list the manifest without a non-zero exit."
        )
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
