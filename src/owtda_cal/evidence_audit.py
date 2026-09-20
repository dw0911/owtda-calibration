"""Independent on-disk evidence checks. No PH, simulation or mutation of evidence.

A summary is never a substitute for its payload. This module verifies the currently
specified fixture bytes; it deliberately does not claim a shared FORMAL adapter
exists merely because a demonstration fixture is internally consistent.
"""
from __future__ import annotations

import hashlib
import json
from collections import Counter
from decimal import Decimal
from pathlib import Path
from typing import Any


def read_object(path: Path) -> dict[str, Any]:
    obj = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(obj, dict):
        raise ValueError(f"{path.name}: expected an object")
    return obj


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def safe_file(root: Path, reference: str) -> Path:
    """Allow only a contained relative reference; relocation must be explicit."""
    root = root.resolve()
    if not isinstance(reference, str) or not reference or "\\" in reference:
        raise ValueError("invalid relative reference")
    value = Path(reference)
    target = (root / value).resolve()
    if value.is_absolute() or not target.is_relative_to(root) or not target.is_file():
        raise ValueError(f"missing/outside evidence root: {reference}")
    return target


def scientific_rows(path: Path) -> list[dict]:
    rows = [json.loads(line) for line in path.read_bytes().splitlines() if line.strip()]
    if not rows or any(not isinstance(row, dict) for row in rows):
        raise ValueError(f"{path.name}: expected nonempty object rows")
    return rows


def _row_contract(rows: list[dict]) -> list[str]:
    issues = []
    ids = [row.get("evaluation_id") for row in rows]
    if any(not isinstance(i, str) or not i for i in ids) or len(ids) != len(set(ids)):
        issues.append("EVALUATION_ID_MISSING_OR_DUPLICATED")
    for index, row in enumerate(rows):
        # Scientific ledgers use exceed_count (some schema versions call it K).
        k = row.get("exceed_count", row.get("K"))
        p = row.get("p_value", row.get("p"))
        reject = row.get("reject")
        if type(k) is not int or not 0 <= k <= 999:
            issues.append(f"ROW_{index}:INVALID_K")
            continue
        try:
            pd = Decimal(str(p))
            if type(p) not in (int, float) or not pd.is_finite() or pd != Decimal(k + 1) / 1000:
                issues.append(f"ROW_{index}:INVALID_P_GRID")
        except Exception:  # noqa: BLE001 - 单行不可解析即判该行 p 网格非法，逐行 fail-closed 并记录问题码
            issues.append(f"ROW_{index}:INVALID_P_GRID")
        if type(reject) is not bool or reject != (k <= 49):
            issues.append(f"ROW_{index}:INVALID_REJECT")
    return issues


def check_fixture_payload(root: Path) -> dict[str, Any]:
    """Read the REAL file payload and exact committed set, independently."""
    from .indexes import phase_seal_hash
    codes: list[str] = []
    evidence: dict[str, Any] = {}
    required = ("LIFECYCLE_FIXTURE.json", "evaluation_ledger.jsonl", "evaluation_rows.jsonl",
                "expected_evaluation_index.json", "PHASE_SEAL_TEST_PREDICTION.json",
                "PHASE_SEAL_TEST_ANALYSIS.json", "analysis_input.json", "analysis_output.json",
                "shard_registry.jsonl", "EXECUTION_CHAIN.json")
    missing = [name for name in required if not (root / name).is_file()]
    if missing:
        return {"status": "INCOMPLETE", "codes": ["MISSING:" + n for n in missing], "evidence": {}}
    try:
        expected = json.loads((root / "expected_evaluation_index.json").read_text())
        rows = scientific_rows(root / "evaluation_ledger.jsonl")
        computed = scientific_rows(root / "evaluation_rows.jsonl")
        codes.extend(_row_contract(rows))
        ids = [row["evaluation_id"] for row in rows]
        expected_ids = [row["evaluation_id"] for row in expected]
        if len(expected_ids) != len(set(expected_ids)) or Counter(ids) != Counter(expected_ids):
            codes.append("EXPECTED_ACTUAL_SET_MISMATCH")
        if rows != computed:
            codes.append("COMPUTED_MERGED_PAYLOAD_MISMATCH")
        committed = []
        for path in sorted(root.glob("runs/**/*.final/evaluation.scientific.jsonl")):
            committed.extend(scientific_rows(path))
        encoded = lambda rs: Counter(json.dumps(r, sort_keys=True, allow_nan=False) for r in rs)
        if encoded(rows) != encoded(committed):
            codes.append("COMMITTED_PAYLOAD_MISMATCH")
        ledger_sha = sha(root / "evaluation_ledger.jsonl")
        pred = read_object(root / "PHASE_SEAL_TEST_PREDICTION.json")
        analysis = read_object(root / "PHASE_SEAL_TEST_ANALYSIS.json")
        report = read_object(root / "LIFECYCLE_FIXTURE.json")
        chain = report.get("chain", [])
        if len(chain) != 2 or [phase_seal_hash(x) for x in (pred, analysis)] != [x.get("new_phase_seal_hash") for x in chain]:
            codes.append("PHASE_CHAIN_MISMATCH")
        if analysis.get("parent_phase_seal_hash") != phase_seal_hash(pred):
            codes.append("ANALYSIS_PARENT_MISMATCH")
        if any(s.get("active_ledger_content_hash") != ledger_sha for s in (pred, analysis)):
            codes.append("PHASE_LEDGER_MISMATCH")
        output = read_object(root / "analysis_output.json")
        if output.get("ledger_sha256") != ledger_sha or output.get("rows") != len(rows):
            codes.append("ANALYSIS_OUTPUT_MISMATCH")
        if output.get("descriptive_only") is not True:
            codes.append("TEST_ANALYSIS_MUST_BE_DESCRIPTIVE")
        run_files = list((root / "run").glob("*SEAL*.json"))
        if len(run_files) != 1:
            codes.append("ACTUAL_RUN_SEAL_MISSING_OR_AMBIGUOUS")
        evidence.update(rows=len(rows), expected=len(expected), committed=len(committed), ledger_sha256=ledger_sha)
    except (OSError, ValueError, KeyError, TypeError, IndexError) as exc:
        codes.append(f"INVALID_FIXTURE:{type(exc).__name__}:{exc}")
    return {"status": "PASS" if not codes else "FAIL", "codes": codes, "evidence": evidence}
