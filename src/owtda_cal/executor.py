"""The bounded shared executor for frozen plan units (task pack §3.3).

One executor drives TEST, smoke and formal work.  A unit is one item of the
frozen plan (optionally a batch of data/feature units) carrying its fixed
scientific id and its own seed stream; the executor never invents or renumbers
work.

The scheduling contract that was missing before:

* **bounded in-flight window** -- the formal plan is never handed to the pool in
  one call, because that would also hand it the whole commit charge;
* the window is relative to ``next_emit``, not to ``len(pending)``: a slow early
  unit must not permit unbounded accumulation of finished results;
* a latched stop (from the capacity monitor) stops *dispatch* immediately,
  cancels only tasks that have not begun, drains the running ones under a fixed
  grace rule, and **preserves every outcome** -- successes and errors alike;
* results are emitted in plan order, so the canonical ledger sees a prefix of
  the frozen plan rather than a completion-ordered subset.
"""

from __future__ import annotations

import concurrent.futures as _futures
import time
from collections.abc import Callable, Sequence
from concurrent.futures.process import BrokenProcessPool
from typing import Any

#: The error taxonomy of ``RESOURCE_POLICY_EXECUTABLE.json:enums.error_class``.
ERROR_CLASSES = (
    "RESOURCE_ALLOCATION_ERROR",
    "WORKER_EXIT",
    "IO_ERROR",
    "SAMPLER_ERROR",
    "TASK_EXCEPTION",
    "CANCELLED_BEFORE_START",
    "RESOURCE_STOP",
)

TERMINAL_STATES = ("COMPLETE", "INCOMPLETE", "FAILED", "REFUSED")


class ExecutorError(RuntimeError):
    """Executor contract violation."""


def classify_error(exc: BaseException) -> str:
    """Map one exception to a registered error class (§3.4)."""
    if isinstance(exc, _futures.CancelledError) or isinstance(exc, CancelledBeforeStart):
        return "CANCELLED_BEFORE_START"
    if isinstance(exc, MemoryError):
        return "RESOURCE_ALLOCATION_ERROR"
    if isinstance(exc, (BrokenProcessPool, _futures.BrokenExecutor)):
        return "WORKER_EXIT"
    if isinstance(exc, OSError):
        return "RESOURCE_ALLOCATION_ERROR" if exc.errno in (12, 11) else "IO_ERROR"
    if type(exc).__name__.endswith("SamplerError") or "sampler" in type(exc).__name__.lower():
        return "SAMPLER_ERROR"
    return "TASK_EXCEPTION"


class CancelledBeforeStart(RuntimeError):
    """Raised for a unit that was cancelled before it ever began."""


def _outcome(
    *,
    index: int,
    status: str,
    payload: Any = None,
    error_class: str | None = None,
    error_detail: str | None = None,
    started: bool = True,
) -> dict[str, Any]:
    return {
        "index": index,
        "status": status,
        "payload": payload,
        "error_class": error_class,
        "error_detail": error_detail,
        "started": started,
    }


def execute_units(
    units: Sequence[Any],
    *,
    submit: Callable[[Any, int], "_futures.Future"],
    monitor: Any | None = None,
    window_size: int = 8,
    poll_interval: float = 0.1,
    grace_seconds: float = 60.0,
) -> dict[str, Any]:
    """Run the frozen plan through one bounded window; return every outcome.

    ``submit(unit, index)`` returns a ``Future``; the caller owns the pool.  When
    ``monitor`` is given it must expose ``stop_requested`` (a
    ``threading.Event``); once set, no further unit is dispatched.
    """
    if window_size < 1:
        raise ExecutorError("window_size must be at least 1")
    number_of_units = len(units)

    next_emit = 0
    next_submit = 0
    pending: dict[Any, int] = {}
    completed: dict[int, dict[str, Any]] = {}
    stop_latched = False
    stop_reason = "NONE"
    emitted: list[dict[str, Any]] = []
    records: list[dict[str, Any]] = []
    max_in_flight = 0

    def _stop_requested() -> bool:
        event = getattr(monitor, "stop_requested", None)
        return bool(event is not None and event.is_set())

    def _classify(future: Any, index: int) -> dict[str, Any]:
        try:
            return _outcome(index=index, status="COMPLETED", payload=future.result())
        except Exception as exc:  # noqa: BLE001 - every failure is classified
            return _outcome(
                index=index, status="FAILED", error_class=classify_error(exc),
                error_detail=f"{type(exc).__name__}: {exc}",
            )

    while pending or next_submit < number_of_units:
        if not stop_latched and _stop_requested():
            stop_latched = True
            stop_reason = "RESOURCE_STOP"

        while (
            not stop_latched
            and next_submit < number_of_units
            and next_submit < next_emit + window_size
        ):
            index = next_submit
            pending[submit(units[index], index)] = index
            next_submit += 1
        max_in_flight = max(max_in_flight, len(pending))

        if not pending:
            # Nothing running: either the plan is exhausted or dispatch is latched.
            if next_submit >= number_of_units:
                break
            if stop_latched:
                break
            time.sleep(poll_interval)
            continue

        done, _not_done = _futures.wait(
            list(pending), timeout=poll_interval, return_when=_futures.FIRST_COMPLETED
        )
        for future in done:
            index = pending.pop(future)
            completed[index] = _classify(future, index)

        while next_emit in completed:
            outcome = completed.pop(next_emit)
            emitted.append(outcome)
            records.append(outcome)
            next_emit += 1

        if stop_latched:
            # Cancel only what has not begun; drain the rest and keep their outcomes.
            for future in list(pending):
                if future.cancel():
                    index = pending.pop(future)
                    outcome = _outcome(
                        index=index, status="CANCELLED_BEFORE_START",
                        error_class="CANCELLED_BEFORE_START",
                        error_detail="cancelled before start by a latched stop",
                        started=False,
                    )
                    completed[index] = outcome
            if pending:
                settled, still_running = _futures.wait(
                    list(pending), timeout=grace_seconds,
                    return_when=_futures.ALL_COMPLETED,
                )
                for future in settled:
                    index = pending.pop(future)
                    completed[index] = _classify(future, index)
                for future in still_running:
                    index = pending.pop(future)
                    future.cancel()
                    completed[index] = _outcome(
                        index=index, status="FAILED", error_class="WORKER_EXIT",
                        error_detail="still running after the grace period; "
                                     "referred to the process supervisor",
                    )
            while next_emit in completed:
                outcome = completed.pop(next_emit)
                emitted.append(outcome)
                records.append(outcome)
                next_emit += 1
            break

    for index in range(next_submit, number_of_units):
        records.append(_outcome(
            index=index, status="CANCELLED_BEFORE_START",
            error_class="RESOURCE_STOP" if stop_latched else "CANCELLED_BEFORE_START",
            error_detail="never dispatched" + (" (stop latched)" if stop_latched else ""),
            started=False,
        ))

    failed = [r for r in records if r["status"] != "COMPLETED"]
    if stop_latched:
        terminal = "FAILED" if any(r["error_class"] not in (
            "RESOURCE_STOP", "CANCELLED_BEFORE_START") for r in failed) else "INCOMPLETE"
    elif failed:
        terminal = "FAILED"
    elif len(emitted) != number_of_units:
        terminal = "INCOMPLETE"
    else:
        terminal = "COMPLETE"

    return {
        "terminal_state": terminal,
        "stop_latched": stop_latched,
        "stop_reason": stop_reason,
        "number_of_units": number_of_units,
        "emitted": emitted,               # in plan order: the canonical ledger
        "records": records,               # every attempt, including failures
        "max_in_flight": max_in_flight,
        "completed": sum(1 for r in records if r["status"] == "COMPLETED"),
        "failed": len([r for r in records if r["status"] == "FAILED"]),
        "cancelled": len([r for r in records if r["status"] == "CANCELLED_BEFORE_START"]),
        "errors_by_class": {
            cls: len([r for r in records if r.get("error_class") == cls])
            for cls in ERROR_CLASSES
        },
    }


__all__ = [
    "CancelledBeforeStart",
    "ERROR_CLASSES",
    "ExecutorError",
    "TERMINAL_STATES",
    "classify_error",
    "execute_units",
]
