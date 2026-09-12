"""Strict contract oracles -- the independent verifier's rules (task pack §2.3).

Re-audit 2026-09-13 pinned seven mutations that the self-check did not notice:
a deleted ledger, a deleted RUN seal, a rewritten row count, duplicated JUnit
testcase identities, a p-value nudged off the legal grid, ``reject`` stored as an
integer, and a duplicated scope row.  Every one of them is a *rule* the checker
never implemented, so they are implemented here as pure functions -- no I/O
policy, no reuse of the producer's own summary.

Rules:

* ``p`` is recomputed **forward** from ``K`` (``p = (K+1)/(B+1)``); ``K`` is
  never rounded back out of ``p``.  ``K`` must be a strict ``int``, ``reject`` a
  strict ``bool``, and ``p`` finite and on the grid.
* expected/actual are checked for *uniqueness* before they are compared as sets,
  and matched entries are compared field by field -- a bare set comparison hides
  duplicates and silently ignores upstream identity.
* a file reference must exist, sit inside the authorised evidence root, and its
  hash must be the hash of the bytes actually on disk.
* the JUnit identity set is compared exactly, against an explicit approved skip
  set.
* monitoring completeness is rebuilt from the raw samples, never from the
  producer's ``incomplete=false`` claim (see :mod:`owtda_cal.resource_policy`).
"""

from __future__ import annotations

import hashlib
import math
import os
import xml.etree.ElementTree as ET
from collections.abc import Iterable, Sequence

B_DEFAULT = 999
REJECT_ALPHA_EXCEED = 49  # p <= 0.05 <=> exceed <= 49 (Plan §6)
_P_GRID_TOL = 1e-12


def _issue(code: str, where: str, detail: str) -> dict:
    return {"code": code, "where": where, "detail": detail}


def check_p_arithmetic(row: dict, *, where: str = "row", B: int = B_DEFAULT) -> list[dict]:
    """Recompute ``p`` and ``reject`` forward from ``K``; never the reverse."""
    issues: list[dict] = []
    k = row.get("K", row.get("exceed"))
    if isinstance(k, bool) or not isinstance(k, int):
        issues.append(_issue("K_NOT_INT", where, f"K/exceed must be a strict int, got {k!r}"))
        return issues
    if not 0 <= k <= B:
        issues.append(_issue("K_OUT_OF_RANGE", where, f"K={k} outside [0, {B}]"))
        return issues

    p = row.get("p")
    if isinstance(p, bool) or not isinstance(p, (int, float)):
        issues.append(_issue("P_NOT_NUMERIC", where, f"p must be numeric, got {p!r}"))
        return issues
    p = float(p)
    if not math.isfinite(p):
        issues.append(_issue("P_NOT_FINITE", where, f"p={p!r} is not finite"))
        return issues
    expected_p = (k + 1) / (B + 1)
    if not math.isclose(p, expected_p, rel_tol=0.0, abs_tol=_P_GRID_TOL):
        issues.append(
            _issue("P_OFF_GRID", where,
                   f"p={p!r} is not on the grid; K={k} gives {expected_p!r}")
        )

    reject = row.get("reject")
    if not isinstance(reject, bool):
        issues.append(
            _issue("REJECT_NOT_BOOL", where,
                   f"reject must be a strict bool, got {reject!r} ({type(reject).__name__})")
        )
    elif reject != (k <= REJECT_ALPHA_EXCEED):
        issues.append(
            _issue("REJECT_INCONSISTENT", where,
                   f"reject={reject} but K={k} implies {k <= REJECT_ALPHA_EXCEED}")
        )
    return issues


def compare_identity_sets(
    expected_rows: Sequence[dict],
    actual_rows: Sequence[dict],
    *,
    key_field: str,
    identity_fields: Iterable[str] = (),
    where: str = "set",
) -> dict:
    """Uniqueness first, then the set comparison, then per-field identity.

    A plain ``set(expected) == set(actual)`` passes when either side contains a
    duplicate, and it cannot notice that a matched key carries a different
    upstream id -- both were defects the re-audit reproduced.
    """
    issues: list[dict] = []

    def _index(rows: Sequence[dict]) -> tuple[list, dict]:
        keys: list = []
        by_key: dict = {}
        for position, row in enumerate(rows):
            key = row.get(key_field)
            keys.append(key)
            if key in by_key:
                issues.append(
                    _issue("DUPLICATE_ENTRY", where,
                           f"{key_field}={key!r} appears more than once (position {position})")
                )
            by_key.setdefault(key, row)
        return keys, by_key

    _expected_keys, expected_by_key = _index(expected_rows)
    _actual_keys, actual_by_key = _index(actual_rows)

    expected_set = set(expected_by_key)
    actual_set = set(actual_by_key)
    missing = sorted(expected_set - actual_set, key=repr)
    extra = sorted(actual_set - expected_set, key=repr)
    for key in missing:
        issues.append(_issue("MISSING_FROM_ACTUAL", where, f"{key_field}={key!r} is not in actual"))
    for key in extra:
        issues.append(_issue("EXTRA_IN_ACTUAL", where, f"{key_field}={key!r} is not in expected"))

    identity_mismatches: list[dict] = []
    for key in sorted(expected_set & actual_set, key=repr):
        for field in identity_fields:
            want = expected_by_key[key].get(field)
            got = actual_by_key[key].get(field)
            if want != got:
                detail = {"key": key, "field": field, "expected": want, "actual": got}
                identity_mismatches.append(detail)
                issues.append(
                    _issue("IDENTITY_FIELD_MISMATCH", where,
                           f"{key_field}={key!r}: {field} {want!r} != {got!r}")
                )
    return {
        "issues": issues,
        "missing": missing,
        "extra": extra,
        "identity_mismatches": identity_mismatches,
        "equal": not issues,
    }


def verify_file_ref(ref: dict, *, evidence_root: str, where: str = "file_ref") -> list[dict]:
    """A file reference must exist, be inside the root, and hash to real bytes."""
    issues: list[dict] = []
    path = ref.get("path")
    declared = ref.get("sha256")
    if not path:
        return [_issue("FILE_REF_NO_PATH", where, "no path in the reference")]
    if not isinstance(declared, str) or len(declared) != 64:
        issues.append(
            _issue("FILE_REF_HASH_INVALID", where,
                   f"sha256 must be 64 hex chars, got {declared!r}")
        )
    root = os.path.realpath(evidence_root)
    target = os.path.realpath(path)
    if os.path.commonpath([root, target]) != root:
        issues.append(
            _issue("FILE_REF_OUTSIDE_ROOT", where,
                   f"{target!r} is outside the authorised evidence root {root!r}")
        )
        return issues
    if not os.path.isfile(target):
        issues.append(_issue("FILE_REF_MISSING", where, f"{target!r} does not exist"))
        return issues
    actual = hashlib.sha256(open(target, "rb").read()).hexdigest()
    if declared and actual != declared:
        issues.append(
            _issue("FILE_REF_HASH_MISMATCH", where,
                   f"{target!r} hashes to {actual[:16]}..., the reference claims "
                   f"{str(declared)[:16]}...")
        )
    return issues


def _testcase_identity(element: ET.Element) -> str:
    return f"{element.get('classname', '')}::{element.get('name', '')}"


def check_junit(
    junit_xml: str | bytes,
    *,
    expected_identities: Iterable[str] | None = None,
    approved_skips: Iterable[str] = (),
    where: str = "junit",
) -> dict:
    """Exact testcase identity set + approved skip set; duplicates are a defect."""
    issues: list[dict] = []
    try:
        root = ET.fromstring(junit_xml)
    except ET.ParseError as exc:
        return {
            "issues": [_issue("JUNIT_UNPARSEABLE", where, str(exc))],
            "identities": set(), "skipped": set(),
        }
    identities: list[str] = []
    skipped: set[str] = set()
    for case in root.iter("testcase"):
        identity = _testcase_identity(case)
        identities.append(identity)
        if case.find("skipped") is not None:
            skipped.add(identity)
    seen: set[str] = set()
    for identity in identities:
        if identity in seen:
            issues.append(
                _issue("JUNIT_DUPLICATE_TESTCASE", where,
                       f"{identity!r} appears more than once")
            )
        seen.add(identity)

    found = set(identities)
    if expected_identities is not None:
        expected = set(expected_identities)
        for identity in sorted(expected - found, key=repr):
            issues.append(_issue("JUNIT_MISSING_TESTCASE", where, f"{identity!r} did not run"))
        for identity in sorted(found - expected, key=repr):
            issues.append(_issue("JUNIT_EXTRA_TESTCASE", where, f"{identity!r} is not registered"))
    approved = set(approved_skips)
    for identity in sorted(skipped - approved, key=repr):
        issues.append(
            _issue("JUNIT_UNAPPROVED_SKIP", where,
                   f"{identity!r} is skipped but not in the approved skip set")
        )
    return {"issues": issues, "identities": found, "skipped": skipped}


def disclosure_consistency(inline_verdict: str, recomputed_verdict: str) -> dict:
    """Disclosure is about agreement, not about being green.

    ``inline == recomputed == FAIL`` means the package disclosed its own failure
    correctly; the old checker counted that as a disclosure failure, which
    punished an honest submission.  Admission is a separate question.
    """
    normalise = lambda value: str(value).strip().upper()
    inline, recomputed = normalise(inline_verdict), normalise(recomputed_verdict)
    agreed = inline == recomputed
    return {
        "inline": inline,
        "recomputed": recomputed,
        "disclosed_consistently": agreed,
        "admissible": agreed and inline == "PASS",
        "note": (
            "both verdicts are FAIL: the package disclosed its own result correctly; "
            "this is not a disclosure defect"
        ) if agreed and inline == "FAIL" else "",
    }


__all__ = [
    "B_DEFAULT",
    "REJECT_ALPHA_EXCEED",
    "check_junit",
    "check_p_arithmetic",
    "compare_identity_sets",
    "disclosure_consistency",
    "verify_file_ref",
]
