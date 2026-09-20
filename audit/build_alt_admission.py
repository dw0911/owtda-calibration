"""Build the ALT (H1) RUN_COMPONENT_SET with parent = authoritative H0 phase seal.

``build_run_admission`` intentionally skips ALT because its
``parent_phase_seal_hash`` must be the H0 phase seal, which does not exist before
the H0 run.  This entry closes that gap now that H0 is sealed: it reuses the same
ref/binding builders and writes the ALT run component set + ``run_admission``.
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import build_run_admission as bra

from owtda_cal import freeze, registry, runs, scope
from owtda_cal.identity import H

GOV = REPO / "governance"


def _h0_phase_seal_hash() -> str:
    """Phase seal of the authoritative H0 run, used as the ALT run's parent.

    Resolution order (2026-09-20: the previous hard-coded ``F:\\BPI\\r5_h0_run\\PHASE_SEAL.json``
    only existed on the build host and broke every clone):

      1. ``$OWTDA_H0_SEAL`` — an explicit seal path, for auditing a different delivery;
      2. ``artifacts/seals/H0_NULL/PHASE_SEAL.json`` — the seal distributed with this repository
         (identical ``phase_seal_hash`` to the delivered copy).
    """
    candidates = [
        os.environ.get("OWTDA_H0_SEAL"),
        REPO / "artifacts" / "seals" / "H0_NULL" / "PHASE_SEAL.json",
    ]
    for candidate in candidates:
        if candidate and Path(candidate).is_file():
            return json.loads(Path(candidate).read_text(encoding="utf-8"))["phase_seal_hash"]
    raise SystemExit(
        "H0 PHASE_SEAL.json not found; set OWTDA_H0_SEAL to the delivery seal "
        "(artifacts/seals/H0_NULL/PHASE_SEAL.json is the in-repo copy)"
    )


def main() -> int:
    manifest = bra._load("FREEZE_MANIFEST.json")
    seed_registry = bra._load("SEED_REGISTRY_v1.0.json")
    component_registry = bra._load("COMPONENT_REGISTRY_v1.json")
    registry.validate_seed_registry(seed_registry["entries"])
    registry.validate_component_registry(component_registry["entries"])

    phase = scope.PHASE_ALT
    h0_seal = _h0_phase_seal_hash()

    rows = scope.scope_design_rows(
        project_id=manifest["project_id"],
        protocol_id=manifest["protocol_id"],
        freeze_id=manifest["freeze_id"],
        evidence_generation_id=manifest["evidence_generation_id"],
        phase=phase,
    )
    design_hash = freeze.scope_design_hash(phase, rows)
    csv_name = f"SCOPE_DESIGN_{phase}_{design_hash}.csv"
    (GOV / csv_name).write_text(freeze.scope_design_csv_text(rows), encoding="utf-8")

    binding_rows = bra._bindings(
        manifest=manifest, component_registry=component_registry, phase=phase
    )
    data, bindings_hash, row_count = runs.run_input_bindings(binding_rows)
    bindings_name = f"RUN_INPUT_BINDINGS_{bindings_hash}.jsonl"
    (GOV / bindings_name).write_bytes(data)

    config_refs = bra._config_refs(manifest)
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
        parent_phase_seal_hash=h0_seal,
        binding_authority_phase_seal_hash=None,
        run_input_bindings_hash=bindings_hash,
        run_input_bindings_row_count=row_count,
        run_input_bindings_empty_by_contract=False,
        ordered_upstream_artifact_refs=[],
        component_refs=bra._component_refs(component_registry),
        root_refs=bra._root_refs(seed_registry, phase),
        config_refs=config_refs,
        code_manifest_refs=bra._code_manifest_refs(component_registry),
        compute_git_commit=bra._git_head(),
        source_tree_hash=manifest["source_tree_hash"],
        run_config_manifest_hash=run_config_manifest_hash,
        registry_snapshot_hash=manifest["seed_registry_snapshot_hash"],
        environment_lock_hash=manifest["environment_lock_hash"],
    )
    set_hash = runs.run_component_set_hash(payload)
    set_name = f"RUN_COMPONENT_SET_{set_hash}.json"
    bra._write_json(GOV / set_name, payload)

    manifest["run_admission"][phase] = {
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
    bra._write_json(GOV / "FREEZE_MANIFEST.json", manifest)

    print(f"ALT run_component_set_hash = {set_hash}")
    print(f"ALT scope_design_hash      = {design_hash}")
    print(f"parent_phase_seal_hash     = {h0_seal}")
    print(f"ALT replicate_count        = {rows[0]['replicate_count']}")
    print(f"ALT scope_design_rows      = {len(rows)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
