"""Tests for registry entry builders/validators (Plan §15.1-§15.3)."""

import pytest

from owtda_cal import registry
from owtda_cal.identity import H

_PID = "owtda-cal-r1"
_PRT = "p"
_FZ = "f" * 64
_EG = "G01"
_AA = "a" * 64
_ROOT = "ab" * 32


class TestSeedRegistry:
    def test_entry_hash_matches_formula(self):
        e = registry.seed_entry(
            project_id=_PID, protocol_id=_PRT, freeze_id=_FZ,
            evidence_generation_id=_EG, phase="NULL", stream_family="null_data",
            component_generation_id="D01", root_key_hex=_ROOT,
        )
        from owtda_cal.seeding import root_key_commitment

        assert e["root_key_commitment"] == root_key_commitment(_ROOT)
        assert e["root_entry_hash"] == H(
            "root_entry",
            project_id=_PID, protocol_id=_PRT, freeze_id=_FZ,
            evidence_generation_id=_EG, phase="NULL", stream_family="null_data",
            component_generation_id="D01",
            root_key_commitment=root_key_commitment(_ROOT),
        )

    def test_requires_exactly_one_of_key_ref(self):
        with pytest.raises(ValueError):
            registry.seed_entry(
                project_id=_PID, protocol_id=_PRT, freeze_id=_FZ,
                evidence_generation_id=_EG, phase="NULL",
                stream_family="real_M0", component_generation_id="M01",
            )
        with pytest.raises(ValueError):
            registry.seed_entry(
                project_id=_PID, protocol_id=_PRT, freeze_id=_FZ,
                evidence_generation_id=_EG, phase="NULL",
                stream_family="real_M0", component_generation_id="M01",
                root_key_hex=_ROOT, secret_ref="sec:1",
            )

    def test_validate_duplicates_rejected(self):
        e1 = registry.seed_entry(
            project_id=_PID, protocol_id=_PRT, freeze_id=_FZ,
            evidence_generation_id=_EG, phase="NULL", stream_family="null_data",
            component_generation_id="D01", root_key_hex=_ROOT,
        )
        e2 = dict(e1)
        e2["root_key_hex"] = "cd" * 32  # same key but different bytes
        with pytest.raises(ValueError):
            registry.validate_seed_registry([e1, e2])


class TestFamilyPhase:
    def test_allowed_mapping(self):
        registry.assert_family_phase_allowed("null_data", "NULL")
        registry.assert_family_phase_allowed("smoke", "SMOKE_NULL")
        with pytest.raises(ValueError):
            registry.assert_family_phase_allowed("null_data", "ALT")

    def test_smoke_formal_separation(self):
        registry.assert_smoke_formal_separation("SMOKE_NULL", "smoke")
        registry.assert_smoke_formal_separation("NULL", "null_data")
        with pytest.raises(ValueError):
            registry.assert_smoke_formal_separation("SMOKE_NULL", "null_data")
        with pytest.raises(ValueError):
            registry.assert_smoke_formal_separation("NULL", "smoke")


class TestComponentRegistry:
    def test_entry_and_hash(self):
        e = registry.component_entry(
            project_id=_PID, protocol_id=_PRT, freeze_id=_FZ,
            evidence_generation_id=_EG, component_kind="feature",
            stable_id="BPI_FIXED20_H01_SIGMA005_GAMMA1_V1",
            component_generation_id="V1", config_hash=_AA,
            code_file_manifest_hash=_AA,
        )
        assert e["component_registry_entry_hash"] == H(
            "component_registry_entry",
            project_id=_PID, protocol_id=_PRT, freeze_id=_FZ,
            evidence_generation_id=_EG, component_kind="feature",
            stable_id="BPI_FIXED20_H01_SIGMA005_GAMMA1_V1",
            component_generation_id="V1", config_hash=_AA,
            code_file_manifest_hash=_AA,
        )
        assert registry.validate_component_registry([e]) == [e]

    def test_duplicate_rejected(self):
        e1 = registry.component_entry(
            project_id=_PID, protocol_id=_PRT, freeze_id=_FZ,
            evidence_generation_id=_EG, component_kind="feature",
            stable_id="X", component_generation_id="V1", config_hash=_AA,
            code_file_manifest_hash=_AA,
        )
        e2 = dict(e1, config_hash="b" * 64)  # same compound key, different bytes
        with pytest.raises(ValueError):
            registry.validate_component_registry([e1, e2])


class TestSecretRegistry:
    def test_entry(self):
        e = registry.secret_commitment_entry(
            project_id=_PID, protocol_id=_PRT, freeze_id=_FZ,
            evidence_generation_id=_EG, task_index_generation_id="TI01",
            secret_kind=registry.SECRET_KIND_CANDIDATE,
            secret_ref="secret://candidate", secret_commitment=_AA,
        )
        assert len(e["secret_entry_hash"]) == 64
        registry.validate_secret_registry([e])

    def test_bad_kind_rejected(self):
        with pytest.raises(ValueError):
            registry.secret_commitment_entry(
                project_id=_PID, protocol_id=_PRT, freeze_id=_FZ,
                evidence_generation_id=_EG, task_index_generation_id="TI01",
                secret_kind="NOPE", secret_ref="r", secret_commitment=_AA,
            )


class TestSnapshot:
    def test_sorted_dedup_golden(self):
        h = registry.registry_snapshot_hash(["2" * 64, "1" * 64, "2" * 64])
        expected = H("registry_snapshot", entry_hashes=["1" * 64, "2" * 64])
        assert h == expected

    def test_bad_hash_rejected(self):
        with pytest.raises(ValueError):
            registry.registry_snapshot_hash(["nope"])
