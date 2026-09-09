"""Tests for synthetic DGP generators (Plan §7, §15.2-§15.4).

Innovation arrays are rho-free; the same replicate shares base innovations
across rho levels, while raw series and raw hashes differ.  Only the
HMAC->seed step is byte-golden; PCG outputs are asserted via recomputation and
invariants (numpy-version sensitive by contract).
"""

import numpy as np
import pytest

from owtda_cal import hashing
from owtda_cal.cells import L_LATENT, L_MASTER
from owtda_cal.dgp import (
    DGP_FAMILY_N_AR,
    DGP_FAMILY_N_CIRCLE,
    data_model_config_hash,
    delay_embedding_3,
    generate_null_master,
    n_ar_data_model_spec,
    n_circle_data_model_spec,
)

_ROOT = "ab" * 32
DG = "D01"


def _master(family, rho, mr="1"):
    return generate_null_master(
        family=family, rho=rho, root_key_hex=_ROOT,
        data_generation_id=DG, master_replicate_id=mr,
    )


class TestDataModelConfig:
    def test_n_ar_spec_and_hash(self):
        spec = n_ar_data_model_spec("0.8")
        assert spec["rho"] == "0.8"
        assert spec["generator_version"] == "N_AR_V1"
        assert data_model_config_hash(spec) == data_model_config_hash(
            n_ar_data_model_spec("0.8")
        )
        assert data_model_config_hash(spec) != data_model_config_hash(
            n_ar_data_model_spec("0")
        )

    def test_rho_float_rejected_in_spec(self):
        with pytest.raises(ValueError):
            n_ar_data_model_spec(0.8)

    def test_n_circle_spec(self):
        spec = n_circle_data_model_spec("0")
        assert spec["rotation"] == "I2"
        assert spec["observation_noise"] == "iid_N2_0_I2_times_0.08"


class TestNArMaster:
    def test_shapes_and_innovation_hash(self):
        m = _master(DGP_FAMILY_N_AR, "0")
        assert m.family == DGP_FAMILY_N_AR
        assert m.innovations.shape == (L_LATENT,)
        assert m.initial_value == float(np.asarray(m.initial_value))
        assert m.noise is None and m.noise_hash is None
        expected = hashing.array_hash(
            "synthetic_latent_innovation_v1", m.innovations, dtype_code=">f8"
        )
        assert m.innovation_hash == expected

    def test_deterministic(self):
        a = _master(DGP_FAMILY_N_AR, "0")
        b = _master(DGP_FAMILY_N_AR, "0")
        assert np.array_equal(a.innovations, b.innovations)
        assert a.innovation_hash == b.innovation_hash
        assert np.array_equal(a.raw_prefix_1d(200), b.raw_prefix_1d(200))

    def test_innovation_shared_across_rho_raw_differs(self):
        a = _master(DGP_FAMILY_N_AR, "0")
        b = _master(DGP_FAMILY_N_AR, "0.8")
        assert np.array_equal(a.innovations, b.innovations)
        assert a.innovation_hash == b.innovation_hash
        ra = a.raw_prefix_1d(500)
        rb = b.raw_prefix_1d(500)
        assert not np.array_equal(ra, rb)
        assert a.raw_series_hash(500) != b.raw_series_hash(500)

    def test_raw_prefix_shapes_and_hash(self):
        m = _master(DGP_FAMILY_N_AR, "0")
        raw = m.raw_prefix(3120)
        assert raw.shape == (3120, 1)
        assert m.raw_series_hash(3120) == hashing.array_hash(
            "synthetic_raw_series_v1", raw, dtype_code=">f8"
        )

    def test_ar1_lag1_correlation(self):
        x0 = _master(DGP_FAMILY_N_AR, "0").raw_prefix_1d(L_MASTER)
        x8 = _master(DGP_FAMILY_N_AR, "0.8").raw_prefix_1d(L_MASTER)
        lag = lambda x: np.corrcoef(x[:-1], x[1:])[0, 1]
        assert abs(lag(x0)) < 0.05
        assert abs(lag(x8) - 0.8) < 0.05

    def test_variance_approx_unity(self):
        for rho in ("0", "0.8"):
            x = _master(DGP_FAMILY_N_AR, rho).raw_prefix_1d(L_MASTER)
            assert abs(x.std() - 1.0) < 0.05


class TestNCircleMaster:
    def test_shapes(self):
        m = _master(DGP_FAMILY_N_CIRCLE, "0")
        assert m.innovations.shape == (L_LATENT,)
        assert m.noise is not None and m.noise.shape == (L_MASTER, 2)
        assert m.noise_hash is not None
        assert m.formal_path.shape == (L_MASTER, 2)

    def test_innovation_and_noise_shared_across_rho(self):
        a = _master(DGP_FAMILY_N_CIRCLE, "0")
        b = _master(DGP_FAMILY_N_CIRCLE, "0.8")
        assert a.innovation_hash == b.innovation_hash
        assert a.noise_hash == b.noise_hash
        assert np.array_equal(a.noise, b.noise)
        assert not np.array_equal(a.formal_path[:500], b.formal_path[:500])

    def test_marginal_mean_and_variance_on_circle(self):
        x = _master(DGP_FAMILY_N_CIRCLE, "0").formal_path[:8000]
        mean = x.mean(axis=0)
        var = x.var(axis=0)
        assert np.abs(mean).max() < 0.03
        assert np.abs(var - 0.5).max() < 0.03

    def test_radius_approx_one(self):
        x = _master(DGP_FAMILY_N_CIRCLE, "0").formal_path[:8000]
        radius = np.linalg.norm(x, axis=1)
        assert abs(radius.mean() - 1.0) < 0.05

    def test_raw_series_hash(self):
        m = _master(DGP_FAMILY_N_CIRCLE, "0")
        raw = m.raw_prefix(100)
        assert raw.shape == (100, 2)
        assert m.raw_series_hash(100) == hashing.array_hash(
            "synthetic_raw_series_v1", raw, dtype_code=">f8"
        )


class TestDelayEmbedding:
    def test_hand_window(self):
        w = np.arange(10.0)
        pts = delay_embedding_3(w)
        assert pts.shape == (4, 3)
        expected = np.array(
            [[0.0, 3.0, 6.0], [1.0, 4.0, 7.0], [2.0, 5.0, 8.0], [3.0, 6.0, 9.0]]
        )
        assert np.array_equal(pts, expected)

    def test_window_too_short(self):
        with pytest.raises(ValueError):
            delay_embedding_3(np.zeros(6))
