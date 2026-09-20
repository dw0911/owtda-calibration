from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from owtda_cal import formal, planbuild


def _manifest() -> dict:
    return json.loads((Path(__file__).resolve().parents[1] / "governance" / "FREEZE_MANIFEST.json").read_text())


@pytest.mark.parametrize("phase", ["NULL", "ALT"])
def test_plan_builder_and_runtime_predeclaration_are_byte_hash_identical(tmp_path, phase):
    m = _manifest()
    report = planbuild.build_expected_plan(
        out_dir=tmp_path / phase,
        project_id=m["project_id"],
        protocol_id=m["protocol_id"],
        freeze_id=m["freeze_id"],
        evidence_generation_id=m["evidence_generation_id"],
        phases=(phase,),
        replicate_override=2,
        data_generation_id=m["component_generations"]["data_generation_id"],
    )
    runtime = formal.predeclare_formal_indexes(manifest=m, phase=phase, replicate_limit=2)
    expected = report["phases"][phase]["index_hashes"]
    actual = {
        "data": runtime["expected_data_index_hash"],
        "feature": runtime["expected_feature_index_hash"],
        "evaluation": runtime["expected_index_hash"],
    }
    assert actual == expected


def test_h1_predeclaration_does_not_collapse_the_two_alternative_scenarios():
    runtime = formal.predeclare_formal_indexes(manifest=_manifest(), phase="ALT", replicate_limit=1)
    assert len(runtime["data_rows"]) == 8
    assert len(runtime["feature_rows"]) == 16
    assert len(runtime["evaluation_rows"]) == 32


def test_formal_lifecycle_refuses_actual_rows_that_do_not_equal_predeclared_set(tmp_path):
    # No PH/science is needed: this pins the B-gate that a short/altered actual
    # ledger may never redefine its own "expected" set after compute.
    import sys
    repo = Path(__file__).resolve().parents[1]
    sys.path.insert(0, str(repo / "audit"))
    from run_formal_phase import run_formal_phase_lifecycle

    class IdentitySchema:
        def encode_to_wire(self, row):
            return row

    result = SimpleNamespace(rows=[], feature_rows=[], errors=0)

    with pytest.raises(RuntimeError, match="FORMAL_ACTUAL_INDEX_MISMATCH"):
        run_formal_phase_lifecycle(
            phase="NULL",
            manifest={},
            seed_registry={},
            workers=1,
            replicate_limit=1,
            root=tmp_path,
            run_id="TEST-RUN",
            runner=lambda **kwargs: result,
            run_instance_id="f" * 64,
            partition="NULL",
            schemas={},
            feature_schema=IdentitySchema(),
            expected_index_hashes={"data": "a" * 64, "feature": "b" * 64, "evaluation": "c" * 64},
            expected_shard_plan_hash="d" * 64,
        )
