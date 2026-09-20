"""Golden tests for PAMAP2 transition-task construction (Plan §13.3)."""

import json
from pathlib import Path

import numpy as np
import pytest

from owtda_cal.hashing import array_hash
from owtda_cal.pamap2_tasks import (
    CONTEXT_SPAN,
    TASK_SIGNAL_OBJECT_KIND,
    TaskBuildError,
    bouts,
    build_task,
    candidate_identity,
    draw_context_lengths,
    eligibility_rows,
    real_data_task_gate,
    task_candidate_id,
    task_id,
    transition_candidates,
    write_sanitized_task,
)

_SALT = "ef" * 32
_ROOT = "cd" * 32


def _candidate():
    act, grid, chest = _segment()
    return act, grid, chest, transition_candidates(act)[0]


def _segment(n_a=3100, n_zero=100, n_b=3200, act_a=1, act_b=2):
    act = np.concatenate([
        np.full(n_a, act_a, dtype=np.int64),
        np.full(n_zero, 0, dtype=np.int64),
        np.full(n_b, act_b, dtype=np.int64),
    ])
    grid = np.arange(act.shape[0], dtype=np.int64)
    chest = np.random.default_rng(3).standard_normal((act.shape[0], 3)) * 0.1
    return act, grid, chest


class TestBouts:
    def test_runs(self):
        act = np.array([1, 1, 0, 2, 2, 2, 0])
        bs = bouts(act)
        assert [(b.activity, b.start, b.end) for b in bs] == [(1, 0, 2), (2, 3, 6)]


class TestCandidates:
    def test_accepts_transition(self):
        act, _, _ = _segment()
        cands = transition_candidates(act)
        assert len(cands) == 1
        assert cands[0]["zero_rows"] == 100

    def test_rejects_short_bout(self):
        act, _, _ = _segment(n_a=2999)
        assert transition_candidates(act) == []

    def test_rejects_long_zero_run(self):
        act, _, _ = _segment(n_zero=501)
        assert transition_candidates(act) == []

    def test_rejects_nonzero_gap(self):
        act = np.concatenate([
            np.full(3100, 1), np.full(50, 3), np.full(3200, 2)
        ]).astype(np.int64)
        assert transition_candidates(act) == []

    def test_rejects_same_activity(self):
        act, _, _ = _segment(act_a=2, act_b=2)
        assert transition_candidates(act) == []


class TestIdentityAndContext:
    def test_identity_and_candidate_id(self):
        ident = candidate_identity(
            dataset_hash="a" * 64, relative_file_path="Protocol/subject101.dat",
            subject_internal_id="subject101", analysis_segment_id=0,
            activity_A=1, A_grid_start=0, A_grid_end=3100,
            activity_B=2, B_grid_start=3200, B_grid_end=6400,
            zero_grid_start=3100, zero_grid_end=3199,
        )
        cid = task_candidate_id(ident)
        assert cid == task_candidate_id(dict(ident))
        assert cid != task_candidate_id(dict(ident, activity_B=3))
        assert len(cid) == 64

    def test_context_lengths_range_and_inequality(self):
        for i in range(120):
            la, lb = draw_context_lengths(
                root_key_hex=_ROOT, dataset_hash="a" * 64,
                task_candidate_id=f"{i:064x}", task_index_generation_id="TI01",
                task_builder_config_hash="b" * 64,
            )
            assert 20 <= la <= 20 + CONTEXT_SPAN - 1
            assert 20 <= lb <= 20 + CONTEXT_SPAN - 1
            assert la != lb

    def test_context_deterministic(self):
        kw = {
            "root_key_hex": _ROOT,
            "dataset_hash": "a" * 64,
            "task_candidate_id": "c" * 64,
            "task_index_generation_id": "TI01",
            "task_builder_config_hash": "b" * 64,
        }
        assert draw_context_lengths(**kw) == draw_context_lengths(**kw)


class TestBuildTask:
    def test_extraction_and_truth(self):
        _, grid, chest, cand = _candidate()
        t = build_task(segment_chest_g=chest, segment_grid=grid, candidate=cand,
                       L_A=20, L_B=21)
        T = t["signal"].shape[0]
        assert T == 100 * 20 + 100 + 100 * 21 == 4200
        assert np.array_equal(t["sample_index"], np.arange(1, T + 1))
        assert t["relative_s"][0] == 0.0
        assert t["relative_s"][-1] == pytest.approx((T - 1) / 100)
        assert t["truth"]["truth_sample_left"] == 2000
        assert t["truth"]["truth_sample_right"] == 2000 + 100 + 1
        assert t["truth"]["truth_relative_s_left"] == pytest.approx(19.995)
        assert t["truth"]["truth_relative_s_right"] == pytest.approx(20.995)
        assert t["task_signal_hash"] == array_hash(
            TASK_SIGNAL_OBJECT_KIND, t["signal"], dtype_code=">f8"
        )

    def test_context_content_matches_source(self):
        _act, grid, chest, cand = _candidate()
        t = build_task(segment_chest_g=chest, segment_grid=grid, candidate=cand,
                       L_A=20, L_B=20)
        a_end = cand["A"].end
        assert np.array_equal(t["signal"][0], chest[a_end - 2000])
        assert np.array_equal(t["signal"][-1], chest[cand["B"].start + 1999])

    def test_insufficient_context(self):
        _act, grid, chest, cand = _candidate()
        with pytest.raises(TaskBuildError):
            build_task(segment_chest_g=chest, segment_grid=grid, candidate=cand,
                       L_A=19, L_B=20)


class TestTaskId:
    def test_deterministic_and_sensitive(self):
        kw = {
            "real_task_id_salt_hex": _SALT,
            "task_candidate_id": "a" * 64,
            "task_index_generation_id": "TI01",
            "task_builder_config_hash": "b" * 64,
            "L_A": 20,
            "L_B": 21,
            "task_root_entry_hash": "c" * 64,
            "task_signal_hash": "d" * 64,
        }
        tid = task_id(**kw)
        assert tid == task_id(**kw) and len(tid) == 64
        assert task_id(**{**kw, "L_B": 22}) != tid
        assert task_id(**{**kw, "task_signal_hash": "e" * 64}) != tid
        assert task_id(**{**kw, "real_task_id_salt_hex": "aa" * 32}) != tid


class TestSanitizedDir:
    def test_written_files_and_manifest(self, tmp_path):
        _, grid, chest, cand = _candidate()
        t = build_task(segment_chest_g=chest, segment_grid=grid, candidate=cand,
                       L_A=20, L_B=20)
        tid = "f" * 64
        d = str(tmp_path / tid)
        manifest = write_sanitized_task(d, task=t, task_id_value=tid)
        files = sorted(p.name for p in Path(d).iterdir())
        assert files == [
            "relative_s.f64le", "sample_index.i64le", "signal.f64le", "task_manifest.json"
        ]
        assert manifest["T"] == t["signal"].shape[0]
        # no truth/subject/activity leakage
        text = json.dumps(manifest)
        for forbidden in ("truth", "subject", "activity", "grid"):
            assert forbidden not in text


class TestEligibilityGate:
    def test_gate_pass(self):
        rows = eligibility_rows({f"subject10{i}": 3 for i in range(1, 9)})
        assert len(rows) == 8
        gate = real_data_task_gate(rows)
        assert gate["pass"] is True and gate["total_tasks"] == 24

    def test_gate_fails_too_few_subjects(self):
        rows = eligibility_rows({f"subject10{i}": 10 for i in range(1, 8)})
        assert real_data_task_gate(rows)["pass"] is False

    def test_zero_task_subject_not_admitted(self):
        rows = eligibility_rows({"subject101": 5, "subject102": 0})
        r2 = next(r for r in rows if r["subject_internal_id"] == "subject102")
        assert r2["subject_admitted"] is False
        assert r2["nonadmission_reason"] == "NO_ELIGIBLE_TASK"
