# VALIDATION_SUMMARY — 本发布版本通过的核验

> 记录对象：`v1.0.0-paper` 发布快照（2026-09-20，commit 见 `FORMAL_MANIFEST.json`）。
> 核验在**独立克隆**（从 git bundle）中执行，全程不触碰工作主副本。

## 1. 结果一览

| # | 核验项 | 命令 | 结果 |
|---|---|---|---|
| 1 | 依赖锁定重建 | `uv sync --frozen` | 通过 |
| 2 | 回归测试 | `pytest tests -q` | **1069 passed / 1 skipped**（0 失败） |
| 3 | 静态检查（代码与工具域） | `ruff check src tests audit scripts configs` | 全清 |
| 4 | canonical 序列化契约 | `python scripts/check_canonical.py` | 257 对象 / 24 in-scope / **0 问题** |
| 5 | 发布快速验证 | `python scripts/verify_release.py --level quick` | 见 §2（全部通过） |
| 6 | P1–P3 再生成一致 | `python scripts/bootstrap_primary_contrasts.py --check` | 通过 |
| 7 | 表再生成一致 | `python scripts/build_tables.py --check` | 通过（CSV 逐字节一致；`Table_H1_COMMON_ESTIMAND.tex` 仅行尾差异） |
| 8 | 图再生成一致 | `python scripts/build_figures.py --check` | 通过（PNG 逐字节一致；PDF/SVG/meta 仅内嵌元数据差异） |
| 9 | H0 canonical 自洽 | `python scripts/analyse_h0.py --check` | 通过 |
| 10 | H1 canonical 自洽 | `python scripts/analyse_h1.py --check` | 通过 |
| 11 | 论文编译 | XeLaTeX ×3 + bibtex | 通过（22→23 页；`main.pdf` 546,178 B） |
| 12 | bundle 完整性 | `git bundle verify` | ok（10 refs：main + v1.0–v1.7） |

## 2. `verify_release --level quick` 覆盖

H0（112 单元 / 28 格 / `n=2500` / `rate=rejects/n` / Wilson 90·95 重算 / 分类词表 / 与 `Table4_calibration.csv` 计数一致）、
H1（16 cell-feature / 几何公式 / `n=1600` / 临界秩 2376）、P1–P3（`p=(tail+1)/(B+1)`、p>0、Holm 重算、CI 与 canonical 一致、
与 `MANUSCRIPT_VALUES` 对齐）、图表 `meta.json` 输入可解析且哈希一致（39 项输入）、
LaTeX `\input`/图件路径（12 个 tex 文件）、`SHA256SUMS` 全部核验。

## 3. 如实披露（不阻断发布，需在投稿前闭合）

1. **表 1–5 原始生成器未保留**（表数据/输入/输入哈希齐备；随图表重构轮补入新生成器）。
2. **`validate_freeze.py` 的 `source_tree_hash` 单项不匹配**（入库 `src/` 为 R4/R5 修复后较新版本；其余检查全 PASS，不影响已封存 seal）。
3. **旧 `p = 0` 值**：`H0_PRIMARY_CONTRASTS.json` / `P1_P3_BOOTSTRAP.json` 的旧推断字段按原字节保留（哈希链要求），
   现行有效值见 `results/bootstrap/P1_P3_BOOTSTRAP_SUMMARY.json`（tail=0 → p=1/10001，Holm=3/10001）。
4. **M0 逐格范围口径**：纸面 [4.72, 97.56] vs canonical 全行 [4.32, 99.96]——已登记待核对（`results/canonical/README.md`）。
5. 外部大对象（3.2 GB 账本 + 大型索引）DOI 待 Zenodo 归档后填入（`data/manifests/external_artifacts.json`）。

## 4. 复现方式

见 [`RUNBOOK.md`](RUNBOOK.md)；环境见 [`ENVIRONMENT.md`](ENVIRONMENT.md)；数据见 [`DATA_AVAILABILITY.md`](DATA_AVAILABILITY.md)。
