"""Run-level resource evidence (audit A08).

Every resource claim must be bound to **the same run** it describes.  Before this
module the only sampling lived in the w* confirmation sweep, so the smoke seals
carried counts and wall time but no memory, swap or disk evidence -- the audited
``workers=8`` NULL record still showed a swap increase that nothing in the G3
chain could see.

One sampler is shared by all callers:

* peak **process-tree** RSS (the run's own demand, not the host's),
* system page-file delta, recorded together with its measurement caveat (the page
  file is host-wide, so unrelated host activity can move it),
* disk free before/after and the bytes actually written under the evidence root.

The thresholds are the frozen ones, quoted rather than restated::

    COMPUTE_SPEC_v1.parallelism_contract.acceptance.peak_total_rss_gib_max = 24
    COMPUTE_SPEC_v1.parallelism_contract.acceptance.swap_growth_bytes_max  = 0
    COMPUTE_SPEC_v1.budget_limits.disk_rule = estimated_peak_disk <= 0.8 * F_free
"""

from __future__ import annotations

import ctypes
import json
import os
import threading
import time
from collections.abc import Callable
from pathlib import Path
from typing import Any

SAMPLE_INTERVAL_S = 0.25
CAPACITY_INTERVAL_S = 1.0
#: A gap beyond this multiple of the interval makes the capacity record INCOMPLETE.
CAPACITY_MAX_GAP_FACTOR = 3.0
GIB = 1024**3
POLICY_PATH = Path(__file__).resolve().parents[1] / "governance/RESOURCE_POLICY_V2.json"


def load_resource_policy() -> dict[str, Any]:
    """The V2 resource contract (capacity + complete execution)."""
    return json.loads(POLICY_PATH.read_text(encoding="utf-8"))


class _PERFORMANCE_INFORMATION(ctypes.Structure):
    _fields_ = [
        ("cb", ctypes.c_ulong),
        ("CommitTotal", ctypes.c_size_t),
        ("CommitLimit", ctypes.c_size_t),
        ("CommitPeak", ctypes.c_size_t),
        ("PhysicalTotal", ctypes.c_size_t),
        ("PhysicalAvailable", ctypes.c_size_t),
        ("SystemCache", ctypes.c_size_t),
        ("KernelTotal", ctypes.c_size_t),
        ("KernelPaged", ctypes.c_size_t),
        ("KernelNonpaged", ctypes.c_size_t),
        ("PageSize", ctypes.c_size_t),
        ("HandleCount", ctypes.c_ulong),
        ("ProcessCount", ctypes.c_ulong),
        ("ThreadCount", ctypes.c_ulong),
    ]


def performance_info() -> dict[str, int] | None:
    """Windows host capacity counters; ``None`` when they cannot be read.

    ``CommitPeak`` is a since-boot peak: recorded, never used as this run's peak.
    Absence is reported, never defaulted to zero.
    """
    if os.name != "nt":
        return None
    try:
        info = _PERFORMANCE_INFORMATION()
        info.cb = ctypes.sizeof(_PERFORMANCE_INFORMATION)
        ok = ctypes.windll.psapi.GetPerformanceInfo(ctypes.byref(info), info.cb)
        page = int(info.PageSize)
    except Exception:  # noqa: BLE001 - absence is a finding, not a zero
        return None
    if not ok or page <= 0:
        return None
    return {
        "commit_total_bytes": int(info.CommitTotal) * page,
        "commit_limit_bytes": int(info.CommitLimit) * page,
        "commit_peak_bytes_since_boot": int(info.CommitPeak) * page,
        "physical_total_bytes": int(info.PhysicalTotal) * page,
        "physical_available_bytes": int(info.PhysicalAvailable) * page,
        "page_size_bytes": page,
    }
COMPUTE_SPEC = Path(__file__).resolve().parents[1] / "governance/COMPUTE_SPEC_v1.json"
LIMITS_SOURCE = "governance/COMPUTE_SPEC_v1.json:parallelism_contract.acceptance"


def acceptance_limits(compute_spec: dict[str, Any]) -> dict[str, Any]:
    """The frozen resource acceptance limits, taken from the compute spec."""
    contract = compute_spec["parallelism_contract"]["acceptance"]
    return {
        "peak_total_rss_gib_max": float(contract["peak_total_rss_gib_max"]),
        "swap_growth_bytes_max": int(contract["swap_growth_bytes_max"]),
        "unexplained_errors_max": int(contract["unexplained_errors_max"]),
        "disk_rule": compute_spec["budget_limits"]["disk_rule"],
        "source": LIMITS_SOURCE,
    }


def load_limits() -> dict[str, Any]:
    return acceptance_limits(json.loads(COMPUTE_SPEC.read_text(encoding="utf-8")))


def disk_free_bytes(path: Path) -> int:
    import shutil

    return int(shutil.disk_usage(str(path)).free)


def tree_bytes(root: Path) -> int:
    return sum(p.stat().st_size for p in root.rglob("*") if p.is_file())


def own_pagefile_bytes(proc: Any) -> int | None:
    """Page-file bytes charged to **this process tree** (the run's own demand).

    ``psutil.Process.memory_info()`` exposes ``pagefile`` on Windows; elsewhere the
    attribute is absent and the instrument is reported as unavailable, which makes
    the acceptance check fail closed rather than silently pass.

    Audit A08 / AM_RESOURCE_INSTRUMENT: the acceptance condition is about the run's
    *own* memory demand.  The machine-wide page-file total (``psutil.swap_memory``)
    moves with unrelated host activity -- the same code on the same host recorded
    0 bytes for the 1100 s NULL phase and 1.5 MB for the 312 s ALT phase -- so it is
    recorded as context only and is never the basis of a verdict.
    """
    import psutil

    total = 0
    available = False
    for candidate in (proc, *proc.children(recursive=True)):
        try:
            value = getattr(candidate.memory_info(), "pagefile", None)
        except psutil.Error:
            continue
        if value is None:
            continue
        available = True
        total += int(value)
    return total if available else None


def sample_run(
    runner: Callable[..., Any], *, evidence_root: Path, **kwargs: Any
) -> tuple[Any, dict[str, Any]]:
    """Run ``runner(**kwargs)`` while sampling the resources that run consumes.

    Alongside the process-level quantities this samples the **host capacity** counters
    the V2 policy is built on (``GetPerformanceInfo``: commit total/limit, physical
    total/available) once per second, and reports them as sampled peak/valley together
    with the sample count and the largest gap.  A missing field or a sampling gap is
    reported as ``incomplete`` -- it is never filled with a zero and passed.
    """
    import psutil

    proc = psutil.Process()
    samples: list[int] = []
    swap_before = int(psutil.swap_memory().used)
    swap_peak = swap_before
    own_before = own_pagefile_bytes(proc)
    own_peak = own_before
    free_before = disk_free_bytes(evidence_root)
    bytes_before = tree_bytes(evidence_root)
    stop = threading.Event()
    # Integers only: this record is embedded in the seal, whose hash is canonical and
    # in which bare floats are forbidden.  Ratios are derived by the verdict.
    capacity: dict[str, Any] = {
        "source": "GetPerformanceInfo",
        "interval_milliseconds": int(CAPACITY_INTERVAL_S * 1000),
        "samples": 0, "missing": 0, "max_gap_milliseconds": 0,
        "physical_available_min_bytes": None, "physical_total_bytes": None,
        "commit_limit_bytes": None, "commit_total_peak_bytes": None,
        "commit_total_min_bytes": None,
    }
    last_capacity_at = 0.0

    def sampler() -> None:
        nonlocal swap_peak, own_peak, last_capacity_at
        while not stop.is_set():
            total = int(proc.memory_info().rss)
            for child in proc.children(recursive=True):
                try:
                    total += int(child.memory_info().rss)
                except psutil.Error:
                    pass
            samples.append(total)
            swap_peak = max(swap_peak, int(psutil.swap_memory().used))
            current = own_pagefile_bytes(proc)
            if current is not None:
                own_peak = max(own_peak or 0, current)
            now = time.time()
            if now - last_capacity_at >= CAPACITY_INTERVAL_S:
                if last_capacity_at:
                    gap_ms = round((now - last_capacity_at) * 1000)
                    capacity["max_gap_milliseconds"] = max(
                        capacity["max_gap_milliseconds"], gap_ms
                    )
                last_capacity_at = now
                info = performance_info()
                if info is None:
                    capacity["missing"] += 1
                else:
                    capacity["samples"] += 1
                    total_c = info["commit_total_bytes"]
                    available = info["physical_available_bytes"]
                    capacity["commit_total_peak_bytes"] = max(
                        capacity["commit_total_peak_bytes"] or 0, total_c
                    )
                    capacity["commit_total_min_bytes"] = (
                        total_c if capacity["commit_total_min_bytes"] is None
                        else min(capacity["commit_total_min_bytes"], total_c)
                    )
                    capacity["physical_available_min_bytes"] = (
                        available if capacity["physical_available_min_bytes"] is None
                        else min(capacity["physical_available_min_bytes"], available)
                    )
                    capacity["physical_total_bytes"] = info["physical_total_bytes"]
                    capacity["commit_limit_bytes"] = info["commit_limit_bytes"]
            stop.wait(SAMPLE_INTERVAL_S)

    thread = threading.Thread(target=sampler, daemon=True)
    thread.start()
    started = time.time()
    try:
        result = runner(**kwargs)
    finally:
        stop.set()
        thread.join(timeout=2.0)

    own_after = own_pagefile_bytes(proc)
    peak = max(samples) if samples else None
    bytes_after = tree_bytes(evidence_root)
    # NOTE: this record is embedded in the seal, and the seal hash is taken over a
    # *canonical* payload in which bare floats are forbidden.  Everything here is
    # therefore int/str/None only; the GiB figure is derived by the checks.
    resources: dict[str, Any] = {
        "schema_version": 1,
        "kind": "run_resources_v1",
        "measured_wall_milliseconds": round((time.time() - started) * 1000),
        "peak_total_rss_bytes": peak,
        # Diagnostic (NOT an acceptance condition): the run's private *commit
        # charge*.  Windows ``PROCESS_MEMORY_COUNTERS_EX.PagefileUsage`` is the process
        # commit charge, not page-file writes.
        #
        # Three quantities must not be conflated: reserved address space
        # (MEM_RESERVE: no commitment), commit charge (MEM_COMMIT: the system has
        # promised the storage), and working set (what is resident now).  Measured on
        # the S04 runs: commit ~8.5-9.1 GiB against ~1.05 GiB peak RSS.  The *cause* of
        # that gap is NOT localised by these numbers: it cannot be attributed to the
        # numeric libraries, and it cannot be used to rule out growth that accumulates
        # with the workload.  Recorded for the capacity discussion; the field is named
        # for what it measures (AM_RESOURCE_MEASUREMENT_SEMANTICS).
        "own_commit_charge_instrument": (
            "psutil.Process.memory_info().pagefile summed over the process tree "
            "(Windows: process commit charge, not page-file writes)"
        ),
        "own_commit_charge_before_bytes": own_before,
        "own_commit_charge_peak_bytes": own_peak,
        "own_commit_charge_after_bytes": own_after,
        "own_commit_charge_growth_bytes": (
            None if own_before is None or own_peak is None
            else int(own_peak) - int(own_before)
        ),
        # Acceptance basis: machine-wide page-file growth during the run, i.e. the
        # declared "no swap growth" condition, unchanged.  The number is sensitive to
        # unrelated host activity; that sensitivity is disclosed, not engineered away.
        "host_swap_before_bytes": swap_before,
        "host_swap_peak_bytes": swap_peak,
        "host_swap_growth_bytes": swap_peak - swap_before,
        "host_swap_measurement_caveat": (
            "machine-wide page file *usage*: capacity, current usage, cumulative I/O and "
            "process commit are distinct quantities, so zero net change over the window "
            "does not prove that no paging occurred; the number is also sensitive to "
            "unrelated host activity. This is the declared condition and its limits are "
            "disclosed rather than overclaimed"
        ),
        "evidence_root": str(evidence_root),
        "disk_free_before_bytes": free_before,
        "evidence_bytes_before": bytes_before,
        "evidence_bytes_after": bytes_after,
        "evidence_bytes_written": bytes_after - bytes_before,
        "samples": len(samples),
        "sample_interval_milliseconds": int(SAMPLE_INTERVAL_S * 1000),
        # V2 capacity record (hard conditions live on these; page-file usage below is
        # diagnostic only).  Missing samples or a gap -> incomplete, never a zero.
        "capacity_sampling": {
            **capacity,
            "incomplete": bool(
                capacity["missing"]
                or capacity["samples"] == 0
                or capacity["max_gap_milliseconds"]
                > CAPACITY_INTERVAL_S * CAPACITY_MAX_GAP_FACTOR * 1000
            ),
        },
        "resource_allocation_failures": None,  # set by the runner once errors are known
    }
    return result, resources


def finalize_persistence(resources: dict[str, Any], *, evidence_root: Path) -> dict[str, Any]:
    """Re-measure the evidence root **after** the run's artifacts were written.

    Re-audit 2026-09-12: the sampler wrapped only the compute step, so
    ``evidence_bytes_written`` read 0 while the phase ledgers were 3.5 MB / 1.0 MB --
    the disk evidence did not cover what the run persisted, which is exactly what the
    frozen disk rule is about.  Call this once the ledger (and any other run output)
    is on disk, before the record is sealed.
    """
    after = tree_bytes(evidence_root)
    before = int(resources.get("evidence_bytes_before") or 0)
    resources["evidence_bytes_after"] = after
    resources["evidence_bytes_written"] = after - before
    resources["persistence_included"] = True
    return resources


def resource_verdict(
    resources: dict[str, Any] | None, *, limits: dict[str, Any], unexplained_errors: int
) -> dict[str, Any]:
    """Evaluate one run's resources against the frozen limits (fail closed).

    Acceptance uses the **declared** quantities only: peak total RSS, machine-wide
    page-file growth ("no swap growth"), unexplained errors and the disk rule.  The
    run's private commit charge is reported under ``diagnostics`` -- it is a real
    number about the run, but it is *not* paging activity and therefore cannot
    decide admission (AM_RESOURCE_MEASUREMENT_SEMANTICS).
    """
    if not resources:
        return {
            "limits": limits,
            "observed": None,
            "checks": {"resources_recorded": False},
            "diagnostics": {},
            "passed": False,
        }
    peak_bytes = resources.get("peak_total_rss_bytes")
    peak = (peak_bytes / GIB) if isinstance(peak_bytes, int) else None
    host_growth = resources.get("host_swap_growth_bytes")
    commit_growth = resources.get("own_commit_charge_growth_bytes")
    written = resources.get("evidence_bytes_written")
    free = resources.get("disk_free_before_bytes")
    checks = {
        "resources_recorded": True,
        "peak_total_rss_within_limit": bool(
            peak is not None and peak <= limits["peak_total_rss_gib_max"]
        ),
        "host_swap_growth_within_limit": bool(
            host_growth is not None
            and host_growth <= limits["swap_growth_bytes_max"]
        ),
        "unexplained_errors_within_limit": bool(
            unexplained_errors <= limits["unexplained_errors_max"]
        ),
        "disk_rule": bool(
            written is not None and free and written <= 0.8 * free
        ),
    }
    return {
        "limits": limits,
        "observed": {
            "peak_total_rss_gib": peak,
            "host_swap_growth_bytes": host_growth,
            "evidence_bytes_written": written,
            "disk_free_before_bytes": free,
            "unexplained_errors": unexplained_errors,
        },
        "checks": checks,
        "diagnostics": {
            "own_commit_charge_growth_bytes": commit_growth,
            "own_commit_charge_instrument": resources.get(
                "own_commit_charge_instrument"
            ),
            "note": (
                "commit charge is not paging activity and is never an acceptance "
                "condition; it is recorded for the memory-budget discussion"
            ),
            "host_swap_measurement_caveat": resources.get(
                "host_swap_measurement_caveat"
            ),
        },
        "passed": all(checks.values()),
    }
