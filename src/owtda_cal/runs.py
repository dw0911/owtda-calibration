"""Run-level identity, admission and seal objects (Plan §16.2, §15.3).

* ``RUN_COMPONENT_SET_<hash>.json`` — strict, cycle-free description of one
  phase run's *inputs*: scope design, four ref classes, registry snapshot,
  source tree and environment lock.  It never contains the current/downstream
  run seal, phase seal, run ID, expected/shard IDs, active indexes, paths,
  status or time.
* ``RUN_INPUT_BINDINGS_<hash>.jsonl`` — ordered input rows feeding the run.
* ``EXPECTED_{DATA,FEATURE,}_INDEX_<hash>.jsonl`` — pre-declared concrete IDs.
* ``run_instance_id`` and the ``RUN_SEAL`` payload/hash.

All hashes are the single-object content contract
``SHA256(canonical_json(obj) + b"\\n")``; JSONL hashes are the SHA256 of the
exact bytes (LF-terminated, final line included).
"""

from __future__ import annotations

import hashlib
from collections.abc import Iterable, Sequence
from typing import Any

from . import chains
from .canonical import canonical_json_bytes
from .identity import H, is_sha256_hex

COMPONENT_SET_FIELDS = frozenset(
    {
        "schema_version",
        "project_id",
        "protocol_id",
        "freeze_id",
        "evidence_generation_id",
        "phase",
        "scope_design_hash",
        "parent_phase_seal_hash",
        "binding_authority_phase_seal_hash",
        "run_input_bindings_hash",
        "run_input_bindings_row_count",
        "run_input_bindings_empty_by_contract",
        "ordered_upstream_artifact_refs",
        "component_refs",
        "root_refs",
        "config_refs",
        "code_manifest_refs",
        "compute_git_commit",
        "source_tree_hash",
        "run_config_manifest_hash",
        "registry_snapshot_hash",
        "environment_lock_hash",
    }
)
REF_CLASSES = (
    "ordered_upstream_artifact_refs",
    "component_refs",
    "root_refs",
    "config_refs",
    "code_manifest_refs",
)
REF_FIELDS = frozenset({"role", "stable_id", "generation_id", "hash"})
REF_ORDER = ("role", "stable_id", "generation_id")

DATA_INDEX_FIELDS = ("logical_data_key", "data_unit_id")
FEATURE_INDEX_FIELDS = (
    "logical_data_key",
    "logical_feature_key",
    "data_unit_id",
    "feature_sufficient_id",
)
EVALUATION_INDEX_FIELDS = (
    "logical_data_key",
    "logical_feature_key",
    "logical_evaluation_key",
    "data_unit_id",
    "feature_sufficient_id",
    "evaluation_id",
)
RUN_SEAL_FIELDS = frozenset(
    {
        "run_instance_id",
        "run_component_set_hash",
        "expected_data_index_hash",
        "expected_index_hash",
        "expected_feature_index_hash",
        "shard_plan_hash",
        "ordered_shard_commit_refs",
        "produced_data_unit_count",
        "data_unit_id_set_hash",
        "ledger_content_hash",
        "row_count",
        "logical_key_count",
        "evaluation_id_set_hash",
        "feature_ledger_content_hash",
        "feature_row_count",
        "feature_sufficient_id_set_hash",
        "feature_empty_by_contract",
    }
)
ID_SET_DOMAINS = {
    "data_unit": "data_unit_id_set",
    "evaluation": "evaluation_id_set",
    "feature_sufficient": "feature_sufficient_id_set",
}
INPUT_BINDING_FIELDS = frozenset(
    {"role", "ref_kind", "stable_id", "generation_id", "hash", "source"}
)


class RunError(ValueError):
    """Run identity / admission contract violation."""


def ref(*, role: str, stable_id: str, generation_id: str, hash_value: str) -> dict[str, Any]:
    if not role or not stable_id or not generation_id:
        raise RunError("ref role/stable_id/generation_id must be non-empty")
    if not is_sha256_hex(hash_value):
        raise RunError(f"ref hash must be 64 hex: {hash_value!r}")
    return {
        "role": role,
        "stable_id": stable_id,
        "generation_id": generation_id,
        "hash": hash_value,
    }


def sorted_refs(refs: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
    """Validate and order one ref class by ``(role, stable_id, generation_id)``."""
    materialized = list(refs)
    for item in materialized:
        if set(item) != REF_FIELDS:
            raise RunError(f"ref field mismatch: {sorted(set(item) ^ REF_FIELDS)}")
        if not is_sha256_hex(item["hash"]):
            raise RunError(f"ref hash must be 64 hex: {item['hash']!r}")
    keys = [tuple(item[k] for k in REF_ORDER) for item in materialized]
    if len(set(keys)) != len(keys):
        raise RunError("duplicate ref (role, stable_id, generation_id)")
    # a ref class may hold several roles; the same (role, stable_id) must be
    # single-generation
    pairs = [(item["role"], item["stable_id"]) for item in materialized]
    if len(set(pairs)) != len(pairs):
        raise RunError("multiple generations for the same (role, stable_id)")
    return sorted(materialized, key=lambda item: tuple(item[k] for k in REF_ORDER))


def run_component_set(**fields: Any) -> dict[str, Any]:
    """Build a strict RUN_COMPONENT_SET payload (without its own hash)."""
    if set(fields) != COMPONENT_SET_FIELDS:
        raise RunError(
            f"RUN_COMPONENT_SET field mismatch: {sorted(set(fields) ^ COMPONENT_SET_FIELDS)}"
        )
    payload = dict(fields)
    for name in REF_CLASSES:
        payload[name] = sorted_refs(payload[name])
    for name in (
        "scope_design_hash",
        "run_input_bindings_hash",
        "source_tree_hash",
        "run_config_manifest_hash",
        "registry_snapshot_hash",
        "environment_lock_hash",
    ):
        if not is_sha256_hex(payload[name]):
            raise RunError(f"{name} must be 64 hex")
    for name in ("parent_phase_seal_hash", "binding_authority_phase_seal_hash"):
        value = payload[name]
        if value is not None and not is_sha256_hex(value):
            raise RunError(f"{name} must be null or 64 hex")
    if not isinstance(payload["run_input_bindings_row_count"], int):
        raise RunError("run_input_bindings_row_count must be an int")
    if not isinstance(payload["run_input_bindings_empty_by_contract"], bool):
        raise RunError("run_input_bindings_empty_by_contract must be a bool")
    return payload


def run_component_set_hash(payload: dict[str, Any]) -> str:
    return chains.event_hash(payload)


def input_binding(
    *, role: str, ref_kind: str, stable_id: str, generation_id: str, hash_value: str, source: str
) -> dict[str, Any]:
    if ref_kind not in ("data", "feature", "method", "root", "config", "code", "upstream"):
        raise RunError(f"unknown ref_kind {ref_kind!r}")
    if not is_sha256_hex(hash_value):
        raise RunError("binding hash must be 64 hex")
    if not source:
        raise RunError("binding source must be non-empty")
    return {
        "role": role,
        "ref_kind": ref_kind,
        "stable_id": stable_id,
        "generation_id": generation_id,
        "hash": hash_value,
        "source": source,
    }


def sorted_bindings(rows: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
    materialized = list(rows)
    for row in materialized:
        if set(row) != INPUT_BINDING_FIELDS:
            raise RunError(f"binding field mismatch: {sorted(set(row) ^ INPUT_BINDING_FIELDS)}")
        if not is_sha256_hex(row["hash"]):
            raise RunError("binding hash must be 64 hex")
    keys = [(r["role"], r["stable_id"], r["generation_id"]) for r in materialized]
    if len(set(keys)) != len(keys):
        raise RunError("duplicate input binding key")
    return sorted(materialized, key=lambda r: (r["role"], r["stable_id"], r["generation_id"]))


def jsonl_bytes(rows: Sequence[dict[str, Any]]) -> bytes:
    return b"".join(canonical_json_bytes(row) + b"\n" for row in rows)


def content_hash(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def run_input_bindings(rows: Sequence[dict[str, Any]]) -> tuple[bytes, str, int]:
    """Return (jsonl bytes, content hash, row count) for the binding file."""
    ordered = sorted_bindings(rows)
    data = jsonl_bytes(ordered)
    return data, content_hash(data), len(ordered)


def _index_rows(rows: Sequence[dict[str, Any]], fields: Sequence[str], primary: str) -> list[dict]:
    materialized = [dict(row) for row in rows]
    for row in materialized:
        if set(row) != set(fields):
            raise RunError(f"index row field mismatch: {sorted(set(row) ^ set(fields))}")
        for name, value in row.items():
            if not is_sha256_hex(value):
                raise RunError(f"index field {name} must be 64 hex")
    keys = [row[primary] for row in materialized]
    if len(set(keys)) != len(keys):
        raise RunError(f"duplicate index primary key {primary}")
    return sorted(materialized, key=lambda row: row[primary])


def expected_data_index(rows: Sequence[dict[str, Any]]) -> list[dict[str, Any]]:
    return _index_rows(rows, DATA_INDEX_FIELDS, "logical_data_key")


def expected_feature_index(rows: Sequence[dict[str, Any]]) -> list[dict[str, Any]]:
    return _index_rows(rows, FEATURE_INDEX_FIELDS, "logical_feature_key")


def expected_evaluation_index(rows: Sequence[dict[str, Any]]) -> list[dict[str, Any]]:
    return _index_rows(rows, EVALUATION_INDEX_FIELDS, "logical_evaluation_key")


def assert_index_closure(
    data_rows: Sequence[dict[str, Any]],
    feature_rows: Sequence[dict[str, Any]],
    evaluation_rows: Sequence[dict[str, Any]],
) -> None:
    """The three expected indexes must agree on shared columns (Plan §15.3)."""
    data_by_key = {row["logical_data_key"]: row for row in data_rows}
    feature_by_key = {row["logical_feature_key"]: row for row in feature_rows}
    for row in feature_rows:
        source = data_by_key.get(row["logical_data_key"])
        if source is None:
            raise RunError("feature row references unknown logical_data_key")
        if source["data_unit_id"] != row["data_unit_id"]:
            raise RunError("data_unit_id mismatch between data and feature index")
    for row in evaluation_rows:
        source = feature_by_key.get(row["logical_feature_key"])
        if source is None:
            raise RunError("evaluation row references unknown logical_feature_key")
        if source["data_unit_id"] != row["data_unit_id"]:
            raise RunError("data_unit_id mismatch between feature and evaluation index")
        if source["feature_sufficient_id"] != row["feature_sufficient_id"]:
            raise RunError("feature_sufficient_id mismatch")
        if data_by_key.get(row["logical_data_key"]) is None:
            raise RunError("evaluation row references unknown logical_data_key")


def id_set_hash(kind: str, ids: Iterable[str]) -> str:
    domain = ID_SET_DOMAINS.get(kind)
    if domain is None:
        raise RunError(f"unknown id-set kind {kind!r}")
    items = list(ids)
    for value in items:
        if not is_sha256_hex(value):
            raise RunError(f"id must be 64 hex: {value!r}")
    return H(domain, ids=sorted(set(items)))


def run_instance_id(
    *,
    phase: str,
    evidence_generation_id: str,
    run_component_set_hash: str,
    expected_data_index_hash: str,
    expected_index_hash: str,
    expected_feature_index_hash: str,
    environment_lock_hash: str,
) -> str:
    return H(
        "run_instance",
        phase=phase,
        evidence_generation_id=evidence_generation_id,
        run_component_set_hash=run_component_set_hash,
        expected_data_index_hash=expected_data_index_hash,
        expected_index_hash=expected_index_hash,
        expected_feature_index_hash=expected_feature_index_hash,
        environment_lock_hash=environment_lock_hash,
    )


def run_seal_payload(**fields: Any) -> dict[str, Any]:
    if set(fields) != RUN_SEAL_FIELDS:
        raise RunError(f"RUN_SEAL field mismatch: {sorted(set(fields) ^ RUN_SEAL_FIELDS)}")
    payload = dict(fields)
    for name in (
        "run_instance_id",
        "run_component_set_hash",
        "expected_data_index_hash",
        "expected_index_hash",
        "expected_feature_index_hash",
        "shard_plan_hash",
        "data_unit_id_set_hash",
        "ledger_content_hash",
        "evaluation_id_set_hash",
        "feature_ledger_content_hash",
        "feature_sufficient_id_set_hash",
    ):
        if not is_sha256_hex(payload[name]):
            raise RunError(f"{name} must be 64 hex")
    for name in ("produced_data_unit_count", "row_count", "logical_key_count", "feature_row_count"):
        if not isinstance(payload[name], int) or payload[name] < 0:
            raise RunError(f"{name} must be a non-negative int")
    if not isinstance(payload["feature_empty_by_contract"], bool):
        raise RunError("feature_empty_by_contract must be a bool")
    commits = payload["ordered_shard_commit_refs"]
    shard_ids = [item["shard_id"] for item in commits]
    if len(set(shard_ids)) != len(shard_ids):
        raise RunError("duplicate shard_id in ordered_shard_commit_refs")
    payload["ordered_shard_commit_refs"] = sorted(commits, key=lambda item: item["shard_id"])
    return payload


def run_seal_hash(payload: dict[str, Any]) -> str:
    return chains.event_hash(payload)


__all__ = [
    "COMPONENT_SET_FIELDS",
    "REF_CLASSES",
    "REF_FIELDS",
    "DATA_INDEX_FIELDS",
    "FEATURE_INDEX_FIELDS",
    "EVALUATION_INDEX_FIELDS",
    "RUN_SEAL_FIELDS",
    "ID_SET_DOMAINS",
    "INPUT_BINDING_FIELDS",
    "RunError",
    "ref",
    "sorted_refs",
    "run_component_set",
    "run_component_set_hash",
    "input_binding",
    "sorted_bindings",
    "jsonl_bytes",
    "content_hash",
    "run_input_bindings",
    "expected_data_index",
    "expected_feature_index",
    "expected_evaluation_index",
    "assert_index_closure",
    "id_set_hash",
    "run_instance_id",
    "run_seal_payload",
    "run_seal_hash",
]
