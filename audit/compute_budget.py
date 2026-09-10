"""Compute budget Gate (Plan §9.4, G3 item 4).

Preliminary (RC) budget probe:
  * ordered-parallel steady-state throughput for workers in {1,4,8} (a pooled
    warm-up run is discarded so process start-up is not counted as compute);
  * bit-for-bit payload equality of every worker count against ``workers=1``;
  * parent-process peak RSS and F: free space;
  * H0/H1/core wall extrapolation from the Plan §9.2 PH-window counts.

Thresholds (Plan §9.4): ``t_H0 <= 192 h``, ``t_H1 <= 76.8 h``,
``t_core <= 268.8 h``, total peak RSS <= 24 GiB, no swap, and
``estimated_peak_disk <= 0.8 * F_free``.

The formal §9.4 estimate must use the blind-smoke wall times
``t_{0,32}``/``t_{1,32}``; this script is marked ``rc_preliminary`` and never
feeds science rows.
"""

from __future__ import annotations

import ctypes
import json
import math
import os
import platform
import shutil
import sys
import time
from concurrent.futures import ProcessPoolExecutor
from datetime import UTC, datetime
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from owtda_cal.parallel import feature_chunk, feature_matrix_parallel

H0_PH_WINDOWS = 5_750_000
H1_PH_WINDOWS = 2_457_600
TOTAL_PH_WINDOWS = 8_207_600
WALL_LIMIT_H0_HOURS = 192.0
WALL_LIMIT_H1_HOURS = 76.8
WALL_LIMIT_CORE_HOURS = 268.8
RSS_LIMIT_BYTES = 24 * 1024**3
WORKER_CANDIDATES = (1, 4, 8)
EQUALITY_WINDOWS = 32
THROUGHPUT_WINDOWS = 192
WORK_VOLUME = "F:/"


def _windows(n: int, w: int = 64) -> list[np.ndarray]:
    rng = np.random.default_rng(20260910)
    out = []
    for _ in range(n):
        t = np.linspace(0.0, 2 * np.pi, w, endpoint=False)
        out.append(
            np.column_stack([np.cos(t), np.sin(t)]) + 0.05 * rng.standard_normal((w, 2))
        )
    return out


def _peak_rss_bytes() -> int | None:
    try:
        import psutil

        info = psutil.Process().memory_info()
        peak = getattr(info, "peak_wset", None)
        return int(peak) if peak else int(info.rss)
    except Exception:  # noqa: BLE001, S110  # pragma: no cover - platform probe
        pass
    if os.name == "nt":
        try:
            from ctypes import wintypes

            class _PMC(ctypes.Structure):
                _fields_ = [
                    ("cb", wintypes.DWORD),
                    ("PageFaultCount", wintypes.DWORD),
                    ("PeakWorkingSetSize", ctypes.c_size_t),
                    ("WorkingSetSize", ctypes.c_size_t),
                    ("QuotaPeakPagedPoolUsage", ctypes.c_size_t),
                    ("QuotaPagedPoolUsage", ctypes.c_size_t),
                    ("QuotaPeakNonPagedPoolUsage", ctypes.c_size_t),
                    ("QuotaNonPagedPoolUsage", ctypes.c_size_t),
                    ("PagefileUsage", ctypes.c_size_t),
                    ("PeakPagefileUsage", ctypes.c_size_t),
                ]

            pmc = _PMC()
            pmc.cb = ctypes.sizeof(_PMC)
            fn = getattr(ctypes.windll.kernel32, "K32GetProcessMemoryInfo", None)
            if fn is not None and fn(
                ctypes.windll.kernel32.GetCurrentProcess(), ctypes.byref(pmc), pmc.cb
            ):
                return int(pmc.PeakWorkingSetSize)
        except Exception:  # noqa: BLE001  # pragma: no cover - platform probe
            return None
        return None
    try:
        with open("/proc/self/status", encoding="ascii") as fh:
            for line in fh:
                if line.startswith("VmHWM:"):
                    return int(line.split()[1]) * 1024
    except OSError:
        return None
    return None


def _steady_seconds_per_window(workers: int) -> float:
    ws = _windows(THROUGHPUT_WINDOWS)
    n = len(ws)
    if workers == 1:
        start = time.perf_counter()
        feature_matrix_parallel(ws, feature_kind="bpi", scenario="N_CIRCLE", workers=1)
        return (time.perf_counter() - start) / n
    size = max(1, math.ceil(n / (workers * 2)))
    chunks = [ws[i : i + size] for i in range(0, n, size)]
    payloads = [(c, "bpi", "N_CIRCLE") for c in chunks]
    with ProcessPoolExecutor(max_workers=workers) as pool:
        list(pool.map(feature_chunk, payloads))  # warm-up: import + first-touch
        start = time.perf_counter()
        list(pool.map(feature_chunk, payloads))
        return (time.perf_counter() - start) / n


def _payload_equal(workers: int) -> bool:
    ws = _windows(EQUALITY_WINDOWS)
    ref = feature_matrix_parallel(ws, feature_kind="bpi", scenario="N_CIRCLE", workers=1)
    got = feature_matrix_parallel(
        ws, feature_kind="bpi", scenario="N_CIRCLE", workers=workers
    )
    return bool(np.array_equal(ref, got))


def main() -> int:
    measurements = []
    for workers in WORKER_CANDIDATES:
        per_window = _steady_seconds_per_window(workers)
        est_h0 = per_window * H0_PH_WINDOWS / 3600.0
        est_h1 = per_window * H1_PH_WINDOWS / 3600.0
        est_core = per_window * TOTAL_PH_WINDOWS / 3600.0
        measurements.append(
            {
                "workers": workers,
                "seconds_per_window_steady": per_window,
                "payload_bitwise_equal_to_workers_1": _payload_equal(workers),
                "estimated_h0_wall_hours": est_h0,
                "estimated_h1_wall_hours": est_h1,
                "estimated_core_wall_hours": est_core,
                "wall_gate_pass": bool(
                    est_h0 <= WALL_LIMIT_H0_HOURS
                    and est_h1 <= WALL_LIMIT_H1_HOURS
                    and est_core <= WALL_LIMIT_CORE_HOURS
                ),
            }
        )

    peak = _peak_rss_bytes()
    rss_gate = None if peak is None else bool(peak <= RSS_LIMIT_BYTES)
    try:
        usage = shutil.disk_usage(WORK_VOLUME)
        disk = {
            "volume": WORK_VOLUME,
            "free_bytes": usage.free,
            "free_gib": usage.free / 1024**3,
        }
    except OSError as exc:  # pragma: no cover
        disk = {"volume": WORK_VOLUME, "error": str(exc)}

    eligible = [
        m
        for m in measurements
        if m["payload_bitwise_equal_to_workers_1"] and m["wall_gate_pass"]
    ]
    best = None
    if eligible:
        fastest = min(eligible, key=lambda m: m["seconds_per_window_steady"])
        near = [
            m
            for m in eligible
            if m["seconds_per_window_steady"] <= fastest["seconds_per_window_steady"] * 1.02
        ]
        best = min(near, key=lambda m: m["workers"])

    evidence = {
        "schema_version": 1,
        "kind": "compute_budget_rc_v1",
        "status": "rc_preliminary",
        "generated_at_utc": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "host": {
            "platform": platform.platform(),
            "python": platform.python_version(),
            "numpy": np.__version__,
            "cpu_count": os.cpu_count(),
        },
        "thresholds": {
            "h0_wall_hours": WALL_LIMIT_H0_HOURS,
            "h1_wall_hours": WALL_LIMIT_H1_HOURS,
            "core_wall_hours": WALL_LIMIT_CORE_HOURS,
            "peak_rss_gib": RSS_LIMIT_BYTES / 1024**3,
            "disk_rule": "estimated_peak_disk <= 0.8 * F_free_space",
        },
        "measurements": measurements,
        "parent_peak_rss_bytes": peak,
        "parent_peak_rss_gate_pass": rss_gate,
        "disk": disk,
        "selected_w_star_rc": None if best is None else best["workers"],
        "swap_gate": "not_measured_in_rc_probe",
        "total_rss_gate": "requires blind smoke (workers' peak RSS not additive here)",
        "disk_gate": "pending_blind_smoke_persisted_increment",
        "note": (
            "RC preliminary only. Formal §9.4 estimate uses blind-smoke wall times "
            "t_0,32 / t_1,32; PH-window counts are the Plan §9.2 totals; "
            "throughput excludes pool start-up via a discarded warm-up pass."
        ),
    }

    out_dir = Path(__file__).resolve().parents[1] / "artifacts/audit"
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / "compute_budget_RC.json"
    out_path.write_text(
        json.dumps(evidence, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )

    for m in measurements:
        print(
            f"workers={m['workers']} per_window={m['seconds_per_window_steady']*1000:.3f} ms "
            f"h0={m['estimated_h0_wall_hours']:.2f} h "
            f"payload_equal={m['payload_bitwise_equal_to_workers_1']} "
            f"wall_gate={m['wall_gate_pass']}"
        )
    print(f"parent_peak_rss_bytes={peak} rss_gate={rss_gate}")
    print(f"disk_free_gib={disk.get('free_gib')}")
    print(f"selected_w_star_rc={evidence['selected_w_star_rc']}")
    print(f"evidence={out_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
