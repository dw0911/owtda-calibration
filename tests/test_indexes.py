"""Tests for expected indexes / shard plan / seal payloads (Plan §15.4, §16.2)."""

import pytest

from owtda_cal import indexes as ix

_H = lambda ch: ch * 64


def _data_rows(n=3):
    return [
        {"logical_data_key": _H(str(i)), "data_unit_id": _H(str(i + 5))}
        for i in range(n)
    ]


def _feature_rows(n=3):
    return [
        {
            "logical_data_key": _H(str(i)),
            "logical_feature_key": _H(str(i + 3)),
            "data_unit_id": _H(str(i + 5)),
            "feature_sufficient_id": _H(str(i + 7)),
        }
        for i in range(n)
    ]


class TestExpectedIndexes:
    def test_sorted_and_unique(self):
        rows = ix.expected_data_index_rows(list(reversed(_data_rows())))
        assert [r["logical_data_key"] for r in rows] == sorted(r["logical_data_key"] for r in rows)
        with pytest.raises(ValueError):
            ix.expected_data_index_rows(_data_rows() + _data_rows()[:1])

    def test_bad_keys_rejected(self):
        with pytest.raises(ValueError):
            ix.expected_data_index_rows([{"logical_data_key": "zz", "data_unit_id": _H("a")}])
        with pytest.raises(ValueError):
            ix.expected_feature_index_rows([{"logical_data_key": _H("1")}])

    def test_content_hash_deterministic(self):
        rows = ix.expected_data_index_rows(_data_rows())
        h1 = ix.index_content_hash(rows)
        h2 = ix.index_content_hash(ix.expected_data_index_rows(_data_rows()))
        assert h1 == h2 and len(h1) == 64

    def test_consistency_check(self):
        d = ix.expected_data_index_rows(_data_rows())
        f = ix.expected_feature_index_rows(_feature_rows())
        e = ix.expected_evaluation_index_rows([
            {
                "logical_data_key": r["logical_data_key"],
                "logical_feature_key": r["logical_feature_key"],
                "logical_evaluation_key": _H(f"{i + 2:x}"),
                "data_unit_id": r["data_unit_id"],
                "feature_sufficient_id": r["feature_sufficient_id"],
                "evaluation_id": _H(f"{i + 9:x}"),
            }
            for i, r in enumerate(f)
        ])
        ix.validate_index_consistency(d, f, e)
        bad = [dict(e[0], data_unit_id=_H("9"))]
        with pytest.raises(ValueError):
            ix.validate_index_consistency(d, f, bad)


class TestShardPlan:
    def test_plan_sorted_and_hashed(self):
        plan = ix.build_shard_plan(
            run_instance_id=_H("1"), phase="NULL",
            expected_data_index_hash=_H("a"), expected_index_hash=_H("b"),
            expected_feature_index_hash=_H("c"),
            entries=[
                {"row_type": ix.ROW_TYPE_FEATURE, "row_id": _H("2"), "partition": "N_AR", "bucket": 0},
                {"row_type": ix.ROW_TYPE_EVALUATION, "row_id": _H("1"), "partition": "N_AR", "bucket": 0},
            ],
        )
        keys = [(e["row_type"], e["row_id"]) for e in plan["entries"]]
        assert keys == sorted(keys)
        assert plan["entries"][0]["shard_id"] == ix.shard_id(
            run_instance_id=_H("1"), phase="NULL", partition="N_AR", bucket=0
        )
        assert len(ix.shard_plan_hash(plan)) == 64

    def test_duplicate_row_rejected(self):
        entry = {"row_type": ix.ROW_TYPE_EVALUATION, "row_id": _H("1"), "partition": "N_AR", "bucket": 0}
        with pytest.raises(ValueError):
            ix.build_shard_plan(
                run_instance_id=_H("1"), phase="NULL",
                expected_data_index_hash=_H("a"), expected_index_hash=_H("b"),
                expected_feature_index_hash=_H("c"), entries=[entry, dict(entry)],
            )

    def test_bad_row_type_rejected(self):
        with pytest.raises(ValueError):
            ix.build_shard_plan(
                run_instance_id=_H("1"), phase="NULL",
                expected_data_index_hash=_H("a"), expected_index_hash=_H("b"),
                expected_feature_index_hash=_H("c"),
                entries=[{"row_type": "OTHER", "row_id": _H("1"), "partition": "p", "bucket": 0}],
            )


class TestRunComponentSet:
    def _rcs(self, phase="NULL"):
        return {
            "schema_version": 1,
            "project_id": "owtda-cal-r1", "protocol_id": "p",
            "freeze_id": _H("f"), "evidence_generation_id": "G01",
            "phase": phase, "scope_design_hash": _H("a"),
            "parent_phase_seal_hash": None, "binding_authority_phase_seal_hash": None,
            "run_input_bindings_hash": _H("b"), "run_input_bindings_row_count": 0,
            "run_input_bindings_empty_by_contract": True,
            "ordered_upstream_artifact_refs": [],
            "component_refs": [], "root_refs": [], "config_refs": [], "code_manifest_refs": [],
            "compute_git_commit": "deadbeef", "source_tree_hash": _H("c"),
            "run_config_manifest_hash": _H("d"), "registry_snapshot_hash": _H("e"),
            "environment_lock_hash": _H("f"),
        }

    def test_valid_and_hash(self):
        obj = self._rcs()
        h = ix.run_component_set_hash(obj)
        assert len(h) == 64 and h == ix.run_component_set_hash(self._rcs())

    def test_upstream_roles_enforced(self):
        obj = self._rcs("ALT")
        obj["ordered_upstream_artifact_refs"] = [{"role": "source_null_phase_seal", "hash": _H("a")}]
        assert len(ix.run_component_set_hash(obj)) == 64
        bad = self._rcs("ALT")
        bad["ordered_upstream_artifact_refs"] = []
        with pytest.raises(ValueError):
            ix.run_component_set_hash(bad)

    def test_extra_field_rejected(self):
        obj = self._rcs()
        obj["extra"] = 1
        with pytest.raises(ValueError):
            ix.validate_run_component_set(obj)


class TestSeals:
    def test_run_seal(self):
        payload = ix.build_run_seal(
            run_instance_id=_H("1"), run_component_set_hash=_H("2"),
            expected_data_index_hash=_H("3"), expected_index_hash=_H("4"),
            expected_feature_index_hash=_H("5"), shard_plan_hash=_H("6"),
            ordered_shard_commit_refs=[
                {"shard_id": _H("7"), "shard_manifest_hash": _H("8"), "shard_commit_hash": _H("9")}
            ],
            produced_data_unit_count=10, data_unit_id_set_hash=_H("a"),
            ledger_content_hash=_H("b"), row_count=20, logical_key_count=20,
            evaluation_id_set_hash=_H("c"), feature_ledger_content_hash=_H("d"),
            feature_row_count=10, feature_sufficient_id_set_hash=_H("e"),
            feature_empty_by_contract=False,
        )
        assert len(ix.run_seal_hash(payload)) == 64

    def test_phase_seal(self):
        payload = ix.build_phase_seal(
            phase="NULL", evidence_generation_id="G01", scope_design_hash=_H("1"),
            parent_phase_seal_hash=None, validity_registry_head_hash=_H("2"),
            data_replacement_key_set_hash=_H("3"), feature_replacement_key_set_hash=_H("4"),
            evaluation_replacement_key_set_hash=_H("5"),
            replacement_source_run_seal_hashes=[_H("6")],
            active_component_manifest_hash=_H("7"), active_data_index_hash=_H("8"),
            active_feature_index_hash=_H("9"), active_evaluation_index_hash=_H("a"),
            active_ledger_content_hash=_H("b"), active_feature_ledger_content_hash=_H("c"),
            active_feature_row_count=10, logical_key_count=20, evaluation_id_set_hash=_H("d"),
            feature_sufficient_id_set_hash=_H("e"),
            ordered_source_run_seal_hashes=[_H("6")], ordered_upstream_artifact_refs=[],
        )
        assert len(ix.phase_seal_hash(payload)) == 64

    def test_id_set_hash_domain(self):
        a = ix.id_set_hash("evaluation_id_set", [_H("1"), _H("2"), _H("1")])
        b = ix.id_set_hash("data_unit_id_set", [_H("1"), _H("2")])
        assert a != b
        with pytest.raises(ValueError):
            ix.id_set_hash("nope", [_H("1")])
