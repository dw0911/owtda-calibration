"""Re-audit 2026-09-17 (R5-05): the formal pipeline commits real shards.

These tests pin that produced formal rows turn into the three expected-index
sets (data/feature/evaluation, unique + consistent) and that a batch commits as
a real shard (three files, idempotent on identical bytes, blocking on conflict).
The calibrators are stubbed so the tests are fast; they exercise the *pipeline*,
not the resampler.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]

import sys

sys.path.insert(0, str(REPO / "src"))

from owtda_cal import (
    formal,
    formal_pipeline,
    formal_rows,
    indexes,
    scope,
    shardio,
)


@pytest.fixture()
def _fast_calibrate(monkeypatch):
    def stub(*args, **kwargs):
        return {"M": 0, "B": 999, "observed_statistic": 0.0,
                "exceed_count": 0, "p_value": 0.5, "reject": False}

    monkeypatch.setattr(formal, "calibrate_m0", stub)
    monkeypatch.setattr(formal, "calibrate_m1", stub)


def _manifest():
    return json.loads((REPO / "governance" / "FREEZE_MANIFEST.json").read_text(encoding="utf-8"))


def _seeds():
    return json.loads((REPO / "governance" / "SEED_REGISTRY_v1.0.json").read_text(encoding="utf-8"))


def _produce():
    manifest = _manifest()
    ctx = formal.formal_context(manifest, "NULL")
    run_identity = {
        "compute_git_commit": "HEAD",
        "run_config_manifest_hash": "r" * 64, "registry_snapshot_hash": "r" * 64,
        "run_component_set_hash": "r" * 64, "run_instance_id": "RUN-1",
        "shard_plan_hash": "r" * 64, "expected_index_hash": "r" * 64,
        "expected_feature_index_hash": "r" * 64, "feature_registry_entry_hash": "r" * 64,
        "method_registry_entry_hash": "r" * 64, "data_registry_entry_hash": "r" * 64,
        "data_root_entry_hash": "r" * 64, "resampling_root_entry_hash": "r" * 64,
    }
    payload = {
        "family": scope.H0_FAMILIES[0],
        "rho": scope.RHO_LEVELS[0],
        "replicate": 1,
        "feature_id": scope.FEATURE_IDS[0],
        "ctx": ctx,
        "root_keys": formal.formal_root_keys(_seeds(), "NULL"),
        "run_identity": run_identity,
    }
    return formal.process_formal_master_feature(payload)


def _schemas():
    feature_id = scope.FEATURE_IDS[0]
    family = "N_AR"
    scenario = "h0"
    return {
        (family, scenario, feature_id, mid): formal_rows.load_row_schema(
            phase="NULL", DGP_family=family, scenario_id=scenario,
            feature_id=feature_id, method_id=mid,
        )
        for mid in ("M0_NAIVE_PERM_B999_V1", "M1_DMB_R1_TRI_EXTIID_B999_V1")
    }, formal_rows.load_feature_schema()


def test_build_expected_indexes_are_unique_and_consistent(_fast_calibrate):
    part = _produce()
    idx = formal_pipeline.build_expected_indexes(part["rows"], part["feature_rows"])
    # 7 cells -> 7 data units; 7 feature-sufficient; 14 evaluations (7 x 2 methods)
    assert len(idx["data_rows"]) == 7
    assert len(idx["feature_rows"]) == 7
    assert len(idx["evaluation_rows"]) == 14
    for h in ("expected_data_index_hash", "expected_index_hash", "expected_feature_index_hash"):
        assert len(idx[h]) == 64


def test_commit_formal_shard_is_idempotent(tmp_path, _fast_calibrate):
    part = _produce()
    idx = formal_pipeline.build_expected_indexes(part["rows"], part["feature_rows"])
    run_root = str(tmp_path / "run")
    registry = str(tmp_path / "registry.jsonl")
    run_instance_id = "RUN-1"
    phase = "NULL"
    plan = formal_pipeline.build_single_shard_plan(
        run_instance_id=run_instance_id, phase=phase,
        expected_data_index_hash=idx["expected_data_index_hash"],
        expected_index_hash=idx["expected_index_hash"],
        expected_feature_index_hash=idx["expected_feature_index_hash"],
        rows=part["rows"], feature_rows=part["feature_rows"],
        partition="r1",
    )
    shard_plan_hash = indexes.shard_plan_hash(plan)
    sid = plan["entries"][0]["shard_id"]
    schemas, feature_schema = _schemas()

    rec = formal_pipeline.commit_formal_shard(
        run_root=run_root, run_instance_id=run_instance_id, shard_id=sid,
        shard_plan_hash=shard_plan_hash, rows=part["rows"],
        feature_rows=part["feature_rows"], registry_path=registry,
        schemas=schemas, feature_schema=feature_schema,
    )
    assert rec["event_type"] == "SHARD_COMMITTED"
    final_dir = Path(run_root) / run_instance_id / f"{sid}.final"
    for name in shardio.COMMITTED_FILES:
        assert (final_dir / name).is_file()
    # idempotent: the same request re-commits with no conflict
    rec2 = formal_pipeline.commit_formal_shard(
        run_root=run_root, run_instance_id=run_instance_id, shard_id=sid,
        shard_plan_hash=shard_plan_hash, rows=part["rows"],
        feature_rows=part["feature_rows"], registry_path=registry,
        schemas=schemas, feature_schema=feature_schema,
    )
    assert rec2["shard_commit_hash"] == rec["shard_commit_hash"]


def test_commit_formal_shard_blocks_on_conflict(tmp_path, _fast_calibrate):
    part = _produce()
    idx = formal_pipeline.build_expected_indexes(part["rows"], part["feature_rows"])
    run_root = str(tmp_path / "run")
    registry = str(tmp_path / "registry.jsonl")
    plan = formal_pipeline.build_single_shard_plan(
        run_instance_id="RUN-1", phase="NULL",
        expected_data_index_hash=idx["expected_data_index_hash"],
        expected_index_hash=idx["expected_index_hash"],
        expected_feature_index_hash=idx["expected_feature_index_hash"],
        rows=part["rows"], feature_rows=part["feature_rows"], partition="r1",
    )
    sid = plan["entries"][0]["shard_id"]
    shard_plan_hash = indexes.shard_plan_hash(plan)
    schemas, feature_schema = _schemas()
    formal_pipeline.commit_formal_shard(
        run_root=run_root, run_instance_id="RUN-1", shard_id=sid,
        shard_plan_hash=shard_plan_hash, rows=part["rows"],
        feature_rows=part["feature_rows"], registry_path=registry,
        schemas=schemas, feature_schema=feature_schema,
    )
    # a conflicting batch (different rows) under the same shard id must block
    changed = [dict(part["rows"][0])]
    changed[0]["observed_statistic"] = 99.9
    with pytest.raises(shardio.ShardError):
        formal_pipeline.commit_formal_shard(
            run_root=run_root, run_instance_id="RUN-1", shard_id=sid,
            shard_plan_hash=shard_plan_hash, rows=changed,
            feature_rows=part["feature_rows"], registry_path=registry,
            schemas=schemas, feature_schema=feature_schema,
        )


def test_build_formal_run_seal(tmp_path, _fast_calibrate):
    part = _produce()
    idx = formal_pipeline.build_expected_indexes(part["rows"], part["feature_rows"])
    schemas, feature_schema = _schemas()
    run_root = str(tmp_path / "run")
    registry = str(tmp_path / "registry.jsonl")
    plan = formal_pipeline.build_single_shard_plan(
        run_instance_id="RUN-1", phase="NULL",
        expected_data_index_hash=idx["expected_data_index_hash"],
        expected_index_hash=idx["expected_index_hash"],
        expected_feature_index_hash=idx["expected_feature_index_hash"],
        rows=part["rows"], feature_rows=part["feature_rows"], partition="r1",
    )
    sid = plan["entries"][0]["shard_id"]
    shard_plan_hash = indexes.shard_plan_hash(plan)
    rec = formal_pipeline.commit_formal_shard(
        run_root=run_root, run_instance_id="RUN-1", shard_id=sid,
        shard_plan_hash=shard_plan_hash, rows=part["rows"],
        feature_rows=part["feature_rows"], registry_path=registry,
        schemas=schemas, feature_schema=feature_schema,
    )
    seal = formal_pipeline.build_formal_run_seal(
        run_instance_id="RUN-1",
        run_component_set_hash="c" * 64,
        expected_data_index_hash=idx["expected_data_index_hash"],
        expected_index_hash=idx["expected_index_hash"],
        expected_feature_index_hash=idx["expected_feature_index_hash"],
        shard_plan_hash=shard_plan_hash,
        commit_records=[rec],
        rows=part["rows"], feature_rows=part["feature_rows"],
        schemas=schemas, feature_schema=feature_schema,
    )
    assert seal["row_count"] == 14
    assert seal["produced_data_unit_count"] == 7
    assert seal["feature_row_count"] == 7
    assert len(seal["ordered_shard_commit_refs"]) == 1
    # the seal hashes over real content
    assert len(indexes.run_seal_hash(seal)) == 64


def test_run_seal_is_empty_when_no_feature_rows(tmp_path, _fast_calibrate):
    part = _produce()
    idx = formal_pipeline.build_expected_indexes(part["rows"], part["feature_rows"])
    schemas, feature_schema = _schemas()
    # no feature rows -> feature_empty_by_contract must be True and count zero
    seal = formal_pipeline.build_formal_run_seal(
        run_instance_id="RUN-1", run_component_set_hash="c" * 64,
        expected_data_index_hash=idx["expected_data_index_hash"],
        expected_index_hash=idx["expected_index_hash"],
        expected_feature_index_hash=idx["expected_feature_index_hash"],
        shard_plan_hash="a" * 64, commit_records=[],
        rows=part["rows"], feature_rows=[],
        schemas=schemas, feature_schema=feature_schema,
    )
    assert seal["feature_empty_by_contract"] is True
    assert seal["feature_row_count"] == 0


def test_build_formal_phase_seal(tmp_path, _fast_calibrate):
    from owtda_cal import identity

    part = _produce()
    idx = formal_pipeline.build_expected_indexes(part["rows"], part["feature_rows"])
    schemas, feature_schema = _schemas()
    run_seal = formal_pipeline.build_formal_run_seal(
        run_instance_id="RUN-1", run_component_set_hash="c" * 64,
        expected_data_index_hash=idx["expected_data_index_hash"],
        expected_index_hash=idx["expected_index_hash"],
        expected_feature_index_hash=idx["expected_feature_index_hash"],
        shard_plan_hash="a" * 64, commit_records=[],
        rows=part["rows"], feature_rows=part["feature_rows"],
        schemas=schemas, feature_schema=feature_schema,
    )
    run_seal_hash = indexes.run_seal_hash(run_seal)
    scope_design_hash = identity.H("scope_design", phase="NULL", rows=[])
    phase_seal = formal_pipeline.build_formal_phase_seal(
        phase="NULL", evidence_generation_id="G01",
        scope_design_hash=scope_design_hash,
        run_seal=run_seal, run_seal_hash=run_seal_hash,
        validity_registry_head_hash="0" * 64,
    )
    assert phase_seal["active_ledger_content_hash"] == run_seal["ledger_content_hash"]
    assert phase_seal["active_evaluation_index_hash"] == run_seal["expected_index_hash"]
    assert phase_seal["active_feature_row_count"] == 7
    assert phase_seal["ordered_source_run_seal_hashes"] == [run_seal_hash]
    assert phase_seal["parent_phase_seal_hash"] is None
    assert phase_seal["replacement_source_run_seal_hashes"] == []
    assert len(indexes.phase_seal_hash(phase_seal)) == 64
