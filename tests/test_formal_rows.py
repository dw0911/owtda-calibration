"""Re-audit 2026-09-17 (R5-03): the formal row must satisfy the frozen schema.

The audit found the adapter emitted an 18-field row while the frozen
``scientific_row.schema.json`` requires 88 value + 10 null fields (and 20
forbidden) for a H0 BPI/M1 NULL row.  These tests pin that ``formal_rows`` builds
the full row and that ``RowSchema.validate_logical`` accepts it, for every H0
variant -- value fields are concrete, null fields are explicit, forbidden fields
are absent.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]

import sys

sys.path.insert(0, str(REPO / "src"))

from owtda_cal import cells, formal, formal_rows, scope

FEATURES = ["BPI_FIXED20_H01_SIGMA005_GAMMA1_V1", "MOMENTS_MEAN_COV_FROB_V1"]
METHODS = ["M0_NAIVE_PERM_B999_V1", "M1_DMB_R1_TRI_EXTIID_B999_V1"]


@pytest.fixture(scope="module")
def manifest():
    return json.loads((REPO / "governance" / "FREEZE_MANIFEST.json").read_text(encoding="utf-8"))


def _ctx(manifest):
    ctx = formal.formal_context(manifest, "NULL")
    ctx.update(
        source_tree_hash=manifest["source_tree_hash"],
        environment_lock_hash=manifest.get("environment_lock_hash"),
        compute_git_commit="HEAD",
    )
    return ctx


def _build(manifest, *, family, feature_id, method_id, method_key, cell, replicate_id=1):
    ctx = _ctx(manifest)
    mid = cells.master_replicate_id(
        project_id=ctx["project_id"], protocol_id=ctx["protocol_id"],
        freeze_id=ctx["freeze_id"], evidence_generation_id=ctx["evidence_generation_id"],
        phase="NULL", DGP_family=family, replicate_id=replicate_id,
    )
    dmh = "d" * 64
    ci = formal.formal_cell_identity(
        ctx=ctx, cell=cell, family=family, master_replicate_id=mid,
        data_model_config_hash=dmh, feature_id=feature_id,
    )
    ei = formal.formal_evaluation_identity(
        ctx=ctx, data_unit_id=ci["data_unit_id"], logical_data_key=ci["logical_data_key"],
        feature_id=feature_id, feature_sufficient_id=ci["feature_sufficient_id"],
        method_id=method_id, method_config_hash_value="m" * 64,
    )
    out = {"observed_statistic": 1.23, "exceed_count": 10, "p_value": 0.011,
           "reject": True, "M": cell.M}
    scan = {"candidate_first": 1, "candidate_last": cell.M,
            "candidate_count": cell.M, "khat": cell.M // 2}
    content = {"data_content_hash": "a" * 64, "feature_matrix_hash": "b" * 64,
               "raw_series_hash": "c" * 64, "innovation_hash": "d" * 64,
               "initial_state_seed": "e" * 64, "innovation_seed": "f" * 64,
               "observation_noise_seed": "g" * 64}
    run_identity = {
        "compute_git_commit": "HEAD",
        "run_config_manifest_hash": "r" * 64, "registry_snapshot_hash": "r" * 64,
        "run_component_set_hash": "r" * 64, "run_instance_id": "RUN-1",
        "shard_plan_hash": "r" * 64, "expected_index_hash": "r" * 64,
        "expected_feature_index_hash": "r" * 64, "feature_registry_entry_hash": "r" * 64,
        "method_registry_entry_hash": "r" * 64, "data_registry_entry_hash": "r" * 64,
        "data_root_entry_hash": "r" * 64, "resampling_root_entry_hash": "r" * 64,
    }
    schema = formal_rows.load_row_schema(
        phase="NULL", DGP_family=family, scenario_id="h0",
        feature_id=feature_id, method_id=method_id,
    )
    return formal_rows.build_formal_row(
        ctx=ctx, cell=cell, family=family, scenario_id="h0", replicate_id=replicate_id,
        feature_id=feature_id, method_id=method_id, method_key=method_key,
        cell_identity=ci, eval_identity=ei, out=out, scan=scan,
        content=content, run_identity=run_identity,
        null_model_config_hash="n" * 64, feature_config_hash="f" * 64,
        method_config_hash="m" * 64, schema=schema,
    )


def test_schema_roles_are_88_10_20():
    sch = formal_rows.load_row_schema(
        phase="NULL", DGP_family="N_AR", scenario_id="h0",
        feature_id=FEATURES[0], method_id=METHODS[1],
    )
    roles = {}
    for r in sch.fields.values():
        roles[r] = roles.get(r, 0) + 1
    assert roles == {"value": 88, "null": 10, "forbidden": 20}


def test_the_full_row_validates_for_every_h0_variant(manifest):
    for family in ("N_AR", "N_CIRCLE"):
        for cell in scope.h0_null_cells():
            if cell.family != family:
                continue
            for feature_id in FEATURES:
                for method_id in METHODS:
                    method_key = "M0" if "M0" in method_id else "M1"
                    sch = formal_rows.load_row_schema(
                        phase="NULL", DGP_family=family, scenario_id="h0",
                        feature_id=feature_id, method_id=method_id,
                    )
                    row = _build(
                        manifest, family=family, feature_id=feature_id,
                        method_id=method_id, method_key=method_key, cell=cell,
                    )
                    validated = sch.validate_logical(row)
                    expected = sum(1 for r in sch.fields.values() if r != "forbidden")
                    assert len(validated) == expected


def test_the_forbidden_fields_are_absent(manifest):
    sch = formal_rows.load_row_schema(
        phase="NULL", DGP_family="N_AR", scenario_id="h0",
        feature_id=FEATURES[0], method_id=METHODS[1],
    )
    cell = next(c for c in scope.h0_null_cells() if c.family == "N_AR")
    row = _build(
        manifest, family="N_AR", feature_id=FEATURES[0], method_id=METHODS[1],
        method_key="M1", cell=cell,
    )
    for forbidden in ("task_id", "subject_id", "subject_cluster_id",
                      "truth_record_hash", "activity_A", "activity_B"):
        assert forbidden not in row
    validated = sch.validate_logical(row)
    assert "task_id" not in validated


def test_the_row_hashes_with_the_plan16_ordering(manifest):
    sch = formal_rows.load_row_schema(
        phase="NULL", DGP_family="N_AR", scenario_id="h0",
        feature_id=FEATURES[0], method_id=METHODS[1],
    )
    cell = next(c for c in scope.h0_null_cells() if c.family == "N_AR")
    row = _build(
        manifest, family="N_AR", feature_id=FEATURES[0], method_id=METHODS[1],
        method_key="M1", cell=cell,
    )
    hashed = sch.with_hash(row, result_hash="r" * 64)
    assert hashed["scientific_result_hash"] == "r" * 64
    assert len(hashed["row_payload_hash"]) == 64
    # round-trip: the wire encoding reproduces the floats bit-for-bit (the
    # hash-less logical row, since computed hashes are not schema-managed)
    sch.round_trip(row)


class TestFeatureSufficientRow:
    def test_feature_sufficient_row_validates(self, manifest):
        ctx = _ctx(manifest)
        feature_id = FEATURES[0]
        cell = next(c for c in scope.h0_null_cells() if c.family == "N_AR")
        mid = cells.master_replicate_id(
            project_id=ctx["project_id"], protocol_id=ctx["protocol_id"],
            freeze_id=ctx["freeze_id"], evidence_generation_id=ctx["evidence_generation_id"],
            phase="NULL", DGP_family=cell.family, replicate_id=1,
        )
        ci = formal.formal_cell_identity(
            ctx=ctx, cell=cell, family=cell.family, master_replicate_id=mid,
            data_model_config_hash="d" * 64, feature_id=feature_id,
        )
        row = formal_rows.build_feature_sufficient_row(
            ctx=ctx, feature_id=feature_id, cell_identity=ci,
            sufficient={"a": [0.1, 0.2, 0.3], "q": 0.5},
            content={"data_content_hash": "a" * 64},
            feature_config_hash="f" * 64, feature_matrix_hash="b" * 64,
        )
        sch = formal_rows.load_feature_schema()
        validated = sch.validate_logical(row)
        assert len(validated) == 18

    def test_feature_sufficient_wire_round_trips_the_vector(self, manifest):
        ctx = _ctx(manifest)
        feature_id = FEATURES[0]
        cell = next(c for c in scope.h0_null_cells() if c.family == "N_AR")
        mid = cells.master_replicate_id(
            project_id=ctx["project_id"], protocol_id=ctx["protocol_id"],
            freeze_id=ctx["freeze_id"], evidence_generation_id=ctx["evidence_generation_id"],
            phase="NULL", DGP_family=cell.family, replicate_id=1,
        )
        ci = formal.formal_cell_identity(
            ctx=ctx, cell=cell, family=cell.family, master_replicate_id=mid,
            data_model_config_hash="d" * 64, feature_id=feature_id,
        )
        a_r = [0.1, 0.2, 0.3]
        row = formal_rows.build_feature_sufficient_row(
            ctx=ctx, feature_id=feature_id, cell_identity=ci,
            sufficient={"a": a_r, "q": 0.5},
            content={"data_content_hash": "a" * 64},
            feature_config_hash="f" * 64, feature_matrix_hash="b" * 64,
        )
        sch = formal_rows.load_feature_schema()
        # the wire encoding encodes a_r as a list of f64 hex and decodes it
        # back to the same floats bit-for-bit
        wire = sch.encode_to_wire(row)
        assert isinstance(wire["a_r"], list)
        assert all(w.startswith("f64:") for w in wire["a_r"])
        decoded = sch.decode_from_wire(wire)
        assert decoded["a_r"] == a_r
