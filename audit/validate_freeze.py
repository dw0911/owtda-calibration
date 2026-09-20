"""G0 freeze-chain validator (Plan §16.2, §19 #1/#83).

Re-derives every frozen hash from bytes on disk and checks the whole chain is
closed and acyclic:

  1. SCOPE_SPEC / PROTOCOL_CONTENT / ESTIMAND_REGISTRY / ANALYSIS_SPEC /
     COMPUTE_SPEC files re-hash to the FREEZE_MANIFEST values;
  2. ``freeze_id`` re-derives from the four spec hashes;
  3. SCOPE_DESIGN CSVs match their recorded byte hash, row count and row hash;
  4. frozen governance documents still hash to the recorded file manifest;
  5. no hashed spec embeds the ``freeze_id`` (cycle check).

Writes ``artifacts/audit/freeze_check_<UTC>.json`` and exits non-zero on any
failure.
"""

from __future__ import annotations

import csv
import hashlib
import io
import json
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parent))  # audit/ -> builders

import build_freeze

from owtda_cal import components, disposition, freeze, registry, scope
from owtda_cal.hashing import file_sha256

GOV = REPO / "governance"


def _load(name: str) -> dict[str, Any]:
    return json.loads((GOV / name).read_text(encoding="utf-8"))


def _parse_csv_row(raw: dict[str, str]) -> dict[str, Any]:
    return {
        "phase": raw["phase"],
        "experiment_id": raw["experiment_id"],
        "logical_cell_id": raw["logical_cell_id"],
        "budget_membership": json.loads(raw["budget_membership"]) if raw["budget_membership"] else [],
        "feature_id": raw["feature_id"],
        "method_id": raw["method_id"],
        "replicate_count": int(raw["replicate_count"]),
        "expected_logical_evaluations": int(raw["expected_logical_evaluations"]),
        "required": raw["required"] == "true",
        "source_null_logical_cell_id": raw["source_null_logical_cell_id"] or None,
        "null_model_config_hash": raw["null_model_config_hash"] or None,
    }


def main() -> int:
    checks: list[dict[str, Any]] = []
    manifest = _load("FREEZE_MANIFEST.json")

    def record(name: str, passed: bool, detail: str = "") -> None:
        checks.append({"check": name, "pass": bool(passed), "detail": detail})

    scope_spec = _load("SCOPE_SPEC_v1.json")
    protocol = _load("PROTOCOL_CONTENT_v1.json")
    estimand_registry = _load("ESTIMAND_SPEC_REGISTRY_v1.json")
    analysis = _load("ANALYSIS_SPEC_v1.0.json")
    compute = _load("COMPUTE_SPEC_v1.json")

    s_hash = freeze.scope_spec_hash(scope_spec)
    p_hash = freeze.protocol_content_hash(protocol)
    e_hash = freeze.estimand_registry_hash(estimand_registry)
    a_hash = freeze.analysis_spec_hash(analysis)
    c_hash = freeze.compute_spec_hash(compute)

    record("scope_spec_hash", s_hash == manifest["scope_spec_hash"], s_hash)
    record("protocol_content_hash", p_hash == manifest["protocol_content_hash"], p_hash)
    record("estimand_registry_hash", e_hash == manifest["estimand_spec_registry_hash"], e_hash)
    record("analysis_spec_hash", a_hash == manifest["analysis_spec_hash"], a_hash)
    record("compute_spec_hash", c_hash == manifest["compute_spec_hash"], c_hash)

    fid = scope.freeze_id(
        project_id=manifest["project_id"],
        protocol_id=manifest["protocol_id"],
        protocol_content_hash=p_hash,
        scope_spec_hash=s_hash,
        analysis_spec_hash=a_hash,
        compute_spec_hash=c_hash,
    )
    record("freeze_id", fid == manifest["freeze_id"], fid)

    analysis_binds_registry = analysis.get("estimand_spec_registry_hash") == e_hash
    record("analysis_binds_estimand_registry", analysis_binds_registry, e_hash)

    for phase in ("NULL", "ALT"):
        info = manifest["scope_design"][phase]
        path = GOV / info["file"]
        if not path.exists():
            record(f"scope_design[{phase}].file", False, "missing")
            continue
        text = path.read_text(encoding="utf-8")
        byte_ok = hashlib.sha256(text.encode("utf-8")).hexdigest() == info["csv_sha256"]
        rows = [_parse_csv_row(r) for r in csv.DictReader(io.StringIO(text))]
        hash_ok = freeze.scope_design_hash(phase, rows) == info["scope_design_hash"]
        record(f"scope_design[{phase}].bytes", byte_ok, info["file"])
        record(f"scope_design[{phase}].rows", len(rows) == info["rows"], str(len(rows)))
        record(f"scope_design[{phase}].row_hash", hash_ok, info["scope_design_hash"])

    docs_ok = True
    for entry in protocol["documents"]:
        path = REPO / entry["path"]
        if not path.exists() or file_sha256(path) != entry["file_sha256"]:
            docs_ok = False
            record("frozen_document", False, entry["path"])
    record("frozen_documents", docs_ok, f"{len(protocol['documents'])} entries")

    specs_blob = json.dumps([scope_spec, protocol, estimand_registry, analysis, compute])
    record("cycle_free", manifest["freeze_id"] not in specs_blob, "freeze_id absent from specs")

    src_entries = freeze.file_manifest_entries(
        [REPO / e["path"] for e in manifest["source_tree_manifest"]], root=REPO
    )
    src_hash = freeze.source_tree_hash(src_entries)
    record(
        "source_tree_hash",
        src_hash == manifest["source_tree_hash"],
        f"recorded={manifest['source_tree_hash'][:12]} now={src_hash[:12]}",
    )

    env_entries = freeze.file_manifest_entries(
        [REPO / e["path"] for e in manifest["environment_lock_manifest"]], root=REPO
    )
    env_hash = freeze.environment_lock_hash(env_entries)
    record(
        "environment_lock_hash",
        env_hash == manifest["environment_lock_hash"],
        env_hash,
    )

    seed_reg = _load("SEED_REGISTRY_v1.0.json")
    comp_reg = _load("COMPONENT_REGISTRY_v1.json")
    secret_reg = _load("SECRET_COMMITMENT_REGISTRY_v1.0.json")
    registry.validate_seed_registry(seed_reg["entries"])
    registry.validate_component_registry(comp_reg["entries"])
    registry.validate_secret_registry(secret_reg["entries"])
    # Derived, never hard-coded: the frozen seed families are the single source of
    # truth, so adding/removing one cannot leave a stale expectation behind.
    record("seed_registry_entries", len(seed_reg["entries"]) == len(build_freeze.SEED_ROOT_FAMILIES), str(len(seed_reg["entries"])))
    # The registry must describe exactly the component set the code defines, so a
    # newly added component (B15c: SYNTHETIC_CIRCLE_BASED_H1_V1) cannot leave a
    # stale registry behind.
    defined_components = sorted(
        (d["component_kind"], d["stable_id"])
        for d in components.component_definitions()
    )
    registered_components = sorted(
        (e["component_kind"], e["stable_id"]) for e in comp_reg["entries"]
    )
    record(
        "component_registry_entries",
        registered_components == defined_components,
        f"{len(registered_components)} vs {len(defined_components)}",
    )
    seed_keys = [
        tuple(
            e[k]
            for k in (
                "project_id",
                "protocol_id",
                "freeze_id",
                "evidence_generation_id",
                "phase",
                "stream_family",
                "component_generation_id",
            )
        )
        for e in seed_reg["entries"]
    ]
    record("seed_registry_sorted", seed_keys == sorted(seed_keys))
    comp_keys = [
        tuple(
            e[k]
            for k in (
                "project_id",
                "protocol_id",
                "freeze_id",
                "evidence_generation_id",
                "component_kind",
                "stable_id",
                "component_generation_id",
            )
        )
        for e in comp_reg["entries"]
    ]
    record("component_registry_sorted", comp_keys == sorted(comp_keys))
    record(
        "seed_registry_snapshot_hash",
        registry.registry_snapshot_hash([e["root_entry_hash"] for e in seed_reg["entries"]])
        == manifest["seed_registry_snapshot_hash"],
    )
    record(
        "component_registry_snapshot_hash",
        registry.registry_snapshot_hash(
            [e["component_registry_entry_hash"] for e in comp_reg["entries"]]
        )
        == manifest["component_registry_snapshot_hash"],
    )
    record(
        "secret_registry_snapshot_hash",
        registry.registry_snapshot_hash([]) == manifest["secret_registry_snapshot_hash"],
    )
    isolated = {"real_task", "real_task_id_salt"}
    record(
        "real_root_keys_isolated",
        all(
            e["root_key_hex"] is None and e["secret_ref"] is not None
            for e in seed_reg["entries"]
            if e["stream_family"] in isolated
        ),
    )

    disp_info = disposition.validate_chain(GOV / "REAL_DISPOSITION.jsonl")
    recorded = manifest["real_disposition"]
    record(
        "real_disposition_tip",
        disp_info["tip_hash"] == recorded["tip_hash"]
        and disp_info["latest_status"] == recorded["latest_status"],
        disp_info["latest_status"],
    )
    reason_path = GOV / f"REAL_DISPOSITION_REASON_{disp_info['reason_object_hash']}.json"
    reason = json.loads(reason_path.read_text(encoding="utf-8"))
    record(
        "real_disposition_reason_object",
        disposition.reason_object_hash(reason) == disp_info["reason_object_hash"]
        and reason["gate"]["pass"] is False,
        disp_info["reason_object_hash"],
    )
    record("real_truth_sealed", disp_info["truth_unsealed"] is False)

    for name in ("PROTOCOL_v1.0.md", "METHOD_SPEC_v1.0.md", "SAP_v1.0.md", "DATA_SPEC_v1.0.md"):
        head = (GOV / name).read_text(encoding="utf-8").splitlines()[:4]
        record(f"status_frozen[{name}]", any("FROZEN" in line for line in head))

    all_pass = all(c["pass"] for c in checks)
    evidence = {
        "schema_version": 1,
        "kind": "freeze_check_v1",
        "generated_at_utc": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "freeze_id": manifest["freeze_id"],
        "all_pass": all_pass,
        "checks": checks,
    }
    out_dir = REPO / "artifacts/audit"
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / f"freeze_check_{datetime.now(UTC).strftime('%Y%m%dT%H%M%SZ')}.json"
    out_path.write_text(
        json.dumps(evidence, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )

    for c in checks:
        print(f"[{'PASS' if c['pass'] else 'FAIL'}] {c['check']}: {c['detail']}")
    print(f"ALL_PASS={all_pass}")
    print(f"EVIDENCE={out_path.name} sha256={file_sha256(out_path)}")
    return 0 if all_pass else 1


if __name__ == "__main__":
    raise SystemExit(main())
