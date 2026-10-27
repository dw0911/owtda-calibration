"""Short-paper figure set (target: single-column A4, ~10 pages).

Figure A  alternative geometry (circle -> figure-eight; mean-shift control), compact canvas.
Figure B  BPI-only H0 rejection rates: 2 (M0/M1) x 2 (fixed-M / fixed-T) panels,
          four DGP x rho curves per panel, stride on a base-2 log axis.

Every value in Figure B is read from the canonical summary ``artifacts/tables/H0_ALL_112.csv``;
no result array is re-typed and no smoothing is applied. M0 and M1 use different y-axis
scales (0--1 vs 0--0.15), which the caption must disclose.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import struct
import sys
from datetime import UTC, datetime
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

CJK_CANDIDATES = (
    "SimSun",
    "STSong",
    "NSimSun",
    "Noto Serif CJK SC",
    "Source Han Serif SC",
    "Songti SC",
    "SimHei",
    "Microsoft YaHei",
    "Noto Sans CJK SC",
    "WenQuanYi Zen Hei",
    "PingFang SC",
    "Hiragino Sans GB",
)

PDF_METADATA = {"Creator": "paper/scripts/make_short_figures.py", "CreationDate": None, "ModDate": None}

ROOT = Path(__file__).resolve().parents[2]
FIG = ROOT / "artifacts" / "figures"
VER = ROOT / "artifacts" / "tables"
H0_SRC = "H0_ALL_112.csv"

H0 = None  # loaded in main() after argument parsing


def resolve_cjk_font() -> str | None:
    from matplotlib import font_manager

    available = {font.name for font in font_manager.fontManager.ttflist}
    for name in CJK_CANDIDATES:
        if name in available:
            return name
    return None


def f64(text: str) -> float:
    return struct.unpack(">d", bytes.fromhex(text[4:]))[0]


def read_csv(path: Path) -> list[dict]:
    with path.open(encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))
    return [{k.lstrip("\ufeff"): v for k, v in r.items()} for r in rows]


def budget_rows(budget: str) -> list[dict]:
    """Unique null cells for one budget regime, parsed from the canonical CSV."""
    out = []
    for r in H0:
        is_m = int(float(r["M_expected"])) == 192
        is_t = int(float(r["T"])) == 3120
        if budget == "M" and not is_m:
            continue
        if budget == "T" and not is_t:
            continue
        rho = f64(r["rho"]) if r["rho"].startswith("f64:") else float(r["rho"])
        out.append(
            {
                "dgp": r["DGP_family"],
                "rho": round(rho, 2),
                "s": int(float(r["stride"])),
                "feature": "BPI" if "BPI" in r["feature_id"] else "MOMENTS",
                "method": "M0" if "M0" in r["method_id"] else "M1",
                "rate": float(r["rejection_rate"]),
                "cls": r["classification"],
            }
        )
    return out


def write_meta(fname: str, outputs: dict[str, str]) -> None:
    meta = {
        "schema_version": 1,
        "kind": "FIGURE",
        "generated_at": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "script": "paper/scripts/make_short_figures.py",
        "script_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        "inputs": [H0_SRC],
        "input_sha256": {H0_SRC: hashlib.sha256((VER / H0_SRC).read_bytes()).hexdigest()},
        "outputs": outputs,
        "referenced_by": [
            p.relative_to(ROOT).as_posix()
            for p in sorted((ROOT / "paper").rglob("*.tex"))
            if fname in p.read_text(encoding="utf-8-sig", errors="replace")
        ],
    }
    (FIG / f"{fname}.meta.json").write_text(json.dumps(meta, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def save(fig, fname: str) -> None:
    outputs = {}
    for ext in ("pdf", "png"):
        path = FIG / f"{fname}.{ext}"
        kwargs = {"dpi": 320, "bbox_inches": "tight"}
        if ext == "pdf":
            kwargs["metadata"] = PDF_METADATA
        fig.savefig(path, **kwargs)
        outputs[path.name] = hashlib.sha256(path.read_bytes()).hexdigest()
    plt.close(fig)
    write_meta(fname, outputs)
    print("wrote", fname)


# ---------------------------------------------------------------------------
# Figure A: alternative geometry (compact)
# ---------------------------------------------------------------------------
def figure_a():
    # Same formal DGP as the long version: C(u)=(cos2pi u, sin2pi u), F(u)=(sin2pi u, sin4pi u),
    # noise 0.08*N(0,I2), shift +0.5*v with v=(1,0) as the illustrative direction.
    # Seed and sample size are kept so the plotted point clouds are identical to Figure 2.
    rng = np.random.default_rng(20260920)
    n = 64
    u1 = rng.uniform(0, 1, n)
    u2 = rng.uniform(0, 1, n)
    u3 = rng.uniform(0, 1, n)
    eta1 = rng.standard_normal((n, 2))
    eta2 = rng.standard_normal((n, 2))
    eta3 = rng.standard_normal((n, 2))
    v = np.array([1.0, 0.0])

    circle = np.column_stack([np.cos(2 * np.pi * u1), np.sin(2 * np.pi * u1)])
    eight = np.column_stack([np.sin(2 * np.pi * u2), np.sin(4 * np.pi * u2)])
    shifted = np.column_stack([np.cos(2 * np.pi * u3), np.sin(2 * np.pi * u3)]) + 0.5 * v

    pts_c1 = circle + 0.08 * eta1
    pts_f = eight + 0.08 * eta2
    pts_c2 = shifted + 0.08 * eta3

    fig, axs = plt.subplots(1, 2, figsize=(5.9, 2.45), constrained_layout=True)
    for ax in axs:
        ax.set_aspect("equal")
        ax.axhline(0, color="0.6", lw=0.6, ls=":")
        ax.axvline(0, color="0.6", lw=0.6, ls=":")
        ax.set_xlim(-1.45, 1.75)
        ax.set_ylim(-1.35, 1.35)
        ax.tick_params(labelsize=7.8, length=2.4, pad=1.5)
        ax.grid(alpha=0.18, lw=0.5)

    ax = axs[0]
    ax.scatter(pts_c1[:, 0], pts_c1[:, 1], s=7, c="#1f77b4", label="变点前：圆 $C(u)$")
    ax.scatter(pts_f[:, 0], pts_f[:, 1], s=7, c="#d62728", label="变点后：八字形 $F(u)$")
    ax.set_title("(a) 形状变化", fontsize=8.6)

    ax = axs[1]
    ax.scatter(pts_c1[:, 0], pts_c1[:, 1], s=7, c="#1f77b4", label="变点前：圆 $C(u)$")
    ax.scatter(pts_c2[:, 0], pts_c2[:, 1], s=7, c="#d62728", label="变点后：$C(u)+0.5v$")
    ax.annotate("", xy=(0.5, 0), xytext=(0, 0), arrowprops={"arrowstyle": "->", "lw": 1.1, "color": "k"})
    ax.text(0.25, 0.08, "$0.5$", ha="center", fontsize=7.8)
    ax.set_title("(b) 均值平移（$v=(1,0)$ 示例）", fontsize=8.6)

    for ax in axs:
        ax.legend(fontsize=7.8, loc="upper left", frameon=True, framealpha=0.85, edgecolor="none",
                  handletextpad=0.3, borderpad=0.25, labelspacing=0.25)
    return fig


# ---------------------------------------------------------------------------
# Figure B: BPI-only H0 rejection rates under both budgets and both calibrators
# ---------------------------------------------------------------------------
SERIES = (
    ("N_AR", 0.0, "N-AR, $\\rho{=}0$", "#1f77b4", "-", "o"),
    ("N_AR", 0.8, "N-AR, $\\rho{=}0.8$", "#4a90d9", "--", "s"),
    ("N_CIRCLE", 0.0, "N-CIRCLE, $\\rho{=}0$", "#d95f02", "-", "o"),
    ("N_CIRCLE", 0.8, "N-CIRCLE, $\\rho{=}0.8$", "#e8a33d", "--", "s"),
)


def figure_b():
    strides = (8, 16, 32, 64)
    fig, axs = plt.subplots(2, 2, figsize=(6.3, 4.6), constrained_layout=True,
                            sharex=True, sharey="row")
    budgets = (("M", "fixed-$M$（$M{=}192$）"), ("T", "fixed-$T$（$T{=}3120$）"))
    upper = {"M0": 1.0, "M1": 0.15}

    for i, method in enumerate(("M0", "M1")):
        for j, (budget, blabel) in enumerate(budgets):
            ax = axs[i, j]
            rows = [r for r in budget_rows(budget) if r["method"] == method and r["feature"] == "BPI"]
            ax.axhspan(0.035, 0.065, color="0.82", alpha=0.55, lw=0, zorder=0)
            ax.axhline(0.05, color="0.35", lw=0.8, ls="-.", zorder=1)
            for dgp, rho, label, color, ls, marker in SERIES:
                ys = []
                for s in strides:
                    hit = [r["rate"] for r in rows if r["dgp"] == dgp and r["rho"] == rho and r["s"] == s]
                    if len(hit) != 1:
                        raise SystemExit(f"non-unique H0 cell for {budget}/{method}/{dgp}/{rho}/{s}: {hit}")
                    ys.append(hit[0])
                ax.plot(strides, ys, ls=ls, marker=marker, ms=3.6, lw=1.1, color=color,
                        label=label, mec="white", mew=0.5, zorder=3)
            ax.set_xscale("log", base=2)
            ax.set_xlim(7, 72)
            ax.set_xticks(strides)
            ax.set_xticklabels([str(s) for s in strides])
            ax.minorticks_off()
            ax.set_ylim(0, upper[method])
            ax.tick_params(labelsize=8.0, length=2.4, pad=1.5)
            ax.grid(alpha=0.22, lw=0.5, axis="y")
            panel = "(a)" if (i, j) == (0, 0) else ("(b)" if (i, j) == (0, 1) else ("(c)" if (i, j) == (1, 0) else "(d)"))
            ax.set_title(f"{panel} {method}，{blabel}", fontsize=8.6)
            if i == 0:
                ax.set_xlabel("")
            if i == 1:
                ax.set_xlabel("步长 $s$", fontsize=8.4)
            if j == 0:
                ax.set_ylabel(f"{method} 拒绝率", fontsize=8.4)

    # 参考带说明置于 (c) 的空白右上区，避免在曲线密集处加箭头
    axs[1, 0].text(0.24, 0.82, "灰带：实用带 $[0.035,0.065]$；点划线：$0.05$",
                   transform=axs[1, 0].transAxes, fontsize=7.9, color="0.25", va="center")

    handles, labels = axs[0, 0].get_legend_handles_labels()
    fig.legend(handles, labels, loc="outside lower center", ncol=4, fontsize=8.0,
               frameon=False, handlelength=2.0, columnspacing=1.2)
    return fig


def main(argv: list[str] | None = None) -> int:
    global H0
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check-fonts", action="store_true")
    parser.add_argument("--allow-missing-fonts", action="store_true")
    parser.add_argument("--only", nargs="*", default=None)
    args = parser.parse_args(argv)

    font = resolve_cjk_font()
    if font:
        plt.rcParams["font.serif"] = [font, "Times New Roman", "DejaVu Serif"]
        plt.rcParams["font.family"] = "serif"
    plt.rcParams["mathtext.fontset"] = "cm"
    plt.rcParams["axes.unicode_minus"] = False
    plt.rcParams["pdf.fonttype"] = 42
    plt.rcParams["ps.fonttype"] = 42

    if args.check_fonts:
        print(f"CJK font resolved: {font}")
        return 0 if font else 1
    if font is None and not args.allow_missing_fonts:
        raise SystemExit("no CJK-capable font found; pass --allow-missing-fonts for a review-only render")

    H0 = read_csv(VER / H0_SRC)
    jobs = [
        ("FigureA_alternative_geometry_short", figure_a),
        ("FigureB_BPI_H0_panels", figure_b),
    ]
    only = set(args.only or [])
    for name, fn in jobs:
        if only and not any(k in name for k in only):
            continue
        save(fn(), name)
    return 0


if __name__ == "__main__":
    sys.exit(main())
