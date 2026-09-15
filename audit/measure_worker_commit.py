"""Measure the job's own commit-charge increment as a function of worker count.

Why this exists (audit decision P1): attempt 10 ran the frozen smoke at 8 workers
and breached the capacity contract for real -- the paired peak commit fraction was
0.9330, with 792 breaching samples.  The decision was *not* to relax 0.80 but to
"落实加法预检，必要时前瞻登记较低固定并行度": choose the largest worker count
whose predicted peak fits

    C_baseline + 1.25 * dC(n)  <=  0.8 * L

and register that count in ``SMOKE_CONFIG_v1.json`` **before** the run, so the run
identity and the run agree.

The increment that matters is the *concurrent working set*: with ``n`` workers, ``n``
tasks are in flight, and each task's footprint is set by the data unit, not by how
many units the phase will eventually produce.  So the increment is measured with the
short (``replicates=2``) runs and is representative of the frozen-scale run, while
costing a fraction of the time.  Everything is measured with the same
:class:`CapacityMonitor` the real runs use, so the numbers come from paired
per-sample rows (host commit total and limit on the same row).

This is a **measurement**, not acceptance evidence: it writes nothing into the
freeze and promotes nothing.

Usage::

    python audit/measure_worker_commit.py [--workers 2 3 4 6 8] [--replicates 2]
                                          [--phase SMOKE_NULL] [--out-dir <dir>]
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "src"))
sys.path.insert(0, str(REPO / "audit"))

import resource_sampler  # noqa: E402

from owtda_cal import scope, smoke  # noqa: E402
from owtda_cal.resource_policy import load_policy  # noqa: E402

GOV = REPO / "governance"
MARGIN_NUM, MARGIN_DEN = 5, 4  # 1.25, the policy's own margin


def _load(name: str) -> dict[str, Any]:
    return json.loads((GOV / name).read_text(encoding="utf-8"))


def measure_one(
    *, phase: str, workers: int, replicates: int, out_dir: Path,
    manifest: dict, seed_registry: dict, policy: dict,
) -> dict[str, Any]:
    """One short run at ``workers``; return its measured commit economics."""
    runner = (
        smoke.run_smoke_null if phase == scope.PHASE_SMOKE_NULL else smoke.run_smoke_alt
    )
    before = resource_sampler.performance_info()
    if before is None:  # pragma: no cover - the host is the reason, not the code
        raise SystemExit("capacity counters unavailable: cannot measure this host")
    raw = out_dir / "resources" / f"capacity_{phase}_w{workers}.jsonl"
    monitor = resource_sampler.CapacityMonitor(
        run_id=f"commit-sweep:{phase}:w{workers}", raw_path=raw, policy=policy,
        stage="measure",
    )
    monitor.start()
    try:
        result = runner(
            manifest=manifest, seed_registry=seed_registry, workers=workers,
            replicate_limit=replicates,
        )
    finally:
        verdict = monitor.stop()

    rows = monitor.rows()
    ok = [r for r in rows if r.get("ok") is True]
    peak_commit = max((r["commit_total_bytes"] for r in ok), default=None)
    limit = ok[0]["commit_limit_bytes"] if ok else None
    increment = (peak_commit - int(before["commit_total_bytes"])) if peak_commit else None
    return {
        "phase": phase,
        "workers": workers,
        "replicates": replicates,
        "host_commit_before_bytes": int(before["commit_total_bytes"]),
        "host_commit_limit_bytes": int(before["commit_limit_bytes"]),
        "host_commit_peak_bytes": peak_commit,
        "own_increment_bytes": increment,
        "paired_peak_ratio": verdict.get("peak_commit_ratio"),
        "capacity_status": verdict.get("status"),
        "samples": verdict.get("samples"),
        "ok_samples": len(ok),
        "incomplete_reasons": verdict.get("incomplete_reasons"),
        "breaches": [b.get("code") for b in verdict.get("breaches", [])][:4],
        "wall_seconds": getattr(result, "wall_seconds", None),
        "evaluation_rows": getattr(result, "evaluation_rows", None),
        "errors": getattr(result, "errors", None),
        "raw_path": str(raw),
        "limit_seen": limit,
    }


def decide(rows: list[dict], *, policy: dict, baseline: int, limit: int) -> dict:
    """Largest worker count whose 1.25x-margined increment still fits 0.8*L."""
    ratio = policy["limits"]["host_commit_fraction_max"]
    budget = (ratio["num"] * limit) // ratio["den"]  # 0.8 * L, integer
    fitting: list[int] = []
    detail: list[dict] = []
    for row in rows:
        increment = row["own_increment_bytes"]
        if increment is None or row["capacity_status"] == "INCOMPLETE":
            detail.append({**row, "predicted_peak_bytes": None, "fits": False,
                           "reason": "no usable increment"})
            continue
        predicted = baseline + (increment * MARGIN_NUM) // MARGIN_DEN
        fits = predicted <= budget
        detail.append({**row, "predicted_peak_bytes": predicted, "fits": fits,
                       "fits_budget_bytes": budget})
        if fits:
            fitting.append(row["workers"])
    return {
        "policy_commit_fraction_max": f"{ratio['num']}/{ratio['den']}",
        "commit_limit_bytes": limit,
        "budget_bytes": budget,
        "baseline_commit_bytes": baseline,
        "margin": f"{MARGIN_NUM}/{MARGIN_DEN}",
        "measured": detail,
        "fitting_workers": sorted(fitting),
        "selected_workers": max(fitting) if fitting else None,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="worker-count commit-charge sweep")
    parser.add_argument("--workers", type=int, nargs="+", default=[2, 4, 6, 8])
    parser.add_argument("--replicates", type=int, default=2)
    parser.add_argument("--phase", default=scope.PHASE_SMOKE_NULL,
                        choices=list(scope.SMOKE_PHASES))
    parser.add_argument("--out-dir", default=None)
    args = parser.parse_args()

    policy = load_policy()
    manifest = _load("FREEZE_MANIFEST.json")
    seed_registry = _load("SEED_REGISTRY_v1.0.json")
    out_dir = Path(args.out_dir).expanduser() if args.out_dir else (
        REPO / "artifacts/audit/worker_commit_sweep")
    out_dir.mkdir(parents=True, exist_ok=True)

    rows: list[dict] = []
    for workers in sorted(set(args.workers)):
        row = measure_one(
            phase=args.phase, workers=workers, replicates=args.replicates,
            out_dir=out_dir, manifest=manifest, seed_registry=seed_registry,
            policy=policy,
        )
        rows.append(row)
        print(
            f"{args.phase} w={workers:<3} increment={row['own_increment_bytes']} B "
            f"paired={row['paired_peak_ratio']} capacity={row['capacity_status']} "
            f"wall={row['wall_seconds']}"
        )

    now = resource_sampler.performance_info()
    baseline = int(now["commit_total_bytes"]) if now else None
    limit = int(now["commit_limit_bytes"]) if now else None
    decision = (
        decide(rows, policy=policy, baseline=baseline, limit=limit)
        if baseline and limit else {"error": "counters unavailable at decision time"}
    )
    if isinstance(decision, dict) and decision.get("selected_workers"):
        print(f"SELECTED workers={decision['selected_workers']} "
              f"(budget={decision['budget_bytes']} baseline={decision['baseline_commit_bytes']})")

    out = {
        "schema_version": 1,
        "kind": "worker_commit_sweep_v1",
        "generated_at_utc": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "smoke_generation_id": scope.SMOKE_GENERATION_ID,
        "phase": args.phase,
        "replicates": args.replicates,
        "source_tree_hash": manifest["source_tree_hash"],
        "environment_lock_hash": manifest["environment_lock_hash"],
        "is_acceptance_evidence": False,
        "note": ("measurement only: the increment is the concurrent working set at n "
                 "workers, measured on short runs and applied to the frozen scale"),
        "decision": decision,
    }
    out_path = REPO / "artifacts/audit/worker_commit_sweep_RC.json"
    out_path.write_text(
        json.dumps(out, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(f"EVIDENCE={out_path.name}")
    return 0 if decision.get("selected_workers") else 1


if __name__ == "__main__":
    raise SystemExit(main())
