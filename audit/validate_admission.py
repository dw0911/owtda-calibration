"""G4 pre-admission checks + full §9.4 budget verdicts (B15c).

Checks:
  1. G3 smoke evidence is contract-complete for *both* phases -- SMOKE_NULL
     (896/3,584/73,600) and SMOKE_ALT (256/1,024/49,152) -- with 0 unexplained
     errors, 0 missing required fields, no formal logical/concrete ID leaked
     into the smoke ledger, provenance bound to the current RUN_COMPONENT_SET /
     source tree / environment lock, and no forbidden aggregate emitted;
  2. §9.4 wall Gate: t_H0_hat = 1.25 * (2500/32) * t_0,32 <= 192 h,
     t_H1_hat = 1.25 * (1600/32) * t_1,32 <= 76.8 h and
     t_core_hat = t_H0_hat + t_H1_hat <= 268.8 h;
  3. §9.4 memory Gate: sampled total peak RSS (parent + workers, worst phase)
     <= 24 GiB with no swap growth during either sample run;
  4. §9.4 disk Gate: estimated_peak_disk = 1.25 * persisted increment (both
     smoke ledgers) * formal/smoke row scale <= 0.8 * F_free;
  5. open_runs = 0.

Memory/disk are sampled on short (replicates=2) smoke runs so the verdict does
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
R0_FORMAL_H1 = 1600
WALL_LIMIT_H0_HOURS = 192.0
WALL_LIMIT_H1_HOURS = 76.8
WALL_LIMIT_CORE_HOURS = 268.8
SAMPLE_REPLICATES = 2
SMOKE_EVIDENCE = {
    scope.PHASE_SMOKE_NULL: "artifacts/audit/smoke_RC.json",
    scope.PHASE_SMOKE_ALT: "artifacts/audit/smoke_alt_RC.json",
}


def _load(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _identity_closure(phase: str, ledger_path: Path) -> dict[str, Any]:
    """Recompute the smoke ledger's identity lattice from the frozen ledger bytes.

    A complete G3 smoke ledger must close exactly over
    experiment -> logical cell -> data unit -> feature-sufficient -> evaluation
    (Plan §16), so a missing or duplicated artefact cannot hide behind the row
    count alone.
    """
    n_cells = (
        len(scope.h0_null_cells())
        if phase == scope.PHASE_SMOKE_NULL
        else len(scope.h1_alt_cells())
    )
    units = n_cells * scope.R0_SMOKE
    cells_n = units * len(scope.FEATURE_IDS)
    evaluations = cells_n * len(scope.METHOD_IDS)
    expected = {
        "experiment_id": 1,
        "logical_cell_id": n_cells,
        "data_unit_id": units,
        "feature_sufficient_id": cells_n,
        "evaluation_id": evaluations,
        "logical_evaluation_key": evaluations,
    }
    rows = [
        json.loads(line)
        for line in ledger_path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    actual = {key: len({row[key] for row in rows}) for key in expected}
    return {
        "expected": expected,
        "actual": actual,
        "rows": len(rows),
        "passed": actual == expected,
    }


def _sample_run(*, phase: str, workers: int) -> dict[str, Any]:
    """Short smoke run with total-RSS and swap sampling."""
    import psutil

    manifest = _load(GOV / "FREEZE_MANIFEST.json")
    seed_registry = _load(GOV / "SEED_REGISTRY_v1.0.json")
    runner = (
        smoke.run_smoke_null
        if phase == scope.PHASE_SMOKE_NULL
        else smoke.run_smoke_alt
    )
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
    result = runner(
        manifest=manifest, seed_registry=seed_registry, workers=workers,
        replicate_limit=SAMPLE_REPLICATES,
    )
    stop.set()
    thread.join(timeout=2.0)
    return {
        "phase": phase,
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

    manifest = _load(GOV / "FREEZE_MANIFEST.json")
    evidence = {
        phase: _load(REPO / path) for phase, path in SMOKE_EVIDENCE.items()
    }

    for phase in scope.SMOKE_PHASES:
        tag = "smoke" if phase == scope.PHASE_SMOKE_NULL else "smoke_alt"
        ev = evidence[phase]
        report = ev["report"]
        admission = manifest["run_admission"][phase]
        expected = smoke.expected_smoke_counts(phase)
        record(
            f"g3_counts_{tag}",
            report["data_units"] == expected["data_units"]
            and report["evaluation_rows"] == expected["evaluation_rows"]
            and report["ph_windows"] == expected["ph_windows"],
            f"{report['data_units']}/{report['evaluation_rows']}/{report['ph_windows']}",
        )
        record(f"g3_zero_unexplained_errors_{tag}", ev["unexplained_errors"] == 0)
        record(f"g3_zero_missing_fields_{tag}", ev["missing_required_fields"] == 0)
        record(
            f"g3_no_formal_id_leak_{tag}",
            ev["formal_id_leak_check"]["passed"] is True,
            f"checked={ev['formal_id_leak_check']['formal_ids_checked']}",
        )
        record(
            f"g3_blind_no_forbidden_aggregates_{tag}",
            ev["forbidden_aggregates_emitted"] is False
            and report["forbidden_aggregates_emitted"] is False,
        )
        provenance = ev["provenance"]
        record(
            f"g3_provenance_bound_{tag}",
            provenance["run_component_set_hash"] == admission["run_component_set_hash"]
            and provenance["scope_design_hash"] == admission["scope_design_hash"]
            and provenance["source_tree_hash"] == manifest["source_tree_hash"]
            and provenance["environment_lock_hash"]
            == manifest["environment_lock_hash"],
            provenance["run_component_set_hash"][:12],
        )
        record(
            f"g3_smoke_generation_{tag}",
            ev["smoke_generation_id"] == scope.SMOKE_GENERATION_ID,
            ev["smoke_generation_id"],
        )
        closure = _identity_closure(phase, REPO / ev["ledger_file"])
        record(
            f"g3_identity_closure_{tag}",
            closure["passed"],
            f"cells={closure['actual']['logical_cell_id']} "
            f"units={closure['actual']['data_unit_id']} "
            f"evaluations={closure['actual']['evaluation_id']}",
        )

    t_0_32 = evidence[scope.PHASE_SMOKE_NULL]["budget"]["t_0_32_seconds"]
    t_1_32 = evidence[scope.PHASE_SMOKE_ALT]["budget"]["t_1_32_seconds"]
    t_h0_hat = SCALE_FACTOR * (R0_FORMAL_H0 / scope.R0_SMOKE) * t_0_32 / 3600.0
    t_h1_hat = SCALE_FACTOR * (R0_FORMAL_H1 / scope.R0_SMOKE) * t_1_32 / 3600.0
    t_core_hat = t_h0_hat + t_h1_hat
    record("wall_gate_h0", t_h0_hat <= WALL_LIMIT_H0_HOURS, f"t_H0_hat={t_h0_hat:.3f}h")
    record("wall_gate_h1", t_h1_hat <= WALL_LIMIT_H1_HOURS, f"t_H1_hat={t_h1_hat:.3f}h")
    record("wall_gate_core", t_core_hat <= WALL_LIMIT_CORE_HOURS, f"t_core_hat={t_core_hat:.3f}h")

    sampled = [
        _sample_run(phase=phase, workers=8)
        for phase in scope.SMOKE_PHASES
    ]
    peaks = [s["peak_total_rss_bytes"] for s in sampled if s["peak_total_rss_bytes"]]
    peak = max(peaks) if peaks else None
    record(
        "memory_gate_total_rss",
        peak is not None and peak <= RSS_LIMIT_BYTES,
        f"peak_total={peak} bytes",
    )
    swap_growth = max(s["swap_growth_bytes"] for s in sampled)
    record(
        "memory_gate_no_swap_growth",
        swap_growth <= 0,
        f"growth={swap_growth} bytes",
    )

    ledger_bytes = sum(ev["resources"]["ledger_bytes"] for ev in evidence.values())
    formal_rows = (
        len(scope.h0_null_cells()) * R0_FORMAL_H0 + len(scope.h1_alt_cells()) * R0_FORMAL_H1
    ) * 4
    smoke_rows = sum(ev["report"]["evaluation_rows"] for ev in evidence.values())
    estimated_peak_disk = SCALE_FACTOR * ledger_bytes * (formal_rows / smoke_rows)
    free = shutil.disk_usage(REPO.drive + "\\").free
    record(
        "disk_gate",
        estimated_peak_disk <= 0.8 * free,
        f"est_peak={estimated_peak_disk / 1024**2:.1f} MiB free={free / 1024**3:.1f} GiB",
    )

    open_runs = 0
    for phase in scope.SMOKE_PHASES:
        shard_registry = REPO / f"artifacts/smoke/{phase}/shard_registry.jsonl"
        if shard_registry.exists():
            open_runs += sum(
                1
                for line in shard_registry.read_text(encoding="utf-8").splitlines()
                if line.strip()
            )
    record("open_runs_zero", open_runs == 0, f"open_runs={open_runs}")

    all_pass = all(c["pass"] for c in checks)
    out = {
        "schema_version": 1,
        "kind": "admission_precheck_v1",
        "generated_at_utc": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "smoke_generation_id": scope.SMOKE_GENERATION_ID,
        "all_pass": all_pass,
        "checks": checks,
        "budget": {
            "t_0_32_seconds": t_0_32,
            "t_1_32_seconds": t_1_32,
            "t_h0_hat_hours": t_h0_hat,
            "t_h1_hat_hours": t_h1_hat,
            "t_core_hat_hours": t_core_hat,
            "wall_limits_hours": {
                "h0": WALL_LIMIT_H0_HOURS,
                "h1": WALL_LIMIT_H1_HOURS,
                "core": WALL_LIMIT_CORE_HOURS,
            },
        },
        "resource_sample": sampled,
    }
    out_dir = REPO / "artifacts/audit"
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / "admission_precheck_RC.json"
    out_path.write_text(
        json.dumps(out, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    for check in checks:
        print(f"[{'PASS' if check['pass'] else 'FAIL'}] {check['check']}: {check['detail']}")
    print(f"ALL_PASS={all_pass}")
    print(f"EVIDENCE={out_path.name}")
    return 0 if all_pass else 1


if __name__ == "__main__":
    raise SystemExit(main())
