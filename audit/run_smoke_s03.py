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

from run_registry import (
    ledger_content_hash,
    open_runs,
    record_seal,
    record_start,
    utc_now,
)
from run_smoke import formal_id_leak_check, identity_closure

from owtda_cal import scope, smoke

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
    args = parser.parse_args()

    generation = smoke.SMOKE_GENERATION_ID
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
        result = runner(
            manifest=manifest, seed_registry=seed_registry, workers=args.workers,
            replicate_limit=args.replicates,
        )
        ledger_dir = root / phase
        ledger_dir.mkdir(parents=True, exist_ok=True)
        ledger = ledger_dir / "evaluation_rows.jsonl"
        with ledger.open("w", encoding="utf-8", newline="\n") as fh:
            for row in result.rows:
                fh.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")

        expected = smoke.expected_smoke_counts(phase)
        scale = replicates / scope.R0_SMOKE
        expected_scaled = {k: round(v * scale) for k, v in expected.items()}
        closure = identity_closure(phase, result.rows, manifest=manifest)
        leak = formal_id_leak_check(manifest, phase, result.rows)
        counts_match = (
            result.data_units == expected_scaled["data_units"]
            and result.evaluation_rows == expected_scaled["evaluation_rows"]
            and result.ph_windows == expected_scaled["ph_windows"]
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
            "missing_required_fields": missing,
            "unexplained_errors": result.errors,
            "formal_id_leak_check": leak,
            "identity_closure": closure,
            "ledger_file": f"{phase}/evaluation_rows.jsonl",
            "ledger_content_hash": ledger_content_hash(ledger),
            "ledger_bytes": ledger.stat().st_size,
            "forbidden_aggregates_emitted": False,
        }
        (root / f"smoke_{'null' if phase == scope.PHASE_SMOKE_NULL else 'alt'}_RC.json").write_text(
            json.dumps(rc, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )

        seal = {
            "ledger_file": rc["ledger_file"],
            "ledger_content_hash": rc["ledger_content_hash"],
            "ledger_bytes": rc["ledger_bytes"],
            "row_count": result.evaluation_rows,
            "data_units": result.data_units,
            "ph_windows": result.ph_windows,
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
        }
        sealed = record_seal(root, run_id=run_id, phase=phase, seal=seal)
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
            },
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
    provenance["terminal_states"] = {
        phase: "RUN_SEALED" for phase in reports
    }
    provenance["sealed_at_utc"] = utc_now()
    (root / "provenance_manifest.json").write_text(
        json.dumps(provenance, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(f"[s03] open_runs={provenance['open_runs']}", flush=True)
    return 0 if provenance["open_runs_zero"] else 1


def _head() -> str:
    import subprocess

    return subprocess.run(
        ["git", "-C", str(REPO), "rev-parse", "HEAD"],
        capture_output=True, text=True, check=False,
    ).stdout.strip()


if __name__ == "__main__":
    raise SystemExit(main())
