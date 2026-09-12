"""The three manifests of task pack §7.

The audit's complaint was precise: the *scientific* identity covered the science
modules, but the last change to the runner (``audit/run_smoke_s03.py``, the
allocation wiring) landed after the recorded test run and nothing bound it to the
evidence.  A folder name is not a dependency either -- ``scripts/frozen_env.py``
sits in ``scripts/`` and still decides the thread environment.

So there are three, with different jobs:

``SCIENTIFIC_MANIFEST``
    the science/configuration identity, computed with the existing inclusion
    rule (which already covered ``shardio``).
``EXECUTION_MANIFEST``
    what actually ran: entry points, launcher, scheduling/sampling/commit/analysis
    IO **and their import closure**, plus command, environment variables,
    interpreter and the executable policy hash.
``VALIDATION_MANIFEST``
    the verifier: test sources, configuration, collection nodeids, the approved
    skip set, the JUnit identity set, stdout/stderr digests and exit code.
"""

from __future__ import annotations

import ast
import hashlib
import json
import os
import sys
from collections.abc import Iterable, Sequence
from pathlib import Path
from typing import Any

from .oracles import check_junit


def sha256_file(path: str | Path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def hash_files(paths: Iterable[str | Path], *, root: str | Path | None = None) -> dict[str, str]:
    """``relative path -> sha256`` for the files that exist."""
    base = Path(root) if root is not None else None
    out: dict[str, str] = {}
    for path in paths:
        target = Path(path)
        if not target.is_file():
            continue
        key = str(target.relative_to(base)) if base else str(target)
        out[key.replace("\\", "/")] = sha256_file(target)
    return dict(sorted(out.items()))


def _module_to_path(module: str, roots: Sequence[Path]) -> Path | None:
    parts = module.split(".")
    for root in roots:
        candidate = root.joinpath(*parts).with_suffix(".py")
        if candidate.is_file():
            return candidate
        package = root.joinpath(*parts, "__init__.py")
        if package.is_file():
            return package
    return None


def _resolve_imports(source: str, current: Path, roots: Sequence[Path],
                     prefix: str) -> list[Path]:
    """Every in-tree file this source imports, absolute and relative forms."""
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return []
    candidates: list[Path] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                # resolution is by *roots*, not by name: a sibling module such as
                # ``resource_sampler`` is a real dependency even though it is not
                # inside the science package
                resolved = _module_to_path(alias.name, roots)
                if resolved is not None:
                    candidates.append(resolved)
        elif isinstance(node, ast.ImportFrom):
            names = [alias.name for alias in node.names]
            if node.level:  # ``from . import x`` / ``from .mod import x``
                base = current.parent
                if node.module:
                    for part in node.module.split("."):
                        base = base / part
                    for name in names:
                        candidates.extend(
                            [base / f"{name}.py", base / name / "__init__.py"])
                    candidates.extend([base.with_suffix(".py"),
                                       base / "__init__.py"])
                else:
                    for name in names:
                        candidates.extend(
                            [current.parent / f"{name}.py",
                             current.parent / name / "__init__.py"])
            elif node.module:
                resolved = _module_to_path(node.module, roots)
                if resolved is not None:
                    candidates.append(resolved)
                for name in names:  # ``from package import submodule``
                    sub = _module_to_path(f"{node.module}.{name}", roots)
                    if sub is not None:
                        candidates.append(sub)
    return candidates


def import_closure(
    entries: Iterable[str | Path],
    *,
    roots: Sequence[str | Path] | None = None,
    prefix: str = "owtda_cal",
) -> list[str]:
    """Files reachable from ``entries`` through imports inside ``prefix``.

    A file is included because it is *imported*, not because it lives in a
    particular directory -- which is exactly the distinction the audit drew.
    """
    search_roots = [Path(r) for r in roots] if roots else [Path.cwd()]
    seen: set[Path] = set()
    queue = [Path(entry) for entry in entries]
    while queue:
        current = queue.pop()
        if not current.is_file() or current in seen:
            continue
        seen.add(current)
        text = current.read_text(encoding="utf-8", errors="replace")
        for resolved in _resolve_imports(text, current, search_roots, prefix):
            if resolved.is_file() and resolved not in seen:
                queue.append(resolved)
    return sorted(str(path).replace("\\", "/") for path in seen)


def scientific_manifest(
    *, files: Iterable[str | Path], root: str | Path | None = None,
    config_files: Iterable[str | Path] = (),
) -> dict[str, Any]:
    """The science/configuration identity (computed with the existing rule)."""
    hashes = hash_files(files, root=root)
    configs = hash_files(config_files, root=root)
    return {
        "schema_version": 1,
        "kind": "SCIENTIFIC_MANIFEST",
        "files": hashes,
        "config_files": configs,
        "manifest_hash": _manifest_hash("SCIENTIFIC_MANIFEST", hashes, configs),
    }


def execution_manifest(
    *,
    entries: Iterable[str | Path],
    command: Sequence[str],
    environment: dict[str, str],
    policy_sha256: str,
    roots: Sequence[str | Path] | None = None,
    root: str | Path | None = None,
    prefix: str = "owtda_cal",
) -> dict[str, Any]:
    """What ran, including the import closure of every entry point."""
    closure = import_closure(entries, roots=roots or [Path.cwd()], prefix=prefix)
    files = hash_files(closure, root=root)
    body = {
        "schema_version": 1,
        "kind": "EXECUTION_MANIFEST",
        "entries": sorted(str(e).replace("\\", "/") for e in entries),
        "import_closure": closure,
        "files": files,
        "command": list(command),
        "environment": dict(sorted(environment.items())),
        "interpreter": {"executable": sys.executable, "version": sys.version.split()[0],
                        "platform": sys.platform},
        "policy_sha256": policy_sha256,
    }
    body["manifest_hash"] = _manifest_hash(
        "EXECUTION_MANIFEST", files, {"policy": policy_sha256})
    return body


def validation_manifest(
    *,
    test_files: Iterable[str | Path],
    config_files: Iterable[str | Path] = (),
    collected_nodeids: Sequence[dict[str, str]] | None = None,
    junit_xml: str | bytes | None = None,
    approved_skips: Iterable[str] = (),
    exit_code: int | None = None,
    stdout: bytes = b"",
    stderr: bytes = b"",
    root: str | Path | None = None,
) -> dict[str, Any]:
    """The verifier's own identity, including what it did *not* run."""
    files = hash_files(test_files, root=root)
    configs = hash_files(config_files, root=root)
    junit: dict[str, Any] = {}
    if junit_xml is not None:
        expected = None
        if collected_nodeids is not None:
            expected = [f"{item['classname']}::{item['name']}"
                        for item in collected_nodeids]
        junit = check_junit(junit_xml, expected_identities=expected,
                            approved_skips=approved_skips, where="junit")
        junit = {"identities": sorted(junit["identities"]),
                 "skipped": sorted(junit["skipped"]),
                 "issues": junit["issues"]}
    body = {
        "schema_version": 1,
        "kind": "VALIDATION_MANIFEST",
        "test_files": files,
        "config_files": configs,
        "collected_nodeids": list(collected_nodeids or []),
        "approved_skips": sorted(approved_skips),
        "junit": junit,
        "exit_code": exit_code,
        "stdout_sha256": hashlib.sha256(stdout).hexdigest(),
        "stderr_sha256": hashlib.sha256(stderr).hexdigest(),
        "unapproved_skips": [issue["where"] for issue in junit.get("issues", [])
                             if issue["code"] == "JUNIT_UNAPPROVED_SKIP"],
    }
    body["manifest_hash"] = _manifest_hash("VALIDATION_MANIFEST", files, configs)
    return body


def _manifest_hash(kind: str, *parts: Any) -> str:
    payload = json.dumps([kind, *parts], sort_keys=True, ensure_ascii=False).encode()
    return hashlib.sha256(payload).hexdigest()


def environment_subset(names: Iterable[str]) -> dict[str, str]:
    """The recorded environment variables (only those that were asked for)."""
    return {name: os.environ[name] for name in sorted(names) if name in os.environ}


__all__ = [
    "environment_subset",
    "execution_manifest",
    "hash_files",
    "import_closure",
    "scientific_manifest",
    "sha256_file",
    "validation_manifest",
]
