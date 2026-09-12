"""Attack regression harness with differential attribution (task pack §6).

Two facts drove this module.

First, "the package fails" was being used as if it proved detection.  When the
baseline already has failing contracts, ``all_pass=false`` after a mutation says
nothing: the same contracts may fail for the original reason.  So every attack
records ``baseline_target_status`` and ``mutant_target_status`` for the contract
*it targets*, and a detection rate is only computed over attacks whose baseline
was PASS.

Second, an honest failure was being scored as a disclosure failure.  The three
verdict layers are therefore reported separately:

``package_integrity``
    the bytes are self-consistent (checksums, referenced files, hashes).
``experiment_evidence_consistency``
    the science record is internally consistent (p arithmetic, unique ids, set
    equality, analysis reading the real ledger).
``formal_admission``
    every precondition for calling the run admission-grade is satisfied.

A failed run can pass the first two and fail the third -- that is a *disclosed*
failure, not a hidden one.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Callable, Sequence
from pathlib import Path
from typing import Any

from .oracles import (
    check_junit,
    check_p_arithmetic,
    compare_identity_sets,
    disclosure_consistency,
    verify_file_ref,
)

LAYERS = ("package_integrity", "experiment_evidence_consistency", "formal_admission")


def _layer(name: str, issues: Sequence[dict]) -> dict[str, Any]:
    return {
        "layer": name,
        "issues": list(issues),
        "status": "FAIL" if issues else "PASS",
    }


def check_package(package_dir: str | Path) -> dict[str, Any]:
    """Evaluate the three layers over a package directory.

    The checker is deliberately minimal and pure: it reads what a package must
    contain, applies the oracles, and never trusts a summary field when the raw
    rows are available.
    """
    root = Path(package_dir)
    integrity_issues: list[dict] = []
    consistency_issues: list[dict] = []
    admission_issues: list[dict] = []

    manifest_path = root / "package_manifest.json"
    manifest: dict[str, Any] = {}
    if not manifest_path.is_file():
        integrity_issues.append({"code": "PACKAGE_MANIFEST_MISSING",
                                 "where": "package_manifest.json", "detail": "absent"})
    else:
        try:
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        except Exception as exc:  # noqa: BLE001 - a broken manifest is a finding
            integrity_issues.append({"code": "PACKAGE_MANIFEST_UNPARSEABLE",
                                     "where": "package_manifest.json",
                                     "detail": str(exc)})
    for ref in manifest.get("objects", []):
        path = ref.get("path")
        integrity_issues.extend(
            verify_file_ref({"path": str(root / path) if path else None,
                             "sha256": ref.get("sha256")},
                            evidence_root=str(root), where=str(path))
        )

    # --- layer 2: the science record ------------------------------------------ #
    ledger = root / "evaluation_ledger.jsonl"
    rows: list[dict] = []
    if not ledger.is_file():
        consistency_issues.append({"code": "LEDGER_MISSING", "where": str(ledger.name),
                                   "detail": "the package has no ledger"})
    else:
        for number, line in enumerate(
                ledger.read_text(encoding="utf-8").splitlines(), start=1):
            if not line.strip():
                continue
            row = json.loads(line)
            rows.append(row)
            consistency_issues.extend(
                check_p_arithmetic(row, where=f"ledger:{number}")
            )
    if rows:
        consistency_issues.extend(
            compare_identity_sets(rows, rows, key_field="evaluation_id",
                                  where="ledger")["issues"]
        )

    scope_rows: list[dict] = []
    scope_path = root / "scope_rows.jsonl"
    if scope_path.is_file():
        scope_rows = [json.loads(line) for line in
                      scope_path.read_text(encoding="utf-8").splitlines() if line.strip()]
        if scope_rows:
            key = next((name for name in ("logical_cell_id", "logical_evaluation_key",
                                          "evaluation_id")
                        if name in scope_rows[0]), None)
            if key is None:
                consistency_issues.append({
                    "code": "SCOPE_ROW_WITHOUT_IDENTITY", "where": "scope_rows.jsonl",
                    "detail": "a scope row carries no registered identity field"})
            else:
                consistency_issues.extend(
                    compare_identity_sets(scope_rows, scope_rows, key_field=key,
                                          where="scope")["issues"]
                )

    analysis_output = root / "analysis_output.json"
    if analysis_output.is_file() and rows:
        output = json.loads(analysis_output.read_text(encoding="utf-8"))
        if output.get("rows") != len(rows):
            consistency_issues.append({
                "code": "ANALYSIS_ROW_COUNT_MISMATCH", "where": "analysis_output.json",
                "detail": f"analysis declares {output.get('rows')!r} rows, the ledger "
                          f"holds {len(rows)}",
            })
        declared = output.get("ledger_sha256")
        actual = hashlib.sha256(ledger.read_bytes()).hexdigest()
        if declared and declared != actual:
            consistency_issues.append({
                "code": "ANALYSIS_LEDGER_HASH_MISMATCH", "where": "analysis_output.json",
                "detail": f"{str(declared)[:16]}... != {actual[:16]}...",
            })

    junit = root / "junit.xml"
    if junit.is_file():
        expected_path = root / "collected_nodeids.json"
        expected = None
        if expected_path.is_file():
            collected = json.loads(expected_path.read_text(encoding="utf-8"))
            expected = [
                f"{item['classname']}::{item['name']}" if isinstance(item, dict) else item
                for item in collected
            ]
        consistency_issues.extend(
            check_junit(junit.read_text(encoding="utf-8", errors="replace"),
                        expected_identities=expected, where="junit")["issues"]
        )

    # --- layer 3: admission ---------------------------------------------------- #
    recomputed = {
        "package_integrity": "PASS" if not integrity_issues else "FAIL",
        "experiment_evidence_consistency": (
            "PASS" if not consistency_issues else "FAIL"),
    }
    certificate = root / "G4_H0_CERTIFICATE.json"
    if not certificate.is_file():
        admission_issues.append({"code": "G4_H0_CERTIFICATE_MISSING",
                                 "where": "G4_H0_CERTIFICATE.json", "detail": "absent"})
    if recomputed["package_integrity"] != "PASS":
        admission_issues.append({"code": "INTEGRITY_NOT_ESTABLISHED",
                                 "where": "package", "detail": "layer 1 failed"})
    if recomputed["experiment_evidence_consistency"] != "PASS":
        admission_issues.append({"code": "EVIDENCE_NOT_CONSISTENT",
                                 "where": "package", "detail": "layer 2 failed"})

    # Disclosure is compared against the *admission* finding, not against an
    # earlier layer: a package may disclose FAIL and be right about it.
    inline = root / "inline_verdict.json"
    recomputed_admission = "PASS" if not admission_issues else "FAIL"
    disclosure = None
    if inline.is_file():
        declared = json.loads(inline.read_text(encoding="utf-8"))
        disclosure = disclosure_consistency(
            declared.get("verdict", "UNKNOWN"), recomputed_admission)
        if not disclosure["disclosed_consistently"]:
            admission_issues.append({
                "code": "DISCLOSURE_INCONSISTENT", "where": "inline_verdict.json",
                "detail": f"inline {disclosure['inline']} != recomputed "
                          f"{disclosure['recomputed']}",
            })
    else:
        disclosure = {"inline": "ABSENT", "recomputed": recomputed_admission,
                      "disclosed_consistently": False,
                      "admissible": False, "note": "no inline verdict was submitted"}

    layers = {
        "package_integrity": _layer("package_integrity", integrity_issues),
        "experiment_evidence_consistency": _layer(
            "experiment_evidence_consistency", consistency_issues),
        "formal_admission": _layer("formal_admission", admission_issues),
    }
    return {
        "layers": layers,
        "disclosure": disclosure,
        "rows": len(rows),
        "scope_rows": len(scope_rows),
        "admissible": layers["formal_admission"]["status"] == "PASS",
        "all_pass": all(layers[name]["status"] == "PASS" for name in LAYERS),
    }


def run_attack(
    attack: dict[str, Any],
    package_dir: str | Path,
    *,
    checker: Callable[[str | Path], dict[str, Any]] = check_package,
) -> dict[str, Any]:
    """Run one mutation and return its full differential record.

    The record carries the six fields the task pack requires:
    ``target_contract, target_file, mutation, baseline_target_status,
    mutant_target_status, attributable_error_code``.
    """
    baseline = checker(package_dir)
    attack["apply"](package_dir)
    mutant = checker(package_dir)
    target = attack["target_contract"]
    baseline_status = baseline["layers"][target]["status"]
    mutant_status = mutant["layers"][target]["status"]
    codes = sorted({issue["code"] for issue in mutant["layers"][target]["issues"]})
    new_codes = sorted(
        set(codes) - {issue["code"] for issue in baseline["layers"][target]["issues"]}
    )
    detected = baseline_status == "PASS" and mutant_status in ("FAIL", "INCOMPLETE")
    return {
        "attack_id": attack["id"],
        "target_contract": target,
        "target_file": attack.get("target_file"),
        "mutation": attack.get("mutation", attack["id"]),
        "baseline_target_status": baseline_status,
        "mutant_target_status": mutant_status,
        "attributable_error_code": (new_codes or codes or [None])[0],
        "new_error_codes": new_codes,
        "detected": detected,
        "baseline_all_pass": baseline["all_pass"],
        "mutant_all_pass": mutant["all_pass"],
    }


def summarise_attacks(records: Sequence[dict[str, Any]]) -> dict[str, Any]:
    """Detection statistics that never count a pre-existing failure as a catch."""
    eligible = [r for r in records if r["baseline_target_status"] == "PASS"]
    detected = [r for r in eligible if r["detected"]]
    skipped = [r for r in records if r["baseline_target_status"] != "PASS"]
    return {
        "attacks": len(records),
        "eligible_baselines": len(eligible),
        "detected": len(detected),
        "undetected": [r["attack_id"] for r in eligible if not r["detected"]],
        "not_scored": [r["attack_id"] for r in skipped],
        "detection_rate": (len(detected) / len(eligible)) if eligible else None,
        "note": (
            "the rate is computed over attacks whose target contract passed on the "
            "baseline; a package that already failed the target cannot demonstrate "
            "detection for it"
        ),
        "records": list(records),
    }


__all__ = [
    "LAYERS",
    "check_package",
    "run_attack",
    "summarise_attacks",
]
