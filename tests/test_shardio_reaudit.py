"""Re-audit 2026-09-12 shard regressions.

Two dangerous paths survived the first shard fix:

* a SHARD_COMMITTED record whose ``.final`` directory had been deleted fell through
  to the first-commit path, so repeating the submission appended a second record;
* ``allocate_attempt`` computed the number before reading the chain tip, so two
  callers could both return ``1``.

The commit-path regressions are executed by ``scripts/verify_shard_regressions.py``
in a clean subprocess (the pytest host here intercepts some file operations, which
made in-process assertions about a deleted directory unreliable).  The allocation
regressions are pure chain arithmetic and run in-process.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

from owtda_cal import chains
from owtda_cal.identity import H as _H
from owtda_cal.shardio import allocate_attempt

REPO = Path(__file__).resolve().parents[1]
REGRESSIONS = REPO / "scripts" / "verify_shard_regressions.py"
RUN = _H("reaudit_run")


def _records(registry: str) -> list[dict]:
    return [
        json.loads(line)
        for line in Path(registry).read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


@pytest.fixture(scope="module")
def outcome() -> dict:
    done = subprocess.run(
        [sys.executable, str(REGRESSIONS)],
        capture_output=True, text=True, encoding="utf-8", errors="replace",
        check=False,
    )
    return {"exit_code": done.returncode, "stdout": done.stdout, "stderr": done.stderr}


class TestCommitPathRegressions:
    """Delegates to the external regressions, which mirror the re-audit's probes."""

    def test_regressions_script_passes(self, outcome):
        assert outcome["exit_code"] == 0, outcome["stdout"] + outcome["stderr"]

    def test_all_four_paths_are_covered(self, outcome):
        for name in (
            "identical_recommit",
            "deleted_final_changed_content",
            "deleted_final_identical_content",
            "interleaved_attempt_allocation",
        ):
            assert f"[PASS] {name}" in outcome["stdout"], name

    def test_summary_reports_no_failure(self, outcome):
        summary = json.loads(outcome["stdout"].strip().splitlines()[-1])
        assert summary["checks"] == 4
        assert summary["failed"] == []


class TestAttemptAllocation:
    def test_monotonic_and_unique(self, tmp_path):
        registry = str(tmp_path / "attempts.jsonl")
        numbers = [allocate_attempt(registry, run_instance_id=RUN, evaluation_id=_H("e"))
                   for _ in range(4)]
        assert numbers == [1, 2, 3, 4]
        stored = [r["attempt_number"] for r in _records(registry)]
        assert stored == numbers
        assert len(set(stored)) == len(stored)

    def test_stale_snapshot_append_is_refused(self, tmp_path):
        """The guard the fix relies on: a CAS bound to a stale tip must fail."""
        registry = str(tmp_path / "attempts.jsonl")
        stale_tip = chains.read_tip(registry, hash_field="attempt_id")
        assert allocate_attempt(registry, run_instance_id=RUN, evaluation_id=_H("e")) == 1
        with pytest.raises(chains.ChainError):
            chains.append_cas(
                registry,
                {"schema_version": 1, "run_instance_id": RUN,
                 "evaluation_id": _H("e"), "attempt_number": 1},
                expected_tip=stale_tip, hash_field="attempt_id",
            )
        assert [r["attempt_number"] for r in _records(registry)] == [1]
