#!/usr/bin/env python
"""G0 identity validator (v1 skeleton, B03).

Runs from the repository root::

    python audit/validate_identity.py

Checks implemented here are the subset of Plan §17 G0 that is meaningful before
freeze: prior-archive integrity, charter/claim-matrix presence, plan-baseline
hash, and workspace cleanliness. Remaining G0 items (COMPUTE_FREEZE, git tags,
component/environment manifests, seed registries) close before the 2026-09-23
freeze. Emits an append-only evidence JSON under ``artifacts/audit/``.
"""

from __future__ import annotations

import csv
import hashlib
import json
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
DMB_DIR = REPO_ROOT / "external_prior_evidence" / "DMB_R1"
DMB_ZIP_SHA256 = "38790d48a044bde41fd21bc31c18142b19e6decd2398cf1c3f3b8640f9df933d"
PLAN_FILE = REPO_ROOT / "OWTDA_CAL_R1_COMPLETE_PLAN_v1.0.md"
PLAN_SHA256 = "dca49727def3d31d2f367d58dba157e782946b862c28d29dd8508a6a3cc19ab3"
PROJECT_ID = "owtda-cal-r1"

checks: list[dict] = []


def record(name: str, ok: bool, detail: str) -> None:
    checks.append({"check": name, "status": "PASS" if ok else "FAIL", "detail": detail})


def file_sha256(p: Path) -> str:
    h = hashlib.sha256()
    with open(p, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def git(args: list[str]) -> str:
    out = subprocess.run(
        ["git", "-C", str(REPO_ROOT), *args],
        capture_output=True,
        text=True,
        check=False,
    )
    return out.stdout.strip()


def check_prior_archive() -> None:
    sums_file = DMB_DIR / "SHA256SUMS.txt"
    if not sums_file.exists():
        record("prior_archive_sha256sums", False, "SHA256SUMS.txt missing")
        return
    sums = {}
    for line in sums_file.read_text(encoding="utf-8").splitlines():
        parts = line.split()
        if len(parts) != 2:
            record("prior_archive_sha256sums", False, f"malformed line: {line!r}")
            return
        sums[parts[1]] = parts[0]
    verified = 0
    missing = []
    for rel, want in sums.items():
        fp = DMB_DIR / rel
        if fp.exists() and file_sha256(fp) == want:
            verified += 1
        else:
            missing.append(rel)
    ok = verified == len(sums) and not missing
    record("prior_archive_sha256sums", ok, f"verified {verified}/{len(sums)}; missing/bad={missing}")


def check_archive_manifest() -> None:
    amf = DMB_DIR / "archive_manifest.json"
    if not amf.exists():
        record("archive_manifest", False, "archive_manifest.json missing")
        return
    m = json.loads(amf.read_text(encoding="utf-8"))
    ok = (
        m.get("zip_sha256") == DMB_ZIP_SHA256
        and m.get("all_content_objects_verified") is True
        and m.get("total_object_count") == 25
    )
    record(
        "archive_manifest",
        ok,
        f"zip_sha256={'match' if m.get('zip_sha256')==DMB_ZIP_SHA256 else 'MISMATCH'}; "
        f"objects={m.get('total_object_count')}; verified={m.get('all_content_objects_verified')}",
    )


def check_charter_and_claim_matrix() -> None:
    charter = REPO_ROOT / "governance" / "PROJECT_CHARTER.md"
    claim = REPO_ROOT / "governance" / "CLAIM_MATRIX_v1.0.csv"
    c_ok = charter.exists() and f"`{PROJECT_ID}`" in charter.read_text(encoding="utf-8")
    c_ok = c_ok or charter.read_text(encoding="utf-8").count(PROJECT_ID) >= 1
    claims_ok = False
    if claim.exists():
        rows = list(csv.reader(claim.open(encoding="utf-8")))
        claims_ok = len(rows) == 9 and len(rows[0]) == 6 and [r[0] for r in rows[1:]] == [
            "C1", "C2", "C3", "C4", "C5", "C6", "C7", "C8",
        ]
    record("charter_claim_matrix", c_ok and claims_ok, f"charter_ok={c_ok}; claims_ok={claims_ok}")


def check_plan_baseline() -> None:
    if not PLAN_FILE.exists():
        record("plan_baseline_hash", False, "COMPLETE_PLAN file missing")
        return
    h = file_sha256(PLAN_FILE)
    record("plan_baseline_hash", h == PLAN_SHA256, f"sha256={h}")


def check_workspace_clean() -> None:
    porcelain = git(["status", "--porcelain=v1"])
    stash = git(["stash", "list"])
    ok = porcelain == "" and stash == ""
    record("workspace_clean", ok, f"porcelain_empty={porcelain==''}; stash_empty={stash==''}")


def main() -> int:
    check_prior_archive()
    check_archive_manifest()
    check_charter_and_claim_matrix()
    check_plan_baseline()
    check_workspace_clean()

    all_pass = all(c["status"] == "PASS" for c in checks)
    payload = {
        "schema_version": 1,
        "kind": "identity_check_v1",
        "generated_at_utc": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "repo_head": git(["rev-parse", "HEAD"]),
        "project_id": PROJECT_ID,
        "all_pass": all_pass,
        "checks": checks,
    }
    # --out-dir lets the audit capture clean-state evidence *outside* the repo, so
    # producing the cleanliness proof cannot itself dirty the worktree (P0-1).
    import argparse

    parser = argparse.ArgumentParser(description="G0 identity validator")
    parser.add_argument("--out-dir", default=None)
    args = parser.parse_args()
    out_dir = (
        Path(args.out_dir).expanduser()
        if args.out_dir
        else REPO_ROOT / "artifacts" / "audit"
    )
    out_dir.mkdir(parents=True, exist_ok=True)
    stamp = payload["generated_at_utc"].replace(":", "").replace("-", "").replace("T", "T")
    out_file = out_dir / f"identity_check_{stamp}.json"
    out_file.write_text(json.dumps(payload, ensure_ascii=False, sort_keys=True) + "\n", encoding="utf-8")

    for c in checks:
        print(f"[{c['status']}] {c['check']}: {c['detail']}")
    print(f"ALL_PASS={all_pass}")
    print(f"EVIDENCE={out_file.name} sha256={file_sha256(out_file)}")
    return 0 if all_pass else 1


if __name__ == "__main__":
    sys.exit(main())
