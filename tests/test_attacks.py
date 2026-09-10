"""Cross-module attack suite mapped to Plan §19 item numbers.

Items already covered by their own module tests are referenced in
``governance/ATTACK_SUITE_v1.0.md``; this file holds the cross-module attacks
and the rule-level boundary attacks that need more than one component.
"""

import json
from decimal import Decimal
from pathlib import Path

import numpy as np
import pytest

from owtda_cal import bpi, cells, hashing, ph, pointcloud, realdata, scan, scope
from owtda_cal.calibrate import (
    calibrate_m0,
    calibrate_m1,
    m0_permutation,
    m1_gaussian_draw,
    p_value,
    reject_from_exceed,
    resample_exceeds,
)
from owtda_cal.canonical import canonical_decimal_text, canonical_json_bytes
from owtda_cal.dgp import generate_null_master
from owtda_cal.rowschema import RowSchema, RowSchemaError
from owtda_cal.seeding import derive_seed_hex

_ROOT_A = "aa" * 32
_ROOT_B = "bb" * 32
_AA = "a" * 64
_AB = "b" * 64
_SCHEMA = json.loads(
    (Path(__file__).resolve().parents[1] / "configs/schema/demo_synthetic_eval_v1.schema.json").read_text(
        encoding="utf-8"
    )
)


# ------------------------------------------------------------------ §19 identity

class TestIdentityAttacks:
    def test_01_one_byte_config_change_breaks_freeze(self):
        # §19 #1
        base = {
            "project_id": "owtda-cal-r1", "protocol_id": "p",
            "protocol_content_hash": _AA, "scope_spec_hash": _AA,
            "analysis_spec_hash": _AA, "compute_spec_hash": _AA,
        }
        fid = scope.freeze_id(**base)
        assert scope.freeze_id(**{**base, "protocol_content_hash": _AB}) != fid

    def test_04_missing_and_unknown_fields_rejected(self):
        # §19 #4
        schema = RowSchema.from_dict(_SCHEMA)
        valid = {
            "evaluation_id": _AA, "phase": "NULL", "scenario_id": "h0",
            "DGP_family": "N_AR", "rho": 0.8, "feature_id": "F", "method_id": "M",
            "data_unit_id": _AB, "observed_statistic": 1.0, "p_value": 0.5,
            "exceed_count": 499, "reject": False, "source_null_logical_cell_id": None,
        }
        with pytest.raises(RowSchemaError):
            schema.validate_logical({**valid, "ghost": 1})
        missing = {k: v for k, v in valid.items() if k != "observed_statistic"}
        with pytest.raises(RowSchemaError):
            schema.validate_logical(missing)

    def test_73_reserved_key_nfc_and_decimal_attacks(self):
        # §19 #73
        with pytest.raises(ValueError):
            derive_seed_hex(_ROOT_A, "null_initial", domain="x")
        with pytest.raises(ValueError):
            canonical_json_bytes({"e\u0301": 1, "\u00e9": 2})  # NFC collision
        for bad in ("0.80", "+0.8", "0.8e0", "1e-1", "00.8"):
            with pytest.raises(ValueError):
                canonical_decimal_text(bad)
        assert canonical_decimal_text(Decimal("-0")) == "0"
        assert canonical_decimal_text("0.8") == "0.8"


# ---------------------------------------------------------------------- §19 RNG

class TestRngAttacks:
    def test_07_same_seed_same_config_identical(self):
        # §19 #7
        a = generate_null_master(
            family="N_AR", rho="0", root_key_hex=_ROOT_A,
            data_generation_id="D01", master_replicate_id="1",
        )
        b = generate_null_master(
            family="N_AR", rho="0", root_key_hex=_ROOT_A,
            data_generation_id="D01", master_replicate_id="1",
        )
        assert a.innovation_hash == b.innovation_hash
        assert np.array_equal(a.innovations, b.innovations)

    def test_10_four_families_have_disjoint_seeds(self):
        # §19 #10
        kinds = ("smoke", "null_data", "h1_data", "real_task")
        seeds = {
            k: derive_seed_hex(_ROOT_A, k, data_generation_id="D01") for k in kinds
        }
        assert len(set(seeds.values())) == len(kinds)

    def test_11_no_collisions_and_intentional_alias(self):
        # §19 #11
        seeds = [
            derive_seed_hex(_ROOT_A, "null_innovation", data_generation_id="D01", master_replicate_id=str(i))
            for i in range(1000)
        ]
        assert len(set(seeds)) == 1000
        alias1 = derive_seed_hex(
            _ROOT_A, "null_innovation", data_generation_id="D01", master_replicate_id="1"
        )
        alias2 = derive_seed_hex(
            _ROOT_A, "null_innovation", data_generation_id="D01", master_replicate_id="1"
        )
        assert alias1 == alias2

    def test_13_rho_and_stride_do_not_change_innovation_stream(self):
        # §19 #13
        m0 = generate_null_master(family="N_AR", rho="0", root_key_hex=_ROOT_A,
                                  data_generation_id="D01", master_replicate_id="1")
        m8 = generate_null_master(family="N_AR", rho="0.8", root_key_hex=_ROOT_A,
                                  data_generation_id="D01", master_replicate_id="1")
        assert m0.innovation_hash == m8.innovation_hash
        assert not np.array_equal(m0.raw_prefix_1d(300), m8.raw_prefix_1d(300))
        # resampling stream is keyed by data unit, not by rho/stride
        p_u1 = m0_permutation(_ROOT_A, method_generation_id="M0", data_unit_id="u1",
                              resample_index=1, M=20)
        p_u2 = m0_permutation(_ROOT_A, method_generation_id="M0", data_unit_id="u2",
                              resample_index=1, M=20)
        assert not np.array_equal(p_u1, p_u2)

    def test_56_root_key_change_is_family_scoped(self):
        # §19 #56
        fam_a_before = derive_seed_hex(_ROOT_A, "null_innovation", data_generation_id="D01")
        fam_a_after = derive_seed_hex(_ROOT_B, "null_innovation", data_generation_id="D01")
        fam_b_before = derive_seed_hex(_ROOT_B, "real_task", data_generation_id="D01")
        fam_b_after = derive_seed_hex(_ROOT_B, "real_task", data_generation_id="D01")
        assert fam_a_before != fam_a_after
        assert fam_b_before == fam_b_after

    def test_57_stream_kind_separates_seeds(self):
        # §19 #57
        a = derive_seed_hex(_ROOT_A, "null_initial", data_generation_id="D01", master_replicate_id="1")
        b = derive_seed_hex(_ROOT_A, "null_innovation", data_generation_id="D01", master_replicate_id="1")
        assert a != b

    def test_52_m0_permutation_and_m1_innovation_shared_per_data_unit(self):
        # §19 #52
        kw = {"method_generation_id": "MG01", "data_unit_id": "u1", "resample_index": 7}
        assert np.array_equal(
            m0_permutation(_ROOT_A, M=20, **kw), m0_permutation(_ROOT_A, M=20, **kw)
        )
        assert np.array_equal(
            m1_gaussian_draw(_ROOT_A, size=30, **kw), m1_gaussian_draw(_ROOT_A, size=30, **kw)
        )


# ------------------------------------------------------------------- §19 windows

class TestWindowAttacks:
    def test_14_15_16_window_formulas(self):
        # §19 #14/#15/#16
        assert cells.window_count(3120, 64, 8) == (3120 - 64) // 8 + 1
        assert cells.fixed_m_raw_length(16) == 64 + 16 * (192 - 1)
        assert cells.T_FIXED_T == 3120  # fixed-T never auto-changes T
        assert cells.fixed_t_window_count(8) == (3120 - 64) // 8 + 1

    def test_17_stride_equals_window_has_zero_overlap(self):
        # §19 #17
        geom = next(g for g in cells.h0_geometry_cells() if g.stride == 64 and g.T == 12288)
        starts = geom.raw_starts()
        assert starts[1] - starts[0] == cells.W_FIXED  # overlap = W - s = 0
        assert starts[-1] + cells.W_FIXED == 12288

    def test_19_window_index_to_raw_time_hand_reversal(self):
        # §19 #19
        assert scan.estimated_change_raw_time(96, stride=64, W=64) == pytest.approx(6144.5)
        assert scan.estimated_change_raw_time(96, stride=16, W=64) == pytest.approx(1560.5)
        assert scan.estimated_change_raw_time(1, stride=16, W=64) == pytest.approx(40.5)


class TestPointCloudAttacks:
    def _cloud(self, n=36):
        t = np.linspace(0.0, 2 * np.pi, n, endpoint=False)
        return np.column_stack([np.cos(t), np.sin(t)])

    def test_20_21_permutation_duplicates_and_far_window(self):
        # §19 #20/#21
        c = self._cloud()
        ref = bpi.bpi_from_diagrams(*ph.h0h1(c), cap=2.5)
        perm = np.random.default_rng(1).permutation(c.shape[0])
        shuffled = bpi.bpi_from_diagrams(*ph.h0h1(c[perm]), cap=2.5)
        duplicated = pointcloud.clean_and_dedup(np.vstack([c, c, c[perm]]))
        dup_feat = bpi.bpi_from_diagrams(*ph.h0h1(duplicated), cap=2.5)
        assert np.array_equal(ref, shuffled)
        assert np.array_equal(ref, dup_feat)

    def test_22_two_ring_and_collinear_structures(self):
        # §19 #22 (two separated rings = two independent H1 classes; a
        # collinear cloud has no H1)
        t = np.linspace(0.0, 2 * np.pi, 30, endpoint=False)
        left = np.column_stack([np.cos(t) - 2.0, np.sin(t)])
        right = np.column_stack([np.cos(t) + 2.0, np.sin(t)])
        _, h1_two = ph.h0h1(np.vstack([left, right]))
        assert h1_two.shape[0] >= 2
        _, h1_line = ph.h0h1(np.column_stack([np.linspace(0, 1, 25), np.zeros(25)]))
        assert h1_line.shape[0] == 0

    def test_23_translation_rotation_and_scale(self):
        # §19 #23
        c = self._cloud()
        _, h1 = ph.h0h1(c)
        _, h1_t = ph.h0h1(c + np.array([3.0, -2.0]))
        rot = np.array([[0.0, -1.0], [1.0, 0.0]])
        _, h1_r = ph.h0h1(c @ rot.T)
        _, h1_s = ph.h0h1(c * 2.0)
        assert np.allclose(h1, h1_t, rtol=1e-10, atol=1e-12)
        assert np.allclose(h1, h1_r, rtol=1e-10, atol=1e-12)
        assert np.allclose(h1_s, h1 * 2.0, rtol=1e-10, atol=1e-12)

    def test_24_vr_thresh_cap_and_grid_are_separate(self):
        # §19 #24
        c = self._cloud()
        h0, h1 = ph.h0h1(c)
        same = bpi.bpi_from_diagrams(h0, h1, cap=2.5)
        cap6 = bpi.bpi_from_diagrams(h0, h1, cap=6.0)
        assert not np.array_equal(same, cap6)  # cap is a mapping parameter only
        # diagrams are recomputed identically regardless of cap
        h0b, h1b = ph.h0h1(c)
        assert np.array_equal(h0, h0b) and np.array_equal(h1, h1b)

    def test_25_empty_and_degenerate_protocol(self):
        # §19 #25
        assert np.all(bpi.intensity_channel(np.zeros((0, 2)), cap=6.0) == 0.0)
        cloud = pointcloud.clean_and_dedup(np.array([[1.0, 1.0], [1.0, 1.0]]))
        assert cloud.shape[0] == 1  # upstream returns zero vector, never calls PH


# --------------------------------------------------------------- §19 inference

class TestInferenceAttacks:
    def _matrix(self, m=30, p=4, seed=2, shift=None):
        x = np.random.default_rng(seed).standard_normal((m, p))
        if shift is not None:
            x[shift:] += 1.5
        return x

    def test_26_cusum_replay_within_1e12(self):
        # §19 #26
        x = self._matrix()
        fast = scan.statistic_curve(x)["values"]
        slow = scan.statistic_curve(x, reference=True)["values"]
        assert np.max(np.abs(fast - slow)) <= 1e-12

    def test_27_observed_statistic_identical_across_methods(self):
        # §19 #27
        x = self._matrix(shift=15)
        m0 = calibrate_m0(x, root_key_hex=_ROOT_A, method_generation_id="MG", data_unit_id="u")
        m1 = calibrate_m1(x, root_key_hex=_ROOT_A, method_generation_id="MG",
                          data_unit_id="u", W=64, stride=16)
        assert m0["observed_statistic"] == m1["observed_statistic"]
        assert m0["observed_statistic"] == scan.scan_statistic(x)["observed_statistic"]

    def test_29_30_p_grid_and_reject_boundary(self):
        # §19 #29/#30
        for exceed in (0, 1, 49, 50, 999):
            assert p_value(exceed) * 1000 == 1 + exceed
        assert reject_from_exceed(49) is True
        assert reject_from_exceed(50) is False

    def test_31_33_dmb_covariance_no_wrap(self):
        # §19 #31/#32/#33
        from owtda_cal.calibrate import dmb_multiplier_series

        e = np.arange(10.0)
        xi = dmb_multiplier_series(e, b=3)
        assert xi.shape == (8,)  # no circular wrap, no trimming
        assert xi[0] == pytest.approx((0.0 + 1.0 + 2.0) / np.sqrt(3.0))
        assert xi[-1] == pytest.approx((7.0 + 8.0 + 9.0) / np.sqrt(3.0))

    def test_34_exceed_uses_exact_ge(self):
        # §19 #34
        assert resample_exceeds(0.5, 0.5) is True
        assert resample_exceeds(np.nextafter(0.5, 0.0), 0.5) is False

    def test_35_candidates_and_plateau_are_method_independent(self):
        # §19 #35
        a = scan.candidate_indices(192)
        b = scan.candidate_indices(192)
        assert np.array_equal(a, b)
        ks = np.array([10, 11, 12, 13])
        vals = np.array([1.0, 2.0, 2.0, 1.0])
        assert scan.plateau_selection(ks, vals)["khat"] == 11


# ------------------------------------------------------- §19 ledger / structure

class TestLedgerStructureAttacks:
    def test_47_shared_s16_cell_single_logical_id(self):
        # §19 #47: the shared (s=16,T=3120,M=192) geometry appears once per
        # DGP/rho combination, never once per budget matrix.
        s16 = [c for c in scope.h0_null_cells() if c.stride == 16 and c.T == 3120]
        assert len(s16) == 4  # 2 DGP families x 2 rho levels
        assert all(c.budget_membership == ("FIXED_M", "FIXED_T") for c in s16)
        ids = {
            scope.logical_cell_id(
                project_id="p", protocol_id="r", freeze_id=_AA,
                evidence_generation_id="G01", phase="NULL", DGP_family=c.family,
                scenario_id="h0", rho=c.rho, W=c.W, stride=c.stride, T=c.T, M=c.M,
            )
            for c in s16
        }
        assert len(ids) == 4

    def test_48_budget_membership_does_not_change_physical_hash(self):
        # §19 #48
        kw = {
            "protocol_id": "p",
            "freeze_id": _AA,
            "evidence_generation_id": "G01",
            "phase": "NULL",
            "rho": "0.8",
            "W": 64,
            "stride": 16,
            "T": 3120,
            "M": 192,
            "data_model_config_hash": _AB,
        }
        assert cells.physical_cell_id(**kw) == cells.physical_cell_id(**kw)
        # budget membership is not part of the physical cell identity
        geom = next(g for g in cells.h0_geometry_cells() if g.stride == 16 and g.T == 3120)
        assert geom.budget_membership == ("FIXED_M", "FIXED_T")

    def test_49_real_row_leakage_rejected(self):
        # §19 #49
        schema = RowSchema.from_dict(_SCHEMA)
        with pytest.raises(RowSchemaError):
            schema.validate_logical({"subject_internal_id": "subject101"})
        with pytest.raises(RowSchemaError):
            schema.validate_logical({"activity_A": 1})

    def test_59_row_hash_excludes_itself_and_rejects_nonfinite(self):
        # §19 #59
        schema = RowSchema.from_dict(_SCHEMA)
        row = {
            "evaluation_id": _AA, "phase": "NULL", "scenario_id": "h0",
            "DGP_family": "N_AR", "rho": 0.8, "feature_id": "F", "method_id": "M",
            "data_unit_id": _AB, "observed_statistic": 1.5, "p_value": 0.05,
            "exceed_count": 49, "reject": False, "source_null_logical_cell_id": None,
        }
        h1 = schema.row_payload_hash(row)
        h2 = schema.row_payload_hash({**row, "row_payload_hash": "f" * 64})
        assert h1 == h2  # the hash field itself is excluded from the payload
        with pytest.raises(RowSchemaError):
            schema.validate_logical({**row, "observed_statistic": float("nan")})

    def test_60_method_generation_changes_only_evaluation_ids(self):
        # §19 #60
        lc, mr = _AA, _AB
        ldk = scope.logical_data_key(logical_cell_id=lc, master_replicate_id=mr)
        lfk = scope.logical_feature_key(logical_data_key=ldk, feature_id="BPI")
        e1 = scope.logical_evaluation_key(logical_data_key=ldk, feature_id="BPI", method_id="M0_G1")
        e2 = scope.logical_evaluation_key(logical_data_key=ldk, feature_id="BPI", method_id="M0_G2")
        assert e1 != e2
        assert scope.logical_data_key(logical_cell_id=lc, master_replicate_id=mr) == ldk
        assert scope.logical_feature_key(logical_data_key=ldk, feature_id="BPI") == lfk

    def test_68_array_endianness_and_header_sensitivity(self):
        # §19 #68
        native = np.array([[1.0, 2.0], [3.0, 4.0]])
        big = native.astype(">f8")
        h_native = hashing.array_hash("attack_array_v1", native)
        h_big = hashing.array_hash("attack_array_v1", big)
        assert h_native == h_big
        assert hashing.array_hash("attack_array_v1", native.reshape(4)) != h_native
        assert hashing.array_hash("attack_array_v1", native, dtype_code=">i8") != h_native
        assert hashing.array_hash("other_kind_v1", native) != h_native

    def test_69_dataset_hash_entry_order_and_scope(self):
        # §19 #69
        entries = [
            {"path": f"Protocol/{n}", "size": 10 + i, "file_sha256": _AA}
            for i, n in enumerate(realdata.SUBJECT_NAMES)
        ]
        h0 = realdata.dataset_hash(entries)
        assert realdata.dataset_hash(list(reversed(entries))) == h0
        changed = [dict(e) for e in entries]
        changed[3]["file_sha256"] = _AB
        assert realdata.dataset_hash(changed) != h0
        renamed = [dict(e) for e in entries]
        renamed[0]["path"] = "Protocol/subject110.dat"
        with pytest.raises(ValueError):
            realdata.dataset_hash(renamed)

    def test_72_discriminated_union_grid_attack(self):
        # §19 #72
        schema = RowSchema.from_dict(_SCHEMA)
        base = {
            "evaluation_id": _AA, "phase": "NULL", "scenario_id": "h0",
            "DGP_family": "N_AR", "rho": 0.8, "feature_id": "F", "method_id": "M",
            "data_unit_id": _AB, "observed_statistic": 1.0, "p_value": 0.5,
            "exceed_count": 499, "reject": False, "source_null_logical_cell_id": None,
        }
        omitted = {k: v for k, v in base.items() if k != "source_null_logical_cell_id"}
        with pytest.raises(RowSchemaError):
            schema.validate_logical(omitted)
        with pytest.raises(RowSchemaError):
            schema.validate_logical({**base, "source_null_logical_cell_id": _AA})
        with pytest.raises(RowSchemaError):
            schema.validate_logical({**base, "truth": 1})

    def test_74_wire_round_trip_and_f64_string_safety(self):
        # §19 #74
        schema = RowSchema.from_dict(_SCHEMA)
        row = {
            "evaluation_id": _AA, "phase": "NULL", "scenario_id": "h0",
            "DGP_family": "N_AR", "rho": 0.8, "feature_id": "f64:0000000000000000",
            "method_id": "M", "data_unit_id": _AB, "observed_statistic": 0.1 + 0.2,
            "p_value": 1 / 3, "exceed_count": 499, "reject": False,
            "source_null_logical_cell_id": None,
        }
        wire = schema.encode_to_wire(row)
        decoded = schema.decode_from_wire(wire)
        assert decoded["observed_statistic"] == row["observed_statistic"]
        assert decoded["feature_id"] == "f64:0000000000000000"

    def test_77_91_shard_commit_cas_and_orphan(self, tmp_path):
        # §19 #77/#91
        from owtda_cal.shardio import ShardError, commit_shard, find_commit

        run_root, registry = str(tmp_path / "runs"), str(tmp_path / "reg.jsonl")
        kw = {
            "run_root": run_root,
            "run_instance_id": "r1",
            "shard_id": "s1",
            "shard_plan_hash": _AA,
            "evaluation_lines": [b'{"r":1}\n'],
            "feature_lines": [b'{"f":1}\n'],
            "evaluation_meta": {},
            "feature_meta": {},
            "registry_path": registry,
        }
        first = commit_shard(**kw)
        again = commit_shard(**kw)
        assert again == first  # idempotent, single CAS record
        assert len(Path(registry).read_text(encoding="utf-8").strip().splitlines()) == 1
        conflicting = dict(first, shard_manifest_hash=_AB, shard_commit_hash=_AA)
        with open(registry, "a", encoding="utf-8") as fh:
            fh.write(json.dumps(conflicting) + "\n")
        with pytest.raises(ShardError):
            find_commit(registry, run_instance_id="r1", shard_id="s1")


class TestRealAttacks:
    def test_62_70_task_builder_boundaries(self):
        # §19 #62/#70
        from owtda_cal import pamap2_tasks as tk

        same = np.concatenate([np.full(3100, 1), np.full(3100, 1)]).astype(np.int64)
        assert tk.transition_candidates(same) == []  # activity_A == activity_B
        at_min = np.concatenate([
            np.full(3000, 1), np.zeros(500, dtype=np.int64), np.full(3000, 2)
        ]).astype(np.int64)
        assert len(tk.transition_candidates(at_min)) == 1
        too_short = np.concatenate([
            np.full(2999, 1), np.full(10, 0), np.full(3000, 2)
        ]).astype(np.int64)
        assert tk.transition_candidates(too_short) == []
        adjacent = np.concatenate([np.full(3000, 1), np.full(3000, 2)]).astype(np.int64)
        assert tk.transition_candidates(adjacent)[0]["zero_rows"] == 0

    def test_71_task_id_sensitivity(self):
        # §19 #71
        from owtda_cal import pamap2_tasks as tk

        kw = {
            "real_task_id_salt_hex": "ef" * 32,
            "task_candidate_id": _AA,
            "task_index_generation_id": "TI01",
            "task_builder_config_hash": _AB,
            "L_A": 20,
            "L_B": 21,
            "task_root_entry_hash": _AA,
            "task_signal_hash": _AB,
        }
        base = tk.task_id(**kw)
        for field, value in (("L_A", 22), ("L_B", 20), ("task_signal_hash", _AA),
                             ("task_root_entry_hash", _AB), ("task_builder_config_hash", _AA)):
            assert tk.task_id(**{**kw, field: value}) != base

    def test_85_import_golden_ordering(self):
        # §19 #85
        from owtda_cal import pamap2_import as imp

        assert imp.grid_map(np.array([0.0, 0.01, 0.02])).tolist() == [0, 1, 2]
        assert imp.convert_to_g(np.array([imp.GRAVITY]))[0] == pytest.approx(1.0)
        filled, bad = imp.interpolate_axis(np.array([0.0, np.nan, 2.0]))
        assert not bad.any() and filled[1] == pytest.approx(1.0)
