"""Build RUN_COMPONENT_SET / RUN_INPUT_BINDINGS for smoke and NULL phases (B15a).

Generates, for SMOKE_NULL / SMOKE_ALT / NULL:

  * ``governance/SMOKE_CONFIG_v1.json`` (smoke replicate count; new file, does
    not touch any already-frozen spec hash),
  * ``governance/SCOPE_DESIGN_<phase>_<scope_design_hash>.csv`` for the smoke
    phases (the NULL/ALT designs were frozen in B14a),
  * ``governance/RUN_COMPONENT_SET_<hash>.json`` and
    ``governance/RUN_INPUT_BINDINGS_<hash>.jsonl``,
  * a ``run_admission`` block in ``FREEZE_MANIFEST.json``.

ALT is intentionally *not* generated: its ``parent_phase_seal_hash`` must be
the authoritative H0 phase seal, which does not exist before the H0 run.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "src"))

from owtda_cal import freeze, registry, runs, scope
from owtda_cal.identity import H, config_hash

GOV = REPO / "governance"
PHASES = (scope.PHASE_SMOKE_NULL, scope.PHASE_SMOKE_ALT, scope.PHASE_NULL)
SMOKE_CONFIG = {
    "schema_version": 1,
    "config_kind": "smoke_config",
    "replicates_per_cell": scope.R0_SMOKE,
    "smoke_evaluations": {"SMOKE_NULL": 3584, "SMOKE_ALT": 1024},
    "derivation": "cells x replicates: 28x128=3584, 8x128=1024 (Plan G3)",
    "reported_outputs": ["wall_time", "field_counts", "errors"],
    "forbidden_outputs": ["rejection_rate_summary", "parameter_selection"],
    "feeds_parameter_selection": False,
}


def _write_json(path: Path, obj: dict[str, Any]) -> None:
    path.write_text(
        json.dumps(obj, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def _load(name: str) -> dict[str, Any]:
    return json.loads((GOV / name).read_text(encoding="utf-8"))


def _config_refs(manifest: dict[str, Any]) -> list[dict[str, Any]]:
    # Analysis-spec identity is deliberately absent: analysis runs after sealing
    # and is not an input of a scientific run.
    return [
        runs.ref(
            role="config",
            stable_id="compute_spec",
            generation_id="C01",
            hash_value=manifest["compute_spec_hash"],
        ),
        runs.ref(
            role="config",
            stable_id="scope_spec",
            generation_id="S01",
            hash_value=manifest["scope_spec_hash"],
        ),
    ]


def _smoke_config_ref() -> dict[str, Any]:
    return runs.ref(
        role="config",
        stable_id="smoke_config",
        generation_id="S01",
        hash_value=config_hash("smoke_config", 1, SMOKE_CONFIG),
    )


def _component_refs(component_registry: dict[str, Any]) -> list[dict[str, Any]]:
    return [
        runs.ref(
            role=entry["component_kind"],
            stable_id=entry["stable_id"],
            generation_id=entry["component_generation_id"],
            hash_value=entry["component_registry_entry_hash"],
        )
        for entry in component_registry["entries"]
    ]


def _root_refs(seed_registry: dict[str, Any], phase: str) -> list[dict[str, Any]]:
    refs = []
    for entry in seed_registry["entries"]:
        if entry["phase"] != phase:
            continue
        refs.append(
            runs.ref(
                role="root",
                stable_id=entry["stream_family"],
                generation_id=entry["component_generation_id"],
                hash_value=entry["root_entry_hash"],
            )
        )
    return refs


def _code_manifest_refs(component_registry: dict[str, Any]) -> list[dict[str, Any]]:
    seen: dict[tuple[str, str], dict[str, Any]] = {}
    for entry in component_registry["entries"]:
        key = (entry["stable_id"], entry["component_generation_id"])
        if key in seen:
            continue
        seen[key] = runs.ref(
            role="code",
            stable_id=entry["stable_id"],
            generation_id=entry["component_generation_id"],
            hash_value=entry["code_file_manifest_hash"],
        )
    return list(seen.values())


def _bindings(
    *, manifest: dict[str, Any], component_registry: dict[str, Any], phase: str
) -> list[dict[str, Any]]:
    rows = [
        runs.input_binding(
            role="config",
            ref_kind="config",
            stable_id="compute_spec",
            generation_id="C01",
            hash_value=manifest["compute_spec_hash"],
            source="governance/COMPUTE_SPEC_v1.json",
        ),
        runs.input_binding(
            role="config",
            ref_kind="config",
            stable_id="scope_spec",
            generation_id="S01",
            hash_value=manifest["scope_spec_hash"],
            source="governance/SCOPE_SPEC_v1.json",
        ),
    ]
    if phase in scope.SMOKE_PHASES:
        rows.append(
            runs.input_binding(
                role="config",
                ref_kind="config",
                stable_id="smoke_config",
                generation_id="S01",
                hash_value=config_hash("smoke_config", 1, SMOKE_CONFIG),
                source="governance/SMOKE_CONFIG_v1.json",
            )
        )
    for entry in component_registry["entries"]:
        rows.append(
            runs.input_binding(
                role=entry["component_kind"],
                ref_kind=entry["component_kind"],
                stable_id=entry["stable_id"],
                generation_id=entry["component_generation_id"],
                hash_value=entry["component_registry_entry_hash"],
                source="governance/COMPONENT_REGISTRY_v1.json",
            )
        )
    return rows


def main() -> int:
    manifest = _load("FREEZE_MANIFEST.json")
    seed_registry = _load("SEED_REGISTRY_v1.0.json")
    component_registry = _load("COMPONENT_REGISTRY_v1.json")
    registry.validate_seed_registry(seed_registry["entries"])
    registry.validate_component_registry(component_registry["entries"])

    smoke_path = GOV / "SMOKE_CONFIG_v1.json"
    _write_json(smoke_path, SMOKE_CONFIG)
    smoke_hash = config_hash("smoke_config", 1, SMOKE_CONFIG)

    admission: dict[str, Any] = {}
    for phase in PHASES:
        rows = scope.scope_design_rows(
            project_id=manifest["project_id"],
            protocol_id=manifest["protocol_id"],
            freeze_id=manifest["freeze_id"],
            evidence_generation_id=manifest["evidence_generation_id"],
            phase=phase,
        )
        design_hash = freeze.scope_design_hash(phase, rows)
        csv_name = f"SCOPE_DESIGN_{phase}_{design_hash}.csv"
        (GOV / csv_name).write_text(
            freeze.scope_design_csv_text(rows), encoding="utf-8"
        )

        binding_rows = _bindings(
            manifest=manifest, component_registry=component_registry, phase=phase
        )
        data, bindings_hash, row_count = runs.run_input_bindings(binding_rows)
        bindings_name = f"RUN_INPUT_BINDINGS_{bindings_hash}.jsonl"
        (GOV / bindings_name).write_bytes(data)

        config_refs = _config_refs(manifest)
        if phase in scope.SMOKE_PHASES:
            config_refs = [*config_refs, _smoke_config_ref()]
        run_config_manifest_hash = H(
            "run_config_manifest",
            config_hashes=sorted({ref["hash"] for ref in config_refs}),
        )

        payload = runs.run_component_set(
            schema_version=1,
            project_id=manifest["project_id"],
            protocol_id=manifest["protocol_id"],
            freeze_id=manifest["freeze_id"],
            evidence_generation_id=manifest["evidence_generation_id"],
            phase=phase,
            scope_design_hash=design_hash,
            parent_phase_seal_hash=None,
            binding_authority_phase_seal_hash=None,
            run_input_bindings_hash=bindings_hash,
            run_input_bindings_row_count=row_count,
            run_input_bindings_empty_by_contract=False,
            ordered_upstream_artifact_refs=[],
            component_refs=_component_refs(component_registry),
            root_refs=_root_refs(seed_registry, phase),
            config_refs=config_refs,
            code_manifest_refs=_code_manifest_refs(component_registry),
            compute_git_commit=_git_head(),
            source_tree_hash=manifest["source_tree_hash"],
            run_config_manifest_hash=run_config_manifest_hash,
            registry_snapshot_hash=manifest["seed_registry_snapshot_hash"],
            environment_lock_hash=manifest["environment_lock_hash"],
        )
        set_hash = runs.run_component_set_hash(payload)
        set_name = f"RUN_COMPONENT_SET_{set_hash}.json"
        _write_json(GOV / set_name, payload)

        admission[phase] = {
            "run_component_set_file": set_name,
            "run_component_set_hash": set_hash,
            "run_input_bindings_file": bindings_name,
            "run_input_bindings_hash": bindings_hash,
            "run_input_bindings_row_count": row_count,
            "scope_design_file": csv_name,
            "scope_design_hash": design_hash,
            "scope_design_rows": len(rows),
            "replicate_count": rows[0]["replicate_count"],
        }

    manifest["smoke_config_hash"] = smoke_hash
    manifest["run_admission"] = admission
    manifest["run_admission_note"] = (
        "ALT run component set is deferred until the authoritative H0 phase seal "
        "exists (parent_phase_seal_hash); smoke phases carry parent=null."
    )
    _write_json(GOV / "FREEZE_MANIFEST.json", manifest)

    for phase, info in admission.items():
        print(
            f"{phase}: cells_rows={info['scope_design_rows']} reps={info['replicate_count']} "
            f"bindings={info['run_input_bindings_row_count']} "
            f"component_set={info['run_component_set_hash'][:12]}"
        )
    print(f"smoke_config_hash = {smoke_hash}")
    return 0


def _git_head() -> str:
    import subprocess

    out = subprocess.run(
        ["git", "-C", str(REPO), "rev-parse", "HEAD"],
        capture_output=True,
        text=True,
        check=False,
    )
    return out.stdout.strip()


if __name__ == "__main__":
    raise SystemExit(main())
