"""G4 pre-admission checks + §9.4 budget verdicts (B15b).

Checks:
  1. G3 smoke evidence is contract-complete: frozen counts (896/3,584/73,600),
     0 unexplained errors, 0 missing required fields, provenance bound to the
     current RUN_COMPONENT_SET / source tree / environment lock, and no
     forbidden aggregate emitted;
  2. §9.4 wall Gate: t_H0_hat = 1.25 * (2500/32) * t_0,32 <= 192 h;
  3. §9.4 memory Gate: sampled total peak RSS (parent + workers) <= 24 GiB with
     no swap growth during the run;
  4. §9.4 disk Gate: estimated_peak_disk = 1.25 * persisted increment
     <= 0.8 * F_free;
  5. open_runs = 0.

Memory/disk are sampled on a short (replicates=2) smoke run so the verdict does
not require re-running the full smoke.
"""

from __future__ import annotations

import json
import shutil
import sys
import threading
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "src"))

from owtda_cal import scope, smoke

GOV = REPO / "governance"
RSS_LIMIT_BYTES = 24 * 1024**3
SCALE_FACTOR = 1.25
R0_FORMAL_H0 = 2500
WALL_LIMIT_H0_HOURS = 192.0
SAMPLE_REPLICATES = 2


def _load(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _sample_run(*, workers: int) -> dict[str, Any]:
    """Short smoke run with total-RSS and swap sampling."""
    import psutil

    manifest = _load(GOV / "FREEZE_MANIFEST.json")
    seed_registry = _load(GOV / "SEED_REGISTRY_v1.0.json")
    proc = psutil.Process()
    samples: list[int] = []
    swap_before = psutil.swap_memory().used
    swap_peak = swap_before
    stop = threading.Event()

    def sampler() -> None:
        nonlocal swap_peak
        while not stop.is_set():
            total = proc.memory_info().rss
            for child in proc.children(recursive=True):
                try:
                    total += child.memory_info().rss
                except psutil.Error:
                    pass
            samples.append(total)
            swap_peak = max(swap_peak, psutil.swap_memory().used)
            stop.wait(0.25)

    thread = threading.Thread(target=sampler, daemon=True)
    thread.start()
    result = smoke.run_smoke_null(
        manifest=manifest, seed_registry=seed_registry, workers=workers,
        replicate_limit=SAMPLE_REPLICATES,
    )
    stop.set()
    thread.join(timeout=2.0)
    return {
        "workers": workers,
        "replicates": SAMPLE_REPLICATES,
        "wall_seconds": result.wall_seconds,
        "peak_total_rss_bytes": max(samples) if samples else None,
        "swap_before_bytes": swap_before,
        "swap_peak_bytes": swap_peak,
        "swap_growth_bytes": swap_peak - swap_before,
        "errors": result.errors,
    }


def main() -> int:
    checks: list[dict[str, Any]] = []

    def record(name: str, passed: bool, detail: str = "") -> None:
        checks.append({"check": name, "pass": bool(passed), "detail": detail})

    smoke_evidence = _load(REPO / "artifacts/audit/smoke_RC.json")
    manifest = _load(GOV / "FREEZE_MANIFEST.json")
    admission = manifest["run_admission"][scope.PHASE_SMOKE_NULL]
    report = smoke_evidence["report"]
    expected = smoke.expected_smoke_counts()

    record(
        "g3_counts",
        report["data_units"] == expected["data_units"]
        and report["evaluation_rows"] == expected["evaluation_rows"]
        and report["ph_windows"] == expected["ph_windows"],
        f"{report['data_units']}/{report['evaluation_rows']}/{report['ph_windows']}",
    )
    record("g3_zero_unexplained_errors", smoke_evidence["unexplained_errors"] == 0)
    record("g3_zero_missing_fields", smoke_evidence["missing_required_fields"] == 0)
    record(
        "g3_blind_no_forbidden_aggregates",
        smoke_evidence["forbidden_aggregates_emitted"] is False
        and report["forbidden_aggregates_emitted"] is False,
    )
    provenance = smoke_evidence["provenance"]
    record(
        "g3_provenance_bound",
        provenance["run_component_set_hash"] == admission["run_component_set_hash"]
        and provenance["scope_design_hash"] == admission["scope_design_hash"]
        and provenance["source_tree_hash"] == manifest["source_tree_hash"]
        and provenance["environment_lock_hash"] == manifest["environment_lock_hash"],
        provenance["run_component_set_hash"][:12],
    )

    t_0_32 = smoke_evidence["budget"]["t_0_32_seconds"]
    t_h0_hat = SCALE_FACTOR * (R0_FORMAL_H0 / scope.R0_SMOKE) * t_0_32 / 3600.0
    record("wall_gate_h0", t_h0_hat <= WALL_LIMIT_H0_HOURS, f"t_H0_hat={t_h0_hat:.3f}h")

    sampled = _sample_run(workers=8)
    peak = sampled["peak_total_rss_bytes"]
    rss_ok = peak is not None and peak <= RSS_LIMIT_BYTES
    record("memory_gate_total_rss", rss_ok, f"peak_total={peak} bytes")
    record(
        "memory_gate_no_swap_growth",
        sampled["swap_growth_bytes"] <= 0,
        f"growth={sampled['swap_growth_bytes']} bytes",
    )

    ledger_bytes = smoke_evidence["resources"]["ledger_bytes"]
    formal_scale = (len(scope.h0_null_cells()) * 2500 * 4) / (len(scope.h0_null_cells()) * scope.R0_SMOKE * 4)
    estimated_peak_disk = SCALE_FACTOR * ledger_bytes * formal_scale
    free = shutil.disk_usage("F:/").free
    record(
        "disk_gate",
        estimated_peak_disk <= 0.8 * free,
        f"est_peak={estimated_peak_disk / 1024**2:.1f} MiB free={free / 1024**3:.1f} GiB",
    )

    shard_registry = REPO / "artifacts/smoke/SMOKE_NULL/shard_registry.jsonl"
    open_runs = 0 if not shard_registry.exists() else sum(
        1 for line in shard_registry.read_text(encoding="utf-8").splitlines() if line.strip()
    )
    record("open_runs_zero", open_runs == 0, f"open_runs={open_runs}")

    all_pass = all(c["pass"] for c in checks)
    evidence = {
        "schema_version": 1,
        "kind": "admission_precheck_v1",
        "generated_at_utc": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "all_pass": all_pass,
        "checks": checks,
        "budget": {
            "t_0_32_seconds": t_0_32,
            "t_h0_hat_hours": t_h0_hat,
            "wall_limit_hours": WALL_LIMIT_H0_HOURS,
            "h1_pending": "SMOKE_ALT (B15c)",
        },
        "resource_sample": sampled,
    }
    out_dir = REPO / "artifacts/audit"
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / "admission_precheck_RC.json"
    out_path.write_text(
        json.dumps(evidence, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    for check in checks:
        print(f"[{'PASS' if check['pass'] else 'FAIL'}] {check['check']}: {check['detail']}")
    print(f"ALL_PASS={all_pass}")
    print(f"EVIDENCE={out_path.name}")
    return 0 if all_pass else 1


if __name__ == "__main__":
    raise SystemExit(main())
