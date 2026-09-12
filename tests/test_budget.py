"""Full-scale budget derivation (task pack §8).

The previous estimate multiplied the smoke record's bytes by a copy factor and
never scaled to the formal counts; the audit measured ~323.5 MB for the
evaluation ledger alone.  These tests pin the derivation from the frozen plan,
the explicit stored-object statements, and the fail-closed behaviour on missing
components.
"""

from __future__ import annotations

from owtda_cal.budget import build_budget, derive_counts

GIB = 1024 ** 3


def _schema(**overrides) -> dict:
    base = {
        "evaluation_row_bytes": 1024,
        "feature_row_bytes": 512,
        "data_unit_bytes": 4096,
        "index_entry_bytes": 128,
        "event_row_bytes": 256,
        "resource_row_bytes": 256,
        "manifest_bytes": 64 * 1024,
        "store_full_feature_matrices": False,
        "store_summaries": False,
        "store_ph_diagrams": False,
        "store_resampling_stats": False,
    }
    base.update(overrides)
    return base


def _profile(**overrides) -> dict:
    base = {
        "compute_seconds_per_evaluation": 0.4,
        "serialize_seconds_per_evaluation": 0.05,
        "merge_seconds_per_phase": 600.0,
        "seal_seconds_per_phase": 120.0,
        "recovery_seconds": 300.0,
    }
    base.update(overrides)
    return base


def _storage(**overrides) -> dict:
    base = {
        "copies": {"staging": 1, "final": 1, "merge": 1, "recovery": 1, "archive": 1},
        "coexisting_stages": ["staging", "final", "merge"],
    }
    base.update(overrides)
    return base


class TestFrozenCounts:
    def test_the_plan_counts_match_the_audit(self):
        counts = derive_counts()
        assert counts["totals"] == {
            "data_units": 82_800,
            "feature_rows": 165_600,
            "evaluation_rows": 331_200,
        }
        assert counts["h0"]["evaluation_rows"] == 280_000
        assert counts["h1"]["evaluation_rows"] == 51_200
        assert counts["source"] == "frozen_plan"

    def test_phases_are_listed_separately(self):
        budget = build_budget(counts=derive_counts(), serialization_schema=_schema(),
                              storage_policy=_storage(), profile=_profile())
        assert set(budget["counts"]["phases"]) == {"h0", "h1"}
        assert budget["counts"]["phases"]["h0"]["evaluation_rows"] == 280_000


class TestDerivation:
    def test_the_evaluation_ledger_is_derived_from_the_full_count(self):
        budget = build_budget(counts=derive_counts(), serialization_schema=_schema(),
                              storage_policy=_storage(), profile=_profile())
        assert budget["status"] == "APPROVED_ESTIMATE"
        # 331,200 rows x 1 KiB -- the old estimate was a smoke-record multiple
        assert budget["components"]["evaluation_ledger_bytes"] == 331_200 * 1024
        assert budget["components"]["evaluation_ledger_bytes"] > 300 * 1024 ** 2

    def test_every_lifecycle_component_is_counted(self):
        budget = build_budget(
            counts=derive_counts(),
            serialization_schema=_schema(store_full_feature_matrices=True,
                                         store_summaries=True, store_ph_diagrams=True,
                                         store_resampling_stats=True,
                                         feature_matrix_bytes=2048,
                                         summary_bytes=1024,
                                         ph_diagram_bytes=2048,
                                         resampling_stats_row_bytes=64),
            storage_policy=_storage(), profile=_profile(),
        )
        for key in ("evaluation_ledger_bytes", "feature_ledger_bytes", "index_bytes",
                    "event_attempt_bytes", "resource_log_bytes", "manifest_bytes",
                    "feature_matrix_bytes", "summary_bytes", "ph_diagram_bytes",
                    "resampling_stat_bytes"):
            assert key in budget["components"], key

    def test_the_stored_object_decision_is_explicit(self):
        budget = build_budget(counts=derive_counts(), serialization_schema=_schema(),
                              storage_policy=_storage(), profile=_profile())
        assert budget["stored_objects"] == {
            "full_feature_matrices": False, "summaries": False,
            "ph_diagrams": False, "resampling_stats": False,
        }

    def test_the_peak_counts_the_coexisting_stages_and_copies(self):
        storage = _storage(copies={"staging": 1, "final": 1, "merge": 2,
                                   "recovery": 1, "archive": 1},
                           coexisting_stages=["staging", "final", "merge"])
        budget = build_budget(counts=derive_counts(), serialization_schema=_schema(),
                              storage_policy=storage, profile=_profile())
        content = budget["content_total_bytes"]
        assert budget["stage_bytes"]["merge"] == 2 * content
        assert budget["peak_bytes"] == (content + content + 2 * content
                                        + budget["recovery_original_bytes"]
                                        + budget["archive_bytes"])

    def test_the_time_projection_is_split_by_stage(self):
        budget = build_budget(counts=derive_counts(), serialization_schema=_schema(),
                              storage_policy=_storage(), profile=_profile())
        time = budget["time_milliseconds"]
        # 331,200 evaluations x 400 ms of compute
        assert time["compute"] == 331_200 * 400
        assert time["merge"] == 1_200_000
        assert sum(time[k] for k in ("compute", "serialize", "merge", "seal",
                                     "recovery")) == time["total"]
        # the payload is canonical: no bare floats anywhere
        assert all(isinstance(v, int) for v in time.values())

    def test_the_formal_measurement_is_not_fabricated(self):
        budget = build_budget(counts=derive_counts(), serialization_schema=_schema(),
                              storage_policy=_storage(), profile=_profile())
        assert budget["formal_measurement"] == "NOT_YET_OBSERVED"

    def test_the_budget_hash_is_stable(self):
        first = build_budget(counts=derive_counts(), serialization_schema=_schema(),
                             storage_policy=_storage(), profile=_profile())
        second = build_budget(counts=derive_counts(), serialization_schema=_schema(),
                              storage_policy=_storage(), profile=_profile())
        assert first["budget_hash"] == second["budget_hash"]
        changed = build_budget(counts=derive_counts(),
                               serialization_schema=_schema(evaluation_row_bytes=2048),
                               storage_policy=_storage(), profile=_profile())
        assert changed["budget_hash"] != first["budget_hash"]


class TestFailClosed:
    def test_a_smoke_extrapolation_is_refused(self):
        counts = derive_counts()
        counts["source"] = "smoke_linear_extrapolation"
        budget = build_budget(counts=counts, serialization_schema=_schema(),
                              storage_policy=_storage(), profile=_profile())
        assert budget["status"] == "INCOMPLETE"
        assert any("frozen plan" in m for m in budget["missing"])

    def test_a_missing_schema_key_is_named(self):
        schema = _schema()
        schema.pop("store_ph_diagrams")
        budget = build_budget(counts=derive_counts(), serialization_schema=schema,
                              storage_policy=_storage(), profile=_profile())
        assert budget["status"] == "INCOMPLETE"
        assert "serialization_schema.store_ph_diagrams" in budget["missing"]

    def test_a_missing_profile_key_is_named(self):
        profile = _profile()
        profile.pop("recovery_seconds")
        budget = build_budget(counts=derive_counts(), serialization_schema=_schema(),
                              storage_policy=_storage(), profile=profile)
        assert "profile.recovery_seconds" in budget["missing"]

    def test_a_missing_storage_key_is_named(self):
        budget = build_budget(counts=derive_counts(), serialization_schema=_schema(),
                              storage_policy={"copies": {}}, profile=_profile())
        assert "storage_policy.coexisting_stages" in budget["missing"]

    def test_a_volume_without_room_refuses_the_estimate(self):
        budget = build_budget(counts=derive_counts(), serialization_schema=_schema(),
                              storage_policy=_storage(), profile=_profile(),
                              volumes=[{"name": "F:", "free_bytes": 1 * GIB}])
        assert budget["status"] == "INCOMPLETE"
        assert budget["volumes"][0]["within_limit"] is False

    def test_a_volume_with_room_passes(self):
        budget = build_budget(counts=derive_counts(), serialization_schema=_schema(),
                              storage_policy=_storage(), profile=_profile(),
                              volumes=[{"name": "F:", "free_bytes": 1_000 * GIB}])
        assert budget["status"] == "APPROVED_ESTIMATE"
        assert budget["volumes"][0]["within_limit"] is True
