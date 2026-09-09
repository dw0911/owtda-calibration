# DMB-R1 Prior Evidence Summary（L1 历史证据披露）

> 本项目 OW-TDA-CAL-R1 开始前，旧证据线 DMB-R1（`bpi-scan` / BPI scan 项目）已于
> 2026-09-09 终止归档。本文档按 OW-TDA-CAL-R1 计划 §2.1 登记本代必须披露的旧证据要点。
> 本代唯一权威旧材料目录：`external_prior_evidence/DMB_R1/`（完整 25 对象由终止归档 zip 物化）。

## 0. 权威引用

| 项 | 值 |
|---|---|
| 终止分类 | `NO_IMPLEMENTATION_DEFECT`（设计层事实缺陷；代码线审计零实现缺陷） |
| R4/E2 准入 | `NOT_REACHED`（E1-DEV-DMB FAIL 阻断） |
| 终止归档 | `BPI-DMB-R1-TERMINAL-CLOSURE-20260909.zip`（SHA256 `38790d48a044bde41fd21bc31c18142b19e6decd2398cf1c3f3b8640f9df933d`） |
| 终止记录 | `DMB-R1-TERMINATION__20260909T105736Z__e0ae4791.json` |
| 交接文档 | `HANDOFF_DMB-R1_20260909.md`（随 commit `419930a`） |

## 1. 必须披露的旧证据数值（L1）

- `s16`（重叠/步长 16 短窗）下 naive permutation Type-I 约为 **0.74–0.83**（严重反保守）；
- `s64`（非重叠）下 naive 约为 **0.03–0.07**；
- `s16` 下 DMB 约为 **0.045–0.075**；
- `s64` 下 DMB 约为 **0.010–0.025**（接近名义水平但偏向保守）；
- B5 code-line audit **未发现实现缺陷**（NO_IMPLEMENTATION_DEFECT）。

## 2. 证据地位声明（强制）

上述数字均属 **假设形成与历史开发证据（L1）**：
- 不得进入本代 L2/L3 主估计；
- 不得与 L2 sealed ledger 拼接计算；
- 只可在引言/补充材料中说明研究动机；
- `s16 DMB 0.045–0.075` 与 `s64 naive 0.03–0.07` 之类的表现不作"注册网格通过"引用。

## 3. 关键事实记录（供 R2/本代假设生成参考）

- E1-DEV-DMB 在 candidate `23b57363` 上 FAIL：`N_IID_s64` 格拒绝率 0.010 < 注册带下界 0.015（7/8 格）；
- G1-BATCH-INTEGRITY 与 G1-OVERLAP 为**保留的已知 FAIL**（审计确认属设计，非实现缺陷）；
- naive 反保守与窗口重叠相关的**因果机制主张已被删除**（G1-OVERLAP 注册 FAIL），仅作开发发现；
- 递归多变更点 FWER、E2 功效/拓扑增益/真实外推均无当前正式证据或未授权。

## 4. 物化计划

后续批次将把终止归档 zip 中 25 对象解出至 `external_prior_evidence/DMB_R1/`，核验
`SHA256SUMS.txt` 与归档 sidecar 后生成 `archive_manifest.json`。本摘要自身属 L1 登记，
不再改写。
