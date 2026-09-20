#!/usr/bin/env python3
"""Smoke entry point (never a paper result).

Default: validate the smoke configuration and drive the pipeline-level smoke tests
(``tests/test_smoke.py``, ``tests/test_smoke_ids.py``) - fast enough for CI.

``--full``: delegate to the registered numbered smoke runner (``audit/run_smoke.py``) with
whatever extra arguments you pass; that runner reproduces the frozen blind-smoke identity
domain and is never used for paper numbers.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
SMOKE_TESTS = ("tests/test_smoke.py", "tests/test_smoke_ids.py")
REGISTERED = REPO / "audit" / "run_smoke.py"


def validate_configs() -> int:
    bad = 0
    for path in sorted((REPO / "configs").rglob("*.json")):
        try:
            json.loads(path.read_text(encoding="utf-8-sig"))
        except Exception as exc:  # noqa: BLE001 - report which config is broken
            bad += 1
            print(f"  invalid config {path.relative_to(REPO)}: {exc}")
    print(f"smoke config validation: {bad} invalid JSON file(s)")
    return 1 if bad else 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--full", action="store_true", help="run the registered numbered smoke runner")
    parser.add_argument("extra", nargs="*", help="arguments forwarded to the registered runner with --full")
    args = parser.parse_args(argv)

    if args.full:
        if not REGISTERED.exists():
            print(f"registered smoke runner missing: {REGISTERED}")
            return 1
        return subprocess.run([sys.executable, str(REGISTERED), *args.extra], cwd=REPO, check=False).returncode

    status = validate_configs()
    proc = subprocess.run(
        [sys.executable, "-m", "pytest", *SMOKE_TESTS, "-q", "--no-header", "-p", "no:cacheprovider"],
        cwd=REPO, check=False,
    )
    return status or proc.returncode


if __name__ == "__main__":
    sys.exit(main())
