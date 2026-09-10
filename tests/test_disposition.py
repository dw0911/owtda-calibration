"""REAL_DISPOSITION chain attacks (Plan §2.3, §16.2, §19 #80/#82)."""

import json
from pathlib import Path

import pytest

from owtda_cal import chains, disposition

REPO = Path(__file__).resolve().parents[1]
GOV = REPO / "governance"

_BASE = {
    "project_id": "owtda-cal-r1",
    "protocol_id": "P",
    "freeze_id": "f" * 64,
    "evidence_generation_id": "G01",
}
_REASON_KW = {
    "reason_code": "TASK_GATE_MIN_TASKS_NOT_MET",
    "admitted_subjects": 8,
    "min_subjects_required": 8,
    "eligible_tasks": 23,
    "min_tasks_required": 24,
    "subjects_without_candidate": ["subject109"],
    "dataset_hash": "a" * 64,
    "task_builder_config_hash": "b" * 64,
}


def _event(**overrides):
    reason = disposition.reason_object(**_REASON_KW)
    kwargs = {
        **_BASE,
        "disposition_status": "REAL_OMITTED_BY_DATA_GATE",
        "disposition_stage": "REAL_DATA_FROZEN",
        "reason_code": "TASK_GATE_MIN_TASKS_NOT_MET",
        "reason_object_hash_value": disposition.reason_object_hash(reason),
        "task_index_seal_hash": None,
        "truth_unsealed": False,
        "prev_real_disposition_event_hash": disposition.genesis_hash(**_BASE),
    }
    kwargs.update(overrides)
    return disposition.event(**kwargs)


class TestReasonObject:
    def test_reason_hash_stable_and_gate_false(self):
        reason = disposition.reason_object(**_REASON_KW)
        assert reason["gate"]["pass"] is False
        assert disposition.reason_object_hash(reason) == disposition.reason_object_hash(
            disposition.reason_object(**_REASON_KW)
        )

    def test_reason_hash_tracks_any_value(self):
        base = disposition.reason_object_hash(disposition.reason_object(**_REASON_KW))
        changed = disposition.reason_object(**{**_REASON_KW, "eligible_tasks": 24})
        assert disposition.reason_object_hash(changed) != base

    def test_unknown_reason_code_rejected(self):
        with pytest.raises(disposition.DispositionError):
            disposition.reason_object(**{**_REASON_KW, "reason_code": "NOPE"})


class TestEventContracts:
    def test_event_fields_exact(self):
        ev = _event()
        assert set(ev) == disposition.EVENT_FIELDS

    def test_deferred_requires_seal_and_sealed_truth(self):
        with pytest.raises(disposition.DispositionError):
            _event(disposition_status="REAL_DEFERRED", task_index_seal_hash=None)
        with pytest.raises(disposition.DispositionError):
            _event(
                disposition_status="REAL_DEFERRED",
                task_index_seal_hash="c" * 64,
                truth_unsealed=True,
            )

    def test_omitted_must_keep_truth_sealed(self):
        with pytest.raises(disposition.DispositionError):
            _event(truth_unsealed=True)

    def test_unknown_enums_rejected(self):
        with pytest.raises(disposition.DispositionError):
            _event(disposition_status="WHATEVER")
        with pytest.raises(disposition.DispositionError):
            _event(disposition_stage="WHATEVER")
        with pytest.raises(disposition.DispositionError):
            _event(reason_code="WHATEVER")


class TestChainValidation:
    def _write(self, path, *events):
        prev = None
        lines = []
        for ev in events:
            payload = {k: v for k, v in ev.items()}
            if prev is not None:
                payload["prev_real_disposition_event_hash"] = prev
            h = chains.event_hash(payload)
            lines.append(json.dumps({**payload, "disposition_hash": h}))
            prev = h
        path.write_text("\n".join(lines) + "\n", encoding="utf-8")

    def test_single_event_chain_valid(self, tmp_path):
        path = tmp_path / "chain.jsonl"
        self._write(path, _event())
        info = disposition.validate_chain(path)
        assert info["event_count"] == 1
        assert info["latest_status"] == "REAL_OMITTED_BY_DATA_GATE"
        assert info["truth_unsealed"] is False

    def test_two_event_chain_valid(self, tmp_path):
        path = tmp_path / "chain.jsonl"
        self._write(
            path,
            _event(),
            _event(
                disposition_status="REAL_DEFERRED",
                task_index_seal_hash="d" * 64,
                disposition_stage="REAL_TASKS_FROZEN",
            ),
        )
        info = disposition.validate_chain(path)
        assert info["event_count"] == 2 and info["latest_status"] == "REAL_DEFERRED"

    def test_tampered_hash_rejected(self, tmp_path):
        path = tmp_path / "chain.jsonl"
        self._write(path, _event())
        data = json.loads(path.read_text(encoding="utf-8").strip())
        data["reason_code"] = "COMPUTE_SCHEDULE_GATE_FAIL"
        path.write_text(json.dumps(data) + "\n", encoding="utf-8")
        with pytest.raises(disposition.DispositionError):
            disposition.validate_chain(path)

    def test_wrong_parent_rejected(self, tmp_path):
        path = tmp_path / "chain.jsonl"
        ev = _event(prev_real_disposition_event_hash="9" * 64)
        h = chains.event_hash(ev)
        path.write_text(json.dumps({**ev, "disposition_hash": h}) + "\n", encoding="utf-8")
        with pytest.raises(disposition.DispositionError):
            disposition.validate_chain(path)

    def test_forked_chain_rejected(self, tmp_path):
        path = tmp_path / "chain.jsonl"
        first = _event()
        h1 = chains.event_hash(first)
        # two distinct children both point at h1: the second is a fork/branch
        child_a = _event(disposition_stage="REAL_TASKS_FROZEN")
        child_b = _event(disposition_stage="REAL_PREDICTION_ADMISSION")
        path.write_text(
            json.dumps({**first, "disposition_hash": h1})
            + "\n"
            + json.dumps(
                {
                    **child_a,
                    "prev_real_disposition_event_hash": h1,
                    "disposition_hash": chains.event_hash(child_a),
                }
            )
            + "\n"
            + json.dumps(
                {
                    **child_b,
                    "prev_real_disposition_event_hash": h1,
                    "disposition_hash": chains.event_hash(child_b),
                }
            )
            + "\n",
            encoding="utf-8",
        )
        with pytest.raises(disposition.DispositionError):
            disposition.validate_chain(path)

    def test_empty_chain_rejected(self, tmp_path):
        path = tmp_path / "chain.jsonl"
        path.write_text("", encoding="utf-8")
        with pytest.raises(disposition.DispositionError):
            disposition.validate_chain(path)


class TestFrozenChainOnDisk:
    def test_frozen_chain_valid_and_truth_sealed(self):
        info = disposition.validate_chain(GOV / "REAL_DISPOSITION.jsonl")
        assert info["latest_status"] == "REAL_OMITTED_BY_DATA_GATE"
        assert info["latest_stage"] == "REAL_DATA_FROZEN"
        assert info["truth_unsealed"] is False

    def test_reason_object_file_rehashes(self):
        disposition.validate_chain(GOV / "REAL_DISPOSITION.jsonl")
        events = disposition.read_events(GOV / "REAL_DISPOSITION.jsonl")
        r_hash = events[-1]["reason_object_hash"]
        reason = json.loads(
            (GOV / f"REAL_DISPOSITION_REASON_{r_hash}.json").read_text(encoding="utf-8")
        )
        assert disposition.reason_object_hash(reason) == r_hash
        assert reason["gate"]["admitted_subjects"] == 8
        assert reason["gate"]["eligible_tasks"] == 23
