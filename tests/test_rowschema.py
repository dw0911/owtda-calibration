"""Tests for logical/wire double-schema machinery (Plan §15.4, §16.1)."""

import json
from pathlib import Path

import pytest

from owtda_cal.rowschema import RowSchema, RowSchemaError

_SCHEMA_PATH = Path(__file__).resolve().parents[1] / "configs/schema/demo_synthetic_eval_v1.schema.json"


@pytest.fixture(scope="module")
def schema() -> RowSchema:
    obj = json.loads(_SCHEMA_PATH.read_text(encoding="utf-8"))
    return RowSchema.from_dict(obj)


def _row(**over) -> dict:
    base = {
        "evaluation_id": "a" * 64,
        "phase": "NULL",
        "scenario_id": "h0",
        "DGP_family": "N_AR",
        "rho": 0.8,
        "feature_id": "BPI_FIXED20_H01_SIGMA005_GAMMA1_V1",
        "method_id": "M0_NAIVE_PERM_B999_V1",
        "data_unit_id": "b" * 64,
        "observed_statistic": 3.141592653589793,
        "p_value": 0.0,
        "exceed_count": 0,
        "reject": True,
        "source_null_logical_cell_id": None,
    }
    base.update(over)
    return base


class TestValidate:
    def test_valid_row(self, schema):
        out = schema.validate_logical(_row())
        assert out["rho"] == 0.8

    def test_unknown_field_rejected(self, schema):
        with pytest.raises(RowSchemaError):
            schema.validate_logical(_row(extra_field=1))

    def test_forbidden_field_rejected(self, schema):
        with pytest.raises(RowSchemaError):
            schema.validate_logical(_row(subject_internal_id="subject101"))
        with pytest.raises(RowSchemaError):
            schema.validate_logical(_row(activity_A=1))

    def test_required_value_missing_rejected(self, schema):
        r = _row()
        del r["observed_statistic"]
        with pytest.raises(RowSchemaError):
            schema.validate_logical(r)

    def test_required_null_must_be_present(self, schema):
        r = _row()
        del r["source_null_logical_cell_id"]
        with pytest.raises(RowSchemaError):
            schema.validate_logical(r)
        # None allowed, non-None rejected
        with pytest.raises(RowSchemaError):
            schema.validate_logical(_row(source_null_logical_cell_id="c" * 64))

    def test_non_finite_float_rejected(self, schema):
        with pytest.raises(RowSchemaError):
            schema.validate_logical(_row(observed_statistic=float("nan")))
        with pytest.raises(RowSchemaError):
            schema.validate_logical(_row(observed_statistic=float("inf")))


class TestRowHash:
    def test_hash_excludes_own_field(self, schema):
        r = schema.with_hash(_row())
        assert "row_payload_hash" in r
        h1 = r["row_payload_hash"]
        # Recompute independent of the hash field being present
        view = schema.logical_hash_view(r)
        import hashlib

        from owtda_cal.canonical import canonical_json_bytes

        assert hashlib.sha256(canonical_json_bytes(view)).hexdigest() == h1

    def test_hash_is_64_hex_and_stable(self, schema):
        r1 = schema.with_hash(_row())
        r2 = schema.with_hash(_row())
        assert len(r1["row_payload_hash"]) == 64
        assert r1["row_payload_hash"] == r2["row_payload_hash"]
        diff = _row(observed_statistic=2.0)
        assert schema.with_hash(diff)["row_payload_hash"] != r1["row_payload_hash"]

    def test_hash_view_f64(self, schema):
        view = schema.logical_hash_view(_row(rho=0.5))
        assert view["rho"] == "f64:" + __import__("struct").pack(">d", 0.5).hex()


class TestWireRoundTrip:
    def test_encode_decode_bitwise(self, schema):
        row = _row(rho=0.8, observed_statistic=0.1 + 0.2, p_value=1 / 3)
        wire = schema.encode_to_wire(row)
        # floats hex-encoded
        assert wire["rho"].startswith("f64:")
        decoded = schema.decode_from_wire(wire)
        assert decoded["rho"] == row["rho"]
        assert decoded["observed_statistic"] == row["observed_statistic"]
        assert decoded["p_value"] == row["p_value"]

    def test_wire_canonical_bytes_roundtrip(self, schema):
        row = _row()
        wire = schema.encode_to_wire(row)
        wire_canon = schema.wire_bytes(wire)
        from owtda_cal.canonical import canonical_json_bytes

        assert wire_canon == canonical_json_bytes(wire) + b"\n"

    def test_regular_f64_string_not_misdecoded(self, schema):
        # add a value-role non-float string that looks like an f64 token
        row = _row()
        row["feature_id"] = "f64:0000000000000000"
        wire = schema.encode_to_wire(row)
        decoded = schema.decode_from_wire(wire)
        assert decoded["feature_id"] == "f64:0000000000000000"
        assert isinstance(decoded["feature_id"], str)

    def test_bad_wire_float_rejected(self, schema):
        row = _row()
        wire = schema.encode_to_wire(row)
        wire["p_value"] = "not-a-float"
        with pytest.raises(RowSchemaError):
            schema.validate_wire(wire)
        wire["p_value"] = "f64:XYZ"
        with pytest.raises(RowSchemaError):
            schema.validate_wire(wire)


class TestSchemaConfig:
    def test_load_from_json(self, schema):
        assert schema.schema_name == "demo_synthetic_eval_v1"
        assert "source_null_logical_cell_id" in schema.fields
        assert set(schema.floats) == {"observed_statistic", "p_value", "rho"}

    def test_bad_role_rejected(self):
        with pytest.raises(RowSchemaError):
            RowSchema(schema_name="bad", fields={"a": "maybe"})

    def test_float_field_must_be_value_role(self):
        with pytest.raises(RowSchemaError):
            RowSchema(schema_name="bad", fields={"a": "null"}, floats={"a"})
