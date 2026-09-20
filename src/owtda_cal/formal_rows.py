"""Formal scientific-row builder (Plan §15.4 / §16.1).

The audit's finding (R5-03): the adapter emitted only an 18-field row, while the
frozen ``configs/schema/scientific_row.schema.json`` requires 88 value + 10 null
fields for a H0 BPI/M1 NULL row, and no feature-sufficient record.  This module
builds the **full** row from the real computation so the schema can be validated.

Field roles are *not* uniform: ``B`` is value for M0 and forbidden for M1,
``kernel``/``padding_rule`` are value for M1 and null for M0, ``kernel_sigma`` and
the moment fields flip between BPI and MOMENTS, and ``dimension`` is value in
both but differs (800 vs 5/9).  ``build_formal_row`` therefore assembles a
*candidate* value for every field and lets the per-variant ``RowSchema`` decide
the final role -- a value field must be non-None, a null field is emitted as
``None``, and a forbidden field is omitted.  No field is ever blanket-filled with
``None`` to satisfy a value role.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from . import cells, dgp, formal_ids, scope
from .calibrate import dmb_block_length
from .features import feature_dimensionality
from .rowschema import RowSchema
from .scan import estimated_change_raw_time

REPO = Path(__file__).resolve().parents[2]
_SCHEMA_PATH = REPO / "configs" / "schema" / "scientific_row.schema.json"
_FEATURE_SCHEMA_PATH = REPO / "configs" / "schema" / "feature_sufficient_row.schema.json"

POINT_LIMIT = 128
KERNEL = "gaussian"
KERNEL_SIGMA = 0.05
PERSISTENCE_WEIGHT = 1.0  # lifetime weight w(v)=v^1
HOMOLOGY_DIMENSIONS = ["H0", "H1"]
COEFFICIENT_FIELD = "F2"
ALPHA = 0.05
ROW_TYPE = "scientific_evaluation"
SCHEMA_VERSION = 1
B = 999


def load_row_schema(
    *,
    phase: str,
    DGP_family: str | None,
    scenario_id: str,
    feature_id: str,
    method_id: str,
    row_type: str = ROW_TYPE,
) -> RowSchema:
    """Load the exact per-variant schema for one (phase, DGP, scenario, feature, method)."""
    data = json.loads(_SCHEMA_PATH.read_text(encoding="utf-8"))
    for variant in data["variants"]:
        disc = variant["discriminator"]
        if (
            disc.get("row_type") == row_type
            and disc.get("phase") == phase
            and disc.get("DGP_family") == DGP_family
            and disc.get("scenario_id") == scenario_id
            and disc.get("feature_id") == feature_id
            and disc.get("method_id") == method_id
        ):
            return RowSchema(
                schema_name=data["schema_name"],
                fields=variant["fields"],
                floats=set(variant["floats"]),
            )
    raise ValueError(
        f"no scientific_row variant for {row_type}/{phase}/{DGP_family}/"
        f"{scenario_id}/{feature_id}/{method_id}"
    )


def load_feature_schema() -> RowSchema:
    """The feature-sufficient row schema (a_r/q_r + identity + content hashes)."""
    data = json.loads(_FEATURE_SCHEMA_PATH.read_text(encoding="utf-8"))
    variant = data["variants"][0]
    return RowSchema(
        schema_name=data["schema_name"],
        fields=variant["fields"],
        floats=set(variant["floats"]),
    )


def _coordinate_cap(family: str) -> float:
    """The frozen BPI coordinate cap per DGP family (N_AR=6.0, circle=2.5)."""
    return {"N_AR": 6.0, "N_CIRCLE": 2.5, "CIRCLE_BASED_H1": 2.5}.get(family, 2.5)


def build_formal_row(
    *,
    ctx: dict[str, Any],
    cell: Any,
    family: str,
    scenario_id: str,
    replicate_id: int,
    feature_id: str,
    method_id: str,
    method_key: str,
    cell_identity: dict[str, str],
    eval_identity: dict[str, str],
    out: dict[str, Any],
    scan: dict[str, Any],
    content: dict[str, str],
    run_identity: dict[str, Any],
    null_model_config_hash: str,
    feature_config_hash: str,
    method_config_hash: str,
    schema: RowSchema,
    source_null_phase_seal_hash: str | None = None,
    shift_direction_seed: str | None = None,
) -> dict[str, Any]:
    """Build the complete logical scientific row, filtered through the variant schema."""
    phase = ctx["phase"]
    data_generation_id = ctx["data_generation_id"]
    feature_kind = "bpi" if feature_id.startswith("BPI") else "moments"
    feature_generation_id = ctx.get("feature_generation_id", {}).get(feature_kind)
    method_generation_id = ctx["method_generation_id"].get(method_key)
    master_replicate_id = cells.master_replicate_id(
        project_id=ctx["project_id"],
        protocol_id=ctx["protocol_id"],
        freeze_id=ctx["freeze_id"],
        evidence_generation_id=ctx["evidence_generation_id"],
        phase=phase,
        DGP_family=family,
        replicate_id=replicate_id,
    )
    experiment_id = scope.experiment_id(
        project_id=ctx["project_id"],
        protocol_id=ctx["protocol_id"],
        freeze_id=ctx["freeze_id"],
        evidence_generation_id=ctx["evidence_generation_id"],
        phase=phase,
        scenario_id=scenario_id,
    )
    cluster_id = cells.cluster_id(
        phase=phase, DGP_stratum=family, master_replicate_id=master_replicate_id
    )
    resampling_stream_id = formal_ids.resampling_stream_id(
        data_generation_id=data_generation_id,
        data_unit_id=cell_identity["data_unit_id"],
        method_random_family=method_key,
    )
    cloud_dim = 3 if family == "N_AR" else 2

    # Candidate value for every field; the schema decides value/null/forbidden.
    candidates: dict[str, Any] = {
        "row_type": ROW_TYPE,
        "schema_version": SCHEMA_VERSION,
        "phase": phase,
        "DGP_family": family,
        "scenario_id": scenario_id,
        "feature_id": feature_id,
        "method_id": method_id,
        "project_id": ctx["project_id"],
        "protocol_id": ctx["protocol_id"],
        "freeze_id": ctx["freeze_id"],
        "evidence_generation_id": ctx["evidence_generation_id"],
        "data_generation_id": data_generation_id,
        "feature_generation_id": feature_generation_id,
        "method_generation_id": method_generation_id,
        "source_tree_hash": ctx.get("source_tree_hash"),
        "environment_lock_hash": ctx.get("environment_lock_hash"),
        "compute_git_commit": run_identity.get("compute_git_commit"),
        "run_config_manifest_hash": run_identity.get("run_config_manifest_hash"),
        "registry_snapshot_hash": run_identity.get("registry_snapshot_hash"),
        "run_component_set_hash": run_identity.get("run_component_set_hash"),
        "run_instance_id": run_identity.get("run_instance_id"),
        "shard_plan_hash": run_identity.get("shard_plan_hash"),
        "expected_index_hash": run_identity.get("expected_index_hash"),
        "expected_feature_index_hash": run_identity.get("expected_feature_index_hash"),
        "feature_registry_entry_hash": run_identity.get("feature_registry_entry_hash"),
        "method_registry_entry_hash": run_identity.get("method_registry_entry_hash"),
        "data_registry_entry_hash": run_identity.get("data_registry_entry_hash"),
        "data_root_entry_hash": run_identity.get("data_root_entry_hash"),
        "resampling_root_entry_hash": run_identity.get("resampling_root_entry_hash"),
        "experiment_id": experiment_id,
        "cluster_id": cluster_id,
        "master_replicate_id": master_replicate_id,
        "replicate_id": replicate_id,
        "logical_cell_id": cell_identity["logical_cell_id"],
        "physical_cell_id": cell_identity["physical_cell_id"],
        "base_series_id": cell_identity["base_series_id"],
        "data_unit_id": cell_identity["data_unit_id"],
        "logical_data_key": cell_identity["logical_data_key"],
        "logical_feature_key": cell_identity["logical_feature_key"],
        "logical_evaluation_key": eval_identity["logical_evaluation_key"],
        "feature_sufficient_id": cell_identity["feature_sufficient_id"],
        "evaluation_id": eval_identity["evaluation_id"],
        "resampling_stream_id": resampling_stream_id,
        "null_model_config_hash": null_model_config_hash,
        "feature_config_hash": feature_config_hash,
        "method_config_hash": method_config_hash,
        "W": cell.W,
        "T": cell.T,
        "stride": cell.stride,
        "M_expected": cell.M,
        "M_observed": out.get("M", cell.M),
        "rho": float(cell.rho),
        "budget_membership": list(getattr(cell, "budget_membership", ())),
        "m_overlap": cells.window_count(cell.T, W=cell.W, stride=cell.stride),
        "overlap_ratio": cells.window_count(cell.T, W=cell.W, stride=cell.stride) / cell.M,
        "dmb_q0": cell.W // cell.stride + 1,
        "coordinate_cap": _coordinate_cap(family),
        "observed_statistic": out["observed_statistic"],
        "exceed_count": out["exceed_count"],
        "p_value": out["p_value"],
        "reject": out["reject"],
        "candidate_first": scan.get("candidate_first"),
        "candidate_last": scan.get("candidate_last"),
        "candidate_count": scan.get("candidate_count"),
        "canonical_sort": "lexsort-bit-dedup",  # DATA_SPEC §4
        "estimated_change_index": scan.get("khat"),
        "eligibility": True,
        "ineligibility_reason": "",
        "point_limit": POINT_LIMIT,
        "point_cloud_rule": "multivariate-direct-window; univariate delay-embedding",
        "padding_rule": "no-padding",
        "infinite_death_rule": "drop-infinite-death",
        "grid_definition": "20x20 delta=1/20 center=(r+1/2)delta",
        "kernel": KERNEL,
        "kernel_sigma": KERNEL_SIGMA,
        "bandwidth_b": dmb_block_length(W=cell.W, stride=cell.stride, M=cell.M),
        "persistence_weight": PERSISTENCE_WEIGHT,
        "homology_dimensions": list(HOMOLOGY_DIMENSIONS),
        "dimension": feature_dimensionality(feature_kind, cloud_dim=cloud_dim),
        "coefficient_field": COEFFICIENT_FIELD,
        "alpha": ALPHA,
        "moment_components": ["mean", "cov_diag", "cov_offdiag_sqrt2"],
        "moment_denominator": "n",
        "moment_scale": 1.0,
        "data_content_hash": content.get("data_content_hash"),
        "feature_matrix_hash": content.get("feature_matrix_hash"),
        "raw_series_hash": content.get("raw_series_hash"),
        "innovation_hash": content.get("innovation_hash"),
        "initial_state_seed": content.get("initial_state_seed"),
        "innovation_seed": content.get("innovation_seed"),
        "observation_noise_seed": content.get("observation_noise_seed"),
        "DGP_parameters": {"rho": cell.rho, "family": family},
        "B": B,
        "estimated_change_raw_time": None,
        "localization_error_synthetic": (
            abs(
                estimated_change_raw_time(scan["khat"], stride=cell.stride, W=cell.W)
                - dgp.h1_change_point(cell.T)
            )
            if phase == scope.PHASE_ALT else None
        ),
        "shift_direction_seed": shift_direction_seed,
        "source_null_logical_cell_id": (
            scope.logical_cell_id(
                project_id=ctx["project_id"], protocol_id=ctx["protocol_id"],
                freeze_id=ctx["freeze_id"], evidence_generation_id=ctx["evidence_generation_id"],
                phase=scope.PHASE_NULL, DGP_family=dgp.DGP_FAMILY_N_CIRCLE,
                scenario_id=scope.SCENARIO_NULL, rho=cell.rho, W=cell.W,
                stride=cell.stride, T=cell.T, M=cell.M,
            )
            if phase == scope.PHASE_ALT else None
        ),
        "source_null_phase_seal_hash": source_null_phase_seal_hash,
        "true_boundary_synthetic": (
            dgp.h1_change_point(cell.T) if phase == scope.PHASE_ALT else None
        ),
    }

    # Filter through the schema: value fields keep their candidate (must be
    # non-None), null fields are emitted as None, forbidden fields are omitted.
    row: dict[str, Any] = {}
    for field, role in schema.fields.items():
        if role == "forbidden":
            continue
        row[field] = None if role == "null" else candidates[field]
    return row


def build_feature_sufficient_row(
    *,
    ctx: dict[str, Any],
    feature_id: str,
    cell_identity: dict[str, str],
    sufficient: dict[str, Any],
    content: dict[str, str],
    feature_config_hash: str,
    feature_matrix_hash: str,
) -> dict[str, Any]:
    """Build the feature-sufficient ledger row (a_r/q_r + identity + content hashes).

    ``sufficient`` is ``features.feature_sufficient_stats`` output: ``a`` is the
    p-vector ``a_r = M^-1 ΣY`` and ``q`` is the scalar ``q_r = M^-1 Σ‖Y‖²``
    (SAP §5 / baseline §11).  ``a_r`` is stored as a list of floats; the wire
    schema encodes it as an f64 array.
    """
    feature_kind = "bpi" if feature_id.startswith("BPI") else "moments"
    data_generation_id = ctx["data_generation_id"]
    feature_generation_id = ctx.get("feature_generation_id", {}).get(feature_kind)
    a = sufficient["a"]
    if hasattr(a, "tolist"):
        a = a.tolist()
    return {
        "row_type": "feature_sufficient",
        "schema_version": 1,
        "project_id": ctx["project_id"],
        "protocol_id": ctx["protocol_id"],
        "freeze_id": ctx["freeze_id"],
        "evidence_generation_id": ctx["evidence_generation_id"],
        "data_generation_id": data_generation_id,
        "feature_generation_id": feature_generation_id,
        "feature_id": feature_id,
        "feature_config_hash": feature_config_hash,
        "feature_sufficient_id": cell_identity["feature_sufficient_id"],
        "data_unit_id": cell_identity["data_unit_id"],
        "logical_data_key": cell_identity["logical_data_key"],
        "logical_feature_key": cell_identity["logical_feature_key"],
        "data_content_hash": content.get("data_content_hash"),
        "feature_matrix_hash": feature_matrix_hash,
        "a_r": a,
        "q_r": float(sufficient["q"]),
    }


__all__ = [
    "build_feature_sufficient_row",
    "build_formal_row",
    "load_feature_schema",
    "load_row_schema",
]
