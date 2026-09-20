# VALIDATION_SUMMARY — 本发布版本通过的核验

> 记录对象：`v1.0.0-paper` 发布快照（2026-09-20）。

## 1. 结果一览

| # | 核验项 | 命令 | 结果 |
|---|---|---|---|
| 1 | 依赖锁定重建 | `uv sync --frozen` | 通过 |
| 2 | 回归测试 | `pytest tests -q` | **745 passed / 8 skipped**（0 失败） |
| 3 | 静态检查 | `ruff check src tests scripts configs paper/scripts` | 全清 |
| 4 | canonical 序列化契约 | `python scripts/check_canonical.py` | **0 问题** |
| 5 | 发布快速验证 | `python scripts/verify_release.py --level quick` | **28/28 通过** |
| 6 | 发布分析验证 | `python scripts/verify_release.py --level analysis` | **31/31 通过** |
| 7 | P1–P3 再生成一致 | `python scripts/bootstrap_primary_contrasts.py --check` | 通过 |
| 8 | 表再生成一致 | `python scripts/build_tables.py --check` | 通过（5/5） |
| 9 | 图再生成一致 | `python scripts/build_figures.py --check` | 通过（24 inputs, 0 unresolved, 0 mismatch） |
| 10 | H0/H1 canonical 自洽 | `python scripts/analyse_h0.py --check` / `analyse_h1.py --check` | 通过 |
| 11 | 论文编译 | XeLaTeX ×3 + bibtex | 通过（24 页） |
| 12 | 从头重跑（冒烟规模） | `python scripts/reproduce.py --phase NULL --replicate-limit 1` | 通过（112 evaluation 行，规则核验 0 违例） |

## 2. `verify_release --level quick` 覆盖

H0（112 单元 / 28 格 / `n=2500` / `rate=rejects/n` / Wilson 90·95 重算 / 分类词表 / 与 `Table4_calibration.csv` 计数一致）、
H1（16 cell-feature / 几何公式 / `n=1600` / 临界秩 2376）、P1–P3（`p=(tail+1)/(B+1)`、p>0、Holm 重算、CI 与 canonical 一致、
与 `MANUSCRIPT_VALUES` 对齐）、图表 `meta.json` 输入可解析且哈希一致、
LaTeX `\input`/图件路径、`SHA256SUMS` 全部核验。

## 3. 如实披露（不阻断发布）

1. **表 1–5 原始生成器未保留**——现由 `paper/scripts/make_tables.py` 从 canonical 源重新生成，正文 `\input`
   生成结果，生成链已在 CI 中 fail-closed 校验。
2. **旧 `p = 0` 值**：`H0_PRIMARY_CONTRASTS.json` / `P1_P3_BOOTSTRAP.json` 的旧推断字段按原字节保留（哈希链要求），
   现行有效值见 `results/bootstrap/P1_P3_BOOTSTRAP_SUMMARY.json`（tail=0 → p=1/10001，Holm=3/10001）。
3. **M0 逐格范围口径**：纸面 [4.72, 97.56] vs canonical 全行 [4.32, 99.96]——已登记待核对。
4. 正式账本与大型索引**不随仓库分发**（哈希登记在 `data/manifests/`）；复现论文的合成实验不需要它们。

## 4. 复现方式

见 [`RUNBOOK.md`](RUNBOOK.md)；环境见 [`ENVIRONMENT.md`](ENVIRONMENT.md)；数据见 [`DATA_AVAILABILITY.md`](DATA_AVAILABILITY.md)。
