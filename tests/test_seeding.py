"""Golden tests for HMAC sub-seed derivation (Plan §15.1-§15.2).

The HMAC->seed_hex step is a pure standard-library contract and therefore
byte-stable across platforms. RNG *outputs* are only asserted for
same-version determinism and stream separation; NumPy versions may change
draws, which by contract requires a component-generation bump (Plan §15.2).
"""

import hashlib
import hmac
import json

import numpy as np
import pytest

from owtda_cal import (
    derive_seed_hex,
    derive_seed_int,
    make_rng,
    root_key_commitment,
)

_ROOT = "ab" * 32  # 64 lowercase hex


class TestDeriveSeedHex:
    def test_golden_bytes(self):
        payload = json.dumps(
            {
                "DGP_family": "N_AR",
                "data_generation_id": "D01",
                "domain": "owtda-seed-v1",
                "master_replicate_id": "1",
                "stream_kind": "null_initial",
            },
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
        expected = hmac.new(bytes.fromhex(_ROOT), payload, hashlib.sha256).digest()[:16].hex()
        assert (
            derive_seed_hex(
                _ROOT, "null_initial", data_generation_id="D01",
                DGP_family="N_AR", master_replicate_id="1",
            )
            == expected
        )

    def test_returns_32_hex(self):
        s = derive_seed_hex(_ROOT, "null_initial", data_generation_id="D01")
        assert len(s) == 32
        assert all(c in "0123456789abcdef" for c in s)

    def test_int_equals_hex(self):
        s = derive_seed_hex(_ROOT, "null_initial", data_generation_id="D01")
        assert derive_seed_int(_ROOT, "null_initial", data_generation_id="D01") == int(s, 16)

    def test_sensitivity(self):
        base = {"data_generation_id": "D01"}
        h_base = derive_seed_hex(_ROOT, "null_initial", **base)
        assert derive_seed_hex(_ROOT, "null_initial", data_generation_id="D02") != h_base
        assert derive_seed_hex(_ROOT, "h1_data", **base) != h_base
        assert derive_seed_hex(_ROOT.replace("a", "b", 1), "null_initial", **base) != h_base

    def test_stream_kind_separates_with_same_fields(self):
        a = derive_seed_hex(_ROOT, "null_initial", data_generation_id="D01")
        b = derive_seed_hex(_ROOT, "null_innovation", data_generation_id="D01")
        assert a != b

    def test_reserved_keys_rejected(self):
        with pytest.raises(ValueError):
            derive_seed_hex(_ROOT, "null_initial", domain="x")
        # "stream_kind" is bound positionally; injecting it again is a
        # TypeError at the call site (equally a rejection).
        with pytest.raises(TypeError):
            derive_seed_hex(_ROOT, "null_initial", stream_kind="x")

    def test_invalid_root_rejected(self):
        for bad in ("ab" * 31, "AB" * 32, "", "zz" * 32):
            with pytest.raises(ValueError):
                derive_seed_hex(bad, "null_initial", data_generation_id="D01")

    def test_invalid_stream_kind_rejected(self):
        with pytest.raises(ValueError):
            derive_seed_hex(_ROOT, "", data_generation_id="D01")
        with pytest.raises(ValueError):
            derive_seed_hex(_ROOT, "bad kind!", data_generation_id="D01")


class TestMakeRng:
    def test_type(self):
        rng = make_rng(_ROOT, "null_initial", data_generation_id="D01")
        assert isinstance(rng, np.random.Generator)
        assert isinstance(rng.bit_generator, np.random.PCG64DXSM)

    def test_same_seed_same_stream_same_version(self):
        a = make_rng(_ROOT, "null_initial", data_generation_id="D01")
        b = make_rng(_ROOT, "null_initial", data_generation_id="D01")
        assert a.random(5).tolist() == b.random(5).tolist()

    def test_different_fields_different_stream(self):
        a = make_rng(_ROOT, "null_initial", data_generation_id="D01")
        b = make_rng(_ROOT, "null_initial", data_generation_id="D02")
        assert a.random(5).tolist() != b.random(5).tolist()


class TestRootKeyCommitment:
    def test_golden(self):
        raw = bytes.fromhex(_ROOT)
        assert root_key_commitment(_ROOT) == hashlib.sha256(raw).hexdigest()
