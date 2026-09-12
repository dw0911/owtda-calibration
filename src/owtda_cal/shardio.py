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
from .chains import ChainError, append_cas, assert_chain_valid, read_last_event, read_tip
from .kernel_lock import kernel_lock, lock_path_for

COMMIT_EVENT = "SHARD_COMMITTED"
ATTEMPT_EVENT = "ATTEMPT_ALLOCATED"
_HASH_FIELD = "shard_commit_hash"
_ATTEMPT_HASH_FIELD = "attempt_id"

#: schema 2: new shard/attempt events carry a sequence number and the hash of the
#: event they follow.  Sealed schema 1 streams are left exactly as they are.
EVENT_SCHEMA_VERSION = 2
_PARENT_FIELD = "prev_event_hash"

_SHARD_LOCK_SUFFIX = ".shardlock"
_ZERO64 = "0" * 64


class ShardError(ValueError):
    """Shard/attempt contract violation."""


def _sha256_bytes(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


def _shard_lock_path(run_dir: str, shard_id: str) -> str:
    """The one lock guarding every commit/repair of ``shard_id`` (§5.1).

    Both the commit path and the repair path take this lock, so a repair can
    never observe (or append to) a half-finished commit.  The registry CAS
    inside ``append_cas`` takes the second lock, in the fixed order.
    """
    return lock_path_for(os.path.join(run_dir, f"{shard_id}"), suffix=_SHARD_LOCK_SUFFIX)


def _event_payload(*, event_type: str, fields: dict, prev_event_hash: str | None, seq: int) -> dict:
    """schema 2 event: explicit parent link, so a spliced event cannot hide."""
    return {
        "schema_version": EVENT_SCHEMA_VERSION,
        "seq": seq,
        _PARENT_FIELD: prev_event_hash,
        "event_type": event_type,
        **fields,
    }


def _next_seq(registry_path: str) -> int:
    _last, count = read_last_event(registry_path)
    return count


def _assert_declared_payload_hash(manifest: dict, name: str, actual_bytes: bytes) -> None:
    """A manifest must *declare* the payload hash, and it must be the real one.

    Re-audit 2026-09-13: ``repair_orphan`` only compared the caller's bytes with
    the files on disk, so an all-zero or wrong declared hash was accepted.
    """
    entry = manifest.get(name)
    if not isinstance(entry, dict) or "scientific_hash" not in entry:
        raise ShardError(
            f"MANIFEST_PAYLOAD_HASH_MISSING: {name} declares no scientific_hash"
        )
    declared = entry["scientific_hash"]
    if not isinstance(declared, str) or declared == _ZERO64:
        raise ShardError(
            f"MANIFEST_PAYLOAD_HASH_INVALID: {name} scientific_hash is not a real hash"
        )
    actual = _sha256_bytes(actual_bytes)
    if declared != actual:
        raise ShardError(
            f"MANIFEST_PAYLOAD_HASH_MISMATCH: {name} declares {declared[:16]}... "
            f"but the file hashes to {actual[:16]}..."
        )


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


#: The three files a committed shard consists of, in comparison order.
COMMITTED_FILES = (
    "shard_manifest.json",
    "evaluation.scientific.jsonl",
    "feature.scientific.jsonl",
)


def assert_committed_bytes_match(
    final_dir: str,
    *,
    commit_record: dict,
    requested_manifest_bytes: bytes,
    requested_evaluation_bytes: bytes,
    requested_feature_bytes: bytes,
) -> None:
    """Fail closed unless the committed shard is byte-identical to the request.

    Audit A04: "already committed" must never mask "the content differs".  Every
    committed file is re-read from disk, the registry manifest hash is recomputed,
    and the plan hash is compared, so a tampered file, a missing file, a changed
    plan hash or a conflicting payload all block.
    """
    checks = (
        (COMMITTED_FILES[0], requested_manifest_bytes),
        (COMMITTED_FILES[1], requested_evaluation_bytes),
        (COMMITTED_FILES[2], requested_feature_bytes),
    )
    for name, expected in checks:
        path = os.path.join(final_dir, name)
        if not os.path.isfile(path):
            raise ShardError(f"MISSING_COMMITTED_FILE: {name} absent from {final_dir}")
        with open(path, "rb") as fh:
            got = fh.read()
        if got != expected:
            raise ShardError(
                f"COMMIT_CONTENT_CONFLICT: {name} differs from the requested bytes"
            )
    if commit_record.get("shard_manifest_hash") != _sha256_bytes(requested_manifest_bytes):
        raise ShardError(
            "COMMIT_CONTENT_CONFLICT: registry manifest hash differs from the request"
        )
    requested_plan = json.loads(requested_manifest_bytes.decode("utf-8"))["shard_plan_hash"]
    if commit_record.get("shard_plan_hash") != requested_plan:
        raise ShardError(
            "COMMIT_CONTENT_CONFLICT: shard_plan_hash differs from the committed record"
        )


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
    lock_timeout: float = 60.0,
) -> dict:
    """Write/commit one shard; returns the SHARD_COMMITTED record.

    Idempotency means *the same request repeated has one effect* (audit A04).  The
    requested bytes are therefore materialised first and compared against what is
    already committed before a re-commit is accepted.

    The whole "look at the state, write the payload, register the commit"
    sequence runs under one per-shard OS lock (task pack §5.1), so a concurrent
    repair or a second committer cannot interleave with it.
    """
    run_dir = os.path.join(run_root, run_instance_id)
    os.makedirs(run_dir, exist_ok=True)
    final = os.path.join(run_dir, f"{shard_id}.final")
    staging = os.path.join(run_dir, f"{shard_id}.tmp")

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
    manifest_hash = _sha256_bytes(manifest_bytes)

    with kernel_lock(
        _shard_lock_path(run_dir, shard_id), scope="shard", timeout=lock_timeout
    ):
        existing = find_commit(registry_path, run_instance_id=run_instance_id, shard_id=shard_id)
        if os.path.exists(final):
            if existing is None:
                raise ShardError("ORPHAN_FINAL: final exists without commit; run repair_orphan")
            assert_committed_bytes_match(
                final,
                commit_record=existing,
                requested_manifest_bytes=manifest_bytes,
                requested_evaluation_bytes=eval_bytes,
                requested_feature_bytes=feat_bytes,
            )
            return existing

        if existing is not None and not os.path.exists(final):
            # Re-audit 2026-09-12: a registry record with the committed directory gone
            # used to fall through to the first-commit path, so repeating the submission
            # with *different* content appended a second, conflicting record.  This is a
            # recovery situation, not an idempotent retry: block and make it explicit.
            raise ShardError(
                f"COMMIT_RECORD_WITHOUT_FINAL: {os.path.basename(final)} is missing while a "
                "SHARD_COMMITTED record exists; rebuild the directory from the record and "
                "verify byte-identity, or void the record explicitly -- do not re-commit"
            )

        if os.path.exists(staging):
            raise ShardError("staging directory already exists; clean it first")
        os.makedirs(staging)

        _write_fsync(os.path.join(staging, "evaluation.scientific.jsonl"), eval_bytes)
        _write_fsync(os.path.join(staging, "feature.scientific.jsonl"), feat_bytes)
        _write_fsync(os.path.join(staging, "shard_manifest.json"), manifest_bytes)
        _fsync_dir(staging)
        os.rename(staging, final)
        _fsync_dir(run_dir)

        # Bounded retry on registry contention (acceptance bench 2026-09-12): several
        # processes committing *different* shards share one chain tip, and a bare CAS
        # would simply fail for the losers.  The snapshot is re-read each round and the
        # identity is re-checked first, so a race can never turn into a duplicate or a
        # conflicting commit.
        for _ in range(16):
            tip = read_tip(registry_path, hash_field=_HASH_FIELD)
            current = find_commit(registry_path, run_instance_id=run_instance_id, shard_id=shard_id)
            if current is not None:
                if current.get("shard_manifest_hash") == manifest_hash:
                    return current  # the same request, committed by a racing caller
                # A racing caller committed *different* content.  Our bytes must not be
                # left where they could masquerade as the committed content: move them
                # aside so the state is the registered "record without final" block, not
                # a silent overwrite.
                if os.path.isdir(final):
                    stray = f"{final}.stray-{os.getpid()}"
                    try:
                        os.rename(final, stray)
                    except OSError:
                        pass
                raise ShardError(
                    "SHARD_CONTENT_CONFLICT: a commit with different content already "
                    "exists; our staged bytes were moved aside, the shard must be voided "
                    "or recomputed from its record, never overwritten"
                )
            payload = _event_payload(
                event_type=COMMIT_EVENT,
                fields={
                    "run_instance_id": run_instance_id,
                    "shard_id": shard_id,
                    "shard_plan_hash": shard_plan_hash,
                    "shard_manifest_hash": manifest_hash,
                },
                prev_event_hash=tip,
                seq=_next_seq(registry_path),
            )
            try:
                commit_hash = append_cas(
                    registry_path, payload, expected_tip=tip, hash_field=_HASH_FIELD
                )
            except ChainError:
                continue
            return {**payload, _HASH_FIELD: commit_hash}
    raise ShardError("commit could not obtain a stable registry snapshot")


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
    expected_shard_plan_hash: str | None = None,
    lock_timeout: float = 60.0,
) -> dict:
    """Recompute an ORPHAN_FINAL shard and append commit iff byte-identical.

    Re-audit 2026-09-13.  The orphan precondition is now checked in full, under
    the same per-shard lock the commit path uses:

    * ``.final`` must exist **and** no ``SHARD_COMMITTED`` record may exist --
      otherwise the call is ``NOT_AN_ORPHAN`` and is refused, because the old
      code appended a *second* commit for an already-committed shard;
    * the manifest inside ``.final`` must declare the run id, the shard id and
      the plan hash the caller claims, and its payload hashes must be real
      (never ``0x00 * 32``) and equal to the hash of the bytes on disk;
    * the registry is verified end-to-end (parent links included) before the
      recovery event is appended, so a recovery can never extend a chain whose
      earlier events no longer authenticate.
    """
    from pathlib import Path

    run_dir = os.path.join(run_root, run_instance_id)
    final = os.path.join(run_dir, f"{shard_id}.final")
    with kernel_lock(
        _shard_lock_path(run_dir, shard_id), scope="shard", timeout=lock_timeout
    ):
        existing = find_commit(registry_path, run_instance_id=run_instance_id, shard_id=shard_id)
        if existing is not None:
            raise ShardError(
                "NOT_AN_ORPHAN: a SHARD_COMMITTED record already exists for this shard; "
                "refusing to append a duplicate recovery commit -- void the existing "
                "record explicitly if it is wrong"
            )
        if not os.path.isdir(final):
            raise ShardError(
                "ORPHAN_PRECONDITION_VIOLATED: repair_orphan requires a .final "
                "directory with no commit; there is nothing to recover"
            )
        os.makedirs(recompute_to, exist_ok=True)

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
        manifest = json.loads(got["shard_manifest.json"].decode("utf-8"))
        if manifest.get("run_instance_id") != run_instance_id:
            raise ShardError(
                f"ORPHAN_IDENTITY_MISMATCH: manifest run_instance_id "
                f"{manifest.get('run_instance_id')!r} != {run_instance_id!r}"
            )
        if manifest.get("shard_id") != shard_id:
            raise ShardError(
                f"ORPHAN_IDENTITY_MISMATCH: manifest shard_id "
                f"{manifest.get('shard_id')!r} != {shard_id!r}"
            )
        declared_plan = manifest.get("shard_plan_hash")
        if expected_shard_plan_hash is not None and declared_plan != expected_shard_plan_hash:
            raise ShardError(
                f"ORPHAN_PLAN_MISMATCH: manifest shard_plan_hash {declared_plan!r} != "
                f"the expected plan {expected_shard_plan_hash!r}"
            )
        if not isinstance(declared_plan, str) or declared_plan == _ZERO64:
            raise ShardError("ORPHAN_PLAN_MISMATCH: manifest declares no real shard_plan_hash")
        _assert_declared_payload_hash(manifest, "evaluation", got["evaluation.scientific.jsonl"])
        _assert_declared_payload_hash(manifest, "feature", got["feature.scientific.jsonl"])

        for name, data in exp.items():
            _write_fsync(os.path.join(recompute_to, name), data)
        if got != exp:
            raise ShardError("ORPHAN_FINAL recomputation mismatch; both copies retained")

        assert_chain_valid(registry_path, hash_field=_HASH_FIELD, parent_field=_PARENT_FIELD)
        manifest_hash = _sha256_bytes(got["shard_manifest.json"])
        payload = _event_payload(
            event_type=COMMIT_EVENT,
            fields={
                "run_instance_id": run_instance_id,
                "shard_id": shard_id,
                "shard_plan_hash": declared_plan,
                "shard_manifest_hash": manifest_hash,
                "recovery": True,
            },
            prev_event_hash=read_tip(registry_path, hash_field=_HASH_FIELD),
            seq=_next_seq(registry_path),
        )
        commit_hash = append_cas(
            registry_path, payload,
            expected_tip=payload[_PARENT_FIELD],
            hash_field=_HASH_FIELD,
        )
        return {**payload, _HASH_FIELD: commit_hash}


def allocate_attempt(registry_path: str, *, run_instance_id: str, evaluation_id: str) -> int:
    """Atomically allocate the next 1-based attempt number for (run, evaluation).

    Re-audit 2026-09-12: the number used to be computed *before* the chain tip was
    read, so two callers could both compute ``n+1`` and both CAS successfully (each
    against a tip the other had already moved past), returning the same number twice.
    The snapshot is now taken first and the CAS is bound to it: any concurrent append
    between the read and the append moves the tip and fails the CAS, which is retried.
    """
    for _ in range(8):
        tip = read_tip(registry_path, hash_field=_ATTEMPT_HASH_FIELD)  # snapshot FIRST
        n = 0
        for rec in _iter_commits(registry_path) or ():
            if (rec.get("run_instance_id") == run_instance_id
                    and rec.get("evaluation_id") == evaluation_id):
                n = max(n, int(rec["attempt_number"]))
        record = _event_payload(
            event_type=ATTEMPT_EVENT,
            fields={
                "run_instance_id": run_instance_id,
                "evaluation_id": evaluation_id,
                "attempt_number": n + 1,
            },
            prev_event_hash=tip,
            seq=_next_seq(registry_path),
        )
        try:
            append_cas(registry_path, record, expected_tip=tip,
                       hash_field=_ATTEMPT_HASH_FIELD)
        except ChainError:
            continue  # the snapshot moved: re-read and recompute, never reuse the number
        return n + 1
    raise ShardError("attempt allocation could not obtain a stable snapshot")


__all__ = [
    "ATTEMPT_EVENT",
    "COMMIT_EVENT",
    "COMMITTED_FILES",
    "EVENT_SCHEMA_VERSION",
    "ShardError",
    "assert_committed_bytes_match",
    "build_shard_manifest",
    "commit_shard",
    "find_commit",
    "repair_orphan",
    "allocate_attempt",
]
