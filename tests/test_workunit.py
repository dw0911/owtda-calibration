"""Contract tests for the shared work-unit dispatch (R4 block A/B seam).

The science is stubbed out on purpose: these tests pin *scheduling and recording*
semantics only -- order, stop-before-dispatch, retained in-flight results, and
attributable failures.  No PH calls, no scientific trial.
"""

from __future__ import annotations

import pytest

from owtda_cal.workunit import run_units


def _echo(payload: int) -> int:
    return payload * 10


def _boom(payload: int) -> int:
    if payload == 2:
        raise ValueError(f"unit {payload} disagrees")
    return payload


class _Monitor:
    """Monitor with an explicit stop latch and an optional trip counter."""

    def __init__(self, *, latch_now: bool = False, trip_after: int | None = None) -> None:
        self.latch_now = latch_now
        self.trip_after = trip_after
        self.polls = 0
        self.stop_requested = self

    def is_set(self) -> bool:
        if self.latch_now:
            return True
        self.polls += 1
        if self.trip_after is not None and self.polls >= self.trip_after:
            self.latch_now = True
            return True
        return False


class TestOrdering:
    def test_every_unit_runs_and_results_keep_submission_order(self):
        result = run_units([1, 2, 3, 4], func=_echo, workers=2)
        assert result.parts == [10, 20, 30, 40]
        assert result.completed == 4 and result.failed == 0
        assert result.not_dispatched == 0
        assert result.is_complete() is True
        assert result.terminal_state in ("COMPLETE", "OK", "DONE")

    def test_a_single_unit_still_goes_through_the_same_channel(self):
        result = run_units([7], func=_echo, workers=1, window=1)
        assert result.parts == [70] and result.is_complete() is True


class TestStopBeforeDispatch:
    def test_a_latched_stop_prevents_dispatch_and_is_accounted(self):
        result = run_units([1, 2, 3], func=_echo, workers=1,
                           monitor=_Monitor(latch_now=True))
        assert result.completed == 0
        assert result.not_dispatched == 3
        assert result.stop_latched is True
        assert result.stop_reason != "NONE"
        # a phase may not seal on this: the shortfall is visible, not silent
        assert result.is_complete() is False

    def test_a_mid_flight_stop_keeps_what_ran_and_skips_the_rest(self):
        result = run_units([1, 2, 3, 4, 5, 6], func=_echo, workers=1, window=1,
                           monitor=_Monitor(trip_after=3))
        assert result.completed >= 1
        assert result.not_dispatched >= 1
        assert result.completed + result.not_dispatched == 6
        ran = [p for p in result.parts if p is not None]
        assert ran == [p * 10 for p in range(1, len(ran) + 1)]


class TestFailuresAreAttributable:
    def test_a_raising_unit_is_classified_and_reported(self):
        """A failure latches the stop: later units are not dispatched, and the
        shortfall is recorded rather than hidden (re-audit 2026-09-16 fix #2)."""
        result = run_units([1, 2, 3], func=_boom, workers=1)
        assert result.completed == 1
        assert result.failed == 1
        assert result.not_dispatched == 1
        assert result.stop_latched is True
        assert result.errors_by_class.get("TASK_EXCEPTION") == 1
        failures = result.failures()
        assert len(failures) == 1
        assert "unit 2 disagrees" in (failures[0].get("error_detail") or "")
        assert result.is_complete() is False

    def test_invalid_worker_count_is_a_programming_error(self):
        with pytest.raises(ValueError):
            run_units([1], func=_echo, workers=0)


class TestPhaseRefusesToSealAShortRun:
    """A latched stop must make the phase fail closed, without running science.

    ``run_smoke_null`` now dispatches through the shared channel, so a monitor that
    is already latched records every unit as ``RESOURCE_STOP`` and the phase raises
    with its summary -- no unit is started, and no short result can be sealed.
    """

    def _governance(self):
        import json
        from pathlib import Path

        root = Path(__file__).resolve().parents[1] / "governance"
        manifest = root / "FREEZE_MANIFEST.json"
        seeds = root / "SEED_REGISTRY_v1.0.json"
        if not (manifest.is_file() and seeds.is_file()):
            pytest.skip("governance inputs are not present in this checkout")
        return (json.loads(manifest.read_text(encoding="utf-8")),
                json.loads(seeds.read_text(encoding="utf-8")))

    def test_a_latched_stop_stops_the_phase_before_any_unit_runs(self):
        from owtda_cal import smoke

        manifest, seeds = self._governance()
        with pytest.raises(RuntimeError) as excinfo:
            smoke.run_smoke_null(
                manifest=manifest, seed_registry=seeds, workers=2,
                replicate_limit=2, monitor=_Monitor(latch_now=True),
            )
        message = str(excinfo.value)
        assert "not_dispatched" in message
        assert "'completed': 0" in message
