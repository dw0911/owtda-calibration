# METHOD SPEC v1.0（draft）— OW-TDA-CAL-R1

> 状态：**DRAFT**。冻结前参数逐项闭合；任何与基线计划冲突处以计划为准并登记。
> 稳定标识（stable_id）一经本文件登记即不可改名；配置/代码改变先升 generation，不改 stable_id。

## 1. 共享观测统计量（基线 §3.3，对所有校准器相同）

- 特征向量 `Y_i`（`R^p`，p=800 BPI / p=5,9 MOMENTS）。
- 候选集 `[ceil(0.15M), M-ceil(0.15M)]`；tie 容差 `64*eps64*max(1,|T_max|)`；
  最长 plateau → 最左 plateau → lower median 作为 `k̂`。
- 回归 `τ̂=(k̂-1/2)s+(W+1)/2`（对非重叠与重叠分别手工验证 §12.4 等式）。

## 2. M0：naive permutation

| 项 | 值 |
|---|---|
| stable_id | `M0_NAIVE_PERM_B999_V1` |
| 规则 | 每 replicate 独立均匀随机排列 `π_r`；按同一候选集/平方范数求 `T_{M,r}^π` |
| B / p | 999 / `(1+#{T_b^*≥T_obs})/1000` |
| RNG | 每个 `(data_unit_id,resample_index)` 一个 Generator，恰一次 `rng.permutation(M)` |

## 3. M1：冻结 DMB-R1 规则

| 项 | 值 |
|---|---|
| stable_id | `M1_DMB_R1_TRI_EXTIID_B999_V1` |
| 块长 | `q0=floor(W/s)+1`，`b_R1=max(q0, ceil(M^(1/3)))`（整数立方根，禁浮点） |
| 新息 | `e_1..e_{M+b-1}` iid N(0,1)；`ξ_i=b^(-1/2)*Σ_{j=0}^{b-1} e_{i+j}`，无 circular wrap、不截边、不再中心化 |
| bridge | `U*_M(k)=M^(-1/2)[Σ_{i≤k} ξ_i Z_i - (k/M) Σ ξ_i Z_i]`，`Z_i=Y_i-Ybar` |
| RNG | 每 unit 每 replicate 恰一次 `rng.standard_normal(M+b-1, dtype=float64)` |

## 4. BPI 特征（固定参数，基线 §5.1–5.2）

stable_id：`BPI_FIXED20_H01_SIGMA005_GAMMA1_V1`

| 参数 | 值 |
|---|---|
| 点云规则 | 多变量直接取窗口行；单变量窗口内 `(x_t,x_{t+3},x_{t+6})`；NaN/Inf 拒绝、`-0.0→+0.0`、字典序去重 |
| point_limit | 128（超出视为配置错误，禁止随机降采样） |
| VR | Vietoris–Rips，`F2`，H0+H1，maxdim=1，无数据驱动 thresh；删 infinite-death；<2 唯一点→零向量 |
| 坐标 cap c | N-AR=6；circle/figure-eight=2.5；PAMAP2 chest=6 g |
| 网格 | 20×20，步长 Δ=1/20，中心 `g_r=(r+1/2)Δ` |
| 核/权重 | σ=0.05；`w(v)=v`；坐标 `Z=sqrt(Δ^2)Σ v*(1/(2πσ^2))*exp(...)` |
| 拼接 | H0 后 H1，各 400 维，再 `/sqrt(2)` → **800 维** |
| 禁止 | 序列级 cap/距离尺度/核宽/网格/energy scale/通道删除估计 |

## 5. MOMENTS 特征（基线 §5.3）

stable_id：`MOMENTS_MEAN_COV_FROB_V1`

| 参数 | 值 |
|---|---|
| 尺度 a | N-AR/circle/figure-eight=1；PAMAP2=6 g |
| 特征 | d 均值 + d 对角协方差 + 字典序 `sqrt(2) S_{ab} (a<b)`；分母固定 n |
| 维数 | 2D→5 维；3D→9 维（欧氏范数 = mean² + S_F²） |
| 常数点云 | 返回实际均值 + 零协方差 |

## 6. 共同内层合同（基线 §6.1）

- B=999、p 网格 0.001、`p≤0.05 ⇔ exceed≤49`、tie 用 `>=`、p 不可能为 0。
- BPI 与 MOMENTS 同数据单元共享 M0 排列索引 / M1 新息张量（避免表征比较混入内层随机化差异）。
- observed statistic 在 M0/M1 间必须逐位一致（G1/G2）。

## 7. 与 G1 的关系

- 两份独立实现统计量绝对误差 ≤1e-12；候选/plateau/中位索引/raw-time 映射手工反例测试；
- permutation/multiplier 只改变校准过程，不改变 observed statistic；
- 若实现退化到核 U-statistic，暂停正式 MC（基线 §3.4）。

## 8. 开放项

- [ ] 每 stable_id 的 config_hash / code_file_manifest_hash 随实现批次登记；
- [ ] golden fixtures（seed→首个输出、CUSUM、CI、plateau）随实现批次建立。
