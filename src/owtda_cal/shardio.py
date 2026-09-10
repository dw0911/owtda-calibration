"""Shard staging/commit, orphan handling and attempts (Plan §15.4).

Writes exactly three files into ``<run_instance_id>/<shard_id>.tmp/``
(evaluation JSONL, feature JSONL, manifest without its own hash), fsyncs, then
atomically renames to ``.final`` and appends a ``SHARD_COMMITTED`` event via
CAS.  Re-committing identical bytes is idempotent; conflicting bytes block.
``ORPHAN_FINAL`` (final exists without commit) is repaired by recomputation
and byte comparison; mismatches keep both copies and block.
"""

from __future__ import annotations

import hashlib
import json
import os
from collections.abc import Iterable

from .canonical import canonical_json_bytes
from .chains import ChainError, append_cas, read_tip

COMMIT_EVENT = "SHARD_COMMITTED"
_HASH_FIELD = "shard_commit_hash"


class ShardError(ValueError):
    """Shard/attempt contract violation."""


def _sha256_bytes(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


def _write_fsync(path: str, data: bytes) -> None:
    with open(path, "wb") as fh:
        fh.write(data)
        fh.flush()
        os.fsync(fh.fileno())


def _fsync_dir(path: str) -> None:
    try:
        fd = os.open(path, os.O_RDONLY)
    except OSError:
        return
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def _jsonl_bytes(lines: Iterable[bytes]) -> bytes:
    out = b"".join(line if line.endswith(b"\n") else line + b"\n" for line in lines)
    return out


def build_shard_manifest(
    *,
    run_instance_id: str,
    shard_id: str,
    shard_plan_hash: str,
    evaluation: dict,
    feature: dict,
) -> dict:
    """Strict manifest object (no self hash)."""
    return {
        "schema_version": 1,
        "run_instance_id": run_instance_id,
        "shard_id": shard_id,
        "shard_plan_hash": shard_plan_hash,
        "evaluation": evaluation,
        "feature": feature,
    }


def commit_shard(
    *,
    run_root: str,
    run_instance_id: str,
    shard_id: str,
    shard_plan_hash: str,
    evaluation_lines: list[bytes],
    feature_lines: list[bytes],
    evaluation_meta: dict,
    feature_meta: dict,
    registry_path: str,
) -> dict:
    """Write/commit one shard; returns the SHARD_COMMITTED record."""
    run_dir = os.path.join(run_root, run_instance_id)
    os.makedirs(run_dir, exist_ok=True)
    final = os.path.join(run_dir, f"{shard_id}.final")
    staging = os.path.join(run_dir, f"{shard_id}.tmp")

    existing = find_commit(registry_path, run_instance_id=run_instance_id, shard_id=shard_id)
    if os.path.exists(final):
        if existing is not None:
            return existing  # idempotent
        raise ShardError("ORPHAN_FINAL: final exists without commit; run repair_orphan")

    if os.path.exists(staging):
        raise ShardError("staging directory already exists; clean it first")
    os.makedirs(staging)

    eval_bytes = _jsonl_bytes(evaluation_lines)
    feat_bytes = _jsonl_bytes(feature_lines)
    evaluation = dict(evaluation_meta)
    evaluation["scientific_hash"] = _sha256_bytes(eval_bytes)
    feature = dict(feature_meta)
    feature["scientific_hash"] = _sha256_bytes(feat_bytes)
    manifest = build_shard_manifest(
        run_instance_id=run_instance_id, shard_id=shard_id,
        shard_plan_hash=shard_plan_hash, evaluation=evaluation, feature=feature,
    )
    manifest_bytes = canonical_json_bytes(manifest) + b"\n"

    _write_fsync(os.path.join(staging, "evaluation.scientific.jsonl"), eval_bytes)
    _write_fsync(os.path.join(staging, "feature.scientific.jsonl"), feat_bytes)
    _write_fsync(os.path.join(staging, "shard_manifest.json"), manifest_bytes)
    _fsync_dir(staging)
    os.rename(staging, final)
    _fsync_dir(run_dir)

    manifest_hash = _sha256_bytes(manifest_bytes)
    payload = {
        "schema_version": 1,
        "event_type": COMMIT_EVENT,
        "run_instance_id": run_instance_id,
        "shard_id": shard_id,
        "shard_plan_hash": shard_plan_hash,
        "shard_manifest_hash": manifest_hash,
    }
    commit_hash = append_cas(
        registry_path, payload,
        expected_tip=read_tip(registry_path, hash_field=_HASH_FIELD),
        hash_field=_HASH_FIELD,
    )
    return {**payload, _HASH_FIELD: commit_hash}


def _iter_commits(registry_path: str):
    if not os.path.exists(registry_path):
        return
    with open(registry_path, "r", encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if line:
                yield json.loads(line)


def find_commit(registry_path: str, *, run_instance_id: str, shard_id: str) -> dict | None:
    """Return the unique commit record; conflict/multiplicity blocks."""
    found = [
        c for c in _iter_commits(registry_path)
        if c.get("run_instance_id") == run_instance_id and c.get("shard_id") == shard_id
    ]
    if not found:
        return None
    hashes = {c["shard_manifest_hash"] for c in found}
    if len(hashes) != 1 or len(found) != 1:
        raise ShardError("conflicting or duplicate SHARD_COMMITTED records")
    return found[0]


def repair_orphan(
    *,
    run_root: str,
    run_instance_id: str,
    shard_id: str,
    registry_path: str,
    recompute_to: str,
    expected_manifest_bytes: bytes,
    expected_evaluation_bytes: bytes,
    expected_feature_bytes: bytes,
) -> dict:
    """Recompute an ORPHAN_FINAL shard and append commit iff byte-identical."""
    final = os.path.join(run_root, run_instance_id, f"{shard_id}.final")
    if not os.path.isdir(final):
        raise ShardError("repair_orphan requires an existing .final directory")
    os.makedirs(recompute_to, exist_ok=True)
    from pathlib import Path

    got = {
        "shard_manifest.json": Path(final, "shard_manifest.json").read_bytes(),
        "evaluation.scientific.jsonl": Path(final, "evaluation.scientific.jsonl").read_bytes(),
        "feature.scientific.jsonl": Path(final, "feature.scientific.jsonl").read_bytes(),
    }
    exp = {
        "shard_manifest.json": expected_manifest_bytes,
        "evaluation.scientific.jsonl": expected_evaluation_bytes,
        "feature.scientific.jsonl": expected_feature_bytes,
    }
    for name, data in exp.items():
        _write_fsync(os.path.join(recompute_to, name), data)
    if got != exp:
        raise ShardError("ORPHAN_FINAL recomputation mismatch; both copies retained")
    manifest_hash = _sha256_bytes(got["shard_manifest.json"])
    manifest = json.loads(got["shard_manifest.json"].decode("utf-8"))
    payload = {
        "schema_version": 1,
        "event_type": COMMIT_EVENT,
        "run_instance_id": run_instance_id,
        "shard_id": shard_id,
        "shard_plan_hash": manifest["shard_plan_hash"],
        "shard_manifest_hash": manifest_hash,
    }
    commit_hash = append_cas(
        registry_path, payload,
        expected_tip=read_tip(registry_path, hash_field=_HASH_FIELD),
        hash_field=_HASH_FIELD,
    )
    return {**payload, _HASH_FIELD: commit_hash}


def allocate_attempt(registry_path: str, *, run_instance_id: str, evaluation_id: str) -> int:
    """Atomically allocate the next 1-based attempt number for (run, evaluation)."""
    n = 0
    for rec in _iter_commits(registry_path) or ():
        if rec.get("run_instance_id") == run_instance_id and rec.get("evaluation_id") == evaluation_id:
            n = max(n, int(rec["attempt_number"]))
    record = {
        "schema_version": 1,
        "run_instance_id": run_instance_id,
        "evaluation_id": evaluation_id,
        "attempt_number": n + 1,
    }
    try:
        append_cas(registry_path, record, expected_tip=read_tip(registry_path, hash_field="attempt_id"),
                   hash_field="attempt_id")
    except ChainError as exc:
        raise ShardError(f"attempt allocation CAS failed: {exc}") from exc
    return n + 1


__all__ = [
    "COMMIT_EVENT",
    "ShardError",
    "build_shard_manifest",
    "commit_shard",
    "find_commit",
    "repair_orphan",
    "allocate_attempt",
]
