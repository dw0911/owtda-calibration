# REPRODUCIBILITY — 复现指南

> 目标：使论文的**全部数值、图、表**可由本仓库（+ 可选外部账本）复现；
> 同时如实说明**不随仓库分发**的大对象、**已从公共树剔除**的历史过程件及其处置方式。

## 0. 当前树（2026-09-20 精简后）

| 目录 | 作用 |
|---|---|
| `src/owtda_cal/` | 核心实现（48 个模块，冻结字节） |
| `tests/` | 契约 + 攻击式回归（71 个文件，1069 passed / 1 skipped） |
| `scripts/` | 规范入口：`verify_release` / `analyse_h0` / `analyse_h1` / `bootstrap_primary_contrasts` / `build_tables` / `build_figures` / `build_reproducibility_index` / `build_release_manifest` / `build_sha256sums` / `fetch_archived_data` / `run_smoke` / `run_h0` / `run_h1` / `run_formal` / `frozen_env` |
| `audit/` | 独立验证器与构建器：`validate_freeze` / `validate_schemas` / `repo_guard` / `build_freeze` / `build_run_admission` / `run_formal_phase` / `analysis_repairs` / `check_active_indexes` / `resource_sampler` 等（Tests 直接引用者全部保留） |
| `results/{canonical,bootstrap}/` | **正文数值的单一真源** |
| `artifacts/{tables,figures}/` | 表 1–5 与图 1–5（含 `meta.json` 血缘：输入/输出/脚本哈希 + 稿件引用） |
| `artifacts/seals/`、`artifacts/summaries/`、`artifacts/preflight/` | 运行封条、索引集 PHASE SEAL、预算证据 |
| `paper/` | LaTeX 工程 + `paper/scripts/{make_tables.py,make_figures.py}`；正文以 `\input` 引用生成表 |
| `configs/`、`environment/`、`governance/` | 冻结设计、环境锁、治理对象（**字节绑定，不得修改**） |
| `reproducibility/` | RUNBOOK / ENVIRONMENT / DATA_AVAILABILITY / FAILURE_POLICY / VALIDATION_SUMMARY / `FORMAL_MANIFEST` / `RELEASE_MANIFEST` / `ARTIFACT_INDEX` / `SHA256SUMS` |

已剔除的历史过程件（交付包副本、冻结/身份/准入检查快照、旧审计 ZIP、smoke 工程证据、
旧代外部证据归档、一次性提交包构建器、过程登记项）全部登记在
[`EXCLUDED_ARTIFACTS.csv`](EXCLUDED_ARTIFACTS.csv) 的 `PRUNED_FROM_PUBLIC_TREE` 段，
并保留在开发历史与工作区归档中。

## 1. 环境

```powershell
uv sync --frozen                      # 依 pyproject.toml + uv.lock
$env:PYTHONDONTWRITEBYTECODE = "1"    # 冻结运行约定（与正式结果一致）
$env:OMP_NUM_THREADS = "1"; $env:OPENBLAS_NUM_THREADS = "1"
$env:MKL_NUM_THREADS = "1"; $env:NUMEXPR_NUM_THREADS = "1"
```

- 冻结环境记录（版本 / BLAS / 线程 / pip freeze / 仓库外重建测试）：`environment/`。
- 生成器：`scripts/frozen_env.py`（解释器启动前设定线程变量并留证）。
- 图件生成另需 `matplotlib`（锁定环境内提供）与可确定获得的 CJK 字体（见 `reproducibility/ENVIRONMENT.md` §5）。

## 2. 数据（可选，仅 REAL 条件线需要）

- 来源与逐文件 SHA256：见 [`DATA_SOURCES.md`](DATA_SOURCES.md)（PAMAP2 Protocol，9 个 `subject10X.dat`）。
- 放置约定：`<base_dir>/Protocol/subject101.dat … subject109.dat`；数据身份按
  `dataset_hash = H("pamap2_protocol_dataset", 9×{path,size,file_sha256})` 计算（`src/owtda_cal/realdata.py`）。
- 本代 REAL 线为 `REAL_OMITTED_BY_DATA_GATE`（23 < 24 合格任务，数据事实；未下调准入线）。
  **合成主线的复现不需要该数据。**

## 3. 复现路径（三级）

### Level 1 — 快速完整性验证（秒级，无需外部数据）

```powershell
python scripts/verify_release.py --level quick      # 28/28
python scripts/build_tables.py --check              # 表 1–5：缺表/数值差异/多余产物 → 非零
python scripts/build_figures.py --check             # 图件：输入/输出/脚本哈希 + 稿件引用
python scripts/check_canonical.py                   # canonical 序列化契约
python -m pytest tests -q                           # 1069 passed / 1 skipped
```

覆盖 H0 112 单元 / 28 唯一格、`rate = rejects/n`、Wilson 90/95 重算、分类计数与
`artifacts/tables/Table4_calibration.csv` 一致；H1 16 cell-feature、几何、临界秩 2376；
P1–P3 的 `p=(tail+1)/(B+1)`、Holm、CI 与 canonical 一致；`MANUSCRIPT_VALUES` 对齐；
LaTeX `\input`/图件路径解析；`reproducibility/SHA256SUMS` 全部核验。

**由 canonical 重生成表与图**（同一 matplotlib 版本下逐字节稳定）：

```powershell
python paper/scripts/make_tables.py                 # → artifacts/tables/Table1..5.{tex,csv,json,meta}
python scripts/build_figures.py                     # → artifacts/figures/Figure1..5.{pdf,svg,png,meta}
```

编译论文（工作目录必须是 `paper/`；正式构建加 `touch paper/STRICT.tex` 启用严格模式）：

```powershell
cd paper
xelatex -interaction=nonstopmode main.tex; bibtex main
xelatex -interaction=nonstopmode main.tex; xelatex -interaction=nonstopmode main.tex
```

### Level 2 — 由封存账本重做分析（分钟级，需外部账本）

```powershell
python scripts/fetch_archived_data.py --verify-only --report-only   # 查看归档状态（始终 0）
python scripts/fetch_archived_data.py --verify-only                 # 就绪必须 0；缺失返回 2
python scripts/analyse_h0.py --from-ledger data/external/H0_NULL_evaluation.scientific.jsonl
python scripts/bootstrap_primary_contrasts.py                       # 真实 draws → p / CI / Holm
python scripts/analyse_h1.py --from-ledgers --delivery <交付目录> --h0-eval <H0 账本> --h1-eval <H1 账本> --out-dir <新目录>
python scripts/build_tables.py && python scripts/build_figures.py
python scripts/verify_release.py --level analysis                   # 31/31
```

- 四个账本与两组大型索引**不随仓库分发**（见 §5）；`data/manifests/external_artifacts.json`
  登记了大小、SHA-256 与 seal 绑定，两组索引另含三份成员的逐文件哈希。
- P1–P3 的精确值可由库内真实 draws 复算：`governance/actual_primary_draws.json`
  （10,000 draws/项）→ `scripts/bootstrap_primary_contrasts.py`（回归测试 `tests/test_analysis_repairs.py`）。
- H1 的账本级重分析脚本：`release/analysis/scripts/reanalyse_h1.py`（`--delivery --h0-eval --h1-eval --out-dir`）。

### Level 3 — 全链重跑（小时级，需要算力）

```powershell
python scripts/run_smoke.py                         # 端到端冒烟（独立身份域，不含论文结论）
python scripts/run_h0.py --plan <冻结计划> --certificate <G4 证书> --seed-registry governance/SEED_REGISTRY_v1.0.json --out <新证据目录>
python scripts/run_h1.py --plan <同上> --certificate <同上> --out <新证据目录>
```

按治理顺序（每步均为 append-only 证据）：`audit/build_freeze.py` → `audit/validate_freeze.py` →
`audit/build_run_admission.py` → `audit/run_smoke.py` → `scripts/run_formal.py`（唯一授权入口，
由 `audit/run_formal_phase.py` 以全生命周期资源监控包围计算与封存）→ 分析与成稿（Level 2 + Level 1）。

> 纪律：formal 阶段 `src/ configs/ audit/` 只读（`audit/repo_guard.py` fail-closed）；
> 失败先停 run、保留 shard/attempt，再按失效范围表处置；不得现场调参续跑。
> 说明：审计提交包的打包/校验工具（`build_audit_submission`、`verify_audit_dossier` 等）与
> 历史审计轨迹的身份校验器（`validate_identity`、`validate_runs`、`build_alt_admission`）属过程工具，
> 已从公共树剔除（见 §0 与 `EXCLUDED_ARTIFACTS.csv`）；它们产出的**封存证据仍在库内**
> （`artifacts/seals/`、`artifacts/summaries/`、`environment/`、`results/canonical/`）。

## 4. 校验矩阵（提交前自检）

| 命令 | 覆盖 |
|---|---|
| `python -m pytest tests -q` | 契约 / 攻击式回归（"故意破坏必须失败"） |
| `python -m ruff check src tests audit scripts configs paper/scripts` | 静态检查（全清） |
| `python scripts/verify_release.py --level quick` / `--analysis` | 28/28 / 31/31（含再生成比对） |
| `python scripts/build_tables.py --check` / `build_figures.py --check` | 表 1–5 / 图件血缘 |
| `python scripts/build_release_manifest.py --check` | 发布清单与 tag 一致 |
| `python scripts/fetch_archived_data.py --verify-only` | 账本 6/6（本机）或缺失返回 2 |
| `python audit/validate_freeze.py` | 冻结对象、seed/component registry、REAL 链（**会报 1 项 `source_tree_hash` 不匹配**：入库 `src/` 为 R4/R5 修复后的较新版本，而 `FREEZE_MANIFEST` 记录的是更早一次冻结的源树哈希；其余 PASS，不影响已封存 seal） |
| `python audit/validate_schemas.py --out-dir <新目录>` | 逐行 schema（24 variants、拒绝未知字段） |

> `ruff check .`（全仓库，含保留原样的交付脚本）可能另报少量风格提示；上表的代码与工具域为全清。

## 5. 不随仓库分发的大对象（如实披露）

完整清单（path / 字节数 / SHA256 / 原因）：[`EXCLUDED_ARTIFACTS.csv`](EXCLUDED_ARTIFACTS.csv)。摘要：

| 对象 | 大小 | 说明 |
|---|---|---|
| H0/H1 四个正式账本 | 1.40 GB / 1.44 GB / 266 MB / 262 MB | 哈希与 `artifacts/seals/<phase>/RUN_SEAL.json` 一致；归档与获取见 `reproducibility/DATA_AVAILABILITY.md` |
| `governance/ACTIVE_*_INDEX_*.jsonl`（6 个） | 7–140 MB | 大型派生索引；汇总见 `governance/active_index_summary.json`；已打包为确定性 tar 并登记哈希（`data/manifests/external_artifacts.json`） |
| PAMAP2 原始数据 | 2.49 GB | 第三方（UCI ML Repository，CC BY 4.0），本仓库不重新分发 |

- 账本为签名绑定的原始证据：哈希已固定在 RUN/PHASE seal 中；获取后按上表校验即可确认字节一致。
- 索引校验工具：`python audit/check_active_indexes.py`（指向本地索引文件即可复核与 `ACTIVE_*` 契约的一致性）。

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
- 本快照：`v1.0.0-paper`（2026-09-20）。若复现结果与论文不一致，请携带命令、环境与产物哈希提 issue。
