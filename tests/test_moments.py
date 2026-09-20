"""Tests for the MOMENTS control representation (Plan §5.3)."""

import numpy as np

from owtda_cal.moments import moments_feature, moments_feature_size


class TestMoments:
    def test_two_points_hand(self):
        pts = np.array([[0.0, 0.0], [2.0, 0.0]])
        f = moments_feature(pts, scale=1.0)
        # mean [1,0]; cov = diag(1,0); off diag 0
        assert np.array_equal(f, [1.0, 0.0, 1.0, 0.0, 0.0])
        assert len(f) == moments_feature_size(2) == 5

    def test_scale_division(self):
        pts = np.array([[0.0, 0.0], [2.0, 0.0]])
        f = moments_feature(pts, scale=2.0)
        assert np.array_equal(f, [0.5, 0.0, 0.25, 0.0, 0.0])

    def test_constant_cloud_returns_mean_zero_cov(self):
        pts = np.array([[3.0, 4.0]])
        f = moments_feature(pts, scale=1.0)
        assert np.array_equal(f, [3.0, 4.0, 0.0, 0.0, 0.0])

    def test_empty_cloud_zero(self):
        f = moments_feature(np.zeros((0, 2)), scale=1.0)
        assert np.array_equal(f, np.zeros(5))

    def test_3d_size_nine(self):
        pts = np.array([[1.0, 0.0, 0.0], [0.0, 1.0, 0.0]])
        f = moments_feature(pts, scale=1.0)
        assert len(f) == moments_feature_size(3) == 9

    def test_translation_moves_mean_only(self):
        pts = np.array([[0.0, 0.0], [1.0, 0.0], [0.0, 1.0]])
        f = moments_feature(pts, scale=1.0)
        g = moments_feature(pts + np.array([5.0, -2.0]), scale=1.0)
        assert np.allclose(g[:2], f[:2] + [5.0, -2.0])
        assert np.allclose(g[2:], f[2:], atol=1e-12)
