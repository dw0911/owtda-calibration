"""Run identity / index / seal contracts (Plan §16.2, §19 #88/#91)."""

import hashlib

import pytest

from owtda_cal import runs

_A = "a" * 64
_B = "b" * 64
_C = "c" * 64
_D = "d" * 64
_E = "e" * 64
_F = "f" * 64


def _refs():
    return [
        runs.ref(role="feature", stable_id="MOMENTS", generation_id="F01", hash_value=_B),
        runs.ref(role="feature", stable_id="BPI", generation_id="F01", hash_value=_A),
    ]


def _component_set(**overrides):
    fields = {
        "schema_version": 1,
        "project_id": "owtda-cal-r1",
        "protocol_id": "P",
        "freeze_id": _A,
        "evidence_generation_id": "G01",
        "phase": "NULL",
        "scope_design_hash": _A,
        "parent_phase_seal_hash": None,
        "binding_authority_phase_seal_hash": None,
        "run_input_bindings_hash": _B,
        "run_input_bindings_row_count": 3,
        "run_input_bindings_empty_by_contract": False,
        "ordered_upstream_artifact_refs": [],
        "component_refs": _refs(),
        "root_refs": [
            runs.ref(role="root", stable_id="null_data", generation_id="D01", hash_value=_C)
        ],
        "config_refs": [
            runs.ref(role="config", stable_id="compute", generation_id="C01", hash_value=_D)
        ],
        "code_manifest_refs": [
            runs.ref(role="code", stable_id="core", generation_id="K01", hash_value=_E)
        ],
        "compute_git_commit": "0" * 40,
        "source_tree_hash": _F,
        "run_config_manifest_hash": _A,
        "registry_snapshot_hash": _B,
        "environment_lock_hash": _C,
    }
    fields.update(overrides)
    return fields


class TestRefs:
    def test_ref_hash_must_be_hex64(self):
        with pytest.raises(runs.RunError):
            runs.ref(role="r", stable_id="s", generation_id="g", hash_value="zz")

    def test_sorted_and_unique(self):
        ordered = runs.sorted_refs(_refs())
        assert [r["stable_id"] for r in ordered] == ["BPI", "MOMENTS"]

    def test_duplicate_key_rejected(self):
        dup = [
            runs.ref(role="feature", stable_id="BPI", generation_id="F01", hash_value=_A),
            runs.ref(role="feature", stable_id="BPI", generation_id="F01", hash_value=_B),
        ]
        with pytest.raises(runs.RunError):
            runs.sorted_refs(dup)

    def test_multiple_generations_same_role_stable_rejected(self):
        dup = [
            runs.ref(role="feature", stable_id="BPI", generation_id="F01", hash_value=_A),
            runs.ref(role="feature", stable_id="BPI", generation_id="F02", hash_value=_B),
        ]
        with pytest.raises(runs.RunError):
            runs.sorted_refs(dup)

    def test_unknown_field_rejected(self):
        bad = [dict(runs.ref(role="r", stable_id="s", generation_id="g", hash_value=_A))]
        bad[0]["extra"] = 1
        with pytest.raises(runs.RunError):
            runs.sorted_refs(bad)


class TestComponentSet:
    def test_fields_are_exactly_the_frozen_whitelist(self):
        payload = runs.run_component_set(**_component_set())
        assert set(payload) == runs.COMPONENT_SET_FIELDS

    def test_downstream_fields_impossible(self):
        for forbidden in ("run_seal_hash", "phase_seal_hash", "run_instance_id", "expected_index_hash"):
            with pytest.raises(runs.RunError):
                runs.run_component_set(**_component_set(**{forbidden: _A}))

    def test_hash_stable_and_sensitive(self):
        payload = runs.run_component_set(**_component_set())
        h1 = runs.run_component_set_hash(payload)
        h2 = runs.run_component_set_hash(runs.run_component_set(**_component_set()))
        assert h1 == h2
        changed = runs.run_component_set(**_component_set(scope_design_hash=_F))
        assert runs.run_component_set_hash(changed) != h1

    def test_bad_hash_field_rejected(self):
        with pytest.raises(runs.RunError):
            runs.run_component_set(**_component_set(scope_design_hash="xyz"))

    def test_row_count_must_be_int(self):
        with pytest.raises(runs.RunError):
            runs.run_component_set(**_component_set(run_input_bindings_row_count="3"))


class TestInputBindings:
    def _rows(self):
        return [
            runs.input_binding(role="root", ref_kind="root", stable_id="null_M1",
                               generation_id="M01", hash_value=_B, source="registry"),
            runs.input_binding(role="root", ref_kind="root", stable_id="null_data",
                               generation_id="D01", hash_value=_A, source="registry"),
        ]

    def test_jsonl_bytes_and_hash(self):
        data, digest, count = runs.run_input_bindings(self._rows())
        assert data.endswith(b"\n") and b"\r" not in data
        assert digest == hashlib.sha256(data).hexdigest()
        assert count == 2
        # ordering key is (role, stable_id, generation_id): "null_M1" < "null_data"
        assert b'"stable_id":"null_M1"' in data.split(b"\n")[0]

    def test_duplicate_binding_key_rejected(self):
        rows = self._rows()
        with pytest.raises(runs.RunError):
            runs.run_input_bindings([*rows, dict(rows[0])])

    def test_unknown_ref_kind_rejected(self):
        with pytest.raises(runs.RunError):
            runs.input_binding(role="r", ref_kind="nope", stable_id="s",
                               generation_id="g", hash_value=_A, source="x")


class TestExpectedIndexes:
    def _triple(self):
        data = [{"logical_data_key": _A, "data_unit_id": _B}]
        feature = [
            {
                "logical_data_key": _A,
                "logical_feature_key": _C,
                "data_unit_id": _B,
                "feature_sufficient_id": _D,
            }
        ]
        evaluation = [
            {
                "logical_data_key": _A,
                "logical_feature_key": _C,
                "logical_evaluation_key": _E,
                "data_unit_id": _B,
                "feature_sufficient_id": _D,
                "evaluation_id": _F,
            }
        ]
        return data, feature, evaluation

    def test_closure_holds(self):
        data, feature, evaluation = self._triple()
        runs.assert_index_closure(
            runs.expected_data_index(data),
            runs.expected_feature_index(feature),
            runs.expected_evaluation_index(evaluation),
        )

    def test_non_hex_field_rejected(self):
        data, _, _ = self._triple()
        with pytest.raises(runs.RunError):
            runs.expected_data_index([{**data[0], "data_unit_id": "xyz"}])

    def test_duplicate_primary_key_rejected(self):
        data, _, _ = self._triple()
        with pytest.raises(runs.RunError):
            runs.expected_data_index([data[0], dict(data[0])])

    def test_mismatched_data_unit_breaks_closure(self):
        data, feature, evaluation = self._triple()
        with pytest.raises(runs.RunError):
            runs.assert_index_closure(
                runs.expected_data_index(data),
                runs.expected_feature_index([{**feature[0], "data_unit_id": _F}]),
                runs.expected_evaluation_index(evaluation),
            )

    def test_unknown_feature_key_breaks_closure(self):
        data, _, evaluation = self._triple()
        with pytest.raises(runs.RunError):
            runs.assert_index_closure(
                runs.expected_data_index(data), [], runs.expected_evaluation_index(evaluation)
            )

    def test_rows_sorted_by_primary_key(self):
        data = [
            {"logical_data_key": _B, "data_unit_id": _A},
            {"logical_data_key": _A, "data_unit_id": _B},
        ]
        assert [r["logical_data_key"] for r in runs.expected_data_index(data)] == [_A, _B]


class TestIdSetsAndSeal:
    def test_id_set_hash_dedups_and_domains(self):
        assert runs.id_set_hash("data_unit", [_A, _A, _B]) == runs.id_set_hash(
            "data_unit", [_B, _A]
        )
        assert runs.id_set_hash("data_unit", [_A]) != runs.id_set_hash("evaluation", [_A])
        assert len(runs.id_set_hash("feature_sufficient", [])) == 64

    def test_unknown_id_set_kind_rejected(self):
        with pytest.raises(runs.RunError):
            runs.id_set_hash("nope", [_A])

    def test_run_instance_sensitive_to_every_input(self):
        base = {
            "phase": "NULL",
            "evidence_generation_id": "G01",
            "run_component_set_hash": _A,
            "expected_data_index_hash": _B,
            "expected_index_hash": _C,
            "expected_feature_index_hash": _D,
            "environment_lock_hash": _E,
        }
        rid = runs.run_instance_id(**base)
        for field in base:
            if field == "phase":
                assert runs.run_instance_id(**{**base, field: "ALT"}) != rid
            else:
                assert runs.run_instance_id(**{**base, field: _F}) != rid

    def _seal(self, **overrides):
        fields = {
            "run_instance_id": _A,
            "run_component_set_hash": _B,
            "expected_data_index_hash": _C,
            "expected_index_hash": _D,
            "expected_feature_index_hash": _E,
            "shard_plan_hash": _F,
            "ordered_shard_commit_refs": [
                {"shard_id": "s2", "shard_manifest_hash": _A, "shard_commit_hash": _B},
                {"shard_id": "s1", "shard_manifest_hash": _C, "shard_commit_hash": _D},
            ],
            "produced_data_unit_count": 10,
            "data_unit_id_set_hash": _A,
            "ledger_content_hash": _B,
            "row_count": 20,
            "logical_key_count": 10,
            "evaluation_id_set_hash": _C,
            "feature_ledger_content_hash": _D,
            "feature_row_count": 20,
            "feature_sufficient_id_set_hash": _E,
            "feature_empty_by_contract": False,
        }
        fields.update(overrides)
        return fields

    def test_seal_fields_exact_and_commits_ordered(self):
        payload = runs.run_seal_payload(**self._seal())
        assert set(payload) == runs.RUN_SEAL_FIELDS
        assert [c["shard_id"] for c in payload["ordered_shard_commit_refs"]] == ["s1", "s2"]

    def test_seal_rejects_self_hash_and_duplicates(self):
        with pytest.raises(runs.RunError):
            runs.run_seal_payload(**self._seal(run_seal_hash=_A))
        dup = [
            {"shard_id": "s1", "shard_manifest_hash": _A, "shard_commit_hash": _B},
            {"shard_id": "s1", "shard_manifest_hash": _C, "shard_commit_hash": _D},
        ]
        with pytest.raises(runs.RunError):
            runs.run_seal_payload(**self._seal(ordered_shard_commit_refs=dup))

    def test_seal_counts_must_be_non_negative_int(self):
        with pytest.raises(runs.RunError):
            runs.run_seal_payload(**self._seal(row_count=-1))

    def test_seal_hash_stable(self):
        p1 = runs.run_seal_payload(**self._seal())
        p2 = runs.run_seal_payload(**self._seal())
        assert runs.run_seal_hash(p1) == runs.run_seal_hash(p2)
