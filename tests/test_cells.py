"""Tests for H0 cell geometry, 575-window map and synthetic IDs (Plan §8)."""

from owtda_cal.cells import (
    BUDGET_FIXED_M,
    BUDGET_FIXED_T,
    T_FIXED_T,
    W_FIXED,
    data_unit_id,
    fixed_m_raw_length,
    fixed_t_window_count,
    h0_geometry_cells,
    master_replicate_id,
    physical_cell_id,
    unique_window_start_map,
    verify_h0_counts,
    window_count,
)
from owtda_cal.identity import H

_AA = "a" * 64


class TestWindowCount:
    def test_plan_fixed_m_table(self):
        assert fixed_m_raw_length(64) == 12288
        assert fixed_m_raw_length(32) == 6176
        assert fixed_m_raw_length(16) == 3120
        assert fixed_m_raw_length(8) == 1592

    def test_plan_fixed_t_table(self):
        assert fixed_t_window_count(64) == 48
        assert fixed_t_window_count(32) == 96
        assert fixed_t_window_count(16) == 192
        assert fixed_t_window_count(8) == 383

    def test_formula(self):
        assert window_count(12288, 64, 64) == 192
        assert window_count(3120, 64, 8) == 383
        assert fixed_m_raw_length(16) == 64 + 16 * (192 - 1)


class TestGeometry:
    def test_seven_unique_geometries(self):
        geom = h0_geometry_cells()
        assert len(geom) == 7
        fm = {g.stride: g for g in geom if BUDGET_FIXED_M in g.budget_membership}
        assert {fm[s].T for s in (64, 32, 16, 8)} == {12288, 6176, 3120, 1592}
        shared = [g for g in geom if g.stride == 16 and g.T == T_FIXED_T]
        assert len(shared) == 1
        assert shared[0].budget_membership == (BUDGET_FIXED_M, BUDGET_FIXED_T)

    def test_raw_starts(self):
        g8m = next(g for g in h0_geometry_cells() if g.stride == 8 and g.T != T_FIXED_T)
        starts = g8m.raw_starts()
        assert len(starts) == g8m.M == 192
        assert starts[0] == 0
        assert starts[-1] + W_FIXED <= g8m.T

    def test_counts(self):
        assert verify_h0_counts() == {
            "unique_geometries": 7,
            "geometry_s16_membership": 2,
            "unique_starts": 575,
            "fixed_m_cells": 4,
            "fixed_t_cells": 4,
        }


class TestWindowStartMap:
    def test_union_size_575(self):
        starts = unique_window_start_map()
        keys = list(starts)
        assert len(starts) == 575
        assert keys == sorted(keys)
        assert keys[0] == 0
        assert keys[-1] == 12224

    def test_stride8_fixed_t_covered(self):
        starts = unique_window_start_map()
        t_covered = [k for k, m in starts.items() if BUDGET_FIXED_T in m]
        assert len(t_covered) == fixed_t_window_count(8) == 383
        assert t_covered[0] == 0 and t_covered[-1] == 3056
        assert set(t_covered) == set(range(0, 3057, 8))

    def test_new_fixed_m_slices(self):
        keys = list(unique_window_start_map())
        s32_new = [k for k in keys if 3056 < k <= 6112 and k % 32 == 0]
        s64_new = [k for k in keys if k > 6112 and k % 64 == 0]
        assert len(s32_new) == 96
        assert len(s64_new) == 96
        assert s32_new[0] == 3072 and s32_new[-1] == 6112
        assert s64_new[0] == 6144 and s64_new[-1] == 12224

    def test_every_start_usable_by_some_cell(self):
        starts = unique_window_start_map()
        for k, members in starts.items():
            if BUDGET_FIXED_T in members:
                assert k + W_FIXED <= T_FIXED_T
            if BUDGET_FIXED_M in members:
                assert k + W_FIXED <= 12288


class TestSyntheticIds:
    def _pcid(self, **overrides) -> str:
        kw = {
            "protocol_id": "p1",
            "freeze_id": "f1",
            "evidence_generation_id": "G01",
            "phase": "NULL",
            "rho": "0.8",
            "W": 64,
            "stride": 16,
            "T": 3120,
            "M": 192,
            "data_model_config_hash": _AA,
        }
        kw.update(overrides)
        return physical_cell_id(**kw)

    def test_physical_cell_id_stable_and_sensitive(self):
        h0 = self._pcid()
        assert h0 == self._pcid()
        assert len(h0) == 64
        assert self._pcid(rho="0") != h0
        assert self._pcid(stride=32) != h0
        assert self._pcid(freeze_id="f2") != h0

    def test_rho_canonical_text(self):
        a = self._pcid(rho="0.8")
        b = self._pcid(rho=0, stride=64, T=12288)
        assert len(a) == 64 and len(b) == 64 and a != b

    def test_base_data_unit_ids(self):
        expected_base = H(
            "synthetic_base_series",
            master_replicate_id="b" * 64,
            data_generation_id="D01",
            DGP_family="N_AR",
            rho="0.8",
            raw_length=3120,
            data_model_config_hash=_AA,
        )
        uid = data_unit_id(
            base_series_id=expected_base,
            physical_cell_id=self._pcid(),
            data_generation_id="D01",
        )
        assert uid != expected_base and uid != self._pcid() and len(uid) == 64

    def test_master_replicate_id(self):
        mr = master_replicate_id(
            project_id="owtda-cal-r1", protocol_id="p", freeze_id="f",
            evidence_generation_id="G01", phase="NULL",
            DGP_family="N_AR", replicate_id=1,
        )
        mr2 = master_replicate_id(
            project_id="owtda-cal-r1", protocol_id="p", freeze_id="f",
            evidence_generation_id="G01", phase="NULL",
            DGP_family="N_AR", replicate_id=2,
        )
        assert len(mr) == 64 and mr != mr2
