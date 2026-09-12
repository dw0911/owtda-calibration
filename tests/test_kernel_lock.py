"""OS-managed kernel locks: persistence, death safety and lock order (§5.1).

The old sentinel lock (``<path>.lock`` created with ``O_CREAT|O_EXCL`` and
deleted in a ``finally`` block) had two failure modes the re-audit cares about:

* a process killed while holding it left the file behind, and every later
  writer waited forever;
* the file was deleted by its holder, so a cleaner -- or a second holder leaving
  -- could remove it while another process was waiting on it.

These tests pin the replacement properties with real processes.
"""

from __future__ import annotations

import json
import subprocess
import sys
import textwrap
from pathlib import Path

import pytest

from owtda_cal import chains
from owtda_cal.kernel_lock import LOCK_ORDER, LockError, kernel_lock, lock_path_for

REPO = Path(__file__).resolve().parents[1]

_CHILD_HOLD = textwrap.dedent(
    """
    import sys, time
    sys.path.insert(0, sys.argv[1])
    from owtda_cal.kernel_lock import kernel_lock
    with kernel_lock(sys.argv[2], scope="registry", timeout=5.0):
        print("held", flush=True)
        time.sleep(float(sys.argv[3]))
    """
)

_CHILD_APPEND = textwrap.dedent(
    """
    import sys
    sys.path.insert(0, sys.argv[1])
    from owtda_cal import chains
    path, count, tag = sys.argv[2], int(sys.argv[3]), sys.argv[4]
    for i in range(count):
        for _ in range(64):
            tip = chains.read_tip(path, hash_field="event_hash")
            try:
                chains.append_cas(path, {"n": i, "tag": tag},
                                  expected_tip=tip, hash_field="event_hash")
                break
            except chains.ChainError:
                continue
        else:
            raise SystemExit("could not append")
    """
)


def _run_child(code: str, *args: str, timeout: float = 60.0) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, "-c", code, str(REPO / "src"), *args],
        capture_output=True, text=True, encoding="utf-8", errors="replace",
        timeout=timeout, check=False,
    )


class TestLockFileLifecycle:
    def test_lock_file_persists_and_is_named(self, tmp_path):
        path = str(tmp_path / "resource.jsonl")
        with kernel_lock(lock_path_for(path), scope="registry"):
            assert Path(lock_path_for(path)).exists()
        # deliberately left in place: deleting it would break a waiter
        assert Path(lock_path_for(path)).exists()

    def test_a_dead_holder_does_not_block_a_later_writer(self, tmp_path):
        """Kill the holder while it holds the lock; the next writer must proceed."""
        lock = str(tmp_path / "resource.jsonl.kernellock")
        child = subprocess.Popen(
            [sys.executable, "-c", _CHILD_HOLD, str(REPO / "src"), lock, "30"],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
        )
        assert child.stdout.readline().strip() == "held"
        child.kill()
        child.wait(timeout=30)
        with kernel_lock(lock, scope="registry", timeout=10.0):
            pass  # the OS released it; a sentinel would have blocked here

    def test_a_second_holder_has_to_wait(self, tmp_path):
        """A concurrent holder is refused rather than admitted (no mutual overlap)."""
        lock = str(tmp_path / "resource.jsonl.kernellock")
        holder = subprocess.Popen(
            [sys.executable, "-c", _CHILD_HOLD, str(REPO / "src"), lock, "3"],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
        )
        assert holder.stdout.readline().strip() == "held"
        try:
            with pytest.raises(LockError, match="lock timeout"), \
                    kernel_lock(lock, scope="registry", timeout=0.5):
                pass
        finally:
            holder.kill()
            holder.wait(timeout=30)
        # once the holder is gone the lock is free again
        with kernel_lock(lock, scope="registry", timeout=10.0):
            pass


class TestMutualExclusion:
    def test_concurrent_processes_produce_one_valid_chain(self, tmp_path):
        """8 processes x 25 appends: no lost update, no interleaved bytes."""
        path = str(tmp_path / "chain.jsonl")
        procs = [
            subprocess.Popen(
                [sys.executable, "-c", _CHILD_APPEND, str(REPO / "src"), path, "25",
                 f"proc-{index}"],
                stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
            )
            for index in range(8)
        ]
        for proc in procs:
            _out, err = proc.communicate(timeout=120)
            assert proc.returncode == 0, err
        records = [
            json.loads(line)
            for line in Path(path).read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]
        assert len(records) == 200
        assert len({r["event_hash"] for r in records}) == 200
        chains.assert_chain_valid(path, hash_field="event_hash")


class TestLockOrder:
    def test_order_is_declared_shard_before_registry(self):
        assert LOCK_ORDER == ("shard", "registry")

    def test_reverse_order_is_refused(self, tmp_path):
        # acquiring "shard" while holding "registry" is the violation itself, so
        # the acquisition is the statement under test
        outer = kernel_lock(str(tmp_path / "registry.lock"), scope="registry")
        with outer, pytest.raises(LockError, match="lock order violation"), \
                kernel_lock(str(tmp_path / "shard.lock"), scope="shard"):
            pass

    def test_unknown_scope_is_refused(self, tmp_path):
        with pytest.raises(LockError, match="unknown lock scope"), \
                kernel_lock(str(tmp_path / "x.lock"), scope="whatever"):
            pass
