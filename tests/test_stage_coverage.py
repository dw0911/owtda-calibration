"""Stage coverage must be provable from the raw sample stream (R4 block B).

The audit's point: relabelling a summary as ``FULL_SCIENTIFIC_LIFECYCLE`` does not
extend coverage.  Coverage exists only when a sample carrying the stage is present in
the raw JSONL, with a row range a seal can quote.  These tests pin the judgement --
and pin that an *intended* stage with no samples is reported missing, not assumed.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "audit"))

from resource_sampler import (
    FULL_LIFECYCLE_STAGES,
    ResourceStageCoverageError,
    assert_stage_coverage,
    merge_final_verdict,
    stage_coverage,
)


def _rows(*stages: str) -> list[dict]:
    return [{"seq": i, "stage": stage} for i, stage in enumerate(stages)]


class TestStageCoverage:
    def test_a_full_stream_reports_every_required_stage(self):
        coverage = stage_coverage(_rows("start", "compute", "compute", "persist",
                                        "teardown"))
        assert coverage["complete"] is True
        assert coverage["missing"] == []
        assert coverage["stages"]["compute"]["samples"] == 2
        assert coverage["stages"]["start"]["first_row"] == 0

    def test_an_intended_but_absent_stage_is_reported_missing(self):
        coverage = stage_coverage(_rows("start", "compute", "teardown"))
        assert coverage["complete"] is False
        assert coverage["missing"] == ["persist"]
        assert coverage["required"] == ["start", "compute", "persist", "teardown"]

    def test_row_ranges_reflect_the_stream_not_the_intent(self):
        coverage = stage_coverage(_rows("start", "compute", "persist", "compute",
                                        "teardown"))
        stages = coverage["stages"]
        assert (stages["start"]["first_row"], stages["start"]["last_row"]) == (0, 0)
        assert (stages["compute"]["first_row"], stages["compute"]["last_row"]) == (1, 3)
        assert (stages["persist"]["first_row"], stages["persist"]["last_row"]) == (2, 2)
        assert coverage["rows"] == 5

    def test_an_empty_stream_covers_nothing(self):
        coverage = stage_coverage([])
        assert coverage["complete"] is False
        assert coverage["missing"] == ["start", "compute", "persist", "teardown"]
        assert coverage["rows"] == 0

    def test_callers_can_demand_a_narrower_contract(self):
        coverage = stage_coverage(_rows("start", "compute"), required=("start", "compute"))
        assert coverage["complete"] is True


class TestSealRefusalGate:
    """The gate a phase seal must pass; it is callable without running a smoke."""

    def test_a_covered_stream_passes_and_returns_the_report(self):
        coverage = assert_stage_coverage(
            _rows("start", "compute", "persist", "teardown"), phase="SMOKE_NULL")
        assert coverage["complete"] is True
        assert coverage["rows"] == 4

    def test_a_missing_stage_refuses_with_the_stage_named(self):
        with pytest.raises(ResourceStageCoverageError) as excinfo:
            assert_stage_coverage(_rows("start", "compute", "teardown"),
                                  phase="SMOKE_ALT")
        message = str(excinfo.value)
        assert "SMOKE_ALT" in message
        assert "persist" in message, "the refusal must name the missing stage"

    def test_an_empty_stream_cannot_seal_either(self):
        with pytest.raises(ResourceStageCoverageError):
            assert_stage_coverage([], phase="SMOKE_NULL")


class TestFullLifecycleRequirement:
    """The gate must also be able to demand the post-compute stages.

    These tests pin the contract the wiring step will switch on: once the sampling
    window spans persistence, shard commit, sealing and worker cleanup, a stream that
    misses any of them is refused -- and the refusal names what is missing.  They use
    an explicit ``required`` so the currently wired default stays compatible until the
    runner is reordered.
    """

    REQUIRED = ("start", "compute", "persist", "commit", "seal", "cleanup", "teardown")

    def test_a_stream_without_commit_and_seal_is_refused_by_name(self):
        rows = _rows("start", "compute", "persist", "cleanup", "teardown")
        with pytest.raises(ResourceStageCoverageError) as excinfo:
            assert_stage_coverage(rows, phase="SMOKE_NULL", required=self.REQUIRED)
        message = str(excinfo.value)
        assert "SMOKE_NULL" in message
        assert "commit" in message and "seal" in message

    def test_a_complete_lifecycle_stream_passes_and_reports_ranges(self):
        coverage = assert_stage_coverage(
            _rows(*self.REQUIRED), phase="SMOKE_ALT", required=self.REQUIRED)
        assert coverage["complete"] is True
        assert set(coverage["stages"]) == set(self.REQUIRED)
        assert coverage["rows"] == len(self.REQUIRED)

    def test_a_stream_that_stops_at_persistence_is_refused(self):
        # the pre-R4 state: compute and persistence covered, sealing never observed
        rows = _rows("start", "compute", "persist", "teardown")
        with pytest.raises(ResourceStageCoverageError) as excinfo:
            assert_stage_coverage(rows, phase="SMOKE_NULL", required=self.REQUIRED)
        assert "commit" in str(excinfo.value)


class TestMergeFinalVerdict:
    """Plan A's closing step: a provisional record becomes a final one, once."""

    def _provisional(self) -> dict:
        return {
            "capacity_sampling": {
                "status": "OPEN", "provisional": True, "incomplete": True,
                "incomplete_reasons": ["keep_open: verdict pending"], "breaches": [],
                "raw_samples": None, "peak_commit_ratio": None,
            },
            "run_id": "S04:SMOKE_NULL:w4:r32",
        }

    def test_a_passing_verdict_replaces_the_provisional_record(self):
        verdict = {"status": "PASS", "samples": 12, "peak_commit_ratio": {"num": 1, "den": 2},
                   "incomplete_reasons": [], "breaches": []}
        resources = merge_final_verdict(
            self._provisional(), verdict,
            observed_stages=("start", "compute", "persist", "commit", "seal", "cleanup",
                             "teardown"),
        )
        capacity = resources["capacity_sampling"]
        assert capacity["status"] == "PASS"
        assert capacity["provisional"] is False
        assert capacity["incomplete"] is False
        assert capacity["incomplete_reasons"] == []
        assert resources["stage_coverage"]["not_observed"] == []

    def test_a_non_passing_verdict_stays_incomplete_and_keeps_its_reasons(self):
        verdict = {"status": "INCOMPLETE", "samples": 3,
                   "incomplete_reasons": ["sample_not_ok:SAMPLER_ERROR"], "breaches": []}
        resources = merge_final_verdict(
            self._provisional(), verdict, observed_stages=("start", "compute"),
        )
        capacity = resources["capacity_sampling"]
        assert capacity["status"] == "INCOMPLETE"
        assert capacity["incomplete"] is True
        assert capacity["incomplete_reasons"] == ["sample_not_ok:SAMPLER_ERROR"]

    def test_unobserved_stages_are_stated_not_implied(self):
        verdict = {"status": "PASS", "samples": 1, "incomplete_reasons": [], "breaches": []}
        resources = merge_final_verdict(
            self._provisional(), verdict,
            observed_stages=("start", "compute", "persist", "teardown"),
        )
        assert resources["stage_coverage"]["not_observed"] == ["commit", "seal", "cleanup"]
        assert resources["stage_coverage"]["verdict_recorded_post_seal"] is True

    def test_the_scope_label_is_derived_when_the_whole_lifecycle_was_observed(self):
        verdict = {"status": "PASS", "samples": 5, "incomplete_reasons": [], "breaches": []}
        resources = merge_final_verdict(
            self._provisional(), verdict,
            observed_stages=FULL_LIFECYCLE_STAGES,
        )
        assert resources["capacity_coverage_scope"] == "FULL_SCIENTIFIC_LIFECYCLE"
        assert resources["stage_coverage"]["not_observed"] == []

    def test_the_scope_label_names_what_is_missing_instead_of_claiming_full_coverage(self):
        verdict = {"status": "PASS", "samples": 5, "incomplete_reasons": [], "breaches": []}
        resources = merge_final_verdict(
            self._provisional(), verdict,
            observed_stages=("start", "compute", "persist", "teardown"),
        )
        # never "COMPUTE_ONLY" as an assembly-time leftover, and never a full claim
        assert resources["capacity_coverage_scope"] == "PARTIAL:commit,seal,cleanup"
