"""Determinism attacks for ordered parallelism (Plan §19 #8/#9/#12)."""

import numpy as np
import pytest

from owtda_cal.parallel import (
    feature_matrix_parallel,
    ordered_map,
    scan_for_global_numpy_random,
)

_REPO = __import__("pathlib").Path(__file__).resolve().parents[1]


def _circle_windows(n=5, w=64, seed=5):
    rng = np.random.default_rng(seed)
    out = []
    for _ in range(n):
        t = np.linspace(0.0, 2 * np.pi, w, endpoint=False)
        out.append(
            np.column_stack([np.cos(t), np.sin(t)]) + 0.05 * rng.standard_normal((w, 2))
        )
    return out


class TestOrderedMap:
    def test_workers_one_is_reference(self):
        assert ordered_map(abs, [-1, 2, -3], workers=1) == [1, 2, 3]

    def test_workers_preserve_order(self):
        items = list(range(20))
        assert ordered_map(abs, items, workers=2) == items

    def test_invalid_workers(self):
        with pytest.raises(ValueError):
            ordered_map(abs, [1], workers=0)


class TestParallelFeatureMatrix:
    def test_bpi_workers_bitwise_equal(self):
        ws = _circle_windows()
        serial = feature_matrix_parallel(
            ws, feature_kind="bpi", scenario="N_CIRCLE", workers=1
        )
        parallel = feature_matrix_parallel(
            ws, feature_kind="bpi", scenario="N_CIRCLE", workers=2
        )
        assert serial.shape == parallel.shape == (5, 800)
        assert np.array_equal(serial, parallel)

    def test_moments_workers_bitwise_equal(self):
        ws = _circle_windows()
        serial = feature_matrix_parallel(
            ws, feature_kind="moments", scenario="N_CIRCLE", workers=1
        )
        parallel = feature_matrix_parallel(
            ws, feature_kind="moments", scenario="N_CIRCLE", workers=3
        )
        assert np.array_equal(serial, parallel)

    def test_submission_order_does_not_change_rows(self):
        ws = _circle_windows(n=6)
        perm = [3, 0, 5, 1, 4, 2]
        shuffled = [ws[i] for i in perm]
        ref = feature_matrix_parallel(
            ws, feature_kind="bpi", scenario="N_CIRCLE", workers=1
        )
        got = feature_matrix_parallel(
            shuffled, feature_kind="bpi", scenario="N_CIRCLE", workers=2
        )
        for row, src in enumerate(perm):
            assert np.array_equal(got[row], ref[src])

    def test_chunk_size_variation_is_irrelevant(self):
        ws = _circle_windows(n=4)
        a = feature_matrix_parallel(
            ws, feature_kind="moments", scenario="N_CIRCLE", workers=2, chunk_size=1
        )
        b = feature_matrix_parallel(
            ws, feature_kind="moments", scenario="N_CIRCLE", workers=2, chunk_size=4
        )
        assert np.array_equal(a, b)

    def test_empty_windows(self):
        m = feature_matrix_parallel(
            [], feature_kind="bpi", scenario="N_CIRCLE", workers=2
        )
        assert m.shape[0] == 0


class TestNoGlobalNumpyRandom:
    def test_src_and_tests_are_clean(self):
        violations = scan_for_global_numpy_random(_REPO / "src", _REPO / "tests")
        assert violations == [], violations
