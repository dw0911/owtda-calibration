"""Expected indexes, shard plan and seal payloads (Plan §15.3-§15.4, §16.2).

Pure builders/validators: no run state is written here.  Index content hashes
are SHA256 over exact uncompressed bytes (UTF-8, canonical JSON, single LF per
line, trailing LF).  Single-object manifests hash
``SHA256(canonical_json(obj_without_own_hash) + b"\\n")``.
"""

from __future__ import annotations

import hashlib
from collections.abc import Iterable

from .canonical import canonical_json_bytes
from .identity import H, ensure_sha256_hex

ROW_TYPE_EVALUATION = "EVALUATION"
ROW_TYPE_FEATURE = "FEATURE_SUFFICIENT"
UPSTREAM_ROLES = {
    "NULL": (),
    "ALT": ("source_null_phase_seal",),
    "REAL_PREDICTION": ("task_index_seal", "ground_truth_commitment"),
    "REAL_EVALUATION": ("prediction_phase_seal", "ground_truth_seal"),
}


class IndexError_(ValueError):
    """Index/shard/seal payload violates the frozen contract."""


def _lines_bytes(lines: Iterable[bytes]) -> bytes:
    return b"".join(lines)


def _canonical_line(obj: dict) -> bytes:
    return canonical_json_bytes(obj) + b"\n"


def _check_64(value: str, what: str) -> None:
    ensure_sha256_hex(value, what=what)


# ---------------------------------------------------------------- expected indexes

def expected_data_index_rows(rows: Iterable[dict]) -> list[dict]:
    """[{logical_data_key, data_unit_id}] sorted, unique on both columns."""
    out = []
    seen_ldk, seen_uid = set(), set()
    for r in rows:
        if set(r) != {"logical_data_key", "data_unit_id"}:
            raise IndexError_(f"expected data row keys: {sorted(r)}")
        _check_64(r["logical_data_key"], "logical_data_key")
        _check_64(r["data_unit_id"], "data_unit_id")
        if r["logical_data_key"] in seen_ldk or r["data_unit_id"] in seen_uid:
            raise IndexError_("duplicate logical_data_key/data_unit_id")
        seen_ldk.add(r["logical_data_key"])
        seen_uid.add(r["data_unit_id"])
        out.append(dict(r))
    out.sort(key=lambda e: e["logical_data_key"])
    return out


def expected_feature_index_rows(rows: Iterable[dict]) -> list[dict]:
    out = []
    seen = set()
    for r in rows:
        expect = {"logical_data_key", "logical_feature_key", "data_unit_id", "feature_sufficient_id"}
        if set(r) != expect:
            raise IndexError_(f"expected feature row keys: {sorted(r)}")
        for k in expect:
            _check_64(r[k], k)
        if r["logical_feature_key"] in seen or r["feature_sufficient_id"] in seen:
            raise IndexError_("duplicate logical_feature_key/feature_sufficient_id")
        seen.add(r["logical_feature_key"])
        seen.add(r["feature_sufficient_id"])
        out.append(dict(r))
    out.sort(key=lambda e: e["logical_feature_key"])
    return out


def expected_evaluation_index_rows(rows: Iterable[dict]) -> list[dict]:
    out = []
    seen = set()
    for r in rows:
        expect = {
            "logical_data_key", "logical_feature_key", "logical_evaluation_key",
            "data_unit_id", "feature_sufficient_id", "evaluation_id",
        }
        if set(r) != expect:
            raise IndexError_(f"expected evaluation row keys: {sorted(r)}")
        for k in expect:
            _check_64(r[k], k)
        if r["logical_evaluation_key"] in seen or r["evaluation_id"] in seen:
            raise IndexError_("duplicate logical_evaluation_key/evaluation_id")
        seen.add(r["logical_evaluation_key"])
        seen.add(r["evaluation_id"])
        out.append(dict(r))
    out.sort(key=lambda e: e["logical_evaluation_key"])
    return out


def index_content_hash(rows: Iterable[dict]) -> str:
    """SHA256 over exact canonical JSONL bytes (trailing LF)."""
    return hashlib.sha256(_lines_bytes(_canonical_line(r) for r in rows)).hexdigest()


def validate_index_consistency(
    data_rows: list[dict], feature_rows: list[dict], evaluation_rows: list[dict]
) -> None:
    """Same logical data/feature must map to the same concrete IDs everywhere."""
    data_map = {r["logical_data_key"]: r["data_unit_id"] for r in data_rows}
    feat_map = {
        r["logical_feature_key"]: (r["logical_data_key"], r["data_unit_id"], r["feature_sufficient_id"])
        for r in feature_rows
    }
    for f in feature_rows:
        if data_map.get(f["logical_data_key"]) != f["data_unit_id"]:
            raise IndexError_("feature row disagrees with data index")
    for e in evaluation_rows:
        if data_map.get(e["logical_data_key"]) != e["data_unit_id"]:
            raise IndexError_("evaluation row disagrees with data index")
        if e["logical_feature_key"] not in feat_map:
            raise IndexError_("evaluation row references unknown feature key")
        _, fuid, fsid = feat_map[e["logical_feature_key"]]
        if fuid != e["data_unit_id"] or fsid != e["feature_sufficient_id"]:
            raise IndexError_("evaluation row disagrees with feature index")


# ------------------------------------------------------------------- shard plan

def shard_id(*, run_instance_id: str, phase: str, partition: str, bucket: int) -> str:
    if not isinstance(bucket, int) or bucket < 0:
        raise IndexError_("bucket must be a non-negative int")
    return H("shard", run_instance_id=run_instance_id, phase=phase,
             partition=partition, bucket=bucket)


def build_shard_plan(
    *,
    run_instance_id: str,
    phase: str,
    expected_data_index_hash: str,
    expected_index_hash: str,
    expected_feature_index_hash: str,
    entries: Iterable[dict],
) -> dict:
    """entries: [{row_type,row_id,partition,bucket}] -> strict sorted object."""
    seen = set()
    normalized = []
    for e in entries:
        if set(e) != {"row_type", "row_id", "partition", "bucket"}:
            raise IndexError_(f"shard entry keys: {sorted(e)}")
        if e["row_type"] not in (ROW_TYPE_EVALUATION, ROW_TYPE_FEATURE):
            raise IndexError_(f"bad row_type {e['row_type']!r}")
        _check_64(e["row_id"], "shard row_id")
        key = (e["row_type"], e["row_id"])
        if key in seen:
            raise IndexError_(f"duplicate shard row {key}")
        seen.add(key)
        sid = shard_id(run_instance_id=run_instance_id, phase=phase,
                       partition=e["partition"], bucket=e["bucket"])
        normalized.append({
            "row_type": e["row_type"], "row_id": e["row_id"],
            "shard_id": sid, "partition": e["partition"], "bucket": e["bucket"],
        })
    normalized.sort(key=lambda e: (e["row_type"], e["row_id"]))
    for h, what in (
        (expected_data_index_hash, "expected_data_index_hash"),
        (expected_index_hash, "expected_index_hash"),
        (expected_feature_index_hash, "expected_feature_index_hash"),
    ):
        _check_64(h, what)
    return {
        "schema_version": 1,
        "run_instance_id": run_instance_id,
        "expected_data_index_hash": expected_data_index_hash,
        "expected_index_hash": expected_index_hash,
        "expected_feature_index_hash": expected_feature_index_hash,
        "entries": normalized,
    }


def shard_plan_hash(plan: dict) -> str:
    return hashlib.sha256(canonical_json_bytes(plan) + b"\n").hexdigest()


# --------------------------------------------------------- run component set

_RCS_FIELDS = {
    "schema_version", "project_id", "protocol_id", "freeze_id",
    "evidence_generation_id", "phase", "scope_design_hash",
    "parent_phase_seal_hash", "binding_authority_phase_seal_hash",
    "run_input_bindings_hash", "run_input_bindings_row_count",
    "run_input_bindings_empty_by_contract", "ordered_upstream_artifact_refs",
    "component_refs", "root_refs", "config_refs", "code_manifest_refs",
    "compute_git_commit", "source_tree_hash", "run_config_manifest_hash",
    "registry_snapshot_hash", "environment_lock_hash",
}


def _validate_refs(refs: Iterable[dict], *, what: str) -> list[dict]:
    out = []
    seen = set()
    for r in refs:
        if set(r) != {"role", "stable_id", "generation_id", "hash"}:
            raise IndexError_(f"{what} ref keys: {sorted(r)}")
        _check_64(r["hash"], f"{what} ref hash")
        key = (r["role"], r["stable_id"], r["generation_id"])
        if key in seen:
            raise IndexError_(f"duplicate {what} ref {key}")
        seen.add(key)
        out.append(dict(r))
    out.sort(key=lambda e: (e["role"], e["stable_id"], e["generation_id"]))
    return out


def validate_run_component_set(obj: dict) -> dict:
    if set(obj) != _RCS_FIELDS:
        raise IndexError_(f"run component set fields: {sorted(set(obj) ^ _RCS_FIELDS)}")
    phase = obj["phase"]
    roles = UPSTREAM_ROLES.get(phase)
    if roles is None:
        raise IndexError_(f"unknown phase {phase!r}")
    upstream = obj["ordered_upstream_artifact_refs"]
    if tuple(r["role"] for r in upstream) != roles:
        raise IndexError_(f"upstream ref roles must be {roles} for {phase}")
    for r in upstream:
        if set(r) != {"role", "hash"}:
            raise IndexError_("upstream ref keys must be role/hash")
        _check_64(r["hash"], "upstream ref hash")
    for name in ("component_refs", "root_refs", "config_refs", "code_manifest_refs"):
        _validate_refs(obj[name], what=name)
    for name in ("scope_design_hash", "run_input_bindings_hash", "source_tree_hash",
                 "run_config_manifest_hash", "registry_snapshot_hash", "environment_lock_hash"):
        _check_64(obj[name], name)
    for name in ("parent_phase_seal_hash", "binding_authority_phase_seal_hash"):
        if obj[name] is not None:
            _check_64(obj[name], name)
    return obj


def run_component_set_hash(obj: dict) -> str:
    validate_run_component_set(obj)
    return hashlib.sha256(canonical_json_bytes(obj) + b"\n").hexdigest()


# --------------------------------------------------------------------- run seal

_RUN_SEAL_FIELDS = {
    "run_instance_id", "run_component_set_hash", "expected_data_index_hash",
    "expected_index_hash", "expected_feature_index_hash", "shard_plan_hash",
    "ordered_shard_commit_refs", "produced_data_unit_count",
    "data_unit_id_set_hash", "ledger_content_hash", "row_count",
    "logical_key_count", "evaluation_id_set_hash", "feature_ledger_content_hash",
    "feature_row_count", "feature_sufficient_id_set_hash",
    "feature_empty_by_contract",
}


def build_run_seal(
    *,
    run_instance_id: str,
    run_component_set_hash: str,
    expected_data_index_hash: str,
    expected_index_hash: str,
    expected_feature_index_hash: str,
    shard_plan_hash: str,
    ordered_shard_commit_refs: Iterable[dict],
    produced_data_unit_count: int,
    data_unit_id_set_hash: str,
    ledger_content_hash: str,
    row_count: int,
    logical_key_count: int,
    evaluation_id_set_hash: str,
    feature_ledger_content_hash: str,
    feature_row_count: int,
    feature_sufficient_id_set_hash: str,
    feature_empty_by_contract: bool,
) -> dict:
    refs = list(ordered_shard_commit_refs)
    seen = set()
    for r in refs:
        if set(r) != {"shard_id", "shard_manifest_hash", "shard_commit_hash"}:
            raise IndexError_("shard commit ref keys")
        for k in ("shard_id", "shard_manifest_hash", "shard_commit_hash"):
            _check_64(r[k], k)
        if r["shard_id"] in seen:
            raise IndexError_("duplicate shard commit ref")
        seen.add(r["shard_id"])
    refs.sort(key=lambda e: e["shard_id"])
    payload = {
        "run_instance_id": run_instance_id,
        "run_component_set_hash": run_component_set_hash,
        "expected_data_index_hash": expected_data_index_hash,
        "expected_index_hash": expected_index_hash,
        "expected_feature_index_hash": expected_feature_index_hash,
        "shard_plan_hash": shard_plan_hash,
        "ordered_shard_commit_refs": refs,
        "produced_data_unit_count": produced_data_unit_count,
        "data_unit_id_set_hash": data_unit_id_set_hash,
        "ledger_content_hash": ledger_content_hash,
        "row_count": row_count,
        "logical_key_count": logical_key_count,
        "evaluation_id_set_hash": evaluation_id_set_hash,
        "feature_ledger_content_hash": feature_ledger_content_hash,
        "feature_row_count": feature_row_count,
        "feature_sufficient_id_set_hash": feature_sufficient_id_set_hash,
        "feature_empty_by_contract": feature_empty_by_contract,
    }
    if set(payload) != _RUN_SEAL_FIELDS:
        raise IndexError_("run seal field mismatch")
    if feature_empty_by_contract and feature_row_count != 0:
        raise IndexError_("empty feature ledger must have zero feature rows")
    for k in ("run_component_set_hash", "expected_data_index_hash", "expected_index_hash",
              "expected_feature_index_hash", "shard_plan_hash", "data_unit_id_set_hash",
              "ledger_content_hash", "evaluation_id_set_hash", "feature_ledger_content_hash",
              "feature_sufficient_id_set_hash"):
        _check_64(payload[k], k)
    return payload


def run_seal_hash(payload: dict) -> str:
    if set(payload) != _RUN_SEAL_FIELDS:
        raise IndexError_("run seal field mismatch")
    return hashlib.sha256(canonical_json_bytes(payload) + b"\n").hexdigest()


# ------------------------------------------------------------------- phase seal

_PHASE_SEAL_FIELDS = {
    "phase", "evidence_generation_id", "scope_design_hash",
    "parent_phase_seal_hash", "validity_registry_head_hash",
    "data_replacement_key_set_hash", "feature_replacement_key_set_hash",
    "evaluation_replacement_key_set_hash", "replacement_source_run_seal_hashes",
    "active_component_manifest_hash", "active_data_index_hash",
    "active_feature_index_hash", "active_evaluation_index_hash",
    "active_ledger_content_hash", "active_feature_ledger_content_hash",
    "active_feature_row_count", "logical_key_count", "evaluation_id_set_hash",
    "feature_sufficient_id_set_hash", "ordered_source_run_seal_hashes",
    "ordered_upstream_artifact_refs",
}


def build_phase_seal(**fields) -> dict:
    if set(fields) != _PHASE_SEAL_FIELDS:
        raise IndexError_(f"phase seal fields: {sorted(set(fields) ^ _PHASE_SEAL_FIELDS)}")
    for name in (
        "scope_design_hash", "validity_registry_head_hash",
        "data_replacement_key_set_hash", "feature_replacement_key_set_hash",
        "evaluation_replacement_key_set_hash", "active_component_manifest_hash",
        "active_data_index_hash", "active_feature_index_hash",
        "active_evaluation_index_hash", "active_ledger_content_hash",
        "active_feature_ledger_content_hash", "evaluation_id_set_hash",
        "feature_sufficient_id_set_hash",
    ):
        _check_64(fields[name], name)
    for name in ("parent_phase_seal_hash",):
        if fields[name] is not None:
            _check_64(fields[name], name)
    for name in ("replacement_source_run_seal_hashes", "ordered_source_run_seal_hashes"):
        vals = list(fields[name])
        for v in vals:
            _check_64(v, name)
        if vals != sorted(set(vals)):
            raise IndexError_(f"{name} must be sorted and unique")
        fields[name] = vals
    return fields


def phase_seal_hash(payload: dict) -> str:
    if set(payload) != _PHASE_SEAL_FIELDS:
        raise IndexError_("phase seal field mismatch")
    return hashlib.sha256(canonical_json_bytes(payload) + b"\n").hexdigest()


def id_set_hash(id_kind: str, ids: Iterable[str]) -> str:
    """Domain-separated ID-set hashes (evaluation/data/feature sets)."""
    if id_kind not in ("data_unit_id_set", "evaluation_id_set", "feature_sufficient_id_set"):
        raise IndexError_(f"unknown id_set kind {id_kind!r}")
    vals = list(ids)
    for v in vals:
        _check_64(v, id_kind)
    return H(id_kind, ids=sorted(set(vals)))


__all__ = [
    "IndexError_",
    "ROW_TYPE_EVALUATION",
    "ROW_TYPE_FEATURE",
    "UPSTREAM_ROLES",
    "expected_data_index_rows",
    "expected_feature_index_rows",
    "expected_evaluation_index_rows",
    "index_content_hash",
    "validate_index_consistency",
    "shard_id",
    "build_shard_plan",
    "shard_plan_hash",
    "validate_run_component_set",
    "run_component_set_hash",
    "build_run_seal",
    "run_seal_hash",
    "build_phase_seal",
    "phase_seal_hash",
    "id_set_hash",
]
