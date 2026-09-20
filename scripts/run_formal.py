"""§9 step 10 entry: the FORMAL_H0 admission gate (no computation happens here).

This script exists so that "start the formal phase" cannot be a side effect of a
loop somewhere: it validates the certificate against the frozen plan and the seed
registry, records the decision, and stops.  Dispatch is the shared
``execute_plan`` path, which currently refuses FORMAL modes until a real scientific adapter is integrated --
and that path is not wired for formal units yet, so this script never claims a run
took place.

Usage::

    python scripts/run_formal.py --plan <PLAN_DIR> --certificate <JSON> \
        [--seed-registry <JSON>] --out <EVIDENCE_DIR>
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "src"))

sys.path.insert(0, str(REPO / "audit"))

from owtda_cal import calibrate, formal, formal_pipeline, formal_rows, indexes, scope
from owtda_cal.execution import _formal_adapter_available
from owtda_cal.formal_admission import (
    CERTIFICATE_FILE,
    check_g4_h0_certificate,
    load_plan_summary,
)


def _load_governance() -> tuple[dict, dict]:
    manifest = json.loads((REPO / "governance" / "FREEZE_MANIFEST.json").read_text(encoding="utf-8"))
    seeds = json.loads((REPO / "governance" / "SEED_REGISTRY_v1.0.json").read_text(encoding="utf-8"))
    return manifest, seeds


def _formal_schemas(phase: str) -> tuple[dict, Any]:
    """The (DGP_family, scenario_id, feature_id, method_id) -> RowSchema map.

    The variant's field *roles* depend on the DGP family AND the scenario (e.g.
    ``observation_noise_seed`` is null for N_AR, value for N_CIRCLE/H1;
    ``shift_direction_seed`` is null for H1 shape, value for H1 mean), so every
    (family, scenario) of the phase is mapped.  NULL has scenario ``h0``; ALT has
    both ``shape_change`` and ``mean_shift``.
    """
    if phase == scope.PHASE_NULL:
        families = list(scope.H0_FAMILIES)
        scenarios = ["h0"]
    else:
        families = [dgp_family_for_phase(phase)]
        scenarios = [scope.SCENARIO_ALT_SHAPE, scope.SCENARIO_ALT_MEAN]
    schemas = {}
    for family in families:
        for scenario in scenarios:
            for feature_id in scope.FEATURE_IDS:
                for mid in (calibrate.M0_STABLE_ID, calibrate.M1_STABLE_ID):
                    schemas[(family, scenario, feature_id, mid)] = formal_rows.load_row_schema(
                        phase=phase, DGP_family=family, scenario_id=scenario,
                        feature_id=feature_id, method_id=mid,
                    )
    return schemas, formal_rows.load_feature_schema()


def dgp_family_for_phase(phase: str) -> str:
    from owtda_cal import dgp

    return dgp.DGP_FAMILY_N_AR if phase == scope.PHASE_NULL else dgp.DGP_FAMILY_H1


def _run_production(args, plan: dict) -> dict:
    """Dispatch the admitted formal run (NULL or ALT) and produce run + phase seal.

    This is the real production pipeline: full-lifecycle monitor + durable shard
    commit (``run_formal_phase_lifecycle``), then the strict run seal and phase
    seal layered on top.  NULL starts the validity registry at the all-zero head;
    ALT carries its ``parent_phase_seal_hash`` from the frozen run component set
    (which ``build_alt_admission`` bound to the authoritative H0 phase seal).
    """
    from run_formal_phase import run_formal_phase_lifecycle

    phase = getattr(args, "phase", scope.PHASE_NULL)
    manifest, seeds = _load_governance()
    admission = manifest.get("run_admission", {}).get(phase, {})
    if not admission:
        raise RuntimeError(
            f"run_admission missing the {phase} phase; run build_run_admission.py "
            "(or build_alt_admission.py for ALT) first"
        )
    run_component_set_hash = admission["run_component_set_hash"]
    scope_design_hash = admission["scope_design_hash"]
    environment_lock_hash = manifest["environment_lock_hash"]
    evidence_generation_id = manifest["evidence_generation_id"]
    component_set = json.loads(
        (REPO / "governance" / admission["run_component_set_file"]).read_text(encoding="utf-8")
    )
    schemas, feature_schema = _formal_schemas(phase)

    # Pre-declare the expected indexes up front, derive run_instance_id and the
    # shard plan from them, and carry that identity into every produced row --
    # so the rows' run identity and the committed shard plan agree by construction.
    predeclared = formal.predeclare_formal_indexes(
        manifest=manifest, phase=phase,
        replicate_limit=args.replicate_limit,
    )
    runtime_index_hashes = {
        "data": predeclared["expected_data_index_hash"],
        "feature": predeclared["expected_feature_index_hash"],
        "evaluation": predeclared["expected_index_hash"],
    }
    certified_index_hashes = plan.get("phases", {}).get(phase, {}).get("index_hashes", {})
    if runtime_index_hashes != certified_index_hashes:
        raise RuntimeError(
            "FORMAL_CERTIFIED_PLAN_MISMATCH: runtime predeclared indexes do not match "
            "the admitted PLAN_SUMMARY; regenerate/freeze the plan before running"
        )
    from owtda_cal import runs

    run_instance_id = runs.run_instance_id(
        phase=phase, evidence_generation_id=evidence_generation_id,
        run_component_set_hash=run_component_set_hash,
        expected_data_index_hash=predeclared["expected_data_index_hash"],
        expected_index_hash=predeclared["expected_index_hash"],
        expected_feature_index_hash=predeclared["expected_feature_index_hash"],
        environment_lock_hash=environment_lock_hash,
    )
    plan = formal_pipeline.build_shard_plan_from_indexes(
        run_instance_id=run_instance_id, phase=phase,
        expected_data_index_hash=predeclared["expected_data_index_hash"],
        expected_index_hash=predeclared["expected_index_hash"],
        expected_feature_index_hash=predeclared["expected_feature_index_hash"],
        evaluation_rows=predeclared["evaluation_rows"],
        feature_rows=predeclared["feature_rows"],
        partition=phase,
    )
    shard_plan_hash = indexes.shard_plan_hash(plan)
    run_identity = formal.formal_run_identity(
        component_set=component_set, predeclared=predeclared,
        run_component_set_hash=run_component_set_hash,
        run_instance_id=run_instance_id, shard_plan_hash=shard_plan_hash,
    )

    out = Path(args.out).expanduser()
    # sample_run's disk_free_bytes() needs the evidence root to exist before the
    # monitor starts; create it here rather than after dispatch (main() only
    # creates it after _run_production, which is too late).
    out.mkdir(parents=True, exist_ok=True)
    run_id = f"FORMAL_{phase}_{run_component_set_hash[:12]}"
    run_fn = formal.run_formal_h0 if phase == scope.PHASE_NULL else formal.run_formal_h1

    def runner(**kwargs: Any) -> Any:
        return run_fn(run_identity=run_identity, **kwargs)

    outcome = run_formal_phase_lifecycle(
        phase=phase, manifest=manifest, seed_registry=seeds,
        workers=args.workers, replicate_limit=args.replicate_limit,
        root=out, run_id=run_id, runner=runner,
        partition=phase,
        schemas=schemas, feature_schema=feature_schema,
        run_instance_id=run_instance_id,
        expected_index_hashes=runtime_index_hashes,
        expected_shard_plan_hash=shard_plan_hash,
    )

    result = outcome["result"]
    idx = outcome["indexes"]
    run_instance_id = outcome["run_instance_id"]
    run_seal = formal_pipeline.build_formal_run_seal(
        run_instance_id=run_instance_id,
        run_component_set_hash=run_component_set_hash,
        expected_data_index_hash=idx["expected_data_index_hash"],
        expected_index_hash=idx["expected_index_hash"],
        expected_feature_index_hash=idx["expected_feature_index_hash"],
        shard_plan_hash=outcome["shard_plan_hash"],
        commit_records=outcome["commit_records"],
        rows=result.rows, feature_rows=result.feature_rows,
        schemas=schemas, feature_schema=feature_schema,
    )
    run_seal_hash = indexes.run_seal_hash(run_seal)
    phase_seal = formal_pipeline.build_formal_phase_seal(
        phase=phase, evidence_generation_id=evidence_generation_id,
        scope_design_hash=scope_design_hash,
        run_seal=run_seal, run_seal_hash=run_seal_hash,
        validity_registry_head_hash="0" * 64,
        parent_phase_seal_hash=component_set.get("parent_phase_seal_hash"),
    )
    phase_seal_hash = indexes.phase_seal_hash(phase_seal)

    (out / "RUN_SEAL.json").write_text(
        json.dumps({"payload": run_seal, "run_seal_hash": run_seal_hash},
                   ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    (out / "PHASE_SEAL.json").write_text(
        json.dumps({"payload": phase_seal, "phase_seal_hash": phase_seal_hash},
                   ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return {
        "run_instance_id": run_instance_id,
        "run_seal_hash": run_seal_hash,
        "phase_seal_hash": phase_seal_hash,
        "shard_plan_hash": outcome["shard_plan_hash"],
        "commit_records": len(outcome["commit_records"]),
        "row_count": run_seal["row_count"],
        "data_unit_count": run_seal["produced_data_unit_count"],
        "feature_row_count": run_seal["feature_row_count"],
        "full_lifecycle": outcome["full_lifecycle"],
        "capacity_coverage_scope": outcome["capacity_coverage_scope"],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="FORMAL_H0 admission gate (§9 step 10)")
    parser.add_argument("--plan", required=True, help="plan directory (step 5 output)")
    parser.add_argument("--certificate", default=None,
                        help=f"G4_H0 certificate JSON (default: <plan>/../{CERTIFICATE_FILE})")
    parser.add_argument("--seed-registry", default=None, help="seed registry JSON")
    parser.add_argument("--out", required=True, help="evidence directory (outside the repo)")
    parser.add_argument("--workers", type=int, default=1, help="process workers (default 1)")
    parser.add_argument("--replicate-limit", type=int, default=None,
                        help="cap replicates (default: full R0_H0)")
    parser.add_argument("--phase", default=scope.PHASE_NULL,
                        choices=[scope.PHASE_NULL, scope.PHASE_ALT],
                        help="formal phase: NULL (H0) or ALT (H1); default NULL")
    args = parser.parse_args()

    plan = load_plan_summary(args.plan)
    certificate = args.certificate or str(Path(args.plan).parent / CERTIFICATE_FILE)
    decision = check_g4_h0_certificate(
        certificate_path=certificate, plan_summary=plan,
        seed_registry_path=args.seed_registry,
    )

    # Re-audit 2026-09-16 (Block A): the formal scientific adapter now exists, so
    # the certificate binding is no longer unconditionally downgraded.  The
    # binding must still pass *and* the adapter must be importable; a missing
    # adapter keeps the protective refusal (never a boolean unlock).
    adapter_available = _formal_adapter_available()
    decision = {
        **decision,
        "certificate_bindings_verified": decision["admitted"],
        "formal_adapter_available": adapter_available,
    }
    if decision["admitted"] and not adapter_available:
        decision = {
            **decision,
            "admitted": False,
            "status": "FORMAL_RUNNER_NOT_IMPLEMENTED",
            "codes": list(decision["codes"]) + ["FORMAL_RUNNER_NOT_IMPLEMENTED"],
        }

    if decision["admitted"]:
        # Re-audit 2026-09-17 (R5-05): the real production pipeline now exists --
        # dispatch it, then layer the run + phase seal onto the committed shards.
        production = _run_production(args, plan)
        decision = {
            **decision,
            "status": "ADMITTED_AND_SEALED",
            "production": production,
        }

    out = Path(args.out).expanduser()
    out.mkdir(parents=True, exist_ok=True)
    if (out / "FORMAL_ADMISSION.json").exists():
        parser.error("formal admission evidence already exists; choose a new --out")
    (out / "FORMAL_ADMISSION.json").write_text(
        json.dumps({"requested_phase": "H0", **decision}, ensure_ascii=False, indent=2,
                   sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({"status": decision["status"], "codes": decision["codes"],
                      "plan_totals": plan.get("totals")}, ensure_ascii=False))
    return 0 if decision["admitted"] else 1


if __name__ == "__main__":
    sys.exit(main())
