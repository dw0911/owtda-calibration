"""Tests for VR persistent homology wrapper (Plan §5.1)."""

import numpy as np
import pytest

from owtda_cal.ph import PersistentHomologyError, h0h1, vr_diagrams


def _circle(n=60):
    t = np.linspace(0.0, 2.0 * np.pi, n, endpoint=False)
    return np.column_stack([np.cos(t), np.sin(t)])


class TestVR:
    def test_circle_h1_class_finite(self):
        h0, h1 = h0h1(_circle())
        # 60 components -> 59 finite H0 merges; final [0,inf] dropped.
        assert h0.shape == (59, 2)
        # one H1 class, death capped at a finite value by ripser 0.6.15.
        assert h1.shape == (1, 2)
        assert np.isfinite(h1).all()
        assert h1[0, 1] > h1[0, 0] > 0.0

    def test_two_points(self):
        pts = np.array([[0.0, 0.0], [3.0, 0.0]])
        h0, h1 = h0h1(pts)
        assert h0.shape == (1, 2)
        assert abs(h0[0, 1] - 3.0) < 1e-12
        assert h1.shape == (0, 2)

    def test_three_points_collinear(self):
        pts = np.array([[0.0, 0.0], [1.0, 0.0], [2.0, 0.0]])
        h0, h1 = h0h1(pts)
        assert h0.shape[0] == 2
        assert h1.shape[0] == 0

    def test_deterministic(self):
        c = _circle()
        a = vr_diagrams(c)
        b = vr_diagrams(c)
        assert all(np.array_equal(x, y) for x, y in zip(a, b))

    def test_row_permutation_same_cloud_same_diagrams(self):
        c = _circle()
        perm = np.random.default_rng(7).permutation(c.shape[0])
        a = vr_diagrams(c)
        b = vr_diagrams(c[perm])
        assert all(np.array_equal(x, y) for x, y in zip(a, b))

    def test_degenerate_rejected(self):
        with pytest.raises(PersistentHomologyError):
            vr_diagrams(np.array([[1.0, 1.0]]))
        with pytest.raises(PersistentHomologyError):
            vr_diagrams(np.zeros((0, 2)))
