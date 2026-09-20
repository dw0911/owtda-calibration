# DATA_AVAILABILITY — 数据可用性声明

## 1. 一句话

代码、冻结配置、测试、论文源文件、规范化的 canonical 汇总与图表生成脚本随 **GitHub 仓库**分发；
体积较大的正式账本与大型派生索引不随仓库分发，登记在 `data/manifests/external_artifacts.json`
（大小 + SHA-256 + seal 绑定），DOI 在 Zenodo 归档创建后填入；真实数据（PAMAP2）为第三方数据，
**不重新分发**，出处与逐文件 SHA-256 见 [`../DATA_SOURCES.md`](../DATA_SOURCES.md)。

## 2. 对象与获取方式

| 对象 | 位置 | 获取方式 |
|---|---|---|
| 合成实验数据（N-AR、N-CIRCLE） | 无（程序化生成） | 由代码 + 冻结种子生成；复现合成主线不需要任何外部数据 |
| 正式账本（H0/H1 evaluation + feature，约 3.2 GB） | `data/manifests/formal_ledgers.json` | `python scripts/fetch_archived_data.py`（Zenodo DOI，**待登记**）；本地已存在时 `--verify-only` 校验 |
| 大型派生索引（`ACTIVE_*_INDEX`，6 个文件） | `data/manifests/external_artifacts.json` | 同上；或由冻结计划/种子重生成 |
| canonical 汇总、图、表 | **本仓库**（`results/`、`artifacts/`） | 直接可用；SHA-256 见 `reproducibility/SHA256SUMS` |
| PAMAP2（真实数据） | UCI ML Repository | 自行下载并校验（见 `../DATA_SOURCES.md`）；本代 REAL 线为 `REAL_OMITTED_BY_DATA_GATE` |

> **退出码语义（P0-6）**：`scripts/fetch_archived_data.py --verify-only` 在任一请求对象不可用时返回 **2**，
> 并明确提示"Level 2 无法完成、Level 1 仍可验证"；`--report-only` 只列状态并返回 0。
> 归档就绪后该命令必须返回 0，否则视为发布门未闭合。已登记的 `local_source` 既可以是文件本身，
> 也可以是包含该文件的目录（按 `filename` 解析）。

## 3. DOI 登记流程（发布顺序）

1. 整理 `main` → 2. 本地完成 quick / analysis 两级验证 → 3. CI 全绿 → 4. 冻结 commit →
5. 创建 annotated tag `v1.0.0-paper` → 6. 创建 GitHub Release → 7. 连接 Zenodo 自动归档该 release（得到**代码 DOI**）→
8. 另建 Zenodo dataset record 上传账本与大型索引（得到**数据 DOI**）→
9. 更新以下三处：`CITATION.cff`（`doi` / `repository-code`）、`data/manifests/external_artifacts.json`（`deposit.doi`）、
`reproducibility/RELEASE_MANIFEST.json`（`code_doi` / `data_doi`）→ 10. 如需再发 `v1.0.1` 仅补引用信息。

> 在 DOI 尚未分配前，`CITATION.cff` 与清单中一律写 `PENDING`/`null`，**不得填写虚构 DOI**。

## 4. 引用要求

使用本仓库时请同时引用（a）软件 release（`CITATION.cff`）与（b）论文；若使用了归档账本，再引用数据 DOI。
论文录用或预印本正式发布后补充卷期页码。
