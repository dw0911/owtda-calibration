"""Run the G3 blind smoke for both phases and emit the §9.4 budget evidence (B15c).

The smoke is *blind*: this script reports wall time, counts, errors and identity
isolation only.  It never prints or persists a rejection-rate summary, method
ranking or any aggregate usable for parameter selection.

Budget extrapolation follows Plan §9.4 exactly:

    t_H0_hat = 1.25 * (2500/32) * t_0,32
    t_H1_hat = 1.25 * (1600/32) * t_1,32
    t_core_hat = t_H0_hat + t_H1_hat

``--phase both`` (the default) runs both blind smokes and writes
``artifacts/audit/smoke_RC.json`` (SMOKE_NULL) and
``artifacts/audit/smoke_alt_RC.json`` (SMOKE_ALT); the full Gate verdict is then
computed by ``audit/validate_admission.py``.
"""

from __future__ import annotations

import argparse
import json
import shutil
import sys
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "src"))

from owtda_cal import cells, dgp, scope, smoke

GOV = REPO / "governance"
WALL_LIMIT_H0_HOURS = 192.0
WALL_LIMIT_H1_HOURS = 76.8
WALL_LIMIT_CORE_HOURS = 268.8
SCALE_FACTOR = 1.25
R0_FORMAL_H0 = 2500
R0_FORMAL_H1 = 1600
#: Formal-ID leak check sample: replicates per (family/alternative, rho) checked.
LEAK_SAMPLE_REPLICATES = 2
PHASE_OUT = {
    scope.PHASE_SMOKE_NULL: "artifacts/audit/smoke_RC.json",
    scope.PHASE_SMOKE_ALT: "artifacts/audit/smoke_alt_RC.json",
}


def _load(name: str) -> dict[str, Any]:
    return json.loads((GOV / name).read_text(encoding="utf-8"))


def _data_model_hash(family: str, rho: str) -> str:
    if family == dgp.DGP_FAMILY_H1:
        return dgp.data_model_config_hash(dgp.h1_data_model_spec(
            scope.SCENARIO_ALT_SHAPE, rho))
    spec = (
        dgp.n_ar_data_model_spec(rho)
        if family == dgp.DGP_FAMILY_N_AR
        else dgp.n_circle_data_model_spec(rho)
    )
    return dgp.data_model_config_hash(spec)


def _formal_ids_for_null(
    manifest: dict[str, Any], *, family: str, rho: str, replicate: int
) -> set[str]:
    from owtda_cal import scope as sc

    data_model = _data_model_hash(family, rho)
    master = cells.master_replicate_id(
        project_id=manifest["project_id"],
        protocol_id=manifest["protocol_id"],
        freeze_id=manifest["freeze_id"],
        evidence_generation_id=manifest["evidence_generation_id"],
        phase=scope.PHASE_NULL, DGP_family=family, replicate_id=replicate,
    )
    out = {master}
    for cell in sc.h0_null_cells():
        if cell.family != family or cell.rho != rho:
            continue
        physical = cells.physical_cell_id(
            protocol_id=manifest["protocol_id"], freeze_id=manifest["freeze_id"],
            evidence_generation_id=manifest["evidence_generation_id"],
            phase=scope.PHASE_NULL, rho=rho, W=cell.W, stride=cell.stride,
            T=cell.T, M=cell.M, data_model_config_hash=data_model,
        )
        series = cells.base_series_id(
            master_replicate_id=master, data_generation_id="D01",
            DGP_family=family, rho=rho, raw_length=cells.L_MASTER,
            data_model_config_hash=data_model,
        )
        unit = cells.data_unit_id(
            base_series_id=series, physical_cell_id=physical,
            data_generation_id="D01",
        )
        logical = sc.logical_cell_id(
            project_id=manifest["project_id"],
            protocol_id=manifest["protocol_id"],
            freeze_id=manifest["freeze_id"],
            evidence_generation_id=manifest["evidence_generation_id"],
            phase=scope.PHASE_NULL, DGP_family=family,
            scenario_id=sc.SCENARIO_NULL, rho=rho, W=cell.W, stride=cell.stride,
            T=cell.T, M=cell.M,
        )
        data_key = sc.logical_data_key(
            logical_cell_id=logical, master_replicate_id=master
        )
        out.update({physical, series, unit, logical, data_key})
    return out


def _formal_ids_for_alt(
    manifest: dict[str, Any], *, scenario: str, rho: str, replicate: int
) -> set[str]:
    from owtda_cal import scope as sc

    family = dgp.DGP_FAMILY_H1
    data_model = dgp.data_model_config_hash(dgp.h1_data_model_spec(scenario, rho))
    master = cells.master_replicate_id(
        project_id=manifest["project_id"],
        protocol_id=manifest["protocol_id"],
        freeze_id=manifest["freeze_id"],
        evidence_generation_id=manifest["evidence_generation_id"],
        phase=scope.PHASE_ALT, DGP_family=family, replicate_id=replicate,
    )
    out = {master}
    for cell in sc.h1_alt_cells():
        if cell.scenario != scenario or cell.rho != rho:
            continue
        physical = cells.physical_cell_id(
            protocol_id=manifest["protocol_id"], freeze_id=manifest["freeze_id"],
            evidence_generation_id=manifest["evidence_generation_id"],
            phase=scope.PHASE_ALT, rho=rho, W=cell.W, stride=cell.stride,
            T=cell.T, M=cell.M, data_model_config_hash=data_model,
        )
        series = cells.base_series_id(
            master_replicate_id=master, data_generation_id="D01",
            DGP_family=family, rho=rho, raw_length=cell.T,
            data_model_config_hash=data_model,
        )
        unit = cells.data_unit_id(
            base_series_id=series, physical_cell_id=physical,
            data_generation_id="D01",
        )
        logical = sc.logical_cell_id(
            project_id=manifest["project_id"],
            protocol_id=manifest["protocol_id"],
            freeze_id=manifest["freeze_id"],
            evidence_generation_id=manifest["evidence_generation_id"],
            phase=scope.PHASE_ALT, DGP_family=family,
            scenario_id=cell.scenario, rho=rho, W=cell.W, stride=cell.stride,
            T=cell.T, M=cell.M,
        )
        data_key = sc.logical_data_key(
            logical_cell_id=logical, master_replicate_id=master
        )
        out.update({physical, series, unit, logical, data_key})
    return out


def formal_id_leak_check(
    manifest: dict[str, Any], phase: str, rows: list[dict[str, Any]]
) -> dict[str, Any]:
    """Reject any formal logical/concrete ID leaking into a smoke ledger (§16)."""
    formal: set[str] = set()
    replicates = range(min(LEAK_SAMPLE_REPLICATES, scope.R0_SMOKE))
    if phase == scope.PHASE_SMOKE_NULL:
        for family in scope.H0_FAMILIES:
            for rho in scope.RHO_LEVELS:
                for replicate in replicates:
                    formal |= _formal_ids_for_null(
                        manifest, family=family, rho=rho, replicate=replicate
                    )
    else:
        for scenario in (scope.SCENARIO_ALT_SHAPE, scope.SCENARIO_ALT_MEAN):
            for rho in scope.RHO_LEVELS:
                for replicate in replicates:
                    formal |= _formal_ids_for_alt(
                        manifest, scenario=scenario, rho=rho, replicate=replicate
                    )
    ledger_values: set[str] = set()
    for row in rows:
        ledger_values.update(v for v in row.values() if isinstance(v, str))
    leaked = sorted(formal & ledger_values)
    return {
        "formal_id_sample_replicates": LEAK_SAMPLE_REPLICATES,
        "formal_ids_checked": len(formal),
        "formal_ids_found_in_smoke_ledger": len(leaked),
        "passed": not leaked,
    }


def identity_closure(
    phase: str, rows: list[dict[str, Any]], *, manifest: dict[str, Any] | None = None
) -> dict[str, Any]:
    """Spec-derived closure check for the smoke ledger (audit A01/A05).

    The previous implementation compared **unique-ID counts**, which cannot see a
    wrong worklist: the audited ledger had the right number of cells and still
    shared no cell id with its own scope, and replacing one evaluation id with
    ``AUDIT_WRONG_ID`` kept every count intact.  Now the expectation is rebuilt
    from the specification by the single smoke enumerator, and the check is set
    equality plus row-by-row foreign keys.  Counts are still reported, but only as
    informational output.
    """
    from owtda_cal import smoke as smoke_mod

    if manifest is None:
        raise ValueError(
            "identity_closure requires the freeze manifest: the expectation must be "
            "rebuilt from the specification, not counted from the ledger"
        )
    ctx = smoke_mod.smoke_context(manifest, phase)
    report = smoke_mod.assert_smoke_ledger_matches_expected(
        ctx=ctx, replicate_count=scope.R0_SMOKE, ledger_rows=rows
    )
    counts = {
        key: len({row[key] for row in rows})
        for key in (
            "experiment_id", "logical_cell_id", "data_unit_id",
            "feature_sufficient_id", "evaluation_id", "logical_evaluation_key",
        )
    }
    return {
        "passed": True,
        "mode": "spec_derived_set_equality_plus_foreign_keys",
        "evaluation_rows": report["evaluation_rows"],
        "cells": report["cells"],
        "replicate_count": report["replicate_count"],
        "counts_informational": counts,
    }


def run_phase(
    *,
    phase: str,
    manifest: dict[str, Any],
    seed_registry: dict[str, Any],
    workers: int,
    replicates: int | None,
) -> dict[str, Any]:
    runner = (
        smoke.run_smoke_null
        if phase == scope.PHASE_SMOKE_NULL
        else smoke.run_smoke_alt
    )
    result = runner(
        manifest=manifest,
        seed_registry=seed_registry,
        workers=workers,
        replicate_limit=replicates,
    )
    used = replicates or scope.R0_SMOKE
    expected = smoke.expected_smoke_counts(phase)
    scale = used / scope.R0_SMOKE
    expected_scaled = {k: round(v * scale) for k, v in expected.items()}
    counts_match = (
        result.data_units == expected_scaled["data_units"]
        and result.evaluation_rows == expected_scaled["evaluation_rows"]
        and result.ph_windows == expected_scaled["ph_windows"]
    )
    missing_fields = smoke.assert_row_fields(result.rows)
    leak = formal_id_leak_check(manifest, phase, result.rows)
    closure = identity_closure(phase, result.rows, manifest=manifest)

    shard_dir = REPO / "artifacts/smoke" / phase
    shard_dir.mkdir(parents=True, exist_ok=True)
    ledger = shard_dir / f"evaluation_rows_w{workers}_r{used}.jsonl"
    with ledger.open("w", encoding="utf-8", newline="\n") as fh:
        for row in result.rows:
            fh.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")

    resources: dict[str, Any] = {
        "ledger_bytes": ledger.stat().st_size,
        "disk_free_bytes": shutil.disk_usage(REPO.drive + "\\").free,
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

    admission = manifest.get("run_admission", {}).get(phase, {})
    budget: dict[str, Any] = {
        "limits": {
            "h0_wall_hours": WALL_LIMIT_H0_HOURS,
            "h1_wall_hours": WALL_LIMIT_H1_HOURS,
            "core_wall_hours": WALL_LIMIT_CORE_HOURS,
        },
    }
    if phase == scope.PHASE_SMOKE_NULL:
        t_0_32 = result.wall_seconds * (scope.R0_SMOKE / used)
        t_h0_hat = SCALE_FACTOR * (R0_FORMAL_H0 / scope.R0_SMOKE) * t_0_32 / 3600.0
        budget.update(
            t_0_32_seconds=t_0_32,
            t_h0_hat_hours=t_h0_hat,
            h0_gate_pass=t_h0_hat <= WALL_LIMIT_H0_HOURS,
        )
    else:
        t_1_32 = result.wall_seconds * (scope.R0_SMOKE / used)
        t_h1_hat = SCALE_FACTOR * (R0_FORMAL_H1 / scope.R0_SMOKE) * t_1_32 / 3600.0
        budget.update(
            t_1_32_seconds=t_1_32,
            t_h1_hat_hours=t_h1_hat,
            h1_gate_pass=t_h1_hat <= WALL_LIMIT_H1_HOURS,
        )

    return {
        "schema_version": 1,
        "kind": "smoke_run_rc_v1",
        "status": "rc_preliminary" if used != scope.R0_SMOKE else "g3_smoke",
        "phase": phase,
        "smoke_generation_id": smoke.SMOKE_GENERATION_ID,
        "workers": workers,
        "replicates_per_cell": used,
        "report": result.report(),
        "expected_counts": expected,
        "expected_counts_scaled": expected_scaled,
        "counts_match_contract": counts_match,
        "missing_required_fields": missing_fields,
        "unexplained_errors": result.errors,
        "formal_id_leak_check": leak,
        "identity_closure": closure,
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
        "budget": budget,
        "forbidden_aggregates_emitted": False,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="G3 blind smoke")
    parser.add_argument(
        "--phase",
        choices=[scope.PHASE_SMOKE_NULL, scope.PHASE_SMOKE_ALT, "both"],
        default="both",
    )
    parser.add_argument("--workers", type=int, default=1)
    parser.add_argument("--replicates", type=int, default=None)
    args = parser.parse_args()

    manifest = _load("FREEZE_MANIFEST.json")
    seed_registry = _load("SEED_REGISTRY_v1.0.json")
    phases = (
        list(scope.SMOKE_PHASES) if args.phase == "both" else [args.phase]
    )
    for phase in phases:
        evidence = run_phase(
            phase=phase,
            manifest=manifest,
            seed_registry=seed_registry,
            workers=args.workers,
            replicates=args.replicates,
        )
        out_path = REPO / PHASE_OUT[phase]
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(
            json.dumps(evidence, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        report = evidence["report"]
        print(
            f"{phase} wall={report['wall_seconds']:.2f}s "
            f"data_units={report['data_units']} rows={report['evaluation_rows']} "
            f"ph_windows={report['ph_windows']} errors={report['errors']}"
        )
        print(
            f"  counts_match={evidence['counts_match_contract']} "
            f"missing_fields={evidence['missing_required_fields']} "
            f"formal_id_leak={evidence['formal_id_leak_check']['passed']} "
            f"identity_closure={evidence['identity_closure']['passed']}"
        )
        budget = evidence["budget"]
        if phase == scope.PHASE_SMOKE_NULL:
            print(
                f"  t_0,32={budget['t_0_32_seconds']:.2f}s "
                f"t_H0_hat={budget['t_h0_hat_hours']:.3f}h "
                f"(limit {WALL_LIMIT_H0_HOURS}h)"
            )
        else:
            print(
                f"  t_1,32={budget['t_1_32_seconds']:.2f}s "
                f"t_H1_hat={budget['t_h1_hat_hours']:.3f}h "
                f"(limit {WALL_LIMIT_H1_HOURS}h)"
            )
        print(f"  evidence={out_path.relative_to(REPO)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
