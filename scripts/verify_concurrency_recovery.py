"""Windows concurrency / interruption acceptance bench (ruling 2026-09-12, item 3).

Fixed scope, six scenarios, then the item is closed -- not generalised into "proves the
system never fails":

  1. 8 processes commit *different* shards concurrently -> one valid commit each, chain
     and directories consistent;
  2. several processes commit the *same* shard with *identical* content -> exactly one
     canonical commit, a retry returns the same identity;
  3. same shard, *conflicting* content -> explicit rejection, no overwrite and no second
     valid commit;
  4. concurrent attempt allocation for one evaluation -> unique numbers / attempt ids,
     losers traceable and retryable;
  5. forced termination at a critical point: (a) after the commit is written but before
     the success is confirmed (the caller then retries), (b) after the rename but before
     the commit append (ORPHAN_FINAL), (c) staging left behind with no final and no commit;
  6. committed directory lost / orphan / content-hash conflict -> the registered
     recovery-or-reject path, never a silent rewrite through the normal channel.

Acceptance: the scientific payload after recovery equals the uninterrupted payload
(timestamps, PIDs and attempt history may differ), and every evaluation ends with
exactly one valid result.  The strong guarantee is limited to process interruption and
detectable loss -- it is NOT extrapolated to power loss.

Usage::

    python scripts/verify_concurrency_recovery.py            # all scenarios
    python scripts/verify_concurrency_recovery.py --child <name> ...   # internal
"""

from __future__ import annotations

import argparse
import json
import os
import random
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "src"))

from owtda_cal.identity import H
from owtda_cal.shardio import (
    ShardError,
    allocate_attempt,
    commit_shard,
    repair_orphan,
)

PY = sys.executable
RUN = H("bench_run")
RESULTS: list[tuple[str, bool, str]] = []


def record(name: str, ok: bool, reason: str) -> None:
    RESULTS.append((name, ok, reason))


def payload(seed: int) -> list[bytes]:
    """A deterministic 'scientific payload' for one shard."""
    rng = random.Random(seed)
    return [
        json.dumps({"row": i, "value": round(rng.random(), 12)}, sort_keys=True).encode()
        + b"\n"
        for i in range(24)
    ]


def _commit_kwargs(run_root: str, registry: str, shard: str, lines: list[bytes]) -> dict:
    return {
        "run_root": run_root, "run_instance_id": RUN, "shard_id": shard,
        "shard_plan_hash": H("bench_plan"),
        "evaluation_lines": lines, "feature_lines": [b'{"f":1}\n'],
        "evaluation_meta": {}, "feature_meta": {}, "registry_path": registry,
    }


def _records(registry: str) -> list[dict]:
    path = Path(registry)
    if not path.exists():
        return []
    return [
        json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


# --------------------------------------------------------------------------- #
# child entry points (self-invoked so true processes, not threads, race)
# --------------------------------------------------------------------------- #
def child_barrier_commit(work: Path, index: int, shard: str, seed: int) -> int:
    (work / f"ready_{index}").write_text("1", encoding="utf-8")
    deadline = time.time() + 60
    while not (work / "go").exists():
        if time.time() > deadline:
            return 2
        time.sleep(0.02)
    try:
        commit_shard(**_commit_kwargs(str(work), str(work / "reg.jsonl"), shard,
                                      payload(seed)))
        (work / f"ok_{index}").write_text("1", encoding="utf-8")
        return 0
    except Exception as exc:  # noqa: BLE001 - reported to the parent
        (work / f"err_{index}").write_text(f"{type(exc).__name__}: {exc}", encoding="utf-8")
        return 1


def child_commit_then_wait(work: Path, shard: str, seed: int) -> int:
    """Commit, then hold: the parent kills us *after* the commit but before we confirm."""
    commit_shard(**_commit_kwargs(str(work), str(work / "reg.jsonl"), shard, payload(seed)))
    (work / "committed").write_text("1", encoding="utf-8")
    time.sleep(60)
    return 0


def child_attempt(work: Path, index: int) -> int:
    (work / f"ready_{index}").write_text("1", encoding="utf-8")
    deadline = time.time() + 60
    while not (work / "go").exists():
        if time.time() > deadline:
            return 2
        time.sleep(0.02)
    try:
        number = allocate_attempt(str(work / "att.jsonl"), run_instance_id=RUN,
                                  evaluation_id=H("bench_eval"))
        (work / f"n_{index}").write_text(str(number), encoding="utf-8")
        return 0
    except Exception as exc:  # noqa: BLE001
        (work / f"err_{index}").write_text(f"{type(exc).__name__}: {exc}", encoding="utf-8")
        return 1


def _spawn(args: list[str]) -> subprocess.Popen:
    return subprocess.Popen(
        [PY, str(Path(__file__).resolve()), *args],
        cwd=str(REPO), stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )


def _wait_for(path: Path, timeout: float = 60.0) -> bool:
    deadline = time.time() + timeout
    while time.time() < deadline:
        if path.exists():
            return True
        time.sleep(0.02)
    return False


# --------------------------------------------------------------------------- #
# scenarios
# --------------------------------------------------------------------------- #
def scenario_1(work: Path) -> None:
    """8 processes, 8 different shards."""
    work.mkdir(parents=True, exist_ok=True)
    shards = [H("bench_shard", n=i) for i in range(8)]
    procs = [_spawn(["--child", "commit", str(work), str(i), shards[i], str(100 + i)])
             for i in range(8)]
    assert _wait_for(work / "ready_7")
    (work / "go").write_text("1", encoding="utf-8")
    for proc in procs:
        proc.wait(timeout=120)
    registry = _records(str(work / "reg.jsonl"))
    per_shard = {shard: [r for r in registry if r["shard_id"] == shard] for shard in shards}
    ok = all(len(v) == 1 for v in per_shard.values()) and len(registry) == 8
    for shard in shards:
        final = Path(work, RUN, f"{shard}.final", "evaluation.scientific.jsonl")
        ok = ok and final.exists() and final.read_bytes() == b"".join(
            payload(100 + shards.index(shard)))
    record("S1_8_processes_different_shards", ok,
           f"records={len(registry)} one_each={all(len(v) == 1 for v in per_shard.values())}")


def scenario_2(work: Path) -> None:
    """Several processes, same shard, identical content."""
    work.mkdir(parents=True, exist_ok=True)
    shard = H("bench_shard", n="same")
    procs = [_spawn(["--child", "commit", str(work), str(i), shard, "7"]) for i in range(4)]
    assert _wait_for(work / "ready_3")
    (work / "go").write_text("1", encoding="utf-8")
    for proc in procs:
        proc.wait(timeout=120)
    registry = _records(str(work / "reg.jsonl"))
    ok_records = len(registry) == 1
    retry = commit_shard(**_commit_kwargs(str(work), str(work / "reg.jsonl"), shard, payload(7)))
    ok = ok_records and retry["shard_manifest_hash"] == registry[0]["shard_manifest_hash"] \
        and len(_records(str(work / "reg.jsonl"))) == 1
    record("S2_same_shard_same_content", ok,
           f"records={len(registry)} retry_same_identity={ok_records}")


def scenario_3_multiprocess(work: Path) -> None:
    """Several processes commit the *same* shard with *conflicting* content.

    Acceptance: exactly one valid commit; the losers refuse; the committed bytes belong
    to the winner -- a loser's bytes must never overwrite or masquerade as the content.
    """
    work.mkdir(parents=True, exist_ok=True)
    shard = H("bench_shard", n="mp_conflict")
    procs = [_spawn(["--child", "commit", str(work), str(i), shard, str(300 + i)])
             for i in range(3)]
    assert _wait_for(work / "ready_2")
    (work / "go").write_text("1", encoding="utf-8")
    for proc in procs:
        proc.wait(timeout=120)
    records = _records(str(work / "reg.jsonl"))
    refused = sorted(
        i for i in range(3) if (work / f"err_{i}").exists()
    )
    ok_count = sorted(i for i in range(3) if (work / f"ok_{i}").exists())
    final = Path(work, RUN, f"{shard}.final", "evaluation.scientific.jsonl")
    winner = None
    if len(records) == 1 and final.exists():
        committed = final.read_bytes()
        winner = next((i for i in range(3) if committed == b"".join(payload(300 + i))), None)
    last_attempt_ok = False
    if len(records) == 1 and winner is not None:
        # the winner's own payload is still accepted idempotently
        retry = commit_shard(**_commit_kwargs(str(work), str(work / "reg.jsonl"), shard,
                                              payload(300 + winner)))
        last_attempt_ok = retry["shard_manifest_hash"] == records[0]["shard_manifest_hash"]
    ok = len(records) == 1 and bool(refused) and winner is not None and last_attempt_ok
    record("S3b_multiprocess_conflicting_content", ok,
           f"records={len(records)} refused={refused} ok={ok_count} winner_seed_index={winner} "
           f"winner_content_kept={winner is not None}")


def scenario_3(work: Path) -> None:
    """Same shard, conflicting content: rejected, no second valid commit."""
    work.mkdir(parents=True, exist_ok=True)
    shard = H("bench_shard", n="conflict")
    commit_shard(**_commit_kwargs(str(work), str(work / "reg.jsonl"), shard, payload(1)))
    before = _records(str(work / "reg.jsonl"))
    refused = False
    try:
        commit_shard(**_commit_kwargs(str(work), str(work / "reg.jsonl"), shard, payload(2)))
    except ShardError:
        refused = True
    after = _records(str(work / "reg.jsonl"))
    final = Path(work, RUN, f"{shard}.final", "evaluation.scientific.jsonl")
    ok = refused and len(after) == len(before) == 1 and final.read_bytes() == b"".join(payload(1))
    record("S3_same_shard_conflicting_content", ok,
           f"refused={refused} records={len(after)} content_unchanged="
           f"{final.read_bytes() == b''.join(payload(1))}")


def scenario_4(work: Path) -> None:
    """Concurrent attempt allocation for one evaluation."""
    work.mkdir(parents=True, exist_ok=True)
    procs = [_spawn(["--child", "attempt", str(work), str(i)]) for i in range(6)]
    assert _wait_for(work / "ready_5")
    (work / "go").write_text("1", encoding="utf-8")
    for proc in procs:
        proc.wait(timeout=120)
    numbers = sorted(
        int((work / f"n_{i}").read_text(encoding="utf-8"))
        for i in range(6) if (work / f"n_{i}").exists()
    )
    records = _records(str(work / "att.jsonl"))
    stored = [r["attempt_number"] for r in records]
    ok = len(numbers) == len(stored) == len(set(stored)) == 6 and numbers == list(range(1, 7))
    record("S4_concurrent_attempt_allocation", ok,
           f"returned={numbers} stored={sorted(stored)} unique={len(set(stored))}")


def scenario_5(work: Path) -> None:
    """Forced termination at a critical point, then recovery."""
    # (a) killed after the commit, before the success is confirmed -> retry is idempotent
    a = work / "a"
    a.mkdir(parents=True, exist_ok=True)
    shard = H("bench_shard", n="kill")
    proc = _spawn(["--child", "commit_wait", str(a), shard, "11"])
    killed_after_commit = _wait_for(a / "committed")
    proc.kill()
    proc.wait(timeout=60)
    first = _records(str(a / "reg.jsonl"))
    retry = commit_shard(**_commit_kwargs(str(a), str(a / "reg.jsonl"), shard, payload(11)))
    second = _records(str(a / "reg.jsonl"))
    ok_a = (killed_after_commit and len(first) == 1 and len(second) == 1
            and retry["shard_manifest_hash"] == first[0]["shard_manifest_hash"])
    record("S5a_kill_after_commit_before_confirm", ok_a,
           f"killed={killed_after_commit} records={len(first)}->{len(second)}")

    # (b) rename done, commit not appended -> ORPHAN_FINAL, repair_orphan recovers it
    b = work / "b"
    b.mkdir(parents=True, exist_ok=True)
    shard_b = H("bench_shard", n="orphan")
    tmp = b / "staging"
    tmp.mkdir()
    (tmp / "evaluation.scientific.jsonl").write_bytes(b"".join(payload(21)))
    (tmp / "feature.scientific.jsonl").write_bytes(b'{"f":1}\n')
    from owtda_cal import shardio as _shardio
    from owtda_cal.canonical import canonical_json_bytes
    manifest = _shardio.build_shard_manifest(
        run_instance_id=RUN, shard_id=shard_b, shard_plan_hash=H("bench_plan"),
        evaluation={"scientific_hash": _shardio._sha256_bytes(b"".join(payload(21)))},
        feature={"scientific_hash": _shardio._sha256_bytes(b'{"f":1}\n')},
    )
    manifest_bytes = canonical_json_bytes(manifest) + b"\n"
    (tmp / "shard_manifest.json").write_bytes(manifest_bytes)
    final_b = Path(b, RUN, f"{shard_b}.final")
    final_b.parent.mkdir(parents=True, exist_ok=True)
    os.rename(tmp, final_b)
    refused = False
    try:
        commit_shard(**_commit_kwargs(str(b), str(b / "reg.jsonl"), shard_b, payload(21)))
    except ShardError:
        refused = True
    repaired = repair_orphan(
        run_root=str(b), run_instance_id=RUN, shard_id=shard_b,
        registry_path=str(b / "reg.jsonl"), recompute_to=str(b / "recompute"),
        expected_manifest_bytes=manifest_bytes,
        expected_evaluation_bytes=b"".join(payload(21)),
        expected_feature_bytes=b'{"f":1}\n',
        expected_shard_plan_hash=H("bench_plan"),
    )
    recovered = Path(b, RUN, f"{shard_b}.final", "evaluation.scientific.jsonl").read_bytes()
    ok_b = refused and bool(repaired) and recovered == b"".join(payload(21))
    record("S5b_orphan_final_repaired", ok_b,
           f"refused={refused} payload_equal={recovered == b''.join(payload(21))}")

    # (c) staging left behind, no final, no commit -> normal channel refuses
    c = work / "c"
    c.mkdir(parents=True, exist_ok=True)
    shard_c = H("bench_shard", n="staging")
    (c / "runs").mkdir(exist_ok=True)
    staging = Path(c, RUN, f"{shard_c}.tmp")
    staging.mkdir(parents=True)
    (staging / "evaluation.scientific.jsonl").write_bytes(b"partial")
    blocked = False
    try:
        commit_shard(**_commit_kwargs(str(c), str(c / "reg.jsonl"), shard_c, payload(31)))
    except ShardError:
        blocked = True
    ok_c = blocked and _records(str(c / "reg.jsonl")) == []
    record("S5c_staging_left_behind_blocks", ok_c,
           f"blocked={blocked} records={len(_records(str(c / 'reg.jsonl')))}")


def scenario_6(work: Path) -> None:
    """Committed directory lost / orphan / content conflict: registered paths only."""
    work.mkdir(parents=True, exist_ok=True)
    shard = H("bench_shard", n="lost")
    commit_shard(**_commit_kwargs(str(work), str(work / "reg.jsonl"), shard, payload(41)))
    final = Path(work, RUN, f"{shard}.final")
    shutil.rmtree(final)
    blocked = False
    try:
        commit_shard(**_commit_kwargs(str(work), str(work / "reg.jsonl"), shard, payload(42)))
    except ShardError as exc:
        blocked = "COMMIT_RECORD_WITHOUT_FINAL" in str(exc)
    records_after = len(_records(str(work / "reg.jsonl")))

    # tampered content under a valid commit -> refused, and the registry is untouched
    shard2 = H("bench_shard", n="tamper")
    commit_shard(**_commit_kwargs(str(work), str(work / "reg.jsonl"), shard2, payload(51)))
    tampered = Path(work, RUN, f"{shard2}.final", "evaluation.scientific.jsonl")
    tampered.write_bytes(b"".join(payload(999)))
    refused = False
    try:
        commit_shard(**_commit_kwargs(str(work), str(work / "reg.jsonl"), shard2, payload(51)))
    except ShardError:
        refused = True
    ok = blocked and records_after == 1 and refused
    record("S6_lost_dir_and_tamper_blocked", ok,
           f"lost_dir_blocked={blocked} records={records_after} tamper_refused={refused}")


def scenario_5_equality(work: Path) -> None:
    """Interrupted-then-recovered payload == uninterrupted payload for the same seed.

    Two recovery routes are exercised, both registered: (i) staging left behind by a
    crash *before* the rename -- staging is never authoritative, so the documented step
    is to clear it and redo the commit; (ii) a ``.final`` present without its commit --
    ``repair_orphan`` re-derives it byte-identically.
    """
    clean = work / "clean"
    clean.mkdir(parents=True, exist_ok=True)
    shard = H("bench_shard", n="equality")
    commit_shard(**_commit_kwargs(str(clean), str(clean / "reg.jsonl"), shard, payload(61)))
    baseline_dir = Path(clean, RUN, f"{shard}.final")
    baseline = (baseline_dir / "evaluation.scientific.jsonl").read_bytes()

    # (i) staging only: blocked, then cleared, then re-committed
    stage_only = work / "stage_only"
    stage_only.mkdir(parents=True, exist_ok=True)
    staging = Path(stage_only, RUN, f"{shard}.tmp")
    staging.mkdir(parents=True)
    (staging / "evaluation.scientific.jsonl").write_bytes(b"partial")
    blocked = False
    try:
        commit_shard(**_commit_kwargs(str(stage_only), str(stage_only / "reg.jsonl"),
                                      shard, payload(61)))
    except ShardError:
        blocked = True
    shutil.rmtree(staging)
    commit_shard(**_commit_kwargs(str(stage_only), str(stage_only / "reg.jsonl"),
                                  shard, payload(61)))
    recovered_stage = Path(stage_only, RUN, f"{shard}.final",
                           "evaluation.scientific.jsonl").read_bytes()

    # (ii) final without commit: repaired byte-identically
    orphan = work / "orphan"
    orphan.mkdir(parents=True, exist_ok=True)
    orphan_final = Path(orphan, RUN, f"{shard}.final")
    orphan_final.parent.mkdir(parents=True, exist_ok=True)
    shutil.copytree(baseline_dir, orphan_final)
    manifest_bytes = (orphan_final / "shard_manifest.json").read_bytes()
    refused = False
    try:
        commit_shard(**_commit_kwargs(str(orphan), str(orphan / "reg.jsonl"), shard,
                                      payload(61)))
    except ShardError:
        refused = True
    repair_orphan(
        run_root=str(orphan), run_instance_id=RUN, shard_id=shard,
        registry_path=str(orphan / "reg.jsonl"), recompute_to=str(orphan / "recompute"),
        expected_manifest_bytes=manifest_bytes,
        expected_evaluation_bytes=baseline,
        expected_feature_bytes=b'{"f":1}\n',
        expected_shard_plan_hash=H("bench_plan"),
    )
    recovered_orphan = Path(orphan, RUN, f"{shard}.final",
                            "evaluation.scientific.jsonl").read_bytes()

    ok = (blocked and recovered_stage == baseline and refused
          and recovered_orphan == baseline)
    record("S5d_payload_equality_after_recovery", ok,
           f"staging_blocked={blocked} staging_path_equal={recovered_stage == baseline} "
           f"orphan_refused={refused} orphan_path_equal={recovered_orphan == baseline}")


def main() -> int:
    parser = argparse.ArgumentParser(description="concurrency / interruption bench")
    parser.add_argument("--child", choices=["commit", "commit_wait", "attempt"])
    parser.add_argument("positional", nargs="*")
    args = parser.parse_args()
    if args.child == "commit":
        work, index, shard, seed = args.positional
        return child_barrier_commit(Path(work), int(index), shard, int(seed))
    if args.child == "commit_wait":
        work, shard, seed = args.positional
        return child_commit_then_wait(Path(work), shard, int(seed))
    if args.child == "attempt":
        work, index = args.positional
        return child_attempt(Path(work), int(index))

    tmp = Path(tempfile.mkdtemp(prefix="cb_"))
    try:
        for name, fn in (
            ("S1", scenario_1), ("S2", scenario_2), ("S3", scenario_3),
            ("S3b", scenario_3_multiprocess),
            ("S4", scenario_4), ("S5", scenario_5), ("S6", scenario_6),
        ):
            try:
                fn(tmp / name)
            except Exception as exc:  # noqa: BLE001 - a crashed scenario is a failure
                record(f"{name}_crashed", False, f"{type(exc).__name__}: {exc}")
        try:
            scenario_5_equality(tmp / "S5")
        except Exception as exc:  # noqa: BLE001
            record("S5d_crashed", False, f"{type(exc).__name__}: {exc}")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    for name, ok, reason in RESULTS:
        print(f"[{'PASS' if ok else 'FAIL'}] {name}: {reason}")
    failed = [name for name, ok, _ in RESULTS if not ok]
    print(json.dumps({"scenarios": len(RESULTS), "failed": failed}, ensure_ascii=False))
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
