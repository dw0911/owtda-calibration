"""The FORMAL_H0 admission gate: every missing binding refuses with a code."""

from __future__ import annotations

import hashlib
import json

from owtda_cal.formal_admission import check_g4_h0_certificate

PLAN_HASHES = {"NULL": "a" * 64, "ALT": "b" * 64}


def _plan(**overrides) -> dict:
    plan = {
        "formal_scale": True,
        "phases": {phase: {"index_hashes": {"evaluation": digest}}
                   for phase, digest in PLAN_HASHES.items()},
    }
    plan.update(overrides)
    return plan


def _certificate(tmp_path, **overrides):
    registry = tmp_path / "SEED_REGISTRY.json"
    registry.write_text('{"entries": []}\n', encoding="utf-8")
    body = {
        "kind": "g4_h0_certificate",
        "phase": "H0",
        "status": "FROZEN",
        "evaluation_index_hashes": dict(PLAN_HASHES),
        "seed_registry_sha256": hashlib.sha256(registry.read_bytes()).hexdigest(),
    }
    body.update(overrides)
    path = tmp_path / "G4_H0_CERTIFICATE.json"
    path.write_text(json.dumps(body), encoding="utf-8")
    return path, registry


def _check(tmp_path, **overrides):
    path, registry = _certificate(tmp_path, **overrides.pop("certificate", {}))
    return check_g4_h0_certificate(
        certificate_path=overrides.pop("certificate_path", path),
        plan_summary=overrides.pop("plan", _plan()),
        seed_registry_path=overrides.pop("seed_registry_path", registry))


class TestAdmission:
    def test_a_fully_bound_certificate_admits(self, tmp_path):
        decision = _check(tmp_path)
        assert decision["status"] == "ADMITTED_PENDING_DISPATCH"
        assert decision["admitted"] is True
        assert decision["codes"] == []
        assert "not a run" in decision["note"]

    def test_a_missing_certificate_refuses(self, tmp_path):
        decision = _check(tmp_path, certificate_path=tmp_path / "nope.json")
        assert "CERTIFICATE_MISSING" in decision["codes"]
        assert decision["admitted"] is False

    def test_an_unparseable_certificate_refuses(self, tmp_path):
        bad = tmp_path / "bad.json"
        bad.write_text("{not json", encoding="utf-8")
        decision = _check(tmp_path, certificate_path=bad)
        assert "CERTIFICATE_UNPARSEABLE" in decision["codes"]

    def test_the_wrong_kind_refuses(self, tmp_path):
        decision = _check(tmp_path, certificate={"kind": "something_else"})
        assert "CERTIFICATE_WRONG_KIND" in decision["codes"]

    def test_a_reduced_plan_can_never_be_admitted(self, tmp_path):
        decision = _check(tmp_path, plan=_plan(formal_scale=False))
        assert "PLAN_NOT_FORMAL_SCALE" in decision["codes"]
        assert decision["admitted"] is False

    def test_a_certificate_for_another_plan_refuses(self, tmp_path):
        decision = _check(tmp_path, certificate={"evaluation_index_hashes":
                                                 {"NULL": "c" * 64}})
        assert "CERTIFICATE_PLAN_BINDING_MISMATCH" in decision["codes"]

    def test_an_unfrozen_certificate_refuses(self, tmp_path):
        decision = _check(tmp_path, certificate={"status": "DRAFT"})
        assert "CERTIFICATE_NOT_FROZEN" in decision["codes"]

    def test_a_phase_mismatch_refuses(self, tmp_path):
        decision = _check(tmp_path, certificate={"phase": "H1"})
        assert "CERTIFICATE_PHASE_MISMATCH" in decision["codes"]

    def test_a_seed_registry_that_does_not_match_refuses(self, tmp_path):
        _path, registry = _certificate(tmp_path)
        registry.write_text('{"entries": ["changed"]}\n', encoding="utf-8")
        decision = check_g4_h0_certificate(
            certificate_path=tmp_path / "G4_H0_CERTIFICATE.json",
            plan_summary=_plan(), seed_registry_path=registry)
        assert "SEED_REGISTRY_HASH_MISMATCH" in decision["codes"]

    def test_a_missing_seed_registry_refuses(self, tmp_path):
        decision = _check(tmp_path, seed_registry_path=tmp_path / "gone.json")
        assert decision["codes"] == ["SEED_REGISTRY_MISSING"]

    def test_a_plan_without_index_hashes_refuses(self, tmp_path):
        decision = _check(tmp_path, plan={"formal_scale": True, "phases": {}})
        assert "PLAN_UNBOUND_EVALUATION_INDEX" in decision["codes"]

    def test_every_refusal_carries_a_code_and_a_reason(self, tmp_path):
        decision = _check(tmp_path, certificate_path=tmp_path / "nope.json")
        assert decision["reasons"][0]["where"].endswith("nope.json")
        assert decision["reasons"][0]["detail"]
