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
from collections import Counter
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "src"))

from owtda_cal.attack_harness import check_package
from owtda_cal.evidence_audit import check_fixture_payload, safe_file, sha
from owtda_cal.formal_admission import check_g4_h0_certificate
from owtda_cal.manifests import _manifest_hash, bound_manifest_hash


def _read(path: Path) -> dict:
    if not path.is_file():
        return {}
    try:
        obj = json.loads(path.read_text(encoding="utf-8"))
        return obj if isinstance(obj, dict) else {}
    except (ValueError, OSError):
        return {}


def _contract(name: str, status: str, codes: list[str], evidence: dict) -> dict:
    return {"contract": name, "status": status, "codes": codes, "evidence": evidence}


def check_c1(manifests_dir: Path, plan: dict) -> dict:
    bundle = _read(manifests_dir / "MANIFEST_BUNDLE.json")
    codes: list[str] = []
    missing = False
    manifest_hashes = {}
    for name in ("SCIENTIFIC_MANIFEST", "EXECUTION_MANIFEST", "VALIDATION_MANIFEST"):
        obj = _read(manifests_dir / (name + ".json"))
        if not obj:
            codes.append(f"{name}_MISSING_OR_INVALID")
            missing = True
            continue
        field = "test_files" if name == "VALIDATION_MANIFEST" else "files"
        content = obj.get(field)
        if not isinstance(content, dict) or not content:
            codes.append(f"{name}_EMPTY_FILE_MANIFEST")
            content = {}
        if obj.get("kind") != name:
            codes.append(f"{name}_KIND_MISMATCH")
        if name == "SCIENTIFIC_MANIFEST":
            digest = _manifest_hash(name, content, obj.get("config_files", {}))
        else:
            digest = bound_manifest_hash(obj)
            if obj.get("schema_version") != 2:
                codes.append(f"{name}_INCOMPLETE_METADATA_BINDING")
        if obj.get("manifest_hash") != digest:
            codes.append(f"{name}_HASH_MISMATCH")
        manifest_hashes[name] = obj.get("manifest_hash")
        for rel, expected in {**content, **obj.get("config_files", {})}.items():
            try:
                if sha(safe_file(REPO, rel)) != expected:
                    codes.append(f"{name}_SOURCE_CHANGED:{rel}")
            except (ValueError, OSError):
                codes.append(f"{name}_FILE_UNAVAILABLE:{rel}")
        if name == "EXECUTION_MANIFEST" and (
            not obj.get("command") or not obj.get("interpreter") or not obj.get("entries")
        ):
            codes.append("EXECUTION_DETAILS_MISSING")
        if name == "VALIDATION_MANIFEST":
            junit = obj.get("junit") or {}
            if type(obj.get("exit_code")) is not int or obj["exit_code"] != 0:
                codes.append("VALIDATION_EXIT_NOT_SUCCESS")
            if not obj.get("collected_nodeids") or not junit.get("identities") or junit.get("issues"):
                codes.append("VALIDATION_EVIDENCE_NOT_COMPLETE")
    binding = bundle.get("plan_binding") or {}
    if not binding or not plan:
        codes.append("PLAN_NOT_BOUND")
    else:
        if binding.get("formal_scale") is not True or plan.get("formal_scale") is not True:
            codes.append("PLAN_NOT_FORMAL_SCALE")
        if binding.get("totals") != plan.get("totals") or not plan.get("totals"):
            codes.append("PLAN_TOTALS_MISMATCH")
        expected = {k: v.get("index_hashes", {}).get("evaluation") for k, v in plan.get("phases", {}).items()}
        if not expected or binding.get("evaluation_index_hashes") != expected:
            codes.append("PLAN_INDEX_BINDING_MISMATCH")
    if len(manifest_hashes) == 3:
        digest = _manifest_hash("MANIFEST_BUNDLE", *(manifest_hashes[n] for n in
            ("SCIENTIFIC_MANIFEST", "EXECUTION_MANIFEST", "VALIDATION_MANIFEST")), binding)
        if bundle.get("bundle_hash") != digest:
            codes.append("BUNDLE_HASH_MISMATCH")
        if bundle.get("manifest_hashes") != manifest_hashes:
            codes.append("BUNDLE_MANIFEST_REFS_MISMATCH")
    return _contract("C1_identity_binding", "INCOMPLETE" if missing else "FAIL" if codes else "PASS", codes,
                     {"bundle_hash": bundle.get("bundle_hash"), "manifest_hashes": manifest_hashes})


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
    codes = []
    results = summary.get("results") or []
    wanted = {f"F{i}" for i in range(1, 11)}
    ids = [r.get("fault") for r in results if isinstance(r, dict)]
    if len(ids) != 10 or set(ids) != wanted:
        codes.append("FAULT_RESULT_SET_INCOMPLETE")
    for fault in sorted(wanted):
        directory = faults_dir / fault
        for name in ("command.txt", "exit_code.txt", "timeline.json", "state_before.json", "state_after.json"):
            if not (directory / name).is_file():
                codes.append(f"FAULT_RAW_MISSING:{fault}/{name}")
        exit_path = directory / "exit_code.txt"
        if exit_path.is_file() and exit_path.read_text().strip() != "0":
            codes.append(f"FAULT_BENCH_EXIT_FAILED:{fault}")
    for result in results:
        if result.get("ok") is not True:
            codes.append(f"FAULT_POINT_FAILED:{result.get('fault')}")
    if not str(summary.get("platform", "")).lower().startswith(("win", "windows")):
        codes.append("TARGET_WINDOWS_EVIDENCE_NOT_PROVIDED")
    if summary.get("checks") != 10 or summary.get("failed") != []:
        codes.append("FAULT_SUMMARY_MISMATCH")
    status = "PASS" if not codes else "INCOMPLETE" if any("MISSING" in c or "INCOMPLETE" in c or "NOT_PROVIDED" in c for c in codes) else "FAIL"
    return _contract("C3_fault_recovery", status, codes, {"checks": len(ids), "platform": summary.get("platform")})


def check_c4(lifecycle_dir: Path) -> dict:
    actual = check_fixture_payload(lifecycle_dir)
    # Payload consistency is independently useful; it does not prove reuse of a
    # formal scientific adapter. That adapter is absent in this revision.
    codes = list(actual["codes"])
    codes.append("PRODUCTION_SCIENTIFIC_ADAPTER_NOT_IMPLEMENTED")
    return _contract("C4_real_lifecycle", "INCOMPLETE" if actual["status"] == "PASS" else actual["status"],
                     codes, {"actual_payload_verification": actual})


def check_c5(sequence_dir: Path, plan: dict, budget_dir: Path | None = None) -> dict:
    from owtda_cal.resource_policy import (
        evaluate_capacity,
        load_policy,
        policy_sha256,
        preflight_capacity,
    )
    preflight = _read(sequence_dir / "preflight" / "preflight.json")
    budget = _read((budget_dir or (sequence_dir / "budget")) / "budget.json")
    inputs = _read(sequence_dir / "preflight" / "preflight_inputs.json")
    codes = []
    if not inputs:
        codes.append("PREFLIGHT_INPUTS_MISSING")
    else:
        try:
            replay = preflight_capacity(**inputs, policy=load_policy())
            if replay.get("passed") is not True or preflight.get("passed") != replay.get("passed"):
                codes.append("PREFLIGHT_REFUSED_OR_MISMATCH")
        except (TypeError, ValueError, KeyError) as exc:
            codes.append("PREFLIGHT_INPUT_INVALID:" + type(exc).__name__)
    if not preflight:
        codes.append("PREFLIGHT_MISSING")
    if not budget:
        codes.append("BUDGET_MISSING")
    elif budget.get("status") != "APPROVED_ESTIMATE" or not budget.get("volumes"):
        codes.append("BUDGET_NOT_APPROVED_OR_VOLUME_MISSING")
    elif not budget.get("bound_plan") or budget["bound_plan"].get("formal_scale") is not True:
        codes.append("BUDGET_NOT_BOUND_TO_FORMAL_PLAN")
    if not plan or plan.get("formal_scale") is not True:
        codes.append("PLAN_NOT_FORMAL_SCALE")
    inventory = _read(sequence_dir / "RESOURCE_RUNS.json")
    entries = inventory.get("runs") or []
    if {r.get("phase") for r in entries} != {"SMOKE_NULL", "SMOKE_ALT"} or len(entries) != 2:
        codes.append("RESOURCE_RUN_INVENTORY_MISSING_OR_INCOMPLETE")
    for item in entries:
        try:
            path = safe_file(sequence_dir, item["raw_file"])
            if sha(path) != item["raw_sha256"]:
                codes.append("RAW_RESOURCE_HASH_MISMATCH")
            rows = [json.loads(line) for line in path.read_bytes().splitlines() if line.strip()]
            decision = evaluate_capacity(rows, policy=load_policy(), expected_run_id=item["run_id"],
                expected_policy_sha256=policy_sha256(), require_boundaries=True,
                expected_start_ns=item["protected_start_ns"], expected_end_ns=item["protected_end_ns"])
            if decision["verdict"] != "PASS":
                codes.append("RAW_RESOURCE_NOT_PASS:" + item["phase"])
        except (KeyError, TypeError, ValueError, OSError) as exc:
            codes.append("RAW_RESOURCE_INVALID:" + str(exc))
    return _contract("C5_capacity_and_budget", "PASS" if not codes else "INCOMPLETE" if any("MISSING" in c for c in codes) else "FAIL", codes,
                     {"resource_runs": len(entries), "preflight_status": preflight.get("status"), "budget_status": budget.get("status")})


def _test_evidence(tests_dir: Path) -> tuple[int | None, list[str]]:
    """Read the test evidence the frozen-env collector actually writes.

    Re-audit 2026-09-15: this used to read ``<tests_dir>/verification.json``, which
    **no tool produces** -- the collected evidence lives in ``verification/`` as
    ``collection_manifest.json``, ``pytest_full.xml`` and
    ``validation_exit_codes.json``.  A contract that can only report
    TEST_EVIDENCE_MISSING verifies nothing, so the real artifacts are read and the
    JUnit identity set is checked here rather than trusted.
    """
    import xml.etree.ElementTree as ET

    ver = tests_dir / "verification" if (tests_dir / "verification").is_dir() else tests_dir
    codes: list[str] = []
    exits = _read(ver / "validation_exit_codes.json")
    if not exits:
        codes.append("TEST_EXIT_CODES_MISSING")
    elif any(int(v) != 0 for v in exits.values()):
        bad = ",".join(sorted(k for k, v in exits.items() if int(v) != 0))
        codes.append("TEST_EXIT_CODES_FAILED:" + bad)
    xml_path = ver / "pytest_full.xml"
    collected = _read(ver / "collection_manifest.json")
    if not xml_path.is_file() or not collected:
        codes.append("TEST_EVIDENCE_MISSING")
        return None, codes
    try:
        root = ET.fromstring(xml_path.read_text(encoding="utf-8"))
    except (ET.ParseError, UnicodeError, OSError):
        return None, codes + ["JUNIT_UNPARSEABLE"]
    identities: list[str] = []
    failures = 0
    for case in root.iter("testcase"):
        identities.append(f"{case.get('classname')}::{case.get('name')}")
        # A <skipped/> child is not a failure: this suite's single skip is the
        # disclosed "S03 evidence root not available on this machine" case, which is
        # approved in the validation manifest.  Only failure/error children count.
        if case.find("failure") is not None or case.find("error") is not None:
            failures += 1
    if failures:
        codes.append(f"TEST_FAILURES:{failures}")
    if len(set(identities)) != len(identities):
        codes.append("TEST_IDENTITY_DUPLICATED")
    expected_nodes = collected.get("node_ids")
    expected_ids = []
    if isinstance(expected_nodes, list):
        for node in expected_nodes:
            if not isinstance(node, str) or "::" not in node:
                codes.append("TEST_COLLECTION_ID_INVALID")
                continue
            pieces = node.split("::")
            module = pieces[0].replace("\\", "/").removesuffix(".py").replace("/", ".")
            expected_ids.append(".".join([module] + pieces[1:-1]) + "::" + pieces[-1])
    if not expected_ids or Counter(expected_ids) != Counter(identities):
        codes.append("TEST_IDENTITY_SET_MISMATCH")
    approved = set(collected.get("approved_skips", []))
    for case in root.iter("testcase"):
        ident = f"{case.get('classname')}::{case.get('name')}"
        if case.find("skipped") is not None and ident not in approved:
            codes.append("UNAPPROVED_SKIP:" + ident)
    expected = collected.get("collected_count")
    if isinstance(expected, int) and expected != len(identities):
        codes.append(f"TEST_IDENTITY_COUNT_MISMATCH:{expected}!={len(identities)}")
    return len(identities), codes


def check_c6(attacks_dir: Path, tests_dir: Path | None) -> dict:
    from owtda_cal.attack_harness import summarise_attacks
    summary = _read(attacks_dir / "SUMMARY.json")
    codes: list[str] = []
    records = [_read(p) for p in sorted((attacks_dir / "attacks").glob("*.json"))]
    if not summary or not records or any(not r for r in records):
        codes.append("ATTACK_RAW_EVIDENCE_MISSING")
    else:
        identities = [r.get("attack_id") for r in records]
        if any(not isinstance(i, str) or not i for i in identities) or len(identities) != len(set(identities)):
            codes.append("ATTACK_IDENTITIES_INVALID")
        actual = summarise_attacks(records)
        for key in ("attacks", "detected", "eligible_baselines", "undetected", "detection_rate"):
            if actual.get(key) != summary.get(key):
                codes.append("ATTACK_SUMMARY_MISMATCH:" + key)
        for record in records:
            if record.get("detected") is True and (record.get("baseline_target_status") != "PASS" or
                    record.get("mutant_target_status") not in ("FAIL", "INCOMPLETE") or
                    not record.get("attributable_error_code")):
                codes.append("ATTACK_ATTRIBUTION_INVALID:" + str(record.get("attack_id")))
        if actual.get("undetected") or not actual.get("eligible_baselines"):
            codes.append("ATTACKS_NOT_CLOSED")
    count = None
    if tests_dir is None:
        codes.append("TEST_EVIDENCE_MISSING")
    else:
        try:
            count, test_codes = _test_evidence(tests_dir)
            codes.extend(test_codes)
        except Exception as exc:  # noqa: BLE001 - 报告畸形不得中断准入判定：记录 TEST_EVIDENCE_INVALID:<类型> 后继续
            # Malformed reports must yield a result; they must not crash admission.
            codes.append("TEST_EVIDENCE_INVALID:" + type(exc).__name__)
    return _contract("C6_final_evidence", "PASS" if not codes else "INCOMPLETE" if any("MISSING" in c for c in codes) else "FAIL", codes,
                     {"attack_records": len(records), "junit_testcases": count})


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
    engineering_ready = all(s == "PASS" for s in statuses.values())
    verdict = {
        "schema_version": 1,
        "kind": "release_contracts",
        "contracts": contracts,
        "statuses": statuses,
        "engineering_evidence_ready": engineering_ready,
        "admissible": engineering_ready and admission is not None and admission.get("admitted") is True,
        "formal_dispatch_supported": False,
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
