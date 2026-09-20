"""Scientific-row logical/wire double-schema machinery (Plan §15.4, §16.1).

A row is validated against per-row-type field roles:
  * ``value``    - key present, value not None (float fields must be finite);
  * ``null``     - key present with value None (no silent omission);
  * ``forbidden`` - key must be absent.

Float fields are the only paths where numbers are hash-encoded as
``f64:<16 hex big-endian>`` (see ``hashing.f64_view``).  ``row_payload_hash``
deletes only its own field and hashes the canonical hash-view.  The wire
encoding replaces float values with ``f64:`` strings; decoding reverses that
only for schema-flagged float paths, so an ordinary string that merely starts
with ``f64:`` is never mis-decoded.  Round-trip gate:
  * ``decode(encode(logical_row))`` reproduces all float values bit-for-bit;
  * canonical bytes of ``encode(decode(wire_row))`` equal canonical bytes of
    ``wire_row``.
"""

from __future__ import annotations

import hashlib
import math
import re
from typing import Any, Literal

from .canonical import canonical_json_bytes
from .hashing import f64_view

Role = Literal["value", "null", "forbidden"]
_F64_HEX_RE = re.compile(r"^f64:[0-9a-f]{16}$")
_HASH_FIELD = "row_payload_hash"


class RowSchemaError(ValueError):
    """Row violates its scientific-row schema."""


class RowSchema:
    """Field-role schema for one scientific row type."""

    def __init__(
        self,
        *,
        schema_name: str,
        fields: dict[str, Role],
        floats: set[str] | None = None,
    ):
        if not isinstance(schema_name, str) or not schema_name:
            raise RowSchemaError("schema_name required")
        unknown_roles = set(fields.values()) - {"value", "null", "forbidden"}
        if unknown_roles:
            raise RowSchemaError(f"unknown roles {sorted(unknown_roles)} in {schema_name}")
        self.schema_name = schema_name
        self.fields = dict(fields)
        self.floats = set(floats or ())
        bad = self.floats - {k for k, v in fields.items() if v == "value"}
        if bad:
            raise RowSchemaError(f"float fields must be 'value' roles: {sorted(bad)}")
        if _HASH_FIELD in self.floats or _HASH_FIELD in self.fields:
            raise RowSchemaError(f"{_HASH_FIELD!r} must not be schema-managed")

    def to_dict(self) -> dict:
        return {
            "schema_version": 1,
            "schema_kind": "scientific_row",
            "schema_name": self.schema_name,
            "fields": {k: v for k, v in sorted(self.fields.items())},
            "floats": sorted(self.floats),
        }

    @classmethod
    def from_dict(cls, obj: dict) -> RowSchema:
        try:
            return cls(
                schema_name=obj["schema_name"],
                fields=obj["fields"],
                floats=set(obj.get("floats", [])),
            )
        except KeyError as exc:
            raise RowSchemaError(f"schema object missing {exc.args[0]}") from exc

    # ---------------------------------------------------------------- logical

    def validate_logical(self, row: dict) -> dict:
        self._check_keys(row)
        out: dict[str, Any] = {}
        for field, role in self.fields.items():
            present = field in row
            if role == "forbidden":
                if present:
                    raise RowSchemaError(
                        f"forbidden field present in {self.schema_name}: {field!r}"
                    )
                continue
            if not present:
                raise RowSchemaError(
                    f"missing field ({role}) in {self.schema_name}: {field!r}"
                )
            value = row[field]
            if role == "null":
                if value is not None:
                    raise RowSchemaError(
                        f"field must be null in {self.schema_name}: {field!r}"
                    )
                out[field] = None
            else:
                if value is None:
                    raise RowSchemaError(
                        f"field must have a value in {self.schema_name}: {field!r}"
                    )
                if field in self.floats:
                    values = value if isinstance(value, (list, tuple)) else [value]
                    for v in values:
                        if isinstance(v, bool) or not isinstance(v, (int, float)):
                            raise RowSchemaError(f"non-numeric float field {field!r}")
                        if isinstance(v, float) and not math.isfinite(v):
                            raise RowSchemaError(f"non-finite float field {field!r}")
                out[field] = value
        return out

    def _check_keys(self, row: dict) -> None:
        allowed = set(self.fields)
        extra = set(row) - allowed
        if extra:
            raise RowSchemaError(
                f"unknown fields in {self.schema_name}: {sorted(extra)}"
            )

    def logical_hash_view(self, row: dict) -> dict:
        """Row with ``row_payload_hash`` removed and floats hex-encoded."""
        view: dict[str, Any] = {}
        for field, value in row.items():
            if field == _HASH_FIELD:
                continue
            if field in self.floats:
                view[field] = _f64_encode(value)
            else:
                view[field] = value
        return view

    def row_payload_hash(self, row: dict) -> str:
        view = self.logical_hash_view(row)
        payload = canonical_json_bytes(view)
        return hashlib.sha256(payload).hexdigest()

    def with_hash(self, row: dict, *, result_hash: str | None = None) -> dict:
        """Return a validated logical row with ``row_payload_hash`` inserted.

        ``result_hash`` (the pre-computed scientific_result_hash, when part of
        the schema row) is included in the payload before hashing, matching
        the Plan §16 ordering (insert result hash, then compute row hash).
        """
        base = self.validate_logical(row)
        if result_hash is not None:
            base["scientific_result_hash"] = result_hash
        base[_HASH_FIELD] = self.row_payload_hash(base)
        return base

    # ------------------------------------------------------------------ wire

    def encode_to_wire(self, logical_row: dict) -> dict:
        logical = self.validate_logical(logical_row)
        wire: dict[str, Any] = {}
        for field, value in logical.items():
            if field in self.floats:
                wire[field] = _f64_encode(value)
            else:
                wire[field] = value
        return self.validate_wire(wire)

    def validate_wire(self, wire_row: dict) -> dict:
        self._check_keys(wire_row)
        out: dict[str, Any] = {}
        for field, role in self.fields.items():
            present = field in wire_row
            if role == "forbidden":
                if present:
                    raise RowSchemaError(
                        f"forbidden field present in wire row {self.schema_name}: {field!r}"
                    )
                continue
            if not present:
                raise RowSchemaError(
                    f"missing wire field ({role}) in {self.schema_name}: {field!r}"
                )
            value = wire_row[field]
            if role == "null":
                if value is not None:
                    raise RowSchemaError(
                        f"wire field must be null in {self.schema_name}: {field!r}"
                    )
                out[field] = None
            elif field in self.floats:
                values = value if isinstance(value, list) else [value]
                for v in values:
                    if not isinstance(v, str) or not _F64_HEX_RE.fullmatch(v):
                        raise RowSchemaError(
                            f"wire float must match ^f64:[0-9a-f]{{16}}$ in {field!r}: {v!r}"
                        )
                out[field] = value
            else:
                if value is None:
                    raise RowSchemaError(
                        f"wire field must have a value in {self.schema_name}: {field!r}"
                    )
                out[field] = value
        return out

    def decode_from_wire(self, wire_row: dict) -> dict:
        wire = self.validate_wire(wire_row)
        logical: dict[str, Any] = {}
        for field, value in wire.items():
            if field in self.floats:
                logical[field] = _f64_decode(value)
            else:
                logical[field] = value
        return self.validate_logical(logical)

    def wire_bytes(self, wire_row: dict) -> bytes:
        return canonical_json_bytes(self.validate_wire(wire_row)) + b"\n"

    def round_trip(self, logical_row: dict) -> dict:
        """Check Plan §15.4 round-trip gate and return the logical row."""
        logical = self.validate_logical(logical_row)
        wire = self.encode_to_wire(logical)
        decoded = self.decode_from_wire(wire)
        # bit-for-bit float equality
        for f in self.floats:
            assert decoded[f] == logical[f]  # exact binary64 equality
        # wire byte round trip
        if self.wire_bytes(wire) != canonical_json_bytes(wire) + b"\n":
            raise RowSchemaError("wire canonical byte mismatch")
        return decoded


def _f64_hex_to_float(hex_text: str) -> float:
    import struct

    raw = bytes.fromhex(hex_text[len("f64:") :])
    return struct.unpack(">d", raw)[0]


def _f64_encode(value: Any) -> Any:
    """f64-encode a scalar float or a list/tuple of floats (a_r is a vector)."""
    if isinstance(value, (list, tuple)):
        return [f64_view(v) for v in value]
    return f64_view(value)


def _f64_decode(value: Any) -> Any:
    """Decode an f64 hex string or a list of them back to float(s)."""
    if isinstance(value, list):
        return [_f64_hex_to_float(v) for v in value]
    return _f64_hex_to_float(value)


__all__ = [
    "Role",
    "RowSchema",
    "RowSchemaError",
    "_F64_HEX_RE",
]
