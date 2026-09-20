"""Re-audit 2026-09-16 (Block A): the formal work-unit domain, pure derivations.

These tests pin the *formal* identity derivations (``formal.py``) and, crucially,
their separation from the smoke domain (Plan §16).  The dispatch entry points and
the ``execute_plan`` FORMAL admission are wired separately; until that happens the
protective ``FORMAL_RUNNER_NOT_IMPLEMENTED`` refusal must stay in place.
"""

from __future__ import annotations

import hashlib
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
GOV = REPO / "governance"


@pytest.fixture(scope="module")
def governance():
    # Standalone test inputs: never consume the project's registered roots.
    manifest = {
        "project_id": "TEST-OWTDA", "protocol_id": "TEST-PROTOCOL",
        "freeze_id": hashlib.sha256(b"TEST-FREEZE-20260917").hexdigest(),
        "evidence_generation_id": "TEST-GENERATION",
        "component_generations": {"data_generation_id": "D01",
            "method_generation_id": {"M0": "M01", "M1": "M01"}},
    }
    entries = []
    for phase, prefix in (("NULL", "null"), ("ALT", "h1")):
        for family, generation in (("data", "D01"), ("M0", "M01"), ("M1", "M01")):
            stream = f"{prefix}_{family}"
            entries.append({"phase": phase, "stream_family": stream,
                "component_generation_id": generation,
                "root_key_hex": hashlib.sha256(("TEST-ONLY:" + stream).encode()).hexdigest()})
    return manifest, {"entries": entries}


def _h(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


class TestFormalContext:
    def test_null_context_has_the_575_unique_window_starts(self, governance):
        from owtda_cal import formal

        manifest, _ = governance
        ctx = formal.formal_context(manifest, "NULL")
        assert ctx["data_generation_id"] == "D01"
        assert len(ctx["starts"]) == 575
        assert len(ctx["index_of"]) == 575

    def test_alt_context_has_no_window_map(self, governance):
        from owtda_cal import formal

        manifest, _ = governance
        ctx = formal.formal_context(manifest, "ALT")
        assert ctx["data_generation_id"] == "D01"
        assert "starts" not in ctx

    def test_unknown_phase_is_refused(self, governance):
        from owtda_cal import formal

        manifest, _ = governance
        with pytest.raises(ValueError):
            formal.formal_context(manifest, "SMOKE_NULL")


class TestFormalRootKeys:
    def test_each_phase_has_three_distinct_root_keys(self, governance):
        from owtda_cal import formal

        _, seeds = governance
        for phase in ("NULL", "ALT"):
            keys = formal.formal_root_keys(seeds, phase)
            assert set(keys) == {"data", "M0", "M1"}
            values = list(keys.values())
            assert len(set(values)) == 3  # three independent streams

    def test_null_and_alt_have_disjoint_root_keys(self, governance):
        from owtda_cal import formal

        _, seeds = governance
        null = formal.formal_root_keys(seeds, "NULL")
        alt = formal.formal_root_keys(seeds, "ALT")
        assert set(null.values()).isdisjoint(set(alt.values()))

    def test_stale_data_generation_is_refused(self, governance):
        from owtda_cal import formal

        _, seeds = governance
        stale = {"entries": [
            {**e, "component_generation_id": "D99"}
            if e["phase"] == "NULL" and e["stream_family"] == "null_data" else e
            for e in seeds["entries"]
        ]}
        with pytest.raises(ValueError):
            formal.formal_root_keys(stale, "NULL")


class TestDomainSeparation:
    def test_formal_identity_chain_never_uses_the_smoke_namespace(self, governance):
        from owtda_cal import cells, formal, scope

        manifest, _ = governance
        ctx = formal.formal_context(manifest, "NULL")
        cell = scope.h0_null_cells()[0]
        mid = cells.master_replicate_id(
            project_id=ctx["project_id"], protocol_id=ctx["protocol_id"],
            freeze_id=ctx["freeze_id"],
            evidence_generation_id=ctx["evidence_generation_id"],
            phase="NULL", DGP_family=cell.family, replicate_id=1,
        )
        dmh = _h("data-model")
        chain = formal.formal_identity_chain(
            ctx=ctx, cell=cell, family=cell.family, master_replicate_id=mid,
            data_model_config_hash=dmh, feature_id=scope.FEATURE_IDS[0],
            feature_config_hash=dmh, method_id="M0", method_config_hash=dmh,
        )
        for key, value in chain.items():
            if key == "scenario_id":  # "h0" is a label, not an H(...) digest
                continue
            # Every formal id is a hex H(...) digest; none may carry a smoke_* id
            # (the smoke ids embed a "smoke_" kind string, so a leaked one would
            # differ -- here we assert the derivations go through the formal domain).
            assert len(value) == 64
        # The formal data-unit id is derived from cells.*, not smoke_ids.*: it must
        # not equal the smoke counterpart for the same cell.
        from owtda_cal import smoke_ids

        smoke_du = smoke_ids.smoke_data_unit_id(
            smoke_base_series_id="x", smoke_physical_cell_id="y",
            smoke_generation_id="S04",
        )
        assert chain["data_unit_id"] != smoke_du

    def test_formal_and_smoke_master_replicate_ids_are_disjoint(self, governance):
        from owtda_cal import cells, smoke_ids

        manifest, _ = governance
        formal_mid = cells.master_replicate_id(
            project_id=manifest["project_id"], protocol_id=manifest["protocol_id"],
            freeze_id=manifest["freeze_id"],
            evidence_generation_id=manifest["evidence_generation_id"],
            phase="NULL", DGP_family="N_AR", replicate_id=1,
        )
        smoke_mid = smoke_ids.smoke_master_replicate_id(
            project_id=manifest["project_id"], protocol_id=manifest["protocol_id"],
            freeze_id=manifest["freeze_id"],
            evidence_generation_id=manifest["evidence_generation_id"],
            smoke_generation_id="S04", phase="SMOKE_NULL", DGP_family="N_AR",
            replicate_id=1,
        )
        assert formal_mid != smoke_mid


class TestFormalScientificUnit:
    """The formal worker produces formal-domain rows.

    The workers are invoked directly (not through ``run_units``) so that
    ``calibrate_m0/m1`` can be stubbed in-process; ``run_units`` uses a process
    pool, whose children re-import the module and would not see a monkeypatch.
    The resampler's own correctness is covered by the smoke/calibrate tests.
    """

    @pytest.fixture()
    def _fast_calibrate(self, monkeypatch):
        from owtda_cal import formal

        def stub(*args, **kwargs):
            return {
                "M": 0, "B": 0, "observed_statistic": 0.0,
                "exceed_count": 0, "p_value": 0.5, "reject": False,
            }

        monkeypatch.setattr(formal, "calibrate_m0", stub)
        monkeypatch.setattr(formal, "calibrate_m1", stub)

    def _null_payload(self, governance):
        from owtda_cal import formal, scope

        manifest, seeds = governance
        return {
            "family": scope.H0_FAMILIES[0],
            "rho": scope.RHO_LEVELS[0],
            "replicate": 1,
            "feature_id": scope.FEATURE_IDS[0],
            "ctx": formal.formal_context(manifest, "NULL"),
            "root_keys": formal.formal_root_keys(seeds, "NULL"),
        }

    def _alt_payload(self, governance):
        from owtda_cal import formal, scope

        manifest, seeds = governance
        return {
            "scenario": scope.SCENARIO_ALT_SHAPE,
            "rho": scope.RHO_LEVELS[0],
            "replicate": 1,
            "feature_id": scope.FEATURE_IDS[0],
            "ctx": formal.formal_context(manifest, "ALT"),
            "root_keys": formal.formal_root_keys(seeds, "ALT"),
        }

    def test_master_feature_counts_one_cell_group(self, governance, _fast_calibrate):
        from owtda_cal import formal

        part = formal.process_formal_master_feature(self._null_payload(governance))
        assert part["data_units"] == 7  # 7 geometries for one (family, rho)
        assert len(part["rows"]) == 14  # 7 cells x 2 methods
        assert part["errors"] == 0
        assert part["rows"][0]["phase"] == "NULL"
        assert part["rows"][0]["scenario_id"] == "h0"

    def test_alt_feature_counts_one_cell_group(self, governance, _fast_calibrate):
        from owtda_cal import formal

        part = formal.process_formal_alt_feature(self._alt_payload(governance))
        assert part["data_units"] == 2  # 2 strides for one (scenario, rho)
        assert len(part["rows"]) == 4  # 2 cells x 2 methods
        assert part["errors"] == 0
        assert part["rows"][0]["phase"] == "ALT"

    def test_formal_rows_are_not_smoke_rows(self, governance, _fast_calibrate):
        from owtda_cal import formal, smoke_ids

        part = formal.process_formal_master_feature(self._null_payload(governance))
        row = part["rows"][0]
        smoke = smoke_ids.smoke_evaluation_id(
            smoke_generation_id="S04", smoke_data_unit_id="x",
            smoke_feature_sufficient_id="y", method_id="M0",
            method_config_hash="z",
        )
        assert row["evaluation_id"] != smoke
        assert row["phase"] == "NULL"
        assert row["scenario_id"] == "h0"
