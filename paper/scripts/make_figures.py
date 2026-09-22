"""Rebuild the manuscript figure set per the 2026-09-20/21 figure audits.

Fig2 H1 alternative geometry; Fig3 M0 Type-I surface (0-1 scale, M0 only); Fig4 M1
calibration deviation (alpha-hat-0.05, diverging, class markers); Fig5 condition-level
H1 power points + BPI-minus-MOMENTS difference.  Every figure is emitted as PDF/SVG/PNG
plus a meta.json with input/script hashes.

Fig1 (flow + overlap schematic) is TikZ source in paper/figures/ compiled by XeLaTeX
directly — it no longer passes through matplotlib (2026-09-21 audit, option A).
"""
import argparse
import csv
import hashlib
import json
import re
import struct
import sys
from collections import defaultdict
from datetime import UTC, datetime
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

# ---------------------------------------------------------------------------
# CJK 字体解析（跨平台 fail-closed）
#
#   图内标签使用中文；字体必须在目标平台上"可确定获得"，否则 Linux/CI 上重新生成会得到
#   缺字方框（2026-09-20 审计：审查环境产生大量 Glyph missing 警告）。
#   解析顺序覆盖 Linux（fonts-noto-cjk / fonts-wqy-zenhei）、macOS 与 Windows。
#   一个都不可用时**默认报错退出**，不静默产出缺字图；仅本地审阅可显式
#   --allow-missing-fonts 放行。CI 使用 --check-fonts 断言字体存在。
# ---------------------------------------------------------------------------
CJK_CANDIDATES = (
    # 正文为 ctexart 默认宋体，图内中文优先匹配宋体（衬线），与正文一致；
    # 找不到宋体时才回退到黑体（2026-09-21 图2 字体审计）。
    "SimSun",                # Windows 宋体
    "STSong",                # Windows 华文宋体
    "NSimSun",               # Windows 新宋体
    "Noto Serif CJK SC",     # Linux 思源宋体
    "Source Han Serif SC",
    "Songti SC",             # macOS 宋体
    "SimHei",                # 回退：黑体（无衬线）
    "Microsoft YaHei",
    "Noto Sans CJK SC",
    "WenQuanYi Zen Hei",
    "PingFang SC",
    "Hiragino Sans GB",
)

# PDF 元数据：抑制创建/修改时间，使同一 matplotlib 版本下的重生成字节稳定
# （PNG 本身逐字节稳定；SVG 由 svg.hashsalt 稳定）。
PDF_METADATA = {"Creator": "paper/scripts/make_figures.py", "CreationDate": None, "ModDate": None}


def resolve_cjk_font() -> str | None:
    """First available CJK-capable font, or None (matplotlib's own font index is used)."""
    from matplotlib import font_manager

    available = {font.name for font in font_manager.fontManager.ttflist}
    for name in CJK_CANDIDATES:
        if name in available:
            return name
    return None

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
    with (VER / name).open(encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))
    return [{k.lstrip("\ufeff"): v for k, v in r.items()} for r in rows]


def paper_references(fname: str) -> list[str]:
    """Manuscript files that include this figure (artifact <-> manuscript provenance link)."""
    hits = []
    for tex in sorted((ROOT / "paper").rglob("*.tex")):
        text = tex.read_text(encoding="utf-8-sig", errors="replace")
        if fname in text:
            hits.append(tex.relative_to(ROOT).as_posix())
    return hits


def write_meta(fname, inputs, outputs):
    content_sha = hashlib.sha256(
        "".join(f"{key}\0{value}\n" for key, value in sorted(outputs.items())).encode()
    ).hexdigest()
    meta_path = FIG / f"{fname}.meta.json"

    # Byte stability: keep the previous wall-clock stamp while the rendered content is unchanged,
    # so re-running the generator does not dirty every meta file.
    generated_at = datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
    if meta_path.exists():
        try:
            previous = json.loads(meta_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            previous = {}
        if previous.get("content_sha256") == content_sha and previous.get("generated_at"):
            generated_at = previous["generated_at"]

    meta = {
        "schema_version": 1,
        "kind": "FIGURE",
        "analysis_id": ANALYSIS_ID,
        "generated_at": generated_at,
        "content_sha256": content_sha,
        "script": "paper/scripts/make_figures.py",
        "script_sha256": SCRIPT_HASH,
        "inputs": inputs,
        "input_sha256": {n: hashlib.sha256((VER / n).read_bytes()).hexdigest() for n in inputs},
        "outputs": outputs,
        "referenced_by": paper_references(fname),
    }
    meta_path.write_text(json.dumps(meta, indent=2, sort_keys=True) + "\n", encoding="utf-8")


SVG_DATE = re.compile(r"[ \t]*<dc:date>[^<]*</dc:date>\n?")


def save(fig, fname, inputs):
    outputs = {}
    for ext in ("png", "svg", "pdf"):
        path = FIG / f"{fname}.{ext}"
        kwargs = {"dpi": 220, "bbox_inches": "tight"}
        if ext == "pdf":
            kwargs["metadata"] = PDF_METADATA
        fig.savefig(path, **kwargs)
        if ext == "svg":
            # matplotlib writes a wall-clock <dc:date> into the SVG metadata, which would make the
            # file (and therefore content_sha256) change on every run. The element carries no
            # scientific information — the timestamp lives in this table's meta.json — so it is
            # removed to keep regenerated figures byte-stable.
            text = path.read_text(encoding="utf-8")
            stripped = SVG_DATE.sub("", text, count=1)
            if stripped != text:
                path.write_text(stripped, encoding="utf-8", newline="\n")
        outputs[path.name] = hashlib.sha256(path.read_bytes()).hexdigest()
    plt.close(fig)
    write_meta(fname, inputs, outputs)
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


# ---------------- Fig 2: H1 alternative geometry ----------------
def fig2():
    # 散点严格遵循正式 DGP 数学定义（04_protocol §备择构造）：
    #   C(u)=(cos 2πu, sin 2πu)，F(u)=(sin 2πu, sin 4πu)，
    #   观测噪声 0.08·N(0,I2)，mean shift 为 +0.5·v（‖v‖=1）。
    # 固定 seed 保证可复现；图中 v=(1,0) 仅为示例方向（正式实验跨重复随机、重复内固定）。
    rng = np.random.default_rng(20260920)
    n = 64
    u1 = rng.uniform(0, 1, n)
    u2 = rng.uniform(0, 1, n)
    u3 = rng.uniform(0, 1, n)
    eta1 = rng.standard_normal((n, 2))
    eta2 = rng.standard_normal((n, 2))
    eta3 = rng.standard_normal((n, 2))
    v = np.array([1.0, 0.0])  # 示例方向

    circle = np.column_stack([np.cos(2 * np.pi * u1), np.sin(2 * np.pi * u1)])
    eight = np.column_stack([np.sin(2 * np.pi * u2), np.sin(4 * np.pi * u2)])
    shifted = np.column_stack([np.cos(2 * np.pi * u3), np.sin(2 * np.pi * u3)]) + 0.5 * v

    pts_c1 = circle + 0.08 * eta1
    pts_f = eight + 0.08 * eta2
    pts_c2 = shifted + 0.08 * eta3

    fig, axs = plt.subplots(1, 2, figsize=(9.6, 4.8))

    for ax in axs:
        ax.set_aspect("equal")
        ax.axhline(0, color="#888888", lw=0.7, ls="--")
        ax.axvline(0, color="#888888", lw=0.7, ls="--")
        ax.set_xlim(-1.45, 1.75)
        ax.set_ylim(-1.45, 1.45)
        ax.grid(alpha=0.2)

    # (a) 形状变化：圆 → 8 字形曲线
    ax = axs[0]
    ax.scatter(pts_c1[:, 0], pts_c1[:, 1], s=16, c="#1f77b4", label="变点前：圆 $C(u)$")
    ax.scatter(pts_f[:, 0], pts_f[:, 1], s=16, c="#d62728", label="变点后：8 字形曲线 $F(u)$")
    ax.set_title("(a) 形状变化", fontsize=9)

    # (b) 均值平移：圆 → 平移圆（共享坐标，位移箭头长度 0.5 可核实）
    ax = axs[1]
    ax.scatter(pts_c1[:, 0], pts_c1[:, 1], s=16, c="#1f77b4", label="变点前：圆 $C(u)$")
    ax.scatter(pts_c2[:, 0], pts_c2[:, 1], s=16, c="#d62728", label="变点后：$C(u)+0.5v$")
    ax.annotate("", xy=(0.5, 0), xytext=(0, 0),
                arrowprops={"arrowstyle": "->", "lw": 1.6, "color": "k"})
    ax.text(0.25, 0.10, "$0.5$", ha="center", fontsize=9)
    ax.set_title("(b) 均值平移（$v=(1,0)$ 示例）", fontsize=9)

    for ax in axs:
        # 半透明白底图例：面板 (a) 左上区域有散点分布，无底框时图例文字与红点重叠
        ax.legend(fontsize=8, loc="upper left", frameon=True, framealpha=0.85,
                  edgecolor="none")

    return fig


# ---------------- Fig 3: M0 Type-I surface ----------------
CLASS_SYMBOLS = {
    "POINTWISE_PRACTICALLY_CALIBRATED": ("o", "实用校准"),
    "MATERIAL_CONSERVATISM": ("v", "实质保守"),
    "MATERIAL_ANTI_CONSERVATISM": ("^", "实质反保守"),
    "BOUNDARY_OR_INDETERMINATE": ("s", "未定"),
}


def fig3():
    # M0 误报表面：2×2 分面（行 = DGP，列 = 预算制度），每面板 8 行（ρ×s）× 2 列（BPI/MOMENTS）。
    # 单调顺序色图 cividis（灰度友好）；四位小数避免 0.9996 被舍入成 1.000；字色按背景亮度选择。
    cmap = plt.get_cmap("cividis")
    # 画布按最终显示宽度 1:1 设计（0.92×正文宽 ≈ 5.8in），格内 7pt / 刻度 8pt / 标题 9pt
    # 即印刷最终字号，避免二次缩放导致的字号缩水（2026-09-21 审计 P1）。
    fig, axs = plt.subplots(2, 2, figsize=(5.8, 5.0), constrained_layout=True)

    rho_levels = (0.0, 0.8)
    strides = (8, 16, 32, 64)
    feats = ["BPI", "MOMENTS"]
    rho_idx = {0.0: 0, 0.8: 1}
    s_idx = {8: 0, 16: 1, 32: 2, 64: 3}
    dgps = [("N_AR", "N-AR"), ("N_CIRCLE", "N-CIRCLE")]
    budgets = [("M", "fixed-$M$（$M=192$）"), ("T", "fixed-$T$（$T=3120$）")]

    im = None
    for i, (dgp, dgp_label) in enumerate(dgps):
        for j, (budget, budget_label) in enumerate(budgets):
            ax = axs[i, j]
            rows = [r for r in budget_rows(budget) if r["method"] == "M0" and r["dgp"] == dgp]
            M = np.full((8, 2), np.nan)
            for r in rows:
                M[rho_idx[r["rho"]] * 4 + s_idx[r["s"]], feats.index(r["feature"])] = r["rate"]
            im = ax.imshow(M, cmap=cmap, vmin=0, vmax=1, aspect="auto")
            ax.set_xticks([0, 1])
            ax.set_xticklabels(feats, fontsize=8)
            ax.set_yticks(range(8))
            ax.set_yticklabels(
                [fr"$\rho{{=}}{rho:g},\ s{{=}}{s:d}$" for rho in rho_levels for s in strides],
                fontsize=7.5,
            )
            ax.axhline(3.5, color="white", lw=1.2)  # ρ=0 与 ρ=0.8 组间分隔
            # 格内数值：四位小数，字色按 cividis 背景感知亮度
            for ri in range(8):
                for ci in range(2):
                    v = M[ri, ci]
                    if np.isfinite(v):
                        r_, g_, b_, _ = cmap(v)
                        lum = 0.299 * r_ + 0.587 * g_ + 0.114 * b_
                        ax.text(ci, ri, f"{v:.4f}", ha="center", va="center",
                                fontsize=7, color="white" if lum < 0.5 else "black")
            # 面板标题：角标与预算制度合并为单个 set_title，避免 ax.text 与标题重叠
            label = chr(97 + i * 2 + j)
            if i == 0:
                ax.set_title(f"({label}) {budget_label}", fontsize=9)
            else:
                ax.set_title(f"({label})", fontsize=9)
            if j == 0:
                ax.set_ylabel(dgp_label, fontsize=9)

    cbar = fig.colorbar(im, ax=axs, shrink=0.85, pad=0.02, fraction=0.035, label="I 类错误率")
    cbar.ax.tick_params(labelsize=8)
    return fig


def fig4():
    from matplotlib.colors import TwoSlopeNorm

    # M1 校准偏差表面：2×2 分面（同 fig3 结构），值为 α̂-0.05。
    # 色尺关于 0 对称（TwoSlopeNorm, [-0.095, 0.095]）；Wilson 分类符号移到单元格右上角；
    # 四位小数并把 |v|<0.00005 规范化为 0.0000（消除浮点 -0.000）。
    cmap = plt.get_cmap("coolwarm")
    norm = TwoSlopeNorm(vmin=-0.095, vcenter=0.0, vmax=0.095)
    fig, axs = plt.subplots(2, 2, figsize=(5.8, 5.0), constrained_layout=True)

    rho_levels = (0.0, 0.8)
    strides = (8, 16, 32, 64)
    feats = ["BPI", "MOMENTS"]
    rho_idx = {0.0: 0, 0.8: 1}
    s_idx = {8: 0, 16: 1, 32: 2, 64: 3}
    dgps = [("N_AR", "N-AR"), ("N_CIRCLE", "N-CIRCLE")]
    budgets = [("M", "fixed-$M$（$M=192$）"), ("T", "fixed-$T$（$T=3120$）")]

    def fmt(v):
        # 直接检查格式化结果：round-half-even 下 v=-0.00005 也会格式化为 "-0.0000"，
        # 阈值判断（abs(v)<0.00005）会漏掉该边界（2026-09-21 审计 P0：消除 -0.000）。
        s = f"{v:.4f}"
        return "0.0000" if s == "-0.0000" else s

    im = None
    for i, (dgp, dgp_label) in enumerate(dgps):
        for j, (budget, budget_label) in enumerate(budgets):
            ax = axs[i, j]
            rows = [r for r in budget_rows(budget) if r["method"] == "M1" and r["dgp"] == dgp]
            M = np.full((8, 2), np.nan)
            cls = {}
            for r in rows:
                ri = rho_idx[r["rho"]] * 4 + s_idx[r["s"]]
                ci = feats.index(r["feature"])
                M[ri, ci] = r["rate"] - 0.05
                cls[(ri, ci)] = r["cls"]
            im = ax.imshow(M, cmap=cmap, norm=norm, aspect="auto")
            ax.set_xticks([0, 1])
            ax.set_xticklabels(feats, fontsize=8)
            ax.set_yticks(range(8))
            ax.set_yticklabels(
                [fr"$\rho{{=}}{rho:g},\ s{{=}}{s:d}$" for rho in rho_levels for s in strides],
                fontsize=7.5,
            )
            ax.axhline(3.5, color="0.6", lw=1.0)  # ρ 组间分隔
            for ri in range(8):
                for ci in range(2):
                    v = M[ri, ci]
                    if not np.isfinite(v):
                        continue
                    t = norm(v)
                    rgba = cmap(t)
                    lum = 0.299 * rgba[0] + 0.587 * rgba[1] + 0.114 * rgba[2]
                    color = "white" if lum < 0.5 else "black"
                    ax.text(ci, ri, fmt(v), ha="center", va="center",
                            fontsize=7, color=color)
                    # Wilson 分类符号：右上角，空心，不遮挡数值
                    c = cls.get((ri, ci))
                    if c in CLASS_SYMBOLS:
                        ax.plot(ci + 0.37, ri + 0.37, CLASS_SYMBOLS[c][0], ms=3.0,
                                mfc="none", mec="k", mew=0.6)
            # 面板标题：角标与预算制度合并为单个 set_title，避免 ax.text 与标题重叠
            label = chr(97 + i * 2 + j)
            if i == 0:
                ax.set_title(f"({label}) {budget_label}", fontsize=9)
            else:
                ax.set_title(f"({label})", fontsize=9)
            if j == 0:
                ax.set_ylabel(dgp_label, fontsize=9)

    cbar = fig.colorbar(im, ax=axs, shrink=0.85, pad=0.02, fraction=0.035,
                        label=r"$\widehat\alpha-0.05$（负=保守，正=反保守）")
    cbar.ax.tick_params(labelsize=8)
    # 四类 Wilson 判定符号图例
    handles = [
        plt.Line2D([], [], ls="none", marker=symbol, mfc="none", mec="k", mew=0.7, ms=5, label=label)
        for symbol, label in CLASS_SYMBOLS.values()
    ]
    fig.legend(handles=handles, loc="lower center", ncol=4, fontsize=7.6, frameon=False,
               bbox_to_anchor=(0.5, -0.03))
    return fig


# ---------------- Fig 5: condition-level power + difference forest ----------------
def fig5():
    # 上下两面板（审查建议）：上 = 条件级功效（ρ 点形、s 水平偏移、表示实心/空心 + 颜色）；
    # 下 = BPI−MOMENTS 差值及 2000 次配对 bootstrap 95% CI（带端帽 errorbar）。
    # 画布 1:1（0.92×正文宽 ≈ 5.8in）；场景均值用五位小数（0.05375 不被舍入成 0.0537）。
    fig, (axL, axR) = plt.subplots(2, 1, figsize=(5.8, 5.4), constrained_layout=True)
    colors = {"BPI": "#1f77b4", "MOMENTS": "#d62728"}
    marks = {0.0: "o", 0.8: "s"}
    scen_x = {"shape_change": 0, "mean_shift": 1}

    grouped = defaultdict(list)
    for r in H1:
        rho = f64(r["rho"]) if isinstance(r["rho"], str) and r["rho"].startswith("f64:") else float(r["rho"])
        grouped[(r["scenario_id"], "BPI" if "BPI" in r["feature_id"] else "MOMENTS")].append(
            (round(rho, 2), int(float(r["stride"])), float(r["size_standardized_power"])))

    def fmt_mean(v):
        return "1.0000" if abs(v - 1.0) < 1e-9 else f"{v:.5f}"

    # ---- 上面板：条件级功效 ----
    for (scen, feat), pts in sorted(grouped.items()):
        x0 = scen_x[scen]
        for rho, s, p in pts:
            jitter = -0.10 if s == 16 else 0.10
            x = x0 + jitter + (0.0 if rho == 0.0 else 0.03)
            axL.plot(x, p, marks[rho], color=colors[feat],
                     mfc=colors[feat] if feat == "BPI" else "none",
                     mec=colors[feat], ms=7, mew=1.2, alpha=0.9)
        mean = sum(y for _, _, y in pts) / len(pts)
        axL.plot([x0 - 0.20, x0 + 0.20], [mean, mean], "-", color=colors[feat], lw=2.2, alpha=0.8)
        axL.text(x0 + 0.22, mean, fmt_mean(mean), fontsize=7.5, color=colors[feat], va="center")

    axL.set_xlim(-0.40, 1.40)
    axL.set_xticks([0, 1])
    axL.set_xticklabels(["形状变化", "均值平移"], fontsize=9)
    axL.set_ylabel("尺寸校正功效", fontsize=9)
    axL.set_ylim(-0.03, 1.06)
    axL.grid(alpha=0.25, axis="y")
    axL.set_title("(a) 四条件功效点（点形= $\\rho$，偏移= $s$；横线=场景等权均值）", fontsize=9)

    # 图例只保留表示（BPI 实心 / MOMENTS 空心）；ρ 与 s 的编码用一行文字说明，
    # 避免灰色图例项与数据点红蓝脱节造成的困惑（2026-09-21 复审：ρ 图例项冗余）。
    handles = [
        plt.Line2D([], [], ls="none", marker="o", mfc=colors["BPI"], mec=colors["BPI"], ms=7, label="BPI（实心）"),
        plt.Line2D([], [], ls="none", marker="o", mfc="none", mec=colors["MOMENTS"], ms=7, label="MOMENTS（空心）"),
    ]
    axL.legend(handles=handles, fontsize=7.5, loc="center left", frameon=False, ncol=1)
    axL.text(0.03, 0.24, "点形：○= $\\rho{=}0$，□= $\\rho{=}0.8$；左点 $s{=}16$，右点 $s{=}64$",
             transform=axL.transAxes, fontsize=7.5, va="bottom")

    # ---- 下面板：表示差及 CI ----
    ypos = {"shape_change": 0.62, "mean_shift": 0.0}
    for r in DIFF:
        d = float(r["difference"]); lo = float(r["lower95"]); hi = float(r["upper95"])
        y = ypos[r["scenario"]]
        axR.errorbar(d, y, xerr=[[d - lo], [hi - d]], fmt="D", color="#b22222",
                     ecolor="#33475b", elinewidth=2.0, capsize=5, ms=8)
        # 标签放图内靠近零线一侧（正差值放左侧右对齐，负差值放右侧左对齐），避免超出图框
        label = f"{d:.5f} [{lo:.5f}, {hi:.5f}]"
        if d > 0:
            axR.text(d - 0.06, y, label, ha="right", va="center", fontsize=7.5)
        else:
            axR.text(hi + 0.06, y, label, ha="left", va="center", fontsize=7.5)
    axR.axvline(0, color="k", ls="--", lw=1)
    axR.set_yticks([ypos["mean_shift"], ypos["shape_change"]])
    axR.set_yticklabels(["均值平移", "形状变化"], fontsize=9)
    axR.set_xlabel("BPI $-$ MOMENTS（尺寸校正功效差）", fontsize=9)
    axR.set_xlim(-1.05, 1.05)
    axR.set_ylim(-0.30, 0.92)
    axR.grid(alpha=0.25, axis="x")
    axR.set_title("(b) 表示差及 2000 次配对 bootstrap 95% CI", fontsize=9)
    return fig


# ---------------- Fig S1 (supplement): complete 16x4 H0 heatmap ----------------
def fig_supplement_h0():
    # 补充材料：完整 16×4 逐格热图。16 行 = 条件（DGP×ρ×s），4 列 = BPI/M0、MOMENTS/M0、
    # BPI/M1、MOMENTS/M1；两个面板分别对应 fixed-M 与 fixed-T。值为 I 类错误率（0-1），
    # cividis 顺序色图，四位小数，字色按背景亮度（2026-09-21 审计 P0：补充 16×4 热图）。
    cmap = plt.get_cmap("cividis")
    fig, axs = plt.subplots(1, 2, figsize=(9.0, 6.2), constrained_layout=True)

    dgp_labels = ["N-AR", "N-CIRCLE"]
    rho_levels = (0.0, 0.8)
    strides = (8, 16, 32, 64)
    feats = ["BPI", "MOMENTS"]
    methods = ["M0", "M1"]
    cols = [f"{f}/{m}" for f in feats for m in methods]
    rho_idx = {0.0: 0, 0.8: 1}
    s_idx = {8: 0, 16: 1, 32: 2, 64: 3}
    dgp_idx = {"N_AR": 0, "N_CIRCLE": 1}
    budgets = [("M", "fixed-$M$（$M=192$）"), ("T", "fixed-$T$（$T=3120$）")]

    ylabels = []
    for dgp_i in (0, 1):
        for rho in rho_levels:
            for s in strides:
                ylabels.append(f"{dgp_labels[dgp_i]} $\\rho$={rho:g}, $s$={s}")

    im = None
    for k, (budget, budget_label) in enumerate(budgets):
        ax = axs[k]
        M = np.full((16, 4), np.nan)
        for r in budget_rows(budget):
            row = dgp_idx[r["dgp"]] * 8 + rho_idx[r["rho"]] * 4 + s_idx[r["s"]]
            col = feats.index(r["feature"]) * 2 + methods.index(r["method"])
            M[row, col] = r["rate"]
        im = ax.imshow(M, cmap=cmap, vmin=0, vmax=1, aspect="auto")
        ax.set_xticks(range(4))
        ax.set_xticklabels(cols, fontsize=7.5, rotation=20, ha="right")
        ax.set_yticks(range(16))
        ax.set_yticklabels(ylabels, fontsize=6.8)
        # 分隔线：DGP 间（y=7.5）、ρ 组间（y=3.5, 11.5）
        ax.axhline(7.5, color="white", lw=1.4)
        ax.axhline(3.5, color="white", lw=0.8)
        ax.axhline(11.5, color="white", lw=0.8)
        for row in range(16):
            for col in range(4):
                v = M[row, col]
                if np.isfinite(v):
                    rgba = cmap(v)
                    lum = 0.299 * rgba[0] + 0.587 * rgba[1] + 0.114 * rgba[2]
                    ax.text(col, row, f"{v:.4f}", ha="center", va="center",
                            fontsize=6.5, color="white" if lum < 0.5 else "black")
        ax.set_title(budget_label, fontsize=9)

    cbar = fig.colorbar(im, ax=axs, shrink=0.85, pad=0.02, fraction=0.03, label="I 类错误率")
    cbar.ax.tick_params(labelsize=8)
    return fig


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check-fonts", action="store_true",
                        help="只报告 CJK 字体解析结果（CI 用），不生成图件")
    parser.add_argument("--allow-missing-fonts", action="store_true",
                        help="缺少 CJK 字体时仍然渲染（仅限本地审阅；CI 必须失败）")
    parser.add_argument("--only", nargs="*", default=None,
                        help="只生成指定图（如 Figure1 / Figure2）；缺省生成全部")
    args = parser.parse_args(argv)

    font = resolve_cjk_font()
    if font:
        plt.rcParams["font.serif"] = [font, "Times New Roman", "DejaVu Serif"]
        plt.rcParams["font.family"] = "serif"
    # 数学公式用 Computer Modern（cm），与正文 XeLaTeX 数学字体一致；默认的
    # DejaVu Sans（无衬线、笔画均匀）会让 $C(u)$ 等显得加粗突兀（2026-09-21 图2 字体审计）。
    plt.rcParams["mathtext.fontset"] = "cm"
    plt.rcParams["axes.unicode_minus"] = False
    plt.rcParams["svg.hashsalt"] = "owtda-cal-r1"
    # 2026-09-20 图片审计：消除 Type 3 字体。
    plt.rcParams["pdf.fonttype"] = 42
    plt.rcParams["ps.fonttype"] = 42
    plt.rcParams["svg.fonttype"] = "none"

    if args.check_fonts:
        print(f"CJK font resolved: {font}")
        return 0 if font else 1
    if font is None and not args.allow_missing_fonts:
        raise SystemExit(
            "no CJK-capable font found; rendering now would produce missing-glyph boxes.\n"
            f"  tried: {', '.join(CJK_CANDIDATES)}\n"
            "  install one (Ubuntu: sudo apt-get install -y fonts-noto-cjk) or pass "
            "--allow-missing-fonts for a review-only render."
        )

    jobs = [
        ("Figure2_alternative_geometry", fig2),
        ("Figure3_M0_type1_surface", fig3),
        ("Figure4_M1_deviation_surface", fig4),
        ("Figure5_H1_power_and_difference", fig5),
        ("FigureS1_H0_16x4_heatmap", fig_supplement_h0),
    ]
    only = set(args.only or [])
    for name, fn in jobs:
        if only and not any(k in name for k in only):
            continue
        save(fn(), name, INPUTS)
    return 0


if __name__ == "__main__":
    sys.exit(main())
