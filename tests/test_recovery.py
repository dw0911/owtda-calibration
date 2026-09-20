"""Tail recovery and run reconciliation (task pack §5.1, §5.2).

The instruction this replaces was "delete the bad line and carry on with the old
seal".  Here a partial trailing event is recovered explicitly: original bytes
preserved read-only, verified prefix rewritten atomically, a dedicated recovery
event, and an explicit statement that the old seal is now stale.
"""

from __future__ import annotations

import json

import pytest

from owtda_cal import chains
from owtda_cal.recovery import (
    RECOVERY_ARTIFACT_NAME,
    RECOVERY_EVENT_TYPE,
    RecoveryError,
    inspect_tail,
    read_recovery_chain,
    reconcile_run,
    repair_incomplete_tail,
)

HASH_FIELD = "shard_commit_hash"


def _chain(path, n: int, *, trailing: bytes = b"") -> list[dict]:
    """Build a schema-2 chain of ``n`` events, optionally cut mid-event."""
    events = []
    tip = None
    for i in range(n):
        payload = {
            "schema_version": 2, "seq": i, "prev_event_hash": tip,
            "event_type": "SHARD_COMMITTED", "shard_id": f"s{i}",
        }
        tip = chains.append_cas(str(path), payload, expected_tip=tip,
                                hash_field=HASH_FIELD)
        events.append({**payload, HASH_FIELD: tip})
    if trailing:
        with open(path, "ab") as fh:
            fh.write(trailing)
    return events


class TestInspect:
    def test_a_complete_chain_is_complete(self, tmp_path):
        path = tmp_path / "reg.jsonl"
        _chain(path, 3)
        assert inspect_tail(path, hash_field=HASH_FIELD)["status"] == "COMPLETE"

    def test_a_partial_trailing_event_is_detected(self, tmp_path):
        path = tmp_path / "reg.jsonl"
        _chain(path, 3, trailing=b'{"schema_version": 2, "seq": 3, "par')
        found = inspect_tail(path, hash_field=HASH_FIELD)
        assert found["status"] == "INCOMPLETE_TAIL"
        assert found["events"] == 3
        assert found["tail"].startswith(b'{"schema_version"')

    def test_a_rewritten_event_with_its_old_hash_is_tampered(self, tmp_path):
        path = tmp_path / "reg.jsonl"
        _chain(path, 2)
        lines = path.read_text(encoding="utf-8").splitlines()
        tampered = json.loads(lines[0])
        tampered["shard_id"] = "rewritten"  # content changed, hash kept
        path.write_text(json.dumps(tampered) + "\n" + lines[1] + "\n", encoding="utf-8")
        found = inspect_tail(path, hash_field=HASH_FIELD)
        assert found["status"] == "TAMPERED"
        assert "does not recompute" in found["detail"]

    def test_a_broken_parent_link_is_detected(self, tmp_path):
        path = tmp_path / "reg.jsonl"
        _chain(path, 2)
        lines = [json.loads(x) for x in path.read_text(encoding="utf-8").splitlines()]
        lines[1]["prev_event_hash"] = "0" * 64
        out = []
        for event in lines:
            body = {k: v for k, v in event.items() if k != HASH_FIELD}
            body[HASH_FIELD] = chains.event_hash(body)
            out.append(json.dumps(body))
        path.write_text("\n".join(out) + "\n", encoding="utf-8")
        assert inspect_tail(path, hash_field=HASH_FIELD)["status"] == "BROKEN_LINK"

    def test_a_non_json_line_is_a_middle_error(self, tmp_path):
        path = tmp_path / "reg.jsonl"
        good = _chain(path, 1)
        path.write_text(json.dumps(good[0]) + "\nnot json\n", encoding="utf-8")
        assert inspect_tail(path, hash_field=HASH_FIELD)["status"] == "MIDDLE_ERROR"


class TestRepair:
    def test_a_partial_tail_is_recovered_with_the_original_preserved(self, tmp_path):
        registry = tmp_path / "reg.jsonl"
        events = _chain(registry, 3, trailing=b'{"schema_version": 2, "seq": 3, "par')
        before = registry.read_bytes()
        recovery_dir = tmp_path / "recovery"
        outcome = repair_incomplete_tail(
            registry_path=registry, recovery_dir=recovery_dir, hash_field=HASH_FIELD,
            log_state="RUN_INTERRUPTED", reason="process killed after a partial append",
        )
        assert outcome["status"] == "REPAIRED"
        assert outcome["events_retained"] == 3
        assert outcome["dropped_bytes"] == len(b'{"schema_version": 2, "seq": 3, "par')
        # the original bytes survive, read-only, and hash to the "before" value
        original = recovery_dir / "reg.jsonl.orig"
        assert original.read_bytes() == before
        assert outcome["before_sha256"] != outcome["after_sha256"]
        # the chain still authenticates and lost nothing
        chains.assert_chain_valid(str(registry), hash_field=HASH_FIELD,
                                  parent_field="prev_event_hash")
        remaining = [json.loads(x) for x in
                     registry.read_text(encoding="utf-8").splitlines() if x.strip()]
        assert [e["shard_id"] for e in remaining] == [e["shard_id"] for e in events]

    def test_the_recovery_is_recorded_on_a_dedicated_chain(self, tmp_path):
        registry = tmp_path / "reg.jsonl"
        _chain(registry, 2, trailing=b"garbage")
        repair_incomplete_tail(
            registry_path=registry, recovery_dir=tmp_path / "recovery",
            hash_field=HASH_FIELD, log_state="TEST", reason="interrupted TEST append",
        )
        recovery_chain = tmp_path / "reg.jsonl.recovery.jsonl"
        records = read_recovery_chain(recovery_chain)
        assert len(records) == 1
        assert records[0]["event_type"] == RECOVERY_EVENT_TYPE
        assert records[0]["seq"] == 0
        assert records[0]["prev_event_hash"] is None
        assert records[0]["dropped_bytes"] == len(b"garbage")
        chains.assert_chain_valid(str(recovery_chain), hash_field="event_hash",
                                  parent_field="prev_event_hash")
        artifact = json.loads((tmp_path / "recovery" / RECOVERY_ARTIFACT_NAME)
                              .read_text(encoding="utf-8"))
        assert artifact["seal_must_be_rederived"] is True

    def test_the_recovery_event_never_enters_the_scientific_chain(self, tmp_path):
        registry = tmp_path / "reg.jsonl"
        _chain(registry, 2, trailing=b"garbage")
        repair_incomplete_tail(
            registry_path=registry, recovery_dir=tmp_path / "recovery",
            hash_field=HASH_FIELD, log_state="TEST", reason="interrupted TEST append",
        )
        assert RECOVERY_EVENT_TYPE not in registry.read_text(encoding="utf-8")

    def test_a_complete_chain_is_left_alone(self, tmp_path):
        registry = tmp_path / "reg.jsonl"
        _chain(registry, 2)
        before = registry.read_bytes()
        outcome = repair_incomplete_tail(
            registry_path=registry, recovery_dir=tmp_path / "recovery",
            hash_field=HASH_FIELD, log_state="TEST", reason="nothing to do",
        )
        assert outcome["repaired"] is False
        assert registry.read_bytes() == before

    def test_a_sealed_chain_is_never_rewritten(self, tmp_path):
        registry = tmp_path / "reg.jsonl"
        _chain(registry, 2, trailing=b"garbage")
        with pytest.raises(RecoveryError, match="SEALED_CHAIN_REFUSED"):
            repair_incomplete_tail(
                registry_path=registry, recovery_dir=tmp_path / "recovery",
                hash_field=HASH_FIELD, log_state="TEST", reason="x", sealed=True,
            )
        assert registry.read_bytes().endswith(b"garbage")

    def test_a_state_that_is_not_interruptible_is_refused(self, tmp_path):
        registry = tmp_path / "reg.jsonl"
        _chain(registry, 2, trailing=b"garbage")
        with pytest.raises(RecoveryError, match="STATE_NOT_REPAIRABLE"):
            repair_incomplete_tail(
                registry_path=registry, recovery_dir=tmp_path / "recovery",
                hash_field=HASH_FIELD, log_state="RUN_SEALED", reason="x",
            )

    def test_a_tampered_middle_is_refused_not_trimmed(self, tmp_path):
        registry = tmp_path / "reg.jsonl"
        _chain(registry, 2, trailing=b"garbage")
        lines = registry.read_text(encoding="utf-8").splitlines()
        tampered = json.loads(lines[0])
        tampered["shard_id"] = "rewritten"
        registry.write_text(json.dumps(tampered) + "\n" + lines[1] + "\n" + "garbage",
                            encoding="utf-8")
        with pytest.raises(RecoveryError, match="TAMPERED_REFUSED"):
            repair_incomplete_tail(
                registry_path=registry, recovery_dir=tmp_path / "recovery",
                hash_field=HASH_FIELD, log_state="RUN_INTERRUPTED", reason="x",
            )
        assert "rewritten" in registry.read_text(encoding="utf-8")

    def test_a_reason_is_required(self, tmp_path):
        registry = tmp_path / "reg.jsonl"
        _chain(registry, 1, trailing=b"x")
        with pytest.raises(RecoveryError, match="reason is required"):
            repair_incomplete_tail(
                registry_path=registry, recovery_dir=tmp_path / "recovery",
                hash_field=HASH_FIELD, log_state="TEST", reason="",
            )


class TestReconcile:
    def _commit(self, tmp_path, shard: str, evaluation_ids: list[str]) -> None:
        from owtda_cal import shardio

        run_root = str(tmp_path / "runs")
        registry = str(tmp_path / "shard_registry.jsonl")
        evaluation_lines = [
            (json.dumps({"evaluation_id": e}, sort_keys=True) + "\n").encode()
            for e in evaluation_ids
        ]
        shardio.commit_shard(
            run_root=run_root, run_instance_id="R1", shard_id=shard,
            shard_plan_hash="p" * 64, evaluation_lines=evaluation_lines,
            feature_lines=[b'{"f":1}\n'], evaluation_meta={}, feature_meta={},
            registry_path=registry,
        )
        return run_root, registry

    def test_a_reconciled_run_reports_its_committed_ids(self, tmp_path):
        run_root, registry = self._commit(tmp_path, "s0", ["e1", "e2"])
        report = reconcile_run(run_root=run_root, run_instance_id="R1",
                               registry_path=registry)
        assert report["reconciled"] is True
        assert report["committed_evaluation_ids"] == ["e1", "e2"]
        assert report["duplicate_evaluation_ids"] == []
        assert report["orphans_requiring_strict_repair"] == []
        assert report["lost_commits"] == []

    def test_an_orphan_directory_is_reported_not_auto_committed(self, tmp_path):
        run_root, registry = self._commit(tmp_path, "s0", ["e1"])
        orphan = tmp_path / "runs" / "R1" / "s9.final"
        orphan.mkdir(parents=True)
        report = reconcile_run(run_root=run_root, run_instance_id="R1",
                               registry_path=registry)
        assert report["orphans_requiring_strict_repair"] == ["s9"]
        assert report["reconciled"] is False

    def test_a_lost_commit_is_reported_not_re_appended(self, tmp_path):
        import shutil

        run_root, registry = self._commit(tmp_path, "s0", ["e1"])
        shutil.rmtree(tmp_path / "runs" / "R1" / "s0.final")
        report = reconcile_run(run_root=run_root, run_instance_id="R1",
                               registry_path=registry)
        assert [x["shard_id"] for x in report["lost_commits"]] == ["s0"]
        assert report["lost_commits"][0]["status"] == "COMMITTED_CONTENT_LOST"
        # no second commit was appended
        records = [x for x in (tmp_path / "shard_registry.jsonl")
                   .read_text(encoding="utf-8").splitlines() if x.strip()]
        assert len(records) == 1

    def test_duplicate_evaluation_ids_are_named(self, tmp_path):
        run_root, registry = self._commit(tmp_path, "s0", ["e1", "e1"])
        report = reconcile_run(run_root=run_root, run_instance_id="R1",
                               registry_path=registry)
        assert report["duplicate_evaluation_ids"] == ["e1"]
        assert report["reconciled"] is False
