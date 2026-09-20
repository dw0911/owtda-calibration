"""Rebuild the manuscript figure set per the 2026-09-20 figure/table audit.

Fig1 method/exchangeability schematic; Fig2 H1 alternative geometry; Fig3 M0 Type-I
surface (0-1 scale, M0 only); Fig4 M1 calibration deviation (alpha-hat-0.05, diverging,
class markers); Fig5 condition-level H1 power points + BPI-minus-MOMENTS difference.
Every figure is emitted as PDF/SVG/PNG plus a meta.json with input/script hashes.
"""
import csv
import hashlib
import json
import struct
import sys
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

plt.rcParams["font.sans-serif"] = ["SimHei", "Microsoft YaHei"]
plt.rcParams["axes.unicode_minus"] = False

# 路径解析为仓库相对（2026-09-20 生成本仓库图件后，仅做可移植性修订；绘图逻辑未变）。
ROOT = Path(__file__).resolve().parents[2]
FIG = ROOT / "artifacts" / "figures"
VER = ROOT / "artifacts" / "tables"
FIG.mkdir(parents=True, exist_ok=True)

CTX = json.loads((ROOT / "governance" / "bootstrap_context.json").read_text(encoding="utf-8"))
ANALYSIS_ID = CTX["analysis_id"]
SCRIPT_HASH = hashlib.sha256(Path(__file__).read_bytes()).hexdigest()


def f64(t):
    return struct.unpack(">d", bytes.fromhex(t[4:]))[0]


def read_csv(name):
    rows = list(csv.DictReader(open(VER / name, encoding="utf-8")))
    return [{k.lstrip("\ufeff"): v for k, v in r.items()} for r in rows]


def write_meta(fname, inputs):
    meta = {
        "schema_version": 1,
        "kind": "FIGURE",
        "analysis_id": ANALYSIS_ID,
        "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "script_sha256": SCRIPT_HASH,
        "input_sha256": {n: hashlib.sha256((VER / n).read_bytes()).hexdigest() for n in inputs},
    }
    (FIG / f"{fname}.meta.json").write_text(json.dumps(meta, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def save(fig, fname, inputs):
    for ext in ("png", "svg", "pdf"):
        fig.savefig(FIG / f"{fname}.{ext}", dpi=220, bbox_inches="tight")
    plt.close(fig)
    write_meta(fname, inputs)
    print("wrote", fname)


H0 = read_csv("H0_ALL_112.csv")
H1 = read_csv("H1_ALL_16_GEOMETRY_COMPLETE.csv")
DIFF = read_csv("H1_SCENARIO_DIFFERENCES.csv")
INPUTS = ["H0_ALL_112.csv", "H1_ALL_16_GEOMETRY_COMPLETE.csv", "H1_SCENARIO_DIFFERENCES.csv"]


def budget_rows(budget):
    out = []
    for r in H0:
        is_m = int(float(r["M_expected"])) == 192
        is_t = int(float(r["T"])) == 3120
        if budget == "M" and not is_m:
            continue
        if budget == "T" and not is_t:
            continue
        rho = f64(r["rho"]) if isinstance(r["rho"], str) and r["rho"].startswith("f64:") else float(r["rho"])
        out.append({
            "dgp": r["DGP_family"], "rho": round(rho, 2), "s": int(float(r["stride"])),
            "T": int(float(r["T"])), "M": int(float(r["M_expected"])),
            "feature": "BPI" if "BPI" in r["feature_id"] else "MOMENTS",
            "method": "M0" if "M0" in r["method_id"] else "M1",
            "rate": float(r["rejection_rate"]), "cls": r["classification"],
        })
    return out


# ---------------- Fig 1: method / exchangeability schematic ----------------
def fig1():
    fig, ax = plt.subplots(figsize=(9, 4.2))
    ax.axis("off")
    ax.set_xlim(0, 100); ax.set_ylim(0, 42)

    def box(x, y, w, h, text, fc="#eef3fa", ec="#33475b"):
        ax.add_patch(plt.Rectangle((x, y), w, h, fc=fc, ec=ec, lw=1.1))
        ax.text(x + w / 2, y + h / 2, text, ha="center", va="center", fontsize=8)

    def arrow(x1, y, x2):
        ax.annotate("", xy=(x2, y), xytext=(x1, y), arrowprops=dict(arrowstyle="->", lw=1.1, color="#33475b"))

    box(1, 26, 15, 10, "原始序列\n$X_1,\\ldots,X_T$")
    arrow(16, 31, 22)
    box(22, 24, 17, 14, "重叠滑动窗口\n$I_i$ (步长 $s<W$)")
    arrow(39, 31, 45)
    box(45, 26, 14, 10, "窗口点云")
    arrow(59, 31, 64)
    box(64, 32, 15, 7, "持续图 / BPI")
    box(64, 23, 15, 7, "MOMENTS")
    arrow(79, 35.5, 84)
    arrow(79, 26.5, 84)
    box(84, 26, 14, 14, "最大扫描\n$T_M$, $\\hat k$")

    # calibration branches
    ax.annotate("", xy=(91, 18), xytext=(91, 26), arrowprops=dict(arrowstyle="->", lw=1.1, color="#33475b"))
    box(78, 8, 12, 8, "M0：全排列\n打乱窗口序", fc="#fdeaea")
    box(93, 8, 12, 8, "M1：相关乘子\n保留滞后结构", fc="#eaf5ea")
    ax.text(91, 19, "校准参考分布", ha="center", fontsize=8, color="#33475b")

    # shared-observation highlight
    ax.text(22, 20, "同一原始观测被多个随机化单位共享\n$\\Rightarrow$ 全排列破坏局部协方差结构",
            fontsize=8, color="#a13d3d")
    ax.add_patch(plt.Rectangle((22, 18), 17, 6, fill=False, ec="#a13d3d", ls="--", lw=1.0))
    ax.text(50, 2, "被相邻窗口重复使用的观测（示意）", fontsize=7.5, color="#a13d3d", ha="center")
    for i in range(8):
        ax.plot(44 + i * 1.6, 5, "o", color="#a13d3d", ms=4)
    for i in range(7):
        ax.plot([44 + i * 1.6, 44 + (i + 1) * 1.6], [5, 5], color="#a13d3d", lw=0.8, ls=":")
    return fig


# ---------------- Fig 2: H1 alternative geometry ----------------
def fig2():
    fig, axs = plt.subplots(1, 4, figsize=(10.5, 2.9))
    th = np.linspace(0, 2 * np.pi, 300)
    circle = (np.cos(th), np.sin(th))
    eight = (np.sin(th), np.sin(2 * th))
    panels = [
        ("变化前：圆形", circle, None),
        ("变化后：八字", eight, None),
        ("变化前：圆形", circle, None),
        ("变化后：整体平移", (circle[0] + 0.5, circle[1] + 0.5), "shift"),
    ]
    for ax, (title, (x, y), kind) in zip(axs, panels):
        ax.plot(x, y, lw=1.4, color="#1f4e79")
        ax.set_title(title, fontsize=8.5)
        ax.set_aspect("equal")
        ax.set_xticks([]); ax.set_yticks([])
        ax.grid(alpha=0.2)
    axs[0].set_ylabel("shape change", fontsize=8)
    axs[2].set_ylabel("mean shift", fontsize=8)
    fig.suptitle("两类备择构造（圆与八字仅匹配单时点均值与协方差；平移直接改变均值）", fontsize=9)
    return fig


# ---------------- Fig 3: M0 Type-I surface ----------------
def heat(ax, panel_rows, vmin, vmax, cmap, methods=("M0", "M1"), show_vals=True, markers=False):
    feats = ["BPI", "MOMENTS"]
    rkeys = []
    for d in ("N_AR", "N_CIRCLE"):
        for rho in (0.0, 0.8):
            for s in (8, 16, 32, 64):
                rkeys.append((d, rho, s))
    cols = [f"{f}/{m}" for f in feats for m in methods]
    M = np.full((len(rkeys), len(cols)), np.nan)
    cls_map = {}
    for r in panel_rows:
        i = rkeys.index((r["dgp"], r["rho"], r["s"])) if (r["dgp"], r["rho"], r["s"]) in rkeys else None
        if i is None:
            continue
        for j, c in enumerate(cols):
            f, m = c.split("/")
            if r["feature"] == f and r["method"] == m:
                M[i, j] = r["rate"]
                cls_map[(i, j)] = r["cls"]
    im = ax.imshow(M, cmap=cmap, vmin=vmin, vmax=vmax, aspect="auto")
    ax.set_xticks(range(len(cols)))
    ax.set_xticklabels(cols, fontsize=7.5, rotation=25, ha="right")
    ax.set_yticks(range(len(rkeys)))
    ax.set_yticklabels([f"{d} $\\rho$={rho:g} $s$={s}" for d, rho, s in rkeys], fontsize=7)
    if show_vals:
        for i in range(M.shape[0]):
            for j in range(M.shape[1]):
                if np.isfinite(M[i, j]):
                    ax.text(j, i, f"{M[i,j]:.3f}", ha="center", va="center", fontsize=6,
                            color="white" if abs(M[i, j] - vmin) > 0.55 * (vmax - vmin) else "black")
    if markers:
        sym = {"POINTWISE_PRACTICALLY_CALIBRATED": "o", "MATERIAL_CONSERVATISM": "v",
               "MATERIAL_ANTI_CONSERVATISM": "^", "BOUNDARY_OR_INDETERMINATE": "s"}
        for (i, j), c in cls_map.items():
            if c in sym:
                ax.plot(j, i, sym[c], ms=3.2, mfc="none", mec="k", mew=0.7)
    return im


def fig3():
    fig, axs = plt.subplots(1, 2, figsize=(9.5, 4.6))
    for ax, (budget, title) in zip(axs, (("M", "fixed-$M$ ($M=192$)"), ("T", "fixed-$T$ ($T=3120$)"))):
        rows = [r for r in budget_rows(budget) if r["method"] == "M0"]
        im = heat(ax, rows, 0, 1, "RdYlBu_r", methods=("M0",))
        ax.set_title(f"{title}：M0 误报表面", fontsize=9)
    fig.colorbar(im, ax=axs, shrink=0.85, label="Type-I rejection rate")
    fig.suptitle("朴素置换（M0）在两种预算制度下的有限样本误报表面（色尺 $[0,1]$）", fontsize=9.5)
    return fig


def fig4():
    fig, axs = plt.subplots(1, 2, figsize=(9.5, 4.6))
    for ax, (budget, title) in zip(axs, (("M", "fixed-$M$ ($M=192$)"), ("T", "fixed-$T$ ($T=3120$)"))):
        rows = [{**r, "rate": r["rate"] - 0.05} for r in budget_rows(budget) if r["method"] == "M1"]
        im = heat(ax, rows, -0.048, 0.0912, "coolwarm", methods=("M1",), markers=True)
        ax.set_title(f"{title}：M1 校准偏差", fontsize=9)
    fig.colorbar(im, ax=axs, shrink=0.85, label=r"$\widehat\alpha-0.05$（负=保守，正=反保守）")
    fig.suptitle("依赖乘子法（M1）的校准偏差表面（以 0 为中心；符号编码 Wilson 判定）", fontsize=9.5)
    return fig


# ---------------- Fig 5: condition-level power + difference forest ----------------
def fig5():
    fig, (axL, axR) = plt.subplots(1, 2, figsize=(10.5, 4.4))
    colors = {"BPI": "#1f77b4", "MOMENTS": "#d62728"}
    marks = {0.0: "o", 0.8: "s"}
    scen_x = {"shape_change": 0, "mean_shift": 1}
    for (scen, feat), sub in defaultdict(list).items() if False else []:
        pass
    grouped = defaultdict(list)
    for r in H1:
        rho = f64(r["rho"]) if isinstance(r["rho"], str) and r["rho"].startswith("f64:") else float(r["rho"])
        grouped[(r["scenario_id"], "BPI" if "BPI" in r["feature_id"] else "MOMENTS")].append(
            (round(rho, 2), int(float(r["stride"])), float(r["size_standardized_power"])))
    for (scen, feat), pts in sorted(grouped.items()):
        x0 = scen_x[scen]
        xs, ys = [], []
        for rho, s, p in pts:
            jitter = 0.045 if s == 16 else 0.115
            xs.append(x0 + jitter + (0.0 if rho == 0.0 else 0.028))
            ys.append(p)
            axL.plot(xs[-1], ys[-1], marks[rho], color=colors[feat], ms=6, alpha=0.85)
        mean = sum(y for _, _, y in pts) / len(pts)
        axL.plot([x0 + 0.02, x0 + 0.16], [mean, mean], "-", color=colors[feat], lw=2.4)
        axL.text(x0 + 0.17, mean, f"{mean:.4f}", fontsize=6.6, color=colors[feat], va="center")
    axL.set_xticks([0.08, 1.08])
    axL.set_xticklabels(["shape change", "mean shift"], fontsize=9)
    axL.set_ylabel("size-standardized power", fontsize=9)
    axL.set_ylim(-0.03, 1.06)
    axL.grid(alpha=0.25, axis="y")
    axL.set_title("四条件功效点（点形= $\\rho$，偏移= $s$；横线=场景等权均值）", fontsize=8.6)
    handles = [plt.Line2D([], [], marker="o", color="w", markerfacecolor=colors[f], label=f, ms=7) for f in ("BPI", "MOMENTS")]
    axL.legend(handles=handles, fontsize=8, loc="center left")

    ypos = {0: 0.62, 1: 0.0}
    for i, r in enumerate(DIFF):
        d = float(r["difference"]); lo = float(r["lower95"]); hi = float(r["upper95"])
        y = ypos[i]
        axR.plot([lo, hi], [y, y], "-", color="#33475b", lw=2.2)
        axR.plot(d, y, "D", color="#b22222", ms=8)
        axR.text(hi + 0.012, y, f"{d:.5f} [{lo:.5f}, {hi:.5f}]", fontsize=7.4, va="center")
    axR.axvline(0, color="k", ls="--", lw=1)
    axR.set_yticks([0.0, 0.62])
    axR.set_yticklabels(["mean shift", "shape change"], fontsize=9)
    axR.set_xlabel("BPI $-$ MOMENTS（标准化功效差）", fontsize=9)
    axR.set_xlim(-1.0, 1.02)
    axR.grid(alpha=0.25, axis="x")
    axR.set_title("表示差及 2000 次配对 bootstrap 95% CI", fontsize=8.6)
    return fig


def main():
    save(fig1(), "Figure1_method_schematic", INPUTS)
    save(fig2(), "Figure2_alternative_geometry", INPUTS)
    save(fig3(), "Figure3_M0_type1_surface", INPUTS)
    save(fig4(), "Figure4_M1_deviation_surface", INPUTS)
    save(fig5(), "Figure5_H1_power_and_difference", INPUTS)


if __name__ == "__main__":
    main()
