"""Audit A08: resource claims must be sampled from the run they describe.

These tests exercise the sampler itself (peak process-tree RSS, page-file delta,
disk delta) and the frozen thresholds it evaluates against, so a resource record
can never be produced by a different execution than the one it is filed with.
"""

from __future__ import annotations

import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
AUDIT = REPO / "audit"
if str(AUDIT) not in sys.path:
    sys.path.insert(0, str(AUDIT))

import resource_sampler


class _FakeResult:
    wall_seconds = 0.01
    errors = 0


class TestFrozenLimits:
    def test_limits_are_the_frozen_ones(self):
        limits = resource_sampler.load_limits()
        assert limits["peak_total_rss_gib_max"] == 24.0
        assert limits["swap_growth_bytes_max"] == 0
        assert limits["unexplained_errors_max"] == 0
        assert "0.8" in limits["disk_rule"]
        assert limits["source"] == resource_sampler.LIMITS_SOURCE

    def test_limits_are_read_from_the_delivered_spec(self):
        import json

        spec = json.loads(resource_sampler.COMPUTE_SPEC.read_text(encoding="utf-8"))
        assert (
            resource_sampler.acceptance_limits(spec)["peak_total_rss_gib_max"]
            == float(spec["parallelism_contract"]["acceptance"]["peak_total_rss_gib_max"])
        )


class TestSampling:
    def test_sampler_records_the_run_it_wrapped(self, tmp_path):
        def runner(**kwargs):
            # A run that writes evidence and touches memory.
            (tmp_path / "ledger.jsonl").write_text("x" * 2048, encoding="utf-8")
            ballast = bytearray(2 * 1024 * 1024)
            assert ballast is not None
            return _FakeResult()

        result, resources = resource_sampler.sample_run(
            runner, evidence_root=tmp_path, manifest={}, seed_registry={}
        )
        assert isinstance(result, _FakeResult)
        assert resources["kind"] == "run_resources_v1"
        assert resources["samples"] >= 1
        assert resources["peak_total_rss_bytes"] > 0
        assert resources["measured_wall_milliseconds"] >= 0
        assert resources["evidence_bytes_written"] >= 2048
        assert resources["disk_free_before_bytes"] > 0
        assert resources["swap_growth_bytes"] >= 0
        assert "host activity" in resources["swap_measurement_caveat"]

    def test_record_is_canonical_encodable(self, tmp_path):
        """The record is embedded in the seal, whose hash is canonical.

        Bare floats are forbidden there, so a float leaking into this record would
        make the seal step raise at the end of an expensive run.  This test is the
        regression guard.
        """
        from owtda_cal.canonical import canonical_json

        def runner(**kwargs):
            return _FakeResult()

        _, resources = resource_sampler.sample_run(runner, evidence_root=tmp_path)
        encoded = canonical_json({**resources, "run_id": "S04:SMOKE_NULL:w8:r32",
                                  "phase": "SMOKE_NULL"})
        assert encoded  # raising would have failed the test

    def test_swap_growth_is_computed_from_before_and_peak(self):
        resources = {
            "peak_total_rss_bytes": 1024**3,
            "swap_before_bytes": 100,
            "swap_peak_bytes": 100,
            "swap_growth_bytes": 0,
            "disk_free_before_bytes": 10**12,
            "evidence_bytes_written": 1,
        }
        verdict = resource_sampler.resource_verdict(
            resources, limits=resource_sampler.load_limits(), unexplained_errors=0
        )
        assert verdict["passed"] is True
        assert verdict["checks"]["no_swap_growth"] is True
        assert verdict["observed"]["swap_growth_bytes"] == 0


class TestResourceVerdictMutations:
    def _verdict(self, **overrides):
        resources = {
            "peak_total_rss_bytes": 1024**3,
            "swap_growth_bytes": 0,
            "disk_free_before_bytes": 10**12,
            "evidence_bytes_written": 10**6,
            "swap_measurement_caveat": "host-wide",
        }
        resources.update(overrides)
        return resource_sampler.resource_verdict(
            resources, limits=resource_sampler.load_limits(), unexplained_errors=0
        )

    def test_clean_record_passes(self):
        assert self._verdict()["passed"] is True

    def test_any_swap_growth_fails(self):
        verdict = self._verdict(swap_growth_bytes=1)
        assert verdict["passed"] is False
        assert verdict["checks"]["no_swap_growth"] is False

    def test_peak_rss_above_limit_fails(self):
        verdict = self._verdict(peak_total_rss_bytes=24 * 1024**3 + 1)
        assert verdict["passed"] is False
        assert verdict["checks"]["peak_total_rss_within_limit"] is False

    def test_disk_rule_fails_above_eighty_percent_of_free(self):
        verdict = self._verdict(disk_free_before_bytes=1000, evidence_bytes_written=801)
        assert verdict["passed"] is False
        assert verdict["checks"]["disk_rule"] is False

    def test_absent_record_fails_closed(self):
        verdict = resource_sampler.resource_verdict(
            None, limits=resource_sampler.load_limits(), unexplained_errors=0
        )
        assert verdict["passed"] is False
        assert verdict["checks"] == {"resources_recorded": False}

    def test_unexplained_errors_counted_against_the_contract(self):
        verdict = resource_sampler.resource_verdict(
            {
                "peak_total_rss_gib": 1.0,
                "swap_growth_bytes": 0,
                "disk_free_before_bytes": 10**12,
                "evidence_bytes_written": 1,
            },
            limits=resource_sampler.load_limits(),
            unexplained_errors=1,
        )
        assert verdict["passed"] is False
        assert verdict["checks"]["unexplained_errors_within_limit"] is False
