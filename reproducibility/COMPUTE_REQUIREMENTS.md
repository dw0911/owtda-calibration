# COMPUTE_REQUIREMENTS — 算力需求

## 1. 论文规模（冻结设计）

| 量 | 值 |
|---|---|
| H0：28 唯一格 × 2,500 replicate | 70,000 data units / 140,000 feature rows / **280,000 evaluation rows** |
| H1：8 格 × 1,600 replicate | 12,800 / 25,600 / **51,200 evaluation rows** |
| 合计 | **331,200 evaluation rows**；330,868,800 内层重采样统计量；8,207,600 个 PH 窗口 |
| 重采样 | `B = 999`（每次评估 999 个置换/乘子重采样） |

## 2. 时间/资源（盲 smoke 预算外推，冻结记录）

| 项 | 值 |
|---|---|
| H0 外推 wall | `t_H0_hat = 22.842 h`（上限 192 h） |
| H1 外推 wall | `t_H1_hat = 4.731 h`（上限 76.8 h） |
| 核心合计 | `t_core_hat = 27.573 h`（上限 268.8 h） |
| 峰值内存 | 总 peak RSS **1.393 GiB**（上限 24 GiB） |
| swap 增量 | 0 |
| 峰值磁盘 | `estimated_peak_disk ≈ 386 MiB`（上限 0.8 × 可用）；账本最终约 3.2 GB |
| 并行度 | `workers ∈ 1..cpu_count`；逐位一致要求；建议 ≥ 8 核（实测 8 workers 用于冻结预算） |
| GPU | **不需要**（纯 CPU；`ripser` 单线程 PH + BLAS 单线程） |

> 以上为冻结计算规格（`governance/COMPUTE_FREEZE.json`、§9.4 预算对象）的记录值；实际主机不同会改变 wall time，
> 但**不得**改变 seeds/参数/规模。

## 3. 各层级的实际开销（本快照构建环境，Windows / 8 workers）

| 层级 | 命令 | 实测 |
|---|---|---|
| Level 1 | `verify_release.py --level quick` | 秒级 |
| 冒烟子集 | `run_smoke.py` | 约 5 s（35 项） |
| 回归测试 | `pytest tests -q` | 约 77 s（1069 项） |
| Level 2（分析链） | 见 RUNBOOK | 分钟级（依赖账本大小；H0 账本 1.4 GB 流式聚合约 1–2 分钟/次） |
| Level 3（完整重跑） | `run_h0.py` / `run_h1.py` | **~28 h**（单机 8 workers，按冻结预算外推） |
| 论文编译 | XeLaTeX ×3 + bibtex | 约 30–60 s |

## 4. 最低硬件建议

- CPU：8 核以上（Level 3 全跑）；Level 1/2 任意现代 CPU 均可；
- 内存：Level 3 ≥ 8 GiB（峰值 1.4 GiB + 系统余量）；Level 2 ≥ 4 GiB；
- 磁盘：Level 3 ≥ 20 GiB（账本 3.2 GB + 中间产物）；Level 1/2 ≥ 2 GiB；
- 操作系统：Windows / Linux 均可（正式快照在 Windows 构建；测试在两者均可运行）。
