"""Smoke identity-domain contracts (Plan §9.3, §15.2, §16).

The smoke namespace must be complete and strictly disjoint from the formal one:
every smoke artefact carries ``smoke_generation_id``, no smoke ID may coincide
with the formal ID built from the same inputs, and the smoke stream field sets
are exactly the ones registered in the RNG contract table.
"""

import pytest

from owtda_cal import calibrate, cells, dgp, scope, smoke_ids

CTX = {
    "project_id": "BPI-Scan",
    "protocol_id": "OWTDA-CAL-R1",
    "freeze_id": "freeze",
    "evidence_generation_id": "E1",
}
PHASE = scope.PHASE_SMOKE_ALT
FAMILY = dgp.DGP_FAMILY_H1
GEN = scope.SMOKE_GENERATION_ID


def _all_ids(generation: str, *, phase: str = PHASE, family: str = FAMILY,
             rho: str = "0", stride: int = 64, T: int = 12288,
             scenario: str = dgp.H1_SCENARIO_SHAPE) -> dict[str, str]:
    master = smoke_ids.smoke_master_replicate_id(
        **CTX, smoke_generation_id=generation, phase=phase,
        DGP_family=family, replicate_id=0,
    )
    if family == dgp.DGP_FAMILY_H1:
        spec = dgp.h1_data_model_spec(scenario, rho)
    else:
        spec = dgp.n_circle_data_model_spec(rho)
    data_model = dgp.data_model_config_hash(spec)
    physical = smoke_ids.smoke_physical_cell_id(
        **CTX, smoke_generation_id=generation, phase=phase, DGP_family=family,
        rho=rho, W=cells.W_FIXED, stride=stride, T=T, M=cells.M_FIXED_M,
        data_model_config_hash=data_model,
    )
    base = smoke_ids.smoke_base_series_id(
        smoke_master_replicate_id=master, smoke_generation_id=generation, rho=rho,
        raw_length=T, data_model_config_hash=data_model,
    )
    unit = smoke_ids.smoke_data_unit_id(
        smoke_base_series_id=base, smoke_physical_cell_id=physical,
        smoke_generation_id=generation,
    )
    feature = smoke_ids.smoke_feature_sufficient_id(
        smoke_generation_id=generation, smoke_data_unit_id=unit,
        feature_id=scope.FEATURE_IDS[0], feature_config_hash="fh",
    )
    return {
        "master": master,
        "physical": physical,
        "base": base,
        "data_unit": unit,
        "feature_sufficient": feature,
        "resampling": smoke_ids.smoke_resampling_stream_id(
            smoke_generation_id=generation, smoke_data_unit_id=unit,
            method_random_family="M1",
        ),
        "evaluation": smoke_ids.smoke_evaluation_id(
            smoke_generation_id=generation, smoke_data_unit_id=unit,
            smoke_feature_sufficient_id=feature, method_id=scope.METHOD_IDS[0],
            method_config_hash="mh",
        ),
        "experiment": smoke_ids.smoke_experiment_id(
            **CTX, smoke_generation_id=generation, phase=phase
        ),
        "logical_cell": smoke_ids.smoke_logical_cell_id(
            smoke_experiment_id=smoke_ids.smoke_experiment_id(
                **CTX, smoke_generation_id=generation, phase=phase
            ),
            smoke_generation_id=generation, DGP_family=family,
            scenario_id=scenario, rho=rho, W=cells.W_FIXED, stride=stride, T=T,
            M=cells.M_FIXED_M,
        ),
        "logical_data": smoke_ids.smoke_logical_data_key(
            smoke_generation_id=generation, smoke_logical_cell_id="lc",
            smoke_master_replicate_id=master,
        ),
        "logical_feature": smoke_ids.smoke_logical_feature_key(
            smoke_generation_id=generation, smoke_logical_data_key="ld",
            feature_id=scope.FEATURE_IDS[0],
        ),
        "logical_evaluation": smoke_ids.smoke_logical_evaluation_key(
            smoke_generation_id=generation, smoke_logical_data_key="ld",
            feature_id=scope.FEATURE_IDS[0], method_id=scope.METHOD_IDS[0],
        ),
    }


class TestSmokeIdDomain:
    def test_all_ids_are_hex256_and_distinct(self):
        ids = _all_ids(GEN)
        assert len(set(ids.values())) == len(ids)
        for name, value in ids.items():
            assert len(value) == 64, name
            assert value == value.lower()
            int(value, 16)

    def test_generation_enters_every_id(self):
        old = _all_ids(scope.SMOKE_GENERATIONS_SUPERSEDED[0])
        new = _all_ids(GEN)
        for name in old:
            assert old[name] != new[name], name

    def test_ids_are_phase_scoped(self):
        alt = _all_ids(GEN, phase=scope.PHASE_SMOKE_ALT)
        null = _all_ids(GEN, phase=scope.PHASE_SMOKE_NULL,
                        family=dgp.DGP_FAMILY_N_CIRCLE,
                        scenario=scope.SCENARIO_NULL)
        assert alt["experiment"] != null["experiment"]
        assert alt["master"] != null["master"]

    def test_alternatives_share_master_but_not_data_identity(self):
        shape = _all_ids(GEN, scenario=dgp.H1_SCENARIO_SHAPE)
        mean = _all_ids(GEN, scenario=dgp.H1_SCENARIO_MEAN)
        assert shape["master"] == mean["master"]
        for name in ("logical_cell", "physical", "base", "data_unit",
                     "feature_sufficient", "evaluation"):
            assert shape[name] != mean[name], name

    def test_rho_changes_data_identity_only(self):
        a = _all_ids(GEN, rho="0")
        b = _all_ids(GEN, rho="0.8")
        assert a["master"] == b["master"]
        for name in ("physical", "base", "data_unit", "logical_cell"):
            assert a[name] != b[name], name


class TestNoFormalIdReuse:
    def test_master_id_differs_from_formal_counterpart(self):
        smoke_id = _all_ids(GEN)["master"]
        formal = cells.master_replicate_id(
            project_id=CTX["project_id"], protocol_id=CTX["protocol_id"],
            freeze_id=CTX["freeze_id"],
            evidence_generation_id=CTX["evidence_generation_id"],
            phase=PHASE, DGP_family=FAMILY, replicate_id=0,
        )
        assert smoke_id != formal

    def test_data_unit_id_differs_from_formal_counterpart(self):
        ids = _all_ids(GEN)
        formal = cells.data_unit_id(
            base_series_id="base", physical_cell_id="physical",
            data_generation_id=GEN,
        )
        assert ids["data_unit"] not in (formal, "base", "physical")

    def test_logical_ids_differs_from_formal_counterpart(self):
        ids = _all_ids(GEN)
        formal = scope.logical_cell_id(
            **CTX, phase=PHASE, DGP_family=FAMILY,
            scenario_id=dgp.H1_SCENARIO_SHAPE, rho="0", W=cells.W_FIXED,
            stride=64, T=12288, M=cells.M_FIXED_M,
        )
        assert ids["logical_cell"] != formal


class TestStreamFieldContracts:
    def test_data_stream_fields_are_exact(self):
        fields = smoke_ids.smoke_data_stream_fields(
            smoke_generation_id=GEN, phase=PHASE, DGP_family=FAMILY,
            replicate_id=7,
        )
        assert fields == {
            "smoke_generation_id": GEN,
            "phase": PHASE,
            "DGP_family": FAMILY,
            "replicate_id": 7,
        }

    def test_method_stream_fields_are_exact(self):
        fields = smoke_ids.smoke_method_stream_fields(
            smoke_generation_id=GEN, phase=PHASE, smoke_data_unit_id="du"
        )
        assert fields == {
            "smoke_generation_id": GEN,
            "phase": PHASE,
            "smoke_data_unit_id": "du",
        }

    def test_resample_fields_add_the_index(self):
        fields = calibrate.resample_stream_fields(
            method_generation_id=None, data_unit_id=None,
            stream_fields={"smoke_generation_id": GEN, "phase": PHASE,
                           "smoke_data_unit_id": "du"},
            resample_index=3,
        )
        assert fields["resample_index"] == 3
        assert set(fields) == {
            "smoke_generation_id", "phase", "smoke_data_unit_id",
            "resample_index",
        }

    def test_resample_fields_formal_form(self):
        fields = calibrate.resample_stream_fields(
            method_generation_id="G1", data_unit_id="du", stream_fields=None,
            resample_index=1,
        )
        assert fields == {
            "method_generation_id": "G1", "data_unit_id": "du",
            "resample_index": 1,
        }

    def test_mixing_the_two_forms_is_rejected(self):
        with pytest.raises(ValueError):
            calibrate.resample_stream_fields(
                method_generation_id="G1", data_unit_id="du",
                stream_fields={"smoke_generation_id": GEN}, resample_index=1,
            )
        with pytest.raises(ValueError):
            calibrate.resample_stream_fields(
                method_generation_id=None, data_unit_id=None,
                stream_fields=None, resample_index=1,
            )
        with pytest.raises(ValueError):
            calibrate.resample_stream_fields(
                method_generation_id=None, data_unit_id=None,
                stream_fields={"resample_index": 5}, resample_index=1,
            )

    def test_stream_prefix_is_the_smoke_prefix(self):
        assert smoke_ids.SMOKE_ID_PREFIX == "smoke_"
        assert smoke_ids.SMOKE_STREAM_FAMILY == "smoke"
