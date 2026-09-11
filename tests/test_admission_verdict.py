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
        "measured_wall_milliseconds": 1000,
        "peak_total_rss_bytes": int(1.5 * 1024**3),
        "swap_growth_bytes": 0,
        "disk_free_before_bytes": 500 * 1024**3,
        "evidence_bytes_written": 1024,
    }
    record.update(overrides)
    return record


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
            # A08: the audited NULL record showed a 4 MB swap increase.
            lambda r: r["SMOKE_ALT"]["resources"].update(swap_growth_bytes=4 * 1024 * 1024),
            lambda r: r["SMOKE_ALT"]["resources"].update(peak_total_rss_bytes=25 * 1024**3),
            lambda r: r["SMOKE_ALT"]["resources"].update(
                evidence_bytes_written=10**15, disk_free_before_bytes=10**15
            ),
        ],
        ids=["swap_growth", "peak_rss_over_24_gib", "disk_over_0.8_free"],
    )
    def test_resource_breach_blocks_admission(self, mutate):
        reports = _reports()
        mutate(reports)
        verdict = run_smoke_s03.admission_verdict(reports, TERMINAL, open_runs_zero=True)
        assert verdict["admission_passed"] is False
        assert verdict["checks"]["resource_admission"] is False
        assert verdict["resources"]["SMOKE_ALT"]["passed"] is False

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
        assert limits["peak_total_rss_gib_max"] == 24.0
        assert limits["swap_growth_bytes_max"] == 0
        assert limits["source"].endswith("parallelism_contract.acceptance")

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
