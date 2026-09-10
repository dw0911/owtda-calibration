"""Tests for append-only chains with CAS (Plan §2.3, §16.2)."""

import json
from pathlib import Path

import pytest

from owtda_cal.chains import (
    ChainError,
    append_cas,
    event_hash,
    genesis,
    phase_state_event,
    read_tip,
    validity_event,
)

_H = lambda ch: ch * 64


class TestGenesis:
    def test_deterministic_and_domain_separated(self):
        a = genesis("validity_genesis", project_id="p", protocol_id="r", freeze_id=_H("f"),
                    evidence_generation_id="G01", phase="NULL")
        b = genesis("validity_genesis", project_id="p", protocol_id="r", freeze_id=_H("f"),
                    evidence_generation_id="G01", phase="NULL")
        c = genesis("phase_state_genesis", project_id="p", protocol_id="r", freeze_id=_H("f"),
                    evidence_generation_id="G01", phase="NULL")
        assert a == b and a != c and len(a) == 64

    def test_unknown_kind_rejected(self):
        with pytest.raises(ChainError):
            genesis("nope", a=1)


class TestAppendCas:
    def test_append_and_tip(self, tmp_path):
        path = str(tmp_path / "chain.jsonl")
        assert read_tip(path, hash_field="event_hash") is None
        h1 = append_cas(path, {"event_type": "A", "n": 1},
                        expected_tip=None, hash_field="event_hash")
        assert read_tip(path, hash_field="event_hash") == h1
        h2 = append_cas(path, {"event_type": "B", "n": 2},
                        expected_tip=h1, hash_field="event_hash")
        assert read_tip(path, hash_field="event_hash") == h2
        lines = [json.loads(x) for x in Path(path).read_text(encoding="utf-8").splitlines() if x.strip()]
        assert [x["n"] for x in lines] == [1, 2]
        assert lines[1]["event_hash"] == event_hash({"event_type": "B", "n": 2})

    def test_stale_tip_rejected(self, tmp_path):
        path = str(tmp_path / "chain.jsonl")
        h1 = append_cas(path, {"n": 1}, expected_tip=None, hash_field="event_hash")
        with pytest.raises(ChainError):
            append_cas(path, {"n": 2}, expected_tip=None, hash_field="event_hash")
        # unchanged file
        assert read_tip(path, hash_field="event_hash") == h1

    def test_pre_containing_hash_field_rejected(self, tmp_path):
        path = str(tmp_path / "chain.jsonl")
        with pytest.raises(ChainError):
            append_cas(path, {"event_hash": "x"}, expected_tip=None, hash_field="event_hash")

    def test_lock_released(self, tmp_path):
        path = str(tmp_path / "chain.jsonl")
        append_cas(path, {"n": 1}, expected_tip=None, hash_field="event_hash")
        assert not (tmp_path / "chain.jsonl.lock").exists()


class TestEventBuilders:
    def test_phase_state_event(self):
        e = phase_state_event(
            project_id="p", protocol_id="r", freeze_id=_H("f"),
            evidence_generation_id="G01", phase="NULL",
            expected_parent_phase_seal_hash=None,
            expected_validity_registry_head_hash=_H("v"),
            new_active_revision_id=_H("a"), new_phase_seal_hash=_H("s"),
            prev_phase_state_event_hash=None,
        )
        assert e["event_type"] == "PHASE_ACTIVATED"
        assert len(event_hash(e)) == 64

    def test_validity_event(self):
        e = validity_event(
            project_id="p", protocol_id="r", freeze_id=_H("f"),
            evidence_generation_id="G01", phase="NULL", logical_kind="DATA",
            logical_key=_H("k"), expected_current_concrete_id=_H("c"),
            expected_current_source_run_seal_hash=_H("s"),
            reason_code="DATA_DEFECT", reason_object_hash=_H("o"),
            prev_event_hash=None,
        )
        assert e["event_type"] == "INVALIDATE"
        with pytest.raises(ChainError):
            validity_event(
                project_id="p", protocol_id="r", freeze_id=_H("f"),
                evidence_generation_id="G01", phase="NULL", logical_kind="NOPE",
                logical_key=_H("k"), expected_current_concrete_id=_H("c"),
                expected_current_source_run_seal_hash=_H("s"),
                reason_code="X", reason_object_hash=_H("o"), prev_event_hash=None,
            )
