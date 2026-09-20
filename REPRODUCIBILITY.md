# REPRODUCIBILITY — 复现指南

> 目标：使论文的**全部数值、图、表**可由本仓库复现；同时如实说明**不随仓库分发**的大对象。

## 0. 当前树（2026-09-20 精简后）

| 目录 | 作用 |
|---|---|
| `src/owtda_cal/` | 核心实现（48 个模块，冻结字节） |
| `tests/` | 契约 + 攻击式回归 |
| `scripts/` | 规范入口：`reproduce` / `verify_release` / `analyse_h0` / `analyse_h1` / `bootstrap_primary_contrasts` / `build_tables` / `build_figures` / `build_reproducibility_index` / `build_release_manifest` / `build_sha256sums` / `fetch_archived_data` / `check_canonical` / `frozen_env` |
| `results/{canonical,bootstrap}/` | **正文数值的单一真源** |
| `artifacts/{tables,figures}/` | 表 1–5 与图 1–5（含 `meta.json` 血缘：输入/输出/脚本哈希 + 稿件引用） |
| `paper/` | LaTeX 工程 + `paper/scripts/{make_tables.py,make_figures.py}`；正文以 `\input` 引用生成表 |
| `configs/`、`environment/`、`governance/` | 冻结设计、环境锁、冻结对象（复现输入，字节绑定） |
| `reproducibility/` | RUNBOOK / ENVIRONMENT / DATA_AVAILABILITY / FAILURE_POLICY / VALIDATION_SUMMARY / `FORMAL_MANIFEST` / `RELEASE_MANIFEST` / `ARTIFACT_INDEX` / `SHA256SUMS` |

审计/治理过程登记项、封存证据（seal/preflight）与一次性构建器已从公共树剔除，
逐项登记在 [`EXCLUDED_ARTIFACTS.csv`](EXCLUDED_ARTIFACTS.csv)，并保留在开发历史中。

## 1. 环境

```powershell
uv sync --frozen                      # 依 pyproject.toml + uv.lock
$env:PYTHONDONTWRITEBYTECODE = "1"    # 冻结运行约定（与正式结果一致）
$env:OMP_NUM_THREADS = "1"; $env:OPENBLAS_NUM_THREADS = "1"
$env:MKL_NUM_THREADS = "1"; $env:NUMEXPR_NUM_THREADS = "1"
```

- 冻结环境记录（版本 / BLAS / 线程 / pip freeze）：`environment/`。
- 图件生成另需 `matplotlib`（锁定环境内提供）与可确定获得的 CJK 字体（见 `reproducibility/ENVIRONMENT.md` §5）。

## 2. 数据（复现合成主线**不需要**任何外部数据）

- 论文的实验是合成实验（N-AR / N-CIRCLE），由代码 + 冻结种子程序化生成（`governance/SEED_REGISTRY_v1.0.json`）。
- 真实数据（PAMAP2）为第三方数据，出处与逐文件 SHA256 见 [`DATA_SOURCES.md`](DATA_SOURCES.md)；本代 REAL 线为
  `REAL_OMITTED_BY_DATA_GATE`，复现合成主线不需要。
- 正式账本与大型索引**不随仓库分发**，哈希登记在 `data/manifests/`（见 §5）。

## 3. 复现路径（三级）

### Level 1 — 快速完整性验证（秒级，零外部数据）

```powershell
python scripts/verify_release.py --level quick      # 28/28
python scripts/build_tables.py --check              # 表 1–5：缺表/数值差异/多余产物 → 非零
python scripts/build_figures.py --check             # 图件：输入/输出/脚本哈希 + 稿件引用
python scripts/check_canonical.py                   # canonical 序列化契约
python -m pytest tests -q                           # 契约与攻击式回归
```

覆盖 H0 112 单元 / 28 唯一格、`rate = rejects/n`、Wilson 90/95 重算、分类计数与
`artifacts/tables/Table4_calibration.csv` 一致；H1 16 cell-feature、临界秩 2376；
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

### Level 3 — 从头重跑（小时级，零外部数据）

这是**复现论文实验的主路径**：用代码 + 冻结种子从零重跑 H0/H1 Monte Carlo。

```powershell
python scripts/reproduce.py --phase NULL --workers 8 --out ./repro   # H0：280,000 evaluation 行
python scripts/reproduce.py --phase ALT  --workers 8 --out ./repro   # H1：51,200 evaluation 行
python scripts/analyse_h0.py --from-ledger ./repro/H0_NULL_evaluation.scientific.jsonl
```

冒烟规模（几分钟，验证流水线可跑）：`python scripts/reproduce.py --phase NULL --replicate-limit 32 --out ./smoke`。

产出账本的 `logical_cell_id` / `feature_id` / `method_id` 与 canonical 一一对应，`analyse_h0.py --from-ledger`
会把逐格聚合结果与 `results/canonical` 对账（规则 `p = (exceed+1)/(B+1)`、`reject = (exceed <= 49)`）。

### Level 2 — 由封存账本重做分析（分钟级，可选，需账本副本）

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
  登记了大小与 SHA-256。
- P1–P3 的精确值可由库内真实 draws 复算：`governance/actual_primary_draws.json`
  （10,000 draws/项）→ `scripts/bootstrap_primary_contrasts.py`。
- H1 的账本级重分析脚本：`release/analysis/scripts/reanalyse_h1.py`。

## 4. 校验矩阵（提交前自检）

| 命令 | 覆盖 |
|---|---|
| `python -m pytest tests -q` | 契约 / 攻击式回归（"故意破坏必须失败"） |
| `python -m ruff check src tests scripts configs paper/scripts` | 静态检查（全清） |
| `python scripts/verify_release.py --level quick` / `--analysis` | 28/28 / 31/31（含再生成比对） |
| `python scripts/build_tables.py --check` / `build_figures.py --check` | 表 1–5 / 图件血缘 |
| `python scripts/build_release_manifest.py --check` | 发布清单与 tag 一致 |
| `python scripts/fetch_archived_data.py --verify-only` | 账本就位时 6/6，否则返回 2 |

## 5. 不随仓库分发的大对象（如实披露）

完整清单（path / 字节数 / SHA256 / 原因）：[`EXCLUDED_ARTIFACTS.csv`](EXCLUDED_ARTIFACTS.csv)。摘要：

| 对象 | 大小 | 说明 |
|---|---|---|
| H0/H1 四个正式账本 | 1.40 GB / 1.44 GB / 266 MB / 262 MB | 哈希登记在 `data/manifests/`；**复现合成实验不需要** |
| `governance/ACTIVE_*_INDEX_*.jsonl`（6 个） | 7–140 MB | 大型派生索引；可由冻结计划/种子重生成 |
| PAMAP2 原始数据 | 2.49 GB | 第三方（UCI ML Repository，CC BY 4.0），本仓库不重新分发 |

## 6. 版本与变更

- 权威变更记录：`governance/CHANGELOG.md`（append-only）。
- 本快照：`v1.0.0-paper`（2026-09-20）。若复现结果与论文不一致，请携带命令、环境与产物哈希提 issue。
