"""Tests for feature specs/matrices and sufficient stats (Plan §5, §10, §11)."""

import numpy as np
import pytest

from owtda_cal import hashing
from owtda_cal.features import (
    BPI_STABLE_ID,
    SCENARIO_N_AR,
    SCENARIO_N_CIRCLE,
    SCENARIO_PAMAP2,
    bpi_feature_spec,
    feature_config_hash,
    feature_matrix_for_windows,
    feature_sufficient_stats,
    moments_feature_spec,
    scenario_bpi_cap,
    scenario_moments_scale,
)


def _n_ar_windows(rng=None, m=8, w=64):
    rng = rng or np.random.default_rng(11)
    return [rng.standard_normal(w) for _ in range(m)]


def _circle_windows(rng=None, m=8, w=64):
    rng = rng or np.random.default_rng(12)
    out = []
    for _ in range(m):
        t = np.linspace(0.0, 2 * np.pi, w, endpoint=False)
        out.append(np.column_stack([np.cos(t), np.sin(t)]) + 0.05 * rng.standard_normal((w, 2)))
    return out


class TestConfigs:
    def test_bpi_spec_fields(self):
        spec = bpi_feature_spec()
        assert spec["stable_id"] == BPI_STABLE_ID
        assert spec["sigma"] == "0.05"
        assert spec["grid_rows"] == 20
        assert spec["homology_channels"] == ["H0", "H1"]

    def test_config_hash_stable_and_sensitive(self):
        h = feature_config_hash(bpi_feature_spec())
        assert h == feature_config_hash(bpi_feature_spec())
        assert len(h) == 64
        mod = dict(bpi_feature_spec(), grid_rows=21)
        assert feature_config_hash(mod) != h
        assert feature_config_hash(moments_feature_spec()) != h

    def test_scenario_scales(self):
        assert scenario_bpi_cap(SCENARIO_N_AR) == 6.0
        assert scenario_bpi_cap(SCENARIO_N_CIRCLE) == 2.5
        assert scenario_bpi_cap(SCENARIO_PAMAP2) == 6.0
        assert scenario_moments_scale(SCENARIO_PAMAP2) == 6.0


class TestMatrices:
    def test_bpi_matrix_n_ar(self):
        ws = _n_ar_windows()
        m = feature_matrix_for_windows(ws, feature_kind="bpi", scenario=SCENARIO_N_AR)
        assert m.shape == (len(ws), 800)

    def test_bpi_matrix_circle(self):
        ws = _circle_windows()
        m = feature_matrix_for_windows(ws, feature_kind="bpi", scenario=SCENARIO_N_CIRCLE)
        assert m.shape == (len(ws), 800)

    def test_moments_matrix_dims(self):
        a = feature_matrix_for_windows(_circle_windows(), feature_kind="moments", scenario=SCENARIO_N_CIRCLE)
        assert a.shape[1] == 5  # 2-D cloud
        b = feature_matrix_for_windows(
            [np.random.default_rng(0).standard_normal((64, 3)) for _ in range(4)],
            feature_kind="moments", scenario=SCENARIO_PAMAP2,
        )
        assert b.shape[1] == 9  # 3-D cloud

    def test_matrix_deterministic(self):
        ws = _n_ar_windows()
        a = feature_matrix_for_windows(ws, feature_kind="bpi", scenario=SCENARIO_N_AR)
        b = feature_matrix_for_windows(ws, feature_kind="bpi", scenario=SCENARIO_N_AR)
        assert np.array_equal(a, b)

    def test_matrix_array_hash(self):
        ws = _n_ar_windows()
        m = feature_matrix_for_windows(ws, feature_kind="bpi", scenario=SCENARIO_N_AR)
        h = hashing.array_hash("window_feature_matrix_v1", m, dtype_code=">f8")
        assert len(h) == 64
        # matrix content change -> hash change
        h2 = hashing.array_hash(
            "window_feature_matrix_v1", m + 1e-9, dtype_code=">f8"
        )
        assert h != h2

    def test_duplicate_windows_dedup_not_cross_window(self):
        # Two distinct windows keep two rows even if clouds are large circles.
        ws = _circle_windows(m=2)
        m = feature_matrix_for_windows(ws, feature_kind="bpi", scenario=SCENARIO_N_CIRCLE)
        assert m.shape[0] == 2


class TestSufficientStats:
    def test_hand_small_matrix(self):
        mat = np.array([[1.0, 2.0], [3.0, 4.0]])
        s = feature_sufficient_stats(mat)
        assert np.array_equal(s["a"], [2.0, 3.0])
        assert s["q"] == pytest.approx(15.0)

    def test_zero_rows(self):
        mat = np.zeros((5, 800))
        s = feature_sufficient_stats(mat)
        assert np.all(s["a"] == 0.0)
        assert s["q"] == 0.0


class TestDegenerate:
    def test_constant_window_bpi_zero_moments_constant(self):
        const = [np.ones(64) * 2.0]  # N-AR delay cloud collapses to 1 point
        mb = feature_matrix_for_windows(const, feature_kind="bpi", scenario=SCENARIO_N_AR)
        mm = feature_matrix_for_windows(const, feature_kind="moments", scenario=SCENARIO_N_AR)
        assert np.all(mb == 0.0)
        assert mb.shape == (1, 800)
        # constant delay cloud of 58 identical triples -> single point (2,2,2);
        # delay cloud is 3-D so the MOMENTS feature is 9-dim.
        assert mm.shape == (1, 9)
        assert np.allclose(mm[0, :3], [2.0, 2.0, 2.0])
        assert np.all(mm[0, 3:] == 0.0)
