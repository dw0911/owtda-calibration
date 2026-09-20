"""Strict ledger schema contracts (audit P0-4).

Golden hash, wire round-trip, unknown-field / required-null rejection and the
§16.1 minimum condition matrix are locked here so a schema edit cannot silently
change the scientific row bytes.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

from owtda_cal.rowschema import RowSchema, RowSchemaError

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "audit"))

import validate_schemas as vs

SCHEMA_DIR = REPO / "configs" / "schema"
GOLDEN_ROW_PAYLOAD_HASH = "3a9f2e8a19741cd47057119e379e1f1606e01c0f0dc2418bb9cde3548e77946b"
EXPECTED_FILES = {
    "scientific_row.schema.json",
    "scientific_row_wire.schema.json",
    "feature_sufficient_row.schema.json",
    "feature_sufficient_row_wire.schema.json",
    "scientific_result_projection.schema.json",
    "feature_result_projection.schema.json",
    "schemas_manifest.json",
}


def _load(name: str) -> dict:
    return json.loads((SCHEMA_DIR / name).read_text(encoding="utf-8"))


def _golden_schema() -> tuple[RowSchema, dict]:
    variant = vs._variant(_load("scientific_row.schema.json"), vs.GOLDEN_VARIANT)
    schema = RowSchema(
        schema_name="scientific_row_v1:golden",
        fields=dict(variant["fields"]),
        floats=set(variant["floats"]),
    )
    return schema, variant


class TestSchemaObjects:
    def test_all_seven_objects_present(self):
        present = {p.name for p in SCHEMA_DIR.iterdir() if p.is_file()}
        assert EXPECTED_FILES <= present

    def test_manifest_hashes_match_files(self):
        manifest = _load("schemas_manifest.json")
        assert manifest["unknown_fields_policy"] == "reject"
        for entry in manifest["objects"]:
            assert entry["sha256"] == vs.hashlib.sha256(
                (SCHEMA_DIR / entry["file"]).read_bytes()
            ).hexdigest()

    def test_wire_objects_declare_f64_rule(self):
        for name in ("scientific_row_wire.schema.json", "feature_sufficient_row_wire.schema.json"):
            wire = _load(name)
            assert wire["wire_float_rule"].startswith("f64:")
            assert "decode only schema-flagged float paths" in wire["decode_rule"]

    def test_discriminator_is_complete_and_unique(self):
        scientific = _load("scientific_row.schema.json")
        keys = {
            tuple(v["discriminator"][k] for k in scientific["discriminator"])
            for v in scientific["variants"]
        }
        assert len(keys) == len(scientific["variants"]) == 24

    def test_result_projection_excludes_run_provenance(self):
        projection = _load("scientific_result_projection.schema.json")
        excluded = {
            "run_instance_id", "compute_git_commit", "source_tree_hash",
            "run_config_manifest_hash", "registry_snapshot_hash",
            "run_component_set_hash", "expected_index_hash",
            "expected_feature_index_hash", "shard_plan_hash",
            "environment_lock_hash", "row_payload_hash", "scientific_result_hash",
        }
        for variant in projection["variants"]:
            assert excluded <= set(variant["forbidden_run_provenance"])
            for field in excluded:
                assert field not in variant["fields"]

    def test_roles_are_from_the_closed_set(self):
        for name in sorted(EXPECTED_FILES):
            if not name.endswith(".schema.json"):
                continue
            doc = _load(name)
            for variant in doc["variants"]:
                assert set(variant["fields"].values()) <= {"value", "null", "forbidden"}
                for field in variant["floats"]:
                    assert variant["fields"][field] == "value"


class TestGoldenRow:
    def test_golden_hash_is_stable(self):
        schema, variant = _golden_schema()
        row = vs._golden_row(variant)
        assert schema.row_payload_hash(schema.validate_logical(row)) == GOLDEN_ROW_PAYLOAD_HASH

    def test_wire_round_trip_is_bitwise(self):
        schema, variant = _golden_schema()
        row = schema.validate_logical(vs._golden_row(variant))
        wire = schema.encode_to_wire(row)
        decoded = schema.decode_from_wire(wire)
        for field in variant["floats"]:
            assert decoded[field] == row[field]
        assert schema.encode_to_wire(decoded) == wire

    def test_unknown_field_rejected(self):
        schema, variant = _golden_schema()
        row = schema.validate_logical(vs._golden_row(variant))
        with pytest.raises(RowSchemaError):
            schema.validate_logical({**row, "feature_hash": "x"})

    def test_omitted_required_null_rejected(self):
        schema, variant = _golden_schema()
        row = schema.validate_logical(vs._golden_row(variant))
        trimmed = {k: v for k, v in row.items() if k != "estimated_change_raw_time"}
        with pytest.raises(RowSchemaError):
            schema.validate_logical(trimmed)

    def test_missing_required_value_rejected(self):
        schema, variant = _golden_schema()
        row = schema.validate_logical(vs._golden_row(variant))
        row["p_value"] = None
        with pytest.raises(RowSchemaError):
            schema.validate_logical(row)

    def test_non_f64_wire_float_rejected(self):
        schema, variant = _golden_schema()
        row = schema.validate_logical(vs._golden_row(variant))
        wire = schema.encode_to_wire(row)
        with pytest.raises(RowSchemaError):
            schema.validate_wire({**wire, "p_value": 0.5})


class TestMinimumConditionMatrix:
    @pytest.mark.parametrize(
        "group,feature,method,field,expected",
        [
            ("H1_MEAN_SHIFT", "BPI", "M1", "shift_direction_seed", "value"),
            ("H1_SHAPE_CHANGE", "BPI", "M1", "shift_direction_seed", "null"),
            ("H0_N_CIRCLE", "BPI", "M0", "observation_noise_seed", "value"),
            ("H0_N_AR", "BPI", "M0", "observation_noise_seed", "null"),
            ("H0_N_AR", "BPI", "M0", "true_boundary_synthetic", "null"),
            ("H1_SHAPE_CHANGE", "BPI", "M0", "true_boundary_synthetic", "value"),
            ("H1_MEAN_SHIFT", "BPI", "M0", "source_null_logical_cell_id", "value"),
            ("H0_N_AR", "BPI", "M0", "source_null_logical_cell_id", "null"),
            ("H1_MEAN_SHIFT", "BPI", "M0", "B", "value"),
            ("H1_MEAN_SHIFT", "BPI", "M0", "bandwidth_b", "null"),
            ("H1_MEAN_SHIFT", "BPI", "M1", "bandwidth_b", "value"),
            ("H1_MEAN_SHIFT", "BPI", "M1", "B", "forbidden"),
            ("H1_MEAN_SHIFT", "MOMENTS", "M0", "homology_dimensions", "null"),
            ("H1_MEAN_SHIFT", "MOMENTS", "M0", "moment_components", "value"),
            ("H1_MEAN_SHIFT", "BPI", "M0", "moment_components", "null"),
            ("REAL_PREDICTION", "MOMENTS", "M0", "replicate_id", "null"),
            ("REAL_PREDICTION", "MOMENTS", "M0", "DGP_family", "null"),
            ("REAL_PREDICTION", "MOMENTS", "M0", "task_signal_hash", "value"),
            ("REAL_PREDICTION", "MOMENTS", "M0", "subject_internal_id", "forbidden"),
            ("REAL_PREDICTION", "MOMENTS", "M0", "estimated_change_raw_time", "null"),
            ("REAL_EVALUATION", "BPI", "M1", "subject_internal_id", "value"),
            ("REAL_EVALUATION", "BPI", "M1", "distance_seconds", "value"),
            ("REAL_EVALUATION", "BPI", "M1", "truth_record_hash", "value"),
        ],
    )
    def test_role(self, group, feature, method, field, expected):
        scientific = _load("scientific_row.schema.json")
        variant = next(
            v
            for v in scientific["variants"]
            if v["data_group"] == group
            and v["role_classes"]["feature"] == feature
            and v["role_classes"]["method"] == method
        )
        assert variant["fields"].get(field, "forbidden") == expected
