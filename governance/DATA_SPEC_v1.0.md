# DATA SPEC v1.0（draft）— OW-TDA-CAL-R1 数据生成与分析范围

> 状态：**DRAFT**。DGP/矩阵/规模的 machine 身份（data_model_config_hash 等）随实现批次登记；
> 与基线冲突以基线为准。

## 1. 合成 DGP（基线 §7）

### N-AR（Gaussian delay null）
```
X_t = ρ X_{t-1} + sqrt(1-ρ²) ε_t,  ε_t iid N(0,1);   ρ∈{0,0.8}
```
- 初值 `X_{-1000}~N(0,1)`；递推后丢弃 X_{-999}..X_0（burn-in 1,000）；正式段 X_1..X_T。
- 每个窗口**内部**做 d=3、τ=3 延迟嵌入 `(x_t,x_{t+3},x_{t+6})`；禁止整序列嵌入再切窗。

### N-CIRCLE（固定边际几何、可控时序依赖）
```
G_t = ρ G_{t-1} + sqrt(1-ρ²) ε_t;  U_t = Φ_N(G_t) (scipy.special.ndtr, float64)
X_t = (cos 2πU_t, sin 2πU_t)^T + 0.08 η_t,  η_t iid N2(0,I2)
```
- 同 burn-in 约定；η 在 ρ 格间共享；`Q=I_2`（禁止随机旋转）；
  任意 ρ 下单时点边际 U_t~U(0,1)；ρ=0.8 只解释为原序列依赖的效应修饰条件。
- H0 与 H1 必须共用 `build_null_signature(rho,W,s,T,M)`（`null_model_config_hash` 模型身份，
  不承载 phase/scenario/effect 参数）。

## 2. 主 H0 双矩阵（基线 §8）

Fixed-M：`W=64, M=192`，`T=64+s*191`：
| s | overlap | T |
|---|---:|---:|
| 64 | 0 | 12,288 |
| 32 | 0.50 | 6,176 |
| 16 | 0.75 | 3,120 |
| 8 | 0.875 | 1,592 |

Fixed-T：`T=3120, W=64`：
| s | overlap | M |
|---|---:|---:|
| 64 | 0 | 48 |
| 32 | 0.50 | 96 |
| 16 | 0.75 | 192 |
| 8 | 0.875 | 383 |

- 2 DGP × 2 ρ × 4 s × 2 预算 − 4 共享 = **28 唯一格**；
- 每条 ρ 变换 master path（L=12,288 正式观测）恰计算 **575 个唯一窗口**（fixed-T s=8 的 383 +
  fixed-M s=32 新增 96 + fixed-M s=64 新增 96）；禁止机械枚举全部 stride-8 窗口；
- shared `(W,s,T,M)=(64,16,3120,192)` 只一个物理 cell，`budget_membership=["FIXED_M","FIXED_T"]`；
- 跨 ρ/stride 共享创新的统计对比以 `cluster_id` 为整簇单位，N-AR/N-CIRCLE 分层等权。

## 3. MC 规模（基线 §9）

| 线 | replicate | 格 | data units | eval rows | PH windows |
|---|---:|---:|---:|---:|---:|
| H0 | 2,500（1..2500） | 28 | 70,000 | 280,000 | 5,750,000 |
| H1 | 1,600（1..1600） | 8 | 12,800 | 51,200 | 2,457,600 |

- 内层重采样统计量：H0 279,720,000 + H1 51,148,800 = 330,868,800；
- blind smoke：每物理格 32 replicate（namespace 独立，`smoke_generation_id=S01`）；
  H0 smoke 896 units/3,584 rows、H1 smoke 256 units/1,024 rows；
- 禁止跨 H1 physical_cell 复用 feature/PH cache（cache key ≥ data_unit_id,window_start,W,feature_config_hash）。

## 4. 窗口局部规则（基线 §3.2/§5.1）

点云拒绝 NaN/Inf、`-0.0→+0.0`、float64 lexsort + 位模式去重、point_limit=128、
VR F2 H0/H1 maxdim=1 无数据驱动 thresh、删 infinite-death、<2 唯一点零向量；
所有 scale/grid/kernel 均窗口局部（METHOD_SPEC §4/§5）。

## 5. 真实数据：PAMAP2（基线 §13）

- UCI PAMAP2（DOI 10.24432/C5NW2H），Protocol 子集 9 受试者
  （subject101..109，54 列）；`dataset_hash` 只哈希九个文件 {path,size,sha256}；
- 活动集合冻结 {1,2,3,4,5,6,7,12,13,16,17,24} + transient 0；时间戳/列语义校验；
- 时钟分段 → 半向上 100 Hz 网格 → 传感器 NaN 线性插值（长度 ≤50，四步 binary64 顺序，
  禁 FMA/代数改写）→ 三轴 bad-row union → 除以 9.80665 得 g 单位；
- BPI cap=6 g；W=100（1 s），s∈{100,50,25}；
- 转移任务：bout 行数 ≥3,000、zero run 0..500、左/右上下文 L∈{20..30} s；≥8 受试者 / ≥24 任务；
- 运行前最迟 9/13 提交 `dataset_hash`、real_task_root/salt commitments 与 real config hashes；
- 失败路由：`REAL_DATA_TASK_GATE`/`REAL_ISOLATION_ADMISSION_GATE` 失败 →
  `REAL_OMITTED_BY_DATA_GATE`；日程 Gate 失败 → `REAL_DEFERRED`（truth 保持封闭）。

## 6. 开放项

- [ ] `REAL_DATA_CONFIG_v1.json`、`TASK_BUILDER_CONFIG_v1.json`、`REAL_SCOPE_SPEC_v1.json`
      实现与 hash 登记；
- [ ] `DATA_MANIFEST.json`（zip/readme/9 文件 SHA256、下载时间、许可、导入器版本）；
- [ ] N-AR/N-CIRCLE 的 data_model_config_hash 实现与 golden fixtures。
