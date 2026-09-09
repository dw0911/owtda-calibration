"""Golden tests for byte contracts (Plan §15.4)."""

import hashlib
import struct

import numpy as np
import pytest

from owtda_cal import array_hash, f64_view, file_sha256


class TestArrayHash:
    def test_golden_f64(self):
        header = (
            b'{"axis_order":"C","domain":"owtda-array-v1","dtype":">f8",'
            b'"object_kind":"test_array_v1","shape":[2]}'
        )
        data = struct.pack(">dd", 1.0, 2.0)
        expected = hashlib.sha256(header + b"\x00" + data).hexdigest()
        assert array_hash("test_array_v1", np.array([1.0, 2.0])) == expected

    def test_golden_i8(self):
        header = (
            b'{"axis_order":"C","domain":"owtda-array-v1","dtype":">i8",'
            b'"object_kind":"test_int_v1","shape":[3]}'
        )
        data = struct.pack(">3q", 1, 2, 3)
        expected = hashlib.sha256(header + b"\x00" + data).hexdigest()
        assert array_hash("test_int_v1", np.array([1, 2, 3]), dtype_code=">i8") == expected

    def test_negative_zero_normalised(self):
        assert array_hash("t", np.array([-0.0, 0.0])) == array_hash("t", np.array([0.0, 0.0]))

    def test_native_little_endian_same_result(self):
        # Contract is big-endian regardless of host endianness.
        a = np.array([1.0, -2.0], dtype=np.float64)  # native (usually LE)
        assert array_hash("t", a) == array_hash("t", a.astype(">f8"))

    def test_shape_change_changes_hash(self):
        assert array_hash("t", np.array([[1.0, 2.0], [3.0, 4.0]])) != array_hash(
            "t", np.array([1.0, 2.0, 3.0, 4.0])
        )

    def test_object_kind_change_changes_hash(self):
        assert array_hash("kind_a", np.array([1.0])) != array_hash(
            "kind_b", np.array([1.0])
        )

    def test_dtype_change_changes_hash(self):
        assert array_hash("t", np.array([1.0, 2.0])) != array_hash(
            "t", np.array([1.0, 2.0]), dtype_code=">f4"
        )

    def test_non_finite_rejected(self):
        for bad in (np.nan, np.inf, -np.inf):
            with pytest.raises(ValueError):
                array_hash("t", np.array([1.0, bad]))

    def test_bad_dtype_code_rejected(self):
        with pytest.raises(ValueError):
            array_hash("t", np.array([1.0]), dtype_code="f8")  # missing endian
        with pytest.raises(ValueError):
            array_hash("t", np.array([1.0]), dtype_code=">c8")  # bad kind


class TestF64View:
    def test_golden_one(self):
        assert f64_view(1.0) == "f64:" + struct.pack(">d", 1.0).hex()

    def test_golden_negative(self):
        assert f64_view(-2.5) == "f64:" + struct.pack(">d", -2.5).hex()

    def test_negative_zero_normalised(self):
        assert f64_view(-0.0) == "f64:0000000000000000"
        assert f64_view(-0.0) == f64_view(0.0)

    def test_accepts_int(self):
        assert f64_view(1) == f64_view(1.0)

    def test_non_finite_rejected(self):
        for bad in (float("nan"), float("inf"), float("-inf")):
            with pytest.raises(ValueError):
                f64_view(bad)


class TestFileSha256:
    def test_matches_hashlib(self, tmp_path):
        p = tmp_path / "x.bin"
        data = bytes(range(256)) * 3
        p.write_bytes(data)
        assert file_sha256(p) == hashlib.sha256(data).hexdigest()
