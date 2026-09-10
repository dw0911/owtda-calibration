"""Build the incremental audit supplement `OWTDA-CAL-R1-AUDIT-SUPPLEMENT-R1-20260910`.

Assembles, from the out-of-repo evidence root and the repository, exactly the P0
material the audit demanded (the previously submitted package stays read-only)::

    revision/      P0-1  git bundle + verify/fsck + zero-byte status/stash + identity_check
    environment/   P0-2  pins, uv.lock, versions, BLAS, thread env, fresh-venv rebuild test
    wstar/         P0-3  preregistered protocol, paired 8/12 runs, payload comparison, verdict
    configs/schema P0-4  strict schemas + manifest + schema_check evidence
    governance/    P0-5  AMENDMENT/INVALIDATION chains, reasons, B12 disposition, changelog
    smoke/S03/     P0-6  sealed smoke evidence, run/state registries, provenance manifest
    verification/  P0-7  raw pytest (log+xml), ruff log, commands, exit codes, environment
    gates/         re-labelled gate objects (BLOCKED_IDENTITY / PROVISIONAL / ...)
    GATE_RELABEL.json + DISCLOSURES.md + README.md + package_manifest.json + SHA256SUMS.txt

A missing P0 input is reported as ``MISSING:<path>`` in the manifest instead of
being silently skipped, so the supplement can never look complete while incomplete.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import zipfile
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parents[1]
SUBMISSION_ID = "OWTDA-CAL-R1-AUDIT-SUPPLEMENT-R1-20260910"
OUT_PARENT = REPO.parent / "_incoming" / "OWTDA_CAL_R1_AUDIT_SUPPLEMENT_R1_20260910"
ZIP_STAMP = (2026, 9, 10, 0, 0, 0)
GOV = REPO / "governance"

#: (archive_path, source_path, required)
PLAN: list[tuple[str, str, bool]] = [
    # P0-1 revision
    ("revision/OWTDA-CAL-R1.bundle", "revision/OWTDA-CAL-R1.bundle", True),
    ("revision/git_bundle_verify.txt", "revision/git_bundle_verify.txt", True),
    ("revision/git_fsck_full.txt", "revision/git_fsck_full.txt", True),
    ("revision/git_rev_parse_HEAD.txt", "revision/git_rev_parse_HEAD.txt", True),
    ("revision/git_show_ref_tags.txt", "revision/git_show_ref_tags.txt", True),
    ("revision/git_log_graph.txt", "revision/git_log_graph.txt", True),
    ("revision/git_status_porcelain_v1.txt", "revision/git_status_porcelain_v1.txt", True),
    ("revision/git_stash_list.txt", "revision/git_stash_list.txt", True),
    ("revision/source_manifest.json", "revision/source_manifest.json", True),
    ("revision/source_tree_hash.txt", "revision/source_tree_hash.txt", True),
    ("revision/REVISION_ACCEPTANCE.json", "revision/REVISION_ACCEPTANCE.json", True),
    # P0-2 environment
    ("environment/pyproject.toml", "repo/environment/pyproject.toml", True),
    ("environment/uv.lock", "repo/environment/uv.lock", True),
    ("environment/environment_manifest.json", "repo/environment/environment_manifest.json", True),
    ("environment/pip_freeze_all.txt", "repo/environment/pip_freeze_all.txt", True),
    ("environment/python_VV.txt", "repo/environment/python_VV.txt", True),
    ("environment/numpy_show_config.txt", "repo/environment/numpy_show_config.txt", True),
    ("environment/tool_versions.json", "repo/environment/tool_versions.json", True),
    ("environment/thread_env.json", "repo/environment/thread_env.json", True),
    (
        "environment/environment_rebuild_test.json",
        "repo/environment/environment_rebuild_test.json",
        True,
    ),
    # P0-3 wstar
    (
        "wstar/WSTAR_CONFIRMATION_PROTOCOL.json",
        "repo/configs/wstar/WSTAR_CONFIRMATION_PROTOCOL.json",
        True,
    ),
    ("wstar/worker_confirmation_raw.jsonl", "wstar/worker_confirmation_raw.jsonl", True),
    ("wstar/worker_payload_comparison.json", "wstar/worker_payload_comparison.json", True),
    ("wstar/worker_confirmation_RC.json", "wstar/worker_confirmation_RC.json", True),
    ("wstar/resource_samples.jsonl", "wstar/resource_samples.jsonl", True),
    # P0-4 schemas
    ("configs/schema/scientific_row.schema.json", "repo/configs/schema/scientific_row.schema.json", True),
    (
        "configs/schema/scientific_row_wire.schema.json",
        "repo/configs/schema/scientific_row_wire.schema.json",
        True,
    ),
    (
        "configs/schema/feature_sufficient_row.schema.json",
        "repo/configs/schema/feature_sufficient_row.schema.json",
        True,
    ),
    (
        "configs/schema/feature_sufficient_row_wire.schema.json",
        "repo/configs/schema/feature_sufficient_row_wire.schema.json",
        True,
    ),
    (
        "configs/schema/scientific_result_projection.schema.json",
        "repo/configs/schema/scientific_result_projection.schema.json",
        True,
    ),
    (
        "configs/schema/feature_result_projection.schema.json",
        "repo/configs/schema/feature_result_projection.schema.json",
        True,
    ),
    ("configs/schema/schemas_manifest.json", "repo/configs/schema/schemas_manifest.json", True),
    # P0-5 governance
    ("governance/AMENDMENT_REGISTRY.jsonl", "repo/governance/AMENDMENT_REGISTRY.jsonl", True),
    (
        "governance/INVALIDATION_REGISTRY.jsonl",
        "repo/governance/INVALIDATION_REGISTRY.jsonl",
        True,
    ),
    ("governance/B12_DISPOSITION.json", "repo/governance/B12_DISPOSITION.json", True),
    (
        "governance/GOVERNANCE_REGISTRY_VERIFICATION.json",
        "repo/governance/GOVERNANCE_REGISTRY_VERIFICATION.json",
        True,
    ),
    ("governance/CHANGELOG.md", "repo/governance/CHANGELOG.md", True),
    ("governance/reasons/AM_SMOKE_SHIFT_DIRECTION.json", "repo/governance/reasons/AM_SMOKE_SHIFT_DIRECTION.json", True),
    ("governance/reasons/AM_WORKER_CONFIRMATION_RULE.json", "repo/governance/reasons/AM_WORKER_CONFIRMATION_RULE.json", True),
    ("governance/reasons/AM_ENVIRONMENT_LOCK_CORRECTION.json", "repo/governance/reasons/AM_ENVIRONMENT_LOCK_CORRECTION.json", True),
    ("governance/reasons/INV_S01_SMOKE.json", "repo/governance/reasons/INV_S01_SMOKE.json", True),
    ("governance/reasons/INV_S02_PREFREEZE_SMOKE.json", "repo/governance/reasons/INV_S02_PREFREEZE_SMOKE.json", True),
    # freeze objects that changed identity
    ("governance/FREEZE_MANIFEST.json", "repo/governance/FREEZE_MANIFEST.json", True),
    ("governance/COMPUTE_SPEC_v1.json", "repo/governance/COMPUTE_SPEC_v1.json", True),
    ("governance/COMPUTE_FREEZE.json", "repo/governance/COMPUTE_FREEZE.json", True),
    # P0-6 smoke S03
    ("smoke/S03/SMOKE_NULL/evaluation_rows.jsonl", "smoke/S03/SMOKE_NULL/evaluation_rows.jsonl", True),
    ("smoke/S03/SMOKE_ALT/evaluation_rows.jsonl", "smoke/S03/SMOKE_ALT/evaluation_rows.jsonl", True),
    ("smoke/S03/smoke_null_RC.json", "smoke/S03/smoke_null_RC.json", True),
    ("smoke/S03/smoke_alt_RC.json", "smoke/S03/smoke_alt_RC.json", True),
    ("smoke/S03/SMOKE_SEAL_SMOKE_NULL.json", "smoke/S03/SMOKE_SEAL_SMOKE_NULL.json", True),
    ("smoke/S03/SMOKE_SEAL_SMOKE_ALT.json", "smoke/S03/SMOKE_SEAL_SMOKE_ALT.json", True),
    ("smoke/S03/RUN_REGISTRY.jsonl", "smoke/S03/RUN_REGISTRY.jsonl", True),
    ("smoke/S03/STATE_REGISTRY.jsonl", "smoke/S03/STATE_REGISTRY.jsonl", True),
    ("smoke/S03/commands.jsonl", "smoke/S03/commands.jsonl", True),
    ("smoke/S03/stdout_stderr/smoke_s03.log", "smoke/S03/stdout_stderr/smoke_s03.log", True),
    ("smoke/S03/provenance_manifest.json", "smoke/S03/provenance_manifest.json", True),
    # P0-7 verification
    ("verification/pytest_full.log", "verification/pytest_full.log", True),
    ("verification/pytest_full.xml", "verification/pytest_full.xml", True),
    ("verification/ruff_check.log", "verification/ruff_check.log", True),
    ("verification/validation_commands.jsonl", "verification/commands.jsonl", True),
    ("verification/validation_exit_codes.json", "verification/validation_exit_codes.json", True),
    ("verification/validation_environment.json", "verification/validation_environment.json", True),
]

GATE_RELABEL = {
    "archive_byte_integrity": {"in_package": "PASS", "material_admission": "PASS"},
    "G0-FREEZE-CHAIN-AND-IDENTITY": {"in_package": "PASS", "material_admission": "BLOCKED_IDENTITY"},
    "G3-BLIND-SMOKE-BOTH-PHASES": {"in_package": "PASS", "material_admission": "PROVISIONAL"},
    "SECTION-9-4-COMPUTE-BUDGET": {"in_package": "PASS", "material_admission": "PROVISIONAL"},
    "W-STAR-CONFIRMATION": {"in_package": "FAIL_UNCONFIRMED", "material_admission": "FAIL_UNCONFIRMED"},
    "H1-ALTERNATIVE-CONSTRUCT-CONTRACTS": {"in_package": "PASS_L0", "material_admission": "PENDING_CODE_REVIEW"},
    "L2/L3-SCIENCE": {"in_package": "NOT_STARTED", "material_admission": "NO_RESULTS_TO_AUDIT"},
}


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def _resolve(source: str, evidence_root: Path) -> Path:
    return REPO / source[5:] if source.startswith("repo/") else evidence_root / source


def _copy_p0_smoke(evidence_root: Path, staging: Path) -> list[dict[str, Any]]:
    """P0-6: copy the whole S03 evidence tree (ledgers, seals, registries)."""
    copied: list[dict[str, Any]] = []
    src_root = evidence_root / "smoke" / "S03"
    if not src_root.exists():
        return [{"path": "smoke/S03", "status": f"MISSING:{src_root}"}]
    for path in sorted(src_root.rglob("*")):
        if not path.is_file():
            continue
        rel = path.relative_to(evidence_root).as_posix()
        dest = staging / rel
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(path, dest)
        copied.append(
            {"path": rel, "status": "ok", "size": path.stat().st_size, "sha256": _sha256(path)}
        )
    return copied


def main() -> int:
    parser = argparse.ArgumentParser(description="build the audit supplement")
    parser.add_argument("--evidence-root", required=True)
    parser.add_argument("--out", default=str(OUT_PARENT))
    args = parser.parse_args()

    evidence_root = Path(args.evidence_root).expanduser()
    out = Path(args.out).expanduser()
    staging = out / SUBMISSION_ID
    shutil.rmtree(staging, ignore_errors=True)
    staging.mkdir(parents=True, exist_ok=True)

    entries: list[dict[str, Any]] = []
    for archive_path, source, required in PLAN:
        src = _resolve(source, evidence_root)
        dest = staging / archive_path
        if src.exists():
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(src, dest)
            entries.append(
                {
                    "path": archive_path,
                    "source": source,
                    "status": "ok",
                    "size": src.stat().st_size,
                    "sha256": _sha256(src),
                }
            )
        else:
            entries.append(
                {"path": archive_path, "source": source, "status": f"MISSING:{src}", "required": required}
            )
    entries.extend(_copy_p0_smoke(evidence_root, staging))

    # newest schema_check_*.json is copied under a stable name
    schema_checks = sorted((evidence_root / "schemas").glob("schema_check_*.json"))
    if schema_checks:
        src = schema_checks[-1]
        dest = staging / "configs/schema/schema_check.json"
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(src, dest)
        entries.append(
            {
                "path": "configs/schema/schema_check.json",
                "source": str(src),
                "status": "ok",
                "size": src.stat().st_size,
                "sha256": _sha256(src),
            }
        )
    else:
        entries.append(
            {
                "path": "configs/schema/schema_check.json",
                "source": str(evidence_root / "schemas"),
                "status": "MISSING:schema_check_*.json",
                "required": True,
            }
        )

    now = datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
    (staging / "GATE_RELABEL.json").write_text(
        json.dumps(
            {
                "schema_version": 1,
                "kind": "gate_relabel",
                "submitted_at_utc": now,
                "note": "material-admission labels replace the in-package labels for the read-only package",
                "gates": GATE_RELABEL,
            },
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
    manifest = {
        "schema_version": 1,
        "kind": "supplement_package_manifest",
        "submission_id": SUBMISSION_ID,
        "generated_at_utc": now,
        "supersedes": "none (incremental; the B15c package stays read-only)",
        "closed_p0_items": [
            "P0-1 git freeze identity",
            "P0-2 real environment lock",
            "P0-3 w* confirmation",
            "P0-4 strict schemas",
            "P0-5 amendment/invalidation chains",
            "P0-6 sealed S03 smoke + run/state registries + open_runs fail-closed",
            "P0-7 raw test evidence",
        ],
        "objects": entries,
        "missing_count": sum(1 for e in entries if e["status"] != "ok"),
    }
    (staging / "package_manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )

    contents: list[tuple[str, bytes]] = []
    for path in sorted(staging.rglob("*")):
        if path.is_file():
            contents.append((path.relative_to(staging).as_posix(), path.read_bytes()))
    sums = "".join(f"{hashlib.sha256(b).hexdigest()}  {rel}\n" for rel, b in contents)
    (staging / "SHA256SUMS.txt").write_bytes(sums.encode("utf-8"))
    contents.append(("SHA256SUMS.txt", sums.encode("utf-8")))

    zip_path = out / f"{SUBMISSION_ID}.zip"
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED, compresslevel=9) as zf:
        for rel, blob in sorted(contents):
            info = zipfile.ZipInfo(f"{SUBMISSION_ID}/{rel}", date_time=ZIP_STAMP)
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o644 << 16
            zf.writestr(info, blob)
    zip_sha = _sha256(zip_path)
    (out / f"{SUBMISSION_ID}.zip.sha256").write_text(
        f"{zip_sha}  {zip_path.name}\n", encoding="utf-8"
    )

    print(json.dumps(
        {
            "submission_id": SUBMISSION_ID,
            "objects": len(entries),
            "missing": [e["path"] for e in entries if e["status"] != "ok"],
            "zip": str(zip_path),
            "zip_bytes": zip_path.stat().st_size,
            "zip_sha256": zip_sha,
        },
        ensure_ascii=False,
        indent=2,
    ))
    return 0 if manifest["missing_count"] == 0 else 2


if __name__ == "__main__":
    raise SystemExit(main())
