"""The formal phase body must commit a real shard under full-lifecycle monitoring.

The audit (R5-05) found the previous wrapper only wrote a ledger and stage labels.
These tests pin the real pipeline: the monitor stays open across compute ->
persist -> commit -> seal -> cleanup -> teardown, the produced rows are committed
as a real shard (three files + registry), and the full-lifecycle scope is derived
from what was actually observed -- never a stage label alone.
"""

from __future__ import annotations

import inspect
import json
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "audit"))
sys.path.insert(0, str(REPO / "src"))

from run_formal_phase import run_formal_phase_lifecycle

from owtda_cal import formal, formal_rows, scope


def _manifest():
    return json.loads((REPO / "governance" / "FREEZE_MANIFEST.json").read_text(encoding="utf-8"))


def _seeds():
    return json.loads((REPO / "governance" / "SEED_REGISTRY_v1.0.json").read_text(encoding="utf-8"))


def _schemas():
    feature_id = scope.FEATURE_IDS[0]
    family = "N_AR"
    scenario = "h0"
    return (
        {
            (family, scenario, feature_id, mid): formal_rows.load_row_schema(
                phase="NULL", DGP_family=family, scenario_id=scenario,
                feature_id=feature_id, method_id=mid,
            )
            for mid in ("M0_NAIVE_PERM_B999_V1", "M1_DMB_R1_TRI_EXTIID_B999_V1")
        },
        formal_rows.load_feature_schema(),
    )


@pytest.fixture()
def _fast_calibrate(monkeypatch):
    def stub(*args, **kwargs):
        return {"M": 0, "B": 999, "observed_statistic": 0.0,
                "exceed_count": 0, "p_value": 0.5, "reject": False}

    monkeypatch.setattr(formal, "calibrate_m0", stub)
    monkeypatch.setattr(formal, "calibrate_m1", stub)


def test_formal_phase_commits_a_real_shard(tmp_path, _fast_calibrate):
    manifest = _manifest()
    seeds = _seeds()

    def runner(**kwargs):
        ctx = formal.formal_context(manifest, "NULL")
        run_identity = {
            "compute_git_commit": "HEAD",
            "run_config_manifest_hash": "r" * 64, "registry_snapshot_hash": "r" * 64,
            "run_component_set_hash": "r" * 64, "run_instance_id": "RUN-1",
            "shard_plan_hash": "r" * 64, "expected_index_hash": "r" * 64,
            "expected_feature_index_hash": "r" * 64, "feature_registry_entry_hash": "r" * 64,
            "method_registry_entry_hash": "r" * 64, "data_registry_entry_hash": "r" * 64,
            "data_root_entry_hash": "r" * 64, "resampling_root_entry_hash": "r" * 64,
        }
        payload = {
            "family": scope.H0_FAMILIES[0], "rho": scope.RHO_LEVELS[0],
            "replicate": 1, "feature_id": scope.FEATURE_IDS[0],
            "ctx": ctx, "root_keys": formal.formal_root_keys(seeds, "NULL"),
            "run_identity": run_identity,
        }
        part = formal.process_formal_master_feature(payload)
        return SimpleNamespace(rows=part["rows"], feature_rows=part["feature_rows"],
                               errors=part["errors"])

    schemas, feature_schema = _schemas()
    outcome = run_formal_phase_lifecycle(
        phase="NULL", manifest=manifest, seed_registry=seeds, workers=1,
        replicate_limit=1, root=tmp_path, run_id="RUN-1", runner=runner,
        run_instance_id="RUN-1", partition="r1",
        schemas=schemas, feature_schema=feature_schema,
    )
    assert outcome["full_lifecycle"] is True
    assert outcome["missing_stages"] == []
    assert outcome["capacity_coverage_scope"] == "FULL_SCIENTIFIC_LIFECYCLE"
    # a real shard was committed (three files + registry)
    assert len(outcome["commit_records"]) == 1
    rec = outcome["commit_records"][0]
    assert rec["event_type"] == "SHARD_COMMITTED"
    final_dir = tmp_path / "run" / "RUN-1" / f"{rec['shard_id']}.final"
    assert (final_dir / "evaluation.scientific.jsonl").is_file()
    assert (final_dir / "feature.scientific.jsonl").is_file()
    assert outcome["shard_plan_hash"] is not None


def test_formal_phase_requires_the_runner_to_accept_the_monitor():
    assert "monitor" in inspect.signature(formal.run_formal_h0).parameters
    assert "monitor" in inspect.signature(formal.run_formal_h1).parameters
