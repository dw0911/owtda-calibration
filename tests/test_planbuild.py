"""The formal expected plan builder (task pack §9 step 5).

Run at TEST scale here (a small replicate override) so the *structure* is pinned
cheaply; the formal call uses the frozen R0_H0 / R0_H1 counts and records that no
override was used.
"""

from __future__ import annotations

import json

from owtda_cal import indexes, planbuild, scope

ARGS = {"project_id": "p", "protocol_id": "q", "freeze_id": "0" * 64,
        "evidence_generation_id": "G01"}


class TestCells:
    def test_the_h0_cell_map_matches_the_scope_enumeration(self):
        cell_map = planbuild.plan_cells(phase=scope.PHASE_NULL, **ARGS)
        design = scope.scope_design_rows(phase=scope.PHASE_NULL, **ARGS)
        assert set(cell_map) == {row["logical_cell_id"] for row in design}
        assert len(cell_map) == 28

    def test_the_h1_cell_map_matches_the_scope_enumeration(self):
        cell_map = planbuild.plan_cells(phase=scope.PHASE_ALT, **ARGS)
        design = scope.scope_design_rows(phase=scope.PHASE_ALT, **ARGS)
        assert set(cell_map) == {row["logical_cell_id"] for row in design}
        assert len(cell_map) == 8

    def test_every_cell_carries_a_data_model_hash(self):
        for phase in (scope.PHASE_NULL, scope.PHASE_ALT):
            for params in planbuild.plan_cells(phase=phase, **ARGS).values():
                assert len(params["data_model_config_hash"]) == 64


class TestPlanShape:
    def _build(self, tmp_path, phase, replicates=2):
        return planbuild.build_phase_plan(
            out_dir=tmp_path, phase=phase, replicate_override=replicates, **ARGS)

    def test_the_counts_are_the_scope_contract_at_full_replicates(self, tmp_path):
        """At TEST scale the 1:2:4 relation must still hold exactly."""
        report = self._build(tmp_path, scope.PHASE_NULL, replicates=3)
        cells_n = report["cells"]
        assert report["counts"] == {
            "data_units": cells_n * 3,
            "feature_rows": cells_n * 3 * len(scope.FEATURE_IDS),
            "evaluation_rows": cells_n * 3 * len(scope.FEATURE_IDS)
                              * len(scope.METHOD_IDS),
        }

    def test_the_three_index_files_are_written_and_hashed(self, tmp_path):
        report = self._build(tmp_path, scope.PHASE_NULL)
        for name in ("expected_data_index.jsonl", "expected_feature_index.jsonl",
                     "expected_evaluation_index.jsonl"):
            path = tmp_path / scope.PHASE_NULL / name
            assert path.is_file(), name
            assert report["files"][name]["rows"] > 0
            assert len(report["files"][name]["sha256"]) == 64

    def test_the_index_hashes_recompute_from_the_written_rows(self, tmp_path):
        report = self._build(tmp_path, scope.PHASE_ALT)
        directory = tmp_path / scope.PHASE_ALT
        rows = [json.loads(line) for line in
                (directory / "expected_evaluation_index.jsonl")
                .read_text(encoding="utf-8").splitlines() if line.strip()]
        assert indexes.index_content_hash(rows) == report["index_hashes"]["evaluation"]

    def test_identities_are_unique_and_join_across_levels(self, tmp_path):
        self._build(tmp_path, scope.PHASE_NULL)
        directory = tmp_path / scope.PHASE_NULL
        data = [json.loads(x) for x in (directory / "expected_data_index.jsonl")
                .read_text(encoding="utf-8").splitlines() if x.strip()]
        feature = [json.loads(x) for x in (directory / "expected_feature_index.jsonl")
                   .read_text(encoding="utf-8").splitlines() if x.strip()]
        evaluation = [json.loads(x) for x in
                      (directory / "expected_evaluation_index.jsonl")
                      .read_text(encoding="utf-8").splitlines() if x.strip()]
        assert len({r["data_unit_id"] for r in data}) == len(data)
        assert len({r["feature_sufficient_id"] for r in feature}) == len(feature)
        assert len({r["evaluation_id"] for r in evaluation}) == len(evaluation)
        units = {r["data_unit_id"] for r in data}
        assert {r["data_unit_id"] for r in evaluation} <= units
        features = {r["feature_sufficient_id"] for r in feature}
        assert {r["feature_sufficient_id"] for r in evaluation} <= features

    def test_the_plan_is_deterministic(self, tmp_path):
        first = self._build(tmp_path / "a", scope.PHASE_NULL)
        second = self._build(tmp_path / "b", scope.PHASE_NULL)
        assert first["index_hashes"] == second["index_hashes"]
        assert first["files"] == second["files"]

    def test_a_reduced_plan_is_flagged_as_not_formal_scale(self, tmp_path):
        summary = planbuild.build_expected_plan(
            out_dir=tmp_path, phases=(scope.PHASE_NULL,), replicate_override=2, **ARGS)
        assert summary["formal_scale"] is False
        assert summary["replicate_override"] == 2
        assert summary["totals"]["evaluation_rows"] > 0
        written = json.loads((tmp_path / "PLAN_SUMMARY.json").read_text(encoding="utf-8"))
        assert written["formal_scale"] is False

    def test_active_ledgers_are_not_touched(self, tmp_path):
        """The plan is an expected index; no ledger role is written."""
        self._build(tmp_path, scope.PHASE_NULL)
        names = {p.name for p in (tmp_path / scope.PHASE_NULL).iterdir()}
        assert "evaluation_ledger.jsonl" not in names
        assert not any("ledger" in name for name in names)
