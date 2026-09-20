#!/usr/bin/env python3
r"""Generate the manuscript tables (Table 1-5) from the canonical summaries.

This is the single generator behind the tables that appear in the manuscript. The sections
``\input`` the generated ``.tex`` floats, so no table body is hand-copied into the paper and a
missing/stale table fails the build instead of silently rendering an outdated number.

Sources of truth (never hand-copied, never the raw ledgers)
  * ``results/canonical/H0_POINTWISE.json``            112 evaluation units (28 cells x 2 features x 2 methods)
  * ``results/canonical/H0_PRIMARY_CONTRASTS.json``    P1-P3 point estimates, thresholds, registered CI
  * ``results/bootstrap/P1_P3_BOOTSTRAP_SUMMARY.json`` tail counts, p = (tail+1)/(B+1), Holm
  * ``results/canonical/H1_REANALYSIS.json``           16 per-condition rows (power / MAE / joint success)
  * ``results/canonical/H1_SCENARIO_DIFFERENCES.json`` scenario-level BPI-minus-MOMENTS differences
  * ``results/canonical/bootstrap_context.json``       analysis id

Outputs (``artifacts/tables/``), four files per table
  * ``TableN_*.tex``           the LaTeX float that the manuscript inputs
  * ``TableN_*.csv``           the same rows, machine readable
  * ``TableN_*.json``          the same rows, with the schema/rows envelope used elsewhere
  * ``TableN_*.json.meta.json`` analysis id, script hash, input hashes, output hashes

Table map (artifact name -> manuscript placement)
  Table1_design               -> ``paper/sections/04_protocol.tex``   (tab:design)
  Table2_h0_representative    -> artifact only (representative cells; the manuscript reports the
                                 full 112-row distribution in the supplement, not a sample table)
  Table3_primary_contrasts    -> ``paper/sections/05_h0.tex``         (tab:primary)
  Table4_calibration          -> ``paper/sections/05_h0.tex``         (tab:calibration)
  Table5_h1_power             -> ``paper/sections/06_h1.tex``         (tab:h1-power)

Usage
  python paper/scripts/make_tables.py            # (re)generate in place
  python paper/scripts/make_tables.py --check    # regenerate to a temp dir and compare; nonzero on
                                                 # missing / mismatched / unexpected table artifact
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import struct
import sys
import tempfile
from collections import defaultdict
from datetime import UTC, datetime
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
CANON = REPO / "results" / "canonical"
BOOTSTRAP = REPO / "results" / "bootstrap"
OUT = REPO / "artifacts" / "tables"
SCRIPT_REL = "paper/scripts/make_tables.py"

W = 64  # frozen window width; the geometry table derives T/M/b from it

# Frozen classification vocabulary, in the order used by the manuscript and by Table4_calibration.csv.
VOCABULARY = (
    "POINTWISE_PRACTICALLY_CALIBRATED",
    "MATERIAL_CONSERVATISM",
    "MATERIAL_ANTI_CONSERVATISM",
    "BOUNDARY_OR_INDETERMINATE",
)
VOCABULARY_HEAD = ("实用校准", "实质保守", "实质反保守", "边界/未定")

SCENARIO_LABEL = {"shape_change": "形状变化", "mean_shift": "均值平移"}
# Row order as it appears in the manuscript (not alphabetical by scenario id).
SCENARIO_ORDER = ("shape_change", "mean_shift")

# Registered estimand wording for the three primary contrasts. This is *text* that describes the
# frozen estimand; the numbers next to it are always read from the canonical sources below.
PRIMARY_DIRECTION = {
    "P1": r"$s{=}16$ 减 $s{=}64$ 的 M0 拒绝率差",
    "P2": r"$s{=}16$ 减 $s{=}64$ 的 M0 拒绝率差",
    "P3": r"$0.05$ 减 M1 拒绝率",
}

# Table artifacts that are intentionally not produced by this generator (kept for the audit trail).
LEGACY_ALLOWLIST = {"Table_H1_COMMON_ESTIMAND.tex", "TABLE_DATA.json"}


def sha256_of(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def decode_rho(value) -> float:
    if isinstance(value, str) and value.startswith("f64:"):
        return struct.unpack(">d", bytes.fromhex(value[4:]))[0]
    return float(value)


def feature_label(feature_id: str) -> str:
    """BPI_FIXED20_... -> BPI_FIX ; MOMENTS_MEAN_COV_... -> MOMENTS  (same rule as analyse_h0.py)."""
    return feature_id[:7]


def method_label(method_id: str) -> str:
    return method_id[:6]


def display_feature(label: str) -> str:
    """BPI_FIX -> BPI (manuscript display form; the csv keeps the canonical label)."""
    return label.split("_")[0]


def display_method(label: str) -> str:
    return label.split("_")[0]


def write_text(path: Path, text: str) -> None:
    path.write_text(text, encoding="utf-8", newline="\n")


def write_csv(path: Path, fieldnames: list[str], rows: list[dict]) -> None:
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames, lineterminator="\n")
        writer.writeheader()
        for row in rows:
            writer.writerow(row)


def write_json(path: Path, payload: dict) -> None:
    write_text(path, json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=False) + "\n")


# --------------------------------------------------------------------------------------------
# Table 1: window geometry under the two budget regimes
# --------------------------------------------------------------------------------------------
def build_design(h0_rows: list[dict]) -> dict:
    geometry: dict[int, dict[str, tuple[int, int]]] = defaultdict(dict)
    for row in h0_rows:
        stride, T, M = int(row["stride"]), int(row["T"]), int(row["M_expected"])
        if M == 192:  # fixed-M regime pins M, T follows from the geometry
            geometry[stride].setdefault("fixed_M", (T, M))
        if T == 3120:  # fixed-T regime pins T, M follows
            geometry[stride].setdefault("fixed_T", (T, M))

    rows = []
    for stride in sorted(geometry):
        fixed_m_T, fixed_m_M = geometry[stride]["fixed_M"]
        fixed_t_T, fixed_t_M = geometry[stride]["fixed_T"]
        rows.append({
            "stride": stride,
            "overlap_pct": round(100 * (1 - stride / W), 1),
            "fixed_M": {
                "T": fixed_m_T, "M": fixed_m_M,
                "b": max(W // stride + 1, math.ceil(fixed_m_M ** (1 / 3))),
            },
            "fixed_T": {
                "T": fixed_t_T, "M": fixed_t_M,
                "b": max(W // stride + 1, math.ceil(fixed_t_M ** (1 / 3))),
            },
        })

    def overlap_text(value: float) -> str:
        return "0" if value == 0 else f"{value:.1f}"

    body = "\n".join(
        "{} & {}\\% & {} & {} & {} & {} & {} & {} \\\\".format(
            r["stride"], overlap_text(r["overlap_pct"]), r["fixed_M"]["T"], r["fixed_M"]["M"], r["fixed_M"]["b"],
            r["fixed_T"]["T"], r["fixed_T"]["M"], r["fixed_T"]["b"],
        )
        for r in rows
    )
    tex = rf"""\begin{{table}}[ht]
\centering
\caption{{双预算制度下的窗口几何设计。重叠率为 $1-s/W$；$b$ 为 M1 依赖乘子带宽，按 $b=\max\{{\lfloor W/s\rfloor+1,\lceil M^{{1/3}}\rceil\}}$ 确定。}}\label{{tab:design}}
\begin{{tabular}}{{cccccccc}}
\toprule
$s$ & 重叠率 & \multicolumn{{3}}{{c}}{{固定窗口数（fixed-$M$）}} & \multicolumn{{3}}{{c}}{{固定观测长度（fixed-$T$）}}\\
\cmidrule(lr){{3-5}}\cmidrule(lr){{6-8}}
 & $1-s/W$ & $T$ & $M$ & $b$ & $T$ & $M$ & $b$\\
\midrule
{body}
\bottomrule
\end{{tabular}}

\begin{{minipage}}{{0.94\textwidth}}
\vspace{{0.4em}}
\footnotesize 注：$s=16$ 行在两种制度下给出相同的 $(T,M)=(3120,192)$，为共享配置；唯一配置计数中只计一次，但在两种预算视角下分别用于解释，因此该行会被两张热图有意重复展示。$s=64$ 时 $s=W$，窗口不重叠，重叠率为 0，对应 M1 保守性主对比 P3 的非重叠端。
\end{{minipage}}
\end{{table}}
"""
    return {
        "name": "Table1_design",
        "title": "Window geometry under the two budget regimes",
        "tex": tex,
        "csv_fields": ["stride", "overlap_pct", "fixed_M_T", "fixed_M_M", "fixed_M_b", "fixed_T_T", "fixed_T_M", "fixed_T_b"],
        "csv_rows": [{
            "stride": r["stride"], "overlap_pct": r["overlap_pct"],
            "fixed_M_T": r["fixed_M"]["T"], "fixed_M_M": r["fixed_M"]["M"], "fixed_M_b": r["fixed_M"]["b"],
            "fixed_T_T": r["fixed_T"]["T"], "fixed_T_M": r["fixed_T"]["M"], "fixed_T_b": r["fixed_T"]["b"],
        } for r in rows],
        "json_rows": rows,
        "inputs": ["H0_POINTWISE"],
    }


# --------------------------------------------------------------------------------------------
# Table 2: representative H0 cells (stride 16 and 64 at rho = 0)
# --------------------------------------------------------------------------------------------
def build_h0_representative(h0_rows: list[dict]) -> dict:
    rows = []
    for row in h0_rows:
        stride, T, M, rho = int(row["stride"]), int(row["T"]), int(row["M_expected"]), decode_rho(row["rho"])
        if abs(rho) > 1e-12:
            continue
        representative = (M == 192 and stride in (16, 64)) or (T == 3120 and stride == 64)
        if not representative:
            continue
        rows.append({
            "DGP": row["DGP_family"],
            "feature": feature_label(row["feature_id"]),
            "method": method_label(row["method_id"]),
            "stride": stride,
            "T": T,
            "M": M,
            "rejection_rate": float(row["rejection_rate"]),
            "classification": row["classification"],
        })
    rows.sort(key=lambda r: (r["DGP"], r["feature"], r["method"], r["T"], r["stride"]))

    tex_lines = [
        r"\begin{table}[ht]", r"\centering",
        r"\caption{代表性零假设单元的拒绝率（$\rho=0$；完整 112 行见补充材料）。}\label{tab:h0-representative}",
        r"\begin{tabular}{lllccrr}", r"\toprule",
        r"DGP & 表示 & 方法 & $s$ & $T$ & $M$ & 拒绝率\\", r"\midrule",
    ]
    for r in rows:
        tex_lines.append(
            f"{r['DGP'].replace('_', r'\_')} & {display_feature(r['feature'])} & "
            f"{display_method(r['method'])} & {r['stride']} & {r['T']} & {r['M']} & "
            f"{r['rejection_rate']:.4f}\\\\"
        )
    tex_lines += [r"\bottomrule", r"\end{tabular}", r"\end{table}", ""]
    return {
        "name": "Table2_h0_representative",
        "title": "Representative H0 calibration (full 112 rows in H0_POINTWISE.json)",
        "tex": "\n".join(tex_lines),
        "csv_fields": ["DGP", "feature", "method", "stride", "T", "M", "rejection_rate", "classification"],
        "csv_rows": rows,
        "json_rows": rows,
        "inputs": ["H0_POINTWISE"],
    }


# --------------------------------------------------------------------------------------------
# Table 3: primary contrasts P1-P3
# --------------------------------------------------------------------------------------------
def build_primary(contrasts: dict, bootstrap: dict) -> dict:
    rows = []
    for key in ("P1", "P2", "P3"):
        registered = contrasts["primary"][key]
        corrected = bootstrap["results"][key]
        estimate = float(corrected["point_estimate"])
        threshold = float(corrected["threshold"])
        lo, hi = (float(x) for x in corrected["ci95_basic"])
        rows.append({
            "contrast": key,
            "point_estimate": estimate,
            "threshold": threshold,
            "excess": round(estimate - threshold, 10),
            "ci95_basic": [lo, hi],
            "bootstrap_iterations": int(bootstrap["bootstrap_iterations"]),
            "tail_count": int(corrected["tail_count"]),
            "p_raw_one_sided": float(corrected["p_raw_one_sided"]),
            "p_holm": float(corrected["p_holm"]),
            "claim_state": registered["claim_state"],
            # superseded legacy bytes kept for the audit trail (p = 0 is illegal under the
            # registered (tail+1)/(B+1) rule; see reproducibility/VALIDATION_SUMMARY.md)
            "canonical_p_boot_one_sided": float(registered["p_boot_one_sided"]),
            "canonical_p_holm": float(registered["p_holm"]),
        })

    tex_lines = [
        r"\begin{table}[ht]", r"\centering",
        r"\caption{主对比 P1--P3 的效应量与推断结果。置信区间为边际 95\% basic 自助区间；"
        r"Holm 校正 $p$ 由 10,000 次配对 cluster bootstrap 的尾部计数按加一规则计算"
        r"（$p=(1+\#\{\text{尾部}\})/10001$）。}\label{tab:primary}",
        r"\begin{tabular}{llccccc}", r"\toprule",
        r"对比 & 估计量方向 & 点估计 & 预设阈值 & 超额效应 & 95\% basic CI & Holm $p$\\", r"\midrule",
    ]
    for r in rows:
        lo, hi = r["ci95_basic"]
        tex_lines.append(
            f"{r['contrast']} & {PRIMARY_DIRECTION[r['contrast']]} & {r['point_estimate']:.4f} & "
            f"{r['threshold']:.2f} & {r['excess']:.4f} & $[{lo:.4f},{hi:.4f}]$ & {r['p_holm']:.5f}\\\\"
        )
    tex_lines += [
        r"\bottomrule", r"\end{tabular}", "",
        r"\begin{minipage}{0.94\textwidth}", r"\vspace{0.4em}",
        r"\footnotesize 注：三项尾部计数经真实 bootstrap 抽样核验均为 0，故原始 "
        r"$p=1/10001\approx9.999\times10^{-5}$；经 Holm 逐步校正后三项调整 $p$ 均为 "
        r"$3/10001\approx0.00030$。点估计与阈值之差为超额效应；正文按预设单侧阈值与多重性规则"
        r"给出支持与否的表述，表中仅列统计量。",
        r"\end{minipage}", r"\end{table}", "",
    ]
    return {
        "name": "Table3_primary_contrasts",
        "title": "Primary contrasts P1-P3",
        "tex": "\n".join(tex_lines),
        "csv_fields": ["contrast", "point_estimate", "threshold", "excess", "ci95_basic",
                       "bootstrap_iterations", "tail_count", "p_raw_one_sided", "p_holm", "claim_state",
                       "canonical_p_boot_one_sided", "canonical_p_holm"],
        "csv_rows": [{**r, "ci95_basic": json.dumps(r["ci95_basic"])} for r in rows],
        "json_rows": rows,
        "inputs": ["H0_PRIMARY_CONTRASTS", "P1_P3_BOOTSTRAP_SUMMARY"],
    }


# --------------------------------------------------------------------------------------------
# Table 4: calibration classification counts (per feature x method, n = 28)
# --------------------------------------------------------------------------------------------
def build_calibration(h0_rows: list[dict]) -> dict:
    counts: dict[tuple[str, str], dict[str, int]] = defaultdict(lambda: {name: 0 for name in VOCABULARY})
    for row in h0_rows:
        counts[(feature_label(row["feature_id"]), method_label(row["method_id"]))][row["classification"]] += 1

    order = [("BPI_FIX", "M0_NAI"), ("BPI_FIX", "M1_DMB"), ("MOMENTS", "M0_NAI"), ("MOMENTS", "M1_DMB")]
    rows = [{"feature": f, "method": m, **counts[(f, m)]} for f, m in order]

    tex_lines = [
        r"\begin{table}[ht]", r"\centering",
        r"\caption{逐格校准分类计数（每行 $n=28$）。完整 112 行拒绝率、Wilson 区间与分类结果见补充材料。}"
        r"\label{tab:calibration}",
        r"\begin{tabular}{llcccc}", r"\toprule",
        "表示 & 方法 & " + " & ".join(f"{head} $n\\,(\\%)$" for head in VOCABULARY_HEAD) + r"\\",
        r"\midrule",
    ]
    for row in rows:
        cells = " & ".join(f"{row[name]} ({100 * row[name] / 28:.1f})" for name in VOCABULARY)
        tex_lines.append(f"{display_feature(row['feature'])} & {display_method(row['method'])} & {cells}\\\\")
    tex_lines += [
        r"\bottomrule", r"\end{tabular}", "",
        r"\begin{minipage}{0.94\textwidth}", r"\vspace{0.4em}",
        r"\footnotesize 注：实用校准采用 90\% Wilson 区间完整落在等效带 $[0.035,0.065]$ 内，"
        r"对应预设的实用等效性判据（两个单侧 5\% 判定等价于一个 90\% 双侧区间）；实质保守要求 "
        r"95\% 区间完整位于实用带下方，实质反保守要求 95\% 区间完整位于实用带上方；"
        r"边界/未定为既不满足实用校准、也不满足实质保守或实质反保守的剩余状态。"
        r"上述计数为预设设计网格内的描述性分布，不构成方法在更广参数空间中的通过率。",
        r"\end{minipage}", r"\end{table}", "",
    ]
    return {
        "name": "Table4_calibration",
        "title": "Calibration-boundary summary (counts per cell)",
        "tex": "\n".join(tex_lines),
        "csv_fields": ["feature", "method", *VOCABULARY],
        "csv_rows": rows,
        "json_rows": rows,
        "inputs": ["H0_POINTWISE"],
    }


# --------------------------------------------------------------------------------------------
# Table 5: H1 condition-level power, localization and joint success
# --------------------------------------------------------------------------------------------
def build_h1_power(h1: dict) -> dict:
    percell = h1["percell"]
    m0_key = "M0_NAIVE_PERM_B999_V1"
    m1_key = "M1_DMB_R1_TRI_EXTIID_B999_V1"

    per_condition = []
    for row in percell:
        per_condition.append({
            "scenario": row["scenario_id"],
            "feature": row["feature_id"],
            "size_std_power": float(row["size_standardized_power"]),
            "raw_mae": float(row["raw_mae"]),
            "normalized_mae": float(row["normalized_mae"]),
            "M0_power": float(row["methods"][m0_key]["nominal_power"]),
            "M1_power": float(row["methods"][m1_key]["nominal_power"]),
            "M0_joint": float(row["methods"][m0_key]["joint_success"]),
            "M1_joint": float(row["methods"][m1_key]["joint_success"]),
        })
    per_condition.sort(key=lambda r: (r["scenario"], r["feature"]))

    groups: dict[tuple[str, str], list[dict]] = defaultdict(list)
    for row in per_condition:
        groups[(row["scenario"], row["feature"])].append(row)

    rows = []
    for (scenario, feature_id), members in sorted(
        groups.items(), key=lambda kv: (SCENARIO_ORDER.index(kv[0][0]), kv[0][1])
    ):
        n = len(members)
        rows.append({
            "scenario": scenario,
            "feature": feature_label(feature_id),
            "feature_id": feature_id,
            "conditions": n,
            "size_std_power": sum(m["size_std_power"] for m in members) / n,
            "normalized_mae": sum(m["normalized_mae"] for m in members) / n,
            "M0_joint": sum(m["M0_joint"] for m in members) / n,
            "M1_joint": sum(m["M1_joint"] for m in members) / n,
        })

    tex_lines = [
        r"\begin{table}[ht]", r"\centering",
        r"\caption{同一场景内四个预设条件的等权描述性汇总。尺寸标准化功效使用各自匹配的零假设临界值；"
        r"平均归一化 MAE 为无条件位置误差除以对应 $T$ 后的均值；联合成功率按式\eqref{eq:joint-success}"
        r"分别计算。}\label{tab:h1-power}",
        r"\begingroup", r"\footnotesize", r"\setlength{\tabcolsep}{3.5pt}",
        r"\begin{tabular}{llccrr}", r"\toprule",
        r"场景 & 表示 & 检出能力 & 定位误差 & \multicolumn{2}{c}{检出--定位联合成功}\\",
        r"\cmidrule(lr){3-3}\cmidrule(lr){4-4}\cmidrule(lr){5-6}",
        r" & & $\widehat\beta_{\mathrm{std}}$ & nMAE & M0 & M1\\", r"\midrule",
    ]
    for row in rows:
        tex_lines.append(
            f"{SCENARIO_LABEL[row['scenario']]} & {display_feature(row['feature'])} & {row['size_std_power']:.5f} & "
            f"{row['normalized_mae']:.5f} & {row['M0_joint']:.4f} & {row['M1_joint']:.4f}\\\\"
        )
    tex_lines += [r"\bottomrule", r"\end{tabular}", r"\endgroup", r"\end{table}", ""]

    return {
        "name": "Table5_h1_power",
        "title": "H1 power/localization",
        "tex": "\n".join(tex_lines),
        "csv_fields": ["scenario", "feature", "size_std_power", "raw_mae", "normalized_mae",
                       "M0_power", "M1_power", "M0_joint", "M1_joint"],
        "csv_rows": per_condition,
        "json_rows": rows,
        "inputs": ["H1_REANALYSIS"],
    }


# --------------------------------------------------------------------------------------------
# driver
# --------------------------------------------------------------------------------------------
def build_all() -> list[dict]:
    h0_rows = load(CANON / "H0_POINTWISE.json")
    contrasts = load(CANON / "H0_PRIMARY_CONTRASTS.json")
    bootstrap = load(BOOTSTRAP / "P1_P3_BOOTSTRAP_SUMMARY.json")
    h1 = load(CANON / "H1_REANALYSIS.json")

    if len(h0_rows) != 112:
        raise SystemExit(f"H0_POINTWISE.json: expected 112 rows, found {len(h0_rows)}")
    if len(h1["percell"]) != 16:
        raise SystemExit(f"H1_REANALYSIS.json: expected 16 percell rows, found {len(h1['percell'])}")

    return [
        build_design(h0_rows),
        build_h0_representative(h0_rows),
        build_primary(contrasts, bootstrap),
        build_calibration(h0_rows),
        build_h1_power(h1),
    ]


INPUT_PATHS = {
    "H0_POINTWISE": CANON / "H0_POINTWISE.json",
    "H0_PRIMARY_CONTRASTS": CANON / "H0_PRIMARY_CONTRASTS.json",
    "H1_REANALYSIS": CANON / "H1_REANALYSIS.json",
    "P1_P3_BOOTSTRAP_SUMMARY": BOOTSTRAP / "P1_P3_BOOTSTRAP_SUMMARY.json",
}


def write_all(out_dir: Path) -> list[dict]:
    out_dir.mkdir(parents=True, exist_ok=True)
    analysis_id = load(CANON / "bootstrap_context.json")["analysis_id"]
    script_sha = sha256_of(Path(__file__))
    tables = build_all()
    for table in tables:
        name = table["name"]
        write_text(out_dir / f"{name}.tex", table["tex"])
        write_csv(out_dir / f"{name}.csv", table["csv_fields"], table["csv_rows"])
        write_json(out_dir / f"{name}.json", {
            "schema_version": 1, "title": table["title"], "rows": table["json_rows"],
        })
        outputs = {
            f"{name}.tex": sha256_of(out_dir / f"{name}.tex"),
            f"{name}.csv": sha256_of(out_dir / f"{name}.csv"),
            f"{name}.json": sha256_of(out_dir / f"{name}.json"),
        }
        content_sha = hashlib.sha256(
            "".join(f"{key}\0{value}\n" for key, value in sorted(outputs.items())).encode()
        ).hexdigest()

        # Byte stability: the wall-clock stamp is reused while the generated content is unchanged,
        # so re-running the generator leaves the tree clean (`git diff --exit-code` in the release
        # job) instead of dirtying every meta file on every run.
        meta_path = out_dir / f"{name}.json.meta.json"
        generated_at = datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
        if meta_path.exists():
            try:
                previous = json.loads(meta_path.read_text(encoding="utf-8"))
            except json.JSONDecodeError:
                previous = {}
            if previous.get("content_sha256") == content_sha and previous.get("generated_at"):
                generated_at = previous["generated_at"]

        write_json(meta_path, {
            "schema_version": 1,
            "kind": "TABLE",
            "title": table["title"],
            "analysis_id": analysis_id,
            "generated_at": generated_at,
            "content_sha256": content_sha,
            "script": SCRIPT_REL,
            "script_sha256": script_sha,
            "inputs": table["inputs"],
            "input_sha256": {n: sha256_of(INPUT_PATHS[n]) for n in table["inputs"]},
            "outputs": outputs,
        })
    return tables


def normalized(path: Path) -> bytes:
    return path.read_bytes().replace(b"\r\n", b"\n")


def compare(fresh: Path, committed: Path) -> tuple[int, list[str]]:
    """Semantic comparison: csv as parsed rows, json as parsed objects, tex as normalised text."""
    problems: list[str] = []
    notes: list[str] = []
    for fresh_file in sorted(fresh.iterdir()):
        name = fresh_file.name
        target = committed / name
        if not target.exists():
            problems.append(f"MISSING {name} (regenerate and commit: `make_tables.py`)")
            continue
        if name.endswith(".csv"):
            with fresh_file.open(encoding="utf-8-sig", newline="") as a, target.open(encoding="utf-8-sig", newline="") as b:
                if list(csv.DictReader(a)) != list(csv.DictReader(b)):
                    problems.append(f"SEMANTIC MISMATCH {name}")
        elif name.endswith(".json") and not name.endswith(".meta.json"):
            if load(fresh_file) != load(target):
                problems.append(f"SEMANTIC MISMATCH {name}")
        elif name.endswith(".meta.json"):
            fresh_meta, committed_meta = load(fresh_file), load(target)
            # `generated_at` is a wall-clock stamp and is excluded from the reproducibility
            # comparison; every hash-bearing field is compared strictly.
            fresh_meta.pop("generated_at", None)
            committed_meta.pop("generated_at", None)
            if fresh_meta != committed_meta:
                differing = sorted(k for k in set(fresh_meta) | set(committed_meta)
                                   if fresh_meta.get(k) != committed_meta.get(k))
                problems.append(f"META MISMATCH {name}: {', '.join(differing)}")
        else:
            if fresh_file.read_bytes() != target.read_bytes():
                if normalized(fresh_file) == normalized(target):
                    notes.append(f"EOL-only difference (ok): {name}")
                else:
                    problems.append(f"TEXT MISMATCH {name}")

    produced = {f.name for f in fresh.iterdir()}
    for extra in sorted(committed.glob("Table*")):
        if extra.name not in produced and extra.name not in LEGACY_ALLOWLIST:
            problems.append(f"UNEXPECTED artifact not produced by the generator: {extra.name}")
    return len(problems), problems + notes


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--out", type=Path, default=OUT, help="output directory (default: artifacts/tables)")
    parser.add_argument("--check", action="store_true", help="compare with the committed tables")
    args = parser.parse_args(argv)

    if not args.check:
        tables = write_all(args.out)
        for table in tables:
            print(f"wrote {args.out}/{table['name']}.{{tex,csv,json,json.meta.json}} ({len(table['json_rows'])} rows)")
        return 0

    with tempfile.TemporaryDirectory() as tmp:
        fresh = Path(tmp) / "tables"
        expected = [table["name"] for table in write_all(fresh)]
        bad, lines = compare(fresh, args.out)
        for line in lines:
            print(f"  {line}")
        broken = {name for name in expected for line in lines if name in line}
        print(f"tables: {len(expected) - len(broken)}/{len(expected)} ok, {bad} problem(s)")
        return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
