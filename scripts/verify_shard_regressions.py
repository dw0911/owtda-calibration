"""External regressions for the two shard paths the re-audit (2026-09-12) reopened.

Run outside pytest, the way the re-audit ran its own probes::

    python scripts/verify_shard_regressions.py

Each check prints PASS/FAIL and a one-line reason; the exit code is non-zero if any
check fails.  Without the fixes these checks fail as::

    changed content after the .final directory is deleted -> accepted (2 records)
    identical content after the .final directory is deleted -> accepted (2 records)
    interleaved attempt allocation -> both callers returned 1
"""

from __future__ import annotations

import json
import shutil
import sys
import tempfile
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "src"))

from owtda_cal import chains
from owtda_cal.identity import H
from owtda_cal.shardio import ShardError, allocate_attempt, commit_shard

RESULTS: list[tuple[str, bool, str]] = []


def record(name: str, ok: bool, reason: str) -> None:
    RESULTS.append((name, ok, reason))


def _commit(tmp: Path, *, eval_lines: list[bytes] | None = None) -> tuple[str, str, Path]:
    run_root = str(tmp / "runs")
    registry = str(tmp / "shard_registry.jsonl")
    commit_shard(
        run_root=run_root, run_instance_id=H("reg_run"), shard_id=H("reg_shard"),
        shard_plan_hash=H("reg_plan"),
        evaluation_lines=eval_lines or [b'{"x":1}\n'],
        feature_lines=[b'{"f":1}\n'], evaluation_meta={}, feature_meta={},
        registry_path=registry,
    )
    return run_root, registry, Path(run_root, H("reg_run"), f"{H('reg_shard')}.final")


def _records(registry: str) -> list[dict]:
    return [
        json.loads(line)
        for line in Path(registry).read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def check_identical_recommit() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root, registry, final = _commit(Path(tmp))
        again = commit_shard(
            run_root=root, run_instance_id=H("reg_run"), shard_id=H("reg_shard"),
            shard_plan_hash=H("reg_plan"), evaluation_lines=[b'{"x":1}\n'],
            feature_lines=[b'{"f":1}\n'], evaluation_meta={}, feature_meta={},
            registry_path=registry,
        )
        records = _records(registry)
        record("identical_recommit", len(records) == 1 and final.exists(),
               f"records={len(records)} final_exists={final.exists()} "
               f"returned_record={'shard_commit_hash' in again}")


def check_deleted_final_changed_content() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root, registry, final = _commit(Path(tmp))
        shutil.rmtree(final)
        try:
            commit_shard(
                run_root=root, run_instance_id=H("reg_run"), shard_id=H("reg_shard"),
                shard_plan_hash=H("reg_plan"), evaluation_lines=[b'{"x":999}\n'],
                feature_lines=[b'{"f":1}\n'], evaluation_meta={}, feature_meta={},
                registry_path=registry,
            )
            record("deleted_final_changed_content", False,
                   f"accepted; records={len(_records(registry))}")
        except ShardError as exc:
            ok = "COMMIT_RECORD_WITHOUT_FINAL" in str(exc) and len(_records(registry)) == 1
            record("deleted_final_changed_content", ok,
                   f"{str(exc)[:60]} records={len(_records(registry))}")


def check_deleted_final_identical_content() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root, registry, final = _commit(Path(tmp))
        shutil.rmtree(final)
        try:
            commit_shard(
                run_root=root, run_instance_id=H("reg_run"), shard_id=H("reg_shard"),
                shard_plan_hash=H("reg_plan"), evaluation_lines=[b'{"x":1}\n'],
                feature_lines=[b'{"f":1}\n'], evaluation_meta={}, feature_meta={},
                registry_path=registry,
            )
            record("deleted_final_identical_content", False,
                   f"accepted; records={len(_records(registry))}")
        except ShardError as exc:
            ok = "COMMIT_RECORD_WITHOUT_FINAL" in str(exc) and len(_records(registry)) == 1
            record("deleted_final_identical_content", ok,
                   f"{str(exc)[:60]} records={len(_records(registry))}")


def check_interleaved_attempts() -> None:
    """A caller holding a stale snapshot must not be able to append its number."""
    with tempfile.TemporaryDirectory() as tmp:
        registry = str(Path(tmp) / "attempts.jsonl")
        stale_tip = chains.read_tip(registry, hash_field="attempt_id")
        first = allocate_attempt(registry, run_instance_id=H("reg_run"),
                                 evaluation_id=H("reg_eval"))
        refused = False
        try:
            chains.append_cas(
                registry,
                {"schema_version": 1, "run_instance_id": H("reg_run"),
                 "evaluation_id": H("reg_eval"), "attempt_number": first},
                expected_tip=stale_tip, hash_field="attempt_id",
            )
        except chains.ChainError:
            refused = True
        second = allocate_attempt(registry, run_instance_id=H("reg_run"),
                                  evaluation_id=H("reg_eval"))
        numbers = [r["attempt_number"] for r in _records(registry)]
        record("interleaved_attempt_allocation",
               refused and second == first + 1 and len(set(numbers)) == len(numbers),
               f"stale_append_refused={refused} numbers={numbers}")


def main() -> int:
    check_identical_recommit()
    check_deleted_final_changed_content()
    check_deleted_final_identical_content()
    check_interleaved_attempts()
    for name, ok, reason in RESULTS:
        print(f"[{'PASS' if ok else 'FAIL'}] {name}: {reason}")
    failed = [name for name, ok, _ in RESULTS if not ok]
    print(json.dumps({"checks": len(RESULTS), "failed": failed}, ensure_ascii=False))
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
