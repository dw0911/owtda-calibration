"""§9 step 9: verify C1-C6 from the evidence that exists, never from a label.

The audit's complaint about the old verifier was that ``all_pass`` was used as the
admission signal: a package that already failed four contracts could "detect" a
mutation simply by staying red.  So each contract below is decided from a named
artifact and reports a status of PASS / FAIL / INCOMPLETE with attributable codes;
``admissible`` requires PASS on every contract, and a contract that has no
evidence at all is INCOMPLETE -- never a silent pass.

Usage::

    python scripts/verify_release_contracts.py --out <EVIDENCE> \
        --plan <PLAN_DIR> --sequence <SEQUENCE_DIR> --faults <FAULTS_DIR> \
        --attacks <ATTACK_DIR> --lifecycle <TEST_DIR>
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "src"))

from owtda_cal.attack_harness import check_package
from owtda_cal.formal_admission import check_g4_h0_certificate


def _read(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8")) if path.is_file() else {}


def _contract(name: str, status: str, codes: list[str], evidence: dict) -> dict:
    return {"contract": name, "status": status, "codes": codes, "evidence": evidence}


def check_c1(manifests_dir: Path, plan: dict) -> dict:
    bundle = _read(manifests_dir / "MANIFEST_BUNDLE.json")
    codes = []
    for name in ("SCIENTIFIC_MANIFEST.json", "EXECUTION_MANIFEST.json",
                 "VALIDATION_MANIFEST.json"):
        if not (manifests_dir / name).is_file():
            codes.append(f"{name.removesuffix('.json')}_MISSING")
    binding = bundle.get("plan_binding") or {}
    if not binding:
        codes.append("PLAN_NOT_BOUND")
    elif binding.get("formal_scale") is not True:
        codes.append("PLAN_NOT_FORMAL_SCALE")
    if plan and binding.get("formal_scale") and not binding.get("totals"):
        codes.append("PLAN_TOTALS_NOT_BOUND")
    status = "PASS" if not codes else "FAIL" if bundle else "INCOMPLETE"
    return _contract("C1_identity_binding", status, codes,
                     {"bundle_hash": bundle.get("bundle_hash"),
                      "plan_bound": bool(binding)})


def check_c2(package: Path) -> dict:
    if not package.is_dir():
        return _contract("C2_computation_and_sets", "INCOMPLETE",
                         ["PACKAGE_NOT_PROVIDED"], {})
    result = check_package(package)
    layer = result["layers"]["experiment_evidence_consistency"]
    codes = [issue["code"] for issue in layer["issues"]]
    return _contract("C2_computation_and_sets", layer["status"], codes,
                     {"rows": result["rows"], "scope_rows": result["scope_rows"]})


def check_c3(faults_dir: Path) -> dict:
    summary = _read(faults_dir / "SUMMARY.json")
    if not summary:
        return _contract("C3_fault_recovery", "INCOMPLETE", ["FAULT_EVIDENCE_MISSING"], {})
    failed = summary.get("failed") or []
    checks = summary.get("checks")
    codes = [f"FAULT_POINT_FAILED:{name}" for name in failed]
    status = "PASS" if checks and not failed else "FAIL"
    if checks != 10:
        codes.append("FAULT_POINTS_INCOMPLETE")
        status = "INCOMPLETE" if not failed else "FAIL"
    return _contract("C3_fault_recovery", status, codes,
                     {"checks": checks, "failed": failed,
                      "platform": summary.get("platform")})


def check_c4(lifecycle_dir: Path) -> dict:
    report = _read(lifecycle_dir / "LIFECYCLE_FIXTURE.json")
    if not report:
        return _contract("C4_real_lifecycle", "INCOMPLETE",
                         ["LIFECYCLE_FIXTURE_MISSING"], {})
    sets = report.get("set_equality") or {}
    verdict = report.get("verdict") or {}
    codes = []
    if not sets.get("identical"):
        codes.append("SETS_NOT_IDENTICAL")
    if len(sets.get("committed") or []) != 8:
        codes.append("COMMITTED_NOT_EIGHT")
    if not verdict.get("ledger_is_the_committed_payload"):
        codes.append("LEDGER_NOT_THE_COMMITTED_PAYLOAD")
    if not verdict.get("analysis_reads_the_actual_ledger"):
        codes.append("ANALYSIS_NOT_BOUND_TO_LEDGER")
    return _contract("C4_real_lifecycle", "FAIL" if codes else "PASS", codes,
                     {"committed": len(sets.get("committed") or []),
                      "counts": report.get("counts")})


def check_c5(sequence_dir: Path, plan: dict, budget_dir: Path | None = None) -> dict:
    preflight = _read(sequence_dir / "preflight" / "preflight.json")
    budget = _read((budget_dir or (sequence_dir / "budget")) / "budget.json")
    codes = []
    if not preflight:
        codes.append("PREFLIGHT_MISSING")
    elif not preflight.get("passed"):
        codes.append("PREFLIGHT_REFUSED")
    if not budget:
        codes.append("BUDGET_MISSING")
    else:
        if budget.get("status") != "APPROVED_ESTIMATE":
            codes.append("BUDGET_NOT_APPROVED")
        bound = budget.get("bound_plan") or {}
        if not bound.get("formal_scale"):
            codes.append("BUDGET_NOT_BOUND_TO_FORMAL_PLAN")
    if plan and not plan.get("formal_scale"):
        codes.append("PLAN_NOT_FORMAL_SCALE")
    status = "PASS" if not codes else ("INCOMPLETE" if not preflight or not budget
                                       else "FAIL")
    return _contract("C5_capacity_and_budget", status, codes,
                     {"preflight_status": preflight.get("status"),
                      "budget_status": budget.get("status")})


def check_c6(attacks_dir: Path, tests_dir: Path) -> dict:
    summary = _read(attacks_dir / "SUMMARY.json")
    verification = _read(tests_dir / "verification.json") if tests_dir else {}
    codes = []
    if not summary:
        codes.append("ATTACK_SUMMARY_MISSING")
    else:
        if summary.get("undetected"):
            codes.append("ATTACK_UNDETECTED:" + ",".join(summary["undetected"]))
        if not summary.get("eligible_baselines"):
            codes.append("NO_ELIGIBLE_BASELINES")
        if (summary.get("detection_rate") or 0) != 1.0:
            codes.append("DETECTION_RATE_NOT_ONE")
    junit = ((verification.get("junit") or {}).get("issues")) if verification else None
    if tests_dir and not verification:
        codes.append("TEST_EVIDENCE_MISSING")
    status = "PASS" if not codes else ("INCOMPLETE" if not summary else "FAIL")
    return _contract("C6_final_evidence", status, codes,
                     {"attacks": summary.get("attacks"),
                      "detected": summary.get("detected"),
                      "eligible": summary.get("eligible_baselines"),
                      "junit_issues": junit})


def main() -> int:
    parser = argparse.ArgumentParser(description="verify C1-C6")
    parser.add_argument("--out", required=True)
    parser.add_argument("--manifests", default=None, help="manifests dir (C1)")
    parser.add_argument("--budget", default=None, help="budget dir (C5)")
    parser.add_argument("--plan", default=None)
    parser.add_argument("--sequence", default=None)
    parser.add_argument("--package", default=None)
    parser.add_argument("--faults", default=None)
    parser.add_argument("--attacks", default=None)
    parser.add_argument("--lifecycle", default=None)
    parser.add_argument("--tests", default=None)
    parser.add_argument("--certificate", default=None)
    parser.add_argument("--seed-registry", default=None)
    args = parser.parse_args()

    out = Path(args.out).expanduser()
    out.mkdir(parents=True, exist_ok=True)
    plan = _read(Path(args.plan) / "PLAN_SUMMARY.json") if args.plan else {}
    sequence = Path(args.sequence).expanduser() if args.sequence else None

    contracts = [
        check_c1(Path(args.manifests).expanduser() if args.manifests
                 else Path(args.out).expanduser() / "manifests", plan),
        check_c2(Path(args.package).expanduser() if args.package else out / "package"),
        check_c3(Path(args.faults).expanduser()) if args.faults
        else _contract("C3_fault_recovery", "INCOMPLETE", ["FAULTS_DIR_NOT_GIVEN"], {}),
        check_c4(Path(args.lifecycle).expanduser()) if args.lifecycle
        else _contract("C4_real_lifecycle", "INCOMPLETE", ["LIFECYCLE_DIR_NOT_GIVEN"], {}),
        check_c5(sequence, plan, Path(args.budget).expanduser() if args.budget else None) if sequence
        else _contract("C5_capacity_and_budget", "INCOMPLETE", ["SEQUENCE_NOT_GIVEN"], {}),
        check_c6(Path(args.attacks).expanduser() if args.attacks else out / "attacks",
                 Path(args.tests).expanduser() if args.tests else None),
    ]
    admission = None
    if args.certificate and plan:
        admission = check_g4_h0_certificate(
            certificate_path=args.certificate, plan_summary=plan,
            seed_registry_path=args.seed_registry)
    statuses = {c["contract"]: c["status"] for c in contracts}
    verdict = {
        "schema_version": 1,
        "kind": "release_contracts",
        "contracts": contracts,
        "statuses": statuses,
        "admissible": all(s == "PASS" for s in statuses.values()),
        "formal_admission_gate": admission,
        "note": ("C1-C6 are decided from named artifacts; a contract without "
                 "evidence is INCOMPLETE, never a silent pass"),
    }
    (out / "RELEASE_CONTRACTS.json").write_text(
        json.dumps(verdict, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8")
    print(json.dumps({"statuses": statuses, "admissible": verdict["admissible"]},
                     ensure_ascii=False))
    return 0 if verdict["admissible"] else 1


if __name__ == "__main__":
    sys.exit(main())
