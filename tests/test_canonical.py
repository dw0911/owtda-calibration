"""Golden tests for canonical serialization contracts (Plan §15.2)."""

import hashlib
from decimal import Decimal

import pytest

from owtda_cal import (
    CanonicalizationError,
    canonical_decimal_text,
    canonical_json,
    canonical_json_bytes,
    single_object_content_hash,
)


class TestCanonicalJson:
    def test_sorted_keys_compact(self):
        assert canonical_json({"b": 2, "a": 1}) == '{"a":1,"b":2}'

    def test_nested_and_unicode_value(self):
        assert canonical_json({"msg": "中文", "z": ["x", None], "n": {"y": True}}) == (
            '{"msg":"中文","n":{"y":true},"z":["x",null]}'
        )

    def test_int_bool_null(self):
        assert canonical_json({"a": True, "b": 1, "c": None}) == '{"a":true,"b":1,"c":null}'

    def test_bare_float_rejected(self):
        with pytest.raises(CanonicalizationError):
            canonical_json({"rho": 0.8})

    def test_float_in_nested_list_rejected(self):
        with pytest.raises(CanonicalizationError):
            canonical_json({"a": [1, 2.5]})

    def test_nan_inf_rejected(self):
        for bad in (float("nan"), float("inf"), float("-inf")):
            with pytest.raises(CanonicalizationError):
                canonical_json({"x": bad})

    def test_bytes_rejected(self):
        with pytest.raises(CanonicalizationError):
            canonical_json({"x": b"bytes"})

    def test_non_ascii_key_rejected(self):
        with pytest.raises(CanonicalizationError):
            canonical_json({"k\u00e9y": 1})

    def test_nfc_key_collision_rejected(self):
        # "e\u0301" normalises to "é", colliding with the already-NFC key.
        with pytest.raises(CanonicalizationError):
            canonical_json({"é": 1, "e\u0301": 2})

    def test_string_value_nfc_normalised(self):
        # value NFD -> NFC is allowed for non-key strings.
        assert canonical_json({"a": "e\u0301"}) == '{"a":"é"}'

    def test_decimal_auto_converted_to_text(self):
        assert canonical_json({"sigma": Decimal("0.05")}) == '{"sigma":"0.05"}'

    def test_bytes_output_utf8(self):
        assert canonical_json_bytes({"a": "中文"}) == '{"a":"中文"}'.encode()


class TestCanonicalDecimal:
    @pytest.mark.parametrize(
        ("value", "expected"),
        [
            (Decimal("0.8"), "0.8"),
            (Decimal("-0"), "0"),
            (Decimal("0.00"), "0"),
            (Decimal("12.3400"), "12.34"),
            (Decimal("-12.3400"), "-12.34"),
            (Decimal("0.800"), "0.8"),
            (Decimal("1E+2"), "100"),
            (Decimal("-1.5E-1"), "-0.15"),
            (0, "0"),
            (800, "800"),
            (-5, "-5"),
        ],
    )
    def test_value_cases(self, value, expected):
        assert canonical_decimal_text(value) == expected

    @pytest.mark.parametrize(
        "text",
        ["0.8", "100", "12.34", "-0.15", "0"],
    )
    def test_canonical_text_roundtrip_accepted(self, text):
        assert canonical_decimal_text(text) == text

    @pytest.mark.parametrize(
        "text",
        ["0.80", "+0.8", "-0", "1e2", "0.8e0", "NaN", "Infinity", "", " 0.8", "0.8 "],
    )
    def test_non_canonical_text_rejected(self, text):
        with pytest.raises(CanonicalizationError):
            canonical_decimal_text(text)

    def test_float_rejected(self):
        with pytest.raises(CanonicalizationError):
            canonical_decimal_text(0.8)

    def test_bool_rejected(self):
        with pytest.raises(CanonicalizationError):
            canonical_decimal_text(True)


class TestSingleObjectHash:
    def test_hash_includes_lf(self):
        expected = hashlib.sha256(b'{"a":1}\n').hexdigest()
        assert single_object_content_hash({"a": 1}) == expected

    def test_unicode_payload(self):
        payload = b'{"a":"\\u4e2d\\u6587"}\n'  # ensure_ascii=False is on, so no escapes
        expected = hashlib.sha256(payload).hexdigest()
        # ensure_ascii=False means raw UTF-8 in the text; recompute expectation:
        expected = hashlib.sha256('{"a":"中文"}\n'.encode()).hexdigest()
        assert single_object_content_hash({"a": "中文"}) == expected

    def test_key_order_insensitive_dict(self):
        a = single_object_content_hash({"x": 1, "y": 2})
        b = single_object_content_hash({"y": 2, "x": 1})
        assert a == b

    def test_returns_64_hex(self):
        assert len(single_object_content_hash({"a": 1})) == 64
