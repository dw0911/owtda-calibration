"""H1 alternative DGP contracts (Plan §12.1-§12.2, §15.2-§15.3).

Covers: change-point rule and window-centre alignment, RNG consumption shapes,
shared latent/noise draws across rho/scenario/stride, the exact circle /
figure-eight / mean-shift skeletons, the zero-effect rejoining of the N-CIRCLE
H0 ``null_model_config_hash``, and the alternative-specific data-model identity.
"""

import numpy as np
import pytest

from owtda_cal import cells, dgp, scan, scope, smoke_ids

ROOT_KEY = "ab" * 32
GENERATION = "S02"
REPLICATE = "smoke_master_replicate_placeholder"


def _master(scenario: str, rho: str, *, root_key_hex: str = ROOT_KEY,
            generation: str = GENERATION, replicate: str = REPLICATE):
    return dgp.generate_h1_master(
        scenario=scenario,
        rho=rho,
        root_key_hex=root_key_hex,
        data_generation_id=generation,
        master_replicate_id=replicate,
    )


def _skeleton(master, T: int) -> np.ndarray:
    """Noise-free skeleton recovered from the raw prefix (up to fp rounding)."""
    return master.raw_prefix(T) - dgp.NOISE_SCALE_FLOAT * master.noise[:T]


class TestChangePoint:
    def test_floor_half_of_T(self):
        assert dgp.h1_change_point(12288) == 6144
        assert dgp.h1_change_point(3120) == 1560
        for cell in scope.h1_alt_cells():
            assert dgp.h1_change_point(cell.T) == cell.T // 2

    def test_rejects_degenerate_T(self):
        with pytest.raises(ValueError):
            dgp.h1_change_point(1)

    def test_boundary_sits_between_k96_and_k97_centres(self):
        """Plan §12.1: tau must be the midpoint of the k=96/97 window centres."""
        for cell in scope.h1_alt_cells():
            tau = dgp.h1_change_point(cell.T)
            centre_96 = (96 - 1) * cell.stride + cell.W / 2
            centre_97 = (97 - 1) * cell.stride + cell.W / 2
            assert (centre_96 + centre_97) / 2 == tau

    def test_tau_true_is_the_k96_candidate_centre(self):
        """Plan §12.4 blocking gate, enforced rather than merely documented.

        Two centre conventions appear in the code and differ by the half-sample
        offset (both are correct, they describe different objects):

        * scan convention, ``(k-1/2)s + (W+1)/2`` -- the raw *time* of window k,
          which is ``tau_true = tau + 1/2`` at k=96;
        * sample-centre convention, ``(k-1)s + W/2`` -- whose k=96/k=97 midpoint
          is ``tau`` itself.

        A builder that cannot satisfy the first equality must be blocked.  The gate
        is stated per *geometry*, not per cross product: the non-overlapping H1
        cell is (s=64, T=12288) and the overlapping one is (s=16, T=3120).
        """
        for cell in scope.h1_alt_cells():
            tau = dgp.h1_change_point(cell.T)
            centre_96 = scan.estimated_change_raw_time(
                96, stride=cell.stride, W=cell.W
            )
            centre_97 = scan.estimated_change_raw_time(
                97, stride=cell.stride, W=cell.W
            )
            assert centre_96 == tau + 0.5
            assert centre_97 - centre_96 == cell.stride
            sample_centre_96 = (96 - 1) * cell.stride + cell.W / 2
            sample_centre_97 = (97 - 1) * cell.stride + cell.W / 2
            assert (sample_centre_96 + sample_centre_97) / 2 == float(tau)

    def test_pre_effect_covers_exactly_the_first_tau_samples(self):
        for scenario in dgp.H1_SCENARIOS:
            master = _master(scenario, "0")
            T = 3120
            tau = dgp.h1_change_point(T)
            circle = master.circle[:T]
            if scenario == dgp.H1_SCENARIO_SHAPE:
                post = master.shape_map[:T]
            else:
                post = circle + dgp.H1_MEAN_SHIFT_DELTA_FLOAT * np.asarray(
                    master.shift_direction_v
                )
            skeleton = _skeleton(master, T)
            assert np.allclose(skeleton[:tau], circle[:tau], rtol=0, atol=1e-15)
            assert np.allclose(skeleton[tau:], post[tau:], rtol=0, atol=1e-15)


class TestRngConsumption:
    def test_draw_shapes_and_dtypes(self):
        master = _master(dgp.H1_SCENARIO_SHAPE, "0.8")
        assert isinstance(master.initial_value, float)
        assert master.innovations.shape == (cells.L_LATENT,)
        assert master.noise.shape == (cells.L_MASTER, 2)
        assert master.innovations.dtype == np.float64
        assert master.noise.dtype == np.float64
        assert master.innovations.flags["C_CONTIGUOUS"]
        assert master.noise.flags["C_CONTIGUOUS"]
        assert master.latent_u.shape == (cells.L_MASTER,)
        assert master.circle.shape == (cells.L_MASTER, 2)

    def test_shift_direction_is_a_single_random_draw(self):
        from owtda_cal.seeding import make_rng

        master = _master(dgp.H1_SCENARIO_MEAN, "0")
        expected = float(
            make_rng(
                ROOT_KEY,
                "h1_shift_direction",
                data_generation_id=GENERATION,
                master_replicate_id=REPLICATE,
            ).random(dtype=np.float64)
        )
        assert master.shift_direction_value == expected
        assert 0.0 <= master.shift_direction_value < 1.0
        angle = 2.0 * np.pi * master.shift_direction_value
        assert master.shift_direction_v == pytest.approx(
            (float(np.cos(angle)), float(np.sin(angle))), abs=0.0
        )
        assert len(master.shift_direction_seed) == 32

    def test_shape_alternative_reports_no_shift_direction(self):
        master = _master(dgp.H1_SCENARIO_SHAPE, "0")
        assert master.shift_direction_value is None
        assert master.shift_direction_v is None
        assert master.shift_direction_seed is None

    def test_shift_direction_is_shared_by_derived_cells(self):
        """One draw per replicate serves every rho/stride of the alternative."""
        values = {
            (rho, generation): _master(
                dgp.H1_SCENARIO_MEAN, rho, generation=generation
            ).shift_direction_value
            for rho in scope.RHO_LEVELS
            for generation in (GENERATION,)
        }
        assert len(set(values.values())) == 1

    def test_rho_free_and_scenario_free_base_draws(self):
        """Plan §15.2: data keys exclude alternative, rho, s, T and M."""
        a = _master(dgp.H1_SCENARIO_SHAPE, "0")
        b = _master(dgp.H1_SCENARIO_MEAN, "0")
        c = _master(dgp.H1_SCENARIO_MEAN, "0.8")
        assert a.innovation_hash == b.innovation_hash == c.innovation_hash
        assert a.noise_hash == b.noise_hash == c.noise_hash
        # the two alternatives share one latent copula path ...
        assert np.array_equal(a.latent_u, b.latent_u)
        # ... while rho changes the recursion, hence the path
        assert not np.array_equal(b.latent_u, c.latent_u)
        assert not np.array_equal(a.raw_prefix(3120), b.raw_prefix(3120))

    def test_rho_changes_the_latent_path_but_not_the_innovations(self):
        a = _master(dgp.H1_SCENARIO_SHAPE, "0")
        b = _master(dgp.H1_SCENARIO_SHAPE, "0.8")
        assert a.innovation_hash == b.innovation_hash
        assert not np.array_equal(a.latent_u, b.latent_u)

    def test_stream_kinds_are_h1_prefixed(self):
        from owtda_cal.seeding import derive_seed_hex

        assert derive_seed_hex(
            ROOT_KEY,
            "h1_shift_direction",
            data_generation_id=GENERATION,
            master_replicate_id=REPLICATE,
        ) == _master(dgp.H1_SCENARIO_MEAN, "0").shift_direction_seed


class TestEffectSkeletons:
    def test_shape_change_switches_circle_to_figure_eight(self):
        master = _master(dgp.H1_SCENARIO_SHAPE, "0.8")
        u = master.latent_u
        expected_circle = np.column_stack(
            [np.cos(2 * np.pi * u), np.sin(2 * np.pi * u)]
        )
        expected_eight = np.column_stack(
            [np.sin(2 * np.pi * u), np.sin(4 * np.pi * u)]
        )
        assert np.array_equal(master.circle, expected_circle)
        assert np.array_equal(master.shape_map, expected_eight)

    def test_figure_eight_identity_on_the_post_effect_half(self):
        """y = sin 4piu, x = sin 2piu  =>  y^2 = 4 x^2 (1 - x^2)."""
        master = _master(dgp.H1_SCENARIO_SHAPE, "0")
        tau = dgp.h1_change_point(cells.L_MASTER)
        x = master.shape_map[tau:, 0]
        y = master.shape_map[tau:, 1]
        assert np.abs(y**2 - 4.0 * x**2 * (1.0 - x**2)).max() < 1e-12

    def test_pre_effect_half_is_the_unit_circle(self):
        master = _master(dgp.H1_SCENARIO_SHAPE, "0.8")
        tau = dgp.h1_change_point(cells.L_MASTER)
        radius = np.linalg.norm(master.circle[:tau], axis=1)
        assert np.abs(radius - 1.0).max() < 1e-12

    def test_mean_shift_is_a_constant_unit_circle_offset(self):
        master = _master(dgp.H1_SCENARIO_MEAN, "0.8")
        direction = np.asarray(master.shift_direction_v)
        assert np.linalg.norm(direction) == pytest.approx(1.0, abs=1e-12)
        T = 3120
        tau = dgp.h1_change_point(T)
        skeleton = _skeleton(master, T)
        circle = master.circle[:T]
        offset = skeleton[tau:] - circle[tau:]
        assert np.allclose(offset, 0.5 * direction, rtol=0, atol=1e-15)
        assert np.allclose(skeleton[:tau], circle[:tau], rtol=0, atol=1e-15)

    def test_observation_noise_is_continuous_across_the_boundary(self):
        """The same eta_t is added on both sides of tau (no re-draw)."""
        for scenario in dgp.H1_SCENARIOS:
            master = _master(scenario, "0")
            raw = master.raw_prefix(cells.L_MASTER)
            assert np.allclose(
                raw - dgp.NOISE_SCALE_FLOAT * master.noise,
                _skeleton(master, cells.L_MASTER),
                rtol=0,
                atol=1e-15,
            )

    def test_shared_draws_agree_between_strides(self):
        master = _master(dgp.H1_SCENARIO_SHAPE, "0.8")
        short = master.raw_prefix(3120)
        long = master.raw_prefix(cells.L_MASTER)
        # both prefixes are pre-effect for t <= 1560 (tau(3120))
        assert np.array_equal(short[:1560], long[:1560])
        assert not np.array_equal(short[1560:], long[1560:3120])

    def test_marginal_moments_are_close_on_both_sides(self):
        """Sanity band (not a scientific gate): E=0, Cov=I/2 on both sides."""
        for rho in scope.RHO_LEVELS:
            master = _master(dgp.H1_SCENARIO_SHAPE, rho)
            tau = dgp.h1_change_point(cells.L_MASTER)
            for half in (master.circle[:tau], master.shape_map[tau:]):
                assert np.abs(half.mean(axis=0)).max() < 0.08
                assert np.abs(np.cov(half.T) - 0.5 * np.eye(2)).max() < 0.12

    def test_raw_prefix_is_float64_c_order(self):
        master = _master(dgp.H1_SCENARIO_MEAN, "0")
        raw = master.raw_prefix(3120)
        assert raw.shape == (3120, 2)
        assert raw.dtype == np.float64
        assert raw.flags["C_CONTIGUOUS"]

    def test_raw_prefix_rejects_out_of_range_T(self):
        master = _master(dgp.H1_SCENARIO_MEAN, "0")
        for bad in (1, cells.L_MASTER + 1):
            with pytest.raises(ValueError):
                master.raw_prefix(bad)


class TestDataModelIdentity:
    def test_alternatives_differ_only_in_scenario(self):
        shape = dgp.h1_data_model_spec(dgp.H1_SCENARIO_SHAPE, "0.8")
        mean = dgp.h1_data_model_spec(dgp.H1_SCENARIO_MEAN, "0.8")
        assert shape["scenario_id"] != mean["scenario_id"]
        assert dgp.data_model_config_hash(shape) != dgp.data_model_config_hash(mean)
        assert dgp.data_model_config_hash(shape) == dgp.data_model_config_hash(
            dgp.h1_data_model_spec(dgp.H1_SCENARIO_SHAPE, "0.8")
        )

    def test_data_model_spec_excludes_geometry(self):
        spec = dgp.h1_data_model_spec(dgp.H1_SCENARIO_SHAPE, "0")
        for key in ("W", "stride", "s", "T", "M", "phase"):
            assert key not in spec

    def test_unknown_scenario_rejected(self):
        with pytest.raises(ValueError):
            dgp.h1_data_model_spec("topology_only", "0")
        with pytest.raises(ValueError):
            _master("topology_only", "0")

    def test_family_is_shared_by_both_alternatives(self):
        assert dgp.h1_data_model_spec(dgp.H1_SCENARIO_SHAPE, "0")["family"] == (
            dgp.DGP_FAMILY_H1
        )
        assert dgp.h1_data_model_spec(dgp.H1_SCENARIO_MEAN, "0")["family"] == (
            dgp.DGP_FAMILY_H1
        )
        assert scope.H1_FAMILY == dgp.DGP_FAMILY_H1


class TestNullSignatureRejoining:
    def test_geometry_matches_the_n_circle_h0_cells(self):
        h0 = {
            (cell.rho, cell.stride): (cell.W, cell.T, cell.M)
            for cell in scope.h0_null_cells()
            if cell.family == dgp.DGP_FAMILY_N_CIRCLE
        }
        for cell in scope.h1_alt_cells():
            assert h0[(cell.rho, cell.stride)] == (cell.W, cell.T, cell.M)

    def test_signature_is_scenario_and_phase_independent(self):
        """Every H1 cell rejoins the matching N-CIRCLE H0 model identity."""
        for cell in scope.h1_alt_cells():
            signature = dgp.build_null_signature(
                rho=cell.rho, W=cell.W, stride=cell.stride, T=cell.T, M=cell.M
            )
            assert signature == dgp.build_null_signature(
                rho=cell.rho, W=cell.W, stride=cell.stride, T=cell.T, M=cell.M
            )
        shape = dgp.build_null_signature(rho="0", W=64, stride=64, T=12288, M=192)
        mean = dgp.build_null_signature(rho="0", W=64, stride=64, T=12288, M=192)
        assert shape == mean

    def test_signature_separates_geometries(self):
        base = dgp.build_null_signature(rho="0", W=64, stride=64, T=12288, M=192)
        assert base != dgp.build_null_signature(
            rho="0", W=64, stride=16, T=3120, M=192
        )
        assert base != dgp.build_null_signature(
            rho="0.8", W=64, stride=64, T=12288, M=192
        )

    @pytest.mark.parametrize(
        "constant,value",
        [
            ("OBSERVATION_NOISE_N_CIRCLE", "iid_N2_0_I2_times_0.09"),
            ("INITIAL_INDEX", -2000),
            ("DISCARDED_INDICES", "-1999..0"),
            ("ROTATION", "Q90"),
            ("N_CIRCLE_VERSION", "N_CIRCLE_V2"),
            ("LATENT_LAW_N_CIRCLE", "other_law"),
        ],
    )
    def test_signature_tracks_the_null_dgp_constants(
        self, monkeypatch, constant, value
    ):
        base = dgp.build_null_signature(rho="0", W=64, stride=64, T=12288, M=192)
        monkeypatch.setattr(dgp, constant, value)
        assert base != dgp.build_null_signature(
            rho="0", W=64, stride=64, T=12288, M=192
        )

    def test_signature_payload_carries_no_effect_terms(self):
        from owtda_cal.canonical import canonical_decimal_text
        from owtda_cal.identity import H

        cell = scope.h1_alt_cells()[0]
        assert dgp.build_null_signature(
            rho=cell.rho, W=cell.W, stride=cell.stride, T=cell.T, M=cell.M
        ) == H(
            dgp.NULL_SIGNATURE_KIND,
            null_family=dgp.NULL_FAMILY_N_CIRCLE,
            generator_version=dgp.N_CIRCLE_VERSION,
            latent_law=dgp.LATENT_LAW_N_CIRCLE,
            initial_index=dgp.INITIAL_INDEX,
            discarded_indices=dgp.DISCARDED_INDICES,
            rho=canonical_decimal_text(cell.rho),
            observation_noise=dgp.OBSERVATION_NOISE_N_CIRCLE,
            rotation=dgp.ROTATION,
            unit=dgp.UNIT,
            W=cell.W,
            stride=cell.stride,
            T=cell.T,
            M=cell.M,
        )


class TestMapLaws:
    """The two maps' *laws*: identical mean and covariance, exactly (Plan §12.1)."""

    @staticmethod
    def _maps(u: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
        return (
            np.column_stack([np.cos(2 * np.pi * u), np.sin(2 * np.pi * u)]),
            np.column_stack([np.sin(2 * np.pi * u), np.sin(4 * np.pi * u)]),
        )

    def test_the_two_maps_share_mean_and_covariance(self):
        # The trapezoid rule is exact for these integer harmonics, so the values
        # below are machine-precision, not Monte-Carlo estimates.
        u = (np.arange(4096) + 0.5) / 4096
        circle, figure = self._maps(u)
        c_mean = circle.mean(axis=0)
        f_mean = figure.mean(axis=0)
        c_cov = np.cov(circle, rowvar=False, bias=True)
        f_cov = np.cov(figure, rowvar=False, bias=True)
        assert np.abs(c_mean - f_mean).max() <= 1e-12
        assert np.abs(c_cov - f_cov).max() <= 1e-12
        assert np.abs(c_cov - 0.5 * np.eye(2)).max() <= 1e-12
        assert np.abs(f_cov - 0.5 * np.eye(2)).max() <= 1e-12
        assert np.abs(f_mean).max() <= 1e-12


class TestMasterPrefixConsistency:
    def test_short_length_is_a_bitwise_prefix_of_the_long_length(self):
        """One master serves every T, but the change point is a *cell* property.

        Only two things carry across lengths: the draws are shared prefixes, and
        the pre-effect segment agrees bitwise up to the *shorter* tau.  Beyond it
        the series intentionally differ, because ``tau = floor(T/2)`` differs --
        this test pins that difference so it can never be mistaken for reuse.
        """
        for scenario in dgp.H1_SCENARIOS:
            master = _master(scenario, "0.8")
            tau_short = dgp.h1_change_point(cells.T_FIXED_T)
            tau_long = dgp.h1_change_point(cells.L_MASTER)
            assert tau_short < tau_long
            assert np.array_equal(
                master.noise[: cells.T_FIXED_T],
                master.noise[: cells.L_MASTER][: cells.T_FIXED_T],
            )
            short = master.raw_prefix(cells.T_FIXED_T)
            long = master.raw_prefix(cells.L_MASTER)
            assert np.array_equal(short[:tau_short], long[:tau_short])
            assert not np.array_equal(short, long[: cells.T_FIXED_T])


class TestSmokeStreamOverride:
    def test_smoke_streams_are_isolated_from_formal_streams(self):
        fields = smoke_ids.smoke_data_stream_fields(
            smoke_generation_id=GENERATION,
            phase=scope.PHASE_SMOKE_ALT,
            DGP_family=dgp.DGP_FAMILY_H1,
            replicate_id=0,
        )
        smoke_master = dgp.generate_h1_master(
            scenario=dgp.H1_SCENARIO_SHAPE,
            rho="0",
            root_key_hex=ROOT_KEY,
            data_generation_id=GENERATION,
            master_replicate_id="smoke-master",
            stream_prefix="smoke_",
            stream_fields=fields,
        )
        formal_master = _master(dgp.H1_SCENARIO_SHAPE, "0")
        assert smoke_master.innovation_hash != formal_master.innovation_hash
        assert smoke_master.noise_hash != formal_master.noise_hash

    def test_null_master_accepts_smoke_stream_override(self):
        fields = smoke_ids.smoke_data_stream_fields(
            smoke_generation_id=GENERATION,
            phase=scope.PHASE_SMOKE_NULL,
            DGP_family=dgp.DGP_FAMILY_N_CIRCLE,
            replicate_id=0,
        )
        master = dgp.generate_null_master(
            family=dgp.DGP_FAMILY_N_CIRCLE,
            rho="0",
            root_key_hex=ROOT_KEY,
            data_generation_id=GENERATION,
            master_replicate_id="smoke-master",
            stream_prefix="smoke_",
            stream_fields=fields,
        )
        assert master.noise is not None
        assert master.noise.shape == (cells.L_MASTER, 2)
