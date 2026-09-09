"""Tests for the maximum scan statistic (Plan §3.3-§3.4)."""

import numpy as np
import pytest

from owtda_cal.scan import (
    candidate_bounds,
    candidate_indices,
    estimated_change_raw_time,
    plateau_selection,
    scan_statistic,
    statistic_curve,
)


class TestCandidates:
    def test_bounds_formula(self):
        assert candidate_bounds(192) == (29, 163)
        assert candidate_bounds(48) == (8, 40)
        ks = candidate_indices(192)
        assert len(ks) == 163 - 29 + 1 == 135
        assert ks[0] == 29 and ks[-1] == 163

    def test_invalid_m(self):
        with pytest.raises(ValueError):
            candidate_bounds(0)
        with pytest.raises(ValueError):
            candidate_bounds(1)


class TestDoubleImplementation:
    def test_fast_equals_slow(self):
        rng = np.random.default_rng(3)
        for (M, p) in [(48, 5), (96, 2), (192, 800), (30, 3)]:
            x = rng.standard_normal((M, p))
            a = statistic_curve(x)
            b = statistic_curve(x, reference=True)
            np.testing.assert_allclose(a["values"], b["values"], rtol=1e-12, atol=1e-12)
            np.testing.assert_array_equal(a["ks"], b["ks"])

    def test_hand_statistic(self):
        # M=4 small candidate-free; build manual with M=20 and known curve via
        # direct mean difference for one candidate.
        M = 20
        y = np.zeros((M, 2))
        y[:10] = 1.0
        y[10:] = -1.0
        curve = statistic_curve(y)
        ks = candidate_indices(M)
        k = 10
        mean_l = y[:k].mean(axis=0)
        mean_r = y[k:].mean(axis=0)
        expected = (k * (M - k) / M) * float(np.dot(mean_l - mean_r, mean_l - mean_r))
        idx = int(np.where(ks == k)[0][0])
        assert curve["values"][idx] == pytest.approx(expected)


class TestPlateau:
    def test_single_max(self):
        ks = np.array([5, 6, 7, 8, 9])
        vals = np.array([1.0, 2.0, 7.0, 3.0, 2.0])
        out = plateau_selection(ks, vals)
        assert out["khat"] == 7
        assert out["plateau_length"] == 1

    def test_longest_plateau_leftmost(self):
        # two runs qualify (within tol of max): lengths 2 and 3; pick length-3.
        ks = np.array([1, 2, 3, 4, 5, 6])
        vals = np.array([100.0, 100.0, 200.0, 200.0, 200.0, 100.0])
        out = plateau_selection(ks, vals)
        assert out["khat"] == 4  # segment [3,4,5], lower median = 4
        assert out["plateau_length"] == 3

    def test_tie_platform_leftmost(self):
        ks = np.array([10, 11, 12, 13, 14])
        vals = np.array([5.0, 9.0, 9.0, 9.0, 5.0])
        out = plateau_selection(ks, vals)
        assert out["plateau_length"] == 3
        assert out["khat"] == 12  # lower median of [11,12,13]
        assert out["qualifying_count"] == 3

    def test_empty_rejected(self):
        with pytest.raises(ValueError):
            plateau_selection(np.array([], dtype=np.int64), np.array([]))


class TestRawTime:
    def test_hand_mapping(self):
        # (W,s,M,k,T,tau): (64,64,192,96,12288,6144) -> 6144.5
        assert estimated_change_raw_time(96, stride=64, W=64) == pytest.approx(6144.5)
        # (64,16,192,96,3120,1560) -> 1560.5
        assert estimated_change_raw_time(96, stride=16, W=64) == pytest.approx(1560.5)


class TestScanStatistic:
    def test_scan_statistic_basics(self):
        M = 192
        y = np.random.default_rng(0).standard_normal((M, 800)) * 1e-3
        y[:96] += 0.5
        out = scan_statistic(y)
        assert out["M"] == 192
        assert out["candidate_count"] == 135
        assert out["observed_statistic"] >= 0.0
        assert out["khat"] in range(29, 164)

    def test_observed_statistic_shared_across_methods(self):
        # observed statistic must not depend on any calibration path
        x = np.random.default_rng(9).standard_normal((64, 3))
        s1 = scan_statistic(x)
        s2 = scan_statistic(x)
        assert s1["observed_statistic"] == s2["observed_statistic"]
