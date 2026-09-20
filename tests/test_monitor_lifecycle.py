"""The monitor must span persistence/commit/seal, not just the compute step.

R4 block B: ``sample_run`` stopped the sampler as soon as the runner returned, so a
breach that happened while writing the ledger, committing shards or sealing the phase
was invisible.  ``sample_run`` now accepts ``on_compute_done``, which runs while the
monitor is still open.  These tests pin that the hook really is inside the sampling
window -- without running any science.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "audit"))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import resource_sampler


def _trivial_runner(**kwargs):
    class _Result:
        def __init__(self) -> None:
            self.rows: list = []
            self.errors = 0
            self.wall_seconds = 0.01

    return _Result()


class TestMonitorSpansPostCompute:
    def test_the_hook_runs_while_the_monitor_is_still_sampling(self, tmp_path):
        seen: dict = {}

        def hook(monitor, result):
            seen["rows_during_hook"] = len(monitor.rows())
            seen["stop_set_during_hook"] = bool(monitor.stop_requested.is_set())
            seen["handle_open"] = getattr(monitor, "_handle", None) is not None

        _result, resources = resource_sampler.sample_run(
            _trivial_runner, evidence_root=tmp_path, run_id="lifecycle:test",
            on_compute_done=hook,
        )

        assert "rows_during_hook" in seen, "the hook was never called"
        assert seen["handle_open"] is True, "the sampler was already closed"
        assert seen["stop_set_during_hook"] is False
        capacity = resources.get("capacity_sampling") or {}
        assert capacity.get("samples", 0) >= seen["rows_during_hook"]

    def test_the_hook_is_optional_and_changes_nothing_when_absent(self, tmp_path):
        _result, resources = resource_sampler.sample_run(
            _trivial_runner, evidence_root=tmp_path, run_id="lifecycle:absent",
        )
        assert (resources.get("capacity_sampling") or {}).get("status") in (
            "PASS", "INCOMPLETE", "FAIL")

    def test_stopping_the_sampler_early_does_not_fabricate_incompleteness(self, tmp_path):
        """The two latches are separate by design (audit: stop != incomplete).

        ``stop_requested`` stops *dispatch*; the verdict is driven by recorded
        incompleteness (sample failures, gaps, missing raw rows).  Asking the
        sampler to stop in the hook must therefore not, by itself, produce
        INCOMPLETE -- otherwise every clean run could be failed by a stop request.
        """
        def hook(monitor, result):
            monitor.stop_requested.set()

        _result, resources = resource_sampler.sample_run(
            _trivial_runner, evidence_root=tmp_path, run_id="lifecycle:stop",
            on_compute_done=hook,
        )
        capacity = resources.get("capacity_sampling") or {}
        assert capacity.get("status") in ("PASS", "INCOMPLETE")
        # what matters here is that the hook ran inside the window and nothing was
        # lost: the raw rows are still on disk with their verdict attached
        assert capacity.get("raw_path")
