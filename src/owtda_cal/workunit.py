"""Shared scientific work-unit dispatch (R4 block A/B seam).

Why this module exists
----------------------
The phase runners in :mod:`owtda_cal.smoke` call ``parallel.ordered_map`` directly,
which is a one-shot ``ProcessPoolExecutor.map``: it has no stop latch, no place for
the monitor to observe progress, and no per-unit failure record.  The generic
executor (:func:`owtda_cal.executor.execute_units`) already has the bounded window,
the stop latch and the error taxonomy, but nothing scientific went through it.

This is the single channel the audit asks for: TEST, smoke and formal dispatch their
units here, so the *same* code decides how work is scheduled, stopped and recorded.

Contract (what a caller may rely on)
------------------------------------
1. **Identity and bytes are not touched.**  ``func`` receives the payload the caller
   built; nothing here re-orders, re-serialises or re-seeds anything.  Payload
   bitwise identity across worker counts stays the science layer's property.
2. **Stop is checked before dispatch, never after.**  When the monitor requests a
   stop, units that have not started are recorded as ``RESOURCE_STOP`` and are *not*
   submitted; in-flight units are allowed to finish so their results are retained.
3. **Results are ordered and complete only if every unit ran.**  ``completed`` counts
   real completions; ``not_dispatched`` counts the latched remainder, so a phase can
   refuse to seal instead of quietly producing a short result.
4. **Every failure is attributable.**  Failures carry ``error_class`` and
   ``error_detail`` from the executor, and the phase seal can bind them.

This module deliberately does **not** decide anything scientific: it decides how
work is run and recorded.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from concurrent import futures
from typing import Any

from .executor import execute_units

__all__ = ["WorkUnitResult", "run_units"]


class _NullMonitor:
    """A monitor that never asks to stop (used when the caller passes none)."""

    class _Never:
        def is_set(self) -> bool:  # pragma: no cover - trivial
            return False

    def __init__(self) -> None:
        self.stop_requested = _NullMonitor._Never()


class WorkUnitResult:
    """Outcome of one phase's unit dispatch; no scientific interpretation."""

    def __init__(self, *, payloads: list[Any], outcome: dict[str, Any]) -> None:
        self._payloads = payloads
        self._outcome = outcome

    # -- accounted work --------------------------------------------------- #
    @property
    def parts(self) -> list[Any]:
        """Payloads in submission order; missing entries are ``None``."""
        return self._payloads

    @property
    def completed(self) -> int:
        return int(self._outcome.get("completed", 0))

    @property
    def failed(self) -> int:
        return int(self._outcome.get("failed", 0))

    @property
    def not_dispatched(self) -> int:
        return int(self._outcome.get("cancelled", 0))

    @property
    def stop_latched(self) -> bool:
        return bool(self._outcome.get("stop_latched"))

    @property
    def stop_reason(self) -> str:
        return str(self._outcome.get("stop_reason") or "NONE")

    @property
    def terminal_state(self) -> str:
        return str(self._outcome.get("terminal_state"))

    @property
    def errors_by_class(self) -> dict[str, int]:
        return dict(self._outcome.get("errors_by_class") or {})

    def failures(self) -> list[dict[str, Any]]:
        """Units that actually ran and failed.

        Units that were never dispatched are *not* failures: they are the latched
        remainder, counted by :attr:`not_dispatched` with class ``RESOURCE_STOP``.
        Keeping the two apart is what lets a seal say "we stopped" instead of
        "everything failed".
        """
        return [r for r in self._outcome.get("records", [])
                if r.get("status") == "FAILED"]

    def is_complete(self) -> bool:
        """True only when every unit ran and none failed (a seal precondition)."""
        return (
            self.terminal_state == "COMPLETE"
            and not self.stop_latched
            and self.completed == len(self._payloads)
            and self.failed == 0
            and self.not_dispatched == 0
        )

    def summary(self) -> dict[str, Any]:
        return {
            "units": len(self._payloads),
            "completed": self.completed,
            "failed": self.failed,
            "not_dispatched": self.not_dispatched,
            "stop_latched": self.stop_latched,
            "stop_reason": self.stop_reason,
            "terminal_state": self.terminal_state,
            "errors_by_class": self.errors_by_class,
            "all_units_ran": self.is_complete(),
        }


def run_units(
    payloads: Sequence[Any],
    *,
    func: Callable[[Any], Any],
    workers: int,
    monitor: Any | None = None,
    window: int | None = None,
    poll_interval: float = 0.05,
    max_in_flight: int | None = None,
) -> WorkUnitResult:
    """Dispatch ``payloads`` through the shared executor and record everything.

    ``workers`` bounds the process pool; ``window`` bounds how far ahead of the
    slowest unit new work may be submitted.  Both default to ``workers`` so the
    scheduling shape matches the historical ``ordered_map`` behaviour while gaining
    the stop latch and the per-unit records.
    """
    if workers < 1:
        raise ValueError("workers must be >= 1")
    size = len(payloads)
    window = workers if window is None else window
    if window < 1:
        raise ValueError("window must be >= 1")

    parts: list[Any] = [None] * size
    active = monitor if monitor is not None else _NullMonitor()
    limit = max(1, max_in_flight or workers)

    with futures.ProcessPoolExecutor(max_workers=limit) as pool:

        def submit(payload: Any, index: int) -> futures.Future:
            return pool.submit(func, payload)

        outcome = execute_units(
            list(payloads), submit=submit, monitor=active,
            window_size=window, poll_interval=poll_interval,
        )

    for record in outcome.get("records", []):
        if record.get("status") == "COMPLETED":
            parts[int(record["index"])] = record.get("payload")
    return WorkUnitResult(payloads=parts, outcome=outcome)
