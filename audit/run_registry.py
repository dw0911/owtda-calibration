"""Run/state registry, terminal states and smoke seals (audit P0-6).

Implements the fail-closed evidence the audit demanded:

* ``RUN_REGISTRY.jsonl`` / ``STATE_REGISTRY.jsonl`` are append-only hash chains
  (``chains.append_cas`` CAS semantics); a **missing registry file is an error**,
  never an implied ``open_runs = 0``;
* ``open_runs`` is derived from the latest state per run, and only states in
  :data:`TERMINAL_STATES` count as closed -- line counts are never used as a
  proxy for run state;
* ``SMOKE_SEAL_<PHASE>.json`` binds, for one smoke run: ledger content hash,
  source tree hash, environment lock hash, the **final ``w*``**, the run
  component set, the smoke generation, counts, zero-error/zero-missing-field
  facts and the terminal state.

Creating an empty registry file to pass a check is explicitly rejected:
:func:`latest_states` raises when the registry is absent or has no events.
"""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from owtda_cal import chains
from owtda_cal.canonical import canonical_json_bytes

RUN_REGISTRY_FILE = "RUN_REGISTRY.jsonl"
STATE_REGISTRY_FILE = "STATE_REGISTRY.jsonl"
RUN_EVENT_HASH_FIELD = "run_registry_event_hash"
STATE_EVENT_HASH_FIELD = "state_registry_event_hash"
TERMINAL_STATES = frozenset(
    {"RUN_SEALED", "RUN_FAILED", "RUN_INVALIDATED", "RUN_ABORTED"}
)
OPENING_STATE = "RUN_STARTED"


class RunRegistryError(ValueError):
    """Registry contract violation (fail closed)."""


def utc_now() -> str:
    return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def ledger_content_hash(path: Path) -> str:
    """SHA256 of the raw (uncompressed) ledger bytes."""
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _registry_paths(registry_dir: Path) -> tuple[Path, Path]:
    return registry_dir / RUN_REGISTRY_FILE, registry_dir / STATE_REGISTRY_FILE


def _append(path: Path, event: dict[str, Any], hash_field: str) -> str:
    return chains.append_cas(
        str(path), event, expected_tip=chains.read_tip(str(path), hash_field=hash_field),
        hash_field=hash_field,
    )


def record_start(
    registry_dir: Path,
    *,
    run_id: str,
    phase: str,
    smoke_generation_id: str,
    workers: int,
    replicates_per_cell: int,
    run_component_set_hash: str,
    compute_git_commit: str,
    source_tree_hash: str,
    environment_lock_hash: str,
    workers_used: int,
) -> dict[str, Any]:
    registry_dir.mkdir(parents=True, exist_ok=True)
    run_path, state_path = _registry_paths(registry_dir)
    at = utc_now()
    run_event = {
        "schema_version": 1,
        "event_type": OPENING_STATE,
        "run_id": run_id,
        "phase": phase,
        "smoke_generation_id": smoke_generation_id,
        "workers": workers,
        "replicates_per_cell": replicates_per_cell,
        "run_component_set_hash": run_component_set_hash,
        "compute_git_commit": compute_git_commit,
        "source_tree_hash": source_tree_hash,
        "environment_lock_hash": environment_lock_hash,
        # AM_PARALLELISM_DECOUPLING: the realised parallelism is a per-run record,
        # not a frozen compute identity (the contract lives in COMPUTE_SPEC).
        "workers_used": workers_used,
        "at_utc": at,
        "prev_event_hash": chains.read_tip(str(run_path), hash_field=RUN_EVENT_HASH_FIELD),
    }
    run_hash = _append(run_path, run_event, RUN_EVENT_HASH_FIELD)
    state_event = {
        "schema_version": 1,
        "event_type": OPENING_STATE,
        "run_id": run_id,
        "phase": phase,
        "state": OPENING_STATE,
        "previous_state": None,
        "run_registry_event_hash": run_hash,
        "at_utc": at,
        "prev_event_hash": chains.read_tip(str(state_path), hash_field=STATE_EVENT_HASH_FIELD),
    }
    state_hash = _append(state_path, state_event, STATE_EVENT_HASH_FIELD)
    return {"run_registry_event_hash": run_hash, "state_registry_event_hash": state_hash}


def record_seal(
    registry_dir: Path,
    *,
    run_id: str,
    phase: str,
    seal: dict[str, Any],
) -> dict[str, Any]:
    """Write ``SMOKE_SEAL_<PHASE>.json`` and append the terminal state."""
    registry_dir.mkdir(parents=True, exist_ok=True)
    run_path, state_path = _registry_paths(registry_dir)
    at = utc_now()
    payload = {
        "schema_version": 1,
        "kind": "smoke_seal",
        "phase": phase,
        "run_id": run_id,
        **{k: v for k, v in seal.items() if k not in {"schema_version", "kind"}},
        "sealed_at_utc": at,
    }
    if "smoke_seal_hash" in payload:
        raise RunRegistryError("seal payload must not pre-contain smoke_seal_hash")
    smoke_seal_hash = hashlib.sha256(
        canonical_json_bytes(payload) + b"\n"
    ).hexdigest()
    stamp = at.replace("-", "").replace(":", "")
    stored = {**payload, "seal_id": f"{phase}__{stamp}__{smoke_seal_hash[:8]}",
              "smoke_seal_hash": smoke_seal_hash}
    (registry_dir / f"SMOKE_SEAL_{phase}.json").write_text(
        json.dumps(stored, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    run_event = {
        "schema_version": 1,
        "event_type": "RUN_SEALED",
        "run_id": run_id,
        "phase": phase,
        "smoke_seal_hash": smoke_seal_hash,
        "at_utc": at,
        "prev_event_hash": chains.read_tip(str(run_path), hash_field=RUN_EVENT_HASH_FIELD),
    }
    run_hash = _append(run_path, run_event, RUN_EVENT_HASH_FIELD)
    state_event = {
        "schema_version": 1,
        "event_type": "RUN_SEALED",
        "run_id": run_id,
        "phase": phase,
        "state": "RUN_SEALED",
        "previous_state": OPENING_STATE,
        "smoke_seal_hash": smoke_seal_hash,
        "run_registry_event_hash": run_hash,
        "at_utc": at,
        "prev_event_hash": chains.read_tip(str(state_path), hash_field=STATE_EVENT_HASH_FIELD),
    }
    state_hash = _append(state_path, state_event, STATE_EVENT_HASH_FIELD)
    return {
        "smoke_seal_hash": smoke_seal_hash,
        "seal_file": f"SMOKE_SEAL_{phase}.json",
        "run_registry_event_hash": run_hash,
        "state_registry_event_hash": state_hash,
    }


def latest_states(registry_dir: Path) -> dict[str, str]:
    """Latest state per run id; **fails closed** when the registry is absent."""
    state_path = registry_dir / STATE_REGISTRY_FILE
    if not state_path.exists():
        raise RunRegistryError(f"MISSING_RUN_REGISTRY: {state_path} does not exist")
    latest: dict[str, str] = {}
    events = 0
    for line in state_path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        event = json.loads(line)
        events += 1
        latest[event["run_id"]] = event["state"]
    if events == 0:
        raise RunRegistryError(f"EMPTY_RUN_REGISTRY: {state_path} has no events")
    return latest


def open_runs(registry_dir: Path) -> set[str]:
    """Runs whose latest state is not terminal (never a line count)."""
    return {
        run_id
        for run_id, state in latest_states(registry_dir).items()
        if state not in TERMINAL_STATES
    }


__all__ = [
    "RUN_REGISTRY_FILE",
    "STATE_REGISTRY_FILE",
    "TERMINAL_STATES",
    "RunRegistryError",
    "ledger_content_hash",
    "record_start",
    "record_seal",
    "latest_states",
    "open_runs",
    "utc_now",
]
