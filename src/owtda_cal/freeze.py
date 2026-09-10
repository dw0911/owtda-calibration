"""Freeze chain and frozen-object construction (Plan §16.2, B14).

Implements the spec-hash family, the ``SCOPE_DESIGN`` row/hash contract and the
deterministic CSV emission used by the 2026-09-23 (B14) common freeze.

Ordering rules that avoid freeze/scope cycles (Plan §16.2):
  1. ``SCOPE_SPEC`` carries only scientific factors (no derived/freeze IDs);
  2. ``protocol_content_hash`` / ``scope_spec_hash`` / ``analysis_spec_hash`` /
     ``compute_spec_hash`` are computed from those specs;
  3. ``freeze_id`` is computed from those four hashes;
  4. ``SCOPE_DESIGN`` rows (which embed ``freeze_id``) and their hash are
     produced last; ``FREEZE_MANIFEST.json`` records every object but is never
     fed back into any hashed object.
"""

from __future__ import annotations

import csv
import io
from collections.abc import Iterable, Sequence
from pathlib import Path
from typing import Any

from .canonical import canonical_json_bytes
from .hashing import file_sha256
from .identity import H, file_manifest_hash

SCOPE_DESIGN_COLUMNS: tuple[str, ...] = (
    "phase",
    "experiment_id",
    "logical_cell_id",
    "budget_membership",
    "feature_id",
    "method_id",
    "replicate_count",
    "expected_logical_evaluations",
    "required",
    "source_null_logical_cell_id",
    "null_model_config_hash",
)
SCOPE_DESIGN_PRIMARY_KEY: tuple[str, ...] = (
    "phase",
    "logical_cell_id",
    "feature_id",
    "method_id",
)


def spec_hash(kind: str, schema_version: int, spec: dict[str, Any]) -> str:
    """``H(kind, schema_version=..., spec=<strict canonical object>)``."""
    return H(kind, schema_version=schema_version, spec=spec)


def protocol_content_hash(spec: dict[str, Any]) -> str:
    return spec_hash("protocol_content", spec["schema_version"], spec)


def scope_spec_hash(spec: dict[str, Any]) -> str:
    return spec_hash("scope_spec", spec["schema_version"], spec)


def analysis_spec_hash(spec: dict[str, Any]) -> str:
    return spec_hash("analysis_spec", spec["schema_version"], spec)


def compute_spec_hash(spec: dict[str, Any]) -> str:
    return spec_hash("compute_spec", spec["schema_version"], spec)


def release_spec_hash(spec: dict[str, Any]) -> str:
    return spec_hash("release_spec", spec["schema_version"], spec)


def estimand_spec_hash(estimand_name: str, spec: dict[str, Any]) -> str:
    return H("estimand_spec", estimand_name=estimand_name, spec=spec)


def bootstrap_plan_spec_hash(plan_name: str, spec: dict[str, Any]) -> str:
    return H("bootstrap_plan_spec", plan_name=plan_name, spec=spec)


def estimand_registry(estimands: dict[str, dict[str, Any]]) -> dict[str, Any]:
    """``ESTIMAND_SPEC_REGISTRY_v1`` body: name-sorted, name-unique, no IDs."""
    entries = [
        {
            "estimand_name": name,
            "spec": estimands[name],
            "estimand_spec_hash": estimand_spec_hash(name, estimands[name]),
        }
        for name in sorted(estimands)
    ]
    return {"schema_version": 1, "entries": entries}


def estimand_registry_hash(registry: dict[str, Any]) -> str:
    return spec_hash("estimand_spec_registry", registry["schema_version"], registry)


def bootstrap_plans(plans: dict[str, dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        {
            "plan_name": name,
            "spec": plans[name],
            "plan_spec_hash": bootstrap_plan_spec_hash(name, plans[name]),
        }
        for name in sorted(plans)
    ]


def _csv_value(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (list, dict)):
        return canonical_json_bytes(value).decode("utf-8")
    return str(value)


def sorted_scope_design_rows(rows: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
    """Order rows by the frozen primary key; reject duplicates/missing keys."""
    materialized = list(rows)
    for row in materialized:
        missing = set(SCOPE_DESIGN_COLUMNS) - set(row)
        extra = set(row) - set(SCOPE_DESIGN_COLUMNS)
        if missing or extra:
            raise ValueError(f"scope design row keys mismatch: missing={missing} extra={extra}")
    out = sorted(
        materialized, key=lambda r: tuple(str(r[k]) for k in SCOPE_DESIGN_PRIMARY_KEY)
    )
    keys = [tuple(str(r[k]) for k in SCOPE_DESIGN_PRIMARY_KEY) for r in out]
    if len(set(keys)) != len(keys):
        raise ValueError("duplicate SCOPE_DESIGN primary key")
    return out


def scope_design_hash(phase: str, rows: Sequence[dict[str, Any]]) -> str:
    """Row-content hash: row order and CSV line endings are irrelevant."""
    return H("scope_design", phase=phase, rows=sorted_scope_design_rows(rows))


def scope_design_csv_text(rows: Sequence[dict[str, Any]]) -> str:
    """Deterministic CSV: fixed column order, LF terminators, trailing LF."""
    buf = io.StringIO()
    writer = csv.writer(buf, lineterminator="\n")
    writer.writerow(SCOPE_DESIGN_COLUMNS)
    for row in sorted_scope_design_rows(rows):
        writer.writerow([_csv_value(row[c]) for c in SCOPE_DESIGN_COLUMNS])
    return buf.getvalue()


def file_manifest_entries(
    paths: Iterable[str | Path], *, root: str | Path
) -> list[dict[str, Any]]:
    """``{path,size,file_sha256}`` entries with POSIX relative paths."""
    base = Path(root).resolve()
    entries = []
    for path in paths:
        p = Path(path).resolve()
        entries.append(
            {
                "path": p.relative_to(base).as_posix(),
                "size": p.stat().st_size,
                "file_sha256": file_sha256(p),
            }
        )
    return entries


def source_tree_hash(entries: Sequence[dict[str, Any]]) -> str:
    return file_manifest_hash(entries)


def environment_lock_hash(entries: Sequence[dict[str, Any]]) -> str:
    return file_manifest_hash(entries)


def build_freeze_manifest(
    *,
    project_id: str,
    protocol_id: str,
    freeze_id: str,
    evidence_generation_id: str,
    protocol_content_hash_value: str,
    scope_spec_hash_value: str,
    analysis_spec_hash_value: str,
    compute_spec_hash_value: str,
    scope_design: dict[str, dict[str, Any]],
    source_tree_hash_value: str,
    environment_lock_hash_value: str,
    component_generations: dict[str, str],
) -> dict[str, Any]:
    """``FREEZE_MANIFEST`` body; never fed back into any hashed object."""
    return {
        "schema_version": 1,
        "kind": "freeze_manifest",
        "project_id": project_id,
        "protocol_id": protocol_id,
        "freeze_id": freeze_id,
        "evidence_generation_id": evidence_generation_id,
        "protocol_content_hash": protocol_content_hash_value,
        "scope_spec_hash": scope_spec_hash_value,
        "analysis_spec_hash": analysis_spec_hash_value,
        "compute_spec_hash": compute_spec_hash_value,
        "scope_design": scope_design,
        "source_tree_hash": source_tree_hash_value,
        "environment_lock_hash": environment_lock_hash_value,
        "component_generations": component_generations,
        "status": "FROZEN",
    }


__all__ = [
    "SCOPE_DESIGN_COLUMNS",
    "SCOPE_DESIGN_PRIMARY_KEY",
    "spec_hash",
    "protocol_content_hash",
    "scope_spec_hash",
    "analysis_spec_hash",
    "compute_spec_hash",
    "release_spec_hash",
    "estimand_spec_hash",
    "bootstrap_plan_spec_hash",
    "estimand_registry",
    "estimand_registry_hash",
    "bootstrap_plans",
    "sorted_scope_design_rows",
    "scope_design_hash",
    "scope_design_csv_text",
    "file_manifest_entries",
    "source_tree_hash",
    "environment_lock_hash",
    "build_freeze_manifest",
]
