"""The capacity monitor: raw rows, latches and stop-request (§3.2).

The re-audit (2026-09-13) reproduced three things with the real sampler:

* the summary divided ``max_k C_k`` by the last commit limit -- a host that
  peaked at 0.90 was reported as 0.45 and passed;
* a sampler that raised after its first sample still produced
  ``incomplete=false`` and therefore PASS;
* monitoring stopped before the payload was written, so persistence was never
  observed.

These tests pin the replacement: one row per sample with both counters of the
same sample, a failed read is still a row, and every anomaly latches.
"""

from __future__ import annotations

import json
import sys
import threading
import time
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
AUDIT = REPO / "audit"
if str(AUDIT) not in sys.path:
    sys.path.insert(0, str(AUDIT))

import resource_sampler  # noqa: E402

GIB = 1024 ** 3


def _fast_policy() -> dict:
    """The executable policy with a short interval so the tests stay fast."""
    from owtda_cal.resource_policy import load_policy

    policy = json.loads(json.dumps(load_policy()))
    policy["sampling"]["interval_ns"] = 20_000_000
    return policy


def _info(commit_gib: float, limit_gib: float, *, phys_total_gib: float = 32.0,
          phys_avail_gib: float = 16.0) -> dict:
    return {
        "commit_total_bytes": int(commit_gib * GIB),
        "commit_limit_bytes": int(limit_gib * GIB),
        "commit_peak_bytes_since_boot": int(commit_gib * GIB),
        "physical_total_bytes": int(phys_total_gib * GIB),
        "physical_available_bytes": int(phys_avail_gib * GIB),
        "page_size_bytes": 4096,
    }


@pytest.fixture()
def monitor_factory(tmp_path):
    created: list[resource_sampler.CapacityMonitor] = []

    def _make(**kwargs):
        monitor = resource_sampler.CapacityMonitor(
            run_id="TEST_RUN",
            raw_path=tmp_path / "resources" / "capacity_raw.jsonl",
            policy=kwargs.pop("policy", None) or _fast_policy(),
            **kwargs,
        )
        created.append(monitor)
        return monitor

    yield _make
    for monitor in created:
        if monitor._thread is not None and monitor._thread.is_alive():
            monitor.stop()


class TestRawRows:
    def test_every_sample_writes_both_counters_of_the_same_instant(
        self, monitor_factory, monkeypatch, tmp_path
    ):
        samples = [_info(70, 100), _info(70, 200), _info(60, 200)]
        monkeypatch.setattr(
            resource_sampler, "performance_info",
            lambda: samples.pop(0) if samples else _info(60, 200),
        )
        monkeypatch.setattr(resource_sampler, "_tree_rss_bytes", lambda: 4 * GIB)
        monitor = monitor_factory()
        monitor.start()
        time.sleep(0.12)
        monitor.stop()
        rows = monitor.rows()
        assert len(rows) >= 2
        for row in rows:
            assert set(row) >= {
                "schema_version", "run_id", "policy_sha256", "seq", "monotonic_ns",
                "ok", "error", "stage", "commit_total_bytes", "commit_limit_bytes",
                "physical_total_bytes", "physical_available_bytes", "rss_tree_bytes",
            }
        written = [
            json.loads(line)
            for line in (tmp_path / "resources" / "capacity_raw.jsonl")
            .read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]
        assert len(written) == len(rows)

    def test_the_audit_probe_is_refused_from_the_raw_rows(
        self, monitor_factory, monkeypatch
    ):
        """C=90/L=100 then C=90/L=200: the real peak is 0.90, not 0.45."""
        samples = [_info(90, 100), _info(90, 200)]
        monkeypatch.setattr(
            resource_sampler, "performance_info",
            lambda: samples.pop(0) if samples else _info(90, 200),
        )
        monkeypatch.setattr(resource_sampler, "_tree_rss_bytes", lambda: 4 * GIB)
        monitor = monitor_factory()
        monitor.start()
        time.sleep(0.05)
        verdict = monitor.stop()
        assert verdict["status"] == "FAIL"
        assert any(b["code"] == "COMMIT_RATIO_BREACH" for b in verdict["breaches"])

    def test_a_clean_host_passes(self, monitor_factory, monkeypatch):
        samples = [_info(40, 100), _info(45, 100), _info(50, 100)]
        monkeypatch.setattr(
            resource_sampler, "performance_info",
            lambda: samples.pop(0) if samples else _info(50, 100),
        )
        monkeypatch.setattr(resource_sampler, "_tree_rss_bytes", lambda: 4 * GIB)
        monitor = monitor_factory()
        monitor.start()
        time.sleep(0.08)
        verdict = monitor.stop()
        assert verdict["status"] == "PASS"
        assert monitor.stop_requested.is_set() is False

    def test_boundary_samples_are_recorded(self, monitor_factory, monkeypatch):
        monkeypatch.setattr(resource_sampler, "performance_info", lambda: _info(50, 100))
        monkeypatch.setattr(resource_sampler, "_tree_rss_bytes", lambda: 4 * GIB)
        monitor = monitor_factory()
        monitor.start()
        time.sleep(0.05)
        monitor.stop()
        rows = monitor.rows()
        assert rows[0]["stage"] == "start"
        assert rows[-1]["stage"] == "teardown"


class TestLatches:
    def test_a_failed_read_is_still_a_row(self, monitor_factory, monkeypatch):
        """The probe: no capacity counters -> INCOMPLETE, never a zero and PASS."""
        monkeypatch.setattr(resource_sampler, "performance_info", lambda: None)
        monkeypatch.setattr(resource_sampler, "_tree_rss_bytes", lambda: 4 * GIB)
        monitor = monitor_factory()
        monitor.start()
        time.sleep(0.05)
        verdict = monitor.stop()
        assert any(row["ok"] is False for row in monitor.rows())
        assert all(row["error"] for row in monitor.rows() if row["ok"] is False)
        assert verdict["status"] == "INCOMPLETE"
        assert monitor.stop_requested.is_set() is True

    def test_a_sampler_exception_latches_and_requests_stop(
        self, monitor_factory, monkeypatch
    ):
        state = {"n": 0}

        def _flaky():
            state["n"] += 1
            if state["n"] > 1:
                raise RuntimeError("GetPerformanceInfo failed")
            return _info(50, 100)

        monkeypatch.setattr(resource_sampler, "performance_info", _flaky)
        monkeypatch.setattr(resource_sampler, "_tree_rss_bytes", lambda: 4 * GIB)
        monitor = monitor_factory()
        monitor.start()
        time.sleep(0.08)
        verdict = monitor.stop()
        assert verdict["status"] == "INCOMPLETE"
        assert monitor.stop_requested.is_set() is True

    def test_a_thread_that_dies_is_reported_not_silently_accepted(
        self, monitor_factory, monkeypatch
    ):
        monkeypatch.setattr(resource_sampler, "performance_info", lambda: _info(50, 100))
        monkeypatch.setattr(resource_sampler, "_tree_rss_bytes", lambda: 4 * GIB)
        class _ExplodingWait:
            """Makes the sampler's sleep raise, i.e. the thread dies mid-stage."""

            def __init__(self, real: threading.Event) -> None:
                self._real = real

            def is_set(self) -> bool:
                return self._real.is_set()

            def set(self) -> None:
                self._real.set()

            def wait(self, *_args, **_kwargs):
                raise RuntimeError("sampler died")

        monitor = monitor_factory()
        monitor.start()
        monitor._stop = _ExplodingWait(monitor._stop)
        time.sleep(0.1)
        verdict = monitor.stop()
        assert verdict["status"] == "INCOMPLETE"
        assert any("sampler_exception" in r for r in verdict["incomplete_reasons"])
        assert monitor.stop_requested.is_set() is True

    def test_a_breach_is_not_cleared_by_a_later_good_sample(
        self, monitor_factory, monkeypatch
    ):
        samples = [_info(95, 100), _info(20, 100), _info(20, 100)]
        monkeypatch.setattr(
            resource_sampler, "performance_info",
            lambda: samples.pop(0) if samples else _info(20, 100),
        )
        monkeypatch.setattr(resource_sampler, "_tree_rss_bytes", lambda: 4 * GIB)
        monitor = monitor_factory()
        monitor.start()
        time.sleep(0.08)
        verdict = monitor.stop()
        assert verdict["status"] == "FAIL"
        assert monitor.stop_requested.is_set() is True
        # the latch survives a re-read: a good sample cannot erase the breach
        assert monitor.verdict()["status"] == "FAIL"

    def test_a_gap_over_the_policy_maximum_latches(self, monitor_factory, monkeypatch):
        monkeypatch.setattr(resource_sampler, "performance_info", lambda: _info(50, 100))
        monkeypatch.setattr(resource_sampler, "_tree_rss_bytes", lambda: 4 * GIB)
        monitor = monitor_factory()
        monitor.start()
        with monitor._lock:
            monitor._last_ns = time.monotonic_ns() - 60_000_000_000  # 60 s ago
        monitor._write_sample(stage="compute")
        verdict = monitor.stop()
        assert verdict["status"] == "INCOMPLETE"
        assert any("gap_exceeds_max_interval_ns" in r for r in verdict["incomplete_reasons"])


class TestPolicyBinding:
    def test_interval_comes_from_the_policy(self, monitor_factory):
        monitor = monitor_factory(policy=_fast_policy())
        assert monitor.interval_ns == 20_000_000
        assert monitor.max_gap_ns == 3_000_000_000

    def test_rows_carry_the_policy_hash(self, monitor_factory, monkeypatch):
        from owtda_cal.resource_policy import policy_sha256

        monkeypatch.setattr(resource_sampler, "performance_info", lambda: _info(50, 100))
        monkeypatch.setattr(resource_sampler, "_tree_rss_bytes", lambda: 4 * GIB)
        monitor = monitor_factory()
        monitor.start()
        time.sleep(0.05)
        monitor.stop()
        assert {row["policy_sha256"] for row in monitor.rows()} == {policy_sha256()}
