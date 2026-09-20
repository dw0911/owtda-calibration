# results/canonical — 正文数值的单一真源

论文正文、表格、图形中的每个科学数字都来自本目录（或 `results/bootstrap/`）。

## 内容

| 文件 | 内容 |
|---|---|
| `H0_POINTWISE.json` | H0 逐格数据（112 个评价单元：28 唯一格 × 2 表示 × 2 方法） |
| `H0_PRIMARY_CONTRASTS.json` | P1–P3 主对比（点估计、阈值）与 rho 交互 |
| `H1_REANALYSIS.json` | H1 重分析（16 个 cell-feature：功效、定位、联合） |
| `H1_ALL_16_GEOMETRY_COMPLETE.{csv,json}` | H1 全 16 行几何/功效/定位表 |
| `H1_SCENARIO_DIFFERENCES.json` | 两场景 BPI−MOMENTS 差值 + 95% CI |
| `CANONICAL_SUMMARY.json` / `MANUSCRIPT_VALUES.json` | 正文数值汇总 |
| `P1_P3_BOOTSTRAP.json` | P1–P3 bootstrap（旧对象，见下） |

## 旧值说明

`H0_PRIMARY_CONTRASTS.json` 中 `p = 0` 为旧值（加一规则下 p ≥ 1/10001），
现行有效值见 `results/bootstrap/P1_P3_BOOTSTRAP_SUMMARY.json`（tail=0 → p=1/10001，Holm=3/10001）。

## 再生成与校验

```powershell
python scripts/bootstrap_primary_contrasts.py          # 真实 draws → p/CI/Holm
python scripts/bootstrap_primary_contrasts.py --check  # 与已提交产物比对
python scripts/build_tables.py                         # canonical 汇总 → 正文表
python scripts/build_figures.py                        # 表 → 图
```
