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
import hashlib
import json
import os
import threading
import time
from collections.abc import Callable, Sequence
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
        # A test policy with a shortened sampling interval has a distinct digest.
        # Never attribute altered policy contents to the registered file's hash.
        self.policy_sha256 = (policy_sha256() if self.policy == load_policy() else
            hashlib.sha256((json.dumps(self.policy, sort_keys=True, separators=(",", ":")) + "\n").encode()).hexdigest())
        self.run_id = run_id
        self.raw_path = Path(raw_path)
        self.stage = stage
        self.stop_requested = threading.Event()  # consumed by the executor
        self._stop = threading.Event()
        self._rows: list[dict[str, Any]] = []
        self._lock = threading.Lock()
        self._sample_lock = threading.RLock()
        self._seq = 0
        self._thread: threading.Thread | None = None
        self._handle = None
        self._last_ns: int | None = None
        self._incomplete: list[str] = []
        self._breaches: list[dict[str, Any]] = []
        self._boundary = {"start": False, "end": False}
        self._started = False
        self._closed = False

    # -- lifecycle --------------------------------------------------------- #
    def __enter__(self) -> CapacityMonitor:  # noqa: PYI034 - explicit return type
        self.start()
        return self

    def __exit__(self, *exc: object) -> bool:
        self.stop()
        return False

    def start(self) -> None:
        if self._started or self._closed:
            raise RuntimeError("capacity monitor cannot be started twice")
        if not isinstance(self.run_id, str) or not self.run_id.strip():
            raise ValueError("run identity is required")
        self.raw_path.parent.mkdir(parents=True, exist_ok=True)
        # The handle stays open for the whole stage -- sampling must not reopen
        # the file per sample, and the rows must keep their append order.
        self._handle = open(self.raw_path, "x", encoding="utf-8")  # noqa: SIM115
        self._started = True
        self._write_sample(stage="start")
        if self._rows and self._rows[-1].get("ok") is True:
            self._boundary["start"] = True
        else:
            self._latch_incomplete("boundary_sample_missing:start")
        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()

    def set_stage(self, stage: str) -> None:
        """Enter a new stage **and record the boundary in the raw stream**.

        R4 block B: stage labels only ride on emitted samples, so a caller that moves
        to "persist"/"seal" and finishes quickly leaves no evidence that the stage was
        covered at all -- a relabelled summary, not coverage.  Writing one boundary
        row per transition puts each stage's start into the raw file, which is what a
        seal can quote.
        """
        with self._sample_lock:
            with self._lock:
                previous, self.stage = self.stage, stage
            if stage != previous:
                self._write_sample(stage=stage)

    def stop(self) -> dict[str, Any]:
        if self._closed:
            return self.summary()
        if not self._started:
            raise RuntimeError("capacity monitor was not started")
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
        self._closed = True
        return self.summary()

    # -- sampling ---------------------------------------------------------- #
    def _loop(self) -> None:
        try:
            while not self._stop.is_set():
                self._write_sample()
                self._stop.wait(self.interval_ns / 1e9)
        except Exception as exc:  # noqa: BLE001 - the thread must not die silently
            self._latch_incomplete(f"sampler_exception:{type(exc).__name__}")
            self.stop_requested.set()

    def _write_sample(self, *, stage: str | None = None) -> None:
        with self._sample_lock:
            self._write_sample_serial(stage=self.stage if stage is None else stage)

    def _write_sample_serial(self, *, stage: str) -> None:
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

        decision = evaluate_capacity(self.rows(), policy=self.policy,
            expected_run_id=self.run_id, expected_policy_sha256=self.policy_sha256,
            require_boundaries=True)
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


def stage_coverage(
    rows: Sequence[dict[str, Any]],
    *,
    required: Sequence[str] = ("start", "compute", "persist", "teardown"),
) -> dict[str, Any]:
    """Report which stages the raw sample stream **actually** covers.

    R4 block B: a stage label only counts as coverage when a sample carrying it is
    present in the raw file.  A caller that intends to cover "persist" but emits no
    sample during it has relabelled a summary, not extended coverage -- which is
    exactly the difference the audit insists on.  Returns per stage the sample count
    and the row range, plus the stages that never appear, so a seal can refuse
    instead of quoting an intended-but-absent stage.
    """
    seen: dict[str, dict[str, int]] = {}
    for index, row in enumerate(rows):
        stage = str(row.get("stage") or "")
        entry = seen.get(stage)
        if entry is None:
            seen[stage] = {"samples": 1, "first_row": index, "last_row": index}
        else:
            entry["samples"] += 1
            entry["last_row"] = index
    missing = [stage for stage in required if stage not in seen]
    return {
        "required": list(required),
        "stages": seen,
        "missing": missing,
        "complete": not missing,
        "rows": len(rows),
    }


class ResourceStageCoverageError(RuntimeError):
    """Raised when a phase's raw stream does not cover the required stages."""


def assert_stage_coverage(
    rows: Sequence[dict[str, Any]],
    *,
    phase: str,
    required: Sequence[str] = ("start", "compute", "persist", "teardown"),
) -> dict[str, Any]:
    """Return the coverage report, or refuse with an **attributable** error.

    R4 block B: sealing a phase whose stages were not observed would imply coverage
    the raw stream does not support.  The refusal names the missing stages, so the
    shortfall can be attributed instead of surfacing as a generic failure -- and the
    gate is callable on its own, which is what makes the refusal testable without
    running a smoke.
    """
    coverage = stage_coverage(rows, required=required)
    if not coverage["complete"]:
        raise ResourceStageCoverageError(
            f"{phase}: the raw stream does not cover {coverage['missing']}; refusing to "
            "seal a phase whose resource stages were not observed"
        )
    return coverage


FULL_LIFECYCLE_STAGES: tuple[str, ...] = (
    "start", "compute", "persist", "commit", "seal", "cleanup", "teardown",
)


def merge_final_verdict(
    resources: dict[str, Any],
    verdict: dict[str, Any],
    *,
    observed_stages: Sequence[str],
    required_stages: Sequence[str] = FULL_LIFECYCLE_STAGES,
) -> dict[str, Any]:
    """Close a provisional capacity record with the **final** verdict (R4 plan A).

    With ``keep_open`` the phase keeps sampling through persistence, shard commit,
    sealing and cleanup.  The record handed to the seal is therefore provisional by
    construction -- the monitor's verdict only exists once it is stopped -- so the seal
    states its coverage as-of-seal-time and the *verdict* is recorded afterwards as a
    chained event.  This helper performs that closing step: it writes the final verdict
    into the record and states which lifecycle stages were actually observed, so
    nothing has to pretend the provisional record was final.
    """
    capacity = dict(resources.get("capacity_sampling") or {})
    status = verdict.get("status")
    capacity.update({
        "status": status,
        "provisional": False,
        "incomplete": status != "PASS",
        "raw_samples": verdict.get("samples"),
        "peak_commit_ratio": verdict.get("peak_commit_ratio"),
        "incomplete_reasons": list(verdict.get("incomplete_reasons") or []),
        "breaches": list(verdict.get("breaches") or []),
    })
    resources["capacity_sampling"] = capacity
    # Re-bind the raw stream to its final bytes.  The stream legitimately grows until
    # the monitor stops (cleanup and teardown rows are written *after* the seal), so the
    # hash bound at assembly time is stale by construction.  A stale binding makes the
    # raw rebuild refuse -- which used to degrade into four breach-looking False flags
    # instead of an attributable INCOMPLETE.  Rebinding here is what keeps the verdict
    # and the record on the same bytes.
    raw_path = resources.get("capacity_raw_path")
    if raw_path:
        path = Path(raw_path)
        if path.is_file():
            from owtda_cal.resource_policy import policy_sha256

            blob = path.read_bytes()
            resources["capacity_raw_sha256"] = hashlib.sha256(blob).hexdigest()
            resources["capacity_policy_sha256"] = policy_sha256()
            root = resources.get("evidence_root")
            try:
                resources["capacity_raw_relative_path"] = (
                    path.relative_to(Path(root)).as_posix() if root else path.name
                )
            except ValueError:
                resources["capacity_raw_relative_path"] = path.name
            # Backfill the fields the boundary-aware rebuild needs, from the *final*
            # rows.  They were written at assembly time, before cleanup/teardown landed,
            # and a missing protected boundary makes evaluate_capacity(require_boundaries)
            # latch INCOMPLETE -- which then overwrites an otherwise-correct verdict.
            rows = [json.loads(line) for line in blob.decode("utf-8").splitlines() if line.strip()]
            good = [r for r in rows if r.get("ok") is True]
            cap = resources.setdefault("capacity_sampling", {})
            cap["samples"] = len(rows)
            cap["missing"] = len(rows) - len(good)
            cap["raw_samples"] = len(rows)
            if good:
                resources["peak_total_rss_bytes"] = max(r["rss_tree_bytes"] for r in good)
                resources["protected_start_ns"] = good[0]["monotonic_ns"]
                resources["protected_end_ns"] = good[-1]["monotonic_ns"]
                cap["commit_total_peak_bytes"] = max(r["commit_total_bytes"] for r in good)
                cap["commit_limit_bytes"] = good[-1]["commit_limit_bytes"]
                cap["physical_total_bytes"] = good[-1]["physical_total_bytes"]
                cap["physical_available_min_bytes"] = min(r["physical_available_bytes"] for r in good)
    missing = [s for s in required_stages if s not in observed_stages]
    # The scope label is *derived* from what was observed, never asserted: the assembly
    # writes it before the later stages run, so closing the record has to restate it.
    # (Audit: "COMPUTE_ONLY 不能改个标签就成为完整监控.")
    resources["capacity_coverage_scope"] = (
        "FULL_SCIENTIFIC_LIFECYCLE" if not missing else "PARTIAL:" + ",".join(missing)
    )
    resources["stage_coverage"] = {
        "required": list(required_stages),
        "observed": list(observed_stages),
        "not_observed": missing,
        "verdict_recorded_post_seal": True,
    }
    return resources


def sample_run(
    runner: Callable[..., Any], *, evidence_root: Path, run_id: str,
    on_compute_done: Callable[[Any], None] | None = None,
    keep_open: bool = False, monitor_holder: dict[str, Any] | None = None,
    **kwargs: Any,
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

    if keep_open and monitor_holder is None:
        raise ValueError("keep_open requires a monitor_holder owner")
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
    raw_path = Path(evidence_root) / "resources" / ("capacity_" + hashlib.sha256(run_id.encode()).hexdigest()[:20] + ".jsonl")
    monitor = CapacityMonitor(run_id=run_id, raw_path=raw_path, stage="compute")
    started = time.time()
    compute_succeeded = False
    try:
        monitor.start()
        # R4 block B: hand the live monitor to the phase runner so a latched
        # capacity/timer stop prevents *new scientific units* from being dispatched
        # inside the phase, rather than only stopping between phases.  Runners that
        # do not accept the parameter keep their historical call shape.
        import inspect

        if "monitor" in inspect.signature(runner).parameters:
            result = runner(monitor=monitor, **kwargs)
        else:
            result = runner(**kwargs)
        # R4 block B: the monitor stays open across whatever the caller still has to
        # do (ledger write, shard commit, seal, worker cleanup).  A breach latched in
        # that window is recorded and cannot be dropped by stopping the sampler early.
        # The hook receives the finished result, because writing the ledger and
        # sealing the phase need it and must happen inside the sampling window.
        if on_compute_done is not None:
            on_compute_done(monitor, result)
        compute_succeeded = True
    finally:
        stop.set()
        thread.join(timeout=2.0)
        # R4 block B: with ``keep_open`` the caller owns the monitor's lifecycle, so a
        # phase keeps sampling while it writes the ledger, commits shards and seals --
        # and then stops the monitor itself and quotes the final verdict.  Without it
        # the historical behaviour is unchanged.  When keep_open is used, the returned
        # ``resources`` are *provisional*: the holder says so explicitly, so no caller
        # can quote a verdict that was taken before the stages it runs afterwards.
        # R4 block B: with ``keep_open`` the caller owns the monitor's lifecycle, so a
        # phase keeps sampling while it writes the ledger, commits shards and seals --
        # and then stops the monitor itself and quotes the final verdict.  The record
        # assembled below is then explicitly provisional (status OPEN), so nothing can
        # be quoted as final before the stages that run afterwards have been observed.
        keep_live = keep_open and compute_succeeded
        monitor_verdict = None
        if not keep_live and monitor._started and not monitor._closed:
            monitor_verdict = monitor.stop()
        if keep_open and monitor_holder is not None:
            monitor_holder["monitor"] = monitor
            monitor_holder["resources_provisional"] = keep_live
            if not compute_succeeded:
                monitor_holder["failure_resource_verdict"] = monitor_verdict

    own_after = own_pagefile_bytes(proc)
    peak = max(samples) if samples else None
    bytes_after = tree_bytes(evidence_root)
    # NOTE: this record is embedded in the seal, and the seal hash is taken over a
    # *canonical* payload in which bare floats are forbidden.  Everything here is
    # therefore int/str/None only; the GiB figure is derived by the checks.
    raw_rows = monitor.rows()
    good_rows = [r for r in raw_rows if r.get("ok") is True]
    if good_rows:
        peak = max(r["rss_tree_bytes"] for r in good_rows)
        capacity.update(samples=len(raw_rows), missing=len(raw_rows)-len(good_rows),
            commit_total_peak_bytes=max(r["commit_total_bytes"] for r in good_rows),
            commit_limit_bytes=good_rows[-1]["commit_limit_bytes"],
            physical_total_bytes=good_rows[-1]["physical_total_bytes"],
            physical_available_min_bytes=min(r["physical_available_bytes"] for r in good_rows))
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
            # ``keep_open``: the monitor is still sampling, so there is no final verdict
            # yet.  The record says OPEN -- never PASS/FAIL -- and carries a pending
            # reason, so a provisional record cannot be quoted as an acceptance result.
            # The caller replaces this block after it stops the monitor itself.
            "status": (monitor_verdict or {}).get("status", "OPEN"),
            "provisional": monitor_verdict is None,
            "incomplete": bool(
                monitor_verdict is None
                or capacity["missing"]
                or capacity["samples"] == 0
                or capacity["max_gap_milliseconds"]
                > CAPACITY_INTERVAL_S * CAPACITY_MAX_GAP_FACTOR * 1000
                or monitor_verdict["status"] == "INCOMPLETE"
            ),
            # The authoritative record: every sample, both counters of a ratio on
            # the same row.  ``resource_verdict`` rebuilds the decision from it.
            "raw_path": str(raw_path),
            "raw_samples": (monitor_verdict or {}).get("samples"),
            "peak_commit_ratio": (monitor_verdict or {}).get("peak_commit_ratio"),
            "incomplete_reasons": list(
                (monitor_verdict or {}).get("incomplete_reasons") or []
            ) + ([] if monitor_verdict is not None else ["keep_open: verdict pending"]),
            "breaches": list((monitor_verdict or {}).get("breaches") or []),
        },
        "run_id": run_id,
        "capacity_raw_path": str(raw_path),
        "capacity_raw_relative_path": raw_path.relative_to(evidence_root).as_posix(),
        "capacity_raw_sha256": hashlib.sha256(raw_path.read_bytes()).hexdigest(),
        "capacity_policy_sha256": monitor.policy_sha256,
        "capacity_coverage_scope": "COMPUTE_ONLY",
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


def _load_raw_capacity(resources: dict[str, Any], *, evidence_root: Path | None = None) -> dict[str, Any] | None:
    """Load and bind raw samples, returning no invented observations on failure."""
    from owtda_cal.resource_policy import evaluate_capacity, load_policy, policy_sha256
    try:
        rel = resources.get("capacity_raw_relative_path")
        if evidence_root is not None:
            if not rel:
                return None
            root = Path(evidence_root).resolve()
            path = (root / rel).resolve()
            if not path.is_relative_to(root):
                return None
        else:
            path = Path(resources["capacity_raw_path"])
        blob = path.read_bytes()
        if hashlib.sha256(blob).hexdigest() != resources.get("capacity_raw_sha256"):
            return None
        if resources.get("capacity_policy_sha256") != policy_sha256():
            return None
        run_id = resources.get("run_id")
        if not isinstance(run_id, str) or not run_id:
            return None
        rows = [json.loads(line) for line in blob.splitlines() if line.strip()]
        decision = evaluate_capacity(rows, policy=load_policy(), expected_run_id=run_id,
            expected_policy_sha256=resources["capacity_policy_sha256"], require_boundaries=True,
            expected_start_ns=resources.get("protected_start_ns"),
            expected_end_ns=resources.get("protected_end_ns"))
        if resources.get("capacity_coverage_scope") == "FULL_SCIENTIFIC_LIFECYCLE":
            start, end = resources.get("protected_start_ns"), resources.get("protected_end_ns")
            if type(start) is not int or type(end) is not int or not 0 <= start <= end:
                decision["issues"].append("protected lifecycle boundaries missing/invalid")
                decision["verdict"] = "INCOMPLETE"
        decision["raw_rows"] = rows
        return decision
    except (OSError, ValueError, KeyError, TypeError):
        return None


def _checks_from_raw_rows(resources: dict[str, Any], *, evidence_root: Path | None = None) -> dict[str, bool]:
    decision = _load_raw_capacity(resources, evidence_root=evidence_root)
    valid = decision is not None and decision["verdict"] != "INCOMPLETE"
    codes = {b["code"] for b in decision["breaches"]} if decision else set()
    return {"capacity_sampling_complete": valid,
            "host_commit_fraction_within_limit": valid and "COMMIT_RATIO_BREACH" not in codes,
            "host_available_phys_within_minimum": valid and "PHYSICAL_FLOOR_BREACH" not in codes,
            "peak_total_rss_within_limit": valid and "RSS_BREACH" not in codes}


def resource_verdict(
    resources: dict[str, Any] | None,
    *,
    unexplained_errors: int,
    limits: dict[str, Any] | None = None,
    policy: dict[str, Any] | None = None,
    evidence_root: Path | None = None,
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
    raw_checks = _checks_from_raw_rows(resources, evidence_root=evidence_root)
    raw_decision = _load_raw_capacity(resources, evidence_root=evidence_root)
    summary_consistent = True
    if raw_decision is not None and raw_decision["verdict"] != "INCOMPLETE":
        rows = raw_decision["raw_rows"]
        paired = raw_decision["peak_commit_ratio"]
        fraction = paired["num"] / paired["den"] if paired else None
        observed_rss = max(row["rss_tree_bytes"] for row in rows)
        if peak_bytes is not None and peak_bytes != observed_rss:
            summary_consistent = False
        peak_bytes, peak_gib = observed_rss, observed_rss / GIB
        expected_fields = {"samples": len(rows), "missing": 0,
            "commit_total_peak_bytes": max(row["commit_total_bytes"] for row in rows),
            "commit_limit_bytes": rows[-1]["commit_limit_bytes"],
            "physical_total_bytes": rows[-1]["physical_total_bytes"],
            "physical_available_min_bytes": min(row["physical_available_bytes"] for row in rows)}
        for key, expected in expected_fields.items():
            if key in capacity and capacity[key] != expected:
                summary_consistent = False
        if capacity.get("incomplete") is not False:
            summary_consistent = False
    written = resources.get("evidence_bytes_written")
    free = resources.get("disk_free_before_bytes")
    allocation_failures = resources.get("resource_allocation_failures")
    checks = {
        "resources_recorded": True,
        "raw_summary_consistent": summary_consistent,
        "complete_lifecycle_observed": resources.get("capacity_coverage_scope") == "FULL_SCIENTIFIC_LIFECYCLE",
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
        "resource_allocation_failures_within_limit": type(allocation_failures) is int and allocation_failures == 0,
        "unexplained_errors_within_limit": bool(
            type(unexplained_errors) is int and 0 <= unexplained_errors <= int(hard["unexplained_errors_max"])
        ),
        "disk_rule": bool(type(written) is int and written >= 0 and type(free) is int and free > 0 and 5 * written <= 4 * free),
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
        "status": "PASS" if passed else "INCOMPLETE" if not raw_checks["capacity_sampling_complete"] or not checks["complete_lifecycle_observed"] else "FAIL",
        "passed": passed,
    }
