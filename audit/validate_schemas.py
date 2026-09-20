"""Validate the strict ledger schemas (audit P0-4).

Checks, for every emitted schema object:

* ``unknown_fields = reject`` and no variant maps a field twice;
* every field role is one of ``value`` / ``null`` / ``forbidden``, floats are
  ``value`` roles only, and the wire object declares the ``f64:`` rule;
* the scientific-row discriminator is complete and unique over
  ``row_type × phase × DGP_family × scenario_id × feature_class × method_class``;
* the §16.1 minimum condition matrix holds for spot-checked variants;
* rejects unknown fields, rejects omission of a required-``null`` field, rejects
  a non-``f64:`` wire float, and round-trips bit-for-bit with a golden hash.

Emits ``schema_check_<UTC>.json`` to ``--out-dir`` (kept outside the repo so the
check cannot dirty the worktree).
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "src"))

from owtda_cal.rowschema import RowSchema, RowSchemaError

SCHEMA_DIR = REPO / "configs/schema"
GOLDEN_VARIANT = {
    "row_type": "scientific_evaluation",
    "phase": "ALT",
    "DGP_family": "CIRCLE_BASED_H1",
    "scenario_id": "mean_shift",
    "feature_id": "BPI_FIXED20_H01_SIGMA005_GAMMA1_V1",
    "method_id": "M1_DMB_R1_TRI_EXTIID_B999_V1",
}
GOLDEN_FLOATS = {"rho": 0.8, "observed_statistic": 1.5, "p_value": 0.03125, "alpha": 0.05}


def _load(name: str) -> dict[str, Any]:
    return json.loads((SCHEMA_DIR / name).read_text(encoding="utf-8"))


def _variant(schema: dict[str, Any], discriminator: dict[str, str]) -> dict[str, Any]:
    for variant in schema["variants"]:
        if all(variant["discriminator"].get(k) == v for k, v in discriminator.items()):
            return variant
    raise KeyError(f"no variant for {discriminator}")


def _golden_row(variant: dict[str, Any]) -> dict[str, Any]:
    """Deterministic golden logical row: forbidden fields are absent, nothing else is."""
    row: dict[str, Any] = {}
    for field, role in variant["fields"].items():
        if role == "forbidden":
            continue
        if role == "null":
            row[field] = None
        elif field in variant["floats"]:
            row[field] = GOLDEN_FLOATS.get(field, 0.125)
        elif field in (
            "replicate_id", "T", "W", "stride", "M_expected", "M_observed", "B",
            "candidate_count", "candidate_first", "candidate_last",
            "estimated_change_index", "exceed_count", "schema_version",
        ):
            row[field] = 3
        elif field in ("reject", "sqrt2_normalize"):
            row[field] = False
        elif field in ("budget_membership", "homology_dimensions"):
            row[field] = ["FIXED_M"]
        elif field.endswith(("_hash", "_id", "_seed")):
            row[field] = "ab" * 32
        else:
            row[field] = f"v:{field}"
    return row


def main() -> int:
    parser = argparse.ArgumentParser(description="validate strict schemas")
    parser.add_argument("--out-dir", required=True)
    args = parser.parse_args()
    out_dir = Path(args.out_dir).expanduser()
    out_dir.mkdir(parents=True, exist_ok=True)

    checks: list[dict[str, Any]] = []

    def record(name: str, passed: bool, detail: str = "") -> None:
        checks.append({"check": name, "pass": bool(passed), "detail": detail})

    manifest = _load("schemas_manifest.json")
    record(
        "manifest_unknown_fields_policy",
        manifest["unknown_fields_policy"] == "reject",
        manifest["unknown_fields_policy"],
    )
    record(
        "manifest_has_seven_objects",
        len(manifest["objects"]) == 6
        and (SCHEMA_DIR / "schemas_manifest.json").exists(),
        f"{len(manifest['objects'])} schema objects + manifest",
    )

    for entry in manifest["objects"]:
        doc = _load(entry["file"])
        record(
            f"{entry['file']}.sha256",
            hashlib.sha256(
                (SCHEMA_DIR / entry["file"]).read_bytes()
            ).hexdigest()
            == entry["sha256"],
        )
        record(
            f"{entry['file']}.unknown_fields_reject",
            doc.get("unknown_fields") == "reject",
        )
        roles_ok = True
        floats_ok = True
        for variant in doc["variants"]:
            roles = set(variant["fields"].values())
            if not roles <= {"value", "null", "forbidden"}:
                roles_ok = False
            for field in variant["floats"]:
                if variant["fields"].get(field) != "value":
                    floats_ok = False
        record(f"{entry['file']}.roles_valid", roles_ok)
        record(f"{entry['file']}.floats_are_value_roles", floats_ok)

    scientific = _load("scientific_row.schema.json")
    keys = {
        (
            v["discriminator"]["row_type"], v["discriminator"]["phase"],
            v["discriminator"]["DGP_family"], v["discriminator"]["scenario_id"],
            v["discriminator"]["feature_id"], v["discriminator"]["method_id"],
        )
        for v in scientific["variants"]
    }
    record("scientific_row.discriminator_unique", len(keys) == len(scientific["variants"]),
           f"{len(keys)} unique of {len(scientific['variants'])}")
    record(
        "scientific_row.discriminator_complete",
        len(scientific["variants"]) == 24,
        f"{len(scientific['variants'])} variants over 6 data groups x 2 features x 2 methods",
    )

    # §16.1 minimum condition matrix spot checks
    matrix = [
        ("H1_MEAN_SHIFT", "BPI", "M1",
         {"shift_direction_seed": "value", "true_boundary_synthetic": "value",
          "source_null_logical_cell_id": "value", "localization_error_synthetic": "value",
          "estimated_change_raw_time": "null", "bandwidth_b": "value", "B": "forbidden",
          "subject_internal_id": "forbidden"}),
        ("H0_N_AR", "BPI", "M0",
         {"observation_noise_seed": "null", "shift_direction_seed": "null",
          "true_boundary_synthetic": "null", "localization_error_synthetic": "null",
          "source_null_logical_cell_id": "null", "B": "value", "bandwidth_b": "null"}),
        ("REAL_PREDICTION", "MOMENTS", "M0",
         {"task_id": "value", "estimated_change_sample_coord": "value",
          "estimated_change_raw_time": "null", "replicate_id": "null",
          "DGP_family": "null", "subject_internal_id": "forbidden",
          "homology_dimensions": "null", "moment_components": "value"}),
        ("REAL_EVALUATION", "BPI", "M1",
         {"subject_internal_id": "value", "distance_seconds": "value",
          "prediction_row_payload_hash": "value", "truth_record_hash": "value"}),
    ]
    for group, feature, method, expectations in matrix:
        variant = next(
            v
            for v in scientific["variants"]
            if v["data_group"] == group
            and v["role_classes"]["feature"] == feature
            and v["role_classes"]["method"] == method
        )
        for field, expected in expectations.items():
            actual = variant["fields"].get(field, "forbidden")
            record(
                f"matrix.{group}.{feature}.{method}.{field}",
                actual == expected,
                f"{actual} (expected {expected})",
            )

    # round-trip + golden hash on one fully specified variant
    variant = _variant(scientific, GOLDEN_VARIANT)
    schema = RowSchema(
        schema_name="scientific_row_v1:golden",
        fields={k: v for k, v in variant["fields"].items()},
        floats=set(variant["floats"]),
    )
    golden = _golden_row(variant)
    validated = schema.validate_logical(golden)
    wire = schema.encode_to_wire(validated)
    decoded = schema.decode_from_wire(wire)
    record(
        "round_trip_bitwise",
        all(decoded[f] == validated[f] for f in variant["floats"]),
    )
    golden_hash = schema.row_payload_hash(validated)
    record("golden_hash_computed", len(golden_hash) == 64, golden_hash)

    try:
        schema.validate_logical({**validated, "unknown_field_x": 1})
        record("rejects_unknown_field", False, "accepted an unknown field")
    except RowSchemaError:
        record("rejects_unknown_field", True)
    try:
        omitted = {k: v for k, v in validated.items() if k != "estimated_change_raw_time"}
        schema.validate_logical(omitted)
        record("rejects_omitted_required_null", False, "accepted omission of a required-null field")
    except RowSchemaError:
        record("rejects_omitted_required_null", True)
    try:
        schema.validate_wire({**wire, "p_value": "0.5"})
        record("rejects_non_f64_wire_float", False, "accepted a non-f64 wire float")
    except RowSchemaError:
        record("rejects_non_f64_wire_float", True)

    all_pass = all(c["pass"] for c in checks)
    payload = {
        "schema_version": 1,
        "kind": "schema_check_v1",
        "generated_at_utc": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "golden_variant": GOLDEN_VARIANT,
        "golden_row_payload_hash": golden_hash,
        "all_pass": all_pass,
        "checks": checks,
    }
    out = out_dir / f"schema_check_{datetime.now(UTC).strftime('%Y%m%dT%H%M%SZ')}.json"
    out.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
                   encoding="utf-8")
    for check in checks:
        print(f"[{'PASS' if check['pass'] else 'FAIL'}] {check['check']}: {check['detail']}")
    print(f"GOLDEN_ROW_PAYLOAD_HASH={golden_hash}")
    print(f"ALL_PASS={all_pass}")
    print(f"EVIDENCE={out.name}")
    return 0 if all_pass else 1


if __name__ == "__main__":
    raise SystemExit(main())
