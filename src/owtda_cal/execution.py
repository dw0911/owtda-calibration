"""The shared execution entry: one API for TEST, smoke and formal (task pack §4.1).

``mode`` controls the allowed identity domain and the admission conditions -- it
does **not** switch scientific implementations.  TEST, smoke and formal work all
go through the same plan -> dispatch -> shard -> seal path, so a claim that was
only ever exercised on a metadata fixture cannot masquerade as a verified
production path.

The execution root is the second half of §2.1: one directory per execution,
created exclusively, ``--resume`` only, never ``exist_ok=True`` over live files.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Callable
from pathlib import Path
from typing import Any

from . import chains
from .executor import execute_units

MODES = ("TEST", "SMOKE", "FORMAL_H0", "FORMAL_H1")

EXECUTION_SUBDIRS = (
    "plan", "events", "resources", "staging", "shards", "seals", "analysis", "logs",
)

#: What each mode is allowed to do, and what it must show before it starts.
MODE_CONTRACT: dict[str, dict[str, Any]] = {
    "TEST": {
        "identity_domain": "TEST",
        "max_units": 64,
        "produces_formal_scientific_summary": False,
        "requires": ("test_seed_domain", "test_id_domain"),
    },
    "SMOKE": {
        "identity_domain": "SMOKE",
        "max_units": 4096,
        "produces_formal_scientific_summary": False,
        "forbidden_outputs": ("size", "power", "method_ranking"),
        "requires": ("frozen_engineering_plan", "replicates_32"),
    },
    "FORMAL_H0": {
        "identity_domain": "FORMAL",
        "max_units": None,
        "produces_formal_scientific_summary": True,
        "requires": ("g4_h0_certificate", "expected_indices_bound", "seed_registry_bound"),
    },
    "FORMAL_H1": {
        "identity_domain": "FORMAL",
        "max_units": None,
        "produces_formal_scientific_summary": True,
        "requires": ("null_evidence_dependency", "independent_authorization"),
    },
}

_EVENT_HASH_FIELD = "event_hash"


class ExecutionError(RuntimeError):
    """Execution-root or mode contract violation."""


class ExecutionRoot:
    """``<root>/executions/<execution_id>/{plan,events,resources,...}``."""

    def __init__(self, path: Path, *, execution_id: str, resumed: bool) -> None:
        self.path = path
        self.execution_id = execution_id
        self.resumed = resumed
        for name in EXECUTION_SUBDIRS:
            setattr(self, f"{name}_dir", path / name)

    def as_dict(self) -> dict[str, Any]:
        return {
            "execution_id": self.execution_id,
            "path": str(self.path),
            "resumed": self.resumed,
            "subdirs": {name: str(self.path / name) for name in EXECUTION_SUBDIRS},
        }


def create_execution_root(
    root: str | Path,
    execution_id: str,
    *,
    resume: bool = False,
) -> ExecutionRoot:
    """Create the execution root exclusively, or attach to it with ``resume``.

    Re-audit 2026-09-13 (P3): a new run must never silently reuse an existing
    directory -- that is how an old attempt's debris ended up inside a "new"
    run's evidence.
    """
    if not execution_id or not str(execution_id).strip():
        raise ExecutionError("execution_id must be a non-empty string")
    path = Path(root) / "executions" / execution_id
    if path.exists():
        if not resume:
            raise ExecutionError(
                f"execution root {path} already exists; pass resume=True (the CLI "
                "flag --resume) to attach to it, never exist_ok=True"
            )
        missing = [d for d in EXECUTION_SUBDIRS if not (path / d).is_dir()]
        if missing:
            raise ExecutionError(
                f"cannot resume {path}: missing subdirectories {missing}"
            )
        return ExecutionRoot(path, execution_id=execution_id, resumed=True)
    if resume:
        raise ExecutionError(f"cannot resume {path}: it does not exist")
    for name in EXECUTION_SUBDIRS:
        (path / name).mkdir(parents=True, exist_ok=False)
    return ExecutionRoot(path, execution_id=execution_id, resumed=False)


def check_mode_admission(mode: str, *, plan: dict[str, Any], **evidence: bool) -> dict[str, Any]:
    """Decide whether ``mode`` may start this plan; never raises, always explains."""
    if mode not in MODES:
        raise ExecutionError(f"unknown mode {mode!r}; expected one of {MODES}")
    contract = MODE_CONTRACT[mode]
    units = plan.get("units") or []
    reasons: list[str] = []

    for requirement in contract["requires"]:
        if not evidence.get(requirement):
            reasons.append(f"missing {requirement!r} required by mode {mode}")

    limit = contract["max_units"]
    if limit is not None and len(units) > limit:
        reasons.append(f"plan has {len(units)} units, mode {mode} allows at most {limit}")

    claimed_phase = plan.get("identity_domain")
    if claimed_phase is not None and claimed_phase != contract["identity_domain"]:
        reasons.append(
            f"plan identity domain {claimed_phase!r} != {contract['identity_domain']!r} "
            f"required by mode {mode}"
        )
    for forbidden in contract.get("forbidden_outputs", ()):
        if forbidden in (plan.get("outputs") or []):
            reasons.append(f"mode {mode} must not produce {forbidden!r}")

    return {
        "mode": mode,
        "admitted": not reasons,
        "reasons": reasons,
        "contract": contract,
    }


def _event(fields: dict[str, Any], *, prev: str | None, seq: int) -> dict[str, Any]:
    return {
        "schema_version": 2,
        "seq": seq,
        "prev_event_hash": prev,
        **fields,
    }


def _append_event(path: Path, fields: dict[str, Any]) -> str:
    tip = chains.read_tip(str(path), hash_field=_EVENT_HASH_FIELD)
    _last, count = chains.read_last_event(str(path))
    return chains.append_cas(
        str(path), _event(fields, prev=tip, seq=count),
        expected_tip=tip, hash_field=_EVENT_HASH_FIELD,
    )


def append_execution_event(root: ExecutionRoot, fields: dict[str, Any]) -> str:
    """Append one schema-2 event to an execution root's dispatch chain."""
    return _append_event(root.events_dir / "dispatch.jsonl", fields)


def write_execution_record(root: ExecutionRoot, record: dict[str, Any]) -> Path:
    """Persist the execution record under ``logs/`` (idempotent overwrite)."""
    target = root.logs_dir / "execution.json"
    target.write_text(
        json.dumps(record, ensure_ascii=False, indent=2, sort_keys=True, default=str) + "\n",
        encoding="utf-8",
    )
    return target


def execute_plan(
    plan: dict[str, Any],
    *,
    mode: str,
    submit: Callable[[dict[str, Any], int], Any],
    manifests: dict[str, Any] | None = None,
    evidence_root: str | Path,
    monitor: Any | None = None,
    execution_id: str | None = None,
    resume: bool = False,
    window_size: int = 8,
    poll_interval: float = 0.1,
    **mode_evidence: bool,
) -> dict[str, Any]:
    """Execute a frozen plan through the shared path; return the execution record.

    Every mode lands here: the frozen plan is written once, each unit is
    dispatched through the bounded executor, and the dispatch/completion events
    are appended as a schema-2 chain under ``events/``.  Nothing here decides a
    scientific question -- it decides *how work is run and recorded*.
    """
    admission = check_mode_admission(mode, plan=plan, **mode_evidence)
    if not admission["admitted"]:
        return {
            "mode": mode,
            "terminal_state": "REFUSED",
            "admission": admission,
            "execution_root": None,
            "records": [],
            "emitted": [],
        }

    units = list(plan.get("units") or [])
    seen: set[str] = set()
    for index, unit in enumerate(units):
        if not isinstance(unit, dict) or not unit.get("unit_id"):
            raise ExecutionError(f"unit {index} must be a dict with a fixed 'unit_id'")
        if unit["unit_id"] in seen:
            raise ExecutionError(f"duplicate unit_id {unit['unit_id']!r} in the plan")
        seen.add(unit["unit_id"])

    execution_id = execution_id or plan.get("execution_id") or "unidentified-execution"
    root = create_execution_root(evidence_root, execution_id, resume=resume)

    plan_bytes = json.dumps(plan, ensure_ascii=False, sort_keys=True).encode() + b"\n"
    (root.plan_dir / "plan.json").write_bytes(plan_bytes)
    plan_sha256 = hashlib.sha256(plan_bytes).hexdigest()
    (root.plan_dir / "plan.sha256").write_text(plan_sha256 + "\n", encoding="utf-8")
    if manifests is not None:
        manifest_bytes = json.dumps(manifests, ensure_ascii=False, sort_keys=True).encode() + b"\n"
        (root.plan_dir / "manifests.json").write_bytes(manifest_bytes)

    events_path = root.events_dir / "dispatch.jsonl"
    _append_event(events_path, {
        "event_type": "EXECUTION_STARTED", "mode": mode,
        "execution_id": execution_id, "plan_sha256": plan_sha256,
        "units": len(units), "window_size": window_size,
    })

    result = execute_units(
        units, submit=submit, monitor=monitor, window_size=window_size,
        poll_interval=poll_interval,
    )

    failures: list[dict[str, Any]] = []
    for record in result["records"]:
        unit_id = units[record["index"]]["unit_id"]
        _append_event(events_path, {
            "event_type": "UNIT_RECORDED", "execution_id": execution_id,
            "unit_id": unit_id,
            "index": record["index"], "status": record["status"],
            "error_class": record.get("error_class"),
            # Re-audit 2026-09-15: the reason must survive the dispatch.  The
            # first smoke dispatch recorded TASK_EXCEPTION for phase SMOKE_ALT
            # and nothing else -- no message, no traceback, so the failure could
            # not be attributed without re-running the phase.
            "error_detail": record.get("error_detail"),
        })
        if record["status"] != "COMPLETED":
            failure_file = root.logs_dir / f"failure_{record['index']:03d}.txt"
            failure_file.write_text(
                "\n".join([
                    f"unit_id: {unit_id}",
                    f"index: {record['index']}",
                    f"status: {record['status']}",
                    f"error_class: {record.get('error_class')}",
                    f"error_detail: {record.get('error_detail')}",
                    "",
                    record.get("error_traceback") or "(no traceback captured)",
                ]) + "\n",
                encoding="utf-8",
            )
            failures.append({
                "index": record["index"],
                "unit_id": unit_id,
                "status": record["status"],
                "error_class": record.get("error_class"),
                "error_detail": record.get("error_detail"),
                "failure_file": str(failure_file),
            })

    resources_ref = None
    if monitor is not None:
        verdict = monitor.verdict() if hasattr(monitor, "verdict") else None
        raw_path = getattr(monitor, "raw_path", None)
        resources_ref = {
            "raw_path": str(raw_path) if raw_path else None,
            "policy_sha256": getattr(monitor, "policy_sha256", None),
            "verdict": verdict,
        }
        (root.resources_dir / "capacity.json").write_text(
            json.dumps(resources_ref, ensure_ascii=False, indent=2, sort_keys=True,
                       default=str) + "\n",
            encoding="utf-8",
        )

    record_out = {
        "schema_version": 1,
        "kind": "execution_record",
        "mode": mode,
        "execution_id": execution_id,
        "execution_root": root.as_dict(),
        "plan_sha256": plan_sha256,
        "terminal_state": result["terminal_state"],
        "stop_latched": result["stop_latched"],
        "stop_reason": result["stop_reason"],
        "units": len(units),
        "completed": result["completed"],
        "failed": result["failed"],
        "cancelled": result["cancelled"],
        "errors_by_class": result["errors_by_class"],
        # one entry per non-completed unit, with its reason and the file that holds
        # the traceback -- execution.json alone must be enough to attribute a stop
        "failures": failures,
        "resources": resources_ref,
        "produces_formal_scientific_summary":
            MODE_CONTRACT[mode]["produces_formal_scientific_summary"],
    }
    _append_event(events_path, {
        "event_type": "EXECUTION_FINISHED", "execution_id": execution_id,
        "terminal_state": result["terminal_state"],
        "completed": result["completed"], "failed": result["failed"],
        "cancelled": result["cancelled"],
    })
    (root.logs_dir / "execution.json").write_text(
        json.dumps(record_out, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    record_out["emitted_unit_ids"] = [
        units[o["index"]]["unit_id"] for o in result["emitted"]
    ]
    record_out["admission"] = admission
    return record_out


__all__ = [
    "EXECUTION_SUBDIRS",
    "MODES",
    "MODE_CONTRACT",
    "ExecutionError",
    "ExecutionRoot",
    "append_execution_event",
    "check_mode_admission",
    "create_execution_root",
    "execute_plan",
    "write_execution_record",
]
