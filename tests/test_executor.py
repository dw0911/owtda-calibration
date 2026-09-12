"""The bounded shared executor (task pack §3.3, §3.4).

The contract: dispatch is bounded, results are emitted in plan order, a latched
stop halts dispatch without discarding what is already in flight, and every
failure carries a registered error class.
"""

from __future__ import annotations

import threading
import time
from concurrent import futures

import pytest

from owtda_cal.executor import (
    ERROR_CLASSES,
    ExecutorError,
    classify_error,
    execute_units,
)


class _Monitor:
    def __init__(self) -> None:
        self.stop_requested = threading.Event()


def _pool(workers: int = 4):
    return futures.ThreadPoolExecutor(max_workers=workers)


class TestHappyPath:
    def test_every_unit_completes_in_plan_order(self):
        units = list(range(20))
        with _pool() as pool:
            result = execute_units(units, submit=lambda unit, index: pool.submit(
                lambda: (time.sleep(0.01 * ((index * 7) % 5)), unit)[1]
            ), window_size=4, poll_interval=0.01)
        assert result["terminal_state"] == "COMPLETE"
        assert [o["payload"] for o in result["emitted"]] == units
        assert result["completed"] == 20
        assert result["failed"] == 0

    def test_order_is_plan_order_not_completion_order(self):
        """A slow first unit must not reorder the ledger."""
        units = [0, 1, 2, 3]
        with _pool() as pool:
            result = execute_units(
                units,
                submit=lambda unit, index: pool.submit(
                    lambda: time.sleep(0.2 if index == 0 else 0.01) or unit
                ),
                window_size=4, poll_interval=0.01,
            )
        assert [o["payload"] for o in result["emitted"]] == units

    def test_the_window_bounds_in_flight_work(self):
        in_flight = {"now": 0, "peak": 0}
        lock = threading.Lock()

        def work(unit):
            with lock:
                in_flight["now"] += 1
                in_flight["peak"] = max(in_flight["peak"], in_flight["now"])
            time.sleep(0.02)
            with lock:
                in_flight["now"] -= 1
            return unit

        with _pool(workers=8) as pool:
            result = execute_units(list(range(40)),
                                   submit=lambda unit, index: pool.submit(work, unit),
                                   window_size=3, poll_interval=0.005)
        assert result["terminal_state"] == "COMPLETE"
        assert in_flight["peak"] <= 3
        assert result["max_in_flight"] <= 3

    def test_an_empty_plan_terminates_immediately(self):
        with _pool() as pool:
            result = execute_units([], submit=lambda unit, index: pool.submit(lambda: unit))
        assert result["terminal_state"] == "COMPLETE"
        assert result["emitted"] == []


class TestFailures:
    def test_a_failing_unit_is_recorded_with_a_class(self):
        def work(unit):
            if unit == 3:
                raise ValueError("boom")
            return unit

        with _pool() as pool:
            result = execute_units(list(range(6)),
                                   submit=lambda unit, index: pool.submit(work, unit),
                                   window_size=2, poll_interval=0.01)
        assert result["terminal_state"] == "FAILED"
        failed = [r for r in result["records"] if r["status"] == "FAILED"]
        assert len(failed) == 1
        assert failed[0]["error_class"] == "TASK_EXCEPTION"
        assert "ValueError" in failed[0]["error_detail"]
        assert result["completed"] == 5

    def test_failures_do_not_drop_the_successful_payloads(self):
        def work(unit):
            if unit % 2:
                raise OSError(5, "io")
            return unit

        with _pool() as pool:
            result = execute_units(list(range(10)),
                                   submit=lambda unit, index: pool.submit(work, unit),
                                   window_size=4, poll_interval=0.01)
        assert [o["payload"] for o in result["emitted"] if o["status"] == "COMPLETED"] == [
            0, 2, 4, 6, 8
        ]
        assert result["errors_by_class"]["IO_ERROR"] == 5


class TestStopLatching:
    def test_a_latched_stop_halts_dispatch_and_preserves_in_flight(self):
        monitor = _Monitor()
        started = threading.Event()

        def work(unit):
            if unit == 0:
                started.set()
                time.sleep(0.15)
            return unit

        def submit(unit, index):
            return pool.submit(work, unit)

        with _pool(workers=4) as pool:
            watcher = threading.Thread(
                target=lambda: (started.wait(5), time.sleep(0.02),
                                monitor.stop_requested.set())
            )
            watcher.start()
            result = execute_units(list(range(50)), submit=submit, monitor=monitor,
                                   window_size=4, poll_interval=0.01, grace_seconds=5)
            watcher.join(timeout=10)
        assert result["stop_latched"] is True
        assert result["stop_reason"] == "RESOURCE_STOP"
        assert result["terminal_state"] == "INCOMPLETE"
        # nothing after the latch was dispatched, and what ran is still recorded
        assert result["completed"] >= 1
        assert result["cancelled"] >= 1
        assert result["completed"] + result["failed"] + result["cancelled"] == 50

    def test_units_cancelled_before_start_are_classified(self):
        monitor = _Monitor()
        monitor.stop_requested.set()  # latched before anything is dispatched
        with _pool() as pool:
            result = execute_units(list(range(5)),
                                   submit=lambda unit, index: pool.submit(lambda: unit),
                                   monitor=monitor, window_size=2, poll_interval=0.01)
        assert result["terminal_state"] == "INCOMPLETE"
        assert result["errors_by_class"]["RESOURCE_STOP"] == 5
        assert result["emitted"] == []

    def test_a_stop_that_follows_a_real_failure_is_failed(self):
        monitor = _Monitor()

        def work(unit):
            if unit == 0:
                raise MemoryError("cannot allocate")
            return unit

        with _pool(workers=2) as pool:
            def submit(unit, index):
                future = pool.submit(work, unit)
                if unit == 0:
                    future.add_done_callback(lambda _f: monitor.stop_requested.set())
                return future
            result = execute_units(list(range(20)), submit=submit, monitor=monitor,
                                   window_size=2, poll_interval=0.01)
        assert result["terminal_state"] == "FAILED"
        assert result["errors_by_class"]["RESOURCE_ALLOCATION_ERROR"] >= 1


class TestErrorTaxonomy:
    def test_classes_match_the_policy_enum(self):
        from owtda_cal.resource_policy import load_policy

        assert set(ERROR_CLASSES) == set(load_policy()["enums"]["error_class"])

    def test_classification(self):
        assert classify_error(MemoryError()) == "RESOURCE_ALLOCATION_ERROR"
        assert classify_error(OSError(12, "ENOMEM")) == "RESOURCE_ALLOCATION_ERROR"
        assert classify_error(OSError(5, "IO")) == "IO_ERROR"
        assert classify_error(ValueError("x")) == "TASK_EXCEPTION"
        assert classify_error(futures.CancelledError()) == "CANCELLED_BEFORE_START"

        class SamplerError(RuntimeError):
            pass

        assert classify_error(SamplerError("dead")) == "SAMPLER_ERROR"

    def test_broken_pool_is_a_worker_exit(self):
        from concurrent.futures.process import BrokenProcessPool

        assert classify_error(BrokenProcessPool("worker died")) == "WORKER_EXIT"


class TestContract:
    def test_window_size_must_be_positive(self):
        with pytest.raises(ExecutorError):
            execute_units([1], submit=lambda unit, index: None, window_size=0)
