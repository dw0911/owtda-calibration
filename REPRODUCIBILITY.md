# REPRODUCIBILITY — 复现指南

> 目标：使论文的**全部数值、图、表**可由本仓库 + 指定外部数据（可选）复现；
> 同时如实说明**不随仓库分发**的大对象及其校验方式（SHA256 / seal 绑定）。

## 1. 环境

```powershell
# 依赖锁定：pyproject.toml + uv.lock
uv sync --frozen

# 冻结运行约定（与正式结果一致）
$env:PYTHONDONTWRITEBYTECODE = "1"
$env:OMP_NUM_THREADS = "1"; $env:OPENBLAS_NUM_THREADS = "1"
$env:MKL_NUM_THREADS = "1"; $env:NUMEXPR_NUM_THREADS = "1"
```

- 冻结环境记录（版本 / BLAS / 线程 / pip freeze / 仓库外重建测试）：`environment/`。
- 生成器：`scripts/frozen_env.py`（解释器启动前设定线程变量并留证）。

## 2. 数据（可选，仅 REAL 条件线需要）

- 来源与逐文件 SHA256：见 [`DATA_SOURCES.md`](DATA_SOURCES.md)（PAMAP2 Protocol，9 个 `subject10X.dat`）。
- 放置约定：`<base_dir>/Protocol/subject101.dat … subject109.dat`；数据身份按
  `dataset_hash = H("pamap2_protocol_dataset", 9×{path,size,file_sha256})` 计算
  （见 `src/owtda_cal/realdata.py`）。
- 本代 REAL 线为 `REAL_OMITTED_BY_DATA_GATE`（23 < 24 合格任务，数据事实；未下调准入线）。
  **合成主线的复现不需要该数据。**

## 3. 复现路径（三级）

### 路径 A — 仅图表/表（轻量，推荐评审使用）

1. 输入（已入库，canonical）：
   - `artifacts/summaries/`：`CANONICAL_SUMMARY.json`、`H0_POINTWISE.json`、`MANUSCRIPT_VALUES.json`、`FIGURE_DATA.json`、`TABLE_DATA.json`、`H1_REANALYSIS.json`、`P1_P3_BOOTSTRAP.json` 等；
   - `release/analysis/`：交付版分析对象与分析脚本（`scripts/` 子目录）。
2. 生成图/表：`manuscript/scripts/make_figures.py`（图）与 `audit/build_supplement.py`（补充表）。
3. 一致性校验：`audit/verify_manuscript_values.py`（正文数值 ↔ canonical 汇总，30 项）。

### 路径 B — 分析链（由封存账本重算）

1. 输入：四个账本文件（本地，不随仓库分发；SHA256 见 §5）：
   `artifacts/ledgers/H0_NULL/{evaluation,feature}.scientific.jsonl`、
   `artifacts/ledgers/H1_ALT/{evaluation,feature}.scientific.jsonl`；
2. 重算：canonical 汇总与 bootstrap（见 `release/analysis/` 内脚本与 `governance/ANALYSIS_INPUT_MANIFEST_*.json`、
   `RESOLVED_BOOTSTRAP_PLAN_INDEX_*.jsonl`；分析身份：`analysis_id=18797cfe…`）；
3. P1–P3 精确值：真实 draws 已在库（`governance/actual_primary_draws.json`，各 10,000），
   用交付包工具复核：`python tools/analysis_repairs.py --draws governance/actual_primary_draws.json --out <new>.json`
   （工具随 R1 审计包提供；重算得到 bootstrap p / CI / Holm，并替换正文 `<0.05` 占位）。

### 路径 C — 全链重跑（需要算力）

按治理顺序（每步均为 append-only 证据）：

1. 预检与冻结：`audit/build_freeze.py` → `audit/validate_freeze.py`（33 项）；
2. 运行身份与准入：`audit/build_run_admission.py` → `audit/validate_runs.py` → `audit/build_alt_admission.py`；
3. smoke（可选，独立身份域，永不进入论文）：`audit/run_smoke.py`、`audit/run_smoke_s03.py`；
4. 正式运行：`scripts/run_formal.py --plan … --certificate …`（唯一授权入口；
   由 `audit/run_formal_phase.py` 以全生命周期资源监控包围计算与封存）；
5. 封存与校验：RUN/PHASE seal 生成（`src/owtda_cal/formal_pipeline.py`）、`audit/validate_identity.py`；
6. 分析与成稿：路径 B + 路径 A。

> 纪律：formal 阶段 `src/ configs/ audit/` 只读（`audit/repo_guard.py` fail-closed）；
> 失败先停 run、保留 shard/attempt，再按失效范围表处置；不得现场调参续跑。

## 4. 校验矩阵（提交前自检）

| 命令 | 覆盖 |
|---|---|
| `python -m pytest tests -q` | 契约 / 攻击式回归（"故意破坏必须失败"） |
| `python -m ruff check .` | 静态检查 |
| `python audit/validate_freeze.py` | 冻结对象、seed/component registry、REAL 链、快照重算 |
| `python audit/validate_schemas.py` | 逐行 schema（24 variants、拒绝未知字段） |
| `python audit/validate_runs.py` / `validate_identity.py` | RUN 身份与 expected index 闭合 |
| `python scripts/verify_release_contracts.py` / `verify_audit_dossier.py` | 发布/审计包合同 |
| `python audit/verify_manuscript_values.py` | 正文数值 ↔ canonical 汇总 |

## 5. 不随仓库分发的大对象（如实披露）

完整清单（path / 字节数 / SHA256）：[`EXCLUDED_ARTIFACTS.csv`](EXCLUDED_ARTIFACTS.csv)。摘要：

| 对象 | 大小 | 说明 |
|---|---|---|
| `artifacts/ledgers/H0_NULL/evaluation.scientific.jsonl` | 1,404,096,576 B | SHA256 `74414103…91d8`，与 `release/h0_run/RUN_SEAL.json` 一致 |
| `artifacts/ledgers/H0_NULL/feature.scientific.jsonl` | 1,437,310,000 B | SHA256 `16b85452…a5f` |
| `artifacts/ledgers/H1_ALT/evaluation.scientific.jsonl` | 266,379,930 B | SHA256 `82ddef2b…52c7` |
| `artifacts/ledgers/H1_ALT/feature.scientific.jsonl` | 262,233,600 B | SHA256 `4ba3d1f7…1cd` |
| `governance/ACTIVE_*_INDEX_*.jsonl`（6 个） | 7–140 MB | 大型派生索引；汇总见 `governance/active_index_summary.json`；可由冻结计划与种子再生成 |

- 账本为**签名绑定的原始证据**：其哈希已在 RUN/PHASE seal 与审计记录中固定；获取到账本后按上表校验即可确认字节一致。
- 大索引不入库的原因：单文件超过 GitHub 100 MB 限制或属可再生的派生对象（不影响 seal 与论文数值的可验证性）。

## 6. 封存证据摘要（论文数字的血缘）

| 项 | 值 |
|---|---|
| freeze_id（G01） | `7cb4f85e31394b23f6c9d6bcaa9ce6a7fc7b824b2b5c8fb6b600c9181979322d` |
| H0 RUN seal | `241c2e95…`；PHASE seal `3913d436…`（详见 `artifacts/seals/H0_NULL/`） |
| H1 RUN seal | `c5ecaead…`；PHASE seal `d1e4a8f7…`（parent = H0 PHASE seal；详见 `artifacts/seals/H1_ALT/`） |
| 计数 | NULL 70,000 / 140,000 / 280,000；ALT 12,800 / 25,600 / 51,200（data / feature / evaluation） |
| 分析身份 | `ANALYSIS_INPUT_MANIFEST(1f1c7492…) → analysis_id(18797cfe…) → RESOLVED_BOOTSTRAP_PLAN_INDEX → bootstrap` |

## 7. 版本与变更

- 权威变更记录：`governance/CHANGELOG.md`（append-only；含批次、冻结标签 v1.0→v1.5、缺陷与修正、审计裁决）。
- 本快照：2026-09-20（R5-paper 阶段）。若复现结果与论文不一致，请携带命令、环境与产物哈希提 issue。
