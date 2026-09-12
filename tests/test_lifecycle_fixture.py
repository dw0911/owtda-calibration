"""Audit A11: the lifecycle chain must be walkable, and every broken link refused.

The fixture itself is the implementation (``audit/run_lifecycle_fixture.py``); these
tests are the contract: the happy path admits, and each injected fault is refused
with a reason that names the link that failed.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
AUDIT = REPO / "audit"
if str(AUDIT) not in sys.path:
    sys.path.insert(0, str(AUDIT))

import run_lifecycle_fixture as fixture  # noqa: E402

FAULTS = ("parent_seal", "shard_plan_hash", "index_hash", "terminal_state")
EXPECTED_COUNTS = {
    "data_units": 2,
    "feature_sufficient": 4,
    "evaluations": 8,
    "shard_entries": 12,
}


class TestHappyPath:
    def test_chain_walks_end_to_end(self, tmp_path):
        report = fixture.run_fixture(out_dir=tmp_path)
        assert report["verdict"]["admitted"] is True
        assert report["verdict"]["chain_walked"] is True
        assert report["verdict"]["analysis_bound_to_phase_seal"] is True
        assert report["verdict"]["terminal_state"] == "PHASE_ACTIVATED"
        assert report["counts"] == EXPECTED_COUNTS
        assert (tmp_path / "LIFECYCLE_FIXTURE.json").exists()
        for name in (
            "expected_data_index.json", "expected_feature_index.json",
            "expected_evaluation_index.json", "shard_plan.json",
            "PHASE_SEAL_TEST_PREDICTION.json", "PHASE_SEAL_TEST_ANALYSIS.json",
            "PHASE_STATE_REGISTRY.jsonl",
        ):
            assert (tmp_path / name).exists(), name

    def test_analysis_is_bound_to_the_phase_seal(self, tmp_path):
        report = fixture.run_fixture(out_dir=tmp_path)
        prediction, analysis = report["chain"]
        assert prediction["phase"] == "TEST_PREDICTION"
        assert analysis["phase"] == "TEST_ANALYSIS"
        assert analysis["expected_parent_phase_seal_hash"] == prediction["new_phase_seal_hash"]

    def test_test_identity_domain_is_disjoint_by_construction(self, tmp_path):
        report = fixture.run_fixture(out_dir=tmp_path)
        assert report["project_id"].startswith("TEST-")
        assert fixture._id("logical_data_key", unit=0) != fixture._id(
            "logical_data_key", project_id=fixture.FORMAL_PROJECT_ID, unit=0
        )


class TestBrokenLinksAreRefused:
    @pytest.mark.parametrize("fault", FAULTS)
    def test_fault_is_refused(self, tmp_path, fault):
        with pytest.raises(fixture.FixtureError) as excinfo:
            fixture.run_fixture(out_dir=tmp_path / fault, fault=fault)
        assert str(excinfo.value)  # a reason, not a bare failure

    def test_refusals_name_the_link_that_failed(self, tmp_path):
        reasons = {}
        for fault in FAULTS:
            with pytest.raises(fixture.FixtureError) as excinfo:
                fixture.run_fixture(out_dir=tmp_path / fault, fault=fault)
            reasons[fault] = str(excinfo.value)
        assert "not bound to the prediction seal payload" in reasons["parent_seal"]
        assert "shard plan hash does not recompute" in reasons["shard_plan_hash"]
        assert "index hash does not recompute" in reasons["index_hash"]
        assert "PHASE_ABORTED" in reasons["terminal_state"]

    def test_unknown_fault_is_rejected(self, tmp_path):
        with pytest.raises(fixture.FixtureError):
            fixture.run_fixture(out_dir=tmp_path, fault="not_a_fault")
