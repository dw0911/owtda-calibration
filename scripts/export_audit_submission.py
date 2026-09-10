"""Export the sealed audit submission into one browsable folder (Plan §20.1).

Creates ``<target>/`` containing

  * ``OWTDA-CAL-R1-AUDIT-SUBMISSION-20260910.zip`` + its ``.sha256`` sidecar,
  * ``PACKAGE_MANIFEST.sha256``,
  * ``00_START_HERE.md`` (handover cover) and the human/machine submission docs,
  * ``package/`` -- the archive extracted verbatim, verifiable in place against
    its own ``SHA256SUMS.txt``.

The cover and the submission docs live **outside** the sealed package on purpose
(``artifacts/archive/`` is excluded from the archive, and the package must stay a
pure evidence object); this exporter is the only supported way to build the
handover folder, so the folder is reproducible from the repo alone.

Usage::

    python scripts/export_audit_submission.py --target "C:/Users/<me>/Desktop/<SUBMISSION_ID>"
"""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import sys
import zipfile
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "src"))

SUBMISSION_ID = "OWTDA-CAL-R1-AUDIT-SUBMISSION-20260910"
ARCHIVE_DIR = REPO / "artifacts" / "archive"
ZIP_PATH = ARCHIVE_DIR / f"{SUBMISSION_ID}.zip"
COVER = ARCHIVE_DIR / f"{SUBMISSION_ID}_HANDOVER.md"
DELIVERY_DIR = REPO.parent / "_incoming" / "OWTDA_CAL_R1_AUDIT_SUBMISSION_20260910"
DELIVERY_DOCS = (
    "AUDIT_SUBMISSION_RECORD.md",
    "OPEN_ISSUES_AND_DECISIONS.md",
    "AUDIT_REQUEST.json",
    "PACKAGE_MANIFEST.sha256",
)
SELF_REFERENTIAL = ("SHA256SUMS.txt", "package_manifest.json")


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def _extract(zip_path: Path, package_dir: Path) -> int:
    shutil.rmtree(package_dir, ignore_errors=True)
    with zipfile.ZipFile(zip_path) as zf:
        for info in zf.infolist():
            rel = info.filename.split("/", 1)[1]
            target = package_dir / rel
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(zf.read(info.filename))
    return sum(1 for p in package_dir.rglob("*") if p.is_file())


def _verify(package_dir: Path, expected_zip_sha: str) -> dict[str, object]:
    sums = [
        line
        for line in (package_dir / "SHA256SUMS.txt")
        .read_text(encoding="utf-8")
        .splitlines()
        if line.strip()
    ]
    sums_bad = [
        rel
        for line in sums
        for digest, rel in [line.split("  ", 1)]
        if rel not in SELF_REFERENTIAL
        and _sha256(package_dir / rel) != digest
    ]
    manifest = json.loads(
        (package_dir / "package_manifest.json").read_text(encoding="utf-8")
    )
    manifest_bad = [
        obj["path"]
        for obj in manifest["objects"]
        if _sha256(package_dir / obj["path"]) != obj["sha256"]
    ]
    zip_sha = _sha256(ZIP_PATH)
    return {
        "sums_entries": len(sums),
        "sums_mismatched": len(sums_bad),
        "manifest_objects": len(manifest["objects"]),
        "manifest_mismatched": len(manifest_bad),
        "zip_sha256": zip_sha,
        "zip_sha256_matches_sidecar": zip_sha == expected_zip_sha,
        "verified": not sums_bad
        and not manifest_bad
        and zip_sha == expected_zip_sha,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="export audit submission folder")
    parser.add_argument("--target", required=True, help="destination folder")
    args = parser.parse_args()

    if not ZIP_PATH.exists():
        raise SystemExit(f"sealed package missing: {ZIP_PATH}")
    sidecar = (ARCHIVE_DIR / f"{SUBMISSION_ID}.zip.sha256").read_text(encoding="utf-8")
    expected_zip_sha = sidecar.split()[0]

    target = Path(args.target).expanduser()
    target.mkdir(parents=True, exist_ok=True)

    files = _extract(ZIP_PATH, target / "package")
    shutil.copyfile(ZIP_PATH, target / ZIP_PATH.name)
    shutil.copyfile(ARCHIVE_DIR / f"{ZIP_PATH.name}.sha256", target / f"{ZIP_PATH.name}.sha256")
    shutil.copyfile(COVER, target / "00_START_HERE.md")
    for name in DELIVERY_DOCS:
        source = DELIVERY_DIR / name
        if source.exists():
            shutil.copyfile(source, target / name)

    result = _verify(target / "package", expected_zip_sha)
    (target / "EXPORT_VERIFY.json").write_text(
        json.dumps(
            {"target": str(target), "extracted_files": files, **result},
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )

    print(f"target              = {target}")
    print(f"extracted_files     = {files}")
    print(f"sums_mismatched     = {result['sums_mismatched']}")
    print(f"manifest_mismatched = {result['manifest_mismatched']}")
    print(f"zip_sha256          = {result['zip_sha256']}")
    print(f"verified            = {result['verified']}")
    return 0 if result["verified"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
