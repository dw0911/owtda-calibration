"""Formal persistence pipeline: expected indexes -> shard plan -> shard commit.

The audit's finding (R5-05): the formal adapter had no real durable commit or
seal -- it only wrote a ledger and stage labels.  This module is the first half
of the real pipeline.  It turns a batch of ``scientific_row`` rows and their
``feature_sufficient_row`` rows into the three expected-index sets (data /
feature / evaluation), builds the strict shard plan, and commits the shard
through ``shardio.commit_shard`` (three files + fsync + atomic rename + CAS
registry).  The run/phase seal (``indexes.build_run_seal`` / ``build_phase_seal``)
is layered on top by the outer supervisor.

A shard is one *batch* (a replicate, or a caller-chosen partition), never a
whole phase written at the end -- the audit forbids "write the whole table at
phase end".
"""

from __future__ import annotations

import hashlib
from typing import Any

from . import indexes, shardio
from .canonical import canonical_json_bytes

_ROW_TYPE_EVALUATION = "EVALUATION"
_ROW_TYPE_FEATURE = "FEATURE_SUFFICIENT"


def build_expected_indexes(
    rows: list[dict[str, Any]],
    feature_rows: list[dict[str, Any]],
) -> dict[str, Any]:
    """The three expected-index sets and their hashes, from produced rows.

    ``rows`` are complete ``scientific_row`` objects and ``feature_rows`` are
    ``feature_sufficient_row`` objects (both already schema-validated).  The
    index sets are the *declared* identity of every produced unit; a later seal
    must quote these hashes so any dropped/duplicated row is detectable.
    """
    # one data-unit entry per produced data unit (an evaluation row appears once
    # per method, so the data index dedups by data_unit_id / logical_data_key)
    data_units: dict[str, dict[str, str]] = {}
    for r in rows:
        data_units[r["data_unit_id"]] = {
            "logical_data_key": r["logical_data_key"],
            "data_unit_id": r["data_unit_id"],
        }
    data_rows = indexes.expected_data_index_rows(data_units.values())
    feature_index = indexes.expected_feature_index_rows(
        {
            "logical_data_key": fr["logical_data_key"],
            "logical_feature_key": fr["logical_feature_key"],
            "data_unit_id": fr["data_unit_id"],
            "feature_sufficient_id": fr["feature_sufficient_id"],
        }
        for fr in feature_rows
    )
    evaluation_index = indexes.expected_evaluation_index_rows(
        {
            "logical_data_key": r["logical_data_key"],
            "logical_feature_key": r["logical_feature_key"],
            "logical_evaluation_key": r["logical_evaluation_key"],
            "data_unit_id": r["data_unit_id"],
            "feature_sufficient_id": r["feature_sufficient_id"],
            "evaluation_id": r["evaluation_id"],
        }
        for r in rows
    )
    indexes.validate_index_consistency(data_rows, feature_index, evaluation_index)
    return {
        "data_rows": data_rows,
        "feature_rows": feature_index,
        "evaluation_rows": evaluation_index,
        "expected_data_index_hash": indexes.index_content_hash(data_rows),
        "expected_index_hash": indexes.index_content_hash(evaluation_index),
        "expected_feature_index_hash": indexes.index_content_hash(feature_index),
    }


def build_shard_plan_from_indexes(
    *,
    run_instance_id: str,
    phase: str,
    expected_data_index_hash: str,
    expected_index_hash: str,
    expected_feature_index_hash: str,
    evaluation_rows: list[dict[str, Any]],
    feature_rows: list[dict[str, Any]],
    partition: str,
) -> dict[str, Any]:
    """A shard plan whose one bucket holds every pre-declared id of the batch.

    This mirrors ``build_single_shard_plan`` but takes the *pre-declared* index
    rows (id-only) instead of the full produced rows, so the shard plan hash can
    be fixed before compute and carried into ``run_identity``.
    """
    entries: list[dict[str, Any]] = []
    for e in evaluation_rows:
        entries.append({
            "row_type": _ROW_TYPE_EVALUATION,
            "row_id": e["evaluation_id"],
            "partition": partition,
            "bucket": 0,
        })
    for f in feature_rows:
        entries.append({
            "row_type": _ROW_TYPE_FEATURE,
            "row_id": f["feature_sufficient_id"],
            "partition": partition,
            "bucket": 0,
        })
    return indexes.build_shard_plan(
        run_instance_id=run_instance_id,
        phase=phase,
        expected_data_index_hash=expected_data_index_hash,
        expected_index_hash=expected_index_hash,
        expected_feature_index_hash=expected_feature_index_hash,
        entries=entries,
    )


def build_single_shard_plan(
    *,
    run_instance_id: str,
    phase: str,
    expected_data_index_hash: str,
    expected_index_hash: str,
    expected_feature_index_hash: str,
    rows: list[dict[str, Any]],
    feature_rows: list[dict[str, Any]],
    partition: str,
) -> dict[str, Any]:
    """A shard plan whose one bucket holds every row of this partition/batch."""
    entries: list[dict[str, Any]] = []
    for r in rows:
        entries.append({
            "row_type": _ROW_TYPE_EVALUATION,
            "row_id": r["evaluation_id"],
            "partition": partition,
            "bucket": 0,
        })
    for fr in feature_rows:
        entries.append({
            "row_type": _ROW_TYPE_FEATURE,
            "row_id": fr["feature_sufficient_id"],
            "partition": partition,
            "bucket": 0,
        })
    return indexes.build_shard_plan(
        run_instance_id=run_instance_id,
        phase=phase,
        expected_data_index_hash=expected_data_index_hash,
        expected_index_hash=expected_index_hash,
        expected_feature_index_hash=expected_feature_index_hash,
        entries=entries,
    )


def commit_formal_shard(
    *,
    run_root: str,
    run_instance_id: str,
    shard_id: str,
    shard_plan_hash: str,
    rows: list[dict[str, Any]],
    feature_rows: list[dict[str, Any]],
    registry_path: str,
    schemas: dict[str, Any],
    feature_schema: Any,
) -> dict[str, Any]:
    """Commit one batch of produced rows as a shard; returns the commit record.

    The evaluation and feature rows are wire-encoded (floats as f64 hex, per the
    frozen schema) and committed through ``shardio.commit_shard``, which writes
    exactly three files and registers a ``SHARD_COMMITTED`` event.  Re-committing
    identical bytes is idempotent; conflicting bytes block.
    """
    eval_bytes, feat_bytes = wire_lines(rows, feature_rows, schemas, feature_schema)
    return shardio.commit_shard(
        run_root=run_root,
        run_instance_id=run_instance_id,
        shard_id=shard_id,
        shard_plan_hash=shard_plan_hash,
        evaluation_lines=eval_bytes.splitlines(keepends=True),
        feature_lines=feat_bytes.splitlines(keepends=True),
        evaluation_meta={"row_type": _ROW_TYPE_EVALUATION, "row_count": len(rows)},
        feature_meta={"row_type": _ROW_TYPE_FEATURE, "row_count": len(feature_rows)},
        registry_path=registry_path,
    )


def wire_lines(
    rows: list[dict[str, Any]],
    feature_rows: list[dict[str, Any]],
    schemas: dict[str, Any],
    feature_schema: Any,
) -> tuple[bytes, bytes]:
    """The wire-encoded ledger bytes for evaluation and feature rows."""
    eval_lines = [
        canonical_json_bytes(
            schemas[(r["DGP_family"], r["scenario_id"], r["feature_id"], r["method_id"])].encode_to_wire(r)
        ) + b"\n"
        for r in rows
    ]
    feat_lines = [
        canonical_json_bytes(feature_schema.encode_to_wire(fr)) + b"\n"
        for fr in feature_rows
    ]
    return b"".join(eval_lines), b"".join(feat_lines)


def build_formal_run_seal(
    *,
    run_instance_id: str,
    run_component_set_hash: str,
    expected_data_index_hash: str,
    expected_index_hash: str,
    expected_feature_index_hash: str,
    shard_plan_hash: str,
    commit_records: list[dict[str, Any]],
    rows: list[dict[str, Any]],
    feature_rows: list[dict[str, Any]],
    schemas: dict[str, Any],
    feature_schema: Any,
) -> dict[str, Any]:
    """Build the strict run seal (``indexes.build_run_seal``) from produced rows.

    Every derived value comes from the actual produced rows and their wire-encoded
    ledgers -- the seal is hashed over real content, never a placeholder.
    """
    data_unit_ids = sorted({r["data_unit_id"] for r in rows})
    evaluation_ids = sorted({r["evaluation_id"] for r in rows})
    feature_ids = sorted({fr["feature_sufficient_id"] for fr in feature_rows})
    eval_ledger, feat_ledger = wire_lines(rows, feature_rows, schemas, feature_schema)
    refs = [
        {
            "shard_id": rec["shard_id"],
            "shard_manifest_hash": rec["shard_manifest_hash"],
            "shard_commit_hash": rec["shard_commit_hash"],
        }
        for rec in commit_records
    ]
    return indexes.build_run_seal(
        run_instance_id=run_instance_id,
        run_component_set_hash=run_component_set_hash,
        expected_data_index_hash=expected_data_index_hash,
        expected_index_hash=expected_index_hash,
        expected_feature_index_hash=expected_feature_index_hash,
        shard_plan_hash=shard_plan_hash,
        ordered_shard_commit_refs=refs,
        produced_data_unit_count=len(data_unit_ids),
        data_unit_id_set_hash=indexes.id_set_hash("data_unit_id_set", data_unit_ids),
        ledger_content_hash=hashlib.sha256(eval_ledger).hexdigest(),
        row_count=len(rows),
        logical_key_count=len({r["logical_evaluation_key"] for r in rows}),
        evaluation_id_set_hash=indexes.id_set_hash("evaluation_id_set", evaluation_ids),
        feature_ledger_content_hash=hashlib.sha256(feat_ledger).hexdigest(),
        feature_row_count=len(feature_rows),
        feature_sufficient_id_set_hash=indexes.id_set_hash(
            "feature_sufficient_id_set", feature_ids
        ),
        feature_empty_by_contract=not feature_rows,
    )


def build_formal_phase_seal(
    *,
    phase: str,
    evidence_generation_id: str,
    scope_design_hash: str,
    run_seal: dict[str, Any],
    run_seal_hash: str,
    validity_registry_head_hash: str,
    parent_phase_seal_hash: str | None = None,
    ordered_upstream_artifact_refs: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Build the strict phase seal from the produced run seal.

    The active ledger/index hashes and the evaluation/feature set hashes come
    straight from the run seal; the replacement key sets are empty on first
    activation (no replacement yet), and the current run seal is the single
    ``ordered_source_run_seal_hash``.  The caller supplies the phase-level
    identities this module does not own: the scope-design hash, the validity
    registry head hash, and any parent/upstream phase seal.
    """
    from .identity import H

    empty_set = lambda kind: H(kind, ids=[])
    return indexes.build_phase_seal(
        phase=phase,
        evidence_generation_id=evidence_generation_id,
        scope_design_hash=scope_design_hash,
        parent_phase_seal_hash=parent_phase_seal_hash,
        validity_registry_head_hash=validity_registry_head_hash,
        data_replacement_key_set_hash=empty_set("data_replacement_key_set"),
        feature_replacement_key_set_hash=empty_set("feature_replacement_key_set"),
        evaluation_replacement_key_set_hash=empty_set("evaluation_replacement_key_set"),
        replacement_source_run_seal_hashes=[],
        active_component_manifest_hash=run_seal["run_component_set_hash"],
        active_data_index_hash=run_seal["expected_data_index_hash"],
        active_feature_index_hash=run_seal["expected_feature_index_hash"],
        active_evaluation_index_hash=run_seal["expected_index_hash"],
        active_ledger_content_hash=run_seal["ledger_content_hash"],
        active_feature_ledger_content_hash=run_seal["feature_ledger_content_hash"],
        active_feature_row_count=run_seal["feature_row_count"],
        logical_key_count=run_seal["logical_key_count"],
        evaluation_id_set_hash=run_seal["evaluation_id_set_hash"],
        feature_sufficient_id_set_hash=run_seal["feature_sufficient_id_set_hash"],
        ordered_source_run_seal_hashes=[run_seal_hash],
        ordered_upstream_artifact_refs=list(ordered_upstream_artifact_refs or []),
    )


__all__ = [
    "build_expected_indexes",
    "build_formal_phase_seal",
    "build_formal_run_seal",
    "build_single_shard_plan",
    "commit_formal_shard",
]
