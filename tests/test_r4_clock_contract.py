"""R4: coarse clocks may repeat; sample identity, gaps and coverage stay strict."""

from copy import deepcopy

import pytest

from owtda_cal.resource_policy import evaluate_capacity, load_policy, policy_sha256

GIB = 1024**3
RUN = "TEST_R4_CLOCK"


def _rows():
    return [
        {
            "schema_version": 1,
            "run_id": RUN,
            "policy_sha256": policy_sha256(),
            "seq": index,
            "monotonic_ns": timestamp,
            "stage": stage,
            "ok": True,
            "error": None,
            "commit_total_bytes": 40 * GIB,
            "commit_limit_bytes": 100 * GIB,
            "physical_total_bytes": 32 * GIB,
            "physical_available_bytes": 16 * GIB,
            "rss_tree_bytes": 4 * GIB,
        }
        for index, (timestamp, stage) in enumerate(
            [(1_000_000_000, "start"), (1_000_000_000, "compute"),
             (1_080_000_000, "teardown")]
        )
    ]


def _judge(rows, **kwargs):
    return evaluate_capacity(
        rows,
        policy=load_policy(),
        expected_run_id=RUN,
        expected_policy_sha256=policy_sha256(),
        require_boundaries=True,
        **kwargs,
    )


def test_adjacent_samples_within_one_tick_pass():
    result = _judge(_rows())
    assert result["verdict"] == "PASS", result
    assert result["issues"] == []


def test_breach_in_a_shared_tick_is_still_a_breach():
    rows = _rows()
    rows[0]["commit_total_bytes"] = 90 * GIB
    rows[1]["commit_limit_bytes"] = 200 * GIB
    result = _judge(rows)
    assert result["verdict"] == "FAIL", result
    assert any(b["code"] == "COMMIT_RATIO_BREACH" for b in result["breaches"])
    assert result["peak_commit_ratio"] == {"num": 90 * GIB, "den": 100 * GIB}


@pytest.mark.parametrize(
    ("field", "value", "message"),
    [
        ("seq", 0, "duplicate seq"),
        ("seq", 2, "non-contiguous"),
        ("run_id", "OTHER", "run identity mismatch"),
        ("run_id", None, "missing run identity"),
        ("policy_sha256", "0" * 64, "invalid policy digest"),
        ("policy_sha256", "f" * 64, "policy identity mismatch"),
        ("monotonic_ns", 999_999_999, "backwards"),
        ("monotonic_ns", -1, "monotonic_ns"),
        ("monotonic_ns", 1.0, "monotonic_ns"),
        ("physical_available_bytes", None, "physical_available_bytes"),
        ("error", "UNEXPECTED", "successful sample carries an error"),
    ],
)
def test_existing_integrity_rejections_are_preserved(field, value, message):
    rows = _rows()
    rows[1][field] = value
    result = _judge(rows)
    assert result["verdict"] == "INCOMPLETE", result
    assert any(message in issue for issue in result["issues"]), result


def test_gap_beyond_registered_maximum_is_rejected():
    rows = _rows()
    rows[-1]["monotonic_ns"] = (
        rows[1]["monotonic_ns"] + load_policy()["sampling"]["max_interval_ns"] + 1
    )
    result = _judge(rows)
    assert result["verdict"] == "INCOMPLETE", result
    assert any("gap" in issue for issue in result["issues"])


def test_duplicate_row_cannot_be_hidden_by_equal_time():
    rows = _rows()
    rows.insert(1, deepcopy(rows[0]))
    result = _judge(rows)
    assert result["verdict"] == "INCOMPLETE", result
    assert any("seq" in issue for issue in result["issues"])


def test_missing_boundary_still_fails():
    rows = _rows()
    rows[-1]["stage"] = "compute"
    result = _judge(rows)
    assert result["verdict"] == "INCOMPLETE", result
    assert "end boundary sample missing" in result["issues"]


def test_frozen_clock_cannot_cover_a_later_protected_end():
    rows = _rows()
    for row in rows:
        row["monotonic_ns"] = 1_000_000_000
    result = _judge(rows, expected_start_ns=1_000_000_000, expected_end_ns=2_000_000_000)
    assert result["verdict"] == "INCOMPLETE", result
    assert "sampling ends before the protected work" in result["issues"]


def test_incomplete_stream_retains_the_observed_breach():
    rows = _rows()
    rows[0]["commit_total_bytes"] = 95 * GIB
    rows[1]["ok"] = False
    rows[1]["error"] = "SAMPLER_ERROR:TEST"
    result = _judge(rows)
    assert result["verdict"] == "INCOMPLETE", result
    assert any(b["code"] == "COMMIT_RATIO_BREACH" for b in result["breaches"])
