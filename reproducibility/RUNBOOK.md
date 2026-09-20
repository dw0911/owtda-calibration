# RUNBOOK — 三层复现入口

> 目标：读者可在**不运行完整 Monte Carlo** 的前提下核验全部论文数值；需要完整重跑时也有明确入口与前提。

## Level 1 · 快速完整性验证（秒级，CI 默认）

```powershell
python scripts/verify_release.py --level quick
```

覆盖：H0 112 个评价单元 / 28 唯一格；`n = 2500`；`rejection_rate = rejects / n`；Wilson 90/95 重算；
分类词表与 `Table4_calibration.csv` 计数一致；H1 16 个 cell-feature、几何公式、临界秩 2376；
P1–P3 的 `p = (tail+1)/(B+1)`、p>0、Holm 重算、CI 与 canonical 一致；`MANUSCRIPT_VALUES` 与 canonical 对齐；
图表 `meta.json` 的输入/输出可解析且哈希一致、生成脚本哈希为当前版本；LaTeX `\input`/图件路径存在；
`reproducibility/SHA256SUMS` 全部核验。

另可在秒级内单独校验两条生成链：

```powershell
python scripts/build_tables.py --check      # 正文表 1–5：缺表 / 数值差异 / 多余产物 → 非零退出
python scripts/build_figures.py --check     # 图件：输入/输出/脚本哈希 + 稿件引用闭合
```

## Level 2 · 由正式记录重做分析（分钟级，需账本）

```powershell
python scripts/fetch_archived_data.py --verify-only --report-only   # 只查看归档状态（始终返回 0）
python scripts/fetch_archived_data.py --verify-only                 # 归档可用时必须 0；不可用返回 2
python scripts/analyse_h0.py --from-ledger data/external/H0_NULL_evaluation.scientific.jsonl
python scripts/bootstrap_primary_contrasts.py               # 真实 draws → p / CI / Holm
python scripts/analyse_h1.py --from-ledgers --delivery <交付目录> --h0-eval <H0 账本> --h1-eval <H1 账本> --out-dir <新目录>
python scripts/build_tables.py                              # canonical 汇总 → 正文表 1–5
python scripts/build_figures.py                             # 表 → 图
python scripts/verify_release.py --level analysis           # Level 1 + 上述再生成的一致性比对
```

> 账本**不随仓库分发**：`fetch_archived_data.py --verify-only` 在账本未就位时以退出码 **2**
> 明确报告依赖缺失（不是静默通过）。复现论文实验走 Level 1 或 Level 3，**不需要账本**。

`analyse_h0 --from-ledger` 会流式聚合 `n`/`rejects` 并与 canonical 逐格比对，同时核验
`p = (exceed_count+1)/(B+1)` 与 `reject == (exceed_count <= 49)`（B = 999）。

## Level 3 · 完整重跑（小时级）

```powershell
python scripts/reproduce.py --phase NULL --workers 8 --out ./repro   # H0：280,000 evaluation 行
python scripts/reproduce.py --phase ALT  --workers 8 --out ./repro   # H1：51,200 evaluation 行
python scripts/analyse_h0.py --from-ledger ./repro/H0_NULL_evaluation.scientific.jsonl
```

`reproduce.py` 用代码 + 冻结种子（`governance/SEED_REGISTRY_v1.0.json`）从零重跑，
产出科学账本后与 canonical 对账；冒烟规模用 `--replicate-limit 32`。
算力需求见 [`COMPUTE_REQUIREMENTS.md`](COMPUTE_REQUIREMENTS.md)。

## 失败策略

见 [`FAILURE_POLICY.md`](FAILURE_POLICY.md)：任何一步失败 → 停止该 run、保留 shard/attempt 证据、
用同一 code/config/seed manifest 重跑**该 run**；禁止静默跳过、换种子补齐或现场调参续跑。

## 环境

见 [`ENVIRONMENT.md`](ENVIRONMENT.md)（`uv sync --frozen`；线程变量=1；`environment_lock_hash` 绑定）。
