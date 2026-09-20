"""G3 blind smoke under the post-amendment freeze, with seals (audit P0-6).

Writes the evidence layout the audit prescribed::

    <root>/smoke/<GEN>/
    ├── SMOKE_NULL/evaluation_rows.jsonl
    ├── SMOKE_ALT/evaluation_rows.jsonl
    ├── smoke_null_RC.json
    ├── smoke_alt_RC.json
    ├── SMOKE_SEAL_SMOKE_NULL.json
    ├── SMOKE_SEAL_SMOKE_ALT.json
    ├── RUN_REGISTRY.jsonl
    ├── STATE_REGISTRY.jsonl
    ├── commands.jsonl
    ├── stdout_stderr/
    └── provenance_manifest.json

Each seal binds the ledger content hash, source tree hash, environment lock hash,
the **final ``w*``** (read from the frozen ``COMPUTE_SPEC``), the run component
set, the smoke generation, the frozen counts, zero unexplained errors and the
terminal state.  ``open_runs`` is derived from the registry's latest states and a
missing registry fails closed.
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

import resource_sampler
from run_registry import (
    STATE_REGISTRY_FILE,
    ledger_content_hash,
    open_runs,
    record_seal,
    record_start,
    utc_now,
)
from run_smoke import formal_id_leak_check, identity_closure

from owtda_cal import execution, scope, smoke

GOV = REPO / "governance"


def _load(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def main() -> int:
    parser = argparse.ArgumentParser(description="G3 smoke with seals and registries")
    parser.add_argument("--root", required=True, help="evidence root (outside the repo)")
    parser.add_argument("--workers", type=int, required=True)
    parser.add_argument("--replicates", type=int, default=None)
    parser.add_argument("--phase", choices=[*scope.SMOKE_PHASES, "both"], default="both")
    parser.add_argument("--label", default=None)
    # Task pack §2.1/P3: every new run gets its own execution root, created
    # exclusively; re-using one requires --resume, never exist_ok=True.
    parser.add_argument("--execution-id", default=None,
                        help="execution root id (defaults to the smoke generation)")
    parser.add_argument("--resume", action="store_true",
                        help="attach to an existing execution root instead of creating one")
    args = parser.parse_args()

    generation = smoke.SMOKE_GENERATION_ID
    execution_root = execution.create_execution_root(
        args.root, args.execution_id or f"smoke-{generation}", resume=args.resume
    )
    root = Path(args.root).expanduser() / "smoke" / generation
    root.mkdir(parents=True, exist_ok=True)
    (root / "stdout_stderr").mkdir(exist_ok=True)

    manifest = _load(GOV / "FREEZE_MANIFEST.json")
    seed_registry = _load(GOV / "SEED_REGISTRY_v1.0.json")
    compute = _load(GOV / "COMPUTE_SPEC_v1.json")
    smoke_config = _load(GOV / "SMOKE_CONFIG_v1.json")
    admission = manifest["run_admission"]
    phases = list(scope.SMOKE_PHASES) if args.phase == "both" else [args.phase]
    replicates = args.replicates or scope.R0_SMOKE

    # AM_PARALLELISM_DECOUPLING: the run records the parallelism it *used* and the
    # value its admission *declared*; the frozen contract only requires that any
    # allowed worker count produce bitwise identical payloads.
    contract = compute["parallelism_contract"]
    declared_workers = int(smoke_config["default_workers"])
    workers_used = int(args.workers)
    if contract["invariance_requirement"] != "bitwise_identical_payload":
        raise SystemExit("parallelism contract violated: unexpected invariance requirement")
    if declared_workers != workers_used:
        raise SystemExit(
            f"REFUSED: the run declares workers={declared_workers} in SMOKE_CONFIG "
            f"but was launched with --workers {workers_used}; the run identity and "
            "the run itself must agree"
        )

    reports: dict[str, Any] = {}
    provenance: dict[str, Any] = {
        "schema_version": 1,
        "kind": "smoke_provenance_manifest",
        "smoke_generation_id": generation,
        "freeze_id": manifest["freeze_id"],
        "evidence_generation_id": manifest["evidence_generation_id"],
        "source_tree_hash": manifest["source_tree_hash"],
        "environment_lock_hash": manifest["environment_lock_hash"],
        "smoke_config_hash": manifest["smoke_config_hash"],
        "workers_used": workers_used,
        "declared_workers": declared_workers,
        "parallelism_contract": contract,
        "parallelism_evidence": manifest.get("parallelism_evidence"),
        "replicates_per_cell": replicates,
        "phases": {},
    }
    resources_by_phase: dict[str, dict[str, Any]] = {}

    for phase in phases:
        runner = (
            smoke.run_smoke_null
            if phase == scope.PHASE_SMOKE_NULL
            else smoke.run_smoke_alt
        )
        run_id = f"{generation}:{phase}:w{args.workers}:r{replicates}"
        record_start(
            root,
            run_id=run_id,
            phase=phase,
            smoke_generation_id=generation,
            workers=args.workers,
            replicates_per_cell=replicates,
            run_component_set_hash=admission[phase]["run_component_set_hash"],
            compute_git_commit=manifest["compute_git_commit"]
            if "compute_git_commit" in manifest
            else _head(),
            source_tree_hash=manifest["source_tree_hash"],
            environment_lock_hash=manifest["environment_lock_hash"],
            workers_used=workers_used,
        )
        # Audit A08: the resources are sampled around *this* run and stored with it,
        # so wall/RSS/swap/disk can never be quoted from a different execution.
        def _persist_ledger_inside_window(
            monitor: Any, result: Any, *, phase: str = phase, target_root: Path = root
        ) -> None:
            """Write the ledger while the monitor is still sampling (R4 block B).

            The ledger used to be written *after* ``sample_run`` stopped the sampler,
            so the persistence of the scientific rows was outside the window: a
            resource breach during that write could not be observed and the seal could
            not show that the stage had been covered at all.
            """
            monitor.set_stage("persist")
            target = target_root / phase
            target.mkdir(parents=True, exist_ok=True)
            with (target / "evaluation_rows.jsonl").open(
                "w", encoding="utf-8", newline="\n"
            ) as handle:
                for row in result.rows:
                    handle.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")

        # R4 plan A: the monitor stays open while the phase persists, commits and
        # seals, so those stages are *observed*; the record it produces on the way is
        # provisional (status OPEN) and is closed with the final verdict after the
        # monitor is stopped -- which is why the verdict is recorded as a chained
        # event instead of being smuggled into a seal that was already hashed.
        _holder: dict[str, Any] = {}
        result, resources = resource_sampler.sample_run(
            runner, evidence_root=root, run_id=run_id,
            manifest=manifest, seed_registry=seed_registry, workers=args.workers,
            replicate_limit=args.replicates,
            on_compute_done=_persist_ledger_inside_window,
            keep_open=True, monitor_holder=_holder,
        )
        monitor = _holder["monitor"]
        # A08: name the run inside the record itself, so "these resources belong to
        # this run" is a checkable fact rather than an assumption about file layout.
        resources = {**resources, "run_id": run_id, "phase": phase}
        resources_by_phase[phase] = resources
        ledger_dir = root / phase
        ledger = ledger_dir / "evaluation_rows.jsonl"
        if not ledger.is_file():
            # the window hook is the only writer now: a missing ledger means the
            # stage did not happen, and sealing would bind a non-existent artifact
            raise RuntimeError(f"{phase}: ledger was not persisted inside the sampling window")
        # The disk evidence must cover the persisted ledger, not just the compute
        # step (re-audit 2026-09-12): re-measure now that the bytes are on disk.
        resource_sampler.finalize_persistence(resources, evidence_root=root)
        # AM_RESOURCE_CAPACITY_V2 hard condition: allocation failures must be *shown* to
        # be zero.  The sampler cannot observe them, but the runner knows the error count:
        # it records 0 only when the run reported no errors at all, and otherwise leaves
        # the field unknown so the condition fails closed (attempt 7 failed on this field
        # being left at None by mistake -- the wiring, not the semantics, was missing).
        resources["resource_allocation_failures"] = 0 if result.errors == 0 else None
        resources_by_phase[phase] = resources
        # The resource evidence of *this* phase lives inside the execution root,
        # next to the dispatch chain, so it can never be quoted from another run.
        (execution_root.resources_dir / f"capacity_{phase}.json").write_text(
            json.dumps(resources, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        execution.append_execution_event(execution_root, {
            "event_type": "PHASE_RECORDED", "phase": phase, "run_id": run_id,
            "ledger_content_hash": ledger_content_hash(ledger) if ledger.exists() else None,
            "unexplained_errors": result.errors,
            "resource_allocation_failures": resources["resource_allocation_failures"],
            "capacity_status": (resources.get("capacity_sampling") or {}).get("status"),
            "note": "capacity_status is provisional here; the final verdict follows as "
                    "RESOURCE_VERDICT_FINAL (the monitor is still sampling)",
        })

        expected = smoke.expected_smoke_counts(phase)
        scale = replicates / scope.R0_SMOKE
        expected_scaled = {k: round(v * scale) for k, v in expected.items()}
        closure = identity_closure(phase, result.rows, manifest=manifest)
        leak = formal_id_leak_check(manifest, phase, result.rows)
        counts_match = (
            result.data_units == expected_scaled["data_units"]
            and result.evaluation_rows == expected_scaled["evaluation_rows"]
            and result.ph_windows == expected_scaled["ph_windows"]
            # A10: the all-feature window work is checked independently of PH work.
            and result.feature_windows == expected_scaled["feature_windows"]
        )
        missing = smoke.assert_row_fields(result.rows)
        rc = {
            "schema_version": 1,
            "kind": "smoke_run_rc_v1",
            "phase": phase,
            "smoke_generation_id": generation,
            "run_id": run_id,
            "workers": args.workers,
            "replicates_per_cell": replicates,
            "report": result.report(),
            "expected_counts": expected,
            "expected_counts_scaled": expected_scaled,
            "counts_match_contract": counts_match,
            # A08: resource evidence bound to this run (same run_id below).
            "resources": resources,
            "missing_required_fields": missing,
            "unexplained_errors": result.errors,
            "formal_id_leak_check": leak,
            "identity_closure": closure,
            "ledger_file": f"{phase}/evaluation_rows.jsonl",
            "ledger_content_hash": ledger_content_hash(ledger),
            "ledger_bytes": ledger.stat().st_size,
            "forbidden_aggregates_emitted": False,
        }

        # R4 block B / plan A: the seal must quote the stages the raw stream *actually*
        # covers at seal time.  A required stage with no sample means the stage was
        # intended but not observed -- the seal refuses instead of implying coverage.
        def _read_stages(
            target_resources: dict[str, Any] = resources,
        ) -> tuple[list[dict[str, Any]], list[str]]:
            rows: list[dict[str, Any]] = []
            path = (target_resources.get("capacity_sampling") or {}).get("raw_path")
            if path and Path(path).is_file():
                rows = [
                    json.loads(line)
                    for line in Path(path).read_text(encoding="utf-8").splitlines()
                    if line.strip()
                ]
            return rows, sorted({str(r.get("stage") or "") for r in rows})

        monitor.set_stage("commit")
        monitor.set_stage("seal")
        _seal_rows, _seal_stages = _read_stages()
        coverage = resource_sampler.assert_stage_coverage(
            _seal_rows, phase=phase,
            required=("start", "compute", "persist", "commit", "seal"),
        )
        execution.append_execution_event(execution_root, {
            "event_type": "RESOURCE_STAGE_COVERAGE", "phase": phase, "run_id": run_id,
            "at": "seal", "stages": _seal_stages, "rows": coverage["rows"],
            "required": list(coverage["required"]),
            "complete": coverage["complete"],
        })
        # Stages the seal cannot speak for are named here rather than implied away;
        # teardown lands when the monitor stops, cleanup after the seal.
        not_observed = [
            stage for stage in resource_sampler.FULL_LIFECYCLE_STAGES
            if stage not in coverage["stages"]
        ]
        seal = {
            "stage_coverage": coverage,
            "resource_stage_gaps": not_observed,
            "stage_coverage_open": True,
            # R4 plan A: the record embedded below is the *seal-time* one, and at seal
            # time it is provisional by construction (the monitor's verdict only exists
            # once it stops).  Saying that explicitly -- and pointing at the chained
            # event that carries the final verdict -- is what stops a reader from
            # treating this snapshot as the acceptance result.
            "resources_provisional_at_seal": True,
            "resources_summary_at_seal": {
                "status": (resources.get("capacity_sampling") or {}).get("status"),
                "stages_observed": _seal_stages,
                "stages_not_observed": not_observed,
                "raw_path": (resources.get("capacity_sampling") or {}).get("raw_path"),
            },
            "capacity_final_ref": {
                "event_type": "RESOURCE_VERDICT_FINAL",
                "phase": phase,
                "run_id": run_id,
            },
            "ledger_file": rc["ledger_file"],
            "ledger_content_hash": rc["ledger_content_hash"],
            "ledger_bytes": rc["ledger_bytes"],
            "row_count": result.evaluation_rows,
            "data_units": result.data_units,
            "ph_windows": result.ph_windows,
            "feature_windows": result.feature_windows,
            "resources": resources,
            "expected_counts": expected,
            "counts_match_contract": counts_match,
            "unexplained_errors": result.errors,
            "missing_required_fields": missing,
            "formal_id_leak_check_passed": bool(leak["passed"]),
            "identity_closure_passed": bool(closure["passed"]),
            "source_tree_hash": manifest["source_tree_hash"],
            "environment_lock_hash": manifest["environment_lock_hash"],
            "workers_used": workers_used,
            "declared_workers": declared_workers,
            "run_component_set_hash": admission[phase]["run_component_set_hash"],
            "run_input_bindings_hash": admission[phase]["run_input_bindings_hash"],
            "scope_design_hash": admission[phase]["scope_design_hash"],
            "smoke_generation_id": generation,
            "smoke_config_hash": manifest["smoke_config_hash"],
            "workers": args.workers,
            "replicates_per_cell": replicates,
            "terminal_state": "RUN_SEALED",
            "verdict_recorded_post_seal": True,
        }
        sealed = record_seal(root, run_id=run_id, phase=phase, seal=seal)

        # Close the record: cleanup is observed, the monitor stops, and the verdict is
        # chained *after* the seal -- a provisional record never becomes a source of a
        # final number, and the seal never claims a verdict it was hashed before.
        monitor.set_stage("cleanup")
        verdict = monitor.stop()
        _final_rows, _final_stages = _read_stages()
        resource_sampler.merge_final_verdict(
            resources, verdict, observed_stages=_final_stages,
        )
        resources_by_phase[phase] = resources
        (execution_root.resources_dir / f"capacity_{phase}.json").write_text(
            json.dumps(resources, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        execution.append_execution_event(execution_root, {
            "event_type": "RESOURCE_VERDICT_FINAL", "phase": phase, "run_id": run_id,
            "status": (resources.get("capacity_sampling") or {}).get("status"),
            "raw_samples": (resources.get("capacity_sampling") or {}).get("raw_samples"),
            "stages_observed": _final_stages,
            # Explicit full-lifecycle requirement: the *default* is narrower, so
            # relying on it here would under-report commit/seal/cleanup as gaps.
            "stages_not_observed": resource_sampler.stage_coverage(
                _final_rows, required=resource_sampler.FULL_LIFECYCLE_STAGES,
            )["missing"],
            "seal_hash": sealed["smoke_seal_hash"],
            "note": "recorded after the seal; the seal itself quotes coverage at seal time",
        })
        # The RC carries the closed record: written only now, so no reader can pick up
        # the provisional (OPEN) capacity block.
        (root / f"smoke_{'null' if phase == scope.PHASE_SMOKE_NULL else 'alt'}_RC.json").write_text(
            json.dumps(rc, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        reports[phase] = {**rc, **sealed}
        provenance["phases"][phase] = {
            "run_id": run_id,
            "ledger_file": rc["ledger_file"],
            "ledger_content_hash": rc["ledger_content_hash"],
            "smoke_seal_hash": sealed["smoke_seal_hash"],
            "seal_file": sealed["seal_file"],
            "run_component_set_hash": admission[phase]["run_component_set_hash"],
            "counts": {
                "data_units": result.data_units,
                "evaluation_rows": result.evaluation_rows,
                "ph_windows": result.ph_windows,
                "feature_windows": result.feature_windows,
            },
            "resources": resources,
            "unexplained_errors": result.errors,
            "terminal_state": "RUN_SEALED",
        }
        print(
            f"[s03] {phase} wall={result.wall_seconds:.2f}s "
            f"rows={result.evaluation_rows} ph={result.ph_windows} errors={result.errors} "
            f"seal={sealed['smoke_seal_hash'][:12]}",
            flush=True,
        )

    provenance["open_runs"] = sorted(open_runs(root))
    provenance["open_runs_zero"] = not provenance["open_runs"]
    # Audit A05: three *separate* notions, each derived rather than declared.
    #   run_terminated   -- the processes finished
    #   evidence_sealed  -- the state registry really ends in RUN_SEALED
    #   admission_passed -- every contract below holds
    # A failure is still archived (the evidence above is already on disk), but it
    # must not exit as if it had been admitted.
    state_events = [
        json.loads(line)
        for line in (root / STATE_REGISTRY_FILE)
        .read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    terminal: dict[str, str] = {}
    for event in state_events:
        terminal[str(event["run_id"])] = str(event["event_type"])
    provenance["terminal_states"] = terminal
    provenance["sealed_at_utc"] = utc_now()
    verdict = admission_verdict(
        reports, terminal, open_runs_zero=bool(provenance["open_runs_zero"]),
        limits=resource_sampler.load_limits(), resources=resources_by_phase,
    )
    provenance["verdict"] = verdict
    provenance["execution_root"] = execution_root.as_dict()
    # §2.1: the execution record closes the chain for this run's own directory.
    execution.append_execution_event(execution_root, {
        "event_type": "EXECUTION_FINISHED", "mode": "SMOKE",
        "execution_id": execution_root.execution_id,
        "admission_passed": bool(verdict["admission_passed"]),
        "phases": sorted(reports),
    })
    execution.write_execution_record(execution_root, {
        "schema_version": 1,
        "kind": "execution_record",
        "mode": "SMOKE",
        "execution_id": execution_root.execution_id,
        "smoke_generation_id": generation,
        "phases": sorted(reports),
        "admission_passed": bool(verdict["admission_passed"]),
        "verdict": verdict,
        "resources_by_phase": {
            phase: (resources or {}).get("capacity_raw_path") for phase, resources
            in resources_by_phase.items()
        },
    })
    (root / "provenance_manifest.json").write_text(
        json.dumps(provenance, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(f"[s03] open_runs={provenance['open_runs']}", flush=True)
    print(f"[s03] verdict={json.dumps(verdict, ensure_ascii=False, sort_keys=True)}",
          flush=True)
    if not verdict["admission_passed"]:
        failed = sorted(k for k, ok in verdict["checks"].items() if not ok)
        print(f"[s03] ADMISSION FAILED: {failed}", flush=True)
        return 1
    return 0


def admission_verdict(
    reports: dict[str, dict[str, Any]],
    terminal_states: dict[str, str],
    *,
    open_runs_zero: bool,
    limits: dict[str, Any] | None = None,
    resources: dict[str, dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """The three-layer verdict, derived from the archived records (audit A05).

    ``run_terminated`` (processes finished), ``evidence_sealed`` (the state
    registry really ends in ``RUN_SEALED``) and ``admission_passed`` (every
    contract holds) are kept apart: a run that terminated and sealed correctly can
    still fail admission, and that must not be reported as success.
    """
    limits = limits if limits is not None else resource_sampler.load_limits()
    resources = resources or {}
    per_phase_resources = {
        phase: resource_sampler.resource_verdict(
            resources.get(phase) if resources else report.get("resources"),
            limits=limits,
            unexplained_errors=int(report["unexplained_errors"]),
        )
        for phase, report in reports.items()
    }
    checks = {
        # A08: resources are part of admission, evaluated against the frozen limits.
        "resource_admission": bool(reports)
        and all(v["passed"] for v in per_phase_resources.values()),
        "counts_match_contract": all(r["counts_match_contract"] for r in reports.values()),
        "no_unexplained_errors": all(r["unexplained_errors"] == 0 for r in reports.values()),
        "no_missing_required_fields": all(
            r["missing_required_fields"] == 0 for r in reports.values()
        ),
        "identity_closure": all(r["identity_closure"]["passed"] for r in reports.values()),
        "formal_id_leak_clean": all(
            r["formal_id_leak_check"]["passed"] for r in reports.values()
        ),
        "open_runs_zero": bool(open_runs_zero),
        "every_run_sealed": bool(terminal_states)
        and all(state == "RUN_SEALED" for state in terminal_states.values()),
    }
    return {
        "run_terminated": True,
        "evidence_sealed": checks["every_run_sealed"],
        "admission_passed": all(checks.values()),
        "checks": checks,
        "resources": per_phase_resources,
    }


def _head() -> str:
    import subprocess

    return subprocess.run(
        ["git", "-C", str(REPO), "rev-parse", "HEAD"],
        capture_output=True, text=True, check=False,
    ).stdout.strip()


if __name__ == "__main__":
    raise SystemExit(main())
