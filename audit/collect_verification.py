"""Collect raw test-execution evidence (audit P0-7).

Runs the full test suite and the linter **through the frozen-env launcher** so the
four thread variables are set before the interpreter starts, and emits the files
the audit prescribed::

    verification/pytest_full.log, pytest_full.xml, ruff_check.log,
    validation_commands.jsonl, validation_exit_codes.json,
    validation_environment.json

Nothing is transcribed by hand: the logs, commands, exit codes and the thread-env
probe come from the launcher, and the environment block is read from the frozen
venv at run time.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import platform
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "src"))

LAUNCHER = REPO / "scripts/frozen_env.py"
GOV = REPO / "governance"
PACKAGES = ("numpy", "scipy", "ripser", "psutil", "pytest", "ruff")


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _versions(python: str) -> dict[str, str]:
    code = (
        "import importlib.metadata as md, json;"
        f"print(json.dumps({{p: md.version(p) for p in {PACKAGES!r} if _has(p)}}, "
        "sort_keys=True))"
    ).replace("_has(p)", "True")
    out = subprocess.run(
        [python, "-c", code], capture_output=True, text=True, check=False
    )
    try:
        return json.loads(out.stdout.strip().splitlines()[-1])
    except Exception:  # noqa: BLE001 - evidence block degrades to empty mapping
        return {}


def _bashless_python_version(python: str) -> str:
    out = subprocess.run(
        [python, "-c", "import sys,platform;print(sys.version)"],
        capture_output=True, text=True, check=False,
    )
    return out.stdout.strip()


def _blas(python: str) -> str:
    code = (
        "import numpy as np, json;"
        "cfg = np.show_config(mode='dicts');"
        "b = cfg.get('Build Dependencies', {}).get('blas', {});"
        "print(b.get('name') or b.get('version') or 'unknown')"
    )
    out = subprocess.run(
        [python, "-c", code], capture_output=True, text=True, check=False
    )
    return out.stdout.strip() or "unknown"


def main() -> int:
    parser = argparse.ArgumentParser(description="collect verification evidence")
    parser.add_argument("--root", required=True)
    parser.add_argument("--python", default=str(REPO / ".venv/Scripts/python.exe"))
    args = parser.parse_args()

    ver = Path(args.root).expanduser() / "verification"
    ver.mkdir(parents=True, exist_ok=True)
    venv_python = args.python

    commands = [
        ("pytest_full", ["-m", "pytest", "-q", "--junitxml", str(ver / "pytest_full.xml")]),
        ("ruff_check", ["-m", "ruff", "check", "."]),
    ]
    for label, cmd in commands:
        completed = subprocess.run(
            [
                sys.executable, str(LAUNCHER),
                "--out-dir", str(ver),
                "--log-dir", str(ver),
                "--label", label,
                "--capture",
                "--python", venv_python,
                "--cmd", *cmd,
            ],
            cwd=str(REPO), capture_output=True, text=True, check=False,
        )
        print(completed.stdout.strip(), flush=True)

    manifest = json.loads((GOV / "FREEZE_MANIFEST.json").read_text(encoding="utf-8"))
    thread_env = json.loads((ver / "thread_env.json").read_text(encoding="utf-8"))
    environment = {
        "schema_version": 1,
        "kind": "validation_environment",
        "generated_at_utc": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "interpreter": venv_python,
        "python_version": _bashless_python_version(venv_python),
        "platform": platform.platform(),
        "machine": platform.machine(),
        "cpu_count": __import__("os").cpu_count(),
        "package_versions": _versions(venv_python),
        "blas_vendor": _blas(venv_python),
        "thread_env": thread_env,
        "git_head": subprocess.run(
            ["git", "-C", str(REPO), "rev-parse", "HEAD"],
            capture_output=True, text=True, check=False,
        ).stdout.strip(),
        "freeze_id": manifest["freeze_id"],
        "source_tree_hash": manifest["source_tree_hash"],
        "environment_lock_hash": manifest["environment_lock_hash"],
        "pyproject_sha256": _sha256(REPO / "pyproject.toml"),
        "uv_lock_sha256": _sha256(REPO / "uv.lock") if (REPO / "uv.lock").exists() else None,
    }
    (ver / "validation_environment.json").write_text(
        json.dumps(environment, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    # Collection manifest (re-audit 2026-09-12): the node IDs pytest actually
    # collected, so the verifier can derive the expected count and bind the evidence
    # to the delivered test tree instead of trusting a literal like "636" or ">500".
    collected = subprocess.run(
        [
            sys.executable, str(LAUNCHER),
            "--out-dir", str(ver), "--log-dir", str(ver),
            "--label", "pytest_collect", "--python", venv_python,
            "--cmd", "-m", "pytest", "--collect-only", "-q",
        ],
        cwd=str(REPO), capture_output=True, text=True, check=False,
    )
    node_ids = sorted(
        line.strip() for line in collected.stdout.splitlines()
        if "::" in line and not line.startswith("=")
    )
    xml_text = (ver / "pytest_full.xml").read_text(encoding="utf-8")
    collection = {
        "schema_version": 1,
        "kind": "pytest_collection_manifest",
        "generated_at_utc": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "collected_count": len(node_ids),
        "junit_testcases": xml_text.count("<testcase "),
        "test_files": sorted(p.name for p in (REPO / "tests").glob("test_*.py")),
        "node_ids": node_ids,
        "git_head": environment["git_head"],
        "source_tree_hash": environment["source_tree_hash"],
        "environment_lock_hash": environment["environment_lock_hash"],
    }
    (ver / "collection_manifest.json").write_text(
        json.dumps(collection, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(f"[verification] collected {collection['collected_count']} tests "
          f"from {len(collection['test_files'])} delivered test files", flush=True)

    codes = json.loads((ver / "validation_exit_codes.json").read_text(encoding="utf-8"))
    print(f"[verification] exit codes: {codes}")
    print(f"[verification] xml present: {(ver / 'pytest_full.xml').exists()}")
    return 0 if all(code == 0 for code in codes.values()) else 1


if __name__ == "__main__":
    raise SystemExit(main())
