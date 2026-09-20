"""Audit A01/A02/A05: the smoke plan must join the smoke ledger, row by row.

The audit found that the SCOPE_DESIGN rows bound by the S03 seal used the *formal*
identity domain while the executed rows used the smoke domain: 28 cells on each
side, **intersection zero**.  Count-based "closure" could not see it.  These tests
pin the repair: one enumerator produces scope + expected + worklist, and the
comparison against a ledger is set equality plus row-by-row foreign keys.

Mutation discipline (audit A05): every check below also has a deliberately broken
case that **must** fail, including the one that keeps the row count identical.
"""

import os
from pathlib import Path

import pytest

from owtda_cal import scope, smoke, smoke_ids

MANIFEST = {
    "project_id": "owtda-cal-r1",
    "protocol_id": "OWTDA-CAL-R1-PROTOCOL-v1.0",
    "freeze_id": "ab" * 32,
    "evidence_generation_id": "G01",
    "smoke_generation_id": scope.SMOKE_GENERATION_ID,
}


_IDS = {
    key: MANIFEST[key]
    for key in ("project_id", "protocol_id", "freeze_id", "evidence_generation_id")
}


def _ctx(phase: str) -> dict:
    return smoke.smoke_context(MANIFEST, phase)


def _expected(phase: str, replicates: int = scope.R0_SMOKE):
    return smoke.enumerate_smoke_expected(ctx=_ctx(phase), replicate_count=replicates)


def _ledger(phase: str, replicates: int = scope.R0_SMOKE) -> list[dict]:
    """An identity-only ledger built from the expectation (no statistics)."""
    return [dict(row) for row in _expected(phase, replicates).rows]


class TestExpectedWorklist:
    @pytest.mark.parametrize(
        "phase,rows,cells",
        [(scope.PHASE_SMOKE_NULL, 3584, 28), (scope.PHASE_SMOKE_ALT, 1024, 8)],
    )
    def test_counts_and_shape(self, phase, rows, cells):
        expected = _expected(phase)
        assert len(expected.rows) == rows
        assert len(expected.logical_cell_ids()) == cells
        assert len(expected.data_unit_ids()) == cells * scope.R0_SMOKE
        assert len(expected.evaluation_ids()) == rows

    @pytest.mark.parametrize("phase", [scope.PHASE_SMOKE_NULL, scope.PHASE_SMOKE_ALT])
    def test_replicate_numbering_is_one_based_and_complete(self, phase):
        expected = _expected(phase)
        wanted = frozenset(range(1, scope.R0_SMOKE + 1))
        per_cell = expected.replicates_per_cell()
        assert all(v == wanted for v in per_cell.values())
        assert 0 not in {r["replicate_id"] for r in expected.rows}

    @pytest.mark.parametrize("phase", [scope.PHASE_SMOKE_NULL, scope.PHASE_SMOKE_ALT])
    def test_units_are_the_full_cartesian_product(self, phase):
        expected = _expected(phase)
        cells = expected.logical_cell_ids()
        want = {
            (cell, rep, feature, method)
            for cell in cells
            for rep in range(1, scope.R0_SMOKE + 1)
            for feature in scope.FEATURE_IDS
            for method in scope.METHOD_IDS
        }
        assert expected.units() == want

    def test_replicate_zero_is_absent_and_replicate_32_is_present(self):
        """A02, exactly as the auditor reconstructed it.

        Under the protocol numbering each cell must *have* replicate 32 and must
        *not* have replicate 0; the audited ledger was the mirror image.  The chain
        is rebuilt here through ``smoke_ids`` for both numbers, so the assertion is
        about real identities rather than relabelled rows.
        """
        expected = _expected(scope.PHASE_SMOKE_NULL)
        generation = expected.smoke_generation_id
        family, rho = scope.H0_FAMILIES[0], scope.RHO_LEVELS[0]
        dmh = smoke._data_model_hash(family, rho)
        cell = next(
            c for c in expected.cells
            if c.DGP_family == family and c.rho == rho
        )
        ids = {}
        for replicate in (0, 32):
            master = smoke_ids.smoke_master_replicate_id(
                **_IDS, smoke_generation_id=generation, phase=scope.PHASE_SMOKE_NULL,
                DGP_family=family, replicate_id=replicate,
            )
            series = smoke_ids.smoke_base_series_id(
                smoke_master_replicate_id=master, smoke_generation_id=generation,
                rho=rho, raw_length=cell.T if cell.DGP_family == "CIRCLE_BASED_H1" else 12288,
                data_model_config_hash=dmh,
            )
            data_unit = smoke_ids.smoke_data_unit_id(
                smoke_base_series_id=series, smoke_physical_cell_id=cell.physical_cell_id,
                smoke_generation_id=generation,
            )
            ids[replicate] = data_unit
        assert ids[0] not in expected.data_unit_ids()
        assert ids[32] in expected.data_unit_ids()


class TestScopeLedgerJoin:
    @pytest.mark.parametrize(
        "phase,cells", [(scope.PHASE_SMOKE_NULL, 28), (scope.PHASE_SMOKE_ALT, 8)]
    )
    def test_scope_cells_equal_expected_cells(self, phase, cells):
        report = scope.smoke_scope_join_report(**_IDS, phase=phase,
                                              replicate_count=scope.R0_SMOKE)
        assert report["scope_cells"] == cells
        assert report["expected_cells"] == cells
        assert report["cell_intersection"] == cells  # was 0 before the fix
        assert report["experiment_intersection"] == 1
        assert report["scope_equals_expected_cells"] is True

    @pytest.mark.parametrize("phase", [scope.PHASE_SMOKE_NULL, scope.PHASE_SMOKE_ALT])
    def test_scope_rows_join_a_spec_built_ledger(self, phase):
        report = scope.smoke_scope_join_report(
            **_IDS, phase=phase, replicate_count=scope.R0_SMOKE,
            ledger_rows=_ledger(phase),
        )
        assert report["evaluation_ids_equal"] is True
        assert report["ledger_expected_cell_intersection"] == report["expected_cells"]

    def test_smoke_scope_uses_the_smoke_domain_not_the_formal_one(self):
        """The original defect: smoke scope ids must not be formal-domain ids."""
        smoke_rows = scope.scope_design_rows(
            project_id=MANIFEST["project_id"], protocol_id=MANIFEST["protocol_id"],
            freeze_id=MANIFEST["freeze_id"],
            evidence_generation_id=MANIFEST["evidence_generation_id"],
            phase=scope.PHASE_SMOKE_NULL, replicate_count=scope.R0_SMOKE,
        )
        formal_rows = scope.scope_design_rows(
            project_id=MANIFEST["project_id"], protocol_id=MANIFEST["protocol_id"],
            freeze_id=MANIFEST["freeze_id"],
            evidence_generation_id=MANIFEST["evidence_generation_id"],
            phase=scope.PHASE_NULL,
        )
        smoke_cells = {r["logical_cell_id"] for r in smoke_rows}
        formal_cells = {r["logical_cell_id"] for r in formal_rows}
        assert smoke_cells and formal_cells
        assert smoke_cells & formal_cells == set()  # two domains, no accidental reuse
        assert {r["experiment_id"] for r in smoke_rows} & {
            r["experiment_id"] for r in formal_rows
        } == set()

    def test_scope_rows_carry_the_generation(self):
        rows = scope.scope_design_rows(
            project_id=MANIFEST["project_id"], protocol_id=MANIFEST["protocol_id"],
            freeze_id=MANIFEST["freeze_id"],
            evidence_generation_id=MANIFEST["evidence_generation_id"],
            phase=scope.PHASE_SMOKE_ALT, replicate_count=scope.R0_SMOKE,
        )
        expected_ids = {r["logical_cell_id"] for r in _expected(scope.PHASE_SMOKE_ALT).rows}
        assert {r["logical_cell_id"] for r in rows} == expected_ids
        assert all(r["replicate_count"] == scope.R0_SMOKE for r in rows)


class TestLedgerValidationFailsClosed:
    def test_identical_ledger_passes(self):
        for phase, rows in (
            (scope.PHASE_SMOKE_NULL, 3584), (scope.PHASE_SMOKE_ALT, 1024)
        ):
            out = smoke.assert_smoke_ledger_matches_expected(
                ctx=_ctx(phase), replicate_count=scope.R0_SMOKE, ledger_rows=_ledger(phase)
            )
            assert out["evaluation_rows"] == rows
            assert out["replicate_count"] == scope.R0_SMOKE

    def test_one_wrong_evaluation_id_is_rejected(self):
        """The auditor's probe: replacing one id keeps the count and must fail."""
        rows = _ledger(scope.PHASE_SMOKE_NULL)
        rows[0] = {**rows[0], "evaluation_id": "AUDIT_WRONG_ID"}
        with pytest.raises(ValueError):
            smoke.assert_smoke_ledger_matches_expected(
                ctx=_ctx(scope.PHASE_SMOKE_NULL), replicate_count=scope.R0_SMOKE,
                ledger_rows=rows,
            )

    def test_wrong_upstream_foreign_key_is_rejected(self):
        rows = _ledger(scope.PHASE_SMOKE_ALT)
        rows[3] = {**rows[3], "data_unit_id": "0" * 64}
        with pytest.raises(ValueError):
            smoke.assert_smoke_ledger_matches_expected(
                ctx=_ctx(scope.PHASE_SMOKE_ALT), replicate_count=scope.R0_SMOKE,
                ledger_rows=rows,
            )

    def test_wrong_phase_is_rejected(self):
        rows = _ledger(scope.PHASE_SMOKE_NULL)
        rows[0] = {**rows[0], "phase": scope.PHASE_SMOKE_ALT}
        with pytest.raises(ValueError):
            smoke.assert_smoke_ledger_matches_expected(
                ctx=_ctx(scope.PHASE_SMOKE_NULL), replicate_count=scope.R0_SMOKE,
                ledger_rows=rows,
            )

    def test_deleted_cell_with_a_duplicated_one_is_rejected(self):
        """Count-preserving mutation: drop one cell's rows, duplicate another's."""
        rows = _ledger(scope.PHASE_SMOKE_ALT)
        by_cell: dict[str, list[dict]] = {}
        for row in rows:
            by_cell.setdefault(row["logical_cell_id"], []).append(row)
        ordered_cells = sorted(by_cell)
        victim, donor = ordered_cells[0], ordered_cells[1]
        mutated = [r for r in rows if r["logical_cell_id"] != victim]
        mutated.extend(dict(r) for r in by_cell[donor])
        assert len(mutated) == len(rows)  # the count is unchanged
        with pytest.raises(ValueError):
            smoke.assert_smoke_ledger_matches_expected(
                ctx=_ctx(scope.PHASE_SMOKE_ALT), replicate_count=scope.R0_SMOKE,
                ledger_rows=mutated,
            )

    def test_smoke_ids_are_not_reused_from_the_formal_domain(self):
        """A smoke generation id must appear in the smoke identity payload."""
        cell = _expected(scope.PHASE_SMOKE_ALT).cells[0]
        assert cell.logical_cell_id not in {
            r["logical_cell_id"]
            for r in scope.scope_design_rows(
                project_id=MANIFEST["project_id"], protocol_id=MANIFEST["protocol_id"],
                freeze_id=MANIFEST["freeze_id"],
                evidence_generation_id=MANIFEST["evidence_generation_id"],
                phase=scope.PHASE_ALT,
            )
        }
        assert smoke_ids.SMOKE_ID_PREFIX == "smoke_"


class TestRunnerClosureIsSpecDerived:
    """The runner/validator closure must fail on the auditor's exact attack."""

    @staticmethod
    def _run_smoke():
        import sys

        audit_dir = str(Path(__file__).resolve().parents[1] / "audit")
        if audit_dir not in sys.path:
            sys.path.insert(0, audit_dir)
        import run_smoke

        return run_smoke

    def test_wrong_evaluation_id_is_rejected(self):
        run_smoke = self._run_smoke()
        rows = _ledger(scope.PHASE_SMOKE_NULL)
        rows[7] = {**rows[7], "evaluation_id": "AUDIT_WRONG_ID"}
        with pytest.raises(ValueError):
            run_smoke.identity_closure(
                scope.PHASE_SMOKE_NULL, rows, manifest=MANIFEST
            )

    def test_closure_is_spec_derived_and_reports_counts_as_information(self):
        run_smoke = self._run_smoke()
        out = run_smoke.identity_closure(
            scope.PHASE_SMOKE_NULL, _ledger(scope.PHASE_SMOKE_NULL), manifest=MANIFEST
        )
        assert out["passed"] is True
        assert out["mode"] == "spec_derived_set_equality_plus_foreign_keys"
        assert out["counts_informational"]["evaluation_id"] == 3584

    def test_manifest_is_required(self):
        run_smoke = self._run_smoke()
        with pytest.raises(ValueError):
            run_smoke.identity_closure(scope.PHASE_SMOKE_NULL, [])


def test_delivered_s03_ledger_is_not_silently_accepted():
    """The audited S03 evidence must NOT validate against the fixed spec (A01/A02).

    If this ever passes, either the generation changed without a new run or the
    expectation was re-derived from the runner's own output.
    """
    # The audited S03 evidence lives outside the repository. Its location is machine specific, so
    # it is resolved from $OWTDA_AUDIT_EVIDENCE_ROOT instead of a hard-coded Windows path
    # (2026-09-20 audit: no local absolute paths in tracked files). Absent evidence -> skip.
    evidence_root = Path(os.environ.get("OWTDA_AUDIT_EVIDENCE_ROOT", "_audit_r1"))
    ledger_path = evidence_root / "smoke" / "S03" / "SMOKE_NULL" / "evaluation_rows.jsonl"
    if not ledger_path.exists():  # pragma: no cover - evidence not present
        pytest.skip("S03 evidence root not available (set OWTDA_AUDIT_EVIDENCE_ROOT)")
    import json

    rows = [
        json.loads(line)
        for line in ledger_path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    with pytest.raises(ValueError):
        smoke.assert_smoke_ledger_matches_expected(
            ctx=_ctx(scope.PHASE_SMOKE_NULL), replicate_count=scope.R0_SMOKE,
            ledger_rows=rows,
        )
