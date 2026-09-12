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
    verify_chain,
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

    def test_lock_file_persists_and_is_reacquirable(self, tmp_path):
        """Re-audit 2026-09-13: the holder must not delete the lock file.

        The old ``<path>.lock`` sentinel was removed in a ``finally`` block, so a
        process killed while holding it blocked every later writer forever, and a
        cleaner could delete the file while another caller was waiting on it.
        The lock file now persists for the lifetime of the chain and ownership
        belongs to the OS, which releases it when the holding handle closes.
        """
        path = str(tmp_path / "chain.jsonl")
        first = append_cas(path, {"n": 1}, expected_tip=None, hash_field="event_hash")
        assert (tmp_path / "chain.jsonl.kernellock").exists()
        second = append_cas(path, {"n": 2}, expected_tip=first, hash_field="event_hash")
        assert read_tip(path, hash_field="event_hash") == second

    def test_tail_tamper_blocks_further_appends(self, tmp_path):
        """An event whose content is edited while its hash is kept must block."""
        path = str(tmp_path / "chain.jsonl")
        append_cas(path, {"n": 1}, expected_tip=None, hash_field="event_hash")
        lines = Path(path).read_text(encoding="utf-8").splitlines()
        tampered = json.loads(lines[0])
        tampered["n"] = 99  # content edited, stored hash kept
        Path(path).write_text(json.dumps(tampered) + "\n", encoding="utf-8")
        with pytest.raises(ChainError, match="CHAIN_TAIL_TAMPERED"):
            append_cas(path, {"n": 2}, expected_tip=tampered["event_hash"],
                       hash_field="event_hash")

    def test_full_chain_verification_detects_a_rewritten_middle(self, tmp_path):
        """O(1) tail checks cannot see the middle; the full verifier must."""
        path = str(tmp_path / "chain.jsonl")
        h1 = append_cas(path, {"n": 1}, expected_tip=None, hash_field="event_hash")
        h2 = append_cas(path, {"n": 2}, expected_tip=h1, hash_field="event_hash")
        lines = Path(path).read_text(encoding="utf-8").splitlines()
        middle = json.loads(lines[0])
        middle["n"] = 42  # hash kept -> tail check alone would not notice
        Path(path).write_text(
            json.dumps(middle) + "\n" + lines[1] + "\n", encoding="utf-8"
        )
        issues = verify_chain(path, hash_field="event_hash")
        assert issues and issues[0].startswith("line 1")
        assert h2 == read_tip(path, hash_field="event_hash")


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
