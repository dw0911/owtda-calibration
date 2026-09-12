"""The shared execution entry: execution roots, mode admission, one path (§4.1)."""

from __future__ import annotations

import json
import threading
from concurrent import futures

import pytest

from owtda_cal import chains
from owtda_cal.execution import (
    EXECUTION_SUBDIRS,
    MODES,
    ExecutionError,
    check_mode_admission,
    create_execution_root,
    execute_plan,
)


def _plan(mode: str = "TEST", n: int = 4) -> dict:
    return {
        "plan_id": "TEST-PLAN",
        "identity_domain": {"TEST": "TEST", "SMOKE": "SMOKE"}.get(mode, "FORMAL"),
        "phase": "TEST_PREDICTION",
        "units": [{"unit_id": f"u{i}", "seed": 1000 + i} for i in range(n)],
    }


class _Monitor:
    def __init__(self) -> None:
        self.stop_requested = threading.Event()
        self.policy_sha256 = "a" * 64
        self.raw_path = None

    def verdict(self) -> dict:
        return {"status": "PASS", "samples": 1, "breaches": [], "issues": []}


class TestExecutionRoot:
    def test_the_root_layout_is_created(self, tmp_path):
        root = create_execution_root(tmp_path, "EXEC-1")
        for name in EXECUTION_SUBDIRS:
            assert (root.path / name).is_dir(), name
        assert root.resumed is False
        assert root.execution_id == "EXEC-1"

    def test_an_existing_root_is_refused_without_resume(self, tmp_path):
        create_execution_root(tmp_path, "EXEC-1")
        with pytest.raises(ExecutionError, match="already exists"):
            create_execution_root(tmp_path, "EXEC-1")

    def test_resume_attaches_to_an_existing_root(self, tmp_path):
        create_execution_root(tmp_path, "EXEC-1")
        again = create_execution_root(tmp_path, "EXEC-1", resume=True)
        assert again.resumed is True

    def test_resume_on_a_missing_root_is_refused(self, tmp_path):
        with pytest.raises(ExecutionError, match="does not exist"):
            create_execution_root(tmp_path, "EXEC-NOPE", resume=True)

    def test_an_empty_execution_id_is_refused(self, tmp_path):
        with pytest.raises(ExecutionError):
            create_execution_root(tmp_path, "   ")


class TestModeAdmission:
    def test_test_requires_the_test_domains(self):
        plan = _plan("TEST")
        assert check_mode_admission("TEST", plan=plan,
                                    test_seed_domain=True, test_id_domain=True)["admitted"]
        denied = check_mode_admission("TEST", plan=plan, test_seed_domain=True)
        assert denied["admitted"] is False
        assert "test_id_domain" in denied["reasons"][0]

    def test_smoke_forbids_size_power_and_ranking(self):
        plan = _plan("SMOKE")
        plan["outputs"] = ["power"]
        denied = check_mode_admission("SMOKE", plan=plan, frozen_engineering_plan=True,
                                      replicates_32=True)
        assert denied["admitted"] is False
        assert any("power" in r for r in denied["reasons"])

    def test_formal_h0_needs_its_certificate_and_bindings(self):
        plan = _plan("FORMAL_H0")
        plan["identity_domain"] = "FORMAL"
        denied = check_mode_admission("FORMAL_H0", plan=plan)
        assert {r.split("'")[1] for r in denied["reasons"]} == {
            "g4_h0_certificate", "expected_indices_bound", "seed_registry_bound"
        }
        allowed = check_mode_admission(
            "FORMAL_H0", plan=plan, g4_h0_certificate=True,
            expected_indices_bound=True, seed_registry_bound=True,
        )
        assert allowed["admitted"] is True

    def test_formal_h1_needs_the_null_dependency_and_authorization(self):
        plan = _plan("FORMAL_H1")
        denied = check_mode_admission("FORMAL_H1", plan=plan, null_evidence_dependency=True)
        assert denied["admitted"] is False
        assert "independent_authorization" in denied["reasons"][0]

    def test_the_plan_domain_must_match_the_mode(self):
        plan = _plan("TEST")
        plan["identity_domain"] = "FORMAL"
        denied = check_mode_admission("TEST", plan=plan, test_seed_domain=True,
                                      test_id_domain=True)
        assert denied["admitted"] is False

    def test_test_rejects_a_plan_that_is_not_micro(self):
        plan = _plan("TEST", n=65)
        denied = check_mode_admission("TEST", plan=plan, test_seed_domain=True,
                                      test_id_domain=True)
        assert denied["admitted"] is False
        assert "at most" in denied["reasons"][0]

    def test_an_unknown_mode_is_a_programming_error(self):
        with pytest.raises(ExecutionError, match="unknown mode"):
            check_mode_admission("FORMAL", plan=_plan())


class TestExecutePlan:
    def test_a_test_plan_runs_end_to_end(self, tmp_path):
        plan = _plan("TEST", n=6)
        monitor = _Monitor()
        with futures.ThreadPoolExecutor(max_workers=4) as pool:
            record = execute_plan(
                plan, mode="TEST", manifests={"scientist": "test"},
                evidence_root=tmp_path, monitor=monitor, execution_id="EXEC-T1",
                submit=lambda unit, index: pool.submit(lambda: dict(unit, done=True)),
                window_size=2, test_seed_domain=True, test_id_domain=True,
            )
        assert record["terminal_state"] == "COMPLETE"
        assert record["completed"] == 6
        assert record["emitted_unit_ids"] == [f"u{i}" for i in range(6)]
        assert record["produces_formal_scientific_summary"] is False
        # the frozen plan and its hash are in the execution root
        root = tmp_path / "executions" / "EXEC-T1"
        assert (root / "plan" / "plan.json").is_file()
        assert (root / "plan" / "plan.sha256").read_text().strip() == record["plan_sha256"]
        assert (root / "plan" / "manifests.json").is_file()
        assert (root / "logs" / "execution.json").is_file()
        assert (root / "resources" / "capacity.json").is_file()

    def test_the_dispatch_events_form_a_schema_two_chain(self, tmp_path):
        plan = _plan("TEST", n=3)
        with futures.ThreadPoolExecutor(max_workers=2) as pool:
            execute_plan(
                plan, mode="TEST", evidence_root=tmp_path, execution_id="EXEC-T2",
                submit=lambda unit, index: pool.submit(lambda: dict(unit)),
                window_size=2, test_seed_domain=True, test_id_domain=True,
            )
        events_path = tmp_path / "executions" / "EXEC-T2" / "events" / "dispatch.jsonl"
        events = [json.loads(x) for x in
                  events_path.read_text(encoding="utf-8").splitlines() if x.strip()]
        assert events[0]["event_type"] == "EXECUTION_STARTED"
        assert [e["event_type"] for e in events][-1] == "EXECUTION_FINISHED"
        assert [e["seq"] for e in events] == list(range(len(events)))
        chains.assert_chain_valid(str(events_path), hash_field="event_hash",
                                  parent_field="prev_event_hash")

    def test_a_refused_mode_does_not_create_an_execution_root(self, tmp_path):
        plan = _plan("FORMAL_H0")
        with futures.ThreadPoolExecutor(max_workers=1) as pool:
            record = execute_plan(
                plan, mode="FORMAL_H0", evidence_root=tmp_path, execution_id="EXEC-T3",
                submit=lambda unit, index: pool.submit(lambda: dict(unit)),
            )
        assert record["terminal_state"] == "REFUSED"
        assert record["execution_root"] is None
        assert not (tmp_path / "executions" / "EXEC-T3").exists()

    def test_duplicate_unit_ids_are_refused(self, tmp_path):
        plan = _plan("TEST", n=2)
        plan["units"][1]["unit_id"] = plan["units"][0]["unit_id"]
        with futures.ThreadPoolExecutor(max_workers=1) as pool, \
                pytest.raises(ExecutionError, match="duplicate unit_id"):
            execute_plan(
                plan, mode="TEST", evidence_root=tmp_path, execution_id="EXEC-T4",
                submit=lambda unit, index: pool.submit(lambda: dict(unit)),
                test_seed_domain=True, test_id_domain=True,
            )

    def test_a_latched_stop_is_recorded_in_the_execution_record(self, tmp_path):
        plan = _plan("TEST", n=20)
        monitor = _Monitor()
        monitor.stop_requested.set()
        with futures.ThreadPoolExecutor(max_workers=2) as pool:
            record = execute_plan(
                plan, mode="TEST", evidence_root=tmp_path, monitor=monitor,
                execution_id="EXEC-T5",
                submit=lambda unit, index: pool.submit(lambda: dict(unit)),
                window_size=2, test_seed_domain=True, test_id_domain=True,
            )
        assert record["stop_latched"] is True
        assert record["terminal_state"] == "INCOMPLETE"
        assert record["completed"] + record["failed"] + record["cancelled"] == 20

    def test_modes_are_the_four_registered_domains(self):
        assert set(MODES) == {"TEST", "SMOKE", "FORMAL_H0", "FORMAL_H1"}
