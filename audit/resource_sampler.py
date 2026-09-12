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


def _tree_rss_bytes() -> int | None:
    """Process-tree RSS; ``None`` when the instrument is unavailable."""
    try:
        import psutil

        proc = psutil.Process()
        total = int(proc.memory_info().rss)
        for child in proc.children(recursive=True):
            try:
                total += int(child.memory_info().rss)
            except Exception:  # noqa: BLE001 - a dead child is reported, not zeroed
                return None
        return total
    except Exception:  # noqa: BLE001 - absence is a finding
        return None


class CapacityMonitor:
    """Raw-sample capacity monitor (task pack §3.2).

    What changed relative to the first implementation:

    * every sample is written to a **raw JSONL** file, one row per sample, with
      the commit total and the commit limit of *that* sample on the same row --
      the previous summary stored ``max_k C_k`` and separately overwrote the
      limit, so the ratio it reported was not ``max_k C_k / L_k``;
    * a failed read writes a row too (``ok=false``) instead of being dropped or
      turned into a zero;
    * sampling exceptions, thread exit, a missing boundary sample and a gap over
      the policy maximum latch ``INCOMPLETE`` **and** raise ``stop_requested``;
    * a capacity breach latches ``FAIL`` and raises ``stop_requested`` as well --
      a later good sample never clears it;
    * the interval comes from the policy and cannot be overridden per run, and
      the monitor stays alive through persistence, commit, merge and seal, not
      only through the compute step.
    """

    def __init__(
        self,
        *,
        run_id: str,
        raw_path: Path,
        policy: dict[str, Any] | None = None,
        stage: str = "compute",
    ) -> None:
        from owtda_cal.resource_policy import load_policy, policy_sha256

        self.policy = policy or load_policy()
        self.interval_ns = int(self.policy["sampling"]["interval_ns"])
        self.max_gap_ns = int(self.policy["sampling"]["max_interval_ns"])
        self.policy_sha256 = policy_sha256()
        self.run_id = run_id
        self.raw_path = Path(raw_path)
        self.stage = stage
        self.stop_requested = threading.Event()  # consumed by the executor
        self._stop = threading.Event()
        self._rows: list[dict[str, Any]] = []
        self._lock = threading.Lock()
        self._seq = 0
        self._thread: threading.Thread | None = None
        self._handle = None
        self._last_ns: int | None = None
        self._incomplete: list[str] = []
        self._breaches: list[dict[str, Any]] = []
        self._boundary = {"start": False, "end": False}

    # -- lifecycle --------------------------------------------------------- #
    def __enter__(self) -> CapacityMonitor:  # noqa: PYI034 - explicit return type
        self.start()
        return self

    def __exit__(self, *exc: object) -> bool:
        self.stop()
        return False

    def start(self) -> None:
        self.raw_path.parent.mkdir(parents=True, exist_ok=True)
        # The handle stays open for the whole stage -- sampling must not reopen
        # the file per sample, and the rows must keep their append order.
        self._handle = open(self.raw_path, "a", encoding="utf-8")  # noqa: SIM115
        self._write_sample(stage="start")
        if self._rows and self._rows[-1].get("ok") is True:
            self._boundary["start"] = True
        else:
            self._latch_incomplete("boundary_sample_missing:start")
        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()

    def set_stage(self, stage: str) -> None:
        with self._lock:
            self.stage = stage

    def stop(self) -> dict[str, Any]:
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=2.0)
            if self._thread.is_alive():
                self._latch_incomplete("sampler_thread_exit")
        self._write_sample(stage="teardown")
        if self._rows and self._rows[-1].get("ok") is True:
            self._boundary["end"] = True
        else:
            self._latch_incomplete("boundary_sample_missing:end")
        if self._handle is not None:
            self._handle.flush()
            os.fsync(self._handle.fileno())
            self._handle.close()
            self._handle = None
        return self.summary()

    # -- sampling ---------------------------------------------------------- #
    def _loop(self) -> None:
        try:
            while not self._stop.is_set():
                self._write_sample(stage=self.stage)
                self._stop.wait(self.interval_ns / 1e9)
        except Exception as exc:  # noqa: BLE001 - the thread must not die silently
            self._latch_incomplete(f"sampler_exception:{type(exc).__name__}")
            self.stop_requested.set()

    def _write_sample(self, *, stage: str) -> None:
        from owtda_cal.resource_policy import inspect_row

        now_ns = time.monotonic_ns()
        try:
            info = performance_info()
            rss = _tree_rss_bytes()
            if info is None or rss is None:
                raise RuntimeError(
                    "capacity counters unavailable"
                    if info is None else "rss_tree unavailable"
                )
            row = {
                "schema_version": 1,
                "run_id": self.run_id,
                "policy_sha256": self.policy_sha256,
                "seq": self._seq,
                "monotonic_ns": now_ns,
                "ok": True,
                "error": None,
                "stage": stage,
                "commit_total_bytes": int(info["commit_total_bytes"]),
                "commit_limit_bytes": int(info["commit_limit_bytes"]),
                "physical_total_bytes": int(info["physical_total_bytes"]),
                "physical_available_bytes": int(info["physical_available_bytes"]),
                "rss_tree_bytes": int(rss),
            }
        except Exception as exc:  # noqa: BLE001 - a failed read is still a row
            row = {
                "schema_version": 1,
                "run_id": self.run_id,
                "policy_sha256": self.policy_sha256,
                "seq": self._seq,
                "monotonic_ns": now_ns,
                "ok": False,
                "error": f"SAMPLER_ERROR:{type(exc).__name__}",
                "stage": stage,
                "commit_total_bytes": None, "commit_limit_bytes": None,
                "physical_total_bytes": None, "physical_available_bytes": None,
                "rss_tree_bytes": None,
            }
        with self._lock:
            self._seq += 1
            self._rows.append(row)
            if self._handle is not None:
                self._handle.write(json.dumps(row, sort_keys=True) + "\n")
                self._handle.flush()
            previous = self._last_ns
            self._last_ns = now_ns
        if row["ok"] is False:
            self._latch_incomplete(f"sample_not_ok:{row['error']}")
        if previous is not None and now_ns - previous > self.max_gap_ns:
            self._latch_incomplete(f"gap_exceeds_max_interval_ns:{now_ns - previous}")
        if row["ok"] is True:
            seen = inspect_row(row, policy=self.policy)
            if seen["breaches"]:
                with self._lock:
                    self._breaches.extend(seen["breaches"])
                self.stop_requested.set()  # latch: never cleared

    def _latch_incomplete(self, reason: str) -> None:
        with self._lock:
            self._incomplete.append(reason)
        self.stop_requested.set()

    # -- reporting --------------------------------------------------------- #
    def rows(self) -> list[dict[str, Any]]:
        with self._lock:
            return list(self._rows)

    def verdict(self) -> dict[str, Any]:
        from owtda_cal.resource_policy import evaluate_capacity

        decision = evaluate_capacity(self.rows(), policy=self.policy)
        with self._lock:
            incomplete = list(self._incomplete)
            breaches = list(self._breaches)
        if incomplete or decision["issues"]:
            status = "INCOMPLETE"
        elif breaches or decision["breaches"]:
            status = "FAIL"
        else:
            status = "PASS"
        return {
            "status": status,
            "samples": decision["samples"],
            "ok_samples": decision["ok_samples"],
            "peak_commit_ratio": decision["peak_commit_ratio"],
            "breaches": breaches + decision["breaches"],
            "incomplete_reasons": incomplete,
            "issues": decision["issues"],
            "policy_sha256": self.policy_sha256,
            "raw_path": str(self.raw_path),
        }

    def summary(self) -> dict[str, Any]:
        return self.verdict()


def sample_run(
    runner: Callable[..., Any], *, evidence_root: Path, run_id: str = "run", **kwargs: Any
) -> tuple[Any, dict[str, Any]]:
    """Run ``runner(**kwargs)`` while sampling the resources that run consumes.

    Alongside the process-level quantities this samples the **host capacity** counters
    the V2 policy is built on (``GetPerformanceInfo``: commit total/limit, physical
    total/available) once per second, and reports them as sampled peak/valley together
    with the sample count and the largest gap.  A missing field or a sampling gap is
    reported as ``incomplete`` -- it is never filled with a zero and passed.

    Since 2026-09-13 every capacity sample is also written to a raw JSONL file by
    :class:`CapacityMonitor`, and the verdict is rebuilt from those rows (paired
    counters, integer cross-multiplication).  This helper still wraps *the compute
    step only*: a caller that needs the persistence, commit, merge and seal stages
    covered must keep one :class:`CapacityMonitor` open across all of them.
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
    raw_path = Path(evidence_root) / "resources" / "capacity_raw.jsonl"
    monitor = CapacityMonitor(run_id=run_id, raw_path=raw_path, stage="compute")
    monitor.start()
    started = time.time()
    try:
        result = runner(**kwargs)
    finally:
        stop.set()
        thread.join(timeout=2.0)
        monitor_verdict = monitor.stop()

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
                or monitor_verdict["status"] == "INCOMPLETE"
            ),
            # The authoritative record: every sample, both counters of a ratio on
            # the same row.  ``resource_verdict`` rebuilds the decision from it.
            "status": monitor_verdict["status"],
            "raw_path": str(raw_path),
            "raw_samples": monitor_verdict["samples"],
            "peak_commit_ratio": monitor_verdict["peak_commit_ratio"],
            "incomplete_reasons": monitor_verdict["incomplete_reasons"],
            "breaches": monitor_verdict["breaches"],
        },
        "capacity_raw_path": str(raw_path),
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


def _checks_from_raw_rows(resources: dict[str, Any]) -> dict[str, bool] | None:
    """Rebuild the four capacity checks from the raw JSONL rows, if they exist."""
    from owtda_cal.resource_policy import evaluate_capacity, load_policy

    raw_path = resources.get("capacity_raw_path")
    if not raw_path or not Path(raw_path).is_file():
        return None
    rows = [
        json.loads(line)
        for line in Path(raw_path).read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    decision = evaluate_capacity(rows, policy=load_policy())
    codes = {b["code"] for b in decision["breaches"]}
    return {
        "capacity_sampling_complete": decision["verdict"] != "INCOMPLETE",
        "host_commit_fraction_within_limit": "COMMIT_RATIO_BREACH" not in codes,
        "host_available_phys_within_minimum": "PHYSICAL_FLOOR_BREACH" not in codes,
        "peak_total_rss_within_limit": "RSS_BREACH" not in codes,
    }


def resource_verdict(
    resources: dict[str, Any] | None,
    *,
    unexplained_errors: int,
    limits: dict[str, Any] | None = None,
    policy: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Evaluate one run against AM_RESOURCE_CAPACITY_V2 (ruling 2026-09-13).

    Hard conditions are **capacity and complete execution**: peak RSS, host commit
    fraction, host available physical memory, resource-allocation failures, unexplained
    errors, the disk rule, and a *complete* capacity record.  Page-file usage, page
    faults and system paging rates are diagnostics and neither pass nor fail a run; the
    retired ``swap_growth_bytes_max = 0`` gate keeps its old records and old verdicts but
    has no future admission use.  A missing or gapped capacity record is INCOMPLETE, and
    INCOMPLETE never passes.
    """
    policy = policy or load_resource_policy()
    hard = policy["hard_conditions"]
    if not resources:
        return {
            "resource_policy_id": policy["resource_policy_id"],
            "observed": None,
            "checks": {"resources_recorded": False},
            "diagnostics": {},
            "status": "INCOMPLETE",
            "passed": False,
        }
    capacity = resources.get("capacity_sampling") or {}
    peak_bytes = resources.get("peak_total_rss_bytes")
    peak_gib = (peak_bytes / GIB) if isinstance(peak_bytes, int) else None
    commit_peak = capacity.get("commit_total_peak_bytes")
    commit_limit = capacity.get("commit_limit_bytes")
    fraction = (
        (commit_peak / commit_limit)
        if isinstance(commit_peak, int) and isinstance(commit_limit, int) and commit_limit
        else None
    )
    available = capacity.get("physical_available_min_bytes")
    physical_total = capacity.get("physical_total_bytes")
    physical_min_required = (
        max(2 * GIB, int(0.10 * physical_total))
        if isinstance(physical_total, int) and physical_total else None
    )
    # Re-audit 2026-09-13: when the raw per-sample rows exist, the hard capacity
    # checks are rebuilt from them (same-sample paired counters, integer compare)
    # instead of trusting the summary's own "incomplete" flag.
    raw_checks = _checks_from_raw_rows(resources)
    written = resources.get("evidence_bytes_written")
    free = resources.get("disk_free_before_bytes")
    allocation_failures = resources.get("resource_allocation_failures")
    checks = {
        "resources_recorded": True,
        "capacity_sampling_complete": capacity.get("incomplete") is False,
        "peak_total_rss_within_limit": bool(
            peak_gib is not None
            and peak_gib <= float(hard["peak_total_rss_gib_max"])
        ),
        "host_commit_fraction_within_limit": bool(
            isinstance(fraction, (int, float))
            and fraction <= float(hard["host_commit_fraction_max"])
        ),
        "host_available_phys_within_minimum": bool(
            isinstance(available, int)
            and physical_min_required is not None
            and available >= physical_min_required
        ),
        "resource_allocation_failures_within_limit": allocation_failures == 0,
        "unexplained_errors_within_limit": bool(
            unexplained_errors <= int(hard["unexplained_errors_max"])
        ),
        "disk_rule": bool(written is not None and free and written <= 0.8 * free),
    }
    if raw_checks is not None:
        checks.update(raw_checks)
    passed = all(checks.values())
    return {
        "resource_policy_id": policy["resource_policy_id"],
        "limits": {
            "peak_total_rss_gib_max": hard["peak_total_rss_gib_max"],
            "host_commit_fraction_max": hard["host_commit_fraction_max"],
            "host_available_phys_min_bytes": physical_min_required,
            "resource_allocation_failures_max": hard["resource_allocation_failures_max"],
            "disk_rule": hard["disk_rule"],
            "source": "governance/RESOURCE_POLICY_V2.json",
        },
        "observed": {
            "peak_total_rss_gib": peak_gib,
            "commit_total_peak_bytes": commit_peak,
            "commit_limit_bytes": commit_limit,
            "commit_fraction_peak": fraction,
            "physical_available_min_bytes": available,
            "physical_total_bytes": physical_total,
            "capacity_samples": capacity.get("samples"),
            "evidence_bytes_written": written,
            "disk_free_before_bytes": free,
            "unexplained_errors": unexplained_errors,
            "resource_allocation_failures": allocation_failures,
        },
        "checks": checks,
        "diagnostics": {
            "host_pagefile_used_growth_bytes": resources.get("host_swap_growth_bytes"),
            "host_pagefile_caveat": resources.get("host_swap_measurement_caveat"),
            "own_commit_charge_growth_bytes": resources.get("own_commit_charge_growth_bytes"),
            "note": (
                "diagnostic only under AM_RESOURCE_CAPACITY_V2: page-file usage, page "
                "faults and system paging rates neither pass nor fail a run"
            ),
        },
        "status": "PASS" if passed else "FAIL",
        "passed": passed,
    }
