"""Dispatch the smoke phases through the shared execution entry (§4.1, step 8).

Why this is a wrapper and not a rewrite of ``audit/run_smoke_s03.py``: the phase
body is ~200 lines of production code whose payloads must stay bitwise identical,
and changing it can only be validated by a real 20-25 minute smoke run.  So the
*dispatch* is moved here instead:

* ``execute_plan`` is the single entry; ``mode="SMOKE"`` applies the mode gate
  (frozen engineering plan + 32 replicates, no size/power/ranking output);
* one unit per phase, bounded in-flight window (1), so the phases run in order
  and a latched stop cancels only what has not started;
* the monitored stop request cancels a phase **before** it starts, which is what
  "越界后停止派发" means for a two-unit plan;
* ``audit/run_smoke_s03.py`` runs unchanged, as a subprocess, so the scientific
  bytes are exactly what the frozen script produces.

``--stub`` replaces the subprocess with a marker-writing command, which is how
the wiring itself is validated without spending a smoke window.

Usage::

    python scripts/run_smoke_via_execution.py --out <EVIDENCE> --workers 8 [--stub]
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from concurrent import futures
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "src"))
sys.path.insert(0, str(REPO / "audit"))

from owtda_cal.execution import execute_plan
from owtda_cal.resource_policy import load_policy, policy_sha256

_STUB = (
    "import sys, json, time;"
    "time.sleep(0.2);"
    "open(sys.argv[1], 'w', encoding='utf-8').write(json.dumps({'phase': sys.argv[2]}))"
)


def phase_command(
    *,
    phase: str,
    out: Path,
    workers: int,
    replicates: int | None,
    dispatch_id: str,
    stub: bool,
) -> list[str]:
    """The subprocess command for one phase.

    Re-audit 2026-09-15: ``audit/run_smoke_s03.py`` creates its execution root
    **exclusively** and defaults the id to ``smoke-<generation>``.  Dispatching
    two phases under one root with that default meant the second phase was
    refused ("execution root already exists") before it wrote a single byte --
    attempt 9 failed exactly this way, with the reason swallowed as
    ``error_class=TASK_EXCEPTION``.  The per-phase id is therefore explicit here
    and must stay unique per phase; the character set is limited to what a
    Windows directory name accepts.
    """
    marker = out / f"dispatch_{phase}.json"
    if stub:
        return [sys.executable, "-c", _STUB, str(marker), phase]
    command = [
        sys.executable, str(REPO / "audit" / "run_smoke_s03.py"),
        "--root", str(out), "--workers", str(workers), "--phase", phase,
        "--execution-id", f"{dispatch_id}-{phase}",
    ]
    if replicates is not None:
        command += ["--replicates", str(replicates)]
    return command


def main() -> int:
    parser = argparse.ArgumentParser(description="smoke phases through execute_plan")
    parser.add_argument("--out", required=True, help="evidence root (outside the repo)")
    parser.add_argument("--workers", type=int, required=True)
    parser.add_argument("--replicates", type=int, default=None)
    parser.add_argument("--execution-id", default=None)
    parser.add_argument("--resume", action="store_true")
    parser.add_argument("--stub", action="store_true",
                        help="validate the wiring without running the real phases")
    args = parser.parse_args()

    load_policy()  # refuses an unbound or non-integer policy before any dispatch
    out = Path(args.out).expanduser().resolve()
    out.mkdir(parents=True, exist_ok=True)
    phases = ["SMOKE_NULL", "SMOKE_ALT"]
    units = [{"unit_id": f"phase:{phase}", "phase": phase} for phase in phases]
    plan = {
        "plan_id": f"SMOKE-{args.workers}w",
        "identity_domain": "SMOKE",
        "phase": "SMOKE",
        "units": units,
        "outputs": [],
    }

    dispatch_id = args.execution_id or f"smoke-{args.workers}w"

    def run_phase(unit: dict) -> str:
        phase = unit["phase"]
        command = phase_command(
            phase=phase, out=out, workers=args.workers,
            replicates=args.replicates, dispatch_id=dispatch_id, stub=args.stub,
        )
        done = subprocess.run(command, cwd=str(REPO), capture_output=True, text=True,
                              encoding="utf-8", errors="replace", check=False)
        if done.returncode != 0:
            tail = (done.stderr or done.stdout)[-1500:]
            raise RuntimeError(f"{phase} exited with {done.returncode}: {tail}")
        return json.dumps({"phase": phase, "exit_code": done.returncode})

    # a real pool, not an inline call: execute_plan's window/cancel semantics need
    # futures that can still be cancelled before they start
    with futures.ThreadPoolExecutor(max_workers=1) as pool:
        def submit(unit: dict, index: int):
            return pool.submit(run_phase, unit)

        record = execute_plan(
            plan, mode="SMOKE", evidence_root=out,
            manifests={"policy_sha256": policy_sha256(),
                       "workers": args.workers, "stub": bool(args.stub)},
            execution_id=dispatch_id,
            resume=args.resume, submit=submit, window_size=1,
            frozen_engineering_plan=True,
            replicates_32=(args.replicates in (None, 32)),
        )
    (out / "SMOKE_DISPATCH.json").write_text(
        json.dumps({k: v for k, v in record.items() if k != "records"},
                   ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({"mode": record["mode"], "terminal_state": record["terminal_state"],
                      "units": record["units"], "completed": record["completed"],
                      "execution_id": record["execution_id"],
                      "admitted": record["admission"]["admitted"],
                      "stub": bool(args.stub)}, ensure_ascii=False))
    return 0 if record["terminal_state"] == "COMPLETE" else 1


if __name__ == "__main__":
    sys.exit(main())
