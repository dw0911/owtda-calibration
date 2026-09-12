"""TEST-identity lifecycle fixture (audit A11, verdict phase four).

Walks the *formal* primitives end to end on a tiny TEST scope::

    expected indexes -> shard plan -> PHASE_SEAL -> analysis seal

The analysis seal is a second phase seal whose ``parent_phase_seal_hash`` is the
first one, so "the analysis is bound to the phase it publishes" is a checked link
rather than a convention.  The chain is then read back and re-verified.

It proves that the chain is walkable **and that a broken link is refused**: every
step takes an injectable fault (``--fault``), and a fault must raise.  The fixture
produces no scientific result and touches no formal identity: every id is derived
under a TEST project id, and the same logical fields under the formal project id
are asserted to give a different id.

Usage::

    python audit/run_lifecycle_fixture.py --out <dir outside the repo> [--fault ...]
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "src"))

from owtda_cal import chains, indexes
from owtda_cal.canonical import canonical_json_bytes
from owtda_cal.identity import H

PROJECT_ID = "TEST-OWTDA-CAL-FIXTURE"
FORMAL_PROJECT_ID = "owtda-cal-r1"
PROTOCOL_ID = "OWTDA-CAL-R1-PROTOCOL-v1.0"
FREEZE_ID = "0" * 64
EVIDENCE_GENERATION_ID = "TEST-G01"
PHASE_PREDICTION = "TEST_PREDICTION"
PHASE_ANALYSIS = "TEST_ANALYSIS"
RUN_INSTANCE_ID = "TEST:lifecycle:01"
PHASE_STATE_FILE = "PHASE_STATE_REGISTRY.jsonl"
PHASE_STATE_HASH_FIELD = "phase_state_event_hash"
FAULTS = ("parent_seal", "shard_plan_hash", "index_hash", "terminal_state")


class FixtureError(ValueError):
    """The fixture chain does not close."""


def _id(kind: str, *, project_id: str = PROJECT_ID, **fields: Any) -> str:
    return H(
        kind,
        project_id=project_id,
        protocol_id=PROTOCOL_ID,
        freeze_id=FREEZE_ID,
        evidence_generation_id=EVIDENCE_GENERATION_ID,
        **fields,
    )


def build_scope(*, units: int = 2, features: int = 2, methods: int = 2) -> dict[str, list[dict]]:
    """A tiny TEST scope: every id is domain-separated by the TEST project id."""
    data: list[dict] = []
    feature: list[dict] = []
    evaluation: list[dict] = []
    for u in range(units):
        logical_data_key = _id("logical_data_key", unit=u)
        data_unit_id = _id("data_unit", unit=u)
        data.append({"logical_data_key": logical_data_key, "data_unit_id": data_unit_id})
        for f in range(features):
            logical_feature_key = _id("logical_feature_key", unit=u, feature=f)
            feature_sufficient_id = _id("feature_sufficient", unit=u, feature=f)
            feature.append({
                "logical_data_key": logical_data_key,
                "logical_feature_key": logical_feature_key,
                "data_unit_id": data_unit_id,
                "feature_sufficient_id": feature_sufficient_id,
            })
            for m in range(methods):
                evaluation.append({
                    "logical_data_key": logical_data_key,
                    "logical_feature_key": logical_feature_key,
                    "logical_evaluation_key": _id(
                        "logical_evaluation_key", unit=u, feature=f, method=m
                    ),
                    "data_unit_id": data_unit_id,
                    "feature_sufficient_id": feature_sufficient_id,
                    "evaluation_id": _id("evaluation", unit=u, feature=f, method=m),
                })
    return {"data": data, "feature": feature, "evaluation": evaluation}


def _seal_fields(
    *,
    phase: str,
    parent_phase_seal_hash: str | None,
    data_hash: str,
    feature_hash: str,
    evaluation_hash: str,
    ledger: bytes,
    feature_ledger: bytes,
    evaluation_rows: list[dict],
    feature_rows: list[dict],
    n_logical_keys: int,
    shard_hash: str,
) -> dict[str, Any]:
    return {
        "phase": phase,
        "evidence_generation_id": EVIDENCE_GENERATION_ID,
        "scope_design_hash": shard_hash,
        "parent_phase_seal_hash": parent_phase_seal_hash,
        "validity_registry_head_hash": hashlib.sha256(ledger).hexdigest(),
        "data_replacement_key_set_hash": hashlib.sha256(b"test-no-replacement").hexdigest(),
        "feature_replacement_key_set_hash": hashlib.sha256(b"test-no-replacement").hexdigest(),
        "evaluation_replacement_key_set_hash": hashlib.sha256(b"test-no-replacement").hexdigest(),
        "replacement_source_run_seal_hashes": [],
        "active_component_manifest_hash": shard_hash,
        "active_data_index_hash": data_hash,
        "active_feature_index_hash": feature_hash,
        "active_evaluation_index_hash": evaluation_hash,
        "active_ledger_content_hash": hashlib.sha256(ledger).hexdigest(),
        "active_feature_ledger_content_hash": hashlib.sha256(feature_ledger).hexdigest(),
        "active_feature_row_count": len(feature_rows),
        "logical_key_count": n_logical_keys,
        "evaluation_id_set_hash": indexes.id_set_hash(
            "evaluation_id_set", [r["evaluation_id"] for r in evaluation_rows]
        ),
        "feature_sufficient_id_set_hash": indexes.id_set_hash(
            "feature_sufficient_id_set", [r["feature_sufficient_id"] for r in feature_rows]
        ),
        "ordered_source_run_seal_hashes": [],
        "ordered_upstream_artifact_refs": [],
    }


def run_fixture(*, out_dir: Path, fault: str | None = None) -> dict[str, Any]:
    if fault is not None and fault not in FAULTS:
        raise FixtureError(f"unknown fault {fault!r}; expected one of {FAULTS}")
    out_dir.mkdir(parents=True, exist_ok=True)

    scope = build_scope()
    data_rows = indexes.expected_data_index_rows(scope["data"])
    feature_rows = indexes.expected_feature_index_rows(scope["feature"])
    evaluation_rows = indexes.expected_evaluation_index_rows(scope["evaluation"])
    indexes.validate_index_consistency(data_rows, feature_rows, evaluation_rows)

    data_hash = indexes.index_content_hash(data_rows)
    feature_hash = indexes.index_content_hash(feature_rows)
    evaluation_hash = indexes.index_content_hash(evaluation_rows)
    if fault == "index_hash":
        evaluation_hash = "0" * 64

    entries = [
        {"row_type": indexes.ROW_TYPE_FEATURE, "row_id": r["feature_sufficient_id"],
         "partition": "TEST-P0", "bucket": 0}
        for r in feature_rows
    ] + [
        {"row_type": indexes.ROW_TYPE_EVALUATION, "row_id": r["evaluation_id"],
         "partition": "TEST-P0", "bucket": 0}
        for r in evaluation_rows
    ]
    plan = indexes.build_shard_plan(
        run_instance_id=RUN_INSTANCE_ID, phase=PHASE_PREDICTION,
        expected_data_index_hash=data_hash, expected_index_hash=evaluation_hash,
        expected_feature_index_hash=feature_hash, entries=entries,
    )
    shard_hash = indexes.shard_plan_hash(plan)
    if fault == "shard_plan_hash":
        shard_hash = "1" * 64

    ledger = b"".join(canonical_json_bytes(r) + b"\n" for r in evaluation_rows)
    feature_ledger = b"".join(canonical_json_bytes(r) + b"\n" for r in feature_rows)

    prediction_seal = indexes.build_phase_seal(**_seal_fields(
        phase=PHASE_PREDICTION, parent_phase_seal_hash=None, data_hash=data_hash,
        feature_hash=feature_hash, evaluation_hash=evaluation_hash, ledger=ledger,
        feature_ledger=feature_ledger, evaluation_rows=evaluation_rows,
        feature_rows=feature_rows, n_logical_keys=len(data_rows), shard_hash=shard_hash,
    ))
    prediction_seal_hash = indexes.phase_seal_hash(prediction_seal)

    parent = prediction_seal_hash if fault != "parent_seal" else "2" * 64
    analysis_seal = indexes.build_phase_seal(**_seal_fields(
        phase=PHASE_ANALYSIS, parent_phase_seal_hash=parent, data_hash=data_hash,
        feature_hash=feature_hash, evaluation_hash=evaluation_hash, ledger=ledger,
        feature_ledger=feature_ledger, evaluation_rows=evaluation_rows,
        feature_rows=feature_rows, n_logical_keys=len(data_rows), shard_hash=shard_hash,
    ))
    analysis_seal_hash = indexes.phase_seal_hash(analysis_seal)

    registry = out_dir / PHASE_STATE_FILE
    registry.unlink(missing_ok=True)

    # Persist everything the verification step must be able to re-derive by itself.
    def _write(name: str, obj: Any) -> None:
        (out_dir / name).write_text(
            json.dumps(obj, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )

    _write("expected_data_index.json", data_rows)
    _write("expected_feature_index.json", feature_rows)
    _write("expected_evaluation_index.json", evaluation_rows)
    _write("shard_plan.json", plan)
    _write("PHASE_SEAL_TEST_PREDICTION.json", prediction_seal)
    _write("PHASE_SEAL_TEST_ANALYSIS.json", analysis_seal)
    for phase, seal_hash, expected_parent in (
        (PHASE_PREDICTION, prediction_seal_hash, None),
        (PHASE_ANALYSIS, analysis_seal_hash, prediction_seal_hash),
    ):
        tip = chains.read_tip(str(registry), hash_field=PHASE_STATE_HASH_FIELD)
        body = chains.phase_state_event(
            project_id=PROJECT_ID, protocol_id=PROTOCOL_ID, freeze_id=FREEZE_ID,
            evidence_generation_id=EVIDENCE_GENERATION_ID, phase=phase,
            expected_parent_phase_seal_hash=expected_parent,
            expected_validity_registry_head_hash=hashlib.sha256(b"test-validity").hexdigest(),
            new_active_revision_id=seal_hash,
            new_phase_seal_hash=seal_hash,
            prev_phase_state_event_hash=tip,
        )
        if fault == "terminal_state" and phase == PHASE_ANALYSIS:
            body["event_type"] = "PHASE_ABORTED"
        chains.append_cas(
            str(registry), body, expected_tip=tip, hash_field=PHASE_STATE_HASH_FIELD,
        )

    # --- read the chain back and verify it (a broken link must be refused) --------
    events = [
        json.loads(line)
        for line in registry.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    tip: str | None = None
    for event in events:
        stored = dict(event)
        claimed = stored.pop(PHASE_STATE_HASH_FIELD)
        if stored.get("prev_phase_state_event_hash") != tip:
            raise FixtureError(f"chain link broken before {stored['phase']}")
        if chains.event_hash(stored) != claimed:
            raise FixtureError(f"event hash mismatch for {stored['phase']}")
        tip = claimed
    if len(events) != 2:
        raise FixtureError(f"expected 2 phase-state events, got {len(events)}")
    for event in events:
        if event["event_type"] != "PHASE_ACTIVATED":
            raise FixtureError(f"terminal state is {event['event_type']!r}, not PHASE_ACTIVATED")
    if events[1]["expected_parent_phase_seal_hash"] != events[0]["new_phase_seal_hash"]:
        raise FixtureError("analysis seal is not bound to the prediction phase seal")

    # Independent re-derivation: read the persisted artifacts back and recompute
    # every hash the seals claim.  Without this step the chain would be a set of
    # assertions about itself, and a wrong index/shard/parent hash would sail
    # through (which is exactly what the first version of this fixture did).
    reloaded_prediction = json.loads(
        (out_dir / "PHASE_SEAL_TEST_PREDICTION.json").read_text(encoding="utf-8")
    )
    reloaded_analysis = json.loads(
        (out_dir / "PHASE_SEAL_TEST_ANALYSIS.json").read_text(encoding="utf-8")
    )
    reloaded_plan = json.loads((out_dir / "shard_plan.json").read_text(encoding="utf-8"))
    recomputed = {
        "data": indexes.index_content_hash(
            json.loads((out_dir / "expected_data_index.json").read_text(encoding="utf-8"))
        ),
        "feature": indexes.index_content_hash(
            json.loads((out_dir / "expected_feature_index.json").read_text(encoding="utf-8"))
        ),
        "evaluation": indexes.index_content_hash(
            json.loads((out_dir / "expected_evaluation_index.json").read_text(encoding="utf-8"))
        ),
        "shard_plan": indexes.shard_plan_hash(reloaded_plan),
    }
    for name, seal in (("prediction", reloaded_prediction), ("analysis", reloaded_analysis)):
        if seal["active_data_index_hash"] != recomputed["data"]:
            raise FixtureError(f"{name} seal: expected data index hash does not recompute")
        if seal["active_feature_index_hash"] != recomputed["feature"]:
            raise FixtureError(f"{name} seal: expected feature index hash does not recompute")
        if seal["active_evaluation_index_hash"] != recomputed["evaluation"]:
            raise FixtureError(f"{name} seal: expected evaluation index hash does not recompute")
        if seal["scope_design_hash"] != recomputed["shard_plan"]:
            raise FixtureError(f"{name} seal: shard plan hash does not recompute")
        if indexes.phase_seal_hash(seal) != events[
            0 if name == "prediction" else 1
        ]["new_phase_seal_hash"]:
            raise FixtureError(f"{name} seal hash does not match its chain event")
    if reloaded_analysis["parent_phase_seal_hash"] != indexes.phase_seal_hash(
        reloaded_prediction
    ):
        raise FixtureError("analysis seal payload is not bound to the prediction seal payload")
    if indexes.phase_seal_hash(prediction_seal) != prediction_seal_hash:
        raise FixtureError("prediction seal hash does not recompute")

    # --- TEST identity domain must be disjoint from the formal one ---------------
    formal_twin = _id("logical_data_key", project_id=FORMAL_PROJECT_ID, unit=0)
    test_id = data_rows[0]["logical_data_key"]
    if formal_twin == test_id:
        raise FixtureError("TEST identity domain collides with the formal domain")

    report = {
        "schema_version": 1,
        "kind": "lifecycle_fixture",
        "identity_domain": "TEST",
        "project_id": PROJECT_ID,
        "run_instance_id": RUN_INSTANCE_ID,
        "counts": {
            "data_units": len(data_rows),
            "feature_sufficient": len(feature_rows),
            "evaluations": len(evaluation_rows),
            "shard_entries": len(plan["entries"]),
        },
        "hashes": {
            "expected_data_index_hash": data_hash,
            "expected_index_hash": evaluation_hash,
            "expected_feature_index_hash": feature_hash,
            "shard_plan_hash": shard_hash,
            "prediction_phase_seal_hash": prediction_seal_hash,
            "analysis_phase_seal_hash": analysis_seal_hash,
            "phase_state_tip": tip,
        },
        "chain": [
            {"phase": e["phase"], "event_type": e["event_type"],
             "expected_parent_phase_seal_hash": e["expected_parent_phase_seal_hash"],
             "new_phase_seal_hash": e["new_phase_seal_hash"]}
            for e in events
        ],
        "verdict": {
            "chain_walked": True,
            "analysis_bound_to_phase_seal": True,
            "terminal_state": "PHASE_ACTIVATED",
            "fault_injected": fault,
            "admitted": True,
        },
    }
    (out_dir / "LIFECYCLE_FIXTURE.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description="TEST-identity lifecycle fixture (A11)")
    parser.add_argument("--out", required=True, help="evidence dir (outside the repo)")
    parser.add_argument("--fault", default=None, choices=[*FAULTS, None])
    args = parser.parse_args()
    try:
        report = run_fixture(out_dir=Path(args.out).expanduser(), fault=args.fault)
    except FixtureError as exc:
        print(json.dumps({"admitted": False, "fault": args.fault,
                          "refused_because": str(exc)}, ensure_ascii=False, indent=2))
        return 1
    print(json.dumps({"admitted": report["verdict"]["admitted"],
                      "counts": report["counts"],
                      "tip": report["hashes"]["phase_state_tip"],
                      "out": str(Path(args.out))}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
