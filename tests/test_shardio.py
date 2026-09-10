"""Tests for shard staging/commit, orphan repair and attempts (Plan §15.4)."""

import json
import os
from pathlib import Path

import pytest

from owtda_cal.shardio import (
    ShardError,
    allocate_attempt,
    commit_shard,
    find_commit,
)

_H = lambda ch: ch * 8


def _commit(tmp_path, *, shard="1", eval_lines=None, feature_lines=None, plan=None):
    plan = plan or _H("p")
    run_root = str(tmp_path / "runs")
    registry = str(tmp_path / "shard_registry.jsonl")
    rec = commit_shard(
        run_root=run_root,
        run_instance_id=_H("r"),
        shard_id=_H(shard),
        shard_plan_hash=plan,
        evaluation_lines=eval_lines or [b'{"row":1}\n'],
        feature_lines=feature_lines or [b'{"f":1}\n'],
        evaluation_meta={"row_count": 1},
        feature_meta={"row_count": 1},
        registry_path=registry,
    )
    return run_root, registry, rec


class TestCommit:
    def test_first_commit(self, tmp_path):
        run_root, _registry, rec = _commit(tmp_path)
        assert rec["event_type"] == "SHARD_COMMITTED"
        assert len(rec["shard_commit_hash"]) == 64
        final = os.path.join(run_root, _H("r"), f"{_H('1')}.final")
        assert os.path.isdir(final)
        assert sorted(os.listdir(final)) == [
            "evaluation.scientific.jsonl", "feature.scientific.jsonl", "shard_manifest.json"
        ]
        manifest = json.loads(Path(final, "shard_manifest.json").read_text(encoding="utf-8"))
        assert manifest["evaluation"]["scientific_hash"]
        assert manifest["feature"]["row_count"] == 1

    def test_idempotent_recommit(self, tmp_path):
        run_root, registry, rec = _commit(tmp_path)
        again = commit_shard(
            run_root=run_root, run_instance_id=_H("r"), shard_id=_H("1"),
            shard_plan_hash=_H("p"), evaluation_lines=[b"different\n"],
            feature_lines=[b"different\n"], evaluation_meta={}, feature_meta={},
            registry_path=registry,
        )
        assert again == rec  # existing commit returned unchanged
        lines = [x for x in Path(registry).read_text(encoding="utf-8").splitlines() if x.strip()]
        assert len(lines) == 1

    def test_conflicting_commit_records_block(self, tmp_path):
        _run_root, registry, rec = _commit(tmp_path)
        # manually append a conflicting record for the same shard
        conflicting = dict(rec, shard_manifest_hash=_H("x"))
        conflicting["shard_commit_hash"] = _H("y")
        with open(registry, "a", encoding="utf-8") as fh:
            fh.write(json.dumps(conflicting) + "\n")
        with pytest.raises(ShardError):
            find_commit(registry, run_instance_id=_H("r"), shard_id=_H("1"))


class TestOrphan:
    def _make_orphan(self, tmp_path, *, corrupt=False):
        run_root = str(tmp_path / "runs")
        registry = str(tmp_path / "shard_registry.jsonl")
        final = os.path.join(run_root, _H("r"), f"{_H('2')}.final")
        os.makedirs(final)
        eval_bytes = b'{"row":1}\n'
        feat_bytes = b'{"f":1}\n'
        manifest = {
            "schema_version": 1, "run_instance_id": _H("r"), "shard_id": _H("2"),
            "shard_plan_hash": _H("p"),
            "evaluation": {"scientific_hash": "0" * 64},
            "feature": {"scientific_hash": "0" * 64},
        }
        from owtda_cal.canonical import canonical_json_bytes

        manifest_bytes = canonical_json_bytes(manifest) + b"\n"
        if corrupt:
            manifest_bytes = manifest_bytes.replace(b'"schema_version":1', b'"schema_version":2')
        Path(final, "evaluation.scientific.jsonl").write_bytes(eval_bytes)
        Path(final, "feature.scientific.jsonl").write_bytes(feat_bytes)
        Path(final, "shard_manifest.json").write_bytes(manifest_bytes)
        return run_root, registry, eval_bytes, feat_bytes, manifest_bytes

    def test_commit_on_orphan_blocks(self, tmp_path):
        run_root, registry, *_ = self._make_orphan(tmp_path)
        with pytest.raises(ShardError):
            commit_shard(
                run_root=run_root, run_instance_id=_H("r"), shard_id=_H("2"),
                shard_plan_hash=_H("p"), evaluation_lines=[b"x\n"], feature_lines=[b"x\n"],
                evaluation_meta={}, feature_meta={}, registry_path=registry,
            )

    def test_repair_orphan_equal_appends_commit(self, tmp_path):
        from owtda_cal.shardio import repair_orphan

        run_root, registry, ev, ft, mf = self._make_orphan(tmp_path)
        rec = repair_orphan(
            run_root=run_root, run_instance_id=_H("r"), shard_id=_H("2"),
            registry_path=registry, recompute_to=str(tmp_path / "recompute"),
            expected_manifest_bytes=mf, expected_evaluation_bytes=ev,
            expected_feature_bytes=ft,
        )
        assert rec["event_type"] == "SHARD_COMMITTED"
        assert find_commit(registry, run_instance_id=_H("r"), shard_id=_H("2"))

    def test_repair_orphan_mismatch_blocks(self, tmp_path):
        from owtda_cal.shardio import repair_orphan

        run_root, registry, ev, ft, mf = self._make_orphan(tmp_path, corrupt=True)
        with pytest.raises(ShardError):
            repair_orphan(
                run_root=run_root, run_instance_id=_H("r"), shard_id=_H("2"),
                registry_path=registry, recompute_to=str(tmp_path / "recompute2"),
                expected_manifest_bytes=mf.replace(b'"schema_version":2', b'"schema_version":1'),
                expected_evaluation_bytes=ev, expected_feature_bytes=ft,
            )


class TestAttempts:
    def test_monotonic_allocation(self, tmp_path):
        registry = str(tmp_path / "attempts.jsonl")
        assert allocate_attempt(registry, run_instance_id=_H("r"), evaluation_id=_H("e")) == 1
        assert allocate_attempt(registry, run_instance_id=_H("r"), evaluation_id=_H("e")) == 2
        assert allocate_attempt(registry, run_instance_id=_H("r"), evaluation_id=_H("f")) == 1
        lines = [json.loads(x) for x in Path(registry).read_text(encoding="utf-8").splitlines() if x.strip()]
        assert [x["attempt_number"] for x in lines] == [1, 2, 1]
