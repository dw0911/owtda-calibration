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
2. **生成表与补充材料**（仅读 canonical 汇总，不调用 MC/PH）：

   ```powershell
   python audit/build_corrected_assets.py `
     --h0 artifacts/summaries/H0_POINTWISE.json `
     --h1 release/analysis/H1_REANALYSIS.json `
     --out <新目录（须不存在）>
   ```

   产出 `H0_ALL_112`、`H1_ALL_16_GEOMETRY_COMPLETE`、`H1_SCENARIO_SAME_FOUR_CONDITIONS`、`H1_SCENARIO_DIFFERENCES`、
   `Table_H1_COMMON_ESTIMAND.tex` 与两张修正热图；与仓库 `artifacts/tables/`、`manuscript/supplement/` 可直接对照。

3. **生成正文图**（读 `artifacts/tables/` 的 canonical CSV）：

   ```powershell
   python manuscript/scripts/make_figures.py     # 输出 artifacts/figures/（Fig1–5 + supplement，每图附 meta.json）
   ```

   > 注：该脚本在 2026-09-20 生成本仓库图件后仅做过**可移植性修订**（绝对路径 → 仓库相对；绘图逻辑未变）。
   > 各图 `meta.json` 的 `script_sha256` 对应**生成时刻**的脚本字节；重新生成会刷新 `generated_at` 与 `script_sha256`（可预期的元数据差异），图件内容由 §2/§3.2 的 canonical 表决定。

4. **一致性/契约校验**：`python scripts/check_canonical.py`（canonical 序列化递归检查）、`python -m pytest tests -q`。

### 路径 B — 分析链（由封存账本重算）

1. 输入：四个账本文件（本地，不随仓库分发；SHA256 见 §5）：
   `artifacts/ledgers/H0_NULL/{evaluation,feature}.scientific.jsonl`、
   `artifacts/ledgers/H1_ALT/{evaluation,feature}.scientific.jsonl`；
2. 重算：canonical 汇总与 bootstrap（见 `release/analysis/` 内脚本与 `governance/ANALYSIS_INPUT_MANIFEST_*.json`、
   `RESOLVED_BOOTSTRAP_PLAN_INDEX_*.jsonl`；分析身份：`analysis_id=18797cfe…`）；
3. P1–P3 精确值：真实 draws 已在库（`governance/actual_primary_draws.json`，各 10,000）。用**仓库内工具**重算：

   ```powershell
   python audit/analysis_repairs.py --draws governance/actual_primary_draws.json --out <新文件>.json
   ```

   得到 bootstrap 单侧 p / basic CI / Holm（回归测试：`tests/test_analysis_repairs.py`），用于替换正文 `<0.05` 占位。
   H1 的账本级重分析（由封存账本出发）见 `release/analysis/scripts/reanalyse_h1.py`；账本不在仓库内（见 §5）。

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
| `python -m ruff check src tests audit scripts configs` | 静态检查（代码与工具域，全清） |
| `python scripts/check_canonical.py` | canonical 序列化契约（governance / artifacts 递归） |
| `python audit/validate_freeze.py` | 冻结对象、seed/component registry、REAL 链、快照重算 |
| `python audit/validate_schemas.py` | 逐行 schema（24 variants、拒绝未知字段） |
| `python audit/validate_runs.py` / `validate_identity.py` | RUN 身份与 expected index 闭合 |
| `python scripts/verify_release_contracts.py` / `verify_audit_dossier.py` | 发布/审计包合同 |

> `ruff check .`（全仓库）另报 **14 项**风格提示，全部位于 3 个交付/构建脚本
> （`release/analysis/scripts/reanalyse_h1.py`、`release/analysis/scripts/review_delivery.py`、`manuscript/scripts/make_figures.py`）——
> 它们保留了交付时的紧凑风格，逻辑无问题，如实披露；代码与工具域（上方命令）为全清。

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
- 大索引的校验工具已入库：`python audit/check_active_indexes.py`（指向本地索引文件即可复核与 `ACTIVE_*` 契约的一致性）。
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
