"""The attack regression of task pack §6, with per-attack attribution records.

Seven verifier counterexamples (file mutations on an independent copy) and six
shard counterexamples (execution-contract probes) are executed here.  Each one
writes ``<out>/attacks/<id>.json`` carrying the six required fields, and the
summary separates:

* attacks whose target contract **passed on the baseline** (only these can show
  detection);
* attacks skipped because the baseline already failed that contract;
* the three layer verdicts, kept apart so an honestly disclosed failure is not
  reported as a verifier miss.

Usage::

    python scripts/run_attack_regression.py <out-dir-outside-the-repo> [--keep-package]
"""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "src"))
sys.path.insert(0, str(REPO / "audit"))

from owtda_cal import chains, shardio
from owtda_cal.attack_harness import (
    check_package,
    run_attack,
    summarise_attacks,
)
from owtda_cal.canonical import canonical_json_bytes
from owtda_cal.identity import H

RECORDS: list[dict[str, Any]] = []


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _write(path: Path, obj: Any) -> None:
    path.write_text(json.dumps(obj, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
                    encoding="utf-8")


def build_package(package: Path) -> dict[str, Any]:
    """A real, clean package: the lifecycle fixture's chain plus a real JUnit run."""
    from run_lifecycle_fixture import run_fixture

    fixture_dir = package / "fixture"
    report = run_fixture(out_dir=fixture_dir)

    shutil.copyfile(fixture_dir / "evaluation_ledger.jsonl",
                    package / "evaluation_ledger.jsonl")
    shutil.copyfile(fixture_dir / "analysis_output.json", package / "analysis_output.json")
    scope_rows = json.loads(
        (fixture_dir / "expected_evaluation_index.json").read_text(encoding="utf-8"))
    with (package / "scope_rows.jsonl").open("w", encoding="utf-8") as fh:
        for row in scope_rows:
            fh.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")

    # a real RUN seal file, referenced by the manifest
    seal_source = sorted((fixture_dir / "run").glob("*SEAL*.json"))
    seal_path = package / "RUN_SEAL.json"
    if seal_source:
        shutil.copyfile(seal_source[0], seal_path)
    else:
        _write(seal_path, {"run_seal_hash": report["hashes"]["phase_state_tip"]})

    # a real (small) JUnit run whose identities are collected independently
    junit_path = package / "junit.xml"
    collected_path = package / "collected_nodeids.json"
    selected = "tests/test_oracles.py"
    subprocess.run(
        [sys.executable, "-m", "pytest", "-q", selected,
         f"--junitxml={junit_path}"],
        cwd=str(REPO), check=False, capture_output=True, text=True,
    )
    collected = subprocess.run(
        [sys.executable, "-m", "pytest", "--collect-only", "-q", selected],
        cwd=str(REPO), check=False, capture_output=True, text=True,
    ).stdout
    identities = []
    for line in collected.splitlines():
        line = line.strip()
        if "::" not in line or line.startswith("="):
            continue
        parts = line.split("::")
        # pytest's JUnit writer reports classname="module.Class", name="test";
        # collect-only reports "module.py::Class::test" -- normalise both sides
        module = parts[0].removesuffix(".py").replace("/", ".").replace("\\", ".")
        classname = ".".join([module, *parts[1:-1]])
        identities.append({"classname": classname, "name": parts[-1]})
    _write(collected_path, identities)

    _write(package / "inline_verdict.json", {"verdict": "PASS"})
    _write(package / "G4_H0_CERTIFICATE.json",
           {"kind": "g4_h0_certificate", "phase": "H0",
            "note": "fixture certificate: proves the layer wiring, not admission"})

    objects = [
        {"path": "RUN_SEAL.json", "sha256": _sha256(seal_path)},
    ]
    _write(package / "package_manifest.json", {"schema_version": 1, "objects": objects})
    return {"fixture_report": report, "scope_rows": len(scope_rows)}


# --------------------------------------------------------------------------- #
# the seven verifier counterexamples
# --------------------------------------------------------------------------- #
def _mutations(package: Path) -> list[dict[str, Any]]:
    def delete_ledger(pkg: Path) -> None:
        (pkg / "evaluation_ledger.jsonl").unlink()

    def delete_seal(pkg: Path) -> None:
        (pkg / "RUN_SEAL.json").unlink()

    def rewrite_analysis_rows(pkg: Path) -> None:
        path = pkg / "analysis_output.json"
        output = json.loads(path.read_text(encoding="utf-8"))
        output["rows"] = 999999
        _write(path, output)

    def duplicate_testcase(pkg: Path) -> None:
        path = pkg / "junit.xml"
        text = path.read_text(encoding="utf-8")
        start = text.index("<testcase")
        end = text.index(">", start) + 1
        if text[end - 2:end] != "/>":
            end = text.index("</testcase>", start) + len("</testcase>")
        first = text[start:end]
        path.write_text(text.replace("<testsuite", first + "<testsuite", 1),
                        encoding="utf-8")

    def nudge_p(pkg: Path) -> None:
        path = pkg / "evaluation_ledger.jsonl"
        rows = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()
                if line.strip()]
        rows[0]["p_value"] = rows[0]["p_value"] + 0.0001
        with path.open("w", encoding="utf-8") as fh:
            for row in rows:
                fh.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")

    def reject_as_integer(pkg: Path) -> None:
        path = pkg / "evaluation_ledger.jsonl"
        rows = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()
                if line.strip()]
        rows[0]["reject"] = 1 if rows[0]["reject"] else 0
        with path.open("w", encoding="utf-8") as fh:
            for row in rows:
                fh.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")

    def duplicate_scope_row(pkg: Path) -> None:
        path = pkg / "scope_rows.jsonl"
        lines = [x for x in path.read_text(encoding="utf-8").splitlines() if x.strip()]
        with path.open("w", encoding="utf-8") as fh:
            fh.write("\n".join([*lines, lines[0]]) + "\n")

    return [
        {"id": "V1_delete_ledger", "target_contract": "experiment_evidence_consistency",
         "target_file": "evaluation_ledger.jsonl", "apply": delete_ledger,
         "mutation": "delete the real ledger"},
        {"id": "V2_delete_run_seal", "target_contract": "package_integrity",
         "target_file": "RUN_SEAL.json", "apply": delete_seal,
         "mutation": "delete the referenced RUN seal"},
        {"id": "V3_analysis_row_count", "target_contract": "experiment_evidence_consistency",
         "target_file": "analysis_output.json", "apply": rewrite_analysis_rows,
         "mutation": "rewrite the analysis row count to 999999"},
        {"id": "V4_junit_duplicate_identity",
         "target_contract": "experiment_evidence_consistency",
         "target_file": "junit.xml", "apply": duplicate_testcase,
         "mutation": "duplicate one testcase identity, total unchanged"},
        {"id": "V5_p_off_grid", "target_contract": "experiment_evidence_consistency",
         "target_file": "evaluation_ledger.jsonl", "apply": nudge_p,
         "mutation": "p + 0.0001 (off the legal grid)"},
        {"id": "V6_reject_not_bool", "target_contract": "experiment_evidence_consistency",
         "target_file": "evaluation_ledger.jsonl", "apply": reject_as_integer,
         "mutation": "reject stored as an integer"},
        {"id": "V7_duplicate_scope_row", "target_contract": "experiment_evidence_consistency",
         "target_file": "scope_rows.jsonl", "apply": duplicate_scope_row,
         "mutation": "duplicate one scope row"},
    ]


# --------------------------------------------------------------------------- #
# the six shard counterexamples (execution-contract probes)
# --------------------------------------------------------------------------- #
def _probe_records(work: Path) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    run_id = H("attack_run")
    plan = H("attack_plan")

    def _new_dir(tag: str) -> Path:
        directory = work / f"S_{tag}"
        if directory.exists():
            shutil.rmtree(directory)
        directory.mkdir(parents=True)
        return directory

    def _expected(error_code: str, observed: str, *, detail: str) -> dict[str, Any]:
        detected = observed == error_code
        return {
            "attack_id": detail,
            "target_contract": "experiment_evidence_consistency",
            "target_file": "shard_registry.jsonl",
            "mutation": detail,
            "baseline_target_status": "PASS",
            "mutant_target_status": "FAIL" if detected else "PASS",
            "attributable_error_code": observed,
            "new_error_codes": [observed] if detected else [],
            "detected": detected,
            "baseline_all_pass": True,
            "mutant_all_pass": not detected,
        }

    # S1 duplicate recovery of a committed shard
    directory = _new_dir("1")
    registry = directory / "reg.jsonl"
    kwargs = {"run_root": str(directory), "run_instance_id": run_id, "shard_id": "s1",
              "shard_plan_hash": plan, "evaluation_lines": [b'{"K":0,"p":0.001,'
                                                            b'"reject":true}\n'],
              "feature_lines": [b'{"f":1}\n'], "evaluation_meta": {}, "feature_meta": {},
              "registry_path": str(registry)}
    shardio.commit_shard(**kwargs)
    try:
        shardio.repair_orphan(
            run_root=str(directory), run_instance_id=run_id, shard_id="s1",
            registry_path=str(registry), recompute_to=str(directory / "re"),
            expected_manifest_bytes=b"{}", expected_evaluation_bytes=b"",
            expected_feature_bytes=b"", expected_shard_plan_hash=plan)
        observed = "ACCEPTED"
    except shardio.ShardError as exc:
        observed = str(exc).split(":")[0]
    records.append(_expected("NOT_AN_ORPHAN", observed,
                             detail="S1 repair of an already-committed shard"))

    # S2/S3 wrong identities
    for tag, override, code in (
        ("2", {"run_instance_id": H("other_run")}, "ORPHAN_IDENTITY_MISMATCH"),
        ("3", {"shard_id": H("other_shard")}, "ORPHAN_IDENTITY_MISMATCH"),
    ):
        directory = _new_dir(tag)
        final = directory / run_id / "s.final"
        final.mkdir(parents=True)
        evaluation = b'{"K":0,"p":0.001,"reject":true}\n'
        feature = b'{"f":1}\n'
        manifest = shardio.build_shard_manifest(
            run_instance_id=run_id, shard_id="s", shard_plan_hash=plan,
            evaluation={"scientific_hash": hashlib.sha256(evaluation).hexdigest()},
            feature={"scientific_hash": hashlib.sha256(feature).hexdigest()})
        manifest.update(override)
        manifest_bytes = canonical_json_bytes(manifest) + b"\n"
        (final / "shard_manifest.json").write_bytes(manifest_bytes)
        (final / "evaluation.scientific.jsonl").write_bytes(evaluation)
        (final / "feature.scientific.jsonl").write_bytes(feature)
        try:
            shardio.repair_orphan(
                run_root=str(directory), run_instance_id=run_id, shard_id="s",
                registry_path=str(directory / "reg.jsonl"),
                recompute_to=str(directory / "re"),
                expected_manifest_bytes=manifest_bytes,
                expected_evaluation_bytes=evaluation, expected_feature_bytes=feature,
                expected_shard_plan_hash=plan)
            observed = "ACCEPTED"
        except shardio.ShardError as exc:
            observed = str(exc).split(":")[0]
        records.append(_expected(code, observed, detail=f"S{tag} wrong identity"))

    # S4 zero payload hash
    directory = _new_dir("4")
    final = directory / run_id / "s.final"
    final.mkdir(parents=True)
    manifest = shardio.build_shard_manifest(
        run_instance_id=run_id, shard_id="s", shard_plan_hash=plan,
        evaluation={"scientific_hash": "0" * 64}, feature={"scientific_hash": "0" * 64})
    manifest_bytes = canonical_json_bytes(manifest) + b"\n"
    (final / "shard_manifest.json").write_bytes(manifest_bytes)
    (final / "evaluation.scientific.jsonl").write_bytes(b'{"K":0}\n')
    (final / "feature.scientific.jsonl").write_bytes(b'{"f":1}\n')
    try:
        shardio.repair_orphan(
            run_root=str(directory), run_instance_id=run_id, shard_id="s",
            registry_path=str(directory / "reg.jsonl"), recompute_to=str(directory / "re"),
            expected_manifest_bytes=manifest_bytes,
            expected_evaluation_bytes=b'{"K":0}\n', expected_feature_bytes=b'{"f":1}\n',
            expected_shard_plan_hash=plan)
        observed = "ACCEPTED"
    except shardio.ShardError as exc:
        observed = str(exc).split(":")[0]
    records.append(_expected("MANIFEST_PAYLOAD_HASH_INVALID", observed,
                             detail="S4 all-zero payload hash"))

    # S5 a rewritten event whose old hash was kept
    directory = _new_dir("5")
    registry = directory / "reg.jsonl"
    shardio.commit_shard(**{**kwargs, "run_root": str(directory),
                            "registry_path": str(registry)})
    lines = registry.read_text(encoding="utf-8").splitlines()
    tampered = json.loads(lines[0])
    tampered["shard_id"] = "rewritten"
    registry.write_text(json.dumps(tampered) + "\n", encoding="utf-8")
    try:
        shardio.commit_shard(**{**kwargs, "run_root": str(directory),
                                "registry_path": str(registry), "shard_id": "s5b"})
        observed = "ACCEPTED"
    except (shardio.ShardError, chains.ChainError) as exc:
        observed = str(exc).split(":")[0]
    records.append(_expected("CHAIN_TAIL_TAMPERED", observed,
                             detail="S5 rewritten event with its old hash kept"))

    # S6 missing parent link (schema-2 event without prev)
    directory = _new_dir("6")
    registry = directory / "reg.jsonl"
    orphan_event = {"schema_version": 2, "seq": 0, "event_type": "SHARD_COMMITTED",
                    "run_instance_id": run_id, "shard_id": "s6"}
    chains.append_cas(str(registry), orphan_event, expected_tip=None,
                      hash_field="shard_commit_hash", verify_tail=False)
    issues = chains.verify_chain(registry, hash_field="shard_commit_hash",
                                 parent_field="prev_event_hash")
    observed = "MISSING_PARENT_LINK" if any("missing" in i for i in issues) else "ACCEPTED"
    records.append(_expected("MISSING_PARENT_LINK", observed,
                             detail="S6 schema-2 event with no parent link"))
    return records


def main() -> int:
    parser = argparse.ArgumentParser(description="attack regression (§6)")
    parser.add_argument("out", help="output directory (outside the repo)")
    parser.add_argument("--keep-package", action="store_true")
    args = parser.parse_args()

    out = Path(args.out).expanduser()
    if out.exists():
        shutil.rmtree(out)
    (out / "attacks").mkdir(parents=True)
    package = out / "package"
    package.mkdir()

    package_info = build_package(package)
    baseline = check_package(package)
    _write(out / "baseline.json", baseline)

    with tempfile.TemporaryDirectory() as scratch:
        scratch_path = Path(scratch)
        for attack in _mutations(package):
            # every mutation runs on its own copy: one attack must not change the
            # baseline another attack is judged against
            copy = scratch_path / attack["id"]
            shutil.copytree(package, copy)
            record = run_attack(attack, copy)
            RECORDS.append(record)
            _write(out / "attacks" / f"{record['attack_id']}.json", record)

        probe_records = _probe_records(scratch_path / "shard_probes")
        for record in probe_records:
            RECORDS.append(record)
            _write(out / "attacks" / f"{record['attack_id'].split()[0]}.json", record)

    summary = summarise_attacks(RECORDS)
    summary["package"] = {"scope_rows": package_info["scope_rows"],
                          "baseline_layers": {
                              name: baseline["layers"][name]["status"]
                              for name in baseline["layers"]},
                          "baseline_admissible": baseline["admissible"]}
    summary["platform"] = sys.platform
    _write(out / "SUMMARY.json", summary)
    if not args.keep_package:
        shutil.rmtree(package, ignore_errors=True)
        (out / "fixture").unlink(missing_ok=True)
    print(json.dumps({k: summary[k] for k in
                      ("attacks", "eligible_baselines", "detected", "undetected",
                       "not_scored", "detection_rate")}, ensure_ascii=False))
    return 1 if summary["undetected"] else 0


if __name__ == "__main__":
    sys.exit(main())
