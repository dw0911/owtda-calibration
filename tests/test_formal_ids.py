"""The formal concrete-identity tail (plan-builder prerequisite, §9 step 5).

The audit's plan step could not start because the formal domain had no concrete
feature-sufficient / evaluation derivations -- only the smoke namespace did, and
Plan §16 forbids mixing the two.  These tests pin the new formal derivations and
their domain separation from the smoke ones.
"""

from __future__ import annotations

from owtda_cal import cells, formal_ids, smoke_ids

G = "G01"
PHASE = "NULL"
FAMILY = "N_CIRCLE"
FEATURE = "BPI_FIXED20_H01_SIGMA005_GAMMA1_V1"
METHOD = "M0_NAIVE_PERM_B999_V1"
FEATURE_HASH = "a" * 64
METHOD_HASH = "b" * 64
MASTER = "1" * 64
CELL = "2" * 64
SERIES = "3" * 64
UNIT = "4" * 64


class TestDerivations:
    def test_the_chain_is_deterministic(self):
        first = formal_ids.feature_sufficient_id(
            data_generation_id=G, data_unit_id=UNIT, feature_id=FEATURE,
            feature_config_hash=FEATURE_HASH)
        second = formal_ids.feature_sufficient_id(
            data_generation_id=G, data_unit_id=UNIT, feature_id=FEATURE,
            feature_config_hash=FEATURE_HASH)
        assert first == second and len(first) == 64

    def test_an_evaluation_binds_its_feature_and_its_method(self):
        feature_sufficient = formal_ids.feature_sufficient_id(
            data_generation_id=G, data_unit_id=UNIT, feature_id=FEATURE,
            feature_config_hash=FEATURE_HASH)
        base = formal_ids.evaluation_id(
            data_generation_id=G, data_unit_id=UNIT,
            feature_sufficient_id=feature_sufficient, method_id=METHOD,
            method_config_hash=METHOD_HASH)
        other_method = formal_ids.evaluation_id(
            data_generation_id=G, data_unit_id=UNIT,
            feature_sufficient_id=feature_sufficient,
            method_id="M1_DMB_R1_TRI_EXTIID_B999_V1", method_config_hash="c" * 64)
        assert base != other_method

    def test_every_level_changes_the_next_one(self):
        feature_sufficient = formal_ids.feature_sufficient_id(
            data_generation_id=G, data_unit_id=UNIT, feature_id=FEATURE,
            feature_config_hash=FEATURE_HASH)
        other_feature = formal_ids.feature_sufficient_id(
            data_generation_id=G, data_unit_id=UNIT, feature_id="MOMENTS_FIXED20",
            feature_config_hash="d" * 64)
        assert feature_sufficient != other_feature
        assert formal_ids.resampling_stream_id(
            data_generation_id=G, data_unit_id=UNIT,
            method_random_family="M0_permutation") != (
            formal_ids.resampling_stream_id(data_generation_id=G, data_unit_id=UNIT,
                                            method_random_family="M1_gaussian_innovation"))

    def test_the_data_unit_id_comes_from_the_existing_cells_chain(self):
        """The plan builder reuses cells.* unchanged; only the tail is new."""
        assert cells.master_replicate_id(
            project_id="p", protocol_id="q", freeze_id="0" * 64,
            evidence_generation_id=G, phase=PHASE, DGP_family=FAMILY,
            replicate_id=1) == cells.master_replicate_id(
            project_id="p", protocol_id="q", freeze_id="0" * 64,
            evidence_generation_id=G, phase=PHASE, DGP_family=FAMILY, replicate_id=1)


class TestNamespaceSeparation:
    """Plan §16: the smoke and formal namespaces must never collide."""

    def _smoke_pair(self):
        smoke_feature = smoke_ids.smoke_feature_sufficient_id(
            smoke_generation_id=G, smoke_data_unit_id=UNIT, feature_id=FEATURE,
            feature_config_hash=FEATURE_HASH)
        smoke_eval = smoke_ids.smoke_evaluation_id(
            smoke_generation_id=G, smoke_data_unit_id=UNIT,
            smoke_feature_sufficient_id=smoke_feature, method_id=METHOD,
            method_config_hash=METHOD_HASH)
        return smoke_feature, smoke_eval

    def test_the_feature_ids_differ_even_with_identical_inputs(self):
        smoke_feature, _ = self._smoke_pair()
        formal_feature = formal_ids.feature_sufficient_id(
            data_generation_id=G, data_unit_id=UNIT, feature_id=FEATURE,
            feature_config_hash=FEATURE_HASH)
        assert smoke_feature != formal_feature

    def test_the_evaluation_ids_differ_even_with_identical_inputs(self):
        _smoke_feature, smoke_eval = self._smoke_pair()
        formal_feature = formal_ids.feature_sufficient_id(
            data_generation_id=G, data_unit_id=UNIT, feature_id=FEATURE,
            feature_config_hash=FEATURE_HASH)
        formal_eval = formal_ids.evaluation_id(
            data_generation_id=G, data_unit_id=UNIT,
            feature_sufficient_id=formal_feature, method_id=METHOD,
            method_config_hash=METHOD_HASH)
        assert smoke_eval != formal_eval

    def test_the_kinds_are_formal_lookalikes_of_the_smoke_ones(self):
        assert formal_ids.FEATURE_SUFFICIENT_KIND == "synthetic_feature_sufficient"
        assert formal_ids.EVALUATION_KIND == "synthetic_evaluation"
        assert not formal_ids.FEATURE_SUFFICIENT_KIND.startswith("smoke_")
        assert not formal_ids.EVALUATION_KIND.startswith("smoke_")
