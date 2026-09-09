"""Byte-level contracts (Plan §15.4): file SHA256, big-endian array hashes,
and the ``f64:`` float hash-view used by scientific row hashing.
"""

from __future__ import annotations

import hashlib
import math
import struct
from pathlib import Path

import numpy as np

from .canonical import canonical_json_bytes

_ARRAY_DOMAIN = "owtda-array-v1"
_ALLOWED_DTYPE_KINDS = frozenset("fiu")


def file_sha256(path: str | Path) -> str:
    """SHA256 of raw file bytes (64 lowercase hex)."""
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def _check_dtype_code(dtype_code: str) -> None:
    if not isinstance(dtype_code, str) or len(dtype_code) < 3:
        raise ValueError(f"invalid dtype code: {dtype_code!r}")
    if dtype_code[0] not in (">", "<"):
        raise ValueError(f"dtype code must be explicit big/little endian: {dtype_code!r}")
    kind = dtype_code[1]  # e.g. '>f8' -> 'f', '>i8' -> 'i'
    if kind not in _ALLOWED_DTYPE_KINDS:
        raise ValueError(f"unsupported dtype kind {kind!r} in {dtype_code!r}")
    try:
        np.dtype(dtype_code)
    except TypeError as exc:
        raise ValueError(f"unparseable dtype code: {dtype_code!r}") from exc


def array_bytes(object_kind: str, arr: np.ndarray, dtype_code: str = ">f8") -> bytes:
    """Canonical big-endian array bytes (header + NUL + data), Plan §15.4.

    Work is done in native order first (finite checks and ``-0.0``
    normalisation), and the big-endian conversion happens last via ``astype``,
    because NumPy ufuncs silently return native-byte-order arrays and would
    otherwise undo the endian swap.
    """
    if not isinstance(object_kind, str) or not object_kind or not object_kind.isascii():
        raise ValueError(f"object_kind must be non-empty ASCII, got {object_kind!r}")
    _check_dtype_code(dtype_code)
    native = np.dtype(dtype_code).newbyteorder("=")
    a = np.array(arr, dtype=native, order="C", copy=True)
    if native.kind == "f":
        if not np.isfinite(a).all():
            raise ValueError(f"non-finite values in array for {object_kind}")
        a = np.where(a == 0.0, 0.0, a)
    a = np.ascontiguousarray(a).astype(np.dtype(dtype_code), order="C", copy=True)
    header_obj = {
        "domain": _ARRAY_DOMAIN,
        "object_kind": object_kind,
        "dtype": dtype_code,
        "shape": [int(x) for x in a.shape],
        "axis_order": "C",
    }
    header_bytes = canonical_json_bytes(header_obj)
    return header_bytes + b"\x00" + a.tobytes(order="C")


def array_hash(object_kind: str, arr: np.ndarray, dtype_code: str = ">f8") -> str:
    """SHA256 of the canonical array bytes (64 lowercase hex)."""
    return hashlib.sha256(array_bytes(object_kind, arr, dtype_code)).hexdigest()


def f64_view(value: float) -> str:
    """Canonical float hash-view: ``f64:`` + 16 hex of 8-byte big-endian.

    ``-0.0`` is normalised to ``+0.0``; NaN/Inf are rejected (Plan §15.4).
    """
    x = float(value)
    if math.isnan(x) or math.isinf(x):
        raise ValueError(f"f64_view rejects non-finite value: {value!r}")
    if x == 0.0:
        x = 0.0
    return "f64:" + struct.pack(">d", x).hex()


__all__ = [
    "array_bytes",
    "array_hash",
    "f64_view",
    "file_sha256",
]
