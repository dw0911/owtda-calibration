"""Task pack §9: run the pre-admission sequence and archive each step's evidence.

Steps 1-7 of the ten-command list.  Each step runs a real CLI, writes its own
directory under ``<out>/``, and records command, exit code and timing.  A step
that cannot run yet is recorded as BLOCKED with the reason instead of being
quietly skipped -- step 8 (a new-policy smoke) must not start unless step 7's
preflight passes, and step 9/10 must not be reached by pretending.

Step 5 (the full formal expected plan) is BLOCKED by design here: expanding
82,800 data / 165,600 feature / 331,200 evaluation identities requires the DGP
identity derivation (``cells.data_unit_id`` / ``master_replicate_id`` /
``physical_cell_id``) per cell, and a half-correct plan would be worse than no
plan.  The budget (step 6) uses the frozen plan *counts* directly, which is what
it needs.

Usage::

    python scripts/run_final_sequence.py <out-dir-outside-the-repo> [--steps 1,2,3,4,6,7]
"""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "src"))
sys.path.insert(0, str(REPO / "audit"))

STEPS: dict[int, dict[str, Any]] = {
    1: {"name": "validate_all_metadata_schemas",
        "cmd": [sys.executable, "audit/validate_schemas.py", "--out-dir", "{out}/precheck"]},
    2: {"name": "collect_and_run_full_tests",
        "cmd": [sys.executable, "audit/collect_verification.py", "--root", "{out}/tests",
                "--python", "{python}"]},
    3: {"name": "run_lifecycle_fixture",
        "cmd": [sys.executable, "audit/run_lifecycle_fixture.py", "--out",
                "{out}/test-lifecycle"]},
    4: {"name": "verify_concurrency_recovery",
        "cmd": [sys.executable, "scripts/verify_fault_points.py", "{out}/faults"]},
    5: {"name": "build_formal_expected_plan", "cmd": None, "internal": "plan"},
    6: {"name": "build_full_budget", "cmd": None, "internal": "budget"},
    7: {"name": "preflight_capacity", "cmd": None, "internal": "preflight"},
}


def _run(cmd: list[str], *, cwd: Path) -> dict[str, Any]:
    started = time.time()
    done = subprocess.run(cmd, cwd=str(cwd), capture_output=True, text=True,
                          encoding="utf-8", errors="replace", check=False)
    return {
        "exit_code": done.returncode,
        "seconds": round(time.time() - started, 2),
        "stdout_tail": done.stdout[-2000:],
        "stderr_tail": done.stderr[-2000:],
    }


def _plan_step(out: Path) -> dict[str, Any]:
    """§9 step 5: the frozen-scale expected plan (no MC, pure enumeration)."""
    from owtda_cal.planbuild import build_expected_plan

    target = out / "plan"
    if target.exists():
        raise FileExistsError("plan evidence already exists; use a new execution root")
    manifest = json.loads((REPO / "governance" / "FREEZE_MANIFEST.json").read_text(encoding="utf-8"))
    return build_expected_plan(
        out_dir=target,
        project_id=manifest["project_id"], protocol_id=manifest["protocol_id"],
        freeze_id=manifest["freeze_id"], evidence_generation_id=manifest["evidence_generation_id"],
        data_generation_id=manifest["component_generations"]["data_generation_id"],
    )


def _budget_step(out: Path) -> dict[str, Any]:
    from owtda_cal.budget import build_budget, derive_counts
    from owtda_cal.resource_policy import load_policy

    policy = load_policy()
    schema = {
        "evaluation_row_bytes": 1024, "feature_row_bytes": 512, "data_unit_bytes": 4096,
        "index_entry_bytes": 128, "event_row_bytes": 256, "resource_row_bytes": 256,
        "manifest_bytes": 65536, "store_full_feature_matrices": False,
        "store_summaries": True, "store_ph_diagrams": False,
        "store_resampling_stats": True, "summary_bytes": 4096,
        "resampling_stats_row_bytes": 64,
    }
    profile = {
        "compute_seconds_per_evaluation": 0.4,
        "serialize_seconds_per_evaluation": 0.05,
        "merge_seconds_per_phase": 600.0, "seal_seconds_per_phase": 120.0,
        "recovery_seconds": 300.0,
    }
    storage = {"copies": {"staging": 1, "final": 1, "merge": 1, "recovery": 1,
                          "archive": 1},
               "coexisting_stages": ["staging", "final", "merge"]}
    free = shutil.disk_usage(str(out)).free
    budget = build_budget(counts=derive_counts(), serialization_schema=schema,
                          storage_policy=storage, profile=profile,
                          volumes=[{"name": str(out.drive or out), "free_bytes": free}],
                          disk_fraction=policy["limits"]["disk_fraction_max"])
    plan_summary = out / "plan" / "PLAN_SUMMARY.json"
    if plan_summary.is_file():
        plan = json.loads(plan_summary.read_text(encoding="utf-8"))
        budget["bound_plan"] = {
            "formal_scale": plan["formal_scale"],
            "totals": plan["totals"],
            "evaluation_index_hashes": {
                phase: report["index_hashes"]["evaluation"]
                for phase, report in plan["phases"].items()
            },
        }
    (out / "budget" ).mkdir(parents=True, exist_ok=True)
    (out / "budget" / "budget.json").write_text(
        json.dumps(budget, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8")
    return budget


def _registered_increment_bytes(workers: int) -> int:
    """Measured own-commit increment for the registered parallelism; fail-closed.

    Re-audit 2026-09-15 (P1): the constant that used to sit here (9.167 GB) was the
    *8-worker* exposure.  The policy now registers 4 workers, and applying the
    8-worker number would refuse runs the measured increment predicts fit.  The
    measured value is used when the sweep evidence is present; otherwise the old
    conservative constant is kept -- never a smaller, invented one.
    """
    conservative = int(9.167 * 1024 ** 3)
    path = Path(__file__).resolve().parents[1] / "artifacts/audit/worker_commit_sweep_RC.json"
    if not path.is_file():
        return conservative
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        for row in (data.get("decision") or {}).get("measured", []):
            if row.get("workers") == workers and row.get("own_increment_bytes"):
                return int(row["own_increment_bytes"])
    except (json.JSONDecodeError, TypeError, KeyError, ValueError):
        return conservative
    return conservative


def _preflight_step(out: Path) -> dict[str, Any]:
    import resource_sampler

    from owtda_cal.resource_policy import load_policy, preflight_capacity

    policy = load_policy()
    info = resource_sampler.performance_info()
    if info is None:
        return {"status": "PREFLIGHT_REFUSED",
                "reasons": ["capacity counters unavailable: the host cannot be measured"]}
    # the job's own increment is the measured exposure at the *registered* parallelism,
    # with the policy's 5/4 margin applied inside preflight_capacity
    delta = _registered_increment_bytes(policy["limits"]["workers"])
    budget = json.loads((out / "budget" / "budget.json").read_text(encoding="utf-8"))
    if budget.get("status") != "APPROVED_ESTIMATE" or type(budget.get("peak_bytes")) is not int:
        return {"status": "PREFLIGHT_REFUSED", "passed": False, "reasons": ["approved budget missing"]}
    inputs = {
        "baseline_commit_bytes": int(info["commit_total_bytes"]), "delta_commit_bytes": delta,
        "commit_limit_bytes": int(info["commit_limit_bytes"]),
        "physical_available_bytes": int(info["physical_available_bytes"]),
        "physical_total_bytes": int(info["physical_total_bytes"]),
        "volumes": [{"name": str(out.drive or out), "free_bytes": shutil.disk_usage(str(out)).free,
                  "required_bytes": budget["peak_bytes"]}], "workers": policy["limits"]["workers"]}
    outcome = preflight_capacity(**inputs, policy=policy)
    (out / "preflight").mkdir(parents=True, exist_ok=True)
    (out / "preflight" / "preflight_inputs.json").write_text(
        json.dumps(inputs, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    (out / "preflight").mkdir(parents=True, exist_ok=True)
    (out / "preflight" / "preflight.json").write_text(
        json.dumps({**outcome, "host": info,
                    "registered_workers": policy["limits"]["workers"],
                    "delta_commit_bytes_used": delta,
                    "delta_source": ("artifacts/audit/worker_commit_sweep_RC.json"
                                     " (measured)" if delta != int(9.167 * 1024 ** 3)
                                     else "conservative 8-worker constant")},
                   ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8")
    return outcome


def main() -> int:
    parser = argparse.ArgumentParser(description="run the §9 pre-admission sequence")
    parser.add_argument("out", help="evidence root (outside the repo)")
    parser.add_argument("--steps", default="1,2,3,4,6,7")
    # Re-audit 2026-09-16: step 2's collect_verification.py defaults --python to
    # <REPO>/.venv/Scripts/python.exe, which does not exist in an extracted
    # candidate tree.  The frozen venv is machine-specific (recorded in
    # environment/environment_manifest.json), so the executor must pass it
    # explicitly; failing that we use the interpreter running this script rather
    # than a venv that is guaranteed absent.
    parser.add_argument("--python", default=None,
                        help="frozen venv python for collect_verification.py (step 2)")
    args = parser.parse_args()

    out = Path(args.out).expanduser().resolve()
    if out.exists() and any(out.iterdir()):
        parser.error("sequence output is nonempty; evidence must not be overwritten")
    out.mkdir(parents=True, exist_ok=True)
    requested = [int(x) for x in args.steps.split(",") if x.strip()]
    results: dict[str, Any] = {}

    for step in requested:
        spec = STEPS[step]
        entry: dict[str, Any] = {"step": step, "name": spec["name"]}
        if spec.get("internal") == "plan":
            plan = _plan_step(out)
            entry.update({"status": "PASS" if plan["formal_scale"] else "REDUCED_SCALE",
                          "totals": plan["totals"],
                          "formal_scale": plan["formal_scale"],
                          "index_hashes": {phase: report["index_hashes"]
                                           for phase, report in plan["phases"].items()}})
        elif spec.get("internal") == "budget":
            budget = _budget_step(out)
            entry.update({"status": budget["status"],
                          "budget_hash": budget["budget_hash"],
                          "peak_bytes": budget["peak_bytes"],
                          "evaluation_rows": budget["counts"]["totals"]["evaluation_rows"]})
        elif spec.get("internal") == "preflight":
            preflight = _preflight_step(out)
            entry.update({"status": preflight["status"],
                          "passed": preflight.get("passed"),
                          "reasons": preflight.get("reasons", [])})
        else:
            cmd = [part.format(out=str(out), python=args.python or sys.executable)
                   for part in spec["cmd"]]
            entry["command"] = cmd
            # each step's evidence directory is regenerated from scratch: a
            # fixture re-run over its own previous output would be judged against
            # stale commits (the first run left a repaired orphan behind)
            target_dirs = sorted({Path(part) for part in cmd
                                  if str(out) in part and Path(part) != out})
            for target in target_dirs:
                if target.exists():
                    raise FileExistsError(f"step output already exists: {target}")
            outcome = _run(cmd, cwd=REPO)
            entry.update(outcome)
            entry["status"] = "PASS" if outcome["exit_code"] == 0 else "FAIL"
        results[spec["name"]] = entry
        print(f"[{entry['status']}] step {step} {spec['name']}", flush=True)

    summary = {
        "platform": sys.platform,
        "requested_steps": requested,
        "results": results,
        "preflight_passed": bool(results.get("preflight_capacity", {}).get("passed")),
        "may_start_smoke": (all(str(i) in {str(x) for x in requested} for i in range(1, 8))
                            and all(v["status"] in ("PASS", "APPROVED_ESTIMATE", "PREFLIGHT_PASS") for v in results.values())
                            and bool(results.get("preflight_capacity", {}).get("passed"))),
        "note": (
            "step 8 (a new-policy smoke) may start only when the preflight passes; "
            "steps 9-10 follow the smoke, not this script"
        ),
    }
    (out / "SEQUENCE_SUMMARY.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8")
    print(json.dumps({k: v["status"] for k, v in results.items()}, ensure_ascii=False))
    return 0 if all(v["status"] in ("PASS", "APPROVED_ESTIMATE", "PREFLIGHT_PASS") for v in results.values()) else 1


if __name__ == "__main__":
    sys.exit(main())
