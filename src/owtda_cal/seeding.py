"""HMAC sub-seed derivation (Plan §15.1-§15.2).

A sub-seed is
``HMAC-SHA256(root_key_hex, canonical_json({"domain":"owtda-seed-v1",
"stream_kind": stream_kind, **named_fields}))[:16].hex()``
(32 lowercase hex), which seeds ``numpy.random.Generator(PCG64DXSM)``.
The keys ``domain`` and ``stream_kind`` are reserved in ``named_fields``.
"""

from __future__ import annotations

import hashlib
import hmac
import re
from typing import Any

import numpy as np

from .canonical import canonical_json_bytes

_SEED_DOMAIN = "owtda-seed-v1"
_RESERVED_SEED_FIELDS = frozenset({"domain", "stream_kind"})
_STREAM_KIND_RE = re.compile(r"^[a-z][a-z0-9_]*$")


def validate_root_key_hex(root_key_hex: Any) -> str:
    if not isinstance(root_key_hex, str):
        raise ValueError("root_key_hex must be a str")
    h = root_key_hex.lower()
    if len(h) != 64 or not all(c in "0123456789abcdef" for c in h):
        raise ValueError("root_key_hex must be exactly 64 lowercase hex chars")
    if h != root_key_hex:
        raise ValueError("root_key_hex must already be lowercase hex")
    return h


def derive_seed_hex(root_key_hex: str, stream_kind: str, **named_fields: Any) -> str:
    """Return the 32-char sub-seed hex for (root_key_hex, stream_kind, fields)."""
    root = validate_root_key_hex(root_key_hex)
    if not isinstance(stream_kind, str) or not _STREAM_KIND_RE.fullmatch(stream_kind):
        raise ValueError(
            f"stream_kind must match ^[a-z][a-z0-9_]*$, got {stream_kind!r}"
        )
    bad = _RESERVED_SEED_FIELDS & named_fields.keys()
    if bad:
        raise ValueError(f"reserved seed payload key(s): {sorted(bad)}")
    payload = canonical_json_bytes(
        {"domain": _SEED_DOMAIN, "stream_kind": stream_kind, **named_fields}
    )
    digest = hmac.new(bytes.fromhex(root), payload, hashlib.sha256).digest()
    return digest[:16].hex()


def derive_seed_int(root_key_hex: str, stream_kind: str, **named_fields: Any) -> int:
    """Sub-seed as the integer seed for PCG64DXSM."""
    return int(derive_seed_hex(root_key_hex, stream_kind, **named_fields), 16)


def make_rng(root_key_hex: str, stream_kind: str, **named_fields: Any) -> np.random.Generator:
    """Instantiate ``Generator(PCG64DXSM(seed))`` for the derived sub-seed."""
    seed = derive_seed_int(root_key_hex, stream_kind, **named_fields)
    return np.random.Generator(np.random.PCG64DXSM(seed))


def root_key_commitment(root_key_hex: str) -> str:
    """SHA256 of the 32 raw bytes, as 64 lowercase hex (Plan §15.1)."""
    root = validate_root_key_hex(root_key_hex)
    return hashlib.sha256(bytes.fromhex(root)).hexdigest()


__all__ = [
    "derive_seed_hex",
    "derive_seed_int",
    "make_rng",
    "root_key_commitment",
    "validate_root_key_hex",
]
