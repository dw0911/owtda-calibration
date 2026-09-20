"""Audit A05: admission must be decided by derived conditions, not by a label.

The audited runner returned success based on ``open_runs`` alone, so a run whose
identity closure had failed could still exit as if it had been admitted.  The
verdict is now three separate notions, and **every** condition below is a
mutation-tested gate: flipping any one of them must block admission.
"""

from __future__ import annotations

import copy
import sys
from pathlib import Path
from typing import Any

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

import run_smoke_s03


def _resources(**overrides: Any) -> dict[str, Any]:
    """A benign resource record (audit A08): every claim bound to this run."""
    record = {
        "schema_version": 1,
        "kind": "run_resources_v1",
        "resource_allocation_failures": 0,
        "capacity_sampling": {
            "source": "GetPerformanceInfo",
            "interval_milliseconds": 1000,
            "samples": 600, "missing": 0, "max_gap_milliseconds": 1004,
            "commit_total_peak_bytes": 26_124_267_520,
            "commit_limit_bytes": 41_942_392_832,
            "physical_total_bytes": 34_157_764_608,
            "physical_available_min_bytes": 10_020_118_528,
            "incomplete": False,
        },
        "measured_wall_milliseconds": 1000,
        "peak_total_rss_bytes": int(1.5 * 1024**3),
        # Acceptance basis (machine-wide page-file growth) and a run-level diagnostic.
        "host_swap_growth_bytes": 0,
        "own_commit_charge_growth_bytes": 0,
        "host_swap_measurement_caveat": (
            "machine-wide page file usage: moves with unrelated host activity"
        ),
        "disk_free_before_bytes": 500 * 1024**3,
        "evidence_bytes_written": 1024,
    }
    record.update(overrides)
    return bind_test_raw(record, _RESOURCE_DIR)


def _report(phase: str = "SMOKE_NULL") -> dict[str, Any]:
    return {
        "phase": phase,
        "counts_match_contract": True,
        "unexplained_errors": 0,
        "missing_required_fields": 0,
        "identity_closure": {"passed": True},
        "formal_id_leak_check": {"passed": True},
        "resources": _resources(),
    }


def _reports() -> dict[str, dict[str, Any]]:
    return {"SMOKE_NULL": _report("SMOKE_NULL"), "SMOKE_ALT": _report("SMOKE_ALT")}


TERMINAL = {"S03:SMOKE_NULL:w8:r32": "RUN_SEALED", "S03:SMOKE_ALT:w8:r32": "RUN_SEALED"}


class TestLayeredVerdict:
    def test_all_conditions_pass(self):
        verdict = run_smoke_s03.admission_verdict(
            _reports(), TERMINAL, open_runs_zero=True
        )
        assert verdict["admission_passed"] is True
        assert verdict["run_terminated"] is True
        assert verdict["evidence_sealed"] is True
        assert set(verdict["checks"]) == {
            "counts_match_contract", "no_unexplained_errors",
            "no_missing_required_fields", "identity_closure",
            "formal_id_leak_clean", "open_runs_zero", "every_run_sealed",
            "resource_admission",
        }
        assert all(verdict["resources"][phase]["passed"] for phase in ("SMOKE_NULL", "SMOKE_ALT"))

    def test_terminated_is_always_reported(self):
        """The process finished even when nothing else holds."""
        verdict = run_smoke_s03.admission_verdict(
            {"SMOKE_NULL": {**_report(), "unexplained_errors": 3}},
            TERMINAL, open_runs_zero=True,
        )
        assert verdict["run_terminated"] is True
        assert verdict["evidence_sealed"] is True
        assert verdict["admission_passed"] is False

    @pytest.mark.parametrize(
        "mutate,expected_key",
        [
            (lambda r: r["SMOKE_ALT"].update(counts_match_contract=False),
             "counts_match_contract"),
            (lambda r: r["SMOKE_ALT"].update(unexplained_errors=1),
             "no_unexplained_errors"),
            (lambda r: r["SMOKE_ALT"].update(missing_required_fields=1),
             "no_missing_required_fields"),
            (lambda r: r["SMOKE_ALT"].update(identity_closure={"passed": False}),
             "identity_closure"),
            (lambda r: r["SMOKE_ALT"].update(formal_id_leak_check={"passed": False}),
             "formal_id_leak_clean"),
        ],
    )
    def test_each_failing_condition_blocks_admission(self, mutate, expected_key):
        reports = _reports()
        mutate(reports)
        verdict = run_smoke_s03.admission_verdict(reports, TERMINAL, open_runs_zero=True)
        assert verdict["admission_passed"] is False
        assert verdict["checks"][expected_key] is False
        assert expected_key in [k for k, ok in verdict["checks"].items() if not ok]

    @pytest.mark.parametrize(
        "mutate",
        [
            # V2: allocation failures are a hard condition; page-file growth is not.
            lambda r: r["SMOKE_ALT"]["resources"].update(resource_allocation_failures=1),
            lambda r: r["SMOKE_ALT"]["resources"].update(peak_total_rss_bytes=25 * 1024**3),
            lambda r: r["SMOKE_ALT"]["resources"].update(
                evidence_bytes_written=10**15, disk_free_before_bytes=10**15
            ),
        ],
        ids=["allocation_failures", "peak_rss_over_24_gib", "disk_over_0.8_free"],
    )
    def test_resource_breach_blocks_admission(self, mutate):
        reports = _reports()
        mutate(reports)
        verdict = run_smoke_s03.admission_verdict(reports, TERMINAL, open_runs_zero=True)
        assert verdict["admission_passed"] is False
        assert verdict["checks"]["resource_admission"] is False
        assert verdict["resources"]["SMOKE_ALT"]["passed"] is False

    def test_commit_charge_alone_does_not_block_admission(self):
        """AM_RESOURCE_MEASUREMENT_SEMANTICS: commit charge is not paging.

        The S04 run recorded 8.5 GiB of private commit charge while peak RSS was
        1.09 GiB and the machine-wide page file did not move at all.  Only the
        declared condition (machine-wide growth) may fail a run.
        """
        reports = _reports()
        reports["SMOKE_ALT"]["resources"].update(
            own_commit_charge_growth_bytes=9 * 1024**3
        )
        verdict = run_smoke_s03.admission_verdict(reports, TERMINAL, open_runs_zero=True)
        assert verdict["admission_passed"] is True
        diag = verdict["resources"]["SMOKE_ALT"]["diagnostics"]
        assert diag["own_commit_charge_growth_bytes"] == 9 * 1024**3
        assert "diagnostic only" in diag["note"]

    def test_missing_resource_evidence_blocks_admission(self):
        """Fail closed: no resource record is not the same as a clean record."""
        reports = _reports()
        reports["SMOKE_ALT"].pop("resources")
        verdict = run_smoke_s03.admission_verdict(reports, TERMINAL, open_runs_zero=True)
        assert verdict["admission_passed"] is False
        assert verdict["checks"]["resource_admission"] is False
        assert verdict["resources"]["SMOKE_ALT"]["checks"]["resources_recorded"] is False

    def test_limits_come_from_the_frozen_compute_spec(self):
        """The thresholds are quoted, not restated in code."""
        verdict = run_smoke_s03.admission_verdict(_reports(), TERMINAL, open_runs_zero=True)
        limits = verdict["resources"]["SMOKE_NULL"]["limits"]
        assert limits["peak_total_rss_gib_max"] == 24
        assert limits["host_commit_fraction_max"] == 0.80
        assert limits["source"].endswith("RESOURCE_POLICY_V2.json")
        assert verdict["resources"]["SMOKE_NULL"]["resource_policy_id"] == (
            "AM_RESOURCE_CAPACITY_V2"
        )

    def test_open_runs_block_admission_and_sealing(self):
        verdict = run_smoke_s03.admission_verdict(
            _reports(), TERMINAL, open_runs_zero=False
        )
        assert verdict["admission_passed"] is False
        assert verdict["checks"]["open_runs_zero"] is False

    @pytest.mark.parametrize("state", ["RUN_OPEN", "FAILED", "BOGUS", "", "SEALED"])
    def test_terminal_state_must_be_exactly_run_sealed(self, state):
        """The old check was `state in (...) or bool(state)`: BOGUS passed."""
        terminal = dict(TERMINAL)
        terminal["S03:SMOKE_ALT:w8:r32"] = state
        verdict = run_smoke_s03.admission_verdict(
            _reports(), terminal, open_runs_zero=True
        )
        assert verdict["admission_passed"] is False
        assert verdict["evidence_sealed"] is False

    def test_empty_registry_is_not_sealed(self):
        verdict = run_smoke_s03.admission_verdict(
            _reports(), {}, open_runs_zero=True
        )
        assert verdict["evidence_sealed"] is False
        assert verdict["admission_passed"] is False

    def test_verdict_does_not_mutate_its_inputs(self):
        reports = _reports()
        before = copy.deepcopy(reports)
        run_smoke_s03.admission_verdict(reports, TERMINAL, open_runs_zero=True)
        assert reports == before
