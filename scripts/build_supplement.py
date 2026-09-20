"""生成补充材料 supplement.tex（S1-S5）。

S1：完整 112 行 H0 拒绝率 + Wilson 区间 + 分类（来自 H0_ALL_112.csv）；
S2：完整 16 行 H1 功效 / 临界值 / MAE / 联合成功率（来自 H1_ALL_16_GEOMETRY_COMPLETE.csv）；
S3：主对比与表示差自助法的完整规格（文字，与 04_protocol 一致）；
S4：完整 16×4 热图（FigureS1）；
S5：代码与数据可用性。

用法：
  python scripts/build_supplement.py            # 生成 paper/supplement/supplement.tex
"""
from __future__ import annotations

import csv
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
ART = REPO / "artifacts"
H0 = ART / "tables" / "H0_ALL_112.csv"
H1 = ART / "tables" / "H1_ALL_16_GEOMETRY_COMPLETE.csv"
OUT = REPO / "paper" / "supplement" / "supplement.tex"

CLASS_ZH = {
    "POINTWISE_PRACTICALLY_CALIBRATED": "实用校准",
    "MATERIAL_CONSERVATISM": "实质保守",
    "MATERIAL_ANTI_CONSERVATISM": "实质反保守",
    "BOUNDARY_OR_INDETERMINATE": "边界或未定",
}

DGP_ZH = {"N_AR": "N-AR", "N_CIRCLE": "N-CIRCLE"}
FEAT = {"BPI_FIXED20_H01_SIGMA005_GAMMA1_V1": "BPI", "MOMENTS_MEAN_COV_FROB_V1": "MOMENTS"}
METHOD = {"M0_NAIVE_PERM_B999_V1": "M0", "M1_DMB_R1_TRI_EXTIID_B999_V1": "M1"}
SCEN_ZH = {"shape_change": "形状变化", "mean_shift": "均值平移"}


def feat(s: str) -> str:
    return next((v for k, v in FEAT.items() if k in s), s)


def meth(s: str) -> str:
    return next((v for k, v in METHOD.items() if k in s), s)


def s1_rows() -> list[str]:
    rows = list(csv.DictReader(H0.open(encoding="utf-8-sig")))
    lines = []
    for r in rows:
        dgp = DGP_ZH[r["DGP_family"]]
        rho = f"{float(r['rho']):g}"
        s = int(float(r["stride"]))
        T = int(float(r["T"]))
        M = int(float(r["M_expected"]))
        f = feat(r["feature_id"])
        m = meth(r["method_id"])
        rate = float(r["rejection_rate"])
        lo, hi = (float(x) for x in r["wilson95"].strip("[]").split(","))
        cls = CLASS_ZH.get(r["classification"], r["classification"])
        lines.append(
            f"{dgp} & {rho} & {s} & {T} & {M} & {f} & {m} & {rate:.4f} & "
            f"[{lo:.4f},{hi:.4f}] & {cls}\\\\"
        )
    return lines


def s2_rows() -> list[str]:
    rows = list(csv.DictReader(H1.open(encoding="utf-8-sig")))
    lines = []
    for r in rows:
        scen = SCEN_ZH[r["scenario_id"]]
        rho = f"{float(r['rho']):g}"
        s = int(float(r["stride"]))
        f = feat(r["feature_id"])
        p = float(r["size_standardized_power"])
        nmae = float(r["normalized_mae"])
        j0 = float(r["M0_joint_success"])
        j1 = float(r["M1_joint_success"])
        nom0 = float(r["M0_nominal_power"])
        nom1 = float(r["M1_nominal_power"])
        lines.append(
            f"{scen} & {rho} & {s} & {f} & {p:.5f} & {nmae:.5f} & "
            f"{j0:.4f} & {j1:.4f} & {nom0:.4f} & {nom1:.4f}\\\\"
        )
    return lines


def build() -> str:
    s1 = "\n".join(s1_rows())
    s2 = "\n".join(s2_rows())
    tpl = r"""\documentclass[UTF8,zihao=-4]{ctexart}
\usepackage[a4paper,margin=2.2cm]{geometry}
\usepackage{amsmath,amssymb}
\usepackage{booktabs,array}
\usepackage{longtable}
\usepackage{graphicx}
\usepackage[hidelinks]{hyperref}
\usepackage{url}

\setlength{\parindent}{2em}

\title{补充材料：重叠窗口拓扑扫描的有限样本校准边界}
\author{}
\date{}

\begin{document}
\maketitle

正文引用本补充材料时按 S1--S5 编号。所有数值与正文及冻结的 canonical 汇总文件一致。

\section*{S1 完整 112 行零假设结果}

下表给出 28 个唯一零假设配置 $\times$ 2 表示 $\times$ 2 方法共 112 个逐格评价单元的
拒绝率（每格 $n=2500$）、95\% Wilson 区间（无连续性修正）与四类校准状态。
列含义：DGP 为数据生成过程；$\rho$ 为原序列依赖；$s$ 为步长；$T$、$M$ 为观测长度与窗口数；
分类取实用校准 / 实质保守 / 实质反保守 / 边界或未定。本表的分类列即正文第 5.2 节所称的
完整状态转换清单。

\begingroup
\footnotesize
\begin{longtable}{llrlrlrrc c}
\toprule
DGP & $\rho$ & $s$ & $T$ & $M$ & 表示 & 方法 & 拒绝率 & 95\% Wilson & 分类\\
\midrule
\endhead
__S1_ROWS__
\bottomrule
\end{longtable}
\endgroup

\section*{S2 完整 16 行备择结果}

下表给出两个场景 $\times$ 4 条件 $\times$ 2 表示共 16 个“条件--表示”单元的
尺寸校正功效、归一化定位误差、联合成功率与名义功效（每格 $n=1600$，临界秩 2376）。
列含义：$\rho$ 为原序列依赖；$s$ 为步长；$J_0$、$J_1$ 分别为 M0、M1 的联合成功率；
$\beta_0$、$\beta_1$ 分别为 M0、M1 的名义功效。

\begingroup
\footnotesize
\begin{longtable}{llrlrrrrrr}
\toprule
场景 & $\rho$ & $s$ & 表示 & 尺寸校正功效 & nMAE & $J_0$ & $J_1$ & $\beta_0$ & $\beta_1$\\
\midrule
\endhead
__S2_ROWS__
\bottomrule
\end{longtable}
\endgroup

\section*{S3 主对比与表示差自助法的完整规格}

\textbf{主对比 P1--P3}：使用 10{,}000 次按数据生成过程分层的整簇自助法；同一主重复编号下
的全部相关条件、表示和方法随簇共同重采样。单侧自助 $p$ 值按加一规则
$p=(1+\#\{\text{尾部}\})/10001$ 计算，三个单侧 $p$ 值经 Holm step-down 校正。
边际 95\% 区间为最近秩（nearest-rank）分位数定义的 basic bootstrap interval。

\textbf{表示差 $\Delta$}：通过两层整簇自助法估计，每层 2000 次。重采样单位为主复制：
零假设层按 N-CIRCLE 主复制整簇重采样以重算经验临界值，备择层按备择主复制整簇重采样以重算功效；
两层分别独立重采样。BPI 与 MOMENTS 使用同一重采样索引成对移动；四个 $(\rho,s)$ 条件
在每个场景内先计算各自的 BPI 减 MOMENTS 功效差，再等权平均得到场景差。
区间采用最近秩定义的 2000 次百分位区间（$2.5\%$ 与 $97.5\%$ 分位数）。

\section*{S4 完整 16$\times$4 热图}

图~\ref{fig:s1}给出 16 个条件（DGP$\times\rho\times s$）$\times$ 4 列
（BPI/M0、BPI/M1、MOMENTS/M0、MOMENTS/M1）的完整逐格 I 类错误率，两个面板分别对应
fixed-$M$ 与 fixed-$T$。色标 $[0,1]$，格内标注四位小数。

\begin{figure}[ht]
\centering
\includegraphics[width=0.95\textwidth]{../../artifacts/figures/FigureS1_H0_16x4_heatmap.pdf}
\caption{完整 16$\times$4 逐格 I 类错误率热图。两面板分别为 fixed-$M$（$M=192$）与
fixed-$T$（$T=3120$）；16 行按 DGP$\times\rho\times s$ 排列，4 列为
BPI/M0、BPI/M1、MOMENTS/M0、MOMENTS/M1。}\label{fig:s1}
\end{figure}

\section*{S5 代码与数据可用性}

复现本文结果的代码、配置、种子清单、完整逐格数据与全部生成脚本由仓库提供：

\begin{itemize}
\item 代码仓库：\url{https://github.com/dw0911/owtda-calibration}
\item 本稿对应 git 标签 \texttt{v1.1.0-paper}
\item 全部合成数据由该版本代码与固定随机种子生成；独立数据 DOI 尚在建立中，未作为已提供材料列出
\end{itemize}

\end{document}
"""
    return tpl.replace("__S1_ROWS__", s1).replace("__S2_ROWS__", s2)


def main() -> int:
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(build(), encoding="utf-8")
    print(f"wrote {OUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
