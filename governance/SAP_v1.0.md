# SAP v1.0（FROZEN）— OW-TDA-CAL-R1 统计分析计划

> 状态：**FROZEN**（2026-09-10 B14a 共同冻结；此后只读，变更走 `AMENDMENT_REGISTRY.jsonl`）。
> 对应基线 §10–§14；estimand registry 在 ANALYSIS spec 前生成（基线 §15.2）。

## 1. 主估计与单格汇总（基线 §10.1）

- `π̂_cj=K_cj/2500`；每格必须完整保留 2,500 trial（不允许 eligible-only 分母或新 seed 补位）。
- 每格报告：K/2500、拒绝率、无连续性修正 **Wilson 95% CI**（90% z=1.6448536269514722；
  95% z=1.959963984540054）、Clopper–Pearson exact 95% CI（辅助，不参与分类）、
  `F̂_p(u)-u` for u∈{.01,.025,.05,.10}、0.95 临界值分布、运行诊断。
- 零 diagram/全常数特征：`T_obs=0, p=1, reject=0`（total function）。

## 2. 主假设与 Claim 映射

| # | 量 | 边界 θ0 | Claim | 条件 |
|---|---|---|---|---|
| P1 | `D^M_OV = ½Σ_g(π^M_{g,0,s16,M0}-π^M_{g,0,s64,M0})`（ρ=0，两 DGP 等权） | 0.10 | C2 | 单侧 |
| P2 | `D^T_ST` 同构（fixed-T，预算固定） | 0.10 | C3 | 单侧 |
| P3 | `D_CONS = 0.05-½Σ_g π^M_{g,0,s64,M1}` | 0.01 | C5 | 单侧 |

- 效应修饰 `I_ρ=D_{0.8}-D_0`（报告，无 SUPPORTED 标签）；MOMENTS 对应量与 M0–M1 配对差 = 次级估计。
- ρ=0.8 不混入因果口径；逐 DGP 差与 CI 同时报告但不作两 DGP 普遍成立断言。

## 3. 整簇 bootstrap 与 Holm（基线 §10.6）

- H0 分层（N-AR/N-CIRCLE 独立）从 2,500 cluster_id 有放回抽 2,500，携带全部 ρ/stride/budget/method；
- P1–P3：`B_A=10000`，p=(1+#{θ̂*_b-θ̂ ≥ θ̂-θ0})/10001；basic 95% CI
  `[2θ̂-q_.975(θ̂*), 2θ̂-q_.025(θ̂*)]`；
- 分位数一律 **nearest-rank** `q_α=x*_{(⌈αB⌉)}`（2,000 次时取第 50/1,950 位）；
- Holm step-down `p^H_(i)=min{1, max_{j≤i}(4-j)p_(j)}`，nominal 0.05；宣称"渐近/近似控制"，
  不宣称有限样本精确 FWER。分析 bootstrap 用冻结 `analysis_bootstrap_root_key`，不复用方法 RNG。

## 4. 校准分类（基线 §10.7）

等价带 `E=[0.035,0.065]`；逐 `cell × feature × method`：
- 90% Wilson CI ⊆ E → `POINTWISE_PRACTICALLY_CALIBRATED`
- 95% Wilson CI 上界 <0.035 → `MATERIAL_CONSERVATISM`
- 95% Wilson CI 下界 >0.065 → `MATERIAL_ANTI_CONSERVATISM`
- 其他 → `BOUNDARY_OR_INDETERMINATE`

CI 覆盖 0.05 只支持"未检出偏差"；禁止统计"通过格数"或由 pointwise 标签推全域。

## 5. 依赖放大（基线 §11）

- 每 replicate 存 `a_r=M^-1ΣY`、`q_r=M^-1Σ‖Y‖²`；
  分子 `tr̂(Ω)=M/(R-1) Σ‖a_r-ā‖²`；分母二阶 U-统计无偏 `D̂_U=q̄-[‖Σa_r‖²-Σ‖a_r‖²]/[R(R-1)]`；
- `Â^tr=D̂^-1×分子`；窗口均值实现须恢复 T3 解析值；退化处理见基线 §11。

## 6. H1 功效/定位（基线 §12）

- 每 cell 报告 nominal power、对应 H0 实际 Type-I、**size-standardized power**
  （用匹配 H0 observed 的经验 0.95 分位数 `ĉ_0.95=T^{(⌈0.95(R0+1)⌉)}`）、raw-index MAE、归一化 raw-index error、
  按 M0/M1 的 detection-and-localization joint success；
- H1 的 `source_null_phase_seal_hash` 必须绑定真实参与 size-standardization 的 NULL phase seal；
  特征/方法的 config/registry hash 一并 join，禁止只核对 (ρ,s,W,T,M)；
- 方法未获 `POINTWISE_PRACTICALLY_CALIBRATED` 不得经 nominal power 宣称更强；
- size-adjusted power 对 M0/M1 相同（observed statistic 相同），只报告一次，用于比较 feature 信息量；
- 定位 `τ̂=(k̂-1/2)s+(W+1)/2`；真连续边界 `τ_true=τ+0.5`；两个手工等式
  (64,64,192,96,12288,6144)→6144.5 与 (64,16,192,96,3120,1560)→1560.5 必须通过。

## 7. REAL estimands（基线 §13.5）

- 维度：边际决定率 r 与联合端点 J 按 feature×method×stride；pair/all-three agreement 按 pair；
  位置命中 L 与 distance 按 feature×stride（M0/M1 定位一致则去重一次）。
- 汇聚：受试者内任务均值 → 准入受试者等权平均；距离用受试者内中位数 + 跨受试者 IQR；
  主文列全 9 名 eligibility 表 + LOSO min/max；subject bootstrap 2,000（`resample_role=REAL_SUBJECT`）。
- distance 阈值：`d_s ≤ 2` 秒命中。全部真实距离只使用 seconds 字段。

## 8. bootstrap plan 注册（基线 §15.2，分析 spec 前闭合）

P1_H0_PRIMARY_V1 / P2_H0_PRIMARY_V1 / P3_H0_PRIMARY_V1（10000 次）；
H0_DIAGNOSTICS_ALL_V1、H1_NULL_QUANTILE_ALL_V1、H1_ALT_POWER_ALL_V1、REAL_ALL_ENDPOINTS_V1（2000 次）。
各 plan 的 resample_role/stratum/ordering 冻结于 ANALYSIS_SPEC，届时生成 `ESTIMAND_SPEC_REGISTRY_v1.json`。

## 9. 分析失败语义

- CI 过宽 → `INCONCLUSIVE`，禁止追加 MC 追过；- coverage 低 → 按预注册降级，禁下调准入线；
- Claim 状态机：`UNTESTED/SUPPORTED/NOT_SUPPORTED/INCONCLUSIVE/DESCRIPTIVE_ONLY/INVALIDATED/SUPERSEDED`，append-only。
