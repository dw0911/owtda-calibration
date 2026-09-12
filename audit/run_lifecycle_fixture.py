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
import shutil
import sys
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "src"))
sys.path.insert(0, str(REPO / "audit"))

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
RUN_INSTANCE_ID = "TEST_LIFECYCLE_01"
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


#: The frozen TEST scope (task pack §4.2): 2 NULL/ALT data tasks x 2 representations
#: x 2 calibrations = 8 real evaluations.  One definition, used by *both* the
#: expected index and the real computation -- the re-audit found the two had drifted
#: apart (8 expected ids, 4 real rows, intersection 0).
TEST_TASKS = ("NULL", "ALT")
TEST_FEATURES = ("bpi", "moments")


def _method_ids() -> tuple[str, str]:
    from owtda_cal.calibrate import M0_STABLE_ID, M1_STABLE_ID

    return (M0_STABLE_ID, M1_STABLE_ID)


def build_scope() -> dict[str, list[dict]]:
    """The TEST scope: every id is domain-separated by the TEST project id.

    The ids are derived from the same (task, feature, method) triple the
    computation uses, so ``E_expected`` and ``E_actual`` are the same set by
    construction -- and the fixture then *checks* that they still are.
    """
    data: list[dict] = []
    feature: list[dict] = []
    evaluation: list[dict] = []
    for task in TEST_TASKS:
        logical_data_key = _id("logical_data_key", task=task)
        data_unit_id = _id("data_unit_id", task=task)
        data.append({"logical_data_key": logical_data_key, "data_unit_id": data_unit_id})
        for feature_id in TEST_FEATURES:
            logical_feature_key = _id("logical_feature_key", task=task, feature=feature_id)
            feature_sufficient_id = _id("feature_sufficient", task=task, feature=feature_id)
            feature.append({
                "logical_data_key": logical_data_key,
                "logical_feature_key": logical_feature_key,
                "data_unit_id": data_unit_id,
                "feature_sufficient_id": feature_sufficient_id,
            })
            for method_id in _method_ids():
                evaluation.append({
                    "logical_data_key": logical_data_key,
                    "logical_feature_key": logical_feature_key,
                    "logical_evaluation_key": _id(
                        "logical_evaluation_key", task=task, feature=feature_id,
                        method=method_id,
                    ),
                    "data_unit_id": data_unit_id,
                    "feature_sufficient_id": feature_sufficient_id,
                    "evaluation_id": _id(
                        "evaluation", task=task, feature=feature_id, method=method_id
                    ),
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
    source_run_seal_hashes: list[str],
    upstream_refs: list[dict[str, Any]],
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
        "ordered_source_run_seal_hashes": sorted(set(source_run_seal_hashes)),
        "ordered_upstream_artifact_refs": upstream_refs,
    }


def real_computation(
    *, out_dir: Path, root_key_hex: str, shard_plan_hash: str
) -> dict[str, Any]:
    """Real PH/BPI/MOMENTS -> M0/M1, producing an actual ledger file (TEST scope).

    Re-audit 2026-09-12: the first fixture walked the metadata chain only -- no real
    PH, no calibration, and the "ledger" was an ID dictionary.  This runs a handful of
    real windows through the real feature and calibration paths (B=999 as frozen) and
    writes the rows as a genuine record file.  It proves the *path* runs; it carries no
    scientific claim.
    """
    import numpy as np

    from owtda_cal import features
    from owtda_cal.calibrate import (
        M0_STABLE_ID,
        M1_STABLE_ID,
        calibrate_m0,
        calibrate_m1,
    )
    W, stride, M = 64, 16, 8
    rows: list[dict[str, Any]] = []
    shards: list[dict[str, Any]] = []
    for task in TEST_TASKS:
        # One data task -> one shard.  The two tasks differ in their seed stream and
        # in whether a change point is injected (ALT), so the eight evaluations are
        # eight genuinely distinct computations.
        rng = np.random.default_rng(20260912 if task == "NULL" else 20260913)
        # The real point-cloud contract requires a 2-D (multi-channel) window whenever
        # delay=False, i.e. for every scenario but N_AR.
        series = rng.standard_normal(((M - 1) * stride + W, 2))
        if task == "ALT":
            series[M // 2 * stride:] += 1.0  # one injected change point
        windows = [series[i * stride:i * stride + W] for i in range(M)]
        task_rows: list[dict[str, Any]] = []
        for feature_id in TEST_FEATURES:
            matrix = features.feature_matrix_for_windows(
                windows, feature_kind=feature_id, scenario=features.SCENARIO_N_CIRCLE
            )
            for method_id, out in (
                (M0_STABLE_ID, calibrate_m0(
                    matrix, root_key_hex=root_key_hex,
                    stream_kind="fixture_M0_permutation",
                    stream_fields={"task": task, "feature_id": feature_id,
                                   "shard_plan_hash": shard_plan_hash},
                )),
                (M1_STABLE_ID, calibrate_m1(
                    matrix, root_key_hex=root_key_hex, W=W, stride=stride,
                    stream_kind="fixture_M1_gaussian_innovation",
                    stream_fields={"task": task, "feature_id": feature_id,
                                   "shard_plan_hash": shard_plan_hash},
                )),
            ):
                row = {
                    "phase": PHASE_PREDICTION,
                    "experiment_id": _id("experiment", task=task),
                    "logical_cell_id": _id("logical_cell", task=task),
                    "logical_data_key": _id("logical_data_key", task=task),
                    "logical_feature_key": _id(
                        "logical_feature_key", task=task, feature=feature_id
                    ),
                    "logical_evaluation_key": _id(
                        "logical_evaluation_key", task=task, feature=feature_id,
                        method=method_id,
                    ),
                    "data_unit_id": _id("data_unit_id", task=task),
                    "feature_sufficient_id": _id(
                        "feature_sufficient", task=task, feature=feature_id
                    ),
                    "evaluation_id": _id(
                        "evaluation", task=task, feature=feature_id, method=method_id
                    ),
                    "DGP_family": "fixture_family",
                    "scenario_id": features.SCENARIO_N_CIRCLE,
                    "rho": "0",
                    "task": task,
                    "feature_id": feature_id,
                    "method_id": method_id,
                    "observed_statistic": float(out["observed_statistic"]),
                    "exceed_count": int(out["exceed_count"]),
                    "p_value": float(out["p_value"]),
                    "reject": bool(out["reject"]),
                }
                task_rows.append(row)
        evaluation_lines = [
            (json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n").encode()
            for row in task_rows
        ]
        feature_lines = [
            (json.dumps(
                {
                    "task": task, "feature_id": feature_id,
                    "feature_sufficient_id": _id(
                        "feature_sufficient", task=task, feature=feature_id
                    ),
                    "data_unit_id": _id("data_unit_id", task=task),
                    "windows": M,
                },
                ensure_ascii=False, sort_keys=True,
            ) + "\n").encode()
            for feature_id in TEST_FEATURES
        ]
        shards.append({
            "task": task,
            "shard_id": _id("shard", task=task),
            "evaluation_lines": evaluation_lines,
            "feature_lines": feature_lines,
            "evaluation_ids": [r["evaluation_id"] for r in task_rows],
        })
        rows.extend(task_rows)
    ledger = out_dir / "evaluation_rows.jsonl"
    ledger.write_bytes(b"".join(
        (json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n").encode()
        for row in rows
    ))
    return {
        "rows": len(rows),
        "ledger": ledger.name,
        "ledger_bytes": ledger.stat().st_size,
        "ledger_sha256": hashlib.sha256(ledger.read_bytes()).hexdigest(),
        "features": sorted({row["feature_id"] for row in rows}),
        "methods": sorted({row["method_id"] for row in rows}),
        "B": 999,
        "windows": M,
        "tasks": list(TEST_TASKS),
        "shards": shards,
        "evaluation_ids": [r["evaluation_id"] for r in rows],
    }


def shard_roundtrip(*, out_dir: Path, computation: dict[str, Any]) -> dict[str, Any]:
    """Commit the real shards, then run the negative probes in their own root.

    Task pack §4.2/§4.3.  Previously the shards carried a ``{"row":1}`` placeholder,
    the expected 8 ids and the 4 real ids were disjoint, and the *positive* registry
    was left holding a commit whose directory the deletion probe had removed.  Now:

    * one shard per data task, carrying the real evaluation/feature lines;
    * the merged ledger is built by reading back what was actually committed, so
      ``∪E_committed`` is what the phase seal hashes;
    * the deletion and orphan probes run under ``<out_dir>/negative`` -- a separate
      TEST execution root -- so their debris can never mix into the active ledger.
    """
    from owtda_cal import shardio

    commit_shard = shardio.commit_shard
    run_root = str(out_dir / "runs")
    registry = str(out_dir / "shard_registry.jsonl")
    plan_hash = _id("shard_plan", unit="fixture")

    committed: list[dict[str, Any]] = []
    evaluation_payload = b""
    feature_payload = b""
    for shard in computation["shards"]:
        kw = {
            "run_root": run_root, "run_instance_id": RUN_INSTANCE_ID,
            "shard_id": shard["shard_id"], "shard_plan_hash": plan_hash,
            "evaluation_lines": shard["evaluation_lines"],
            "feature_lines": shard["feature_lines"],
            "evaluation_meta": {"row_count": len(shard["evaluation_lines"])},
            "feature_meta": {"row_count": len(shard["feature_lines"])},
            "registry_path": registry,
        }
        record = commit_shard(**kw)
        again = commit_shard(**kw)  # idempotent re-commit: one record, same bytes
        final = Path(run_root, RUN_INSTANCE_ID, f"{shard['shard_id']}.final")
        evaluation_payload += (final / "evaluation.scientific.jsonl").read_bytes()
        feature_payload += (final / "feature.scientific.jsonl").read_bytes()
        committed.append({
            "task": shard["task"], "shard_id": shard["shard_id"],
            "shard_commit_hash": record["shard_commit_hash"],
            "idempotent_recommit": again["shard_commit_hash"] == record["shard_commit_hash"],
            "evaluation_ids": list(shard["evaluation_ids"]),
        })

    (out_dir / "evaluation_ledger.jsonl").write_bytes(evaluation_payload)
    (out_dir / "feature_ledger.jsonl").write_bytes(feature_payload)

    negative = _negative_shard_probes(out_dir=out_dir, plan_hash=plan_hash)

    return {
        "committed_shards": committed,
        "committed_evaluation_ids": sorted(
            evaluation_id for shard in committed for evaluation_id in shard["evaluation_ids"]
        ),
        "ledger": "evaluation_ledger.jsonl",
        "feature_ledger": "feature_ledger.jsonl",
        "idempotent_recommit": all(c["idempotent_recommit"] for c in committed),
        "deleted_final_blocked": negative["deleted_final_blocked"],
        "orphan_refused": negative["orphan_refused"],
        "orphan_committed_by_repair": negative["orphan_committed_by_repair"],
        "registry_records": len(
            [line for line in Path(registry).read_text(encoding="utf-8").splitlines()
             if line.strip()]
        ),
        "negative_root": "negative",
        "negative_registry_records": negative["registry_records"],
    }


def _negative_shard_probes(*, out_dir: Path, plan_hash: str) -> dict[str, Any]:
    """The destructive probes, isolated in their own TEST execution root."""
    from owtda_cal import shardio

    commit_shard = shardio.commit_shard
    negative_dir = out_dir / "negative"
    run_root = str(negative_dir / "runs")
    registry = str(negative_dir / "shard_registry.jsonl")
    shard_id = _id("shard", unit="negative")
    kw = {
        "run_root": run_root, "run_instance_id": RUN_INSTANCE_ID, "shard_id": shard_id,
        "shard_plan_hash": plan_hash, "evaluation_lines": [b'{"row":1}\n'],
        "feature_lines": [b'{"f":1}\n'], "evaluation_meta": {}, "feature_meta": {},
        "registry_path": registry,
    }
    commit_shard(**kw)
    final = Path(run_root, RUN_INSTANCE_ID, f"{shard_id}.final")
    deleted_blocked = False
    shutil.rmtree(final)
    try:
        commit_shard(**kw)
    except shardio.ShardError:
        deleted_blocked = True
    # orphan recovery: a .final with no commit must refuse, then repair_orphan appends
    orphan_id = _id("shard", unit="orphan")
    orphan_dir = Path(run_root, RUN_INSTANCE_ID, f"{orphan_id}.final")
    orphan_dir.mkdir(parents=True, exist_ok=True)
    # Task pack §2.2/§4.2: the manifest must *declare* the real payload hashes --
    # repair_orphan now verifies that declaration instead of trusting the caller.
    orphan_eval = b'{"row":1}\n'
    orphan_feat = b'{"f":1}\n'
    manifest = shardio.build_shard_manifest(
        run_instance_id=RUN_INSTANCE_ID, shard_id=orphan_id, shard_plan_hash=plan_hash,
        evaluation={"scientific_hash": hashlib.sha256(orphan_eval).hexdigest()},
        feature={"scientific_hash": hashlib.sha256(orphan_feat).hexdigest()},
    )
    manifest_bytes = canonical_json_bytes(manifest) + b"\n"
    (orphan_dir / "shard_manifest.json").write_bytes(manifest_bytes)
    (orphan_dir / "evaluation.scientific.jsonl").write_bytes(b'{"row":1}\n')
    (orphan_dir / "feature.scientific.jsonl").write_bytes(b'{"f":1}\n')
    orphan_refused = False
    orphan_committed = False
    try:
        commit_shard(
            run_root=run_root, run_instance_id=RUN_INSTANCE_ID, shard_id=orphan_id,
            shard_plan_hash=plan_hash, evaluation_lines=[b'{"row":1}\n'],
            feature_lines=[b'{"f":1}\n'], evaluation_meta={}, feature_meta={},
            registry_path=registry,
        )
    except shardio.ShardError:
        orphan_refused = True
    shardio.repair_orphan(
        run_root=run_root, run_instance_id=RUN_INSTANCE_ID, shard_id=orphan_id,
        registry_path=registry, recompute_to=str(negative_dir / "orphan_recompute"),
        expected_manifest_bytes=manifest_bytes,
        expected_evaluation_bytes=orphan_eval,
        expected_feature_bytes=orphan_feat,
        expected_shard_plan_hash=plan_hash,
    )
    orphan_committed = True
    return {
        "deleted_final_blocked": deleted_blocked,
        "orphan_refused": orphan_refused,
        "orphan_committed_by_repair": orphan_committed,
        "registry_records": len(
            [line for line in Path(registry).read_text(encoding="utf-8").splitlines()
             if line.strip()]
        ),
    }


def run_seal_and_analysis(*, out_dir: Path, ledger: dict[str, Any]) -> dict[str, Any]:
    """RUN_SEAL via the production registry, then an analysis input/output pair."""
    from run_registry import record_seal, record_start

    root = out_dir / "run"
    root.mkdir(parents=True, exist_ok=True)
    run_id = RUN_INSTANCE_ID
    record_start(
        root, run_id=run_id, phase=PHASE_PREDICTION,
        smoke_generation_id="TEST-FIXTURE", workers=1, replicates_per_cell=1,
        run_component_set_hash="0" * 64, compute_git_commit="fixture",
        source_tree_hash="0" * 64, environment_lock_hash="0" * 64, workers_used=1,
    )
    sealed = record_seal(
        root, run_id=run_id, phase=PHASE_PREDICTION,
        seal={
            "ledger_file": ledger["ledger"],
            "ledger_content_hash": ledger["ledger_sha256"],
            "ledger_bytes": ledger["ledger_bytes"],
            "row_count": ledger["rows"],
            "unexplained_errors": 0,
            "counts_match_contract": True,
            "terminal_state": "RUN_SEALED",
        },
    )
    return {
        "run_seal_hash": sealed["smoke_seal_hash"],
        "run_seal_file": sealed["seal_file"],
        "sealed_ledger": ledger["ledger"],
        "sealed_ledger_sha256": ledger["ledger_sha256"],
        "sealed_row_count": ledger["rows"],
    }


def finalize_analysis(
    *,
    out_dir: Path,
    ledger_file: str,
    phase_seal_hashes: list[str],
    analysis_seal_hash: str,
    source_run_seal_hashes: list[str],
) -> dict[str, Any]:
    """Freeze the analysis input, then produce the output from the real ledger.

    Task pack §4.2: the previous analysis entry took its numbers from the summary
    the computation had already produced and only bolted the phase reference on
    afterwards.  Here the input (phase seals, ledger path and hash) is frozen
    first, and every reported figure is then recomputed by reading the actual
    committed rows -- including the row count, the id sets and the ledger hash.
    """
    ledger_path = out_dir / ledger_file
    raw = ledger_path.read_bytes()
    rows = [
        json.loads(line)
        for line in raw.decode("utf-8").splitlines()
        if line.strip()
    ]
    analysis_input = {
        "schema_version": 1,
        "kind": "analysis_input_manifest",
        "phase_seal_hashes": sorted(set(phase_seal_hashes)),
        "analysis_seal_hash": analysis_seal_hash,
        "source_run_seal_hashes": sorted(set(source_run_seal_hashes)),
        "ledger": ledger_file,
        "ledger_sha256": hashlib.sha256(raw).hexdigest(),
    }
    (out_dir / "analysis_input.json").write_text(
        json.dumps(analysis_input, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    output = {
        "schema_version": 1,
        "kind": "analysis_output",
        "descriptive_only": True,
        "note": "counts and identities only: the fixture carries no rejection rate or power",
        "rows": len(rows),
        "evaluation_ids": sorted({row["evaluation_id"] for row in rows}),
        "duplicate_evaluation_ids": sorted({
            row["evaluation_id"] for row in rows
            if [r["evaluation_id"] for r in rows].count(row["evaluation_id"]) > 1
        }),
        "features": sorted({row["feature_id"] for row in rows}),
        "methods": sorted({row["method_id"] for row in rows}),
        "ledger_sha256": hashlib.sha256(raw).hexdigest(),
        "ledger_bytes": len(raw),
    }
    (out_dir / "analysis_output.json").write_text(
        json.dumps(output, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return {"analysis_input": "analysis_input.json",
            "analysis_output": "analysis_output.json", "rows": len(rows)}


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

    # --- the real execution chain (re-audit: metadata alone is not a lifecycle) ---
    root_key_hex = hashlib.sha256(b"TEST-FIXTURE-ROOT-KEY").hexdigest()
    computation = real_computation(
        out_dir=out_dir, root_key_hex=root_key_hex, shard_plan_hash=shard_hash
    )
    shards = shard_roundtrip(out_dir=out_dir, computation=computation)

    # The ledger the seals hash is the *merged committed* payload, not the expected
    # index and not the computation's private row file.
    merged_ledger = out_dir / shards["ledger"]
    merged_bytes = merged_ledger.read_bytes()
    merged_rows = [
        json.loads(line) for line in merged_bytes.decode("utf-8").splitlines() if line.strip()
    ]
    expected_ids = sorted(r["evaluation_id"] for r in evaluation_rows)
    actual_ids = sorted(computation["evaluation_ids"])
    committed_ids = sorted(shards["committed_evaluation_ids"])
    if not (expected_ids == actual_ids == committed_ids):
        raise FixtureError(
            "evaluation identity sets disagree: expected "
            f"{len(expected_ids)}, actual {len(actual_ids)}, committed "
            f"{len(committed_ids)} (intersection "
            f"{len(set(expected_ids) & set(actual_ids) & set(committed_ids))})"
        )
    if len(set(committed_ids)) != len(committed_ids):
        raise FixtureError("an evaluation id was committed more than once")
    if len(merged_rows) != len(committed_ids):
        raise FixtureError(
            f"the merged ledger holds {len(merged_rows)} rows for "
            f"{len(committed_ids)} committed evaluations"
        )

    # The report is JSON: the raw payload bytes stay out of it, only their ids and
    # hashes are recorded (the bytes themselves live in the committed shards).
    computation_public = {
        **{k: v for k, v in computation.items() if k != "shards"},
        "shards": [
            {"task": s["task"], "shard_id": s["shard_id"],
             "evaluation_ids": list(s["evaluation_ids"])}
            for s in computation["shards"]
        ],
    }
    execution: dict[str, Any] = {"computation": computation_public, "shards": shards}
    execution.update(run_seal_and_analysis(out_dir=out_dir, ledger={
        "ledger": shards["ledger"],
        "ledger_bytes": len(merged_bytes),
        "ledger_sha256": hashlib.sha256(merged_bytes).hexdigest(),
        "rows": len(merged_rows),
        "features": sorted({row["feature_id"] for row in merged_rows}),
        "methods": sorted({row["method_id"] for row in merged_rows}),
    }))
    set_equality = {
        "expected": expected_ids,
        "actual": actual_ids,
        "committed": committed_ids,
        "identical": True,
        "count_per_evaluation": 1,
    }
    upstream_refs = [{
        "role": "source_run_seal",
        "stable_id": execution["run_seal_hash"],
        "generation_id": EVIDENCE_GENERATION_ID,
        "hash": execution["run_seal_hash"],
    }]
    # written once the analysis has been bound to the sealed phases (see below)

    # The ledger content hash is taken over the real committed scientific bytes --
    # re-audit 2026-09-13: it used to be the serialisation of the *expected id
    # dictionary*, so the seal did not cover a single real row.
    ledger = merged_bytes
    feature_ledger = (out_dir / shards["feature_ledger"]).read_bytes()

    merged_feature_rows = [
        json.loads(line)
        for line in (out_dir / shards["feature_ledger"]).read_text(encoding="utf-8")
        .splitlines() if line.strip()
    ]
    prediction_seal = indexes.build_phase_seal(**_seal_fields(
        phase=PHASE_PREDICTION, parent_phase_seal_hash=None, data_hash=data_hash,
        feature_hash=feature_hash, evaluation_hash=evaluation_hash, ledger=ledger,
        feature_ledger=feature_ledger, evaluation_rows=merged_rows,
        feature_rows=merged_feature_rows, n_logical_keys=len(data_rows),
        shard_hash=shard_hash,
        source_run_seal_hashes=[execution["run_seal_hash"]], upstream_refs=upstream_refs,
    ))
    prediction_seal_hash = indexes.phase_seal_hash(prediction_seal)

    parent = prediction_seal_hash if fault != "parent_seal" else "2" * 64
    analysis_seal = indexes.build_phase_seal(**_seal_fields(
        phase=PHASE_ANALYSIS, parent_phase_seal_hash=parent, data_hash=data_hash,
        feature_hash=feature_hash, evaluation_hash=evaluation_hash, ledger=ledger,
        feature_ledger=feature_ledger, evaluation_rows=merged_rows,
        feature_rows=merged_feature_rows, n_logical_keys=len(data_rows),
        shard_hash=shard_hash,
        source_run_seal_hashes=[execution["run_seal_hash"]], upstream_refs=upstream_refs,
    ))
    analysis_seal_hash = indexes.phase_seal_hash(analysis_seal)

    # Bind the analysis entry to the sealed phases: the input is frozen first, and
    # the output is then computed from the actual committed rows (§4.2).
    execution.update(finalize_analysis(
        out_dir=out_dir, ledger_file=shards["ledger"],
        phase_seal_hashes=[prediction_seal_hash, analysis_seal_hash],
        analysis_seal_hash=analysis_seal_hash,
        source_run_seal_hashes=[execution["run_seal_hash"]],
    ))
    (out_dir / "EXECUTION_CHAIN.json").write_text(
        json.dumps(execution, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )

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
            "expected_evaluation_index_hash": evaluation_hash,
            "expected_feature_index_hash": feature_hash,
            # 'expected index' and 'ledger content' are different roles: the first
            # is what the plan promises, the second is what was really committed.
            "active_ledger_content_hash": hashlib.sha256(ledger).hexdigest(),
            "active_feature_ledger_content_hash": hashlib.sha256(feature_ledger).hexdigest(),
            "roles_are_distinct": hashlib.sha256(ledger).hexdigest() != evaluation_hash,
            "shard_plan_hash": shard_hash,
            "prediction_phase_seal_hash": prediction_seal_hash,
            "analysis_phase_seal_hash": analysis_seal_hash,
            "phase_state_tip": tip,
        },
        "set_equality": set_equality,
        "chain": [
            {"phase": e["phase"], "event_type": e["event_type"],
             "expected_parent_phase_seal_hash": e["expected_parent_phase_seal_hash"],
             "new_phase_seal_hash": e["new_phase_seal_hash"]}
            for e in events
        ],
        "execution": execution,
        "verdict": {
            "chain_walked": True,
            "analysis_bound_to_phase_seal": True,
            "terminal_state": "PHASE_ACTIVATED",
            "fault_injected": fault,
            "real_computation_executed": True,
            "shard_commit_and_recovery_exercised": True,
            "expected_actual_committed_identical": set_equality["identical"],
            "ledger_is_the_committed_payload": (
                hashlib.sha256(ledger).hexdigest() == execution["sealed_ledger_sha256"]
            ),
            "analysis_reads_the_actual_ledger": True,
            "phase_seals_carry_source_run_seal": bool(
                prediction_seal["ordered_source_run_seal_hashes"]
            ),
            "analysis_output_written": (out_dir / "analysis_output.json").exists(),
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
