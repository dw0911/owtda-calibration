"""The attack harness: three layers, differential attribution, honest disclosure."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

from owtda_cal.attack_harness import check_package, run_attack, summarise_attacks


def _package(tmp_path: Path, **overrides) -> Path:
    root = tmp_path / "package"
    root.mkdir(exist_ok=True)
    rows = [
        {"evaluation_id": f"e{i}", "K": i, "p": (i + 1) / 1000,
         "reject": i <= 49, "feature_id": "bpi", "method_id": "M0"}
        for i in range(3)
    ]
    ledger = root / "evaluation_ledger.jsonl"
    ledger.write_text("".join(json.dumps(r, sort_keys=True) + "\n" for r in rows),
                      encoding="utf-8")
    (root / "scope_rows.jsonl").write_text(
        "".join(json.dumps({"logical_cell_id": f"c{i}"}, sort_keys=True) + "\n"
                for i in range(3)), encoding="utf-8")
    (root / "analysis_output.json").write_text(
        json.dumps({"rows": 3, "ledger_sha256":
                    hashlib.sha256(ledger.read_bytes()).hexdigest()}), encoding="utf-8")
    (root / "inline_verdict.json").write_text(json.dumps({"verdict": "PASS"}),
                                              encoding="utf-8")
    (root / "G4_H0_CERTIFICATE.json").write_text(json.dumps({"kind": "g4"}), encoding="utf-8")
    seal = root / "RUN_SEAL.json"
    seal.write_text(json.dumps({"seal": "x"}), encoding="utf-8")
    (root / "package_manifest.json").write_text(json.dumps({
        "objects": [{"path": "RUN_SEAL.json",
                     "sha256": hashlib.sha256(seal.read_bytes()).hexdigest()}],
    }), encoding="utf-8")
    for name, value in overrides.items():
        (root / name).write_text(json.dumps(value), encoding="utf-8")
    return root


class TestLayers:
    def test_a_clean_package_passes_all_three(self, tmp_path):
        result = check_package(_package(tmp_path))
        assert {name: layer["status"] for name, layer in result["layers"].items()} == {
            "package_integrity": "PASS",
            "experiment_evidence_consistency": "PASS",
            "formal_admission": "PASS",
        }
        assert result["admissible"] is True

    def test_a_deleted_ledger_fails_the_evidence_layer_only(self, tmp_path):
        root = _package(tmp_path)
        (root / "evaluation_ledger.jsonl").unlink()
        result = check_package(root)
        assert result["layers"]["package_integrity"]["status"] == "PASS"
        assert result["layers"]["experiment_evidence_consistency"]["status"] == "FAIL"
        assert [i["code"] for i in
                result["layers"]["experiment_evidence_consistency"]["issues"]] == [
            "LEDGER_MISSING"]

    def test_a_missing_certificate_fails_admission_only(self, tmp_path):
        root = _package(tmp_path)
        (root / "G4_H0_CERTIFICATE.json").unlink()
        result = check_package(root)
        assert result["layers"]["package_integrity"]["status"] == "PASS"
        assert result["layers"]["experiment_evidence_consistency"]["status"] == "PASS"
        assert result["layers"]["formal_admission"]["status"] == "FAIL"
        codes = [i["code"] for i in result["layers"]["formal_admission"]["issues"]]
        assert codes[0] == "G4_H0_CERTIFICATE_MISSING"
        # the package still claims PASS, so it is also a disclosure mismatch
        assert "DISCLOSURE_INCONSISTENT" in codes
        assert result["disclosure"]["disclosed_consistently"] is False

    def test_an_honest_failure_is_disclosed_not_hidden(self, tmp_path):
        root = _package(tmp_path)
        (root / "G4_H0_CERTIFICATE.json").unlink()
        (root / "inline_verdict.json").write_text(json.dumps({"verdict": "FAIL"}),
                                                  encoding="utf-8")
        result = check_package(root)
        # the package says FAIL and the recomputation says FAIL: they agree
        assert result["disclosure"]["disclosed_consistently"] is True
        assert result["admissible"] is False
        assert "DISCLOSURE_INCONSISTENT" not in [
            i["code"] for i in result["layers"]["formal_admission"]["issues"]]

    def test_a_hidden_failure_is_a_disclosure_defect(self, tmp_path):
        root = _package(tmp_path)
        (root / "evaluation_ledger.jsonl").unlink()
        result = check_package(root)
        assert result["disclosure"]["disclosed_consistently"] is False
        assert "DISCLOSURE_INCONSISTENT" in [
            i["code"] for i in result["layers"]["formal_admission"]["issues"]]


class TestDifferentialAttribution:
    def _attack(self, name: str, mutate, *, contract: str = "experiment_evidence_consistency"):
        return {"id": name, "target_contract": contract,
                "target_file": "evaluation_ledger.jsonl", "mutation": name,
                "apply": mutate}

    def test_a_detected_attack_names_its_new_error_code(self, tmp_path):
        root = _package(tmp_path)

        def mutate(pkg: Path) -> None:
            path = pkg / "evaluation_ledger.jsonl"
            rows = [json.loads(x) for x in path.read_text(encoding="utf-8").splitlines()]
            rows[0]["p"] = rows[0]["p"] + 0.0001
            path.write_text("".join(json.dumps(r, sort_keys=True) + "\n" for r in rows),
                            encoding="utf-8")

        record = run_attack(self._attack("nudge_p", mutate), root)
        assert record["detected"] is True
        assert record["baseline_target_status"] == "PASS"
        assert record["mutant_target_status"] == "FAIL"
        assert "P_OFF_GRID" in record["new_error_codes"]
        assert record["attributable_error_code"] is not None
        for field in ("target_contract", "target_file", "mutation",
                      "baseline_target_status", "mutant_target_status",
                      "attributable_error_code"):
            assert field in record

    def test_an_attack_on_an_already_failing_baseline_is_not_scored(self, tmp_path):
        root = _package(tmp_path)
        (root / "evaluation_ledger.jsonl").unlink()  # layer already fails

        def noop(pkg: Path) -> None:
            return None

        record = run_attack(self._attack("noop_on_broken_baseline", noop), root)
        assert record["baseline_target_status"] == "FAIL"
        assert record["detected"] is False
        summary = summarise_attacks([record])
        assert summary["eligible_baselines"] == 0
        assert summary["detection_rate"] is None
        assert summary["not_scored"] == ["noop_on_broken_baseline"]

    def test_the_rate_counts_only_eligible_attacks(self, tmp_path):
        root = _package(tmp_path)

        def noop(pkg: Path) -> None:
            return None

        good = run_attack(self._attack("noop_clean", noop), root)
        (root / "evaluation_ledger.jsonl").unlink()
        bad = run_attack(self._attack("noop_broken", noop), root)
        summary = summarise_attacks([good, bad])
        assert summary["attacks"] == 2
        assert summary["eligible_baselines"] == 1
        assert summary["undetected"] == ["noop_clean"]
        assert summary["detection_rate"] == 0.0
        assert "already failed the target" in summary["note"]
