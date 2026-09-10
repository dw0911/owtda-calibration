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

    def test_replicates_are_32(self):
        assert scope.R0_SMOKE == 32
        config = _load("SMOKE_CONFIG_v1.json")
        assert config["replicates_per_cell"] == scope.R0_SMOKE
        assert config["smoke_data_units"]["SMOKE_NULL"] == 896
        assert config["smoke_ph_windows"]["SMOKE_NULL"] == 73600

    def test_context_has_575_unique_starts(self):
        ctx = smoke.smoke_context(_load("FREEZE_MANIFEST.json"))
        assert len(ctx["starts"]) == 575
        assert ctx["phase"] == scope.PHASE_SMOKE_NULL

    def test_geometry_starts_are_inside_the_union(self):
        ctx = smoke.smoke_context(_load("FREEZE_MANIFEST.json"))
        known = set(ctx["starts"])
        for geometry in cells.h0_geometry_cells():
            assert set(geometry.raw_starts()) <= known


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


class TestSmokeRootIsolation:
    def test_root_key_is_plaintext_hex64(self):
        key = smoke.smoke_root_key(_load("SEED_REGISTRY_v1.0.json"), scope.PHASE_SMOKE_NULL)
        assert len(key) == 64 and key == key.lower()

    def test_missing_smoke_entry_rejected(self):
        with pytest.raises(ValueError):
            smoke.smoke_root_key({"entries": []}, scope.PHASE_SMOKE_NULL)

    def test_formal_phase_has_no_smoke_entry(self):
        with pytest.raises(ValueError):
            smoke.smoke_root_key(_load("SEED_REGISTRY_v1.0.json"), scope.PHASE_NULL)

    def test_stream_prefix_is_smoke(self):
        assert smoke.SMOKE_STREAM_PREFIX == "smoke_"
        assert smoke.SMOKE_GENERATION_ID == "S01"
