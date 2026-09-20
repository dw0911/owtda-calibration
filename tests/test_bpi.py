"""Tests for fixed persistence-intensity mapping (Plan §5.2)."""

import numpy as np
import pytest

from owtda_cal.bpi import GRID_DELTA, SIGMA, bpi_from_diagrams, intensity_channel


class TestIntensityChannel:
    def test_empty_channel_zero(self):
        z = intensity_channel(np.zeros((0, 2)), cap=6.0)
        assert z.shape == (400,)
        assert np.all(z == 0.0)

    def test_single_class_golden_cell(self):
        cap = 4.0
        classes = np.array([[1.0, 2.5]])  # u=0.25, v=0.375
        z = intensity_channel(classes, cap=cap)
        u = 0.25
        v = 0.375
        r, l = 7, 13
        gr = (r + 0.5) * GRID_DELTA
        gl = (l + 0.5) * GRID_DELTA
        kernel_norm = 1.0 / (2.0 * np.pi * SIGMA * SIGMA)
        expected = (
            GRID_DELTA
            * kernel_norm
            * v
            * np.exp(-((gr - u) ** 2 + (gl - v) ** 2) / (2.0 * SIGMA * SIGMA))
        )
        assert np.isclose(z[r * 20 + l], expected, rtol=1e-9, atol=1e-12)

    def test_cap_winsor(self):
        # birth/death far above cap saturate u=v=1; finite, non-zero kernel at (0.975).
        classes = np.array([[100.0, 200.0]])
        z = intensity_channel(classes, cap=6.0)
        # centre near g_19=0.975; value must be positive
        assert z[19 * 20 + 19] > 0.0

    def test_death_less_equal_birth_rejected(self):
        with pytest.raises(ValueError):
            intensity_channel(np.array([[1.0, 1.0]]), cap=6.0)


class TestBpiFromDiagrams:
    def test_length_800(self):
        h0 = np.array([[0.0, 1.0], [0.0, 2.0]])
        h1 = np.array([[0.5, 1.5]])
        f = bpi_from_diagrams(h0, h1, cap=6.0)
        assert f.shape == (800,)
        assert np.isclose(np.linalg.norm(f) * np.sqrt(2.0) > 0.0, True)

    def test_h0_first_then_h1(self):
        h0 = np.array([[0.0, 1.0]])
        h1 = np.empty((0, 2))
        f = bpi_from_diagrams(h0, h1, cap=6.0)
        # H0 channel populated; H1 all zeros; 800 total.
        assert not np.all(f[:400] == 0.0)
        assert np.all(f[400:] == 0.0)
