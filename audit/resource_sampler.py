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

import json
import threading
import time
from collections.abc import Callable
from pathlib import Path
from typing import Any

SAMPLE_INTERVAL_S = 0.25
GIB = 1024**3
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


def sample_run(
    runner: Callable[..., Any], *, evidence_root: Path, **kwargs: Any
) -> tuple[Any, dict[str, Any]]:
    """Run ``runner(**kwargs)`` while sampling the resources that run consumes."""
    import psutil

    proc = psutil.Process()
    samples: list[int] = []
    swap_before = int(psutil.swap_memory().used)
    swap_peak = swap_before
    free_before = disk_free_bytes(evidence_root)
    bytes_before = tree_bytes(evidence_root)
    stop = threading.Event()

    def sampler() -> None:
        nonlocal swap_peak
        while not stop.is_set():
            total = int(proc.memory_info().rss)
            for child in proc.children(recursive=True):
                try:
                    total += int(child.memory_info().rss)
                except psutil.Error:
                    pass
            samples.append(total)
            swap_peak = max(swap_peak, int(psutil.swap_memory().used))
            stop.wait(SAMPLE_INTERVAL_S)

    thread = threading.Thread(target=sampler, daemon=True)
    thread.start()
    started = time.time()
    try:
        result = runner(**kwargs)
    finally:
        stop.set()
        thread.join(timeout=2.0)

    peak = max(samples) if samples else None
    bytes_after = tree_bytes(evidence_root)
    resources: dict[str, Any] = {
        "schema_version": 1,
        "kind": "run_resources_v1",
        "wall_seconds": float(getattr(result, "wall_seconds", time.time() - started)),
        "measured_wall_seconds": round(time.time() - started, 3),
        "peak_total_rss_bytes": peak,
        "peak_total_rss_gib": round(peak / GIB, 6) if peak is not None else None,
        "swap_before_bytes": swap_before,
        "swap_peak_bytes": swap_peak,
        "swap_growth_bytes": swap_peak - swap_before,
        "swap_measurement_caveat": (
            "system-wide page file usage: sensitive to unrelated host activity"
        ),
        "evidence_root": str(evidence_root),
        "disk_free_before_bytes": free_before,
        "evidence_bytes_before": bytes_before,
        "evidence_bytes_after": bytes_after,
        "evidence_bytes_written": bytes_after - bytes_before,
        "samples": len(samples),
        "sample_interval_s": SAMPLE_INTERVAL_S,
    }
    return result, resources


def resource_verdict(
    resources: dict[str, Any] | None, *, limits: dict[str, Any], unexplained_errors: int
) -> dict[str, Any]:
    """Evaluate one run's resources against the frozen limits (fail closed)."""
    if not resources:
        return {
            "limits": limits,
            "observed": None,
            "checks": {"resources_recorded": False},
            "passed": False,
        }
    peak = resources.get("peak_total_rss_gib")
    swap = resources.get("swap_growth_bytes")
    written = resources.get("evidence_bytes_written")
    free = resources.get("disk_free_before_bytes")
    checks = {
        "resources_recorded": True,
        "peak_total_rss_within_limit": bool(
            peak is not None and peak <= limits["peak_total_rss_gib_max"]
        ),
        "no_swap_growth": bool(
            swap is not None and swap <= limits["swap_growth_bytes_max"]
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
            "swap_growth_bytes": swap,
            "evidence_bytes_written": written,
            "disk_free_before_bytes": free,
            "unexplained_errors": unexplained_errors,
            "swap_measurement_caveat": resources.get("swap_measurement_caveat"),
        },
        "checks": checks,
        "passed": all(checks.values()),
    }
