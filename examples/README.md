# examples — 最小可用示例

> 全部示例**只读** `results/canonical/` 与 `artifacts/`，不调用 Monte Carlo，不写任何正式证据。
> 运行：`uv run python examples/<script>`（或先 `uv sync --frozen`）。

| 脚本 | 演示 |
|---|---|
| `minimal_scan.py` | 窗口几何与校准规则的最小演示：`M = floor((T-W)/s)+1`、`p = (tail+1)/(B+1)`、`reject ⇔ exceed ≤ 49` |
| `reproduce_one_h0_cell.py` | 取一个 H0 评价单元，打印 canonical 拒绝率/区间/分类，并用 Wilson 公式独立重算 |
| `reproduce_one_h1_cell.py` | 取一个 H1 cell-feature，打印功效/定位/联合成功，并复算场景差 Δ(BPI−MOMENTS) |

需要端到端（含账本）的复现请看 `reproducibility/RUNBOOK.md` 的 Level 2/3。
