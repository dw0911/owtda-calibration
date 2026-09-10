"""G4 pre-admission validator for run component sets (B15a, Plan §16.2).

For every phase recorded in ``FREEZE_MANIFEST.run_admission``:

  * the component-set file re-hashes to the hash in its file name;
  * fields equal the frozen whitelist (no downstream seal/ID/path/status/time);
  * every ref class is ordered and unique;
  * ``scope_design_hash`` matches the phase CSV bytes and row content;
  * ``run_input_bindings_hash``/row count match the bindings file bytes;
  * ``source_tree_hash`` / ``environment_lock_hash`` / ``registry_snapshot_hash``
    match the freeze manifest;
  * ``run_config_manifest_hash`` re-derives from the config refs.

Also enforces the phase rule that a formal ALT run must bind a parent phase seal.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "src"))

from owtda_cal import freeze, runs, scope
from owtda_cal.identity import H

GOV = REPO / "governance"


def _load(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


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
    import csv
    import io

    manifest = _load(GOV / "FREEZE_MANIFEST.json")
    checks: list[dict[str, Any]] = []

    def record(name: str, passed: bool, detail: str = "") -> None:
        checks.append({"check": name, "pass": bool(passed), "detail": detail})

    admission = manifest.get("run_admission")
    record("run_admission_present", isinstance(admission, dict), str(sorted(admission or {})))
    if not isinstance(admission, dict):
        return _finish(checks)

    record(
        "alt_deferred_until_h0_seal",
        scope.PHASE_ALT not in admission,
        "formal ALT component set is not generated before the H0 phase seal",
    )

    for phase, info in sorted(admission.items()):
        set_path = GOV / info["run_component_set_file"]
        if not set_path.exists():
            record(f"{phase}.component_set_file", False, "missing")
            continue
        payload = _load(set_path)
        recomputed = runs.run_component_set_hash(payload)
        record(
            f"{phase}.component_set_hash",
            recomputed == info["run_component_set_hash"],
            recomputed[:12],
        )
        record(
            f"{phase}.component_set_filename_hash",
            info["run_component_set_hash"] in info["run_component_set_file"],
        )
        record(
            f"{phase}.fields_whitelist",
            set(payload) == runs.COMPONENT_SET_FIELDS,
            str(sorted(set(payload) ^ runs.COMPONENT_SET_FIELDS)),
        )
        refs_ok = True
        for name in runs.REF_CLASSES:
            try:
                assert payload[name] == runs.sorted_refs(payload[name])
            except Exception:  # noqa: BLE001
                refs_ok = False
        record(f"{phase}.refs_sorted_unique", refs_ok)

        design_csv = GOV / info["scope_design_file"]
        if design_csv.exists():
            text = design_csv.read_text(encoding="utf-8")
            rows = [_parse_csv_row(r) for r in csv.DictReader(io.StringIO(text))]
            record(
                f"{phase}.scope_design_hash",
                freeze.scope_design_hash(phase, rows) == info["scope_design_hash"]
                and payload["scope_design_hash"] == info["scope_design_hash"],
                str(len(rows)),
            )
        else:
            record(f"{phase}.scope_design_file", False, "missing")

        bindings_path = GOV / info["run_input_bindings_file"]
        if bindings_path.exists():
            data = bindings_path.read_bytes()
            record(
                f"{phase}.bindings_hash",
                runs.content_hash(data) == info["run_input_bindings_hash"]
                == payload["run_input_bindings_hash"],
            )
            record(
                f"{phase}.bindings_row_count",
                data.count(b"\n") == info["run_input_bindings_row_count"]
                == payload["run_input_bindings_row_count"],
            )
        else:
            record(f"{phase}.bindings_file", False, "missing")

        record(
            f"{phase}.source_tree_hash",
            payload["source_tree_hash"] == manifest["source_tree_hash"],
        )
        record(
            f"{phase}.environment_lock_hash",
            payload["environment_lock_hash"] == manifest["environment_lock_hash"],
        )
        record(
            f"{phase}.registry_snapshot_hash",
            payload["registry_snapshot_hash"] == manifest["seed_registry_snapshot_hash"],
        )
        expected_config_hash = H(
            "run_config_manifest",
            config_hashes=sorted({ref["hash"] for ref in payload["config_refs"]}),
        )
        record(
            f"{phase}.run_config_manifest_hash",
            payload["run_config_manifest_hash"] == expected_config_hash,
        )
        if phase == scope.PHASE_ALT:
            record(
                f"{phase}.parent_phase_seal_bound",
                payload["parent_phase_seal_hash"] is not None,
            )
        else:
            record(f"{phase}.parent_null_ok", payload["parent_phase_seal_hash"] is None)

    return _finish(checks)


def _finish(checks: list[dict[str, Any]]) -> int:
    all_pass = all(c["pass"] for c in checks)
    out_dir = REPO / "artifacts/audit"
    out_dir.mkdir(parents=True, exist_ok=True)
    from datetime import UTC, datetime

    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    out_path = out_dir / f"run_admission_check_{stamp}.json"
    out_path.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "kind": "run_admission_check_v1",
                "generated_at_utc": stamp,
                "all_pass": all_pass,
                "checks": checks,
            },
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
    for c in checks:
        print(f"[{'PASS' if c['pass'] else 'FAIL'}] {c['check']}: {c['detail']}")
    print(f"ALL_PASS={all_pass}")
    print(f"EVIDENCE={out_path.name}")
    return 0 if all_pass else 1


if __name__ == "__main__":
    raise SystemExit(main())
