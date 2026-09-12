"""Tests for shard staging/commit, orphan repair and attempts (Plan §15.4)."""

import hashlib
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

    def test_identical_recommit_is_idempotent(self, tmp_path):
        """Audit A04: idempotency is 'the same request twice, one effect'.

        The previous version of this test passed *different* bytes and still
        asserted the old record was returned, which is how the defect became a
        green test.  That assertion is now inverted.
        """
        _run_root, registry, rec = _commit(tmp_path)
        again = _commit(tmp_path)[2]
        assert again == rec  # identical request -> committed record returned
        lines = [x for x in Path(registry).read_text(encoding="utf-8").splitlines() if x.strip()]
        assert len(lines) == 1

    def test_conflicting_content_is_blocked(self, tmp_path):
        """Same identity, different bytes -> block, never accept silently."""
        _run_root, registry, _rec = _commit(tmp_path)
        with pytest.raises(ShardError):
            _commit(tmp_path, eval_lines=[b'{"value":2}\n'])
        with pytest.raises(ShardError):
            _commit(tmp_path, feature_lines=[b'{"f":2}\n'])
        lines = [x for x in Path(registry).read_text(encoding="utf-8").splitlines() if x.strip()]
        assert len(lines) == 1  # nothing was appended

    def test_plan_hash_conflict_is_blocked(self, tmp_path):
        _run_root, _registry, _rec = _commit(tmp_path)
        with pytest.raises(ShardError):
            _commit(tmp_path, plan=_H("q"))

    def test_metadata_conflict_is_blocked(self, tmp_path):
        _run_root, registry, _rec = _commit(tmp_path)
        with pytest.raises(ShardError):
            commit_shard(
                run_root=str(tmp_path / "runs"), run_instance_id=_H("r"),
                shard_id=_H("1"), shard_plan_hash=_H("p"),
                evaluation_lines=[b'{"row":1}\n'], feature_lines=[b'{"f":1}\n'],
                evaluation_meta={"row_count": 2}, feature_meta={"row_count": 1},
                registry_path=registry,
            )

    def test_tampered_committed_file_is_blocked(self, tmp_path):
        """The A04 probe: rewrite the committed file, re-commit, still blocked."""
        run_root, _registry, _rec = _commit(tmp_path)
        final = Path(run_root, _H("r"), f"{_H('1')}.final")
        Path(final, "evaluation.scientific.jsonl").write_bytes(b'{"value":999}\n')
        with pytest.raises(ShardError):
            _commit(tmp_path)

    def test_tampered_manifest_is_blocked(self, tmp_path):
        run_root, _registry, _rec = _commit(tmp_path)
        final = Path(run_root, _H("r"), f"{_H('1')}.final")
        Path(final, "shard_manifest.json").write_bytes(b'{"tampered":true}\n')
        with pytest.raises(ShardError):
            _commit(tmp_path)

    def test_missing_committed_file_is_blocked(self, tmp_path):
        """Missing committed directory content must not read as 'already done'."""
        run_root, _registry, _rec = _commit(tmp_path)
        final = Path(run_root, _H("r"), f"{_H('1')}.final")
        os.remove(final / "shard_manifest.json")
        with pytest.raises(ShardError):
            _commit(tmp_path)
        missing_dir = Path(run_root, _H("r"), f"{_H('1')}.final")
        for name in ("evaluation.scientific.jsonl", "feature.scientific.jsonl"):
            os.remove(missing_dir / name)
        with pytest.raises(ShardError):
            _commit(tmp_path)

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
    def _make_orphan(self, tmp_path, *, corrupt=False, run_id=None, shard_id=None,
                     plan=None, zero_hashes=False, manifest_overrides=None):
        """A .final directory with no commit (the ORPHAN_FINAL precondition).

        Re-audit 2026-09-13: the previous fixture declared all-zero payload
        hashes and repair still accepted it.  The manifest now carries the real
        hashes of the bytes it describes, and ``zero_hashes`` reproduces the old
        defect so it can be asserted against.
        """
        run_root = str(tmp_path / "runs")
        registry = str(tmp_path / "shard_registry.jsonl")
        rid = run_id or _H("r")
        sid = shard_id or _H("2")
        plan_hash = plan or _H("p")
        final = os.path.join(run_root, rid, f"{sid}.final")
        os.makedirs(final)
        eval_bytes = b'{"row":1}\n'
        feat_bytes = b'{"f":1}\n'
        if zero_hashes:
            eval_decl = feature_decl = "0" * 64
        else:
            eval_decl = hashlib.sha256(eval_bytes).hexdigest()
            feature_decl = hashlib.sha256(feat_bytes).hexdigest()
        manifest = {
            "schema_version": 1, "run_instance_id": rid, "shard_id": sid,
            "shard_plan_hash": plan_hash,
            "evaluation": {"scientific_hash": eval_decl},
            "feature": {"scientific_hash": feature_decl},
        }
        if manifest_overrides:
            manifest.update(manifest_overrides)
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
                expected_shard_plan_hash=_H("p"),
            )


class TestOrphanRepairStrictness:
    """Re-audit 2026-09-13: the four defects the probes reproduced."""

    def _repair(self, tmp_path, *, tag="x", **orphan_kw):
        from owtda_cal.shardio import repair_orphan

        run_root, registry, ev, ft, mf = TestOrphan()._make_orphan(tmp_path, **orphan_kw)
        return repair_orphan, {
            "run_root": run_root, "registry_path": registry,
            "recompute_to": str(tmp_path / f"recompute_{tag}"),
            "expected_manifest_bytes": mf, "expected_evaluation_bytes": ev,
            "expected_feature_bytes": ft, "expected_shard_plan_hash": _H("p"),
        }, registry

    def test_repair_of_an_already_committed_shard_is_refused(self, tmp_path):
        """The old code appended a second commit for a committed shard."""
        from owtda_cal.shardio import commit_shard, repair_orphan

        run_root = str(tmp_path / "runs")
        registry = str(tmp_path / "shard_registry.jsonl")
        commit_shard(
            run_root=run_root, run_instance_id=_H("r"), shard_id=_H("1"),
            shard_plan_hash=_H("p"), evaluation_lines=[b'{"row":1}\n'],
            feature_lines=[b'{"f":1}\n'], evaluation_meta={}, feature_meta={},
            registry_path=registry,
        )
        before = len([x for x in Path(registry).read_text(encoding="utf-8").splitlines() if x.strip()])
        with pytest.raises(ShardError, match="NOT_AN_ORPHAN"):
            repair_orphan(
                run_root=run_root, run_instance_id=_H("r"), shard_id=_H("1"),
                registry_path=registry, recompute_to=str(tmp_path / "rec"),
                expected_manifest_bytes=b"{}", expected_evaluation_bytes=b"",
                expected_feature_bytes=b"", expected_shard_plan_hash=_H("p"),
            )
        after = len([x for x in Path(registry).read_text(encoding="utf-8").splitlines() if x.strip()])
        assert before == after == 1

    def test_second_repair_does_not_duplicate_the_commit(self, tmp_path):
        repair_orphan, kw, registry = self._repair(tmp_path, tag="once")
        repair_orphan(run_instance_id=_H("r"), shard_id=_H("2"), **kw)
        with pytest.raises(ShardError, match="NOT_AN_ORPHAN"):
            repair_orphan(run_instance_id=_H("r"), shard_id=_H("2"), **kw)
        lines = [x for x in Path(registry).read_text(encoding="utf-8").splitlines() if x.strip()]
        assert len(lines) == 1

    def test_wrong_run_identity_is_attributable(self, tmp_path):
        """The manifest declares a different run than the path it sits under."""
        repair_orphan, kw, _registry = self._repair(
            tmp_path, tag="runid", manifest_overrides={"run_instance_id": _H("other")}
        )
        with pytest.raises(ShardError, match="ORPHAN_IDENTITY_MISMATCH"):
            repair_orphan(run_instance_id=_H("r"), shard_id=_H("2"), **kw)

    def test_wrong_shard_identity_is_attributable(self, tmp_path):
        repair_orphan, kw, _registry = self._repair(
            tmp_path, tag="shardid", manifest_overrides={"shard_id": _H("other")}
        )
        with pytest.raises(ShardError, match="ORPHAN_IDENTITY_MISMATCH"):
            repair_orphan(run_instance_id=_H("r"), shard_id=_H("2"), **kw)

    def test_wrong_plan_hash_is_attributable(self, tmp_path):
        repair_orphan, kw, _registry = self._repair(tmp_path, tag="plan")
        kw = dict(kw, expected_shard_plan_hash=_H("q"))
        with pytest.raises(ShardError, match="ORPHAN_PLAN_MISMATCH"):
            repair_orphan(run_instance_id=_H("r"), shard_id=_H("2"), **kw)

    def test_all_zero_payload_hashes_are_refused(self, tmp_path):
        """The exact probe: 0x00*32 declarations used to be accepted."""
        repair_orphan, kw, registry = self._repair(tmp_path, tag="zero", zero_hashes=True)
        with pytest.raises(ShardError, match="MANIFEST_PAYLOAD_HASH_INVALID"):
            repair_orphan(run_instance_id=_H("r"), shard_id=_H("2"), **kw)
        assert not Path(registry).exists() or not [
            x for x in Path(registry).read_text(encoding="utf-8").splitlines() if x.strip()
        ]

    def test_declared_hash_that_does_not_match_the_bytes_is_refused(self, tmp_path):
        # the committed manifest declares a hash the actual bytes do not have
        repair_orphan, kw, _registry = self._repair(
            tmp_path, tag="lies",
            manifest_overrides={"evaluation": {"scientific_hash":
                                               hashlib.sha256(b"other").hexdigest()}},
        )
        with pytest.raises(ShardError, match="MANIFEST_PAYLOAD_HASH_MISMATCH"):
            repair_orphan(run_instance_id=_H("r"), shard_id=_H("2"), **kw)


class TestSchemaTwoParentChain:
    """New shard/attempt events carry their predecessor (task pack §2.2)."""

    def test_commit_event_is_schema_two_and_linked(self, tmp_path):
        from owtda_cal.shardio import EVENT_SCHEMA_VERSION

        _run_root, registry, rec = _commit(tmp_path)
        assert rec["schema_version"] == EVENT_SCHEMA_VERSION
        assert rec["seq"] == 0
        assert rec["prev_event_hash"] is None
        _commit(tmp_path, shard="2")
        lines = [json.loads(x) for x in Path(registry).read_text(encoding="utf-8").splitlines() if x.strip()]
        assert [x["seq"] for x in lines] == [0, 1]
        assert lines[1]["prev_event_hash"] == lines[0]["shard_commit_hash"]

    def test_attempt_events_form_a_chain(self, tmp_path):
        registry = str(tmp_path / "attempts.jsonl")
        allocate_attempt(registry, run_instance_id=_H("r"), evaluation_id=_H("e"))
        allocate_attempt(registry, run_instance_id=_H("r"), evaluation_id=_H("e"))
        lines = [json.loads(x) for x in Path(registry).read_text(encoding="utf-8").splitlines() if x.strip()]
        assert [x["attempt_number"] for x in lines] == [1, 2]
        assert lines[1]["prev_event_hash"] == lines[0]["attempt_id"]

    def test_registry_authenticates_end_to_end(self, tmp_path):
        from owtda_cal.chains import verify_chain

        _run_root, registry, _rec = _commit(tmp_path)
        _commit(tmp_path, shard="2")
        assert verify_chain(registry, hash_field="shard_commit_hash",
                            parent_field="prev_event_hash") == []


class TestAttempts:
    def test_monotonic_allocation(self, tmp_path):
        registry = str(tmp_path / "attempts.jsonl")
        assert allocate_attempt(registry, run_instance_id=_H("r"), evaluation_id=_H("e")) == 1
        assert allocate_attempt(registry, run_instance_id=_H("r"), evaluation_id=_H("e")) == 2
        assert allocate_attempt(registry, run_instance_id=_H("r"), evaluation_id=_H("f")) == 1
        lines = [json.loads(x) for x in Path(registry).read_text(encoding="utf-8").splitlines() if x.strip()]
        assert [x["attempt_number"] for x in lines] == [1, 2, 1]
