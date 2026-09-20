"""Freeze-chain attacks and frozen-object consistency (Plan §16.2, §19 #1/#83)."""

import csv
import hashlib
import io
import json
from pathlib import Path

import pytest

from owtda_cal import freeze, scope
from owtda_cal.identity import H

REPO = Path(__file__).resolve().parents[1]
GOV = REPO / "governance"
MANIFEST = json.loads((GOV / "FREEZE_MANIFEST.json").read_text(encoding="utf-8"))

_ROW = {
    "phase": "NULL",
    "experiment_id": "a" * 64,
    "logical_cell_id": "b" * 64,
    "budget_membership": ["FIXED_M"],
    "feature_id": "BPI_FIXED20_H01_SIGMA005_GAMMA1_V1",
    "method_id": "M0_NAIVE_PERMUTATION_V1",
    "replicate_count": 2500,
    "expected_logical_evaluations": 2500,
    "required": True,
    "source_null_logical_cell_id": None,
    "null_model_config_hash": None,
}


def _parse_csv_row(raw: dict[str, str]) -> dict:
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


class TestSpecHashes:
    def test_spec_hash_matches_manual_H(self):
        spec = {"schema_version": 1, "config_kind": "x", "value": "1"}
        assert freeze.spec_hash("demo_spec", 1, spec) == H(
            "demo_spec", schema_version=1, spec=spec
        )

    def test_one_value_change_changes_hash(self):
        spec = {"schema_version": 1, "value": "0.8"}
        assert freeze.spec_hash("demo_spec", 1, spec) != freeze.spec_hash(
            "demo_spec", 1, {**spec, "value": "0.9"}
        )

    def test_freeze_id_sensitive_to_each_spec(self):
        base = {
            "project_id": "owtda-cal-r1",
            "protocol_id": "P",
            "protocol_content_hash": "1" * 64,
            "scope_spec_hash": "2" * 64,
            "analysis_spec_hash": "3" * 64,
            "compute_spec_hash": "4" * 64,
        }
        fid = scope.freeze_id(**base)
        for field in (
            "protocol_content_hash",
            "scope_spec_hash",
            "analysis_spec_hash",
            "compute_spec_hash",
        ):
            assert scope.freeze_id(**{**base, field: "f" * 64}) != fid

    def test_protocol_content_hash_tracks_document_bytes(self):
        doc = json.loads((GOV / "PROTOCOL_CONTENT_v1.json").read_text(encoding="utf-8"))
        base = freeze.protocol_content_hash(doc)
        tampered = json.loads(json.dumps(doc))
        tampered["documents"][0]["file_sha256"] = "0" * 64
        assert freeze.protocol_content_hash(tampered) != base


class TestScopeDesignRows:
    def test_row_order_irrelevant_for_hash_and_csv(self):
        rows = [dict(_ROW), {**_ROW, "logical_cell_id": "c" * 64}]
        assert freeze.scope_design_hash("NULL", rows) == freeze.scope_design_hash(
            "NULL", list(reversed(rows))
        )
        assert freeze.scope_design_csv_text(rows) == freeze.scope_design_csv_text(
            list(reversed(rows))
        )

    def test_csv_is_lf_terminated_with_fixed_columns(self):
        text = freeze.scope_design_csv_text([_ROW])
        assert text.endswith("\n") and "\r" not in text
        header = next(csv.reader(io.StringIO(text)))
        assert tuple(header) == freeze.SCOPE_DESIGN_COLUMNS

    def test_value_change_changes_hash(self):
        assert freeze.scope_design_hash("NULL", [_ROW]) != freeze.scope_design_hash(
            "NULL", [{**_ROW, "replicate_count": 2499}]
        )

    def test_duplicate_primary_key_rejected(self):
        with pytest.raises(ValueError):
            freeze.scope_design_hash("NULL", [dict(_ROW), dict(_ROW)])

    def test_unknown_or_missing_column_rejected(self):
        with pytest.raises(ValueError):
            freeze.scope_design_hash("NULL", [{**_ROW, "ghost": 1}])
        with pytest.raises(ValueError):
            freeze.scope_design_hash("NULL", [{k: v for k, v in _ROW.items() if k != "phase"}])


class TestFrozenObjectsOnDisk:
    def test_scope_spec_file_rehashes_to_manifest(self):
        spec = json.loads((GOV / "SCOPE_SPEC_v1.json").read_text(encoding="utf-8"))
        assert freeze.scope_spec_hash(spec) == MANIFEST["scope_spec_hash"]

    def test_protocol_content_file_rehashes_to_manifest(self):
        doc = json.loads((GOV / "PROTOCOL_CONTENT_v1.json").read_text(encoding="utf-8"))
        assert freeze.protocol_content_hash(doc) == MANIFEST["protocol_content_hash"]

    def test_analysis_spec_file_rehashes_to_manifest(self):
        doc = json.loads((GOV / "ANALYSIS_SPEC_v1.0.json").read_text(encoding="utf-8"))
        assert freeze.analysis_spec_hash(doc) == MANIFEST["analysis_spec_hash"]

    def test_compute_spec_file_rehashes_to_manifest(self):
        doc = json.loads((GOV / "COMPUTE_SPEC_v1.json").read_text(encoding="utf-8"))
        assert freeze.compute_spec_hash(doc) == MANIFEST["compute_spec_hash"]

    def test_estimand_registry_sorted_and_id_free(self):
        registry = json.loads(
            (GOV / "ESTIMAND_SPEC_REGISTRY_v1.json").read_text(encoding="utf-8")
        )
        names = [e["estimand_name"] for e in registry["entries"]]
        assert names == sorted(names) and len(set(names)) == len(names)
        assert freeze.estimand_registry_hash(registry) == MANIFEST["estimand_spec_registry_hash"]
        blob = json.dumps(registry)
        assert "analysis_id" not in blob and "estimand_id" not in blob

    def test_seven_bootstrap_plans_with_hashes(self):
        doc = json.loads((GOV / "ANALYSIS_SPEC_v1.0.json").read_text(encoding="utf-8"))
        plans = doc["bootstrap_plans"]
        assert len(plans) == 7
        assert [p["plan_name"] for p in plans] == sorted(p["plan_name"] for p in plans)
        for plan in plans:
            assert plan["plan_spec_hash"] == freeze.bootstrap_plan_spec_hash(
                plan["plan_name"], plan["spec"]
            )

    def test_scope_design_csv_rehashes_to_manifest(self):
        for phase in ("NULL", "ALT"):
            info = MANIFEST["scope_design"][phase]
            path = GOV / info["file"]
            text = path.read_text(encoding="utf-8")
            assert hashlib.sha256(text.encode("utf-8")).hexdigest() == info["csv_sha256"]
            rows = [_parse_csv_row(r) for r in csv.DictReader(io.StringIO(text))]
            assert len(rows) == info["rows"]
            assert freeze.scope_design_hash(phase, rows) == info["scope_design_hash"]

    def test_scope_design_counts(self):
        assert MANIFEST["scope_design"]["NULL"]["rows"] == 112
        assert MANIFEST["scope_design"]["ALT"]["rows"] == 32

    def test_manifest_is_cycle_free(self):
        # the manifest records hashes but is itself never hashed into any spec
        assert MANIFEST["kind"] == "freeze_manifest"
        assert "manifest_hash" not in json.dumps(MANIFEST)
        specs = [
            json.loads((GOV / n).read_text(encoding="utf-8"))
            for n in (
                "SCOPE_SPEC_v1.json",
                "PROTOCOL_CONTENT_v1.json",
                "ANALYSIS_SPEC_v1.0.json",
                "COMPUTE_SPEC_v1.json",
            )
        ]
        for spec in specs:
            assert MANIFEST["freeze_id"] not in json.dumps(spec)

    def test_frozen_document_status(self):
        for name in ("PROTOCOL_v1.0.md", "METHOD_SPEC_v1.0.md", "SAP_v1.0.md", "DATA_SPEC_v1.0.md"):
            text = (GOV / name).read_text(encoding="utf-8")
            assert "FROZEN" in text.splitlines()[0] or "FROZEN" in text.splitlines()[2]
