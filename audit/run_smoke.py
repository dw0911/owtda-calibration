"""Run the G3 blind smoke and emit the §9.4 (H0 part) budget evidence (B15b).

The smoke is *blind*: this script reports wall time, counts and errors only.
It never prints or persists a rejection-rate summary, method ranking or any
aggregate usable for parameter selection.

Budget extrapolation follows Plan §9.4 exactly:

    t_H0_hat = 1.25 * (2500/32) * t_0,32
    t_H1_hat = 1.25 * (1600/32) * t_1,32      (H1 smoke runs in B15c)
    t_core_hat = t_H0_hat + t_H1_hat
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "src"))

from owtda_cal import scope, smoke

GOV = REPO / "governance"
WALL_LIMIT_H0_HOURS = 192.0
WALL_LIMIT_H1_HOURS = 76.8
WALL_LIMIT_CORE_HOURS = 268.8
SCALE_FACTOR = 1.25
R0_FORMAL_H0 = 2500
R0_FORMAL_H1 = 1600


def _load(name: str) -> dict[str, Any]:
    return json.loads((GOV / name).read_text(encoding="utf-8"))


def main() -> int:
    parser = argparse.ArgumentParser(description="G3 blind smoke (SMOKE_NULL)")
    parser.add_argument("--workers", type=int, default=1)
    parser.add_argument("--replicates", type=int, default=None)
    parser.add_argument("--out", default="artifacts/audit/smoke_RC.json")
    args = parser.parse_args()

    manifest = _load("FREEZE_MANIFEST.json")
    seed_registry = _load("SEED_REGISTRY_v1.0.json")

    result = smoke.run_smoke_null(
        manifest=manifest,
        seed_registry=seed_registry,
        workers=args.workers,
        replicate_limit=args.replicates,
    )
    replicates = args.replicates or scope.R0_SMOKE
    expected = smoke.expected_smoke_counts()
    scale = replicates / scope.R0_SMOKE
    expected_scaled = {k: round(v * scale) for k, v in expected.items()}
    missing_fields = smoke.assert_row_fields(result.rows)

    t_0_32 = result.wall_seconds * (scope.R0_SMOKE / replicates)
    t_h0_hat_hours = SCALE_FACTOR * (R0_FORMAL_H0 / scope.R0_SMOKE) * t_0_32 / 3600.0
    t_h1_hat_hours = SCALE_FACTOR * (R0_FORMAL_H1 / scope.R0_SMOKE) * t_0_32 / 3600.0

    shard_dir = REPO / "artifacts/smoke/SMOKE_NULL"
    shard_dir.mkdir(parents=True, exist_ok=True)
    ledger = shard_dir / f"evaluation_rows_w{args.workers}_r{replicates}.jsonl"
    with ledger.open("w", encoding="utf-8", newline="\n") as fh:
        for row in result.rows:
            fh.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")

    counts_match = (
        result.data_units == expected_scaled["data_units"]
        and result.evaluation_rows == expected_scaled["evaluation_rows"]
        and result.ph_windows == expected_scaled["ph_windows"]
    )

    import shutil

    resources: dict[str, Any] = {
        "ledger_bytes": ledger.stat().st_size,
        "disk_free_bytes": shutil.disk_usage("F:/").free,
    }
    try:
        import psutil

        info = psutil.Process().memory_info()
        resources["peak_rss_bytes"] = int(getattr(info, "peak_wset", info.rss))
        swap = psutil.swap_memory()
        resources["swap_used_bytes"] = int(swap.used)
        resources["swap_gate"] = "no_swap_observed" if swap.used == 0 else "swap_in_use"
    except Exception:  # noqa: BLE001  # pragma: no cover - optional dependency
        resources["peak_rss_bytes"] = None
        resources["swap_gate"] = "unmeasured"

    admission = manifest.get("run_admission", {}).get(scope.PHASE_SMOKE_NULL, {})
    evidence = {
        "schema_version": 1,
        "kind": "smoke_run_rc_v1",
        "status": "rc_preliminary" if replicates != scope.R0_SMOKE else "g3_smoke",
        "phase": scope.PHASE_SMOKE_NULL,
        "workers": args.workers,
        "replicates_per_cell": replicates,
        "report": result.report(),
        "expected_counts": expected,
        "expected_counts_scaled": expected_scaled,
        "counts_match_contract": counts_match,
        "missing_required_fields": missing_fields,
        "unexplained_errors": result.errors,
        "provenance": {
            "run_component_set_file": admission.get("run_component_set_file"),
            "run_component_set_hash": admission.get("run_component_set_hash"),
            "run_input_bindings_hash": admission.get("run_input_bindings_hash"),
            "scope_design_hash": admission.get("scope_design_hash"),
            "source_tree_hash": manifest["source_tree_hash"],
            "environment_lock_hash": manifest["environment_lock_hash"],
            "smoke_config_hash": manifest["smoke_config_hash"],
        },
        "resources": resources,
        "ledger_file": str(ledger.relative_to(REPO)).replace("\\", "/"),
        "budget": {
            "t_0_32_seconds": t_0_32,
            "t_h0_hat_hours": t_h0_hat_hours,
            "t_h1_hat_hours_using_h0_smoke": t_h1_hat_hours,
            "t_core_hat_hours_using_h0_smoke": t_h0_hat_hours + t_h1_hat_hours,
            "limits": {
                "h0_wall_hours": WALL_LIMIT_H0_HOURS,
                "h1_wall_hours": WALL_LIMIT_H1_HOURS,
                "core_wall_hours": WALL_LIMIT_CORE_HOURS,
            },
            "h0_gate_pass": t_h0_hat_hours <= WALL_LIMIT_H0_HOURS,
            "note": (
                "t_1,32 requires the SMOKE_ALT run (B15c); the H1 figure here is a "
                "placeholder derived from the H0 smoke and is NOT a Gate verdict."
            ),
        },
        "forbidden_aggregates_emitted": False,
    }
    out_path = REPO / args.out
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(
        json.dumps(evidence, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )

    print(
        f"SMOKE_NULL wall={result.wall_seconds:.2f}s data_units={result.data_units} "
        f"rows={result.evaluation_rows} ph_windows={result.ph_windows} errors={result.errors}"
    )
    print(f"counts_match_contract={counts_match} missing_fields={missing_fields}")
    print(f"t_0,32={t_0_32:.2f}s  t_H0_hat={t_h0_hat_hours:.3f}h  (limit {WALL_LIMIT_H0_HOURS}h)")
    print(f"evidence={out_path.relative_to(REPO)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
