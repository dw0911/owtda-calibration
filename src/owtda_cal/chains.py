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
import time
from contextlib import contextmanager

from .canonical import canonical_json_bytes

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


@contextmanager
def _exclusive_lock(path: str, *, timeout: float = 10.0):
    lock = path + ".lock"
    start = time.monotonic()
    fd = None
    while True:
        try:
            fd = os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
            break
        except FileExistsError:
            if time.monotonic() - start > timeout:
                raise ChainError(f"lock timeout on {lock}")
            time.sleep(0.01)
    try:
        yield
    finally:
        if fd is not None:
            os.close(fd)
        try:
            os.remove(lock)
        except FileNotFoundError:
            pass


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
    timeout: float = 10.0,
) -> str:
    """CAS-append one event; returns the new tip (the event hash)."""
    if hash_field in event_without_hash:
        raise ChainError(f"event must not pre-contain {hash_field!r}")
    with _exclusive_lock(path, timeout=timeout):
        current = read_tip(path, hash_field=hash_field)
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
    "append_cas",
    "phase_state_event",
    "validity_event",
]
