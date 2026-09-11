"""Blind-smoke contracts (Plan §9.3-§9.4): counts, blind outputs, root isolation."""

import json
from pathlib import Path

import pytest

from owtda_cal import cells, scope, smoke

REPO = Path(__file__).resolve().parents[1]
GOV = REPO / "governance"


def _load(name: str) -> dict:
    return json.loads((GOV / name).read_text(encoding="utf-8"))


class TestSmokeCounts:
    def test_frozen_g3_counts(self):
        counts = smoke.expected_smoke_counts()
        assert counts["data_units"] == 896
        assert counts["evaluation_rows"] == 3584
        assert counts["ph_windows"] == 73600

    def test_frozen_g3_counts_alt(self):
        counts = smoke.expected_smoke_counts(scope.PHASE_SMOKE_ALT)
        assert counts["data_units"] == 256
        assert counts["evaluation_rows"] == 1024
        assert counts["ph_windows"] == 49152

    def test_unknown_phase_rejected(self):
        with pytest.raises(ValueError):
            smoke.expected_smoke_counts(scope.PHASE_NULL)

    def test_replicates_are_32(self):
        assert scope.R0_SMOKE == 32
        config = _load("SMOKE_CONFIG_v1.json")
        assert config["replicates_per_cell"] == scope.R0_SMOKE
        assert config["smoke_data_units"]["SMOKE_NULL"] == 896
        assert config["smoke_ph_windows"]["SMOKE_NULL"] == 73600
        assert config["smoke_data_units"]["SMOKE_ALT"] == 256
        assert config["smoke_ph_windows"]["SMOKE_ALT"] == 49152

    def test_context_has_575_unique_starts(self):
        ctx = smoke.smoke_context(_load("FREEZE_MANIFEST.json"))
        assert len(ctx["starts"]) == 575
        assert ctx["phase"] == scope.PHASE_SMOKE_NULL

    def test_geometry_starts_are_inside_the_union(self):
        ctx = smoke.smoke_context(_load("FREEZE_MANIFEST.json"))
        known = set(ctx["starts"])
        for geometry in cells.h0_geometry_cells():
            assert set(geometry.raw_starts()) <= known

    def test_alt_context_carries_no_shared_window_union(self):
        """Plan §9.2: H1 strides may not share a window cache."""
        ctx = smoke.smoke_context(_load("FREEZE_MANIFEST.json"), scope.PHASE_SMOKE_ALT)
        assert ctx["phase"] == scope.PHASE_SMOKE_ALT
        assert "starts" not in ctx and "index_of" not in ctx
        assert ctx["smoke_generation_id"] == scope.SMOKE_GENERATION_ID


class TestBlindOutput:
    def test_report_has_no_aggregates(self):
        result = smoke.SmokeResult(
            phase="SMOKE_NULL", wall_seconds=1.0, data_units=896,
            evaluation_rows=3584, ph_windows=73600, errors=0,
        )
        report = result.report()
        assert set(report) == {
            "phase", "wall_seconds", "data_units", "evaluation_rows",
            "ph_windows", "errors", "forbidden_aggregates_emitted",
        }
        for forbidden in ("rejection_rate", "power", "ranking", "p_value", "reject"):
            assert forbidden not in report
        assert report["forbidden_aggregates_emitted"] is False

    def test_smoke_config_forbids_parameter_selection(self):
        config = _load("SMOKE_CONFIG_v1.json")
        assert config["feeds_parameter_selection"] is False
        assert "rejection_rate_summary" in config["forbidden_outputs"]

    def test_row_fields_and_missing_detection(self):
        assert smoke.assert_row_fields([dict.fromkeys(smoke.ROW_FIELDS)]) == 0
        assert smoke.assert_row_fields([{"phase": "SMOKE_NULL"}]) == 1

    def test_row_fields_use_the_smoke_identity_domain(self):
        for column in ("experiment_id", "logical_cell_id", "logical_data_key",
                       "logical_feature_key", "logical_evaluation_key",
                       "data_unit_id", "feature_sufficient_id",
                       "evaluation_id", "scenario_id"):
            assert column in smoke.ROW_FIELDS


class TestSmokeRootIsolation:
    def test_root_key_is_plaintext_hex64(self):
        key = smoke.smoke_root_key(_load("SEED_REGISTRY_v1.0.json"), scope.PHASE_SMOKE_NULL)
        assert len(key) == 64 and key == key.lower()

    def test_both_smoke_phases_have_a_key(self):
        registry = _load("SEED_REGISTRY_v1.0.json")
        for phase in scope.SMOKE_PHASES:
            key = smoke.smoke_root_key(registry, phase)
            assert len(key) == 64

    def test_missing_smoke_entry_rejected(self):
        with pytest.raises(ValueError):
            smoke.smoke_root_key({"entries": []}, scope.PHASE_SMOKE_NULL)

    def test_formal_phase_has_no_smoke_entry(self):
        with pytest.raises(ValueError):
            smoke.smoke_root_key(_load("SEED_REGISTRY_v1.0.json"), scope.PHASE_NULL)

    def test_stale_generation_is_rejected(self):
        registry = _load("SEED_REGISTRY_v1.0.json")
        stale = {
            "entries": [
                {**entry, "component_generation_id": "S00"}
                for entry in registry["entries"]
                if entry["stream_family"] == "smoke"
            ]
        }
        with pytest.raises(ValueError):
            smoke.smoke_root_key(stale, scope.PHASE_SMOKE_NULL)

    def test_stream_prefix_is_smoke(self):
        assert smoke.SMOKE_STREAM_PREFIX == "smoke_"
        # The *current* generation is never hard-coded: it is whatever
        # scope.SMOKE_GENERATION_ID says, and it must not be a superseded one.
        assert smoke.SMOKE_GENERATION_ID == scope.SMOKE_GENERATION_ID
        assert scope.SMOKE_GENERATION_ID not in scope.SMOKE_GENERATIONS_SUPERSEDED
        assert scope.SMOKE_GENERATIONS_SUPERSEDED == ("S01", "S02")
