"""Machine-readable capacity policy and the paired-capacity decision (§3.1, §3.2).

Two things live here and nowhere else:

* :func:`load_policy` reads ``governance/RESOURCE_POLICY_EXECUTABLE.json`` -- the
  exact implementation of the V2 coefficients.  Every ratio in it is an integer
  rational ``{num, den}``; the file is bound to the hash of the V2 document it
  implements, and code is not allowed to keep a second, looser copy.
* :func:`evaluate_capacity` is the pure decision function the re-audit
  (2026-09-13) showed was missing.  The old summary stored ``max_k C_k`` and
  separately overwrote the commit limit, then divided the two -- which is not
  ``max_k C_k / L_k`` when CommitLimit moves.  It also trusted the producer's
  ``incomplete=false`` flag.  Here the verdict is rebuilt from the raw rows:
  each comparison uses the two counters of the *same* sample, and unknown or
  missing observations latch ``INCOMPLETE`` instead of being filled with zero.
"""

from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path

POLICY_FILENAME = "RESOURCE_POLICY_EXECUTABLE.json"
SOURCE_FILENAME = "RESOURCE_POLICY_V2.json"


class ResourcePolicyError(ValueError):
    """Policy file missing, unbound, or not integer-exact."""


def _repo_root() -> Path:
    here = Path(__file__).resolve()
    for parent in here.parents:
        if (parent / "governance" / POLICY_FILENAME).is_file():
            return parent
    raise ResourcePolicyError(
        f"cannot locate governance/{POLICY_FILENAME} above {here}"
    )


def policy_path(root: str | Path | None = None) -> Path:
    base = Path(root) if root is not None else _repo_root()
    return base / "governance" / POLICY_FILENAME


def policy_sha256(root: str | Path | None = None) -> str:
    """SHA-256 of the exact policy bytes (this is what a run binds to)."""
    return hashlib.sha256(policy_path(root).read_bytes()).hexdigest()


def load_policy(root: str | Path | None = None) -> dict:
    """Load the executable policy and verify it is bound to the V2 document."""
    target = policy_path(root)
    policy = json.loads(target.read_text(encoding="utf-8"))
    source = policy.get("source_policy", {})
    declared = source.get("sha256")
    declared_file = Path(str(source.get("file", SOURCE_FILENAME))).name
    source_path = target.parent / declared_file
    if not source_path.is_file():
        raise ResourcePolicyError(f"the V2 document {source_path} is missing")
    actual = hashlib.sha256(source_path.read_bytes()).hexdigest()
    if declared != actual:
        raise ResourcePolicyError(
            "policy is not bound to the V2 document: declared "
            f"{declared!r} != actual {actual!r}"
        )
    _assert_integers_only(policy)
    return policy


def _assert_integers_only(node, where: str = "policy") -> None:
    """Coefficients must be integers or {num, den} pairs -- never floats."""
    if isinstance(node, dict):
        if set(node) == {"num", "den"}:
            for key in ("num", "den"):
                value = node[key]
                if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
                    raise ResourcePolicyError(
                        f"{where}: rational {key} must be a positive int, got {value!r}"
                    )
            return
        for key, value in node.items():
            _assert_integers_only(value, f"{where}.{key}")
    elif isinstance(node, list):
        for index, value in enumerate(node):
            _assert_integers_only(value, f"{where}[{index}]")
    elif isinstance(node, float):
        raise ResourcePolicyError(f"{where}: float coefficient {node!r} is not allowed")


def _get_int(row: dict, field: str, issues: list[str], seq: object) -> int | None:
    value = row.get(field)
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        issues.append(f"seq={seq}: {field} missing or not a non-negative int ({value!r})")
        return None
    return value


def inspect_row(row: dict, *, policy: dict) -> dict:
    """Judge **one** raw sample; pure.

    Both counters of a ratio come from this same row -- that is the whole point:
    the old record divided ``max_k C_k`` by a commit limit that had been
    overwritten by a later sample.
    """
    limits = policy["limits"]
    ratio = limits["host_commit_fraction_max"]
    floor = limits["host_available_phys_floor"]
    floor_frac = floor["fraction_of_physical_total"]
    rss_max = int(limits["peak_total_rss_bytes_max"])

    issues: list[str] = []
    breaches: list[str] = []
    seq = row.get("seq")
    if row.get("ok") is not True:
        return {
            "issues": [f"seq={seq}: sample is not ok (ok={row.get('ok')!r}, "
                       f"error={row.get('error')!r})"],
            "breaches": [], "ratio": None, "ok": False,
        }
    commit_total = _get_int(row, "commit_total_bytes", issues, seq)
    commit_limit = _get_int(row, "commit_limit_bytes", issues, seq)
    phys_total = _get_int(row, "physical_total_bytes", issues, seq)
    phys_avail = _get_int(row, "physical_available_bytes", issues, seq)
    rss = _get_int(row, "rss_tree_bytes", issues, seq)

    ratio_seen = None
    if commit_total is not None and commit_limit is not None:
        if commit_limit == 0:
            issues.append(f"seq={seq}: commit_limit_bytes is zero")
        else:
            ratio_seen = {"commit": commit_total, "limit": commit_limit}
            if commit_total * ratio["den"] > ratio["num"] * commit_limit:
                breaches.append({
                    "code": "COMMIT_RATIO_BREACH", "seq": seq,
                    "detail": f"commit ratio {commit_total}/{commit_limit} > "
                              f"{ratio['num']}/{ratio['den']}",
                })
    if phys_total is not None and phys_total == 0:
        issues.append(f"seq={seq}: physical_total_bytes must be positive")
    if phys_avail is not None and phys_total is not None and phys_avail > phys_total:
        issues.append(f"seq={seq}: available physical exceeds total physical")
    if phys_avail is not None and phys_total is not None:
        required = max(int(floor["absolute_bytes"]),
                       (floor_frac["num"] * phys_total + floor_frac["den"] - 1) // floor_frac["den"])
        if phys_avail < required:
            breaches.append({
                "code": "PHYSICAL_FLOOR_BREACH", "seq": seq,
                "detail": f"available physical {phys_avail} < required {required}",
            })
    if rss is not None and rss > rss_max:
        breaches.append({
            "code": "RSS_BREACH", "seq": seq,
            "detail": f"rss_tree_bytes {rss} > {rss_max}",
        })
    return {"issues": issues, "breaches": breaches, "ratio": ratio_seen, "ok": True}


def evaluate_capacity(
    rows: list[dict], *, policy: dict,
    expected_run_id: str | None = None,
    expected_policy_sha256: str | None = None,
    require_boundaries: bool = False,
    expected_start_ns: int | None = None,
    expected_end_ns: int | None = None,
) -> dict:
    """Rebuild the capacity verdict from raw samples; pure, no I/O.

    ``rows`` are the raw JSONL samples of one stage.  The verdict is
    ``INCOMPLETE`` unless the observation set is complete, and ``FAIL`` if any
    hard limit is breached -- breaching latches and can never be cleared by a
    later good sample.
    """
    max_gap_ns = int(policy["sampling"]["max_interval_ns"])

    issues: list[str] = []
    breached: list[str] = []
    peak: dict | None = None
    previous_ns: int | None = None
    gap_too_large = False

    stream_run = expected_run_id
    stream_policy = expected_policy_sha256
    if not isinstance(rows, list):
        rows = []
        issues.append("samples must be a list")
    for position, row in enumerate(rows):
        if not isinstance(row, dict):
            issues.append(f"sample {position}: expected an object")
            continue
        seq = row.get("seq")
        if type(seq) is not int or seq != position:
            issues.append(f"sample {position}: non-contiguous or duplicate seq {seq!r}")
        run_id = row.get("run_id")
        digest = row.get("policy_sha256")
        if not isinstance(run_id, str) or not run_id:
            issues.append(f"seq={seq}: missing run identity")
        elif stream_run is None:
            stream_run = run_id
        elif run_id != stream_run:
            issues.append(f"seq={seq}: run identity mismatch")
        if not isinstance(digest, str) or not re.fullmatch(r"[0-9a-f]{64}", digest) or digest == "0" * 64:
            issues.append(f"seq={seq}: invalid policy digest")
        elif stream_policy is None:
            stream_policy = digest
        elif digest != stream_policy:
            issues.append(f"seq={seq}: policy identity mismatch")
        if row.get("ok") is True and row.get("error") is not None:
            issues.append(f"seq={seq}: successful sample carries an error")
        now_ns = row.get("monotonic_ns")
        if type(now_ns) is not int or now_ns < 0:
            issues.append(f"seq={seq}: monotonic_ns missing or not an int ({now_ns!r})")
        else:
            # A monotonic clock may return the same value within one hardware
            # tick (notably GetTickCount64 on CPython 3.12 / Windows). Sequence
            # numbers supply strict sample ordering; timestamps must not regress.
            if previous_ns is not None and now_ns < previous_ns:
                issues.append(f"seq={seq}: timestamps must not go backwards")
            if previous_ns is not None and now_ns - previous_ns > max_gap_ns:
                gap_too_large = True
                issues.append(
                    f"seq={seq}: gap {now_ns - previous_ns} ns exceeds the policy "
                    f"maximum of {max_gap_ns} ns"
                )
            previous_ns = now_ns
        seen = inspect_row(row, policy=policy)
        issues.extend(seen["issues"])
        breached.extend(seen["breaches"])
        ratio_seen = seen["ratio"]
        if ratio_seen is not None and (
            peak is None
            or ratio_seen["commit"] * peak["limit"] > peak["commit"] * ratio_seen["limit"]
        ):
            peak = ratio_seen

    if not rows:
        issues.append("zero samples: the stage was never observed")
    if require_boundaries and rows:
        if not isinstance(rows[0], dict) or rows[0].get("stage") != "start":
            issues.append("start boundary sample missing")
        if not isinstance(rows[-1], dict) or rows[-1].get("stage") != "teardown":
            issues.append("end boundary sample missing")
        if len(rows) < 2:
            issues.append("a complete stream needs both boundary samples")
    if rows and expected_start_ns is not None and (
        rows[0].get("monotonic_ns", expected_start_ns + 1) > expected_start_ns
    ):
        issues.append("sampling starts after the protected work")
    if rows and expected_end_ns is not None and (
        rows[-1].get("monotonic_ns", expected_end_ns - 1) < expected_end_ns
    ):
        issues.append("sampling ends before the protected work")
    if gap_too_large:
        issues.append("sampling gap exceeded the policy maximum")

    if issues:
        verdict = "INCOMPLETE"
    elif breached:
        verdict = "FAIL"
    else:
        verdict = "PASS"
    return {
        "verdict": verdict,
        "samples": len(rows),
        "ok_samples": sum(1 for row in rows if isinstance(row, dict) and row.get("ok") is True),
        "peak_commit_ratio": (
            {"num": peak["commit"], "den": peak["limit"]} if peak else None
        ),
        "breaches": breached,
        "issues": issues,
    }


def preflight_capacity(
    *,
    baseline_commit_bytes: int,
    delta_commit_bytes: int,
    commit_limit_bytes: int,
    physical_available_bytes: int | None = None,
    physical_total_bytes: int | None = None,
    volumes: list[dict] | None = None,
    workers: int | None = None,
    policy: dict,
) -> dict:
    """The pre-flight inequality (§3.5): ``C_baseline + ΔC_hat <= 4/5 L``.

    Integer cross-multiplication only.  ``baseline <= 0.70`` is *not* a
    substitute for the inequality: the audit recorded a host whose baseline
    looked comfortable while the run's own increment pushed it over.  The
    estimate carries the policy's 5/4 margin, and a refusal is recorded -- it
    never silently lowers the parallelism or starts the run anyway.
    """
    limits = policy["limits"]
    ratio = limits["host_commit_fraction_max"]
    margin = policy["preflight"]["delta_margin_multiplier"]
    floor = limits["host_available_phys_floor"]
    floor_frac = floor["fraction_of_physical_total"]
    disk = limits["disk_fraction_max"]

    for name, value in (("baseline_commit_bytes", baseline_commit_bytes),
                        ("delta_commit_bytes", delta_commit_bytes),
                        ("commit_limit_bytes", commit_limit_bytes)):
        if isinstance(value, bool) or not isinstance(value, int) or value < 0:
            raise ResourcePolicyError(f"{name} must be a non-negative int, got {value!r}")

    workers = policy["limits"]["workers"] if workers is None else workers
    delta_with_margin = (delta_commit_bytes * margin["num"] + margin["den"] - 1) // margin["den"]
    projected = baseline_commit_bytes + delta_with_margin
    lhs = projected * ratio["den"]
    rhs = ratio["num"] * commit_limit_bytes
    commit_ok = lhs <= rhs

    checks = {
        "commit_projection_within_limit": commit_ok and commit_limit_bytes > 0,
        "workers_match_policy": type(workers) is int and workers == policy["limits"]["workers"],
        "physical_measurements_complete": (
            type(physical_available_bytes) is int and type(physical_total_bytes) is int
            and physical_total_bytes > 0 and 0 <= physical_available_bytes <= physical_total_bytes),
        "volume_measurements_complete": isinstance(volumes, list) and bool(volumes),
    }
    reasons: list[str] = []
    if not commit_ok:
        reasons.append(
            f"C_baseline + ΔC_hat = {projected} exceeds {ratio['num']}/{ratio['den']} "
            f"of L = {commit_limit_bytes}"
        )

    if checks["physical_measurements_complete"]:
        required = max(int(floor["absolute_bytes"]),
                       (floor_frac["num"] * physical_total_bytes + floor_frac["den"] - 1) // floor_frac["den"])
        checks["physical_memory_headroom"] = physical_available_bytes >= required
        if physical_available_bytes < required:
            reasons.append(
                f"available physical {physical_available_bytes} < required {required}"
            )

    volume_reports = []
    for volume in volumes or []:
        free = volume.get("free_bytes")
        needed = volume.get("required_bytes")
        ok = (type(free) is int and type(needed) is int and free > 0 and needed >= 0
              and needed * disk["den"] <= disk["num"] * free)
        volume_reports.append({**volume, "within_limit": bool(ok)})
        if not ok:
            reasons.append(
                f"volume {volume.get('name', '?')}: required {needed} exceeds "
                f"{disk['num']}/{disk['den']} of free {free}"
            )
    if volume_reports:
        checks["volumes_within_limit"] = all(v["within_limit"] for v in volume_reports)

    reasons.extend(name for name, ok in checks.items() if not ok and name not in reasons)
    passed = all(checks.values())
    return {
        "status": "PASS" if passed else "PREFLIGHT_REFUSED",
        "passed": passed,
        "workers": workers,
        "projected_commit_bytes": projected,
        "margin": margin,
        "checks": checks,
        "volumes": volume_reports,
        "reasons": reasons,
        # A refusal may be re-registered with a *fixed* lower parallelism; the
        # run itself may never change parallelism mid-flight without a record.
        "recommended_fixed_workers": None if passed else (4 if workers > 4 else None),
        "note": (
            "a refusal records PREFLIGHT_REFUSED and does not start the run; the "
            "parallelism may only change through a registered configuration"
        ),
    }


__all__ = [
    "POLICY_FILENAME",
    "SOURCE_FILENAME",
    "ResourcePolicyError",
    "evaluate_capacity",
    "inspect_row",
    "load_policy",
    "policy_path",
    "policy_sha256",
    "preflight_capacity",
]
