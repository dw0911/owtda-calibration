#!/usr/bin/env python3
"""H0 layer of the analysis chain.

Two modes:

* ``--check`` (default, no ledger needed, CI-friendly): verify that the committed canonical
  H0 dataset is self-consistent - 112 evaluation units over 28 unique cells, ``n = 2500``,
  ``rejection_rate = rejects / n``, Agresti-Coull 90/95 intervals recomputed, classification
  vocabulary, and the per-(feature, method) counts equal ``Table4_calibration.csv``.
* ``--from-ledger`` (level 2): stream a sealed ``evaluation.scientific.jsonl``, aggregate
  ``n``/``rejects`` per ``(logical_cell_id, feature_id, method_id)``, verify the registered
  rules ``p = (exceed_count + 1) / (B + 1)`` and ``reject == (exceed_count <= 49)`` for B = 999,
  and compare the aggregate with the committed canonical rows.
"""

from __future__ import annotations

import argparse
import csv
import json
import math
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
CANON = REPO / "results" / "canonical"
TABLES = REPO / "artifacts" / "tables"
Z90, Z95 = 1.6448536269514722, 1.959963984540054
VOCABULARY = (
    "POINTWISE_PRACTICALLY_CALIBRATED",
    "MATERIAL_CONSERVATISM",
    "MATERIAL_ANTI_CONSERVATISM",
    "BOUNDARY_OR_INDETERMINATE",
)


def wilson_interval(rejects: int, n: int, z: float) -> tuple[float, float]:
    """Wilson score interval (the registered H0 interval definition)."""
    p = rejects / n
    denominator = 1 + z * z / n
    centre = (p + z * z / (2 * n)) / denominator
    half = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / denominator
    return centre - half, centre + half


def load_rows() -> list[dict]:
    return json.loads((CANON / "H0_POINTWISE.json").read_text(encoding="utf-8-sig"))


def check_canonical() -> int:
    rows = load_rows()
    problems: list[str] = []
    if len(rows) != 112:
        problems.append(f"rows={len(rows)} != 112")
    if len({row["logical_cell_id"] for row in rows}) != 28:
        problems.append("unique cells != 28")
    counts: dict[tuple[str, str, str], int] = {}
    for row in rows:
        n, rejects = int(row["n"]), int(row["rejects"])
        if n != 2500:
            problems.append(f"{row['logical_cell_id'][:8]}: n={n}")
        if abs(float(row["rejection_rate"]) - rejects / n) > 1e-12:
            problems.append(f"{row['logical_cell_id'][:8]}: rate")
        for z, field in ((Z90, "wilson90"), (Z95, "wilson95")):
            lo, hi = wilson_interval(rejects, n, z)
            if abs(lo - row[field][0]) > 1e-9 or abs(hi - row[field][1]) > 1e-9:
                problems.append(f"{row['logical_cell_id'][:8]}: {field}")
        if row["classification"] not in VOCABULARY:
            problems.append(f"{row['logical_cell_id'][:8]}: classification")
        key = (row["feature_id"][:7], row["method_id"][:6], row["classification"])
        counts[key] = counts.get(key, 0) + 1

    table4 = TABLES / "Table4_calibration.csv"
    if table4.exists():
        with table4.open(encoding="utf-8-sig", newline="") as handle:
            for row in csv.DictReader(handle):
                for name in VOCABULARY:
                    if int(row[name]) != counts.get((row["feature"], row["method"], name), 0):
                        problems.append(f"Table4 {row['feature']}/{row['method']}/{name}")
    else:
        problems.append("Table4_calibration.csv missing")

    if problems:
        print(f"H0 canonical: FAIL ({len(problems)} problems)")
        for item in problems[:12]:
            print(f"  - {item}")
        return 1
    print("H0 canonical: OK (112 units / 28 cells / rates / intervals / counts)")
    return 0


def from_ledger(ledger: Path, limit: int | None, tolerance: float) -> int:
    aggregate: dict[tuple[str, str, str], dict[str, int]] = {}
    rule_p = rule_reject = rows_seen = 0
    with ledger.open(encoding="utf-8") as handle:
        for line in handle:
            if limit is not None and rows_seen >= limit:
                break
            row = json.loads(line)
            rows_seen += 1
            key = (row["logical_cell_id"], row["feature_id"], row["method_id"])
            bucket = aggregate.setdefault(key, {"n": 0, "rejects": 0})
            bucket["n"] += 1
            bucket["rejects"] += int(bool(row["reject"]))
            b = int(row["B"])
            exceed = int(row["exceed_count"])
            if abs(float(row["p_value"]) - (exceed + 1) / (b + 1)) > 1e-15:
                rule_p += 1
            if bool(row["reject"]) != (exceed <= math.floor(0.05 * (b + 1)) - 1):
                rule_reject += 1

    canonical = {(row["logical_cell_id"], row["feature_id"], row["method_id"]): row for row in load_rows()}
    missing = mismatch = 0
    for key, bucket in aggregate.items():
        row = canonical.get(key)
        if row is None:
            missing += 1
            continue
        if abs(bucket["n"] - int(row["n"])) > tolerance or abs(bucket["rejects"] - int(row["rejects"])) > tolerance:
            mismatch += 1
    print(
        f"ledger rows={rows_seen} groups={len(aggregate)} rule_p_violations={rule_p} "
        f"rule_reject_violations={rule_reject} groups_missing_in_canonical={missing} "
        f"groups_with_mismatch={mismatch}"
    )
    return 1 if (rule_p or rule_reject or missing or mismatch) else 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true", help="verify the committed canonical dataset")
    parser.add_argument("--from-ledger", type=Path, default=None, help="sealed evaluation.scientific.jsonl")
    parser.add_argument("--limit", type=int, default=None, help="only read the first N ledger rows")
    parser.add_argument("--tolerance", type=float, default=1e-12)
    args = parser.parse_args(argv)

    if args.from_ledger:
        return from_ledger(args.from_ledger, args.limit, args.tolerance)
    return check_canonical()


if __name__ == "__main__":
    sys.exit(main())
