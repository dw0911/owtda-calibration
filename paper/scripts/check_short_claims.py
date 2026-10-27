"""Assert every numerical claim of the short paper against the canonical summaries.

Inputs (never edited here):
  artifacts/tables/H0_ALL_112.csv
  artifacts/tables/P1_P3_BOOTSTRAP.json
  artifacts/tables/H1_SCENARIO_SAME_FOUR_CONDITIONS.csv
  artifacts/tables/H1_SCENARIO_DIFFERENCES.csv

Exit code is non-zero if any claim drifts from the canonical values.
"""
from __future__ import annotations

import csv
import json
import struct
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
TAB = ROOT / "artifacts" / "tables"
TOL = 5e-5

failures: list[str] = []


def check(label: str, got, want, tol: float = TOL) -> None:
    if isinstance(want, tuple):
        ok = len(got) == len(want) and all(abs(float(a) - float(b)) <= tol for a, b in zip(got, want))
    elif isinstance(want, str):
        ok = got == want
    else:
        ok = abs(float(got) - float(want)) <= tol
    print(f"{'PASS' if ok else 'FAIL'}  {label}: got={got!r} want={want!r}")
    if not ok:
        failures.append(label)


def f64(text: str) -> float:
    return struct.unpack(">d", bytes.fromhex(text[4:]))[0]


def h0_rows() -> list[dict]:
    with (TAB / "H0_ALL_112.csv").open(encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))
    out = []
    for raw in rows:
        r = {k.lstrip("\ufeff"): v for k, v in raw.items()}
        rho = f64(r["rho"]) if r["rho"].startswith("f64:") else float(r["rho"])
        out.append(
            {
                "dgp": r["DGP_family"],
                "rho": round(rho, 2),
                "s": int(float(r["stride"])),
                "T": int(float(r["T"])),
                "M": int(float(r["M_expected"])),
                "feature": "BPI" if "BPI" in r["feature_id"] else "MOMENTS",
                "method": "M0" if "M0" in r["method_id"] else "M1",
                "rate": float(r["rejection_rate"]),
                "cls": r["classification"],
            }
        )
    return out


def span(rows: list[dict], **kw) -> tuple[float, float]:
    vals = [r["rate"] for r in rows if all(r[k] == v for k, v in kw.items())]
    assert vals, f"empty selection {kw}"
    return min(vals), max(vals)


def main() -> int:
    rows = h0_rows()
    print(f"cells: {len(rows)}")

    # --- Section 5.1 ranges (budget-explicit) --------------------------------
    for s, want in ((8, (0.8816, 0.9712)), (16, (0.4384, 0.7356)),
                    (32, (0.1088, 0.3044)), (64, (0.0504, 0.0528))):
        got = span(rows, feature="BPI", method="M0", M=192, s=s)
        check(f"BPI/M0 fixed-M s={s}", got, want)
    check("BPI/M0 fixed-T s=64", span(rows, feature="BPI", method="M0", T=3120, s=64), (0.0472, 0.0608))
    check("BPI/M1 merged s=8", span(rows, feature="BPI", method="M1", s=8), (0.0436, 0.1180))
    check("BPI/M1 merged s=64", span(rows, feature="BPI", method="M1", s=64), (0.0056, 0.0276))
    check("MOMENTS/M0 global", span(rows, feature="MOMENTS", method="M0"), (0.0432, 0.9996))
    check("MOMENTS/M1 global", span(rows, feature="MOMENTS", method="M1"), (0.0020, 0.1412))

    # --- Table 1 classification counts --------------------------------------
    # column order of Table 1: calibrated / conservative / anti-conservative / undetermined
    order = [("POINTWISE_PRACTICALLY_CALIBRATED", "cal"), ("MATERIAL_CONSERVATISM", "cons"),
             ("MATERIAL_ANTI_CONSERVATISM", "anti"), ("BOUNDARY_OR_INDETERMINATE", "und")]
    for feature, method, want in (
        ("BPI", "M0", (7, 0, 20, 1)),
        ("BPI", "M1", (5, 10, 7, 6)),
        ("MOMENTS", "M0", (6, 0, 20, 2)),
        ("MOMENTS", "M1", (1, 12, 7, 8)),
    ):
        counts = tuple(sum(1 for r in rows if r["feature"] == feature and r["method"] == method
                           and r["cls"] == key) for key, _ in order)
        check(f"Table 1 counts {feature}/{method}", counts, want)

    # --- Overlap / non-overlap statements -----------------------------------
    for feature in ("BPI", "MOMENTS"):
        anti = sum(1 for r in rows if r["feature"] == feature and r["method"] == "M0"
                   and r["s"] < 64 and r["cls"] == "MATERIAL_ANTI_CONSERVATISM")
        check(f"{feature} M0 anti among 20 overlap configs", anti, 20)
        cons = sum(1 for r in rows if r["feature"] == feature and r["method"] == "M1"
                   and r["s"] == 64 and r["cls"] == "MATERIAL_CONSERVATISM")
        check(f"{feature} M1 conservative among 8 non-overlap configs", cons, 8)

    key = lambda r: (r["dgp"], r["rho"], r["s"], r["T"], r["M"], r["feature"])
    m0 = {key(r): r for r in rows if r["method"] == "M0"}
    m1 = {key(r): r for r in rows if r["method"] == "M1"}
    check("matched cells", len(m0), 56)
    check("M1 below M0 in all matched cells", sum(1 for k in m0 if m1[k]["rate"] < m0[k]["rate"]), 56)

    # --- P1-P3 --------------------------------------------------------------
    boot = json.loads((TAB / "P1_P3_BOOTSTRAP.json").read_text(encoding="utf-8"))["results"]
    for name, point, lo, hi in (("P1", 0.5354, 0.5210, 0.5494),
                                ("P2", 0.5330, 0.5194, 0.5462),
                                ("P3", 0.0266, 0.0224, 0.0308)):
        check(f"{name} point", boot[name]["point_estimate"], point)
        check(f"{name} CI low", boot[name]["ci95_basic"][0], lo)
        check(f"{name} CI high", boot[name]["ci95_basic"][1], hi)
        check(f"{name} Holm p", round(boot[name]["p_holm"], 5), 0.00030)

    # --- H1 ---------------------------------------------------------------
    with (TAB / "H1_SCENARIO_SAME_FOUR_CONDITIONS.csv").open(encoding="utf-8") as handle:
        h1 = [{k.lstrip("\ufeff"): v for k, v in r.items()} for r in csv.DictReader(handle)]
    power = {(r["scenario"], r["feature"]): float(r["size_standardized_power"]) for r in h1}
    check("power shape/BPI", power[("shape_change", "BPI")], 1.00000)
    check("power shape/MOMENTS", power[("shape_change", "MOMENTS")], 0.06203)
    check("power shift/BPI", power[("mean_shift", "BPI")], 0.05375)
    check("power shift/MOMENTS", power[("mean_shift", "MOMENTS")], 1.00000)
    nmae = [float(r["mean_normalized_mae"]) for r in h1]
    joint = [float(r[f"{m}_joint_success"]) for r in h1 for m in ("M0", "M1")]
    check("scenario nMAE range", (round(min(nmae), 5), round(max(nmae), 5)), (0.00330, 0.20255))
    check("joint success range", (round(min(joint), 4), round(max(joint), 4)), (0.0009, 0.9839))

    with (TAB / "H1_SCENARIO_DIFFERENCES.csv").open(encoding="utf-8") as handle:
        diff = [{k.lstrip("\ufeff"): v for k, v in r.items()} for r in csv.DictReader(handle)]
    d = {r["scenario"]: r for r in diff}
    check("shape diff", float(d["shape_change"]["difference"]), 0.93797)
    check("shape CI low", float(d["shape_change"]["lower95"]), 0.92969)
    check("shape CI high", float(d["shape_change"]["upper95"]), 0.94609)
    check("shift diff", float(d["mean_shift"]["difference"]), -0.94625)
    check("shift CI low", float(d["mean_shift"]["lower95"]), -0.95344)
    check("shift CI high", float(d["mean_shift"]["upper95"]), -0.93844)

    print()
    if failures:
        print(f"{len(failures)} claim(s) drifted: {failures}")
        return 1
    print("all short-paper numerical claims match the canonical summaries")
    return 0


if __name__ == "__main__":
    sys.exit(main())
