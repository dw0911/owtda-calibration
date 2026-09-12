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


def evaluate_capacity(rows: list[dict], *, policy: dict) -> dict:
    """Rebuild the capacity verdict from raw samples; pure, no I/O.

    ``rows`` are the raw JSONL samples of one stage.  The verdict is
    ``INCOMPLETE`` unless the observation set is complete, and ``FAIL`` if any
    hard limit is breached -- breaching latches and can never be cleared by a
    later good sample.
    """
    limits = policy["limits"]
    ratio = limits["host_commit_fraction_max"]
    floor = limits["host_available_phys_floor"]
    floor_frac = floor["fraction_of_physical_total"]
    max_gap_ns = int(policy["sampling"]["max_interval_ns"])
    rss_max = int(limits["peak_total_rss_bytes_max"])

    issues: list[str] = []
    breached: list[str] = []
    peak: dict | None = None
    previous_ns: int | None = None
    gap_too_large = False

    for row in rows:
        seq = row.get("seq")
        okay = row.get("ok")
        if okay is not True:
            issues.append(f"seq={seq}: sample is not ok (ok={okay!r}, error={row.get('error')!r})")
            continue
        commit_total = _get_int(row, "commit_total_bytes", issues, seq)
        commit_limit = _get_int(row, "commit_limit_bytes", issues, seq)
        phys_total = _get_int(row, "physical_total_bytes", issues, seq)
        phys_avail = _get_int(row, "physical_available_bytes", issues, seq)
        rss = _get_int(row, "rss_tree_bytes", issues, seq)
        now_ns = row.get("monotonic_ns")
        if isinstance(now_ns, bool) or not isinstance(now_ns, int):
            issues.append(f"seq={seq}: monotonic_ns missing or not an int ({now_ns!r})")
        elif previous_ns is not None and now_ns - previous_ns > max_gap_ns:
            gap_too_large = True
            issues.append(
                f"seq={seq}: gap {now_ns - previous_ns} ns exceeds the policy maximum "
                f"of {max_gap_ns} ns"
            )
        if isinstance(now_ns, int) and not isinstance(now_ns, bool):
            previous_ns = now_ns

        if commit_total is not None and commit_limit is not None:
            if commit_limit == 0:
                issues.append(f"seq={seq}: commit_limit_bytes is zero")
            else:
                # paired comparison: both counters of the same sample
                if commit_total * ratio["den"] > ratio["num"] * commit_limit:
                    breached.append(
                        f"seq={seq}: commit ratio {commit_total}/{commit_limit} > "
                        f"{ratio['num']}/{ratio['den']}"
                    )
                if peak is None or commit_total * peak["limit"] > peak["commit"] * commit_limit:
                    peak = {"commit": commit_total, "limit": commit_limit}
        if phys_avail is not None and phys_total is not None:
            required = max(int(floor["absolute_bytes"]),
                           (floor_frac["num"] * phys_total) // floor_frac["den"])
            if phys_avail < required:
                breached.append(
                    f"seq={seq}: available physical {phys_avail} < required {required}"
                )
        if rss is not None and rss > rss_max:
            breached.append(f"seq={seq}: rss_tree_bytes {rss} > {rss_max}")

    if not rows:
        issues.append("zero samples: the stage was never observed")
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
        "ok_samples": sum(1 for row in rows if row.get("ok") is True),
        "peak_commit_ratio": (
            {"num": peak["commit"], "den": peak["limit"]} if peak else None
        ),
        "breaches": breached,
        "issues": issues,
    }


__all__ = [
    "POLICY_FILENAME",
    "SOURCE_FILENAME",
    "ResourcePolicyError",
    "evaluate_capacity",
    "load_policy",
    "policy_path",
    "policy_sha256",
]
