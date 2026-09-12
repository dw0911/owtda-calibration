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
        "cmd": [sys.executable, "audit/collect_verification.py", "--root", "{out}/tests"]},
    3: {"name": "run_lifecycle_fixture",
        "cmd": [sys.executable, "audit/run_lifecycle_fixture.py", "--out",
                "{out}/test-lifecycle"]},
    4: {"name": "verify_concurrency_recovery",
        "cmd": [sys.executable, "scripts/verify_fault_points.py", "{out}/faults"]},
    5: {"name": "build_formal_expected_plan", "cmd": None},
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
    (out / "budget" ).mkdir(parents=True, exist_ok=True)
    (out / "budget" / "budget.json").write_text(
        json.dumps(budget, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8")
    return budget


def _preflight_step(out: Path) -> dict[str, Any]:
    import resource_sampler

    from owtda_cal.resource_policy import load_policy, preflight_capacity

    policy = load_policy()
    info = resource_sampler.performance_info()
    if info is None:
        return {"status": "PREFLIGHT_REFUSED",
                "reasons": ["capacity counters unavailable: the host cannot be measured"]}
    # the job's own increment is taken from the recorded attempt-7 style exposure
    # (~9.167 GB) with the policy's 5/4 margin applied inside preflight_capacity
    outcome = preflight_capacity(
        baseline_commit_bytes=int(info["commit_total_bytes"]),
        delta_commit_bytes=int(9.167 * 1024 ** 3),
        commit_limit_bytes=int(info["commit_limit_bytes"]),
        physical_available_bytes=int(info["physical_available_bytes"]),
        physical_total_bytes=int(info["physical_total_bytes"]),
        volumes=[{"name": str(out.drive or out),
                  "free_bytes": shutil.disk_usage(str(out)).free,
                  "required_bytes": 6 * 1024 ** 3}],
        workers=policy["limits"]["workers"], policy=policy,
    )
    (out / "preflight").mkdir(parents=True, exist_ok=True)
    (out / "preflight" / "preflight.json").write_text(
        json.dumps({**outcome, "host": info}, ensure_ascii=False, indent=2,
                   sort_keys=True) + "\n", encoding="utf-8")
    return outcome


def main() -> int:
    parser = argparse.ArgumentParser(description="run the §9 pre-admission sequence")
    parser.add_argument("out", help="evidence root (outside the repo)")
    parser.add_argument("--steps", default="1,2,3,4,6,7")
    args = parser.parse_args()

    out = Path(args.out).expanduser().resolve()
    out.mkdir(parents=True, exist_ok=True)
    requested = [int(x) for x in args.steps.split(",") if x.strip()]
    results: dict[str, Any] = {}

    for step in requested:
        spec = STEPS[step]
        entry: dict[str, Any] = {"step": step, "name": spec["name"]}
        if step == 5:
            entry.update({
                "status": "BLOCKED",
                "reason": (
                    "expanding the frozen plan needs the DGP identity derivation "
                    "(master_replicate_id / physical_cell_id / data_unit_id) per cell; "
                    "a plan built without it would not join to the real ledgers"
                ),
            })
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
            cmd = [part.format(out=str(out)) for part in spec["cmd"]]
            entry["command"] = cmd
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
        "may_start_smoke": bool(results.get("preflight_capacity", {}).get("passed")),
        "note": (
            "step 8 (a new-policy smoke) may start only when the preflight passes; "
            "steps 9-10 follow the smoke, not this script"
        ),
    }
    (out / "SEQUENCE_SUMMARY.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8")
    print(json.dumps({k: v["status"] for k, v in results.items()}, ensure_ascii=False))
    return 0 if all(v["status"] in ("PASS", "BLOCKED") for v in results.values()) else 1


if __name__ == "__main__":
    sys.exit(main())
