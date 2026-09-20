# method_overview — 方法概要（面向代码读者）

> 论文方法的**权威定义**在 `paper/sections/02_method.tex` 与 `03_theory.tex`；治理规格在
> `governance/METHOD_SPEC_v1.0.md`、`PROTOCOL_v1.0.md`。本文件只做"代码在哪、概念对应什么"的索引。

## 1. 对象链（与代码模块的对应）

```text
原序列 (DGP)               src/owtda_cal/dgp.py            N-AR / N-CIRCLE（含 H1 变体）
  └─ 重叠窗口               src/owtda_cal/scan.py           窗口数 M = floor((T-W)/s) + 1
       └─ 点云              src/owtda_cal/pointcloud.py     时延嵌入 / 圆形嵌入
            └─ 持续同调 PH   src/owtda_cal/ph.py             ripser 包装（固定精度分层）
                 └─ 固定表示  src/owtda_cal/features.py      BPI_FIXED20（800 维）与 MOMENTS（均值-协方差）
                      └─ 扫描统计量 src/owtda_cal/scan.py    最大扫描统计量 + 确定性平台选点
                           ├─ 朴素置换 M0   src/owtda_cal/calibrate.py  B=999，p=(1+exceed)/1000
                           └─ 依赖乘子 M1   src/owtda_cal/calibrate.py  三角协方差核，带宽 b
```

## 2. 三个"为什么"

1. **为什么会失效**：窗口级置换检验要求可交换性；重叠窗口使窗口统计量之间存在依赖（相邻窗口共享观测），
   朴素置换保留的是**边际**结构而不是真实长期协方差 → `Ω = qΓ₀ ≠ Γ₀`（`W = qs, q > 1`）。
   精确反例与解析放大见 `paper/sections/03_theory.tex`（T1–T5）。
2. **为什么用双预算**：fixed-M（M=192，重叠率随 s 变化）与 fixed-T（T=3120，s 变化时 M 变化）
   把"重叠率"与"观测预算"两个因素分离；两者共享 s=16、T=3120、M=192 的同一组科学配置。
3. **为什么比较 BPI 与 MOMENTS**：两者是同一流水线上不同**表示**；形状变化与均值平移是单时点边际
   均值-协方差匹配的两种备择，表现为镜像的功效选择性（论文 §6）。

## 3. 校准器（已冻结）

| 代号 | 名称 | 规则 |
|---|---|---|
| M0 | `M0_NAIVE_PERM_B999_V1` | 窗口级朴素置换，`B=999`，`p = (1 + exceed) / 1000`，`reject ⇔ exceed ≤ 49` |
| M1 | `M1_DMB_R1_TRI_EXTIID_B999_V1` | 依赖乘子（DMB-R1 冻结规则，三角协方差 `Cov(ξ_i, ξ_{i+h}) = (1 - |h|/b)_+`），同 `B` 与 `p` 规则 |

## 4. 唯一数据流（禁止手工填数）

```text
sealed trial JSON → validated canonical ledger → canonical summaries
→ tables/figures → manuscript_values → manuscript consistency check
```

对应入口：`scripts/analyse_h0.py`（H0 汇总）、`release/analysis/scripts/reanalyse_h1.py`（H1 重分析）、
`scripts/bootstrap_primary_contrasts.py`（P1–P3）、`scripts/build_tables.py`、`scripts/build_figures.py`、
`scripts/verify_release.py`（一致性）。

## 5. 复现分级（与 RUNBOOK 对应）

R0 单测/攻击 → R1 解析反例 → R2 盲 smoke → R3 正式 L2/L3 → R4 独立环境重建。
本仓库的 `scripts/verify_release.py --level quick` 覆盖 R0–R2 的可核验部分；Level 2/3 见 RUNBOOK。
