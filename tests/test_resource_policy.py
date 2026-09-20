"""The executable capacity policy and the paired-ratio decision (§3.1, §3.2).

The re-audit (2026-09-13) reproduced two defects with the actual probes:

* the summary divided ``max_k C_k`` by the *last* commit limit, so a host that
  really peaked at 0.90 was reported as 0.45 and passed;
* a sampler that died after one sample still produced ``incomplete=false`` and
  therefore ``PASS``.

Both are pinned here against the raw rows, not against the producer's summary.
"""

from __future__ import annotations

import json

import pytest

from owtda_cal.resource_policy import (
    ResourcePolicyError,
    evaluate_capacity,
    load_policy,
    policy_sha256,
    preflight_capacity,
)

GIB = 1024 ** 3


@pytest.fixture(scope="module")
def policy() -> dict:
    return load_policy()


def _row(seq: int, *, ns: int, commit: int, limit: int, ok: bool = True,
         error: str | None = None, phys_total: int = 32 * GIB,
         phys_avail: int = 16 * GIB, rss: int = 4 * GIB, stage: str = "compute") -> dict:
    return {
        "schema_version": 1,
        "run_id": "TEST_RUN",
        "policy_sha256": policy_sha256(),
        "seq": seq,
        "monotonic_ns": ns,
        "ok": ok,
        "error": error,
        "stage": stage,
        "commit_total_bytes": commit,
        "commit_limit_bytes": limit,
        "physical_total_bytes": phys_total,
        "physical_available_bytes": phys_avail,
        "rss_tree_bytes": rss,
    }


class TestPolicyFile:
    def test_is_bound_to_the_v2_document(self, policy):
        assert policy["resource_policy_id"] == "AM_RESOURCE_CAPACITY_V2"
        assert len(policy["source_policy"]["sha256"]) == 64

    def test_hash_is_stable_and_64_hex(self):
        digest = policy_sha256()
        assert len(digest) == 64 and int(digest, 16) >= 0

    def test_max_interval_is_three_seconds_in_ns(self, policy):
        assert policy["sampling"]["max_interval_ns"] == 3_000_000_000
        assert policy["sampling"]["interval_ns"] == 1_000_000_000

    def test_ratios_are_integer_rationals(self, policy):
        assert policy["limits"]["host_commit_fraction_max"] == {"num": 4, "den": 5}
        assert policy["limits"]["disk_fraction_max"] == {"num": 4, "den": 5}
        assert policy["limits"]["host_available_phys_floor"]["fraction_of_physical_total"] == {
            "num": 1, "den": 10
        }

    def test_a_float_coefficient_is_refused(self, tmp_path):
        bad = json.loads(json.dumps(load_policy()))
        bad["limits"]["host_commit_fraction_max"] = 0.8
        governance = tmp_path / "governance"
        governance.mkdir()
        source = tmp_path / "governance" / "RESOURCE_POLICY_V2.json"
        source.write_text("{}", encoding="utf-8")
        import hashlib

        bad["source_policy"]["sha256"] = hashlib.sha256(source.read_bytes()).hexdigest()
        (governance / "RESOURCE_POLICY_EXECUTABLE.json").write_text(
            json.dumps(bad), encoding="utf-8"
        )
        with pytest.raises(ResourcePolicyError, match="float coefficient"):
            load_policy(root=tmp_path)

    def test_an_unbound_policy_is_refused(self, tmp_path):
        good = load_policy()
        good["source_policy"]["sha256"] = "0" * 64
        governance = tmp_path / "governance"
        governance.mkdir()
        (governance / "RESOURCE_POLICY_V2.json").write_text("{}", encoding="utf-8")
        (governance / "RESOURCE_POLICY_EXECUTABLE.json").write_text(
            json.dumps(good), encoding="utf-8"
        )
        with pytest.raises(ResourcePolicyError, match="not bound"):
            load_policy(root=tmp_path)


class TestPairedCapacity:
    def test_the_audit_probe_is_now_refused(self, policy):
        """C=90/L=100 then C=90/L=200: the real peak is 0.90, not 0.45."""
        rows = [
            _row(0, ns=0, commit=90 * GIB, limit=100 * GIB),
            _row(1, ns=1_000_000_000, commit=90 * GIB, limit=200 * GIB),
        ]
        decision = evaluate_capacity(rows, policy=policy)
        assert decision["verdict"] == "FAIL"
        assert decision["peak_commit_ratio"] == {"num": 90 * GIB, "den": 100 * GIB}
        assert decision["breaches"]

    def test_peak_uses_the_same_sample_on_both_sides(self, policy):
        rows = [
            _row(0, ns=0, commit=10 * GIB, limit=100 * GIB),
            _row(1, ns=1_000_000_000, commit=70 * GIB, limit=100 * GIB),
        ]
        decision = evaluate_capacity(rows, policy=policy)
        assert decision["verdict"] == "PASS"
        assert decision["peak_commit_ratio"] == {"num": 70 * GIB, "den": 100 * GIB}

    def test_a_clean_stage_passes(self, policy):
        rows = [_row(i, ns=i * 1_000_000_000, commit=20 * GIB, limit=100 * GIB)
                for i in range(5)]
        assert evaluate_capacity(rows, policy=policy)["verdict"] == "PASS"

    def test_physical_floor_is_enforced(self, policy):
        # 32 GiB total -> floor = max(2 GiB, 3.2 GiB); 1 GiB available is a breach
        rows = [_row(0, ns=0, commit=10 * GIB, limit=100 * GIB, phys_avail=1 * GIB)]
        decision = evaluate_capacity(rows, policy=policy)
        assert decision["verdict"] == "FAIL"
        assert any(b["code"] == "PHYSICAL_FLOOR_BREACH" for b in decision["breaches"])

    def test_rss_ceiling_is_enforced(self, policy):
        rows = [_row(0, ns=0, commit=10 * GIB, limit=100 * GIB, rss=25 * GIB)]
        assert evaluate_capacity(rows, policy=policy)["verdict"] == "FAIL"


def _complete_preflight(**kwargs):
    # These tests isolate the arithmetic; provide explicit valid observations for
    # every other required guard. Missing-observation rejection is tested in R4.
    kwargs.setdefault("physical_available_bytes", 16 * GIB)
    kwargs.setdefault("physical_total_bytes", 32 * GIB)
    kwargs.setdefault("volumes", [{"name": "TEST", "free_bytes": 100 * GIB, "required_bytes": GIB}])
    return preflight_capacity(**kwargs)


class TestPreflight:
    def test_a_comfortable_baseline_still_has_to_satisfy_the_inequality(self, policy):
        """baseline <= 0.70 is not enough: the job's own increment is added."""
        limit = 100 * GIB
        # baseline 23.52 GiB passes the "<= 0.70 L" rule of thumb...
        baseline = int(0.70 * limit)
        # ...but the measured own increment (~9.167 GiB) pushes it over 0.8 L
        outcome = _complete_preflight(
            baseline_commit_bytes=baseline, delta_commit_bytes=int(9.167 * GIB),
            commit_limit_bytes=limit, policy=policy,
        )
        assert outcome["status"] == "PREFLIGHT_REFUSED"
        assert outcome["checks"]["commit_projection_within_limit"] is False
        assert outcome["recommended_fixed_workers"] is None  # registered policy already uses four

    def test_the_inequality_passes_with_headroom(self, policy):
        outcome = _complete_preflight(
            baseline_commit_bytes=int(0.30 * 100 * GIB),
            delta_commit_bytes=int(9.167 * GIB),
            commit_limit_bytes=100 * GIB, policy=policy,
        )
        assert outcome["status"] == "PASS"
        assert outcome["recommended_fixed_workers"] is None

    def test_the_margin_is_applied_to_the_estimate(self, policy):
        limit = 100 * GIB
        outcome = _complete_preflight(
            baseline_commit_bytes=int(0.70 * limit),
            delta_commit_bytes=4 * GIB,  # 5 GiB with the 5/4 margin
            commit_limit_bytes=limit, policy=policy,
        )
        assert outcome["projected_commit_bytes"] == int(0.70 * limit) + 5 * GIB

    def test_physical_headroom_and_volumes_are_checked(self, policy):
        outcome = _complete_preflight(
            baseline_commit_bytes=10 * GIB, delta_commit_bytes=1 * GIB,
            commit_limit_bytes=100 * GIB, physical_available_bytes=1 * GIB,
            physical_total_bytes=32 * GIB,
            volumes=[{"name": "F:", "free_bytes": 100 * GIB,
                      "required_bytes": 90 * GIB}],
            policy=policy,
        )
        assert outcome["status"] == "PREFLIGHT_REFUSED"
        assert outcome["checks"]["physical_memory_headroom"] is False
        assert outcome["checks"]["volumes_within_limit"] is False
        assert any("available physical" in r for r in outcome["reasons"])
        assert any("volume F:" in r for r in outcome["reasons"])

    def test_a_refusal_does_not_silently_lower_parallelism(self, policy):
        outcome = _complete_preflight(
            baseline_commit_bytes=95 * GIB, delta_commit_bytes=1 * GIB,
            commit_limit_bytes=100 * GIB, workers=8, policy=policy,
        )
        assert outcome["workers"] == 8
        assert "PREFLIGHT_REFUSED" in outcome["note"]


class TestIncompleteLatching:
    def test_sampler_death_after_one_sample_is_incomplete(self, policy):
        """The probe: first sample ok, second raises -> INCOMPLETE, never PASS."""
        rows = [
            _row(0, ns=0, commit=10 * GIB, limit=100 * GIB),
            _row(1, ns=1_000_000_000, commit=10 * GIB, limit=100 * GIB,
                 ok=False, error="SAMPLER_ERROR"),
        ]
        decision = evaluate_capacity(rows, policy=policy)
        assert decision["verdict"] == "INCOMPLETE"
        assert decision["ok_samples"] == 1

    def test_zero_samples_is_incomplete(self, policy):
        decision = evaluate_capacity([], policy=policy)
        assert decision["verdict"] == "INCOMPLETE"
        assert decision["issues"] == ["zero samples: the stage was never observed"]

    def test_a_sixty_second_gap_is_incomplete(self, policy):
        rows = [
            _row(0, ns=0, commit=10 * GIB, limit=100 * GIB),
            _row(1, ns=60_000_000_000, commit=10 * GIB, limit=100 * GIB),
        ]
        decision = evaluate_capacity(rows, policy=policy)
        assert decision["verdict"] == "INCOMPLETE"
        assert any("exceeds the policy maximum" in i for i in decision["issues"])

    def test_negative_counters_are_incomplete_not_zero(self, policy):
        rows = [_row(0, ns=0, commit=-1, limit=100 * GIB)]
        decision = evaluate_capacity(rows, policy=policy)
        assert decision["verdict"] == "INCOMPLETE"
        assert any("commit_total_bytes" in i for i in decision["issues"])

    def test_a_breach_is_not_cleared_by_a_later_good_sample(self, policy):
        rows = [
            _row(0, ns=0, commit=95 * GIB, limit=100 * GIB),
            _row(1, ns=1_000_000_000, commit=10 * GIB, limit=100 * GIB),
        ]
        decision = evaluate_capacity(rows, policy=policy)
        assert decision["verdict"] == "FAIL"
