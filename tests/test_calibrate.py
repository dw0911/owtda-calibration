"""Tests for M0/M1 resamplers (Plan §6)."""

import numpy as np
import pytest

from owtda_cal.calibrate import (
    calibrate_m0,
    calibrate_m1,
    dmb_block_length,
    dmb_multiplier_series,
    integer_cuberoot_ceil,
    m0_permutation,
    m1_gaussian_draw,
)
from owtda_cal.scan import scan_statistic

_ROOT = "ab" * 32
DG = "M01"
UID = "data_unit_1"  # opaque test id


def _matrix(m=40, p=3, seed=1, shift_at=None):
    rng = np.random.default_rng(seed)
    x = rng.standard_normal((m, p))
    if shift_at is not None:
        x[shift_at:] += 1.0
    return x


class TestBlockLength:
    def test_cuberoot_ceil(self):
        assert integer_cuberoot_ceil(192) == 6
        assert integer_cuberoot_ceil(216) == 6
        assert integer_cuberoot_ceil(215) == 6
        assert integer_cuberoot_ceil(48) == 4
        assert integer_cuberoot_ceil(1) == 1

    def test_dmb_b(self):
        # R1 configuration W=64,s=64,M=192 -> b=6 (matches DMB-R1)
        assert dmb_block_length(W=64, stride=64, M=192) == 6
        assert dmb_block_length(W=64, stride=16, M=192) == 6
        assert dmb_block_length(W=64, stride=8, M=192) == 9  # q0=9 dominates
        assert dmb_block_length(W=64, stride=64, M=48) == 4


class TestMultiplier:
    def test_length(self):
        e = np.random.default_rng(0).standard_normal(20)
        xi = dmb_multiplier_series(e, b=6)
        assert xi.shape == (15,)  # 20 - 6 + 1

    def test_triangular_covariance(self):
        b = 6
        draws = np.random.default_rng(1).standard_normal((20000, 2 * b + 4))
        xi = np.stack([dmb_multiplier_series(d, b=b) for d in draws])
        corr1 = np.corrcoef(xi[:, 0], xi[:, 1])[0, 1]
        assert corr1 == pytest.approx(1 - 1 / b, abs=0.01)
        # h >= b -> zero covariance
        corr_b = np.corrcoef(xi[:, 0], xi[:, b])[0, 1]
        assert abs(corr_b) < 0.03


class TestM0:
    def test_permutation_contract(self):
        perm = m0_permutation(_ROOT, method_generation_id=DG,
                              data_unit_id=UID, resample_index=1, M=40)
        assert perm.shape == (40,) and perm.dtype == np.int64
        assert sorted(perm.tolist()) == list(range(40))
        perm2 = m0_permutation(_ROOT, method_generation_id=DG,
                               data_unit_id=UID, resample_index=1, M=40)
        assert np.array_equal(perm, perm2)
        other = m0_permutation(_ROOT, method_generation_id=DG,
                               data_unit_id=UID + "_x", resample_index=1, M=40)
        assert not np.array_equal(perm, other)

    def test_calibrate_deterministic(self):
        x = _matrix(shift_at=20)
        a = calibrate_m0(x, root_key_hex=_ROOT, method_generation_id=DG, data_unit_id=UID)
        b = calibrate_m0(x, root_key_hex=_ROOT, method_generation_id=DG, data_unit_id=UID)
        assert a == b

    def test_p_grid_and_observed(self):
        x = _matrix(shift_at=20)
        out = calibrate_m0(x, root_key_hex=_ROOT, method_generation_id=DG, data_unit_id=UID)
        assert out["B"] == 999
        assert out["p_value"] * 1000 == pytest.approx(1 + out["exceed_count"])
        assert out["reject"] == (out["exceed_count"] <= 49)
        assert out["observed_statistic"] == scan_statistic(x)["observed_statistic"]

    def test_strong_shift_rejects(self):
        x = _matrix(m=60, p=2, seed=5, shift_at=30)
        out = calibrate_m0(x, root_key_hex=_ROOT, method_generation_id=DG, data_unit_id=UID)
        assert out["reject"] is True


class TestM1:
    def test_draw_contract(self):
        e = m1_gaussian_draw(_ROOT, method_generation_id=DG,
                             data_unit_id=UID, resample_index=1, size=44)
        assert e.shape == (44,)
        e2 = m1_gaussian_draw(_ROOT, method_generation_id=DG,
                              data_unit_id=UID, resample_index=1, size=44)
        assert np.array_equal(e, e2)

    def test_calibrate_deterministic(self):
        x = _matrix(shift_at=20)
        a = calibrate_m1(x, root_key_hex=_ROOT, method_generation_id=DG,
                         data_unit_id=UID, W=64, stride=64)
        b = calibrate_m1(x, root_key_hex=_ROOT, method_generation_id=DG,
                         data_unit_id=UID, W=64, stride=64)
        assert a == b
        assert a["observed_statistic"] == scan_statistic(x)["observed_statistic"]

    def test_p_and_reject_rules(self):
        x = _matrix(shift_at=20)
        out = calibrate_m1(x, root_key_hex=_ROOT, method_generation_id=DG,
                           data_unit_id=UID, W=64, stride=16)
        assert out["p_value"] * 1000 == pytest.approx(1 + out["exceed_count"])
        assert out["reject"] == (out["exceed_count"] <= 49)
