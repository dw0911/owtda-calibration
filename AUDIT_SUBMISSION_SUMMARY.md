# OW-TDA-CAL R1 完整成果汇总（提交审计）

**版本：2026-09-19** · **状态：A/B/C 核心审计通过，H0/H1 正式运行保留，进入论文分析完成阶段**

## 0. 总裁定

| Gate | 结果 |
|---|---|
| A 科学/分析正确性 | **PASS**（无要求重跑数据生成、拓扑特征、p 值的证据） |
| B trial/身份完整性 | **PASS**（plan == cert == RUN seal == PHASE seal，H1 parent 正确） |
| C 独立复算 | **PASS**（流式审计 pass=true、critical_failures=[]） |
| H0/H1 重跑 | **NO** |

## 1. 正式运行（已保留）

| Phase | evaluation | data | feature | run_seal_hash | phase_seal_hash |
|---|---|---|---|---|---|
| H0/NULL | 280,000 | 70,000 | 140,000 | `241c2e95…` | `3913d436…` |
| H1/ALT | 51,200 | 12,800 | 25,600 | `c5ecaead…` | `d1e4a8f7…`（parent=H0 seal） |
| **合计** | **331,200** | **82,800** | **165,600** | — | — |

分片（3.37GB）位于 `artifacts/ledgers/`，逐字节 hash 与 seal 一致。

## 2. 主结果（全部 SUPPORTED）

### H0 逐格校准（112 格 × Wilson 分类）

| 表示/方法 | 实用校准 | 实质保守 | 实质反保守 | 边界 |
|---|---|---|---|---|
| BPI/M0 | 7 | 0 | 20 | 1 |
| BPI/M1 | 5 | 10 | 7 | 6 |
| MOMENTS/M0 | 6 | 0 | 20 | 2 |
| MOMENTS/M1 | 1 | 12 | 7 | 8 |

### P1–P3 主对比（10,000 registered bootstrap + Holm，全部 SUPPORTED）

| 对比 | 估计 | 95% basic CI | 阈值 |
|---|---|---|---|
| P1 fixed-M overlap | 0.5354 | [0.5210, 0.5494] | 0.10 |
| P2 fixed-T stride | 0.5330 | [0.5194, 0.5462] | 0.10 |
| P3 DMB conservatism | 0.0266 | [0.0224, 0.0308] | 0.01 |

### H1 两场景 size-standardized power 差（2000 registered bootstrap）

| 场景 | Δ | 95% CI |
|---|---|---|
| shape change（BPI−MOMENTS） | +0.9380 | [0.9297, 0.9461] |
| mean shift（BPI−MOMENTS） | −0.9463 | [−0.9534, −0.9384] |

**核心结论**：M0 在 overlap 下严重反保守（4.7%–97.6%）；M1 接近 nominal 但有保守/反保守边界；BPI 对 shape 强、MOMENTS 对 mean 强（镜像、CI 远离 0）。

## 3. 文件结构（Plan §20 规范态）

```
owtda-calibration/
├── src/owtda_cal/  (48 .py)  ├── tests/ (70 .py)
├── configs/  ├── governance/ (174 文件：registry + 分析层 + ACTIVE index)
├── scripts/ (19)  ├── audit/
├── artifacts/
│   ├── ledgers/ (3.37GB)  ├── seals/ (8)  ├── summaries/ (23)
│   ├── tables/ (17)  ├── figures/ (13)  └── preflight/
├── manuscript/ (main.tex + 10 sections)
└── release/ (35 文件)
```

分析身份链：`ANALYSIS_INPUT_MANIFEST(1f1c7492…) → analysis_id(18797cfe…) → RESOLVED_BOOTSTRAP_PLAN_INDEX → bootstrap`，全可重放。

## 4. 论文起草状态

- 图表：Table 1–5 + Figure 3/4/7（PDF/SVG/PNG + 可溯源 `.meta.json`）
- 正文：main.tex + 10 sections（00–09），Methods/Theory/Protocol/Results/Discussion 全实质内容
- 一致性检查（WP-W4）：**ALL_MATCH**（正文 30 项数值与 canonical summary 一致）

## 5. 如实保留的未闭合项（均不阻断）

1. 3.38GB 原始账本未入交付 ZIP（仅 hash + 源路径，逐行结论依赖本地流式核验报告）；
2. `isolation_proof_refs` 为空（governance 无隔离证明对象，已显式标注 NOT GENERATED）；
3. C4（T4 理论 Ω≠Γ₀）状态 `UNTESTED`，正文已降级为 proposition；
4. C8（REAL/PAMAP2）状态 `REAL_OMITTED_BY_DATA_GATE`，正文 07_real 为条件节；
5. Figure 1/2/5/6 + 文献 bibliography 待补充（不阻塞主线）。

## 6. 历史与过程稿

100+ 过程稿目录（r4 时代 + 反复试跑产物）已归档至 `F:\BPI\bpi\archive\`，不在提交范围。
