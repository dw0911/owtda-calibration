"""The ten fault points of task pack §5.3, executed on the target environment.

This is the raw-record bench: for every fault point it stores the command, the
exit code, the process timeline and the bytes/hashes before and after the fault,
under ``<out>/<fault_id>/``.  The ten-line summary printed at the end is a
convenience; the artifacts are the evidence, because the re-audit explicitly said
a ten-item summary cannot stand in for the originals.

Scope: process interruption and detectable file anomalies.  No claim of zero loss
on a whole-machine power cut.
"""

from __future__ import annotations

import hashlib
import json
import shutil
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "src"))

from owtda_cal import chains, recovery, shardio
from owtda_cal.canonical import canonical_json_bytes
from owtda_cal.identity import H
from owtda_cal.kernel_lock import kernel_lock, lock_path_for

RUN = H("fault_run")
RESULTS: list[dict[str, Any]] = []

_CHILD_HOLD_LOCK = """
import sys, time
sys.path.insert(0, sys.argv[1])
from owtda_cal.kernel_lock import kernel_lock, lock_path_for
with kernel_lock(lock_path_for(sys.argv[2]), scope=sys.argv[3], timeout=5.0):
    print("held", flush=True)
    time.sleep(30)
"""

_CHILD_PARTIAL_APPEND = """
import sys, json
sys.path.insert(0, sys.argv[1])
from owtda_cal import chains
path = sys.argv[2]
tip = chains.read_tip(path, hash_field="shard_commit_hash")
payload = {"schema_version": 2, "seq": 0, "prev_event_hash": tip,
           "event_type": "SHARD_COMMITTED", "shard_id": "half"}
chains.append_cas(path, payload, expected_tip=tip, hash_field="shard_commit_hash")
# now write a *partial* next event and die, as a killed writer would
with open(path, "ab") as fh:
    fh.write(b'{"schema_version": 2, "seq": 1, "par')
print("partial", flush=True)
"""

_CHILD_ATTEMPT_RACE = """
import sys
sys.path.insert(0, sys.argv[1])
from owtda_cal.shardio import allocate_attempt
print(allocate_attempt(sys.argv[2], run_instance_id=sys.argv[3],
                       evaluation_id=sys.argv[4]), flush=True)
"""


def _record(fault_id: str, name: str, ok: bool, reason: str, artifacts: Path) -> None:
    RESULTS.append({"fault": fault_id, "name": name, "ok": bool(ok), "reason": reason,
                    "artifacts": str(artifacts)})
    print(f"[{'PASS' if ok else 'FAIL'}] {fault_id} {name}: {reason}", flush=True)


def _write_artifacts(directory: Path, *, command: str, exit_code: int | None,
                     timeline: dict[str, Any], before: dict[str, Any],
                     after: dict[str, Any], extra: dict[str, Any] | None = None) -> None:
    directory.mkdir(parents=True, exist_ok=True)
    (directory / "command.txt").write_text(command + "\n", encoding="utf-8")
    (directory / "exit_code.txt").write_text(
        "" if exit_code is None else f"{exit_code}\n", encoding="utf-8")
    (directory / "timeline.json").write_text(
        json.dumps(timeline, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    (directory / "state_before.json").write_text(
        json.dumps(before, indent=2, sort_keys=True, default=str) + "\n", encoding="utf-8")
    (directory / "state_after.json").write_text(
        json.dumps(after, indent=2, sort_keys=True, default=str) + "\n", encoding="utf-8")
    if extra:
        (directory / "verdict.json").write_text(
            json.dumps(extra, indent=2, sort_keys=True, default=str) + "\n",
            encoding="utf-8")


def _file_state(root: Path) -> dict[str, Any]:
    state: dict[str, Any] = {}
    for path in sorted(root.rglob("*")):
        if path.is_file():
            blob = path.read_bytes()
            state[str(path.relative_to(root))] = {
                "bytes": len(blob),
                "sha256": hashlib.sha256(blob).hexdigest(),
            }
    return state


def _registry_records(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    return [json.loads(line) for line in
            path.read_text(encoding="utf-8").splitlines() if line.strip()]


def _commit_kwargs(run_root: str, registry: str, shard: str, lines: list[bytes]) -> dict:
    return {
        "run_root": run_root, "run_instance_id": RUN, "shard_id": shard,
        "shard_plan_hash": H("fault_plan"), "evaluation_lines": lines,
        "feature_lines": [b'{"f":1}\n'], "evaluation_meta": {}, "feature_meta": {},
        "registry_path": registry,
    }


def _payload(seed: int) -> list[bytes]:
    return [
        json.dumps({"row": i, "seed": seed}, sort_keys=True).encode() + b"\n"
        for i in range(4)
    ]


def _run_child(code: str, *args: str, timeout: float = 60.0) -> subprocess.CompletedProcess:
    return subprocess.run([sys.executable, "-c", code, str(REPO / "src"), *args],
                          capture_output=True, text=True, encoding="utf-8",
                          errors="replace", timeout=timeout, check=False)


# --------------------------------------------------------------------------- #
# the ten fault points
# --------------------------------------------------------------------------- #
def fault_1(out: Path) -> None:
    """Kill while holding the per-shard (and registry) lock -> the OS releases it."""
    work = out / "F1"
    work.mkdir(parents=True, exist_ok=True)
    started = time.time()
    observed = {}
    for scope in ("shard", "registry"):
        lock = work / f"{scope}.target"
        child = subprocess.Popen(
            [sys.executable, "-c", _CHILD_HOLD_LOCK, str(REPO / "src"), str(lock), scope],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
        )
        assert child.stdout is not None
        child.stdout.readline()  # "held"
        killed_at = time.time()
        child.kill()
        child.wait(timeout=30)
        reacquired = False
        try:
            with kernel_lock(lock_path_for(str(lock)), scope=scope, timeout=10.0):
                reacquired = True
        except Exception:  # noqa: BLE001 - reported, not swallowed
            reacquired = False
        observed[scope] = {
            "killed": child.returncode is not None,
            "kill_exit_code": child.returncode,
            "reacquired": reacquired,
            "lock_file_persists": (Path(lock_path_for(str(lock)))).exists(),
            "seconds_to_kill": round(killed_at - started, 3),
        }
    ok = all(v["reacquired"] and v["lock_file_persists"] for v in observed.values())
    _write_artifacts(
        work, command="kill(child holding the OS lock); reacquire",
        exit_code=0, timeline={"started": started, "ended": time.time()},
        before={}, after=observed,
        extra={"note": "a sentinel lock deleted in a finally block would block here"},
    )
    _record("F1", "kill_while_holding_lock", ok, json.dumps(observed), work)


def fault_2(out: Path) -> None:
    """Killed while writing the evaluation file: staging is never committed."""
    work = out / "F2"
    work.mkdir(parents=True, exist_ok=True)
    staging = work / RUN / "s2.tmp"
    staging.mkdir(parents=True)
    (staging / "evaluation.scientific.jsonl").write_bytes(b"partial")
    registry = work / "reg.jsonl"
    before = _file_state(work)
    refused = False
    try:
        shardio.commit_shard(**_commit_kwargs(str(work), str(registry), "s2", _payload(2)))
    except shardio.ShardError as exc:
        refused = "staging" in str(exc)
    after = _file_state(work)
    ok = refused and not (work / RUN / "s2.final").exists() and _registry_records(registry) == []
    _write_artifacts(work, command="commit with a half-written staging directory",
                     exit_code=1 if refused else 0,
                     timeline={"started": time.time()}, before=before, after=after,
                     extra={"refused": refused})
    _record("F2", "staging_never_authoritative", ok,
            f"refused={refused} records={len(_registry_records(registry))}", work)


def fault_3(out: Path) -> None:
    """manifest fsynced, rename not done: a staged shard must not read as done."""
    work = out / "F3"
    work.mkdir(parents=True, exist_ok=True)
    staging = work / RUN / "s3.tmp"
    staging.mkdir(parents=True)
    manifest = shardio.build_shard_manifest(
        run_instance_id=RUN, shard_id="s3", shard_plan_hash=H("fault_plan"),
        evaluation={}, feature={},
    )
    (staging / "shard_manifest.json").write_bytes(canonical_json_bytes(manifest) + b"\n")
    (staging / "evaluation.scientific.jsonl").write_bytes(b"".join(_payload(3)))
    (staging / "feature.scientific.jsonl").write_bytes(b'{"f":1}\n')
    registry = work / "reg.jsonl"
    before = _file_state(work)
    refused = False
    try:
        shardio.commit_shard(**_commit_kwargs(str(work), str(registry), "s3", _payload(3)))
    except shardio.ShardError:
        refused = True
    ok = refused and _registry_records(registry) == []
    shutil.rmtree(staging)
    committed = shardio.commit_shard(
        **_commit_kwargs(str(work), str(registry), "s3", _payload(3)))
    after = _file_state(work)
    ok = ok and len(_registry_records(registry)) == 1
    _write_artifacts(work, command="commit with a fully staged, unrenamed shard",
                     exit_code=1 if refused else 0, timeline={"started": time.time()},
                     before=before, after=after,
                     extra={"refused": refused, "commit_after_cleanup": committed[
                         "shard_commit_hash"][:12]})
    _record("F3", "staged_is_not_committed", ok,
            f"refused={refused} records={len(_registry_records(registry))}", work)


def fault_4(out: Path) -> None:
    """rename done, commit missing: orphan repair recomputes and commits once."""
    work = out / "F4"
    work.mkdir(parents=True, exist_ok=True)
    shard = "s4"
    evaluation = b"".join(_payload(4))
    feature = b'{"f":1}\n'
    final = work / RUN / f"{shard}.final"
    final.parent.mkdir(parents=True, exist_ok=True)
    final.mkdir()
    manifest = shardio.build_shard_manifest(
        run_instance_id=RUN, shard_id=shard, shard_plan_hash=H("fault_plan"),
        evaluation={"scientific_hash": hashlib.sha256(evaluation).hexdigest()},
        feature={"scientific_hash": hashlib.sha256(feature).hexdigest()},
    )
    manifest_bytes = canonical_json_bytes(manifest) + b"\n"
    (final / "shard_manifest.json").write_bytes(manifest_bytes)
    (final / "evaluation.scientific.jsonl").write_bytes(evaluation)
    (final / "feature.scientific.jsonl").write_bytes(feature)
    registry = work / "reg.jsonl"
    before = _file_state(work)
    refused = False
    try:
        shardio.commit_shard(**_commit_kwargs(str(work), str(registry), shard, _payload(4)))
    except shardio.ShardError:
        refused = True
    repaired = shardio.repair_orphan(
        run_root=str(work), run_instance_id=RUN, shard_id=shard,
        registry_path=str(registry), recompute_to=str(work / "recompute"),
        expected_manifest_bytes=manifest_bytes, expected_evaluation_bytes=evaluation,
        expected_feature_bytes=feature, expected_shard_plan_hash=H("fault_plan"),
    )
    after = _file_state(work)
    records = _registry_records(registry)
    ok = (refused and len(records) == 1
          and (final / "evaluation.scientific.jsonl").read_bytes() == evaluation)
    _write_artifacts(work, command="commit over an orphan, then repair_orphan",
                     exit_code=0, timeline={"started": time.time()},
                     before=before, after=after,
                     extra={"refused": refused, "records": len(records),
                            "repaired": repaired["shard_commit_hash"][:12]})
    _record("F4", "orphan_repaired_once", ok,
            f"refused={refused} records={len(records)}", work)


def fault_5(out: Path) -> None:
    """Partial trailing event: original preserved, prefix verified, explicit repair."""
    work = out / "F5"
    work.mkdir(parents=True, exist_ok=True)
    registry = work / "reg.jsonl"
    done = _run_child(_CHILD_PARTIAL_APPEND, str(registry))
    before_bytes = registry.read_bytes()
    before = _file_state(work)
    inspection = recovery.inspect_tail(registry, hash_field="shard_commit_hash")
    outcome = recovery.repair_incomplete_tail(
        registry_path=registry, recovery_dir=work / "recovery",
        hash_field="shard_commit_hash", log_state="RUN_INTERRUPTED",
        reason="writer killed after appending partial event bytes",
    )
    after = _file_state(work)
    records = _registry_records(registry)
    original = work / "recovery" / "reg.jsonl.orig"
    ok = (
        inspection["status"] == "INCOMPLETE_TAIL"
        and outcome["status"] == "REPAIRED"
        and original.read_bytes() == before_bytes
        and len(records) == 1
        and chains.verify_chain(registry, hash_field="shard_commit_hash",
                                parent_field="prev_event_hash") == []
    )
    _write_artifacts(work, command="append partial bytes, then repair_incomplete_tail",
                     exit_code=done.returncode,
                     timeline={"child_stdout": done.stdout.strip()},
                     before={**before, "bytes_sha256": hashlib.sha256(before_bytes).hexdigest()},
                     after={**after, "bytes_sha256": hashlib.sha256(
                         registry.read_bytes()).hexdigest()},
                     extra={"inspection": inspection["status"], "outcome": outcome["status"],
                            "records": len(records),
                            "dropped_bytes": outcome.get("dropped_bytes")})
    _record("F5", "partial_event_tail_recovered", ok,
            f"status={inspection['status']}->{outcome['status']} records={len(records)}",
            work)


def fault_6(out: Path) -> None:
    """Commit fsynced, response lost: the retry returns the same valid commit."""
    work = out / "F6"
    work.mkdir(parents=True, exist_ok=True)
    registry = work / "reg.jsonl"
    first = shardio.commit_shard(**_commit_kwargs(str(work), str(registry), "s6", _payload(6)))
    before = _file_state(work)
    retry = shardio.commit_shard(**_commit_kwargs(str(work), str(registry), "s6", _payload(6)))
    after = _file_state(work)
    records = _registry_records(registry)
    ok = (retry["shard_commit_hash"] == first["shard_commit_hash"]
          and len(records) == 1 and before == after)
    _write_artifacts(work, command="commit, then retry after a lost response",
                     exit_code=0, timeline={"started": time.time()},
                     before=before, after=after,
                     extra={"same_commit": retry["shard_commit_hash"] == first[
                         "shard_commit_hash"], "records": len(records)})
    _record("F6", "retry_returns_the_same_commit", ok,
            f"records={len(records)} bytes_unchanged={before == after}", work)


def fault_7(out: Path) -> None:
    """Two competitors: identical content -> one commit; different -> conflict."""
    work = out / "F7"
    work.mkdir(parents=True, exist_ok=True)
    registry = work / "reg.jsonl"
    shardio.commit_shard(**_commit_kwargs(str(work), str(registry), "s7a", _payload(7)))
    shardio.commit_shard(**_commit_kwargs(str(work), str(registry), "s7a", _payload(7)))
    same_records = len(_registry_records(registry))
    winner_bytes = (work / RUN / "s7a.final" / "evaluation.scientific.jsonl").read_bytes()
    conflict = False
    detail = ""
    try:
        shardio.commit_shard(**_commit_kwargs(str(work), str(registry), "s7a", _payload(99)))
    except shardio.ShardError as exc:
        conflict = True
        detail = str(exc)[:80]
    loser_bytes = (work / RUN / "s7a.final" / "evaluation.scientific.jsonl").read_bytes()
    ok = (same_records == 1 and conflict and loser_bytes == winner_bytes
          and len(_registry_records(registry)) == 1)
    _write_artifacts(work, command="commit identical, then conflicting content",
                     exit_code=1 if conflict else 0, timeline={"started": time.time()},
                     before={"winner_sha256": hashlib.sha256(winner_bytes).hexdigest()},
                     after={"loser_sha256": hashlib.sha256(loser_bytes).hexdigest(),
                            "records": len(_registry_records(registry))},
                     extra={"conflict": conflict, "detail": detail})
    _record("F7", "same_content_one_commit_conflict_blocked", ok,
            f"records={len(_registry_records(registry))} winner_bytes_intact="
            f"{loser_bytes == winner_bytes}", work)


def fault_8(out: Path) -> None:
    """Repair aimed at an already-committed shard: refused, no duplicate event."""
    work = out / "F8"
    work.mkdir(parents=True, exist_ok=True)
    registry = work / "reg.jsonl"
    shard = "s8"
    evaluation = b"".join(_payload(8))
    record = shardio.commit_shard(
        **_commit_kwargs(str(work), str(registry), shard, _payload(8)))
    before = _file_state(work)
    refused = ""
    try:
        shardio.repair_orphan(
            run_root=str(work), run_instance_id=RUN, shard_id=shard,
            registry_path=str(registry), recompute_to=str(work / "recompute"),
            expected_manifest_bytes=(work / RUN / f"{shard}.final" / "shard_manifest.json")
            .read_bytes(),
            expected_evaluation_bytes=evaluation, expected_feature_bytes=b'{"f":1}\n',
            expected_shard_plan_hash=H("fault_plan"),
        )
    except shardio.ShardError as exc:
        refused = str(exc)[:60]
    after = _file_state(work)
    records = _registry_records(registry)
    ok = "NOT_AN_ORPHAN" in refused and len(records) == 1
    _write_artifacts(work, command="repair_orphan on an already-committed shard",
                     exit_code=1 if refused else 0, timeline={"started": time.time()},
                     before=before, after=after,
                     extra={"refused": refused, "records": len(records),
                            "commit": record["shard_commit_hash"][:12]})
    _record("F8", "duplicate_recovery_refused", ok,
            f"records={len(records)} reason={refused!r}", work)


def fault_9(out: Path) -> None:
    """Wrong run/shard/plan/payload hash: every refusal must be attributable."""
    work = out / "F9"
    work.mkdir(parents=True, exist_ok=True)
    shard = "s9"
    evaluation = b"".join(_payload(9))
    feature = b'{"f":1}\n'
    cases: dict[str, str] = {}

    def _orphan(manifest_overrides: dict, *, run_id: str = RUN, shard_id: str = shard,
                expected_plan: str | None = None) -> str:
        directory = work / run_id / f"{shard_id}.final"
        if directory.exists():
            shutil.rmtree(directory)
        directory.mkdir(parents=True)
        manifest = shardio.build_shard_manifest(
            run_instance_id=run_id, shard_id=shard_id, shard_plan_hash=H("fault_plan"),
            evaluation={"scientific_hash": hashlib.sha256(evaluation).hexdigest()},
            feature={"scientific_hash": hashlib.sha256(feature).hexdigest()},
        )
        manifest.update(manifest_overrides)
        manifest_bytes = canonical_json_bytes(manifest) + b"\n"
        (directory / "shard_manifest.json").write_bytes(manifest_bytes)
        (directory / "evaluation.scientific.jsonl").write_bytes(evaluation)
        (directory / "feature.scientific.jsonl").write_bytes(feature)
        registry = work / f"reg_{len(cases)}.jsonl"
        try:
            shardio.repair_orphan(
                run_root=str(work), run_instance_id=RUN, shard_id=shard,
                registry_path=str(registry), recompute_to=str(work / f"re_{len(cases)}"),
                expected_manifest_bytes=manifest_bytes,
                expected_evaluation_bytes=evaluation, expected_feature_bytes=feature,
                expected_shard_plan_hash=expected_plan or H("fault_plan"),
            )
            return "ACCEPTED"
        except shardio.ShardError as exc:
            return str(exc).split(":")[0]

    cases["wrong_run_id"] = _orphan({"run_instance_id": H("other_run")})
    cases["wrong_shard_id"] = _orphan({"shard_id": H("other_shard")})
    cases["wrong_plan_hash"] = _orphan({}, expected_plan=H("other_plan"))
    cases["zero_payload_hash"] = _orphan({"evaluation": {"scientific_hash": "0" * 64}})
    cases["lying_payload_hash"] = _orphan(
        {"evaluation": {"scientific_hash": hashlib.sha256(b"nope").hexdigest()}})
    expected_codes = {
        "wrong_run_id": "ORPHAN_IDENTITY_MISMATCH",
        "wrong_shard_id": "ORPHAN_IDENTITY_MISMATCH",
        "wrong_plan_hash": "ORPHAN_PLAN_MISMATCH",
        "zero_payload_hash": "MANIFEST_PAYLOAD_HASH_INVALID",
        "lying_payload_hash": "MANIFEST_PAYLOAD_HASH_MISMATCH",
    }
    ok = cases == expected_codes
    _write_artifacts(work, command="repair_orphan with each wrong identity/hash",
                     exit_code=0, timeline={"started": time.time()},
                     before={"cases": sorted(cases)}, after=cases,
                     extra={"expected": expected_codes})
    _record("F9", "attributable_refusals", ok, json.dumps(cases, sort_keys=True), work)


def fault_10(out: Path) -> None:
    """Concurrent attempt allocation: unique numbers, valid parent chain."""
    work = out / "F10"
    work.mkdir(parents=True, exist_ok=True)
    registry = work / "attempts.jsonl"
    started = time.time()
    procs = [
        subprocess.Popen(
            [sys.executable, "-c", _CHILD_ATTEMPT_RACE, str(REPO / "src"),
             str(registry), RUN, H("fault_eval")],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
        )
        for _ in range(8)
    ]
    numbers: list[str] = []
    codes = []
    for proc in procs:
        out_text, _err = proc.communicate(timeout=120)
        codes.append(proc.returncode)
        numbers.append(out_text.strip())
    parsed = sorted(int(n) for n in numbers if n.isdigit())
    records = _registry_records(registry)
    chain_ok = chains.verify_chain(registry, hash_field="attempt_id",
                                   parent_field="prev_event_hash") == []
    ok = (all(c == 0 for c in codes) and parsed == list(range(1, 9))
          and len({r["attempt_number"] for r in records}) == 8 and chain_ok)
    _write_artifacts(work, command="8 concurrent attempt allocations",
                     exit_code=max(codes) if codes else None,
                     timeline={"started": started, "ended": time.time(),
                               "seconds": round(time.time() - started, 3)},
                     before={"requested": 8},
                     after={"numbers": parsed, "exit_codes": codes,
                            "records": len(records)},
                     extra={"chain_ok": chain_ok})
    _record("F10", "concurrent_attempt_allocation", ok,
            f"numbers={parsed} chain_ok={chain_ok}", work)


FAULTS = (fault_1, fault_2, fault_3, fault_4, fault_5,
          fault_6, fault_7, fault_8, fault_9, fault_10)


def main() -> int:
    parser_out = sys.argv[1] if len(sys.argv) > 1 else None
    if parser_out is None:
        print("usage: python scripts/verify_fault_points.py <out-dir-outside-the-repo>")
        return 2
    out = Path(parser_out).expanduser()
    if out.exists():
        shutil.rmtree(out)
    out.mkdir(parents=True)
    for fault in FAULTS:
        try:
            fault(out)
        except Exception as exc:  # noqa: BLE001 - a crash is a failed fault point
            _record(getattr(fault, "__name__", "?"), "exception", False,
                    f"{type(exc).__name__}: {exc}", out)
    failed = [r["fault"] for r in RESULTS if not r["ok"]]
    (out / "SUMMARY.json").write_text(
        json.dumps({"platform": sys.platform, "python": sys.version.split()[0],
                    "checks": len(RESULTS), "failed": failed, "results": RESULTS},
                   indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({"checks": len(RESULTS), "failed": failed}, sort_keys=True))
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
