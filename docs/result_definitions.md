# result_definitions — 术语与量定义

## 1. 计数与规模

| 量 | 定义 | 值 |
|---|---|---|
| H0 唯一格 | `(DGP, ρ, s, T, M)` 的唯一组合 | 28 |
| H0 评价单元 | `(格, 表示, 方法)` | **112** |
| H0 replicate | 每一评价单元的 master replicate 数 | 2,500 |
| H1 cell-feature | `(场景, 表示, s, ρ)` | **16** |
| H1 replicate | 每一 cell-feature | 1,600 |
| 重采样 | 每一评价的置换/乘子次数 | B = 999 |

## 2. 统计量

| 量 | 定义 | 代码 |
|---|---|---|
| 拒绝率 | `rejects / n` | `results/canonical/H0_POINTWISE.json` |
| Wilson 90% / 95% | Wilson score 区间（z = 1.6449 / 1.9600），用于实用等效性与保守/反保守分类 | `scripts/analyse_h0.py` |
| M0 逐格 Type-I 范围 | 全部 M0 单元的拒绝率最小/最大值 | `scripts/verify_release.py`（INFO 输出） |
| P1/P2/P3 | 主对比：fixed-M 重叠失真 / fixed-T stride 对比 / DMB 非重叠端保守性 | `results/bootstrap/P1_P3_BOOTSTRAP_SUMMARY.json` |
| `p_raw_one_sided` | `(tail_count + 1) / (B + 1)`（加一规则，禁止 p = 0） | 同上 |
| `p_holm` | Holm step-down（3 个对比） | 同上 |
| basic 95% CI | `[2·est − q₀.₉₇₅, 2·est − q₀.₀₂₅]`（nearest-rank） | 同上 |
| size-standardized power | 用对应 H0 格的经验临界值（秩 **2376**）标准化的功效 | `results/canonical/H1_REANALYSIS.json` |
| 定位误差 | `|τ̂ − τ_true|`，`τ̂ = (k̂ − ½)s + (W+1)/2`，`τ_true = T//2 + ½` | 同上 |
| joint success | 检出 ∧ 定位（`|误差| ≤ W/2`）；漏检保留在分母 | 同上 |

## 3. 四分类（逐格校准状态）

| 类别 | 含义 |
|---|---|
| `POINTWISE_PRACTICALLY_CALIBRATED` | 点态实用校准（90% Wilson 落在 `[0.035, 0.065]` 等价带内） |
| `MATERIAL_CONSERVATISM` | 实质保守（95% Wilson 低于名义侧） |
| `MATERIAL_ANTI_CONSERVATISM` | 实质反保守 |
| `BOUNDARY_OR_INDETERMINATE` | 未满足以上三类判据的剩余状态 |

> 判据的权威表述在 `governance/SAP_v1.0.md` 与 `paper/sections/04_protocol.tex`；
> 计数视图见 `artifacts/tables/Table4_calibration.csv`。

## 4. 禁止的表述（论文与文档均适用）

- "所有重叠窗口必然失去交换性"；"重叠必然导致 Type-I 膨胀"；"拓扑映射制造了时间依赖"；
  "A_Φ 单独决定多维扫描 Type-I"；"DMB 普遍恢复名义水平"；"BPI 在真实数据上普遍优于标量方法"；
  "固定参数 BPI 与旧自适应 BPI 是同一数值方法"。
- 审计流程不是科学贡献；旧代 DMB-R1 结果不得与本代 L2 拼接。
