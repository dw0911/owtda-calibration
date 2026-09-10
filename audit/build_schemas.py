"""Generate the strict discriminated-union ledger schemas (audit P0-4).

Emits the seven objects the audit prescribed into ``configs/schema/``::

    scientific_row.schema.json / scientific_row_wire.schema.json
    feature_sufficient_row.schema.json / feature_sufficient_row_wire.schema.json
    scientific_result_projection.schema.json / feature_result_projection.schema.json
    schemas_manifest.json

Contract encoded (Plan §16, §16.1, §15.4):

* discriminator = ``row_type × phase × DGP_family × scenario_id × feature_id ×
  method_id`` (the plan's five dimensions plus ``scenario_id``, which §12.1/§12.2
  need to separate the two H1 alternatives); every variant fixes each field to
  ``value`` / ``null`` / ``forbidden`` and all variants reject unknown fields;
* REAL rows carry the synthetic fields as **required null** (never omitted, never
  forbidden) and the REAL truth fields as forbidden in the prediction layer;
* ``row_payload_hash`` is machinery-managed and the result hash is inserted before
  it (§16 ordering); both are declared in ``computed_fields``, not in ``fields``;
* floats are the only wire-encoded paths: ``f64:<16 lowercase hex big-endian>``.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parents[1]
OUT = REPO / "configs" / "schema"
WIRE_FLOAT_RULE = "f64:<16 lowercase hex, big-endian binary64>"

# concrete component identities (authoritative: src/owtda_cal/components.py)
FEATURE_IDS = {
    "BPI": "BPI_FIXED20_H01_SIGMA005_GAMMA1_V1",
    "MOMENTS": "MOMENTS_MEAN_COV_FROB_V1",
}
METHOD_IDS = {
    "M0": "M0_NAIVE_PERM_B999_V1",
    "M1": "M1_DMB_R1_TRI_EXTIID_B999_V1",
}

# ---------------------------------------------------------------- field groups
IDENTITY_VALUE = [
    "schema_version", "row_type", "project_id", "protocol_id", "freeze_id",
    "evidence_generation_id", "data_generation_id", "feature_generation_id",
    "method_generation_id", "phase", "experiment_id", "logical_cell_id",
    "physical_cell_id", "budget_membership", "logical_data_key", "data_unit_id",
    "data_content_hash", "logical_feature_key", "logical_evaluation_key",
    "evaluation_id", "feature_id", "feature_config_hash", "feature_sufficient_id",
    "method_id", "method_config_hash",
]
SYNTHETIC_IDENTITY = ["replicate_id", "master_replicate_id", "cluster_id", "base_series_id"]
RUN_PROVENANCE = [
    "run_instance_id", "compute_git_commit", "source_tree_hash",
    "run_config_manifest_hash", "data_registry_entry_hash",
    "feature_registry_entry_hash", "method_registry_entry_hash",
    "data_root_entry_hash", "resampling_root_entry_hash", "registry_snapshot_hash",
    "run_component_set_hash", "expected_index_hash", "expected_feature_index_hash",
    "shard_plan_hash", "environment_lock_hash",
]
SYNTHETIC_DATA = [
    "DGP_family", "scenario_id", "rho", "DGP_parameters", "initial_state_seed",
    "innovation_seed", "observation_noise_seed", "shift_direction_seed",
    "innovation_hash", "raw_series_hash", "true_boundary_synthetic",
    "source_null_logical_cell_id", "source_null_phase_seal_hash",
    "null_model_config_hash",
]
REAL_OR_SHARED_GEOMETRY = [
    "T", "dimension", "W", "stride", "overlap_ratio", "M_expected", "M_observed",
    "m_overlap", "dmb_q0",
]
FEATURE_PH = [
    "homology_dimensions", "coefficient_field", "grid_definition", "kernel_sigma",
    "persistence_weight", "point_limit", "infinite_death_rule",
]
FEATURE_SHARED = ["point_cloud_rule", "coordinate_cap", "canonical_sort", "feature_matrix_hash"]
FEATURE_MOMENTS = ["moment_components", "moment_scale", "moment_denominator"]
INFERENCE_COMMON = [
    "candidate_first", "candidate_last", "candidate_count", "eligibility",
    "ineligibility_reason", "resampling_stream_id", "observed_statistic",
    "exceed_count", "p_value", "alpha", "reject", "estimated_change_index",
    "estimated_change_raw_time", "localization_error_synthetic",
]
INFERENCE_M0 = ["B"]
INFERENCE_M1 = ["bandwidth_b", "kernel", "padding_rule"]
REAL_ONLY = [
    "task_id", "task_index_generation_id", "task_builder_config_hash",
    "task_signal_hash", "estimated_change_sample_coord",
    "estimated_change_relative_s",
]
REAL_EVAL_ONLY = [
    "subject_cluster_id", "subject_internal_id", "activity_A", "activity_B",
    "truth_sample_left", "truth_sample_right", "truth_relative_s_left",
    "truth_relative_s_right", "distance_seconds", "prediction_row_payload_hash",
    "truth_record_hash", "prediction_phase_seal_hash", "ground_truth_seal_hash",
]
FEATURE_SUFFICIENT_FIELDS = [
    "schema_version", "row_type", "project_id", "protocol_id", "freeze_id",
    "evidence_generation_id", "data_generation_id", "feature_generation_id",
    "logical_data_key", "logical_feature_key", "data_unit_id", "data_content_hash",
    "feature_id", "feature_sufficient_id", "feature_config_hash",
    "feature_matrix_hash", "a_r", "q_r",
]
FEATURE_PROJECTION_FIELDS = [
    "feature_sufficient_id", "data_content_hash", "feature_generation_id",
    "feature_config_hash", "feature_matrix_hash", "a_r", "q_r",
]
FLOAT_FIELDS = [
    "rho", "overlap_ratio", "dmb_q0", "coordinate_cap", "kernel_sigma",
    "persistence_weight", "moment_scale", "observed_statistic", "p_value", "alpha",
    "localization_error_synthetic", "estimated_change_relative_s", "m_overlap",
    "a_r", "q_r",
]
COMPUTED_FIELDS = {
    "row_payload_hash": "sha256 of the §15.4 hash-view canonical bytes (covers the inserted result hash)",
    "scientific_result_hash": "sha256 over the result-projection hash-view; inserted before row_payload_hash",
}
DATA_GROUPS = [
    "H0_N_AR", "H0_N_CIRCLE", "H1_SHAPE_CHANGE", "H1_MEAN_SHIFT",
    "REAL_PREDICTION", "REAL_EVALUATION",
]
GROUP_DISCRIMINATOR = {
    "H0_N_AR": {"phase": "NULL", "DGP_family": "N_AR", "scenario_id": "h0"},
    "H0_N_CIRCLE": {"phase": "NULL", "DGP_family": "N_CIRCLE", "scenario_id": "h0"},
    "H1_SHAPE_CHANGE": {"phase": "ALT", "DGP_family": "CIRCLE_BASED_H1", "scenario_id": "shape_change"},
    "H1_MEAN_SHIFT": {"phase": "ALT", "DGP_family": "CIRCLE_BASED_H1", "scenario_id": "mean_shift"},
    "REAL_PREDICTION": {"phase": "REAL", "DGP_family": None, "scenario_id": None},
    "REAL_EVALUATION": {"phase": "REAL", "DGP_family": None, "scenario_id": None},
}


def _is_real(group: str) -> bool:
    return group.startswith("REAL")


def _role(field: str, group: str, feature: str, method: str) -> str | None:
    real = _is_real(group)
    if field in IDENTITY_VALUE or field in RUN_PROVENANCE:
        return "value"
    if field in SYNTHETIC_IDENTITY:
        return "null" if real else "value"
    if field in SYNTHETIC_DATA:
        if real:
            # Plan §16.1 row 4/5: synthetic-only fields are *required null* in REAL rows.
            return "null"
        if field == "shift_direction_seed":
            return "value" if group == "H1_MEAN_SHIFT" else "null"
        if field == "true_boundary_synthetic":
            return "value" if group.startswith("H1") else "null"
        if field in ("source_null_logical_cell_id", "source_null_phase_seal_hash"):
            return "value" if group.startswith("H1") else "null"
        if field == "observation_noise_seed":
            return "null" if group == "H0_N_AR" else "value"
        return "value"
    if field in REAL_OR_SHARED_GEOMETRY:
        return "value"
    if field in FEATURE_PH:
        return "value" if feature == "BPI" else "null"
    if field in FEATURE_MOMENTS:
        return "value" if feature == "MOMENTS" else "null"
    if field in FEATURE_SHARED:
        return "value"
    if field in REAL_ONLY:
        return "value" if real else "forbidden"
    if field in REAL_EVAL_ONLY:
        if group == "REAL_EVALUATION":
            return "value"
        return "forbidden"
    if field in INFERENCE_COMMON:
        if field == "estimated_change_raw_time":
            return "null"
        if field == "localization_error_synthetic":
            if real:
                return "forbidden"
            return "value" if group.startswith("H1") else "null"
        if field == "estimated_change_index":
            return "null" if group == "REAL_PREDICTION" else "value"
        return "value"
    if field in INFERENCE_M0:
        return "value" if method == "M0" else "forbidden"
    if field in INFERENCE_M1:
        return "value" if method == "M1" else "null"
    return None


ALL_FIELDS = (
    IDENTITY_VALUE + SYNTHETIC_IDENTITY + RUN_PROVENANCE + SYNTHETIC_DATA
    + REAL_OR_SHARED_GEOMETRY + FEATURE_PH + FEATURE_SHARED + FEATURE_MOMENTS
    + INFERENCE_COMMON + INFERENCE_M0 + INFERENCE_M1 + REAL_ONLY + REAL_EVAL_ONLY
)


def _variant(group: str, feature: str, method: str) -> dict[str, Any]:
    fields = {}
    for name in ALL_FIELDS:
        role = _role(name, group, feature, method)
        if role is not None:
            fields[name] = role
    discriminator = {
        "row_type": "scientific_prediction"
        if group == "REAL_PREDICTION"
        else "scientific_evaluation",
        **GROUP_DISCRIMINATOR[group],
        "feature_id": FEATURE_IDS[feature],
        "method_id": METHOD_IDS[method],
    }
    return {
        "discriminator": discriminator,
        "data_group": group,
        "role_classes": {"feature": feature, "method": method},
        "fields": dict(sorted(fields.items())),
        "floats": [
            f for f in FLOAT_FIELDS if fields.get(f) == "value"
        ],
    }


def _scientific_row() -> dict[str, Any]:
    variants = [
        _variant(group, feature, method)
        for group in DATA_GROUPS
        for feature in FEATURE_IDS
        for method in METHOD_IDS
    ]
    return {
        "schema_version": 1,
        "schema_kind": "scientific_row",
        "schema_name": "scientific_row_v1",
        "unknown_fields": "reject",
        "null_rule": "required-null fields must be present with value null; omission is an error",
        "wire_float_rule": WIRE_FLOAT_RULE,
        "discriminator": [
            "row_type", "phase", "DGP_family", "scenario_id", "feature_id", "method_id",
        ],
        "discriminator_note": (
            "Plan §16.1 fixes row_type × phase × DGP_family × feature_id × method_id; "
            "scenario_id is added because §12.1/§12.2 separate the two H1 alternatives by it. "
            "For REAL rows DGP_family/scenario_id are the discriminator value null (and the row "
            "must carry them as required null), while phase=REAL identifies the layer."
        ),
        "source": "Plan §16 / §16.1 / §15.4",
        "computed_fields": COMPUTED_FIELDS,
        "variants": variants,
    }


def _wire(schema: dict[str, Any], *, name: str) -> dict[str, Any]:
    obj = json.loads(json.dumps(schema))
    obj["schema_kind"] = obj["schema_kind"] + "_wire"
    obj["schema_name"] = name
    obj["encoding"] = "all float fields replaced by f64: strings; all other values byte-identical"
    obj["decode_rule"] = (
        "decode only schema-flagged float paths; a plain string starting with f64: is never decoded"
    )
    return obj


def _feature_row() -> dict[str, Any]:
    return {
        "schema_version": 1,
        "schema_kind": "feature_sufficient_row",
        "schema_name": "feature_sufficient_row_v1",
        "unknown_fields": "reject",
        "null_rule": "required-null fields must be present with value null; omission is an error",
        "wire_float_rule": WIRE_FLOAT_RULE,
        "discriminator": ["row_type", "phase", "feature_generation_id"],
        "source": "Plan §16 (FEATURE_SUFFICIENT_LEDGER)",
        "computed_fields": {
            "row_payload_hash": "sha256 of the §15.4 hash-view canonical bytes (covers feature_result_hash)",
            "feature_result_hash": "sha256 over the feature projection hash-view; inserted before row_payload_hash",
        },
        "variants": [
            {
                "discriminator": {
                    "row_type": "feature_sufficient", "phase": phase,
                    "feature_generation_id": "F01",
                },
                "fields": {f: "value" for f in FEATURE_SUFFICIENT_FIELDS},
                "floats": ["a_r", "q_r"],
            }
            for phase in ("NULL", "ALT", "REAL")
        ],
    }


def _feature_projection() -> dict[str, Any]:
    return {
        "schema_version": 1,
        "schema_kind": "feature_result_projection",
        "schema_name": "feature_result_projection_v1",
        "unknown_fields": "reject",
        "null_rule": "projections contain no required-null fields",
        "wire_float_rule": WIRE_FLOAT_RULE,
        "discriminator": ["feature_generation_id"],
        "source": "Plan §16 (feature projection 恰含 7 个字段)",
        "hash_rule": "feature_result_hash over the §15.4 hash-view canonical bytes (floats f64-encoded)",
        "variants": [
            {
                "discriminator": {"feature_generation_id": "F01"},
                "fields": {f: "value" for f in FEATURE_PROJECTION_FIELDS},
                "floats": ["a_r", "q_r"],
            }
        ],
    }


def _scientific_projection() -> dict[str, Any]:
    full = _scientific_row()
    variants = []
    for variant in full["variants"]:
        fields = {
            k: v for k, v in variant["fields"].items() if k not in RUN_PROVENANCE
        }
        variants.append(
            {
                "discriminator": variant["discriminator"],
                "data_group": variant["data_group"],
                "role_classes": variant["role_classes"],
                "fields": fields,
                # the two hash fields are *derived from* this projection, so they are
                # excluded from its input field set together with run provenance.
                "forbidden_run_provenance": [
                    *RUN_PROVENANCE, "row_payload_hash", "scientific_result_hash",
                ],
                "floats": variant["floats"],
            }
        )
    return {
        "schema_version": 1,
        "schema_kind": "scientific_result_projection",
        "schema_name": "scientific_result_projection_v1",
        "unknown_fields": "reject",
        "hash_rule": "scientific_result_hash over the §15.4 hash-view canonical bytes (floats f64-encoded)",
        "encoding_order": "insert scientific_result_hash first, then compute row_payload_hash which covers it",
        "wire_float_rule": WIRE_FLOAT_RULE,
        "discriminator": [
            "row_type", "phase", "DGP_family", "scenario_id", "feature_id", "method_id",
        ],
        "source": "Plan §16 (projection 明确排除 run provenance)",
        "variants": variants,
    }


def _write(path: Path, doc: dict[str, Any]) -> str:
    text = json.dumps(doc, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    # write exact bytes: text-mode write_text would translate LF -> CRLF on Windows
    # and silently break the sha256 recorded in the manifest.
    path.write_bytes(text.encode("utf-8"))
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser(description="build strict ledger schemas")
    parser.add_argument("--out", default=str(OUT))
    args = parser.parse_args()
    out = Path(args.out).expanduser()
    out.mkdir(parents=True, exist_ok=True)

    documents = {
        "scientific_row.schema.json": _scientific_row(),
        "scientific_row_wire.schema.json": _wire(_scientific_row(), name="scientific_row_wire_v1"),
        "feature_sufficient_row.schema.json": _feature_row(),
        "feature_sufficient_row_wire.schema.json": _wire(
            _feature_row(), name="feature_sufficient_row_wire_v1"
        ),
        "scientific_result_projection.schema.json": _scientific_projection(),
        "feature_result_projection.schema.json": _feature_projection(),
    }
    entries = []
    for name, doc in documents.items():
        digest = _write(out / name, doc)
        entries.append(
            {
                "file": name,
                "schema_kind": doc["schema_kind"],
                "variants": len(doc["variants"]),
                "sha256": digest,
            }
        )

    manifest = {
        "schema_version": 1,
        "kind": "schemas_manifest",
        "unknown_fields_policy": "reject",
        "null_policy": "required-null fields are present-and-null; omission is an error",
        "wire_float_rule": WIRE_FLOAT_RULE,
        "discriminator_dimensions": [
            "row_type", "phase", "DGP_family", "scenario_id", "feature_id", "method_id",
        ],
        "data_groups": DATA_GROUPS,
        "feature_ids": FEATURE_IDS,
        "method_ids": METHOD_IDS,
        "generated_by": "audit/build_schemas.py",
        "objects": entries,
    }
    _write(out / "schemas_manifest.json", manifest)
    print(f"[schemas] wrote {len(documents)} schema objects + manifest into {out}")
    for entry in entries:
        print(f"  {entry['file']}: variants={entry['variants']} sha256={entry['sha256'][:12]}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
