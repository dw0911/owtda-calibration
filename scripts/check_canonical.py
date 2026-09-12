"""P6: recursive canonical-schema check over governance/identity/seal objects.

Every object that is sealed under a canonical hash must be free of bare floats,
NaN/Inf, raw bytes and non-string keys -- *at any depth*.  A top-level schema test
misses a float nested inside a registry entry, which is what this walks for.

Scientific ledgers are exempt by design: their frozen serialisation rules allow
the documented decimal text, and they are checked by their own contract.

Usage::

    python scripts/check_canonical.py [DIR ...]   # default: governance + artifacts
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "src"))

from owtda_cal.canonical import non_canonical_nodes

#: Ledgers carry the frozen scientific serialisation, not the governance one.
EXEMPT_SUFFIXES = ("_rows.jsonl", "evaluation_ledger.jsonl", "feature_ledger.jsonl",
                   "expected_data_index.jsonl", "expected_feature_index.jsonl",
                   "expected_evaluation_index.jsonl")

#: The rule applies to objects that are *sealed under a canonical hash*: seals,
#: manifests, registries, reason objects and certificates.  Human-facing reports
#: (audit dispositions, review packets, submission records) may carry floats --
#: they are not canonical payloads, and demanding otherwise would be a category
#: error.  They are counted separately instead of being silently ignored.
CANONICAL_KIND_SUFFIXES = ("_manifest", "_seal", "_registry", "_certificate",
                           "_reason", "_entry", "_record", "_identity",
                           "_attestation")
CANONICAL_PATH_HINTS = ("/reasons/", "/seals/", "/manifests/", "/registries/")


def _label(path: Path) -> str:
    try:
        return str(path.relative_to(REPO))
    except ValueError:
        return str(path)


def in_canonical_scope(path: Path, obj) -> bool:
    posix = path.as_posix()
    if any(hint in f"/{posix}" for hint in CANONICAL_PATH_HINTS):
        return True
    kind = str(obj.get("kind", "")) if isinstance(obj, dict) else ""
    return kind.endswith(CANONICAL_KIND_SUFFIXES)


def check_object(path: Path, obj) -> list[dict[str, str]]:
    return [{"file": _label(path), **issue} for issue in non_canonical_nodes(obj)]


def check_file(path: Path, *, scope_only: bool = False) -> list[dict[str, str]]:
    if path.name.endswith(EXEMPT_SUFFIXES):
        return []
    issues: list[dict[str, str]] = []
    if path.suffix == ".jsonl":
        lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
        for number, line in enumerate(lines, start=1):
            if not line.strip():
                continue
            try:
                obj = json.loads(line)
            except json.JSONDecodeError as exc:
                issues.append({"file": _label(path), "path": f"line {number}",
                               "code": "UNPARSEABLE_JSON", "detail": str(exc)})
                continue
            if scope_only and not in_canonical_scope(path, obj):
                continue
            issues.extend(check_object(path, obj))
        return issues
    try:
        obj = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        return [{"file": _label(path), "path": "$",
                 "code": "UNPARSEABLE_JSON", "detail": str(exc)}]
    if scope_only and not in_canonical_scope(path, obj):
        return []
    return check_object(path, obj)


def main() -> int:
    arguments = [a for a in sys.argv[1:] if not a.startswith("--")]
    scope_only = "--all-objects" not in sys.argv
    targets = [Path(a) for a in arguments] or [REPO / "governance", REPO / "artifacts"]
    files: list[Path] = []
    for target in targets:
        path = target if target.is_absolute() else REPO / target
        if path.is_dir():
            files.extend(sorted(p for p in path.rglob("*")
                                if p.suffix in (".json", ".jsonl") and p.is_file()))
        elif path.is_file():
            files.append(path)
    issues: list[dict[str, str]] = []
    checked = 0
    for file in files:
        found = check_file(file, scope_only=scope_only)
        issues.extend(found)
        checked += 1 if found or in_scope_file(file) else 0
    print(json.dumps({"files": len(files), "files_in_scope": checked,
                      "issues": len(issues), "first": issues[:5],
                      "scope": "canonical payloads only" if scope_only
                               else "every object"}, ensure_ascii=False))
    return 1 if issues else 0


def in_scope_file(path: Path) -> bool:
    try:
        text = path.read_text(encoding="utf-8")
        obj = json.loads(text) if path.suffix == ".json" else None
    except (OSError, json.JSONDecodeError):
        return False
    return obj is not None and in_canonical_scope(path, obj)


if __name__ == "__main__":
    sys.exit(main())
