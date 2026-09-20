# Correction Note — 2026-09-18（已由下游分析 supersede）

**status: SUPERSEDED_BY `analysis/H1_REANALYSIS.json`**

本文记录 ledger 字段约定与 Plan §12.3 定义的偏差；实际数值分析已按正确公式在
`analysis/H1_REANALYSIS.json` 中重算，本文仅作历史说明，不得用于正式引用。

## 1. true_boundary / localization error 的半采样点约定

ledger 中：

- `true_boundary_synthetic` 记录的是 `τ = T//2`（例如 6144），而 Plan §12.3 的
  真实连续边界是 `τ_true = τ + 0.5`（例如 6144.5）。
- `localization_error_synthetic = |τ̂ − τ|`，而登记定义为 `|τ̂ − τ_true|`。

其中 `τ̂ = (k̂ − ½)s + (W + 1)/2`，`k̂` 取 `estimated_change_index`（**窗口切分索引**，
不是原始采样时间，必须先映射）。

## 2. 修正后的正确算法（现行）

逐 trial 从原始 `k̂` 一次性重算：

```
estimate = (k̂ - .5) * stride + (W + 1) / 2
truth    = T // 2 + .5
error    = |estimate - truth|
```

**绝对误差相对旧字段可能增加，也可能减少；变化幅度不超过 0.5。**
因此不能以"统一给 MAE 减去 0.5"来修正——旧版本文的表述已被本条取代。

实证（W=64, s=16, T=3120）：

| k̂ | τ̂ | 旧误差 | 正确误差 |
|---|---|---|---|
| 94 | 1528.5 | 31.5 | 32.0 |
| 96 | 1560.5 | 0.5 | 0.0 |
| 98 | 1592.5 | 32.5 | 32.0 |

最后一行会从"不满足误差 ≤ W/2"变为"满足"，故 joint success 成员会变化；
`H1_REANALYSIS.json` 已记录每格的 `joint_membership_changed`，漏检样本保留在分母。

## 3. 影响范围

- **不影响**：p 公式、reject 公式、nominal power、H0 Type-I。
- **影响**：localization MAE / normalized MAE、joint success（均已在
  `analysis/H1_REANALYSIS.json` 中按正确方式重算）。

## 4. size-standardized power 的 critical value（后续修正）

所有 H1 cell-feature 统一使用 `ceil(0.95 * (2500 + 1)) = 2376` 阶统计量；
相较早期 `percell_analysis.json` 有 5 个格的 size-standardized power 发生很小变化
（例如 `c_0.95` 由 0.101578 修正为 0.10174494934738995）。这属于分析精度修复，
不涉及重新执行 H0/H1。

## 5. H1 admission 的 requested_phase（已知小瑕疵）

`h1_run/FORMAL_ADMISSION.json` 的 `requested_phase` 误写为 `H0`（实际生产 phase 为
`ALT`）。已追踪确认：certificate 绑定 ALT expected hash、H1 RUN seal 绑定正确
ALT index、H1 PHASE seal 明确为 ALT、parent 精确指向 H0 PHASE seal、51,200 行计数
完全匹配 ALT plan → 判定为 metadata/governance inconsistency，**非 trial 身份错误**，
不触发重跑；后续 H1 admission 应正确写 `requested_phase=ALT`。
