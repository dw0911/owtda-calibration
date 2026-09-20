"""The formal expected plan: 82,800 / 165,600 / 331,200 concrete identities.

Task pack §9 step 5.  The plan is *the* join target for every later claim, so it
is built from the frozen enumeration and nothing else:

* cells come from ``scope.h0_null_cells()`` / ``scope.h1_alt_cells()`` and are
  keyed exactly the way ``scope.scope_design_rows`` keys them (same
  ``DGP_family``/``scenario_id``/``rho``/``W``/``stride``/``T``/``M``), so the plan
  and the design rows cannot drift apart;
* per cell, the data model hash comes from ``dgp`` (``n_ar_data_model_spec`` /
  ``n_circle_data_model_spec`` / ``h1_data_model_spec``);
* ``cells.master_replicate_id`` -> ``base_series_id`` -> ``physical_cell_id`` ->
  ``data_unit_id`` -> ``formal_ids.feature_sufficient_id`` -> ``evaluation_id``;
* rows are emitted in the frozen index order (sorted by logical key) and hashed
  with ``indexes.index_content_hash`` over the emitted bytes.

``replicate_override`` exists for TEST-scale self-checks only; the formal call
uses the frozen ``R0_H0`` / ``R0_H1`` counts and the override is recorded in the
report so a reduced plan can never be mistaken for the formal one.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from . import cells, dgp, formal_ids, indexes, scope
from .canonical import canonical_json_bytes

DEFAULT_PHASES = (scope.PHASE_NULL, scope.PHASE_ALT)


def _data_model_hash(*, phase: str, family: str, scenario: str, rho: str) -> str:
    if phase == scope.PHASE_NULL:
        spec = (dgp.n_ar_data_model_spec(rho) if family == scope.DGP_FAMILY_N_AR
                else dgp.n_circle_data_model_spec(rho))
    else:
        spec = dgp.h1_data_model_spec(scenario, rho)
    return dgp.data_model_config_hash(spec)


def plan_cells(
    *, project_id: str, protocol_id: str, freeze_id: str,
    evidence_generation_id: str, phase: str,
) -> dict[str, dict[str, Any]]:
    """``logical_cell_id -> {DGP_family, scenario_id, rho, W, stride, T, M, hash}``.

    The cell id is computed with the same arguments ``scope.scope_design_rows``
    uses, so the two enumerations are keyed identically by construction.
    """
    ctx = scope._Ctx(project_id=project_id, protocol_id=protocol_id,
                     freeze_id=freeze_id, evidence_generation_id=evidence_generation_id)
    out: dict[str, dict[str, Any]] = {}
    if phase == scope.PHASE_NULL:
        for cell in scope.h0_null_cells():
            key = ctx.cell_id(phase=phase, DGP_family=cell.family,
                              scenario_id=scope.SCENARIO_NULL, rho=cell.rho, W=cell.W,
                              stride=cell.stride, T=cell.T, M=cell.M)
            out[key] = {
                "DGP_family": cell.family, "scenario_id": scope.SCENARIO_NULL,
                "rho": cell.rho, "W": cell.W, "stride": cell.stride, "T": cell.T,
                "M": cell.M,
                "data_model_config_hash": _data_model_hash(
                    phase=phase, family=cell.family, scenario=scope.SCENARIO_NULL,
                    rho=cell.rho),
            }
    elif phase == scope.PHASE_ALT:
        for cell in scope.h1_alt_cells():
            key = ctx.cell_id(phase=phase, DGP_family=scope.H1_FAMILY,
                              scenario_id=cell.scenario, rho=cell.rho, W=cell.W,
                              stride=cell.stride, T=cell.T, M=cell.M)
            out[key] = {
                "DGP_family": scope.H1_FAMILY, "scenario_id": cell.scenario,
                "rho": cell.rho, "W": cell.W, "stride": cell.stride, "T": cell.T,
                "M": cell.M,
                "data_model_config_hash": _data_model_hash(
                    phase=phase, family=scope.H1_FAMILY, scenario=cell.scenario,
                    rho=cell.rho),
            }
    else:
        raise ValueError(f"plan_cells supports {scope.PHASE_NULL}/{scope.PHASE_ALT}")
    return out


def _feature_hash(feature_id: str) -> str:
    from .features import bpi_feature_spec, feature_config_hash, moments_feature_spec

    if feature_id == scope.FEATURE_IDS[0]:
        return feature_config_hash(bpi_feature_spec())
    return feature_config_hash(moments_feature_spec())


def _method_hash(method_id: str) -> str:
    from .components import method_config_hash

    return method_config_hash(method_id)


def build_phase_plan(
    *,
    out_dir: str | Path,
    project_id: str,
    protocol_id: str,
    freeze_id: str,
    evidence_generation_id: str,
    phase: str,
    replicate_override: int | None = None,
    data_generation_id: str | None = None,
) -> dict[str, Any]:
    """Expand one phase into the three expected index files; return counts/hashes."""
    if replicate_override is not None and (type(replicate_override) is not int or replicate_override < 1):
        raise ValueError("replicate_override must be a positive TEST integer")
    if not isinstance(data_generation_id, str) or not data_generation_id:
        if replicate_override is None:
            raise ValueError("FORMAL_DATA_GENERATION_REQUIRED: pass frozen data_generation_id")
        data_generation_id = "TEST-DATA"
    if replicate_override is None and (not isinstance(freeze_id, str) or len(freeze_id) != 64 or set(freeze_id) == {"0"}):
        raise ValueError("FORMAL_FREEZE_ID_REQUIRED: placeholder identity is forbidden")
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    directory = out / phase
    directory.mkdir(parents=True, exist_ok=False)

    cell_map = plan_cells(project_id=project_id, protocol_id=protocol_id,
                          freeze_id=freeze_id,
                          evidence_generation_id=evidence_generation_id, phase=phase)
    design_rows = sorted(
        scope.scope_design_rows(project_id=project_id, protocol_id=protocol_id,
                                freeze_id=freeze_id,
                                evidence_generation_id=evidence_generation_id,
                                phase=phase),
        key=lambda r: (r["logical_cell_id"], r["feature_id"], r["method_id"]),
    )
    cell_ids = sorted({row["logical_cell_id"] for row in design_rows})
    unknown = [cell_id for cell_id in cell_ids if cell_id not in cell_map]
    if unknown:
        raise ValueError(
            f"{len(unknown)} design-row cell ids are not produced by plan_cells; the "
            "plan and the scope enumeration have drifted apart"
        )

    # one pass per cell: every replicate of a cell shares its geometry, so the
    # per-replicate ids are derived once and reused by feature/evaluation rows
    data_rows: list[dict[str, Any]] = []
    feature_rows: list[dict[str, Any]] = []
    evaluation_rows: list[dict[str, Any]] = []
    per_cell: dict[str, dict[str, int]] = {}
    for cell_id in cell_ids:
        params = cell_map[cell_id]
        count = replicate_override or design_rows[0]["replicate_count"]
        count = next(row["replicate_count"] for row in design_rows
                     if row["logical_cell_id"] == cell_id)
        if replicate_override:
            count = min(count, replicate_override)
        physical = cells.physical_cell_id(
            protocol_id=protocol_id, freeze_id=freeze_id,
            evidence_generation_id=evidence_generation_id, phase=phase,
            rho=params["rho"], W=params["W"], stride=params["stride"], T=params["T"],
            M=params["M"], data_model_config_hash=params["data_model_config_hash"])
        per_cell[cell_id] = {"replicates": count}
        for replicate_id in range(1, count + 1):
            master = cells.master_replicate_id(
                project_id=project_id, protocol_id=protocol_id, freeze_id=freeze_id,
                evidence_generation_id=evidence_generation_id, phase=phase,
                DGP_family=params["DGP_family"], replicate_id=replicate_id)
            base_series = cells.base_series_id(
                master_replicate_id=master, data_generation_id=data_generation_id,
                DGP_family=params["DGP_family"], rho=params["rho"],
                raw_length=params["T"],
                data_model_config_hash=params["data_model_config_hash"])
            unit = cells.data_unit_id(
                base_series_id=base_series, physical_cell_id=physical,
                data_generation_id=data_generation_id)
            logical_data = scope.logical_data_key(
                logical_cell_id=cell_id, master_replicate_id=master)
            data_rows.append({"logical_data_key": logical_data, "data_unit_id": unit})
            for feature_id in scope.FEATURE_IDS:
                feature_hash = _feature_hash(feature_id)
                logical_feature = scope.logical_feature_key(
                    logical_data_key=logical_data, feature_id=feature_id)
                feature_sufficient = formal_ids.feature_sufficient_id(
                    data_generation_id=data_generation_id, data_unit_id=unit,
                    feature_id=feature_id, feature_config_hash=feature_hash)
                feature_rows.append({
                    "logical_data_key": logical_data,
                    "logical_feature_key": logical_feature,
                    "data_unit_id": unit,
                    "feature_sufficient_id": feature_sufficient,
                })
                for method_id in scope.METHOD_IDS:
                    evaluation_rows.append({
                        "logical_data_key": logical_data,
                        "logical_feature_key": logical_feature,
                        "logical_evaluation_key": scope.logical_evaluation_key(
                            logical_data_key=logical_data, feature_id=feature_id,
                            method_id=method_id),
                        "data_unit_id": unit,
                        "feature_sufficient_id": feature_sufficient,
                        "evaluation_id": formal_ids.evaluation_id(
                            data_generation_id=data_generation_id, data_unit_id=unit,
                            feature_sufficient_id=feature_sufficient,
                            method_id=method_id,
                            method_config_hash=_method_hash(method_id)),
                    })

    # Canonical index ordering must be identical to the runtime predeclaration
    # contract.  Sorting every row type by logical_data_key is set-equivalent
    # but byte/hash-incompatible for feature/evaluation indexes.
    data_rows = indexes.expected_data_index_rows(data_rows)
    feature_rows = indexes.expected_feature_index_rows(feature_rows)
    evaluation_rows = indexes.expected_evaluation_index_rows(evaluation_rows)
    indexes.validate_index_consistency(data_rows, feature_rows, evaluation_rows)
    written = {}
    for name, rows in (("expected_data_index.jsonl", data_rows),
                       ("expected_feature_index.jsonl", feature_rows),
                       ("expected_evaluation_index.jsonl", evaluation_rows)):
        blob = b"".join(canonical_json_bytes(r) + b"\n" for r in rows)
        (directory / name).write_bytes(blob)
        written[name] = {"rows": len(rows), "bytes": len(blob),
                         "sha256": hashlib.sha256(blob).hexdigest()}
    return {
        "phase": phase,
        "cells": len(cell_ids),
        "replicate_override": replicate_override,
        "per_cell_replicates": per_cell,
        "counts": {
            "data_units": len(data_rows),
            "feature_rows": len(feature_rows),
            "evaluation_rows": len(evaluation_rows),
        },
        "index_hashes": {
            "data": indexes.index_content_hash(data_rows),
            "feature": indexes.index_content_hash(feature_rows),
            "evaluation": indexes.index_content_hash(evaluation_rows),
        },
        "files": written,
    }


def build_expected_plan(
    *,
    out_dir: str | Path,
    project_id: str = "owtda-cal-r1",
    protocol_id: str = "OWTDA-CAL-R1-PROTOCOL-v1.0",
    freeze_id: str = "0" * 64,
    evidence_generation_id: str = "G01",
    phases: tuple[str, ...] = DEFAULT_PHASES,
    replicate_override: int | None = None,
    data_generation_id: str | None = None,
) -> dict[str, Any]:
    """Build every requested phase and write the plan summary."""
    out = Path(out_dir)
    phases_report = {
        phase: build_phase_plan(
            out_dir=out, project_id=project_id, protocol_id=protocol_id,
            freeze_id=freeze_id, evidence_generation_id=evidence_generation_id,
            phase=phase, replicate_override=replicate_override,
            data_generation_id=data_generation_id)
        for phase in phases
    }
    totals = {
        key: sum(report["counts"][key] for report in phases_report.values())
        for key in ("data_units", "feature_rows", "evaluation_rows")
    }
    summary = {
        "schema_version": 1,
        "kind": "formal_expected_plan",
        "project_id": project_id, "protocol_id": protocol_id,
        "freeze_id": freeze_id, "evidence_generation_id": evidence_generation_id,
        "data_generation_id": data_generation_id if data_generation_id is not None else "TEST-DATA",
        "replicate_override": replicate_override,
        "formal_scale": replicate_override is None,
        "phases": phases_report,
        "totals": totals,
    }
    (out / "PLAN_SUMMARY.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8")
    return summary


__all__ = ["build_expected_plan", "build_phase_plan", "plan_cells"]
