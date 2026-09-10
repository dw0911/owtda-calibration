"""Tests for scope spec / logical identity layer (Plan §15.3, §16.2)."""

import pytest

from owtda_cal import scope
from owtda_cal.calibrate import M0_STABLE_ID, M1_STABLE_ID
from owtda_cal.features import BPI_STABLE_ID, MOMENTS_STABLE_ID

_PID = "owtda-cal-r1"
_PRT = "protocol_placeholder_1"
_FZ = "f" * 64
_EG = "G01"
_SCOPE = scope.scope_spec_hash(scope.scope_spec_h0())
_AA = "a" * 64


class TestScopeSpecHash:
    def test_stable_and_sensitive(self):
        h0 = scope.scope_spec_hash(scope.scope_spec_h0())
        assert h0 == scope.scope_spec_hash(scope.scope_spec_h0())
        assert h0 != scope.scope_spec_hash(scope.scope_spec_h1())
        assert len(h0) == 64

    def test_no_derived_ids_in_spec(self):
        spec = scope.scope_spec_h0()
        assert "freeze_id" not in str(spec)
        assert "logical_cell_id" not in str(spec)


class TestFreezeId:
    def test_chain(self):
        f1 = scope.freeze_id(
            project_id=_PID, protocol_id=_PRT, protocol_content_hash=_AA,
            scope_spec_hash=_SCOPE, analysis_spec_hash=_AA, compute_spec_hash=_AA,
        )
        f2 = scope.freeze_id(
            project_id=_PID, protocol_id=_PRT, protocol_content_hash=_AA,
            scope_spec_hash=_SCOPE, analysis_spec_hash=_AA, compute_spec_hash=_AA,
        )
        assert f1 == f2
        assert f1 != scope.freeze_id(
            project_id=_PID, protocol_id=_PRT, protocol_content_hash="b" * 64,
            scope_spec_hash=_SCOPE, analysis_spec_hash=_AA, compute_spec_hash=_AA,
        )


class TestLogicalIds:
    def _cell(self, **over):
        kw = {
            "project_id": _PID,
            "protocol_id": _PRT,
            "freeze_id": _FZ,
            "evidence_generation_id": _EG,
            "phase": "NULL",
            "DGP_family": "N_AR",
            "scenario_id": "h0",
            "rho": "0.8",
            "W": 64,
            "stride": 16,
            "T": 3120,
            "M": 192,
        }
        kw.update(over)
        return scope.logical_cell_id(**kw)

    def test_stable_and_sensitive(self):
        c = self._cell()
        assert c == self._cell()
        assert self._cell(rho="0") != c
        assert self._cell(stride=64, T=12288) != c
        assert self._cell(phase="ALT") != c
        assert len(c) == 64

    def test_data_feature_evaluation_keys(self):
        lc = self._cell()
        mr = "b" * 64
        ldk = scope.logical_data_key(logical_cell_id=lc, master_replicate_id=mr)
        lfk = scope.logical_feature_key(logical_data_key=ldk, feature_id=BPI_STABLE_ID)
        lek = scope.logical_evaluation_key(logical_data_key=ldk, feature_id=BPI_STABLE_ID,
                                           method_id=M0_STABLE_ID)
        lek2 = scope.logical_evaluation_key(logical_data_key=ldk, feature_id=BPI_STABLE_ID,
                                            method_id=M1_STABLE_ID)
        assert len({ldk, lfk, lek, lek2}) == 4
        assert lek != lek2


class TestEnumeration:
    def test_cell_counts(self):
        assert len(scope.h0_null_cells()) == 28
        assert len(scope.h1_alt_cells()) == 8

    def test_h1_not_budget_labelled(self):
        # H0 cells always carry a budget membership; ALT cells are not
        # budget-labelled (no budget_membership field) and use strides 64/16.
        assert all(c.budget_membership for c in scope.h0_null_cells())
        for a in scope.h1_alt_cells():
            assert not hasattr(a, "budget_membership")
            assert a.stride in (64, 16)
            assert a.scenario in (scope.SCENARIO_ALT_SHAPE, scope.SCENARIO_ALT_MEAN)

    def test_counts_summary(self):
        s = scope.scope_counts_summary()
        assert s == {
            "h0_logical_cells": 28,
            "h1_logical_cells": 8,
            "h0_data_units": 70_000,
            "h1_data_units": 12_800,
            "h0_evaluation_rows": 280_000,
            "h1_evaluation_rows": 51_200,
            "h0_feature_rows": 140_000,
            "h1_feature_rows": 25_600,
        }


class TestScopeDesignRows:
    def _rows(self, phase):
        return scope.scope_design_rows(
            project_id=_PID, protocol_id=_PRT, freeze_id=_FZ,
            evidence_generation_id=_EG, phase=phase,
        )

    def test_h0_112_rows_total_280k(self):
        rows = self._rows("NULL")
        assert len(rows) == 28 * 2 * 2 == 112
        assert sum(r["expected_logical_evaluations"] for r in rows) == 280_000
        keys = {(r["phase"], r["logical_cell_id"], r["feature_id"], r["method_id"]) for r in rows}
        assert len(keys) == len(rows)
        assert all(r["source_null_logical_cell_id"] is None for r in rows)
        cells = {r["logical_cell_id"] for r in rows}
        assert len(cells) == 28

    def test_h1_32_rows_total_51200_with_source_null(self):
        rows = self._rows("ALT")
        assert len(rows) == 8 * 2 * 2 == 32
        assert sum(r["expected_logical_evaluations"] for r in rows) == 51_200
        assert all(r["source_null_logical_cell_id"] for r in rows)
        # Source-null cells are unique per (rho, stride) geometry and shared by
        # both alternatives (Plan §12.3): 2 rho x 2 strides -> 4.
        srcs = {r["source_null_logical_cell_id"] for r in rows}
        assert len(srcs) == 4
        assert all(len(s) == 64 for s in srcs)

    def test_method_feature_ids_present(self):
        rows = self._rows("NULL")
        fids = {r["feature_id"] for r in rows}
        mids = {r["method_id"] for r in rows}
        assert fids == {BPI_STABLE_ID, MOMENTS_STABLE_ID}
        assert mids == {M0_STABLE_ID, M1_STABLE_ID}

    def test_invalid_phase(self):
        with pytest.raises(ValueError):
            scope.scope_design_rows(
                project_id=_PID, protocol_id=_PRT, freeze_id=_FZ,
                evidence_generation_id=_EG, phase="NOPE",
            )

    def test_smoke_phases_share_geometry_with_own_identity(self):
        null_rows = scope.scope_design_rows(
            project_id=_PID, protocol_id=_PRT, freeze_id=_FZ,
            evidence_generation_id=_EG, phase=scope.PHASE_NULL,
        )
        smoke_rows = scope.scope_design_rows(
            project_id=_PID, protocol_id=_PRT, freeze_id=_FZ,
            evidence_generation_id=_EG, phase=scope.PHASE_SMOKE_NULL,
        )
        assert len(null_rows) == len(smoke_rows) == 112
        assert all(r["replicate_count"] == scope.R0_SMOKE for r in smoke_rows)
        assert {r["logical_cell_id"] for r in smoke_rows} & {
            r["logical_cell_id"] for r in null_rows
        } == set()
        smoke_alt = scope.scope_design_rows(
            project_id=_PID, protocol_id=_PRT, freeze_id=_FZ,
            evidence_generation_id=_EG, phase=scope.PHASE_SMOKE_ALT,
        )
        assert len(smoke_alt) == 32
        assert all(r["replicate_count"] == scope.R0_SMOKE for r in smoke_alt)
