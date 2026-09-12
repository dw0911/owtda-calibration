"""Audit A11: the lifecycle chain must be walkable, and every broken link refused.

The fixture itself is the implementation (``audit/run_lifecycle_fixture.py``); these
tests are the contract: the happy path admits, and each injected fault is refused
with a reason that names the link that failed.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

from owtda_cal import shardio

REPO = Path(__file__).resolve().parents[1]
AUDIT = REPO / "audit"
if str(AUDIT) not in sys.path:
    sys.path.insert(0, str(AUDIT))

import run_lifecycle_fixture as fixture

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


class TestRealLifecycle:
    """Re-audit 2026-09-13: 8 expected ids, 4 real rows, placeholder shards.

    The task pack requires one production entry whose TEST run really produces
    2 data tasks x 2 representations x 2 calibrations = 8 evaluations, with
    ``E_expected = E_actual = union(E_committed)`` and ``count(e) = 1``.
    """

    def test_eight_real_evaluations_are_committed(self, tmp_path):
        report = fixture.run_fixture(out_dir=tmp_path)
        assert report["counts"] == EXPECTED_COUNTS
        execution = report["execution"]
        assert execution["computation"]["rows"] == 8
        assert len(execution["shards"]["committed_shards"]) == 2  # one per data task
        ledger = json.loads(
            (tmp_path / "evaluation_ledger.jsonl").read_text(encoding="utf-8").splitlines()[0]
        )
        assert "observed_statistic" in ledger and "p_value" in ledger
        assert "row" not in ledger  # the old placeholder row is gone

    def test_expected_actual_and_committed_are_the_same_set(self, tmp_path):
        report = fixture.run_fixture(out_dir=tmp_path)
        sets = report["set_equality"]
        assert sets["identical"] is True
        assert sets["expected"] == sets["actual"] == sets["committed"]
        assert len(sets["committed"]) == 8
        assert len(set(sets["committed"])) == 8  # count(e) == 1

    def test_the_ledger_role_and_the_expected_role_are_distinct(self, tmp_path):
        report = fixture.run_fixture(out_dir=tmp_path)
        hashes = report["hashes"]
        assert hashes["roles_are_distinct"] is True
        assert hashes["active_ledger_content_hash"] != hashes["expected_evaluation_index_hash"]

    def test_the_analysis_reads_the_actual_rows(self, tmp_path):
        report = fixture.run_fixture(out_dir=tmp_path)
        output = json.loads((tmp_path / "analysis_output.json").read_text(encoding="utf-8"))
        assert output["rows"] == 8
        assert output["evaluation_ids"] == report["set_equality"]["committed"]
        assert output["duplicate_evaluation_ids"] == []
        assert output["ledger_sha256"] == report["hashes"]["active_ledger_content_hash"]
        analysis_input = json.loads(
            (tmp_path / "analysis_input.json").read_text(encoding="utf-8")
        )
        # the input is frozen before the output: it carries the phase seals
        assert analysis_input["phase_seal_hashes"] == sorted({
            report["hashes"]["prediction_phase_seal_hash"],
            report["hashes"]["analysis_phase_seal_hash"],
        })

    def test_negative_probes_do_not_pollute_the_active_ledger(self, tmp_path):
        report = fixture.run_fixture(out_dir=tmp_path)
        execution = report["execution"]
        assert execution["shards"]["registry_records"] == 2  # the two real shards
        assert execution["shards"]["deleted_final_blocked"] is True
        assert execution["shards"]["orphan_refused"] is True
        assert execution["shards"]["orphan_committed_by_repair"] is True
        # both committed directories survive in the positive root
        runs = tmp_path / "runs" / fixture.RUN_INSTANCE_ID
        finals = sorted(p.name for p in runs.glob("*.final"))
        assert len(finals) == 2
        for name in finals:
            directory = runs / name
            for required in shardio.COMMITTED_FILES:
                assert (directory / required).is_file()
        # the destructive probes are isolated under their own root
        assert (tmp_path / "negative").is_dir()


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
