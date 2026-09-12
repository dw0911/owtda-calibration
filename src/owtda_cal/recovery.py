"""Tail recovery and run reconciliation (task pack §5.1-§5.2).

A crash between "the event bytes were appended" and "the append returned" leaves a
registry whose last line is a *partial* event.  The previous instruction was to
re-run and hope; the joint fix requires an explicit, recorded recovery:

* only an **unsealed** log in state ``TEST`` or ``RUN_INTERRUPTED`` may be
  repaired -- a sealed chain is never edited;
* the original bytes, their hash, the failure offset and the reason are saved to
  a read-only recovery artifact **before** anything is rewritten;
* only the trailing incomplete event is removed; a corrupted *complete* event, a
  mid-file error or a broken parent link refuses the repair outright;
* the verified prefix goes to a new file, fsync, atomic replace, original kept;
* a ``TAIL_RECOVERED`` record is appended to a **dedicated** recovery chain (never
  to the scientific chain), because every consumer of the scientific chain is
  built on its own tip -- introducing a new event type there would silently
  change what those consumers verify;
* the run is then reconciled: orphan directories go through strict orphan repair,
  a lost committed payload is reported as such (no new commit is appended), and
  the expected/actual/committed sets are rebuilt so they can be compared with an
  uninterrupted run.
"""

from __future__ import annotations

import hashlib
import json
import os
import tempfile
from pathlib import Path
from typing import Any

from . import chains
from .shardio import COMMITTED_FILES, find_commit

#: States whose logs may be repaired.  Anything sealed is out of scope.
REPAIRABLE_STATES = ("TEST", "RUN_INTERRUPTED")

#: The dedicated event type for recovery bookkeeping (consumers below).
RECOVERY_EVENT_TYPE = "TAIL_RECOVERED"
RECOVERY_ARTIFACT_NAME = "TAIL_RECOVERY.json"
RECOVERY_CHAIN_SUFFIX = ".recovery.jsonl"


class RecoveryError(ValueError):
    """A tail recovery or reconciliation was refused."""


def _sha256(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


def inspect_tail(
    path: str | Path,
    *,
    hash_field: str,
    parent_field: str = "prev_event_hash",
) -> dict[str, Any]:
    """Classify a chain file's tail without changing anything.

    Returns one of ``EMPTY``/``COMPLETE``/``INCOMPLETE_TAIL``/``TAMPERED``/
    ``BROKEN_LINK``/``MIDDLE_ERROR`` with the verified prefix and the offset at
    which the good prefix ends.
    """
    target = Path(path)
    raw = target.read_bytes() if target.exists() else b""
    if not raw:
        return {"status": "EMPTY", "verified_prefix": b"", "tail": b"",
                "offset": 0, "events": 0, "detail": "the file is empty"}
    if not raw.endswith(b"\n"):
        split = raw.rfind(b"\n")
        prefix = raw[:split + 1] if split >= 0 else b""
        tail = raw[split + 1:]
        status_tail = "INCOMPLETE_TAIL"
    else:
        prefix, tail = raw, b""
        status_tail = "COMPLETE"

    previous: str | None = None
    seq = -1
    for number, line in enumerate(prefix.splitlines(), start=0):
        try:
            event = json.loads(line)
        except Exception:  # noqa: BLE001 - a bad line is a finding
            return {"status": "MIDDLE_ERROR", "verified_prefix": prefix, "tail": tail,
                    "offset": len(prefix), "events": number,
                    "detail": f"line {number + 1} is not valid JSON"}
        stored = event.get(hash_field)
        recomputed = chains.event_hash({k: v for k, v in event.items() if k != hash_field})
        if stored != recomputed:
            return {"status": "TAMPERED", "verified_prefix": prefix, "tail": tail,
                    "offset": len(prefix), "events": number,
                    "detail": f"line {number + 1}: {hash_field} does not recompute"}
        if parent_field in event:
            if event[parent_field] != previous:
                return {"status": "BROKEN_LINK", "verified_prefix": prefix, "tail": tail,
                        "offset": len(prefix), "events": number,
                        "detail": f"line {number + 1}: {parent_field} != previous hash"}
        if "seq" in event and isinstance(event["seq"], int) and event["seq"] != seq + 1:
            return {"status": "BROKEN_LINK", "verified_prefix": prefix, "tail": tail,
                    "offset": len(prefix), "events": number,
                    "detail": f"line {number + 1}: seq {event['seq']} != {seq + 1}"}
        if isinstance(event.get("seq"), int):
            seq = event["seq"]
        previous = stored
    return {
        "status": status_tail,
        "verified_prefix": prefix,
        "tail": tail,
        "offset": len(prefix),
        "events": prefix.count(b"\n"),
        "detail": "" if tail == b"" else f"{len(tail)} trailing bytes are not an event",
    }


def _append_recovery_event(path: Path, fields: dict[str, Any]) -> str:
    """The dedicated recovery chain: schema 2, own tip, own consumers."""
    tip = chains.read_tip(str(path), hash_field="event_hash")
    _last, count = chains.read_last_event(str(path))
    payload = {
        "schema_version": 2,
        "seq": count,
        "prev_event_hash": tip,
        "event_type": RECOVERY_EVENT_TYPE,
        **fields,
    }
    return chains.append_cas(str(path), payload, expected_tip=tip, hash_field="event_hash")


def read_recovery_chain(path: str | Path) -> list[dict[str, Any]]:
    """The consumer of the recovery chain (defined before the producer is used)."""
    target = Path(path)
    if not target.exists():
        return []
    return [
        json.loads(line)
        for line in target.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def repair_incomplete_tail(
    *,
    registry_path: str | Path,
    recovery_dir: str | Path,
    hash_field: str,
    log_state: str,
    reason: str,
    sealed: bool = False,
    parent_field: str = "prev_event_hash",
    lock_timeout: float = 60.0,
) -> dict[str, Any]:
    """Recover a partially written trailing event, explicitly and reversibly."""
    from .kernel_lock import kernel_lock, lock_path_for

    target = Path(registry_path)
    if sealed:
        raise RecoveryError("SEALED_CHAIN_REFUSED: a sealed chain is never rewritten")
    if log_state not in REPAIRABLE_STATES:
        raise RecoveryError(
            f"STATE_NOT_REPAIRABLE: {log_state!r} is not one of {REPAIRABLE_STATES}"
        )
    if not reason:
        raise RecoveryError("a recovery reason is required")

    recovery = Path(recovery_dir)
    recovery.mkdir(parents=True, exist_ok=True)
    # the lock guards the *chain file*, but lives in its own persistent file --
    # locking the registry bytes themselves would deny our own reads on Windows
    with kernel_lock(lock_path_for(str(target)), scope="registry", timeout=lock_timeout):
        original = target.read_bytes() if target.exists() else b""
        before_hash = _sha256(original)
        inspection = inspect_tail(target, hash_field=hash_field, parent_field=parent_field)
        status = inspection["status"]
        if status in ("TAMPERED", "BROKEN_LINK", "MIDDLE_ERROR"):
            raise RecoveryError(
                f"{status}_REFUSED: {inspection['detail']} -- a corrupted complete "
                "event, a mid-file error or a broken parent link is not a tail "
                "problem and must not be repaired automatically"
            )
        if status in ("EMPTY", "COMPLETE"):
            return {
                "status": status,
                "repaired": False,
                "before_sha256": before_hash,
                "after_sha256": before_hash,
                "registry_path": str(target),
                "detail": inspection["detail"] or "nothing to recover",
            }

        # 1) preserve the original before touching anything
        original_copy = recovery / f"{target.name}.orig"
        if not original_copy.exists():
            # first recovery wins: the pre-repair bytes are evidence, so they are
            # written once and then made read-only
            original_copy.write_bytes(original)
            os.chmod(original_copy, 0o444)

        # 2) write the verified prefix to a new file, fsync, then replace
        prefix = inspection["verified_prefix"]
        handle, temp_name = tempfile.mkstemp(dir=str(target.parent), suffix=".recover")
        try:
            with os.fdopen(handle, "wb") as fh:
                fh.write(prefix)
                fh.flush()
                os.fsync(fh.fileno())
            os.replace(temp_name, target)
        except BaseException:
            if os.path.exists(temp_name):
                os.unlink(temp_name)
            raise

        after = target.read_bytes()
        after_hash = _sha256(after)
        artifact = {
            "schema_version": 1,
            "kind": "tail_recovery",
            "registry": str(target),
            "reason": reason,
            "log_state": log_state,
            "failure_offset": inspection["offset"],
            "dropped_bytes": len(inspection["tail"]),
            "before_sha256": before_hash,
            "after_sha256": after_hash,
            "original_bytes_sha256": _sha256(original_copy.read_bytes()),
            "original_copy": original_copy.name,
            "events_retained": inspection["events"],
            # A recovered chain's tip differs from the pre-crash tip by
            # construction: any seal taken before the crash is stale.
            "seal_must_be_rederived": True,
        }
        (recovery / RECOVERY_ARTIFACT_NAME).write_text(
            json.dumps(artifact, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        _append_recovery_event(target.with_name(target.name + RECOVERY_CHAIN_SUFFIX), {
            "registry": str(target),
            "reason": reason,
            "failure_offset": inspection["offset"],
            "dropped_bytes": len(inspection["tail"]),
            "before_sha256": before_hash,
            "after_sha256": after_hash,
        })
        return {
            "status": "REPAIRED",
            "repaired": True,
            "before_sha256": before_hash,
            "after_sha256": after_hash,
            "dropped_bytes": len(inspection["tail"]),
            "events_retained": inspection["events"],
            "recovery_artifact": str(recovery / RECOVERY_ARTIFACT_NAME),
            "original_copy": str(original_copy),
            "registry_path": str(target),
            "seal_must_be_rederived": True,
        }


def reconcile_run(
    *,
    run_root: str | Path,
    run_instance_id: str,
    registry_path: str | Path,
) -> dict[str, Any]:
    """Compare the committed directories with the registry, without changing them.

    * a ``.final`` directory with no commit -> strict orphan repair is required;
    * a commit whose directory is missing or whose payload hash no longer matches
      -> reported as ``COMMITTED_CONTENT_LOST`` (recover that commit explicitly,
      never append a new one);
    * the expected/actual/committed id sets and every payload hash are rebuilt so
      the caller can compare them with an uninterrupted run.
    """
    run_dir = Path(run_root) / run_instance_id
    orphans: list[str] = []
    lost: list[dict[str, Any]] = []
    committed_ids: list[str] = []
    payload_hashes: dict[str, str] = {}
    if run_dir.is_dir():
        for directory in sorted(run_dir.glob("*.final")):
            shard_id = directory.name[: -len(".final")]
            record = find_commit(str(registry_path), run_instance_id=run_instance_id,
                                 shard_id=shard_id)
            if record is None:
                orphans.append(shard_id)
    registry = Path(registry_path)
    if registry.exists():
        for line in registry.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            record = json.loads(line)
            if record.get("run_instance_id") != run_instance_id:
                continue
            shard_id = record.get("shard_id")
            directory = run_dir / f"{shard_id}.final"
            missing = [name for name in COMMITTED_FILES if not (directory / name).is_file()]
            declared = record.get("shard_manifest_hash")
            actual = None
            manifest = directory / "shard_manifest.json"
            if manifest.is_file():
                actual = _sha256(manifest.read_bytes())
            if missing or (declared and actual and declared != actual):
                lost.append({
                    "shard_id": shard_id,
                    "missing_files": missing,
                    "declared_manifest_hash": declared,
                    "actual_manifest_hash": actual,
                    "status": "COMMITTED_CONTENT_LOST",
                })
                continue
            evaluation = directory / "evaluation.scientific.jsonl"
            if evaluation.is_file():
                for row in evaluation.read_text(encoding="utf-8").splitlines():
                    if not row.strip():
                        continue
                    try:
                        committed_ids.append(json.loads(row)["evaluation_id"])
                    except Exception:  # noqa: BLE001 - a non-scientific line is reported
                        pass
            payload_hashes[shard_id] = actual
    duplicates = sorted({i for i in committed_ids if committed_ids.count(i) > 1})
    return {
        "run_instance_id": run_instance_id,
        "orphans_requiring_strict_repair": orphans,
        "lost_commits": lost,
        "committed_evaluation_ids": sorted(committed_ids),
        "duplicate_evaluation_ids": duplicates,
        "payload_hashes": payload_hashes,
        "reconciled": not orphans and not lost and not duplicates,
    }


__all__ = [
    "RECOVERY_ARTIFACT_NAME",
    "RECOVERY_EVENT_TYPE",
    "REPAIRABLE_STATES",
    "RecoveryError",
    "inspect_tail",
    "read_recovery_chain",
    "reconcile_run",
    "repair_incomplete_tail",
]
