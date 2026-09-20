# DATA_AVAILABILITY — 数据可用性声明

## 1. 一句话

代码、冻结配置、测试、论文源文件、规范化的 canonical 汇总与图表生成脚本随 **GitHub 仓库**分发。
论文的实验是**合成实验**（N-AR / N-CIRCLE 两个数据生成过程），由代码 + 冻结种子程序化生成，
**不需要任何外部数据**即可完整复现（`scripts/reproduce.py`）。正式账本与大型派生索引**不随仓库分发**，
其哈希登记在 `data/manifests/` 供完整性核对；真实数据（PAMAP2）为第三方数据，**不重新分发**。

## 2. 对象与获取方式

| 对象 | 位置 | 获取方式 |
|---|---|---|
| 合成实验数据（N-AR、N-CIRCLE） | 无（程序化生成） | 由代码 + 冻结种子生成（`governance/SEED_REGISTRY_v1.0.json`）；复现合成主线不需要任何外部数据 |
| 正式账本（H0/H1 evaluation + feature，约 3.2 GB） | `data/manifests/formal_ledgers.json` + `external_artifacts.json` | **不随仓库分发**；哈希已登记，如需核对一份副本可用 `scripts/fetch_archived_data.py --verify-only`。复现论文实验不需要账本 |
| 大型派生索引（`ACTIVE_*_INDEX`） | `data/manifests/external_artifacts.json` | 同上；或由冻结计划/种子重生成 |
| canonical 汇总、图、表 | **本仓库**（`results/`、`artifacts/`） | 直接可用；SHA-256 见 `reproducibility/SHA256SUMS` |
| PAMAP2（真实数据） | UCI ML Repository | 自行下载并校验（见 [`../DATA_SOURCES.md`](../DATA_SOURCES.md)）；本代 REAL 线为 `REAL_OMITTED_BY_DATA_GATE`，**复现合成主线不需要** |

> **退出码语义**：`scripts/fetch_archived_data.py --verify-only` 在任一请求对象不可用时返回 **2**，
> 并明确提示"Level 2 无法完成、Level 1 仍可验证"；`--report-only` 只列状态并返回 0。

## 3. 复现路径与数据的关系

- **Level 1（秒级，零数据依赖）**：`python scripts/verify_release.py --level quick` 验证论文全部数值与血缘。
- **Level 3（从头重跑，零数据依赖）**：`python scripts/reproduce.py --phase NULL|ALT --out <DIR>` 用代码 + 冻结种子
  从零重跑 H0/H1 Monte Carlo，产出科学账本后用 `analyse_h0.py --from-ledger` 与 canonical 对账。
- **Level 2（账本重做，可选）**：需要账本副本；账本不随仓库分发，可由作者按需提供。

## 4. 引用要求

使用本仓库时请同时引用（a）软件 release（`CITATION.cff`）与（b）论文。
论文录用或预印本正式发布后补充卷期页码。
