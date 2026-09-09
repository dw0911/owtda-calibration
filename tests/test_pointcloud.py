"""Tests for window-local point-cloud pipeline (Plan §5.1)."""

import numpy as np
import pytest

from owtda_cal.pointcloud import (
    PointCloudError,
    build_point_cloud,
    check_point_limit,
    clean_and_dedup,
)


class TestCleanDedup:
    def test_negative_zero_normalised(self):
        pts = np.array([[0.0, 0.0], [-0.0, 0.0], [1.0, -0.0]])
        out = clean_and_dedup(pts)
        assert out.shape == (2, 2)
        assert np.array_equal(out[0], [0.0, 0.0])
        assert not np.any(np.signbit(out))

    def test_row_permutation_invariant(self):
        a = clean_and_dedup(np.array([[1.0, 2.0], [0.0, 0.0], [3.0, 4.0]]))
        b = clean_and_dedup(np.array([[3.0, 4.0], [1.0, 2.0], [0.0, 0.0]]))
        assert np.array_equal(a, b)

    def test_duplicates_removed(self):
        out = clean_and_dedup(np.array([[1.0, 1.0], [1.0, 1.0], [2.0, 2.0]]))
        assert out.shape == (2, 2)

    def test_nan_inf_rejected(self):
        for bad in (np.nan, np.inf, -np.inf):
            with pytest.raises(PointCloudError):
                clean_and_dedup(np.array([[1.0, 2.0], [bad, 0.0]]))

    def test_non_2d_rejected(self):
        with pytest.raises(PointCloudError):
            clean_and_dedup(np.zeros(5))


class TestPointLimit:
    def test_exceeding_limit_raises(self):
        with pytest.raises(PointCloudError):
            check_point_limit(129, point_limit=128)

    def test_at_limit_ok(self):
        check_point_limit(128, point_limit=128)
        check_point_limit(1, point_limit=128)


class TestBuildCloud:
    def test_delay_route_n_ar(self):
        w = np.arange(10.0)
        cloud = build_point_cloud(w, delay=True)
        assert cloud.shape == (4, 3)
        assert np.array_equal(cloud[0], [0.0, 3.0, 6.0])

    def test_direct_route_2d(self):
        pts = np.array([[0.0, 0.0], [1.0, 0.0], [1.0, 0.0]])
        cloud = build_point_cloud(pts, delay=False)
        assert cloud.shape == (2, 2)

    def test_delay_requires_1d(self):
        with pytest.raises(PointCloudError):
            build_point_cloud(np.zeros((5, 2)), delay=True)

    def test_direct_requires_2d(self):
        with pytest.raises(PointCloudError):
            build_point_cloud(np.zeros(5), delay=False)
