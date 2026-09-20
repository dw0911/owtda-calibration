"""Build the real environment lock (audit P0-2).

Writes ``environment/`` inside the repo so that ``environment_lock_hash`` can
cover it, plus a genuine rebuild test in a fresh directory outside the repo:

    pyproject.toml, uv.lock, environment_manifest.json, pip_freeze_all.txt,
    python_VV.txt, numpy_show_config.txt, tool_versions.json, thread_env.json,
    environment_rebuild_test.json

The rebuild test copies only ``pyproject.toml`` + ``uv.lock`` into a fresh
directory and runs ``uv sync --frozen`` there, so the lock is proven to
reproduce the interpreter environment without the repo's own state.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import platform
import shutil
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "src"))

LAUNCHER = REPO / "scripts/frozen_env.py"
DEFAULT_OUT = REPO / "environment"
PACKAGES = ("numpy", "scipy", "ripser", "psutil", "pytest", "ruff")


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _run(cmd: list[str], *, cwd: Path | None = None, env: dict | None = None) -> subprocess.CompletedProcess:
    # utf-8 with replacement: the console code page (GBK) must never break evidence
    # collection, and undecodable bytes must be visible rather than fatal.
    return subprocess.run(
        cmd, cwd=str(cwd or REPO), env=env, capture_output=True, check=False,
        encoding="utf-8", errors="replace",
    )


def _text(cmd: list[str], *, env: dict | None = None) -> str:
    """Run a command and return its stdout, failing loudly on any error.

    Audit A07: the previous version returned stdout only and ignored the exit code,
    so a command that failed on this host (``python -m pip freeze`` is unavailable
    in a uv-managed venv) silently produced a **zero-byte** evidence file.  A
    non-zero exit now raises with the command, its exit code and stderr; stderr is
    appended to successful output too, so warnings cannot hide either.
    """
    done = _run(cmd, env=env)
    if done.returncode != 0:
        raise RuntimeError(
            f"evidence command failed (exit {done.returncode}): {' '.join(cmd)}\n"
            f"stderr: {done.stderr.strip()}"
        )
    stderr = done.stderr.strip()
    return done.stdout + (f"\n[stderr]\n{stderr}\n" if stderr else "")


def _capture_evidence(path: Path, candidates: list[list[str]]) -> dict[str, Any]:
    """Write ``path`` from the first candidate command that really produces output.

    Audit A07: the evidence must name the command that produced it, and a command
    that fails may never be recorded as an empty (unrecognisable) file.
    """
    attempts: list[dict[str, Any]] = []
    for cmd in candidates:
        done = _run(cmd)
        attempts.append({
            "command": cmd,
            "exit_code": done.returncode,
            "stdout_bytes": len(done.stdout or ""),
            "stderr": (done.stderr or "").strip()[:2000],
        })
        if done.returncode == 0 and (done.stdout or "").strip():
            path.write_text(done.stdout, encoding="utf-8")
            return {
                "file": path.name,
                "command": cmd,
                "exit_code": 0,
                "attempts": attempts,
            }
    raise RuntimeError(f"no candidate command produced {path.name}: {attempts}")


def main() -> int:
    parser = argparse.ArgumentParser(description="build environment lock evidence")
    parser.add_argument("--out", default=str(DEFAULT_OUT))
    parser.add_argument("--python", default=str(REPO / ".venv/Scripts/python.exe"))
    parser.add_argument("--rebuild-dir", default=str(REPO.parent / "_audit_r1/env_rebuild"))
    args = parser.parse_args()

    out = Path(args.out).expanduser()
    out.mkdir(parents=True, exist_ok=True)
    python = args.python
    # A07: `uv` is a host executable, not a module of the venv interpreter, so it
    # is resolved explicitly and its absence is fatal (the rebuild test needs it).
    uv_bin = shutil.which("uv")
    if uv_bin is None:
        raise SystemExit("uv executable not found on PATH; the environment rebuild test requires it")
    if not Path(python).exists():
        raise SystemExit(f"frozen interpreter missing: {python}")

    shutil.copyfile(REPO / "pyproject.toml", out / "pyproject.toml")
    shutil.copyfile(REPO / "uv.lock", out / "uv.lock")

    candidates: list[list[str]] = []
    if uv_bin:
        candidates.append([uv_bin, "pip", "freeze", "--python", python])
    candidates.append([python, "-m", "pip", "freeze"])
    candidates.append([sys.executable, "-m", "pip", "freeze"])
    if uv_bin:
        candidates.append(
            [uv_bin, "pip", "list", "--format", "freeze", "--python", python]
        )
    freeze_info = _capture_evidence(out / "pip_freeze_all.txt", candidates)
    (out / "python_VV.txt").write_text(
        _text([python, "-VV"]) + "\n" + "sys.executable=" + python + "\n", encoding="utf-8"
    )
    (out / "numpy_show_config.txt").write_text(
        _text([python, "-c", "import numpy;numpy.show_config()"]), encoding="utf-8"
    )

    # thread env: captured by the launcher probe (set before interpreter start)
    probe_dir = out / "_probe"
    probe_dir.mkdir(parents=True, exist_ok=True)
    _run(
        [
            sys.executable, str(LAUNCHER), "--out-dir", str(probe_dir),
            "--label", "env_probe", "--python", python, "--cmd", "-c", "pass",
        ]
    )
    shutil.copyfile(probe_dir / "thread_env.json", out / "thread_env.json")
    shutil.rmtree(probe_dir, ignore_errors=True)

    versions = json.loads(
        _text(
            [
                python, "-c",
                f"import importlib.metadata as md, json; print(json.dumps({{p: md.version(p) for p in {PACKAGES!r}}}, sort_keys=True))",
            ]
        ).strip()
    )
    # A07: uv lives on PATH, not as a module of the venv interpreter; collecting
    # its version through `sys.executable -m uv` silently produced empty evidence.
    uv_version = _text([uv_bin, "--version"]).strip() if uv_bin else "UNAVAILABLE"
    blas = json.loads(
        _text(
            [
                python, "-c",
                "import numpy as np, json; cfg = np.show_config(mode='dicts'); "
                "b = cfg.get('Build Dependencies', {}).get('blas', {}); "
                "print(json.dumps({'blas_name': b.get('name'), 'blas_version': b.get('version')}))",
            ]
        ).strip()
    )
    tool_versions = {
        "schema_version": 1,
        "kind": "tool_versions",
        "generated_at_utc": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "interpreter": python,
        "python": platform.python_version(),
        "packages": versions,
        "uv": uv_version,
        "os": platform.platform(),
        "machine": platform.machine(),
        "cpu_count": os.cpu_count(),
        "blas": blas,
    }
    (out / "tool_versions.json").write_text(
        json.dumps(tool_versions, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )

    rebuild_dir = Path(args.rebuild_dir).expanduser()
    shutil.rmtree(rebuild_dir, ignore_errors=True)
    rebuild_dir.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(REPO / "pyproject.toml", rebuild_dir / "pyproject.toml")
    shutil.copyfile(REPO / "uv.lock", rebuild_dir / "uv.lock")
    # pyproject declares readme = "README.md"; the metadata build needs it.
    if (REPO / "README.md").exists():
        shutil.copyfile(REPO / "README.md", rebuild_dir / "README.md")
    os.makedirs(rebuild_dir / "src" / "owtda_cal", exist_ok=True)
    (rebuild_dir / "src" / "owtda_cal" / "__init__.py").write_text(
        "VERSION = '0.1.0'\n", encoding="utf-8"
    )
    sync = _run([uv_bin, "sync", "--frozen"], cwd=rebuild_dir)
    installed = _text([uv_bin, "pip", "list", "--python", str(rebuild_dir / ".venv/Scripts/python.exe")])
    rebuild = {
        "schema_version": 1,
        "kind": "environment_rebuild_test",
        "generated_at_utc": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "method": "copy pyproject.toml + uv.lock into a fresh directory and run `uv sync --frozen`",
        "directory": str(rebuild_dir),
        "command": "uv sync --frozen",
        "exit_code": sync.returncode,
        "passed": sync.returncode == 0,
        "stdout_tail": (sync.stdout or "")[-4000:],
        "stderr_tail": (sync.stderr or "")[-2000:],
        "installed_packages": installed,
    }
    (out / "environment_rebuild_test.json").write_text(
        json.dumps(rebuild, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )

    # Audit A07: the manifest must describe the *other* evidence files only.  The
    # previous version enumerated the directory before rewriting itself, so the
    # stale manifest was hashed into its own replacement and the recorded
    # size/hash could never match the delivered file.  It is removed first and
    # excluded explicitly; the freeze manifest seals the final bytes from outside.
    manifest_path = out / "environment_manifest.json"
    manifest_path.unlink(missing_ok=True)
    excluded = {"environment_manifest.json"}
    files = sorted(
        p for p in out.iterdir()
        if p.is_file() and p.name not in excluded and not p.name.endswith(".tmp")
    )
    manifest = {
        "schema_version": 1,
        "kind": "environment_manifest",
        "generated_at_utc": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "self_excluded": sorted(excluded),
        "excluded_patterns": ["*.tmp", "_probe/"],
        "sealed_by": "FREEZE_MANIFEST.environment_lock_manifest",
        "freeze_evidence": freeze_info,
        "lock_covers": [
            "pyproject.toml",
            "uv.lock",
            "environment/tool_versions.json",
            "environment/thread_env.json",
            "environment/pip_freeze_all.txt",
            "environment/numpy_show_config.txt",
            "environment/python_VV.txt",
            "environment/environment_rebuild_test.json",
        ],
        "thread_env_rule": "four BLAS/thread variables set to \"1\" by scripts/frozen_env.py before the interpreter starts",
        "files": [
            {"path": p.name, "size": p.stat().st_size, "sha256": _sha256(p)} for p in files
        ],
        "rebuild_test_passed": rebuild["passed"],
    }
    (out / "environment_manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(f"[environment] files={len(files)} rebuild_passed={rebuild['passed']}")
    print(f"[environment] python={tool_versions['python']} packages={versions}")
    return 0 if rebuild["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
