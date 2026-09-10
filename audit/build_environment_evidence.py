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
    return _run(cmd, env=env).stdout


def main() -> int:
    parser = argparse.ArgumentParser(description="build environment lock evidence")
    parser.add_argument("--out", default=str(DEFAULT_OUT))
    parser.add_argument("--python", default=str(REPO / ".venv/Scripts/python.exe"))
    parser.add_argument("--rebuild-dir", default=str(REPO.parent / "_audit_r1/env_rebuild"))
    args = parser.parse_args()

    out = Path(args.out).expanduser()
    out.mkdir(parents=True, exist_ok=True)
    python = args.python
    if not Path(python).exists():
        raise SystemExit(f"frozen interpreter missing: {python}")

    shutil.copyfile(REPO / "pyproject.toml", out / "pyproject.toml")
    shutil.copyfile(REPO / "uv.lock", out / "uv.lock")

    (out / "pip_freeze_all.txt").write_text(
        _text([python, "-m", "pip", "freeze"]), encoding="utf-8"
    )
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
    uv_version = _text([sys.executable, "-m", "uv", "--version"]).strip()
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
    sync = _run([sys.executable, "-m", "uv", "sync", "--frozen"], cwd=rebuild_dir)
    installed = _text([sys.executable, "-m", "uv", "pip", "list", "--python", str(rebuild_dir / ".venv/Scripts/python.exe")])
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

    files = sorted(p for p in out.iterdir() if p.is_file())
    manifest = {
        "schema_version": 1,
        "kind": "environment_manifest",
        "generated_at_utc": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
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
