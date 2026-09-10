"""Launch any command inside the frozen compute environment (P0-2).

The frozen contract requires the four BLAS/thread variables to be ``"1"`` *before
the interpreter starts* (``COMPUTE_SPEC.thread_env``); setting them from inside
Python is too late for OpenBLAS.  This launcher therefore

  1. sets ``OMP_NUM_THREADS``/``OPENBLAS_NUM_THREADS``/``MKL_NUM_THREADS``/
     ``NUMEXPR_NUM_THREADS`` to ``"1"`` in the child environment,
  2. runs a probe child that reports the variables *before* and *after* importing
     numpy (proof they were inherited, not patched at runtime),
  3. runs the target command, optionally capturing stdout/stderr to files,
  4. appends one machine-readable record per invocation to ``commands.jsonl``
     and writes ``thread_env.json`` / exit codes, so the audit evidence is
     produced by construction rather than by transcription.

Usage::

    python scripts/frozen_env.py --out-dir <dir> --label wstar_h0_w8 \
        --cmd .venv/Scripts/python.exe -- -u audit/run_worker_sweep.py ...
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
from datetime import UTC, datetime
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
THREAD_ENV = {
    "OMP_NUM_THREADS": "1",
    "OPENBLAS_NUM_THREADS": "1",
    "MKL_NUM_THREADS": "1",
    "NUMEXPR_NUM_THREADS": "1",
}
PROBE = (
    "import json,os,sys;"
    "before={k:os.environ.get(k,'unset') for k in %r};"
    "import numpy;"
    "after={k:os.environ.get(k,'unset') for k in %r};"
    "print(json.dumps({'argv0':sys.executable,'before_import':before,"
    "'after_import':after,'numpy':numpy.__version__}))" % (tuple(THREAD_ENV), tuple(THREAD_ENV))
)


def _child_env() -> dict[str, str]:
    return {**os.environ, **THREAD_ENV}


def _run(cmd: list[str], *, env: dict[str, str], capture: Path | None) -> tuple[int, float, str]:
    start = time.perf_counter()
    if capture is None:
        code = subprocess.run(cmd, env=env, cwd=str(REPO)).returncode
        return code, time.perf_counter() - start, ""
    capture.parent.mkdir(parents=True, exist_ok=True)
    with capture.open("wb") as fh:
        proc = subprocess.run(cmd, env=env, cwd=str(REPO), stdout=fh, stderr=subprocess.STDOUT)
    return proc.returncode, time.perf_counter() - start, str(capture)


def main() -> int:
    parser = argparse.ArgumentParser(description="run a command in the frozen env")
    parser.add_argument("--out-dir", required=True)
    parser.add_argument("--label", required=True)
    parser.add_argument("--python", default=sys.executable)
    parser.add_argument("--capture", action="store_true", help="capture stdout+stderr to a log")
    parser.add_argument("--cmd", nargs=argparse.REMAINDER, required=True)
    args = parser.parse_args()

    out_dir = Path(args.out_dir).expanduser()
    out_dir.mkdir(parents=True, exist_ok=True)
    cmd = [c for c in args.cmd if c != "--"]

    env = _child_env()
    probe_out = out_dir / "thread_env.json"
    probe = subprocess.run(
        [args.python, "-c", PROBE], env=env, cwd=str(REPO), capture_output=True, text=True
    )
    observed = json.loads(probe.stdout.strip().splitlines()[-1]) if probe.stdout else {}
    declared = {k: "1" for k in THREAD_ENV}
    inherited_before = observed.get("before_import", {})
    inherited_after = observed.get("after_import", {})
    thread_env = {
        "schema_version": 1,
        "kind": "thread_env_evidence",
        "generated_at_utc": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "launcher": "scripts/frozen_env.py",
        "declared": declared,
        "observed_before_import": inherited_before,
        "observed_after_import": inherited_after,
        "interpreter": observed.get("argv0"),
        "set_before_interpreter_start": inherited_before == declared,
        "stable_across_numpy_import": inherited_before == inherited_after,
        "passed": inherited_before == declared and inherited_before == inherited_after,
    }
    probe_out.write_text(
        json.dumps(thread_env, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )

    log_path = out_dir / f"{args.label}.log" if args.capture else None
    code, seconds, log = _run([args.python, *cmd], env=env, capture=log_path)

    record = {
        "label": args.label,
        "utc": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "python": args.python,
        "argv": cmd,
        "thread_env": declared,
        "cwd": str(REPO),
        "exit_code": code,
        "wall_seconds": round(seconds, 3),
        "log": log or None,
    }
    with (out_dir / "commands.jsonl").open("a", encoding="utf-8", newline="\n") as fh:
        fh.write(json.dumps(record, ensure_ascii=False, sort_keys=True) + "\n")
    codes_path = out_dir / "validation_exit_codes.json"
    codes = (
        json.loads(codes_path.read_text(encoding="utf-8")) if codes_path.exists() else {}
    )
    codes[args.label] = code
    codes_path.write_text(
        json.dumps(codes, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )

    print(f"[frozen_env] {args.label} exit={code} wall={seconds:.1f}s thread_env_ok={thread_env['passed']}")
    return code


if __name__ == "__main__":
    raise SystemExit(main())
