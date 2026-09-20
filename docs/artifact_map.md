# artifact_map — 规范命名 ↔ 本仓库实际路径

> 审计规范的目录树是**参考模板**（其自身注明"无需逐项照搬"）。本仓库在**不破坏已封存证据身份**的前提下
> 尽量对齐；下表逐项给出映射与"未改名"的原因。凡"未改名"项都是因为路径/文件名被
> seal、registry、`code_file_manifest` 或 `environment_lock_hash` 绑定——改名会使已封存身份无法复核。

## 1. 目录级映射

| 规范建议 | 本仓库实际 | 说明 |
|---|---|---|
| `src/owtda/` | **`src/owtda_cal/`** | ⚠️ 未改名：`pyproject.toml` 的 `packages=["src/owtda_cal"]` 进入 `environment_lock_hash`，且组件登记含逐文件 `code_file_manifest`；改名即破坏已封存 run 身份 |
| `configs/formal/*.yaml` | **`configs/formal/*.json`** + 权威源 `governance/` | 未用 YAML：`pyyaml` 不在冻结依赖内（不得改 `pyproject.toml`）；参数值本身在 `gov` 对象中冻结 |
| `configs/schema/` | `configs/schema/` ✓ | 同名 |
| `scripts/`（10 个规范入口） | ✅ 已全部创建 | 见 §2 |
| `tests/{unit,integration,regression,fixtures}` | **`tests/`（扁平）** | 未拆分：测试文件被冻结期的证据清单引用；`testpaths=["tests"]` 不变即可，功能不受影响 |
| `results/canonical/` | ✅ 已创建 | 由 `artifacts/summaries/` 迁入（`PHASE_SEAL_*.json` 原地保留，见 §3） |
| `results/bootstrap/` | ✅ 已创建 | P1–P3 真实 draws（`npz` + summary + meta） |
| `artifacts/figures/`、`artifacts/tables/` | ✅ 同名 | 图件 `meta.json` 与图**并排**（不改名：`make_figures.py` 的输出约定；审计包已核验该布局） |
| `artifacts/metadata/` | **未单独创建** | 元数据与图/表并排（同上）；全部登记在 `reproducibility/ARTIFACT_INDEX.csv` |
| `reproducibility/` | ✅ 已创建 | 见 §3 |
| `paper/` | ✅ 由 `manuscript/` **迁移**而来 | `main.pdf` 保留原名（LaTeX jobname 即 `main`）；`\includegraphics{../artifacts/...}` 相对路径不受影响 |
| `data/` | ✅ 已创建 | `manifests/`（正式账本 + 外部归档 + SHA256SUMS）、`sample/`、`external/`（占位） |
| `docs/` | ✅ 已创建 | 本文件 + method_overview + result_definitions + faq |
| `examples/` | ✅ 已创建 | 4 个脚本/说明 |
| `.github/` | ✅ 已创建 | ci / paper / release + issue 模板 + PR 模板 |
| `LICENSES/` | ✅ 已创建 | `DATA_LICENSE.txt`、`PAPER_LICENSE.txt`（均待作者确认；根 `LICENSE` 为代码许可占位） |
| `Dockerfile` / `Makefile` | ✅ 已创建 | 快捷入口；正式入口仍是 Python CLI |
| `notebooks/exploratory/` | 无 | 本仓库不使用 notebook 产生任何正式结果 |

## 2. `scripts/` 入口对照

| 规范入口 | 实际实现 | 说明 |
|---|---|---|
| `run_smoke.py` | ✅ 新建 | 默认跑冒烟子集（`tests/test_smoke*.py`）；`--full` 转发 `audit/run_smoke.py` |
| `run_h0.py` / `run_h1.py` | ✅ 新建 | 校验前提（plan/证书/种子/输出目录）后转发唯一授权入口 `scripts/run_formal.py` |
| `analyse_h0.py` | ✅ 新建 | `--check`（canonical 自洽）+ `--from-ledger`（账本流式聚合与规则核验） |
| `analyse_h1.py` | ✅ 新建 | `--check`（canonical 自洽）+ `--from-ledgers`（转发 `release/analysis/scripts/reanalyse_h1.py`） |
| `bootstrap_primary_contrasts.py` | ✅ 新建 | 真实 draws → p/CI/Holm；`--check` 自洽 |
| `build_tables.py` / `build_figures.py` | ✅ 新建 | 包装 `audit/build_corrected_assets.py` / `paper/scripts/make_figures.py`；均带 `--check` |
| `verify_release.py --level quick\|analysis` | ✅ 新建 | 规范 Level 1/2 的全部检查 |
| `fetch_archived_data.py` | ✅ 新建 | 按 `data/manifests/external_artifacts.json` 校验/下载大对象 |
| —（额外） | `build_sha256sums.py`、`build_reproducibility_index.py`、`check_canonical.py`、`frozen_env.py`、审计工具若干 | 证据与清单工具 |

## 3. `reproducibility/` 与既有证据目录的关系

| 目录 | 角色 |
|---|---|
| `reproducibility/` | 规范要求的复现文档与清单（RUNBOOK / ENVIRONMENT / COMPUTE_REQUIREMENTS / DATA_AVAILABILITY / FAILURE_POLICY / VALIDATION_SUMMARY / FORMAL_MANIFEST / RELEASE_MANIFEST / SEED_MANIFEST / EXPECTED_OUTPUTS / ARTIFACT_INDEX / SHA256SUMS） |
| `governance/` | **保留**：冻结对象、registry、append-only 变更链（`CHANGELOG.md`）、`FREEZE_MANIFEST`、seal 绑定的分析身份对象。规范树中未列，但它们是可复现性的**身份真源** |
| `artifacts/seals/`、`artifacts/preflight/`、`artifacts/audit/`、`artifacts/archive/`、`artifacts/smoke/` | **保留**：封存证据与历史工程证据（smoke 仅工程诊断，不进论文） |
| `release/` | **保留**：2026-09-18 交付包的原始副本（审计留存）；其中的 canonical 内容与 `results/canonical/` 一致（已校验），**不是**第二个真源 |
| `external_prior_evidence/` | **保留**：旧代 DMB-R1 终止归档（L1 证据，按治理要求披露与隔离） |
| `audit/` | **保留**：独立验证器与审计工具（`repo_guard`、schemas、freeze/runs 校验、攻击套件等） |

## 4. 单一真源对照

| 科学量 | 唯一真源 |
|---|---|
| H0 逐格率/区间/分类 | `results/canonical/H0_POINTWISE.json`（CSV 视图 `artifacts/tables/H0_ALL_112.csv`） |
| P1–P3 推断 | `results/bootstrap/P1_P3_BOOTSTRAP_SUMMARY.json`（旧 `p=0` 值仅作历史字节保留） |
| H1 逐格与场景差 | `results/canonical/H1_REANALYSIS.json`、`H1_SCENARIO_DIFFERENCES.json`（CSV 视图见 `artifacts/tables/`） |
| 正文数值 | `results/canonical/MANUSCRIPT_VALUES.json`（由 `verify_release` 与上述真源比对） |
| 图表 | `artifacts/figures/`、`artifacts/tables/`（脚本生成，禁止手工填数） |
