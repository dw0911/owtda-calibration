"""AM_PARALLELISM_DECOUPLING: parallelism is a contract, not a frozen value.

Three properties are pinned here:

1. the hashed ``compute_spec`` contains **no worker count** — it freezes the
   invariance requirement and the acceptance conditions instead;
2. the realised parallelism is recorded per run (declared in SMOKE_CONFIG, used in
   the run registry / provenance), and the declared range is inside the contract;
3. a ``freeze_id`` change can no longer be silently reused by the REAL
   disposition chain — the drift must be decided explicitly and the tip must end
   up anchored to the current freeze.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

import pytest

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "src"))
sys.path.insert(0, str(REPO / "audit"))

import build_freeze
import build_run_admission

from owtda_cal import chains, disposition

GOV = REPO / "governance"


def _all_keys(node: Any) -> set[str]:
    """Every dict key in a nested structure.

    Substring tests are not usable here: ``cache_key_fields`` contains the literal
    ``window_start``, which contains ``w_star``.
    """
    if isinstance(node, dict):
        keys = set(node)
        for value in node.values():
            keys |= _all_keys(value)
        return keys
    if isinstance(node, (list, tuple)):
        return set().union(*(_all_keys(v) for v in node)) if node else set()
    return set()


def _all_ints(node: Any) -> set[int]:
    if isinstance(node, bool):
        return set()
    if isinstance(node, int):
        return {node}
    if isinstance(node, dict):
        return set().union(*(_all_ints(v) for v in node.values())) if node else set()
    if isinstance(node, (list, tuple)):
        return set().union(*(_all_ints(v) for v in node)) if node else set()
    return set()


class TestContractShape:
    def test_spec_has_a_parallelism_contract_and_no_w_star(self):
        spec = build_freeze._compute_spec()
        assert "parallelism_contract" in spec
        assert "w_star" not in _all_keys(spec)
        contract = spec["parallelism_contract"]
        assert contract["invariance_requirement"] == "bitwise_identical_payload"
        assert contract["workers_used_must_be_recorded_per_run"] is True
        assert contract["workers_range"] == "1..cpu_count"
        assert set(contract["thread_env"].values()) == {"1"}

    def test_acceptance_conditions_are_frozen(self):
        contract = build_freeze._compute_spec()["parallelism_contract"]
        assert contract["acceptance"]["peak_total_rss_gib_max"] == "24"
        assert contract["acceptance"]["swap_growth_bytes_max"] == 0
        assert contract["acceptance"]["unexplained_errors_max"] == 0

    def test_no_declared_worker_count_is_frozen_in_the_hashed_spec(self):
        """The whole point: a worker count must not be able to move identity."""
        declared = build_run_admission.SMOKE_CONFIG["default_workers"]
        assert declared not in _all_ints(build_freeze._compute_spec())

    def test_environment_lock_no_longer_carries_a_worker_count(self):
        text = json.dumps(build_freeze._compute_freeze())
        assert "w_star" not in text
        assert "default_workers" not in text

    def test_verdict_and_protocol_are_evidence_not_identity(self):
        evidence = build_freeze._parallelism_evidence()
        assert "parallelism_evidence" not in json.dumps(build_freeze._compute_spec())
        assert evidence["confirmation_protocol"].endswith(
            "WSTAR_CONFIRMATION_PROTOCOL.json"
        )
        assert evidence["confirmation_protocol_sha256"]


class TestRunLevelRecording:
    def test_smoke_config_declares_a_worker_count_in_range(self):
        config = build_run_admission.SMOKE_CONFIG
        assert isinstance(config["default_workers"], int)
        assert 1 <= config["default_workers"]

    def test_smoke_config_and_manifest_artifact_agree(self):
        """Artifact-level agreement (only true once the freeze has been rebuilt)."""
        config = json.loads((GOV / "SMOKE_CONFIG_v1.json").read_text(encoding="utf-8"))
        spec = json.loads((GOV / "COMPUTE_SPEC_v1.json").read_text(encoding="utf-8"))
        assert config["default_workers"] == build_run_admission.SMOKE_CONFIG["default_workers"]
        assert spec["parallelism_contract"] == build_freeze._compute_spec()[
            "parallelism_contract"
        ]
        assert "w_star" not in _all_keys(spec)
        manifest = json.loads((GOV / "FREEZE_MANIFEST.json").read_text(encoding="utf-8"))
        assert manifest["parallelism_evidence"]["contract"] == (
            "COMPUTE_SPEC.parallelism_contract"
        )

    def test_run_registry_records_workers_used(self):
        text = (REPO / "audit/run_registry.py").read_text(encoding="utf-8")
        assert '"workers_used": workers_used' in text
        assert '"w_star"' not in text


class TestRealDispositionAnchoring:
    def test_decision_create_when_chain_is_empty(self):
        assert build_freeze.real_disposition_decision([], "f" * 64) == "CREATE"

    def test_decision_reuse_when_anchored(self):
        events = [{"freeze_id": "a" * 64}]
        assert build_freeze.real_disposition_decision(events, "a" * 64) == "REUSE"

    def test_decision_reanchor_on_freeze_id_drift(self):
        """The defect: validate_chain alone cannot see this drift."""
        events = [{"freeze_id": "a" * 64}]
        assert build_freeze.real_disposition_decision(events, "b" * 64) == "REANCHOR"

    def test_chain_level_drift_is_invisible_without_the_explicit_decision(self, tmp_path: Path):
        """Documents *why* the decision is needed: each event is self-consistent."""
        path = tmp_path / "REAL_DISPOSITION.jsonl"
        evidence = build_freeze.REAL_RC_EVIDENCE
        reason = disposition.reason_object(
            reason_code="TASK_GATE_MIN_TASKS_NOT_MET", **evidence
        )
        r_hash = disposition.reason_object_hash(reason)
        old_fid, new_fid = "a" * 64, "b" * 64
        first = disposition.event(
            project_id="p", protocol_id="q", freeze_id=old_fid,
            evidence_generation_id="G01", disposition_status="REAL_OMITTED_BY_DATA_GATE",
            disposition_stage="REAL_DATA_FROZEN", reason_code="TASK_GATE_MIN_TASKS_NOT_MET",
            reason_object_hash_value=r_hash, task_index_seal_hash=None,
            truth_unsealed=False,
            prev_real_disposition_event_hash=disposition.genesis_hash(
                project_id="p", protocol_id="q", freeze_id=old_fid,
                evidence_generation_id="G01",
            ),
        )
        chains.append_cas(str(path), first, expected_tip=None, hash_field="disposition_hash")
        # A chain anchored to the *old* freeze still validates cleanly ...
        assert disposition.validate_chain(path)["event_count"] == 1
        # ... so the drift has to be decided explicitly and re-anchored by an event.
        assert build_freeze.real_disposition_decision(
            disposition.read_events(path), new_fid
        ) == "REANCHOR"
        prev = disposition.read_events(path)[-1]["disposition_hash"]
        second = disposition.event(
            project_id="p", protocol_id="q", freeze_id=new_fid,
            evidence_generation_id="G01", disposition_status="REAL_OMITTED_BY_DATA_GATE",
            disposition_stage="REAL_DATA_FROZEN", reason_code="TASK_GATE_MIN_TASKS_NOT_MET",
            reason_object_hash_value=r_hash, task_index_seal_hash=None,
            truth_unsealed=False, prev_real_disposition_event_hash=prev,
        )
        chains.append_cas(str(path), second, expected_tip=prev, hash_field="disposition_hash")
        info = disposition.validate_chain(path)
        assert info["event_count"] == 2
        assert disposition.read_events(path)[-1]["freeze_id"] == new_fid
        assert build_freeze.real_disposition_decision(
            disposition.read_events(path), new_fid
        ) == "REUSE"

    def test_manifest_records_the_decision(self):
        manifest = json.loads((GOV / "FREEZE_MANIFEST.json").read_text(encoding="utf-8"))
        block = manifest["real_disposition"]
        assert block["decision"] in {"CREATE", "REUSE", "REANCHOR"}
        assert block["freeze_id_anchored"] is True

    @pytest.mark.parametrize(
        "existing,expected",
        [(None, "CREATE"), ("same", "REUSE"), ("other", "REANCHOR")],
    )
    def test_decision_is_exhaustive(self, existing: str | None, expected: str):
        fid = "a" * 64
        events = [] if existing is None else [
            {"freeze_id": fid if existing == "same" else "b" * 64}
        ]
        assert build_freeze.real_disposition_decision(events, fid) == expected
