"""Smoke-level throughput probe tests (Plan §9.4 exploratory budget)."""

from owtda_cal import probe


class TestBenchmark:
    def test_metrics_present_and_positive(self):
        m = probe.benchmark()
        for key in (
            "bpi_circle_per_window_seconds",
            "bpi_ar_per_window_seconds",
            "m1_full_b999_seconds",
            "extrapolated_h0_wall_hours_1w",
        ):
            assert m[key] > 0.0, key

    def test_budget_scale_is_finite(self):
        m = probe.benchmark()
        assert abs(m["extrapolated_h0_wall_hours_1w"]) < 1e6

    def test_independent_root_separate(self):
        assert len(probe.smoke_independent_root()) == 64
