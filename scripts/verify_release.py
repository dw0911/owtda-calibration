#!/usr/bin/env python3
"""Release verification (auditor level 1 "quick" and level 2 "analysis").

quick (seconds, no Monte Carlo):
  * H0 canonical: 112 evaluation units over 28 unique cells; rate == rejects / n;
    Wilson/Agresti-Coull 90/95 intervals recomputed; classification vocabulary;
    per-(feature, method) classification counts vs artifacts/tables/Table4_calibration.csv.
  * H1 canonical: 16 cell-feature rows; n == 1600; M == floor((T - W) / s) + 1.
  * P1-P3: p == (tail + 1) / (B + 1); p > 0; Holm step-down recomputed; CI equals the
    registered canonical CI; MANUSCRIPT_VALUES matches the canonical sources.
  * Artifact provenance: every figure/table .meta.json input hash resolves to a file in
    the repository; report the known script_sha256 gaps (never a hard failure).
  * Paper (long manuscript, short submission manuscript, supplement): LaTeX \\input /
    \\includegraphics targets exist; PDFs present; undefined references absent when the
    corresponding .log file is present.
  * reproducibility/SHA256SUMS verified when present.

analysis (adds the level-2 checks):
  * scripts/bootstrap_primary_contrasts.py --check    (P1-P3 regeneration, semantic comparison:
                                                       JSON as parsed objects, npz by key/dtype/
                                                       shape/element equality; cross-platform)
  * scripts/build_tables.py --check                   (Table 1-5 regeneration, semantic comparison
                                                       against paper/scripts/make_tables.py)

Exit code 0 only when every executed check passed.

Usage:
  python scripts/verify_release.py --level quick
  python scripts/verify_release.py --level analysis
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import re
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
CANON = REPO / "results" / "canonical"
BOOT = REPO / "results" / "bootstrap"
TABLES = REPO / "artifacts" / "tables"
FIGURES = REPO / "artifacts" / "figures"
PAPER = REPO / "paper"

Z90, Z95 = 1.6448536269514722, 1.959963984540054
FEATURE_SHORT, METHOD_SHORT = 7, 6


class Result:
    def __init__(self) -> None:
        self.rows: list[tuple[bool, str, str]] = []

    def add(self, ok: bool, name: str, detail: str = "") -> None:
        self.rows.append((bool(ok), name, detail))

    @property
    def failed(self) -> list[tuple[bool, str, str]]:
        return [row for row in self.rows if not row[0]]


def sha256_of(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(8 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def script_sha256(path: Path) -> str:
    """Hash a script with CRLF normalised to LF, so every checkout agrees."""
    return hashlib.sha256(path.read_bytes().replace(b"\r\n", b"\n")).hexdigest()


def load(path: Path):
    return json.loads(path.read_text(encoding="utf-8-sig"))


def decode_rho(value: object) -> float:
    if isinstance(value, str) and value.startswith("f64:"):
        import struct

        return struct.unpack(">d", bytes.fromhex(value[4:]))[0]
    return float(value)  # type: ignore[arg-type]


def wilson_interval(rejects: int, n: int, z: float) -> tuple[float, float]:
    """Wilson score interval (the registered H0 interval definition)."""
    p = rejects / n
    denominator = 1 + z * z / n
    centre = (p + z * z / (2 * n)) / denominator
    half = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / denominator
    return centre - half, centre + half


def check_h0(res: Result, info: Result) -> None:
    rows = load(CANON / "H0_POINTWISE.json")
    n_rows = len(rows)
    cells = {row["logical_cell_id"] for row in rows}
    units = {(row["logical_cell_id"], row["feature_id"], row["method_id"]) for row in rows}
    res.add(n_rows == 112, "H0 evaluation units == 112", f"rows={n_rows}")
    res.add(len(cells) == 28, "H0 unique cells == 28", f"cells={len(cells)}")
    res.add(len(units) == 112, "H0 (cell, feature, method) unique == 112", f"units={len(units)}")

    bad_rate = bad_w90 = bad_w95 = bad_n = bad_class = 0
    vocabulary = {
        "POINTWISE_PRACTICALLY_CALIBRATED",
        "MATERIAL_CONSERVATISM",
        "MATERIAL_ANTI_CONSERVATISM",
        "BOUNDARY_OR_INDETERMINATE",
    }
    counts: dict[tuple[str, str, str], int] = {}
    by_method: dict[str, list[float]] = {"M0": [], "M1": []}
    for row in rows:
        n, rejects = int(row["n"]), int(row["rejects"])
        if n != 2500:
            bad_n += 1
        if abs(float(row["rejection_rate"]) - rejects / n) > 1e-12:
            bad_rate += 1
        lo, hi = wilson_interval(rejects, n, Z90)
        if abs(lo - row["wilson90"][0]) > 1e-9 or abs(hi - row["wilson90"][1]) > 1e-9:
            bad_w90 += 1
        lo, hi = wilson_interval(rejects, n, Z95)
        if abs(lo - row["wilson95"][0]) > 1e-9 or abs(hi - row["wilson95"][1]) > 1e-9:
            bad_w95 += 1
        if row["classification"] not in vocabulary:
            bad_class += 1
        key = (row["feature_id"][:FEATURE_SHORT], row["method_id"][:METHOD_SHORT], row["classification"])
        counts[key] = counts.get(key, 0) + 1
        by_method[row["method_id"][:2]].append(float(row["rejection_rate"]))

    res.add(bad_n == 0, "H0 n == 2500 for every unit", f"violations={bad_n}")
    res.add(bad_rate == 0, "H0 rejection_rate == rejects / n", f"violations={bad_rate}")
    res.add(bad_w90 == 0 and bad_w95 == 0, "H0 Wilson 90/95 intervals recompute", f"violations={bad_w90 + bad_w95}")
    res.add(bad_class == 0, "H0 classification vocabulary", f"violations={bad_class}")

    table4 = TABLES / "Table4_calibration.csv"
    if table4.exists():
        mismatch = 0
        with table4.open(encoding="utf-8-sig", newline="") as handle:
            for row in csv.DictReader(handle):
                for name in vocabulary:
                    key = (row["feature"], row["method"], name)
                    if int(row[name]) != counts.get(key, 0):
                        mismatch += 1
        res.add(mismatch == 0, "H0 classification counts == Table4_calibration.csv", f"mismatches={mismatch}")
    else:
        res.add(False, "Table4_calibration.csv present", str(table4))

    values = load(CANON / "MANUSCRIPT_VALUES.json")
    m0 = [100 * v for v in by_method["M0"]]
    m1 = [100 * v for v in by_method["M1"]]
    info.add(True, "computed H0 ranges over all canonical rows", f"M0={min(m0):.2f}-{max(m0):.2f} M1={min(m1):.2f}-{max(m1):.2f}")
    inside = (
        values["M0_type1_range_pct"][0] >= min(m0) - 1e-9
        and values["M0_type1_range_pct"][1] <= max(m0) + 1e-9
        and values["M1_type1_range_pct"][0] >= min(m1) - 1e-9
        and values["M1_type1_range_pct"][1] <= max(m1) + 1e-9
    )
    res.add(inside, "MANUSCRIPT_VALUES M0/M1 ranges lie inside the canonical range",
            f"paper M0={values['M0_type1_range_pct']} M1={values['M1_type1_range_pct']}")


def check_h1(res: Result) -> None:
    h1 = load(CANON / "H1_REANALYSIS.json")
    cells = h1["percell"]
    keys = {(row["scenario_id"], row["feature_id"], int(row["stride"]), str(row["rho"])) for row in cells}
    res.add(len(cells) == 16, "H1 cell-feature rows == 16", f"rows={len(cells)}")
    res.add(len(keys) == 16, "H1 (scenario, feature, stride, rho) unique == 16", f"keys={len(keys)}")
    bad_geom = 0
    for row in cells:
        w, stride, t = int(row["W"]), int(row["stride"]), int(row["T"])
        if not (w > 0 and stride > 0 and t >= w and (t - w) // stride + 1 >= 1):
            bad_geom += 1
    res.add(bad_geom == 0, "H1 geometry valid (M = floor((T - W)/s) + 1 >= 1)", f"violations={bad_geom}")

    table = TABLES / "H1_ALL_16_GEOMETRY_COMPLETE.csv"
    if table.exists():
        with table.open(encoding="utf-8-sig", newline="") as handle:
            derived = list(csv.DictReader(handle))
        bad_n = bad_m = bad_rank = 0
        for row in derived:
            if int(row["n"]) != 1600:
                bad_n += 1
            if int(row["M"]) != (int(row["T"]) - int(row["W"])) // int(row["stride"]) + 1:
                bad_m += 1
            if "critical_rank" in row and int(row["critical_rank"]) != 2376:
                bad_rank += 1
        res.add(len(derived) == 16, "H1 derived table rows == 16", f"rows={len(derived)}")
        res.add(bad_n == 0, "H1 n == 1600 (derived table)", f"violations={bad_n}")
        res.add(bad_m == 0, "H1 M formula holds (derived table)", f"violations={bad_m}")
        res.add(bad_rank == 0, "H1 empirical critical rank == 2376", f"violations={bad_rank}")
    else:
        res.add(False, "H1_ALL_16_GEOMETRY_COMPLETE.csv present", str(table))


def check_primary(res: Result) -> None:
    summary = load(BOOT / "P1_P3_BOOTSTRAP_SUMMARY.json")
    canonical = load(CANON / "H0_PRIMARY_CONTRASTS.json")["primary"]
    values = load(CANON / "MANUSCRIPT_VALUES.json")
    b = int(summary["bootstrap_iterations"])
    bad_rule = bad_pos = bad_ci = 0
    pvalues = {}
    for key, row in summary["results"].items():
        pvalues[key] = float(row["p_raw_one_sided"])
        if abs(row["p_raw_one_sided"] - (row["tail_count"] + 1) / (b + 1)) > 1e-15:
            bad_rule += 1
        if not row["p_raw_one_sided"] > 0:
            bad_pos += 1
        if any(abs(a - c) > 1e-9 for a, c in zip(row["ci95_basic"], canonical[key]["ci95_basic"])):
            bad_ci += 1
    res.add(bad_rule == 0, "P1-P3 p == (tail + 1) / (B + 1)", f"violations={bad_rule}")
    res.add(bad_pos == 0, "P1-P3 p strictly positive (no illegal p = 0)", f"violations={bad_pos}")
    res.add(bad_ci == 0, "P1-P3 CI == registered canonical CI", f"violations={bad_ci}")

    order = sorted(pvalues, key=lambda k: (pvalues[k], k))
    running, holm = 0.0, {}
    for rank, key in enumerate(order):
        running = max(running, (len(order) - rank) * pvalues[key])
        holm[key] = min(1.0, running)
    res.add(
        all(abs(holm[k] - summary["results"][k]["p_holm"]) < 1e-12 for k in order),
        "P1-P3 Holm values recompute",
        ", ".join(f"{k}={holm[k]:.3g}" for k in order),
    )

    pairs = [
        ("P1", "P1_fixed_M_overlap_diff", "P1_ci95", "P1_threshold"),
        ("P2", "P2_fixed_T_stride_diff", "P2_ci95", "P2_threshold"),
        ("P3", "P3_dmb_conservatism", "P3_ci95", "P3_threshold"),
    ]
    bad_ms = 0
    for key, est_key, ci_key, thr_key in pairs:
        row = summary["results"][key]
        if (
            abs(values[est_key] - row["point_estimate"]) > 1e-12
            or abs(values[thr_key] - row["threshold"]) > 1e-12
            or any(abs(a - c) > 1e-9 for a, c in zip(values[ci_key], row["ci95_basic"]))
        ):
            bad_ms += 1
    res.add(bad_ms == 0, "MANUSCRIPT_VALUES P1-P3 == bootstrap summary", f"mismatches={bad_ms}")


def check_artifact_provenance(res: Result, info: Result) -> None:
    candidates: dict[str, Path] = {}
    for path in list(TABLES.glob("*")) + list(CANON.glob("*")) + list(BOOT.glob("*")):
        if path.is_file():
            candidates.setdefault(path.name, path)
            candidates.setdefault(path.stem, path)
    repo_scripts = {script_sha256(p) for p in (REPO / "scripts").glob("*.py")} | {
        script_sha256(p) for p in (PAPER / "scripts").glob("*.py")
    }
    checked = missing = mismatch = 0
    script_gaps = []
    for meta_path in sorted(list(TABLES.glob("*.meta.json")) + list(FIGURES.glob("*.meta.json"))):
        meta = load(meta_path)
        for name, digest in (meta.get("input_sha256") or {}).items():
            checked += 1
            target = candidates.get(name) or candidates.get(Path(name).name)
            if target is None:
                missing += 1
                info.add(True, f"unresolved input name (informational): {name}", meta_path.name)
                continue
            if sha256_of(target) != digest:
                mismatch += 1
        script = meta.get("script_sha256")
        if script and script not in repo_scripts:
            script_gaps.append(meta_path.name)
    res.add(checked > 0, "artifact meta inputs discovered", f"inputs={checked}")
    res.add(missing == 0, "every meta input resolves inside the repository", f"unresolved={missing}")
    res.add(mismatch == 0, "every meta input hash matches its file", f"mismatches={mismatch}")
    if script_gaps:
        info.add(True, "script_sha256 gaps (known: original generator not preserved)", ", ".join(sorted(set(script_gaps))))


def check_paper(res: Result) -> None:
    main = PAPER / "main.tex"
    if not main.exists():
        res.add(False, "paper/main.tex present", str(main))
        return
    documents = [
        (main, [main] + sorted((PAPER / "sections").glob("*.tex")),
         PAPER / "main.pdf", PAPER / "main.log"),
    ]
    short = PAPER / "main_short.tex"
    if short.exists():
        documents.append(
            (short, [short] + sorted((PAPER / "short_sections").glob("*.tex")),
             PAPER / "main_short.pdf", PAPER / "main_short.log")
        )
    supplement = PAPER / "supplement" / "supplement.tex"
    if supplement.exists():
        documents.append(
            (supplement, [supplement],
             PAPER / "supplement" / "supplement.pdf",
             PAPER / "supplement" / "supplement.log")
        )

    pattern_input = re.compile(r"\\input\{([^}]+)\}")
    pattern_graphic = re.compile(r"\\includegraphics(?:\[[^\]]*\])?\{([^}]+)\}")
    missing: list[str] = []
    checked = 0
    for _, tex_files, _, _ in documents:
        for tex in tex_files:
            text = tex.read_text(encoding="utf-8-sig")
            base = tex.parent
            for pattern in (pattern_input, pattern_graphic):
                for raw in pattern.findall(text):
                    checked += 1
                    candidates = (
                        base / raw,
                        base / f"{raw}.tex",
                        PAPER / raw,
                        PAPER / f"{raw}.tex",
                    )
                    if not any(candidate.exists() for candidate in candidates):
                        missing.append(f"{tex.name} -> {raw}")
    res.add(
        not missing,
        "LaTeX inputs/figure paths resolve",
        "; ".join(missing[:5]) or f"files={checked}",
    )

    for _, _, pdf, _ in documents:
        res.add(pdf.exists(), f"{pdf.relative_to(REPO).as_posix()} present")

    for _, _, _, log_path in documents:
        if not log_path.exists():
            continue
        log_text = log_path.read_text(encoding="utf-8", errors="replace")
        undefined = len(
            re.findall(r"LaTeX Warning: (?:Reference|Citation) .* undefined", log_text)
        )
        res.add(
            undefined == 0,
            f"no undefined LaTeX references ({log_path.name})",
            f"count={undefined}",
        )


def check_sums(res: Result) -> None:
    sums = REPO / "reproducibility" / "SHA256SUMS"
    if not sums.exists():
        res.add(False, "reproducibility/SHA256SUMS present", str(sums))
        return
    bad = total = 0
    for line in sums.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        digest, _, rel = line.partition("  ")
        total += 1
        target = REPO / rel.strip()
        if not target.exists() or sha256_of(target) != digest:
            bad += 1
    res.add(bad == 0, "SHA256SUMS entries verify", f"checked={total} mismatches={bad}")


def check_level2(res: Result) -> None:
    for label, argv in (
        ("P1-P3 regeneration", [sys.executable, "scripts/bootstrap_primary_contrasts.py", "--check"]),
        ("manuscript tables regeneration", [sys.executable, "scripts/build_tables.py", "--check"]),
        ("canonical H0 self-consistency", [sys.executable, "scripts/analyse_h0.py", "--check"]),
    ):
        proc = subprocess.run(argv, cwd=REPO, capture_output=True, text=True, check=False)
        lines = (proc.stdout or proc.stderr).strip().splitlines()
        res.add(proc.returncode == 0, f"level 2: {label}", lines[-1] if lines else "")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--level", choices=("quick", "analysis"), default="quick")
    args = parser.parse_args(argv)

    res, info = Result(), Result()
    check_h0(res, info)
    check_h1(res)
    check_primary(res)
    check_artifact_provenance(res, info)
    check_paper(res)
    check_sums(res)
    if args.level == "analysis":
        check_level2(res)

    for ok, name, detail in res.rows:
        print(f"[{'PASS' if ok else 'FAIL'}] {name}" + (f"  ({detail})" if detail else ""))
    for _, name, detail in info.rows:
        print(f"[INFO] {name}" + (f"  ({detail})" if detail else ""))

    failures = len(res.failed)
    print(f"\n{args.level}: {len(res.rows) - failures}/{len(res.rows)} checks passed")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
