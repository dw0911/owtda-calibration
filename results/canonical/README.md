# results/canonical — 正文数值的单一真源

> **规则**：论文正文/表格/图形中的每一个科学数字都必须来自本目录（或 `results/bootstrap/`）；
> 禁止 `final/`、`final2/`、`latest/`、`corrected/` 之类并排版本。历史版本由 git 历史与冻结 tag 管理。

## 1. 内容（canonical 对象）

| 文件 | 内容 | 生成者 |
|---|---|---|
| `H0_POINTWISE.json` | H0 逐格 canonical 数据（112 个评价单元：28 唯一格 × 2 表示 × 2 方法） | 分析链（ledger → canonical） |
| `H0_PRIMARY_CONTRASTS.json` | P1–P3 主对比（点估计、阈值、旧推断字段）＋ rho 交互与次级对比 | 分析链 |
| `H1_REANALYSIS.json` | H1 重分析（16 个 cell-feature：功效、size、定位、联合、bootstrap） | `release/analysis/scripts/reanalyse_h1.py` |
| `H1_ALL_16_GEOMETRY_COMPLETE.{csv,json}` | H1 全 16 行几何/功效/定位表（csv 另见 `artifacts/tables/`） | `audit/build_corrected_assets.py` |
| `H1_SCENARIO_DIFFERENCES.json` | 两场景 BPI−MOMENTS 差值 + 配对 95% CI（csv 另见 `artifacts/tables/`） | `audit/build_corrected_assets.py` |
| `CANONICAL_SUMMARY.json` / `MANUSCRIPT_VALUES.json` | 正文数值汇总（后者为正文 ↔ canonical 一致性检查的输入） | 分析链 |
| `FIGURE_DATA.json` / `TABLE_DATA.json` | 图/表输入数据（程序化生成用） | 分析链 |
| `P1_P3_BOOTSTRAP.json` | P1–P3 bootstrap 旧对象（见 §3 取代说明） | 分析链 |
| `CLAIM_EVIDENCE_MAP.csv` | 主张 ↔ 证据 ↔ 当前状态映射（C1–C8） | 本批次生成 |
| 其他 provenance | `ANALYSIS_INPUT_MANIFEST_*.json`、`bootstrap_context.json`、`validation_summary.json`、`aggregation_summary.json`、`percell_analysis.json`、`shard_hashes.json`、`activation_summary.json`、`active_index_summary.json`、`bootstrap_power_diff.json` | 分析链 / 交付 |

**未移动文件**：`artifacts/summaries/PHASE_SEAL_*.json` 留在原地——`audit/check_active_indexes.py` 依赖该路径。
**交付包副本**：`release/analysis/*` 是 2026-09-18 封存交付包的原始副本（审计留存，逐字节与本目录一致者已在交付审计中登记），**不是**第二个真源。

## 2. 与审计规范命名的映射

| 规范建议名 | 本仓库实际位置 |
|---|---|
| `H0_POINTWISE.csv` | `artifacts/tables/H0_ALL_112.csv`（112 行逐格表） |
| `H0_CLASSIFICATION_COUNTS.csv` | `artifacts/tables/Table4_calibration.csv`（四分类计数，n=28） |
| `H1_CANONICAL_SUMMARY.json` | `H1_REANALYSIS.json` + `CANONICAL_SUMMARY.json` |
| `P1_P3_BOOTSTRAP_SUMMARY.json` | `results/bootstrap/P1_P3_BOOTSTRAP_SUMMARY.json`（**当前有效推断**） |
| `CLAIM_EVIDENCE_MAP.csv` | 本目录同名文件 |

## 3. SUPERSEDED：不得作为现行结果的旧值

| 位置 | 旧值 | 状态与处置 |
|---|---|---|
| `H0_PRIMARY_CONTRASTS.json` → `primary.*.p_boot_one_sided` / `p_holm` | `0.0` | **非法**（加一规则下 p≥1/10001）。R1 审计裁定以真实 draws 重算；**原字节保留**（其 SHA-256 被表格 meta 与分析身份引用），**现行有效值见 `results/bootstrap/P1_P3_BOOTSTRAP_SUMMARY.json`**（tail=0 → p=1/10001，Holm=3/10001） |
| `P1_P3_BOOTSTRAP.json` | 旧 bootstrap 对象（p=0 语境） | 同上，作为历史对象保留 |
| `CORRECTION_NOTE_20260918.md`（现 `artifacts/audit/`） | 定位误差半采样点约定偏差 | 已由 `H1_REANALYSIS.json` 取代（文档自身已声明 SUPERSEDED） |

### 待核对（复现校验中发现，需作者在图表重构轮核定）

| 项 | canonical 全行计算值 | `MANUSCRIPT_VALUES.json` / 稿件 | 说明 |
|---|---|---|---|
| M0 逐格 Type-I 范围 | **[4.32%, 99.96%]**（全部 112 单元）；fixed-T 子集 [4.72%, 99.96%] | **[4.72%, 97.56%]** | 上下界均可重复计算，但口径与全行范围不一致；疑似为某个子集（或早期修订）。已由 `scripts/verify_release.py` 以"纸面值应落在 canonical 范围内"的方式校验（当前通过），并如实登记于此 |
| M1 逐格 Type-I 范围 | [0.20%, 14.12%] | [0.20%, 14.12%] | 一致 ✓ |

## 4. 再生成与校验

```powershell
# P1-P3（真实 draws → p/CI/Holm）
python scripts/bootstrap_primary_contrasts.py
python scripts/bootstrap_primary_contrasts.py --check     # 与已提交产物逐哈希比对

# 表/补充材料（canonical 汇总 → 表）
python audit/build_corrected_assets.py --h0 results/canonical/H0_POINTWISE.json --h1 results/canonical/H1_REANALYSIS.json --out <新目录>

# 图（表 → 图）
python scripts/build_figures.py
```
