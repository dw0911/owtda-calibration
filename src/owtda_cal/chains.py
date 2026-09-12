"""Append-only hash chains with CAS appends (Plan §2.3, §16.2).

Chains are JSONL files whose every line is a canonical JSON event carrying its
own event hash; the chain tip is the hash of the last event.  ``append_cas``
verifies the expected tip under an exclusive lock file, appends one event with
fsync, and returns the new tip.  Genesis values are domain-separated ``H()``
objects.
"""

from __future__ import annotations

import hashlib
import json
import os

from .canonical import canonical_json_bytes
from .kernel_lock import kernel_lock, lock_path_for

GENESIS_KINDS = {
    "phase_state_genesis",
    "validity_genesis",
    "real_disposition_genesis",
}


class ChainError(ValueError):
    """Chain/CAS contract violation."""


def genesis(kind: str, **fields) -> str:
    from .identity import H

    if kind not in GENESIS_KINDS:
        raise ChainError(f"unknown genesis kind {kind!r}")
    return H(kind, **fields)


def event_hash(event_without_hash: dict) -> str:
    return hashlib.sha256(canonical_json_bytes(event_without_hash) + b"\n").hexdigest()


def _lock_path(path: str) -> str:
    """Persistent, OS-managed lock file for a chain (task pack §2.2).

    Replaces the deleted-on-exit ``<path>.lock`` sentinel: a process killed while
    holding the old sentinel blocked every later writer forever.
    """
    return lock_path_for(path)


def read_last_event(path: str) -> tuple[dict | None, int]:
    """Return ``(last event, event count)``; recomputes nothing."""
    if not os.path.exists(path):
        return None, 0
    last = None
    count = 0
    with open(path, "r", encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if line:
                last = json.loads(line)
                count += 1
    return last, count


def read_tip(path: str, *, hash_field: str) -> str | None:
    if not os.path.exists(path):
        return None
    tip = None
    with open(path, "r", encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if line:
                tip = json.loads(line)[hash_field]
    return tip


def append_cas(
    path: str,
    event_without_hash: dict,
    *,
    expected_tip: str | None,
    hash_field: str,
    timeout: float = 30.0,
    verify_tail: bool = True,
) -> str:
    """CAS-append one event; returns the new tip (the event hash).

    ``verify_tail`` recomputes the hash of the event that is already on disk
    before appending.  Re-audit 2026-09-13: an existing event whose *content*
    was edited while its stored hash was kept let the append path continue on a
    chain that no longer authenticated.  The check is O(1) -- a full history
    verification is available through :func:`assert_chain_valid` for seal time.
    """
    if hash_field in event_without_hash:
        raise ChainError(f"event must not pre-contain {hash_field!r}")
    with kernel_lock(_lock_path(path), scope="registry", timeout=timeout):
        last, _count = read_last_event(path)
        current = last[hash_field] if last is not None else None
        if verify_tail and last is not None:
            stored = last[hash_field]
            recomputed = event_hash({k: v for k, v in last.items() if k != hash_field})
            if stored != recomputed:
                raise ChainError(
                    "CHAIN_TAIL_TAMPERED: the last event's content does not "
                    f"recompute to its stored {hash_field!r}"
                )
        if current != expected_tip:
            raise ChainError(f"CAS failed: tip {current!r} != expected {expected_tip!r}")
        h = event_hash(event_without_hash)
        stored = dict(event_without_hash)
        stored[hash_field] = h
        line = canonical_json_bytes(stored) + b"\n"
        with open(path, "ab") as fh:
            fh.write(line)
            fh.flush()
            os.fsync(fh.fileno())
    return h


def verify_chain(
    path: str,
    *,
    hash_field: str,
    parent_field: str | None = None,
) -> list[str]:
    """Recompute the whole chain; return a list of human-readable problems.

    Every event hash is recomputed from the stored content, so an event whose
    content was edited while its hash was kept is detected.  When
    ``parent_field`` is given (schema 2 event streams) the declared parent of
    each event must be the previous event's hash, which is what makes a
    "rewritten middle with the old tail" detectable at all.
    """
    issues: list[str] = []
    if not os.path.exists(path):
        return issues
    previous: str | None = None
    with open(path, "r", encoding="utf-8") as fh:
        for lineno, line in enumerate(fh, start=1):
            line = line.strip()
            if not line:
                continue
            event = json.loads(line)
            stored = event.get(hash_field)
            recomputed = event_hash({k: v for k, v in event.items() if k != hash_field})
            if stored != recomputed:
                issues.append(f"line {lineno}: {hash_field} does not recompute from content")
            if parent_field is not None:
                if parent_field not in event:
                    issues.append(f"line {lineno}: missing {parent_field!r} (schema 2 parent link)")
                elif event[parent_field] != previous:
                    issues.append(
                        f"line {lineno}: {parent_field}={event[parent_field]!r} "
                        f"!= previous event hash {previous!r}"
                    )
            previous = stored
    return issues


def assert_chain_valid(
    path: str,
    *,
    hash_field: str,
    parent_field: str | None = None,
) -> None:
    """Raise :class:`ChainError` unless the whole chain authenticates."""
    issues = verify_chain(path, hash_field=hash_field, parent_field=parent_field)
    if issues:
        raise ChainError("chain verification failed: " + "; ".join(issues))


def phase_state_event(
    *,
    project_id: str,
    protocol_id: str,
    freeze_id: str,
    evidence_generation_id: str,
    phase: str,
    expected_parent_phase_seal_hash: str | None,
    expected_validity_registry_head_hash: str,
    new_active_revision_id: str,
    new_phase_seal_hash: str,
    prev_phase_state_event_hash: str | None,
) -> dict:
    return {
        "schema_version": 1,
        "event_type": "PHASE_ACTIVATED",
        "project_id": project_id,
        "protocol_id": protocol_id,
        "freeze_id": freeze_id,
        "evidence_generation_id": evidence_generation_id,
        "phase": phase,
        "expected_parent_phase_seal_hash": expected_parent_phase_seal_hash,
        "expected_validity_registry_head_hash": expected_validity_registry_head_hash,
        "new_active_revision_id": new_active_revision_id,
        "new_phase_seal_hash": new_phase_seal_hash,
        "prev_phase_state_event_hash": prev_phase_state_event_hash,
    }


def validity_event(
    *,
    project_id: str,
    protocol_id: str,
    freeze_id: str,
    evidence_generation_id: str,
    phase: str,
    logical_kind: str,
    logical_key: str,
    expected_current_concrete_id: str,
    expected_current_source_run_seal_hash: str,
    reason_code: str,
    reason_object_hash: str,
    prev_event_hash: str | None,
) -> dict:
    if logical_kind not in ("DATA", "FEATURE", "EVALUATION"):
        raise ChainError(f"bad logical_kind {logical_kind!r}")
    return {
        "schema_version": 1,
        "event_type": "INVALIDATE",
        "project_id": project_id,
        "protocol_id": protocol_id,
        "freeze_id": freeze_id,
        "evidence_generation_id": evidence_generation_id,
        "phase": phase,
        "logical_kind": logical_kind,
        "logical_key": logical_key,
        "expected_current_concrete_id": expected_current_concrete_id,
        "expected_current_source_run_seal_hash": expected_current_source_run_seal_hash,
        "reason_code": reason_code,
        "reason_object_hash": reason_object_hash,
        "prev_event_hash": prev_event_hash,
    }


__all__ = [
    "GENESIS_KINDS",
    "ChainError",
    "genesis",
    "event_hash",
    "read_tip",
    "read_last_event",
    "append_cas",
    "verify_chain",
    "assert_chain_valid",
    "phase_state_event",
    "validity_event",
]
