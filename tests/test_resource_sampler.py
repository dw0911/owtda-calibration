"""Resource sampling and the AM_RESOURCE_CAPACITY_V2 judge (ruling 2026-09-13).

Hard conditions are capacity and complete execution.  Page-file usage, page faults and
system paging rates are diagnostics: the judge contract below pins that they can neither
pass nor fail a run, that a breach of a capacity condition is refused, and that a
missing/gapped capacity record -- or an old-policy record -- cannot be signed off.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest
from capacity_fixture import bind_test_raw

_RESOURCE_DIR = None

@pytest.fixture(autouse=True)
def _raw_fixture_directory(tmp_path):
    global _RESOURCE_DIR
    _RESOURCE_DIR = tmp_path / "raw-fixtures"

REPO = Path(__file__).resolve().parents[1]
AUDIT = REPO / "audit"
if str(AUDIT) not in sys.path:
    sys.path.insert(0, str(AUDIT))

import resource_sampler

GIB = 1024**3


class _FakeResult:
    wall_seconds = 0.01
    errors = 0


def _resources(**overrides) -> dict:
    """A V2-shaped record: capacity present and complete, diagnostics alongside."""
    record = {
        "schema_version": 1,
        "kind": "run_resources_v1",
        "measured_wall_milliseconds": 1000,
        "peak_total_rss_bytes": int(1.05 * GIB),
        "evidence_bytes_written": 3_491_911,
        "disk_free_before_bytes": 486_340_247_552,
        "resource_allocation_failures": 0,
        "capacity_sampling": {
            "source": "GetPerformanceInfo",
            "interval_milliseconds": 1000,
            "samples": 900,
            "missing": 0,
            "max_gap_milliseconds": 1003,
            "commit_total_peak_bytes": 26_124_267_520,
            "commit_limit_bytes": 41_942_392_832,
            "physical_total_bytes": 34_157_764_608,
            "physical_available_min_bytes": 10_020_118_528,
            "incomplete": False,
        },
        # diagnostics: must never decide anything
        "host_swap_growth_bytes": 7_397_376,
        "own_commit_charge_growth_bytes": 9_163_272_192,
        "host_swap_measurement_caveat": "diagnostic only",
    }
    record.update(overrides)
    return record


def _verdict(resources=None, *, unexplained_errors: int = 0) -> dict:
    return resource_sampler.resource_verdict(
        bind_test_raw(resources if resources is not None else _resources(), _RESOURCE_DIR),
        unexplained_errors=unexplained_errors,
    )


class TestFrozenLimits:
    def test_policy_is_capacity_v2(self):
        policy = resource_sampler.load_resource_policy()
        assert policy["resource_policy_id"] == "AM_RESOURCE_CAPACITY_V2"
        assert policy["hard_conditions"]["host_commit_fraction_max"] == 0.80
        # Re-audit 2026-09-15 (P1): the registered parallelism is prospective and was
        # lowered 8 -> 4 after attempt 10 breached the paired commit ratio (0.9330)
        # and the worker sweep measured the job's own increment (~1.17 GB/worker).
        assert policy["hard_conditions"]["workers"] == 4
        assert "host_pagefile_used_growth" in policy["diagnostic_only"]

    def test_retired_gate_is_kept_in_history_not_in_admission(self):
        policy = resource_sampler.load_resource_policy()
        assert "swap_growth_bytes_max = 0" in policy["supersedes_for_future_admission"]
        verdict = _verdict()
        assert "host_swap_growth_within_limit" not in verdict["checks"]
        assert verdict["resource_policy_id"] == "AM_RESOURCE_CAPACITY_V2"


class TestJudgeContract:
    """The five contract cases the ruling asked the judge to be tested on first."""

    def test_a_positive_pagefile_growth_with_ample_capacity_does_not_reject(self):
        verdict = _verdict(_resources(host_swap_growth_bytes=64 * 1024**2))
        assert verdict["passed"] is True
        assert verdict["status"] == "PASS"
        assert verdict["diagnostics"]["host_pagefile_used_growth_bytes"] == 64 * 1024**2

    def test_b_large_normal_page_faults_do_not_fail_a_run(self):
        resources = _resources()
        resources["process_tree_page_faults"] = 10**9
        resources["system_paging_rates"] = {"page_reads_per_second_peak": 1234.5}
        verdict = _verdict(resources)
        assert verdict["passed"] is True
        assert "diagnostic only" in verdict["diagnostics"]["note"]

    def test_c_capacity_breach_is_refused(self):
        tight_commit = _resources()
        tight_commit["capacity_sampling"] = {
            **tight_commit["capacity_sampling"],
            "commit_total_peak_bytes": int(0.95 * 41_942_392_832),
        }
        assert _verdict(tight_commit)["passed"] is False
        assert _verdict(tight_commit)["checks"]["host_commit_fraction_within_limit"] is False

        low_memory = _resources()
        low_memory["capacity_sampling"] = {
            **low_memory["capacity_sampling"],
            "physical_available_min_bytes": 1024**3,  # below max(2 GiB, 10%)
        }
        assert _verdict(low_memory)["passed"] is False
        assert _verdict(low_memory)["checks"]["host_available_phys_within_minimum"] is False

    def test_d_missing_or_gapped_capacity_record_is_incomplete(self):
        gapped = _resources()
        gapped["capacity_sampling"] = {
            **gapped["capacity_sampling"], "max_gap_milliseconds": 60_000,
            "incomplete": True,
        }
        verdict = _verdict(gapped)
        assert verdict["passed"] is False
        assert verdict["checks"]["capacity_sampling_complete"] is False

        absent = _resources()
        absent.pop("capacity_sampling")
        assert _verdict(absent)["passed"] is False

        # the empty-record path is called directly: the helper substitutes a good record
        no_record = resource_sampler.resource_verdict(None, unexplained_errors=0)
        assert no_record["status"] == "INCOMPLETE"
        assert no_record["passed"] is False

    def test_e_old_policy_record_cannot_be_signed_under_v2(self):
        """A V1 record (no capacity block) must not receive a V2 PASS."""
        v1 = {
            "peak_total_rss_bytes": int(1.05 * GIB),
            "host_swap_growth_bytes": 0,
            "evidence_bytes_written": 3_491_911,
            "disk_free_before_bytes": 486_340_247_552,
        }
        verdict = _verdict(v1)
        assert verdict["passed"] is False
        assert verdict["checks"]["capacity_sampling_complete"] is False

    def test_allocation_failures_must_be_shown_to_be_zero(self):
        unknown = _resources(resource_allocation_failures=None)
        assert _verdict(unknown)["passed"] is False
        assert _verdict(unknown)["checks"]["resource_allocation_failures_within_limit"] is False
        assert _verdict(_resources(resource_allocation_failures=1))["passed"] is False


class TestSampling:
    def test_sampler_records_the_run_it_wrapped(self, tmp_path):
        def runner(**kwargs):
            (tmp_path / "ledger.jsonl").write_text("x" * 2048, encoding="utf-8")
            return _FakeResult()

        _result, resources = resource_sampler.sample_run(runner, evidence_root=tmp_path, run_id="TEST")
        assert resources["samples"] >= 1
        assert resources["peak_total_rss_bytes"] > 0
        capacity = resources["capacity_sampling"]
        assert capacity["samples"] >= 0 and capacity["missing"] >= 0
        if capacity["samples"]:
            assert capacity["commit_limit_bytes"] > 0
            assert capacity["physical_total_bytes"] > 0
            assert capacity["incomplete"] is False
        assert resources["resource_allocation_failures"] is None  # set by the runner

    def test_capacity_record_is_integer_only(self):
        """The record is sealed under a canonical hash, where bare floats are banned."""
        def runner(**kwargs):
            return _FakeResult()

        import tempfile

        with tempfile.TemporaryDirectory() as tmp:
            _result, resources = resource_sampler.sample_run(
                runner, evidence_root=Path(tmp), run_id="TEST"
            )
        capacity = resources["capacity_sampling"]
        for key, value in capacity.items():
            assert not isinstance(value, float), key

    def test_persistence_is_measured_after_the_ledger_is_written(self, tmp_path):
        def runner(**kwargs):
            (tmp_path / "ledger.jsonl").write_text("y" * 4096, encoding="utf-8")
            return _FakeResult()

        _result, resources = resource_sampler.sample_run(runner, evidence_root=tmp_path, run_id="TEST")
        before = resources["evidence_bytes_written"]
        resource_sampler.finalize_persistence(resources, evidence_root=tmp_path)
        assert resources["evidence_bytes_written"] >= before
        assert resources["persistence_included"] is True

    def test_performance_info_shape_when_available(self):
        info = resource_sampler.performance_info()
        if info is None:  # pragma: no cover - non-Windows or unavailable counters
            pytest.skip("capacity counters unavailable on this platform")
        assert info["commit_limit_bytes"] > 0
        assert info["physical_total_bytes"] >= info["physical_available_bytes"]
        assert info["page_size_bytes"] in (4096, 65536)
