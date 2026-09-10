"""REAL_DISPOSITION append-only chain (Plan §2.3, §16.2).

The chain records why the REAL line is omitted or deferred.  Genesis is the
domain-separated hash ``H("real_disposition_genesis", ...)``; every event
carries its own ``disposition_hash = SHA256(canonical_json(event_without_hash)
+ b"\\n")`` and points at the previous event hash, so the tip is a CAS target.

Validation rejects: hash mismatch, broken/forked/cyclic linkage, a first event
whose parent is not the recomputed genesis, unknown status/stage/reason codes,
and illegal field combinations (``REAL_DEFERRED`` must bind a task-index seal
with ``truth_unsealed=false``).
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from . import chains

DISPOSITION_STATUSES = ("REAL_OMITTED_BY_DATA_GATE", "REAL_DEFERRED")
DISPOSITION_STAGES = (
    "REAL_DATA_STAGED",
    "REAL_DATA_FROZEN",
    "REAL_TASKS_FROZEN",
    "REAL_PREDICTION_ADMISSION",
    "REAL_PREDICTION_RUNNING",
)
REASON_CODES = (
    "TASK_GATE_MIN_TASKS_NOT_MET",
    "TASK_GATE_MIN_SUBJECTS_NOT_MET",
    "DATA_GATE_TIMEBASE_FAIL",
    "COMPUTE_SCHEDULE_GATE_FAIL",
)

EVENT_FIELDS = frozenset(
    {
        "schema_version",
        "event_type",
        "project_id",
        "protocol_id",
        "freeze_id",
        "evidence_generation_id",
        "disposition_status",
        "disposition_stage",
        "reason_code",
        "reason_object_hash",
        "task_index_seal_hash",
        "truth_unsealed",
        "prev_real_disposition_event_hash",
    }
)


class DispositionError(ValueError):
    """REAL_DISPOSITION contract violation."""


def genesis_hash(
    *, project_id: str, protocol_id: str, freeze_id: str, evidence_generation_id: str
) -> str:
    return chains.genesis(
        "real_disposition_genesis",
        project_id=project_id,
        protocol_id=protocol_id,
        freeze_id=freeze_id,
        evidence_generation_id=evidence_generation_id,
    )


def reason_object(
    *,
    reason_code: str,
    admitted_subjects: int,
    min_subjects_required: int,
    eligible_tasks: int,
    min_tasks_required: int,
    subjects_without_candidate: list[str],
    dataset_hash: str,
    task_builder_config_hash: str,
    thresholds_unchanged: bool = True,
) -> dict[str, Any]:
    """Strict machine object referenced by ``reason_object_hash``."""
    if reason_code not in REASON_CODES:
        raise DispositionError(f"unknown reason_code {reason_code!r}")
    return {
        "schema_version": 1,
        "kind": "real_disposition_reason",
        "reason_code": reason_code,
        "gate": {
            "admitted_subjects": admitted_subjects,
            "min_subjects_required": min_subjects_required,
            "eligible_tasks": eligible_tasks,
            "min_tasks_required": min_tasks_required,
            "every_admitted_subject_has_task": not subjects_without_candidate,
            "pass": bool(
                admitted_subjects >= min_subjects_required
                and eligible_tasks >= min_tasks_required
                and not subjects_without_candidate
            ),
        },
        "subjects_without_candidate": sorted(subjects_without_candidate),
        "dataset_hash": dataset_hash,
        "task_builder_config_hash": task_builder_config_hash,
        "thresholds_unchanged": thresholds_unchanged,
    }


def reason_object_hash(reason: dict[str, Any]) -> str:
    return chains.event_hash(reason)


def event(
    *,
    project_id: str,
    protocol_id: str,
    freeze_id: str,
    evidence_generation_id: str,
    disposition_status: str,
    disposition_stage: str,
    reason_code: str,
    reason_object_hash_value: str,
    task_index_seal_hash: str | None,
    truth_unsealed: bool,
    prev_real_disposition_event_hash: str,
) -> dict[str, Any]:
    """Build a REAL_DISPOSITION event payload (without ``disposition_hash``)."""
    if disposition_status not in DISPOSITION_STATUSES:
        raise DispositionError(f"unknown disposition_status {disposition_status!r}")
    if disposition_stage not in DISPOSITION_STAGES:
        raise DispositionError(f"unknown disposition_stage {disposition_stage!r}")
    if reason_code not in REASON_CODES:
        raise DispositionError(f"unknown reason_code {reason_code!r}")
    if not isinstance(truth_unsealed, bool):
        raise DispositionError("truth_unsealed must be a bool")
    if disposition_status == "REAL_DEFERRED" and task_index_seal_hash is None:
        raise DispositionError("REAL_DEFERRED must bind a task_index_seal_hash")
    if disposition_status == "REAL_DEFERRED" and truth_unsealed:
        raise DispositionError("REAL_DEFERRED requires truth_unsealed=false")
    if disposition_status == "REAL_OMITTED_BY_DATA_GATE" and truth_unsealed:
        raise DispositionError("REAL_OMITTED_BY_DATA_GATE requires truth_unsealed=false")
    return {
        "schema_version": 1,
        "event_type": "REAL_DISPOSITION",
        "project_id": project_id,
        "protocol_id": protocol_id,
        "freeze_id": freeze_id,
        "evidence_generation_id": evidence_generation_id,
        "disposition_status": disposition_status,
        "disposition_stage": disposition_stage,
        "reason_code": reason_code,
        "reason_object_hash": reason_object_hash_value,
        "task_index_seal_hash": task_index_seal_hash,
        "truth_unsealed": truth_unsealed,
        "prev_real_disposition_event_hash": prev_real_disposition_event_hash,
    }


def read_events(path: str | Path) -> list[dict[str, Any]]:
    p = Path(path)
    if not p.exists():
        return []
    return [json.loads(line) for line in p.read_text(encoding="utf-8").splitlines() if line.strip()]


def validate_chain(path: str | Path) -> dict[str, Any]:
    """Replay the chain; raise on any structural or semantic violation."""
    events = read_events(path)
    if not events:
        raise DispositionError(f"empty REAL_DISPOSITION chain: {path}")
    prev_expected: str | None = None
    for index, ev in enumerate(events):
        stored_hash = ev.get("disposition_hash")
        if not isinstance(stored_hash, str) or len(stored_hash) != 64:
            raise DispositionError(f"event {index}: missing/invalid disposition_hash")
        payload = {k: v for k, v in ev.items() if k != "disposition_hash"}
        if set(payload) != EVENT_FIELDS:
            raise DispositionError(
                f"event {index}: field mismatch {sorted(set(payload) ^ EVENT_FIELDS)}"
            )
        if chains.event_hash(payload) != stored_hash:
            raise DispositionError(f"event {index}: disposition_hash does not replay")
        if ev["disposition_status"] not in DISPOSITION_STATUSES:
            raise DispositionError(f"event {index}: bad status")
        if ev["disposition_stage"] not in DISPOSITION_STAGES:
            raise DispositionError(f"event {index}: bad stage")
        if ev["reason_code"] not in REASON_CODES:
            raise DispositionError(f"event {index}: bad reason_code")
        if ev["disposition_status"] == "REAL_DEFERRED":
            if ev["task_index_seal_hash"] is None:
                raise DispositionError(f"event {index}: DEFERRED without task-index seal")
            if ev["truth_unsealed"] is not False:
                raise DispositionError(f"event {index}: DEFERRED with truth_unsealed")
        if index == 0:
            expected_genesis = genesis_hash(
                project_id=ev["project_id"],
                protocol_id=ev["protocol_id"],
                freeze_id=ev["freeze_id"],
                evidence_generation_id=ev["evidence_generation_id"],
            )
            if ev["prev_real_disposition_event_hash"] != expected_genesis:
                raise DispositionError("event 0: parent is not the recomputed genesis")
        elif ev["prev_real_disposition_event_hash"] != prev_expected:
            raise DispositionError(f"event {index}: broken/forked linkage")
        prev_expected = stored_hash
    return {
        "tip_hash": prev_expected,
        "event_count": len(events),
        "latest_status": events[-1]["disposition_status"],
        "latest_stage": events[-1]["disposition_stage"],
        "truth_unsealed": events[-1]["truth_unsealed"],
        "reason_object_hash": events[-1]["reason_object_hash"],
    }


__all__ = [
    "DISPOSITION_STATUSES",
    "DISPOSITION_STAGES",
    "REASON_CODES",
    "EVENT_FIELDS",
    "DispositionError",
    "genesis_hash",
    "reason_object",
    "reason_object_hash",
    "event",
    "read_events",
    "validate_chain",
]
