# Changelog

> 本仓库的**权威变更记录**是治理层的 append-only 链：**`governance/CHANGELOG.md`**
> （逐批次记录 B01…、冻结标签 v1.0→v1.5、缺陷与修正、审计裁决等，含时间与依据）。
> 本文件仅作为 GitHub 惯例入口，不复制其内容以避免双份维护。

## 公开发布快照

### 2026-09-20 — 公共树精简（作者要求：推送包只含复现所需，不多不少）

- **剔除 156 个历史过程文件**（676 → 401 个跟踪文件），科学内容与复现链**不受影响**：
  - `release/` 交付包原始副本（仅保留 `release/analysis/scripts/` 的 H1 重分析脚本）；
  - `artifacts/audit|archive|smoke/`（冻结/身份/准入检查快照、旧审计 ZIP、smoke 工程证据）；
  - `external_prior_evidence/`（旧代 DMB-R1 归档，不参与本代估计）；
  - `governance/` 过程登记项 129 个（冻结未引用的 RUN_COMPONENT_SET/RUN_INPUT_BINDINGS/SCOPE_DESIGN 实例、
    预注册/结果记录、reasons/ 等）；
  - 一次性构建器 13 个（审计提交包打包/校验、环境/身份/准入收集器等）；
  - `AUDIT_SUBMISSION_SUMMARY.md`。
- **保留判据**：被测试或入口脚本**实际导入/引用**、被 `FREEZE_MANIFEST` **点名**、或为论文数值/血缘所必需；
  剔除名单与原因逐项登记在 [`EXCLUDED_ARTIFACTS.csv`](EXCLUDED_ARTIFACTS.csv) → `PRUNED_FROM_PUBLIC_TREE`。
- **恢复判据（闭包）**：凡被留存文件引用（含运行时拼接路径，如 `REAL_DISPOSITION.jsonl` → reason 对象、
  `audit/check_active_indexes.py` → `artifacts/summaries/PHASE_SEAL_*.json`）的文件一律保留。
- 修正 `scripts/frozen_env.py` 文档示例与 `.gitattributes` 中对已删文件的残留引用；
  `EXCLUDED_ARTIFACTS.csv` 中指向 `release/*/RUN_SEAL.json` 的备注改为 `artifacts/seals/<phase>/RUN_SEAL.json`。
- 全量校验在精简树上通过：`pytest` 1069 passed / 1 skipped、`ruff` 全清、`verify_release` 28/28 与 31/31、
  表生成链 5/5、图件血缘 24/0、账本 6/6、发布 dry run 0 差异。

### 2026-09-20 — 许可/作者定稿与账本归档（发布门闭合，未推送）

- **三项许可定稿**（作者确认）：代码 **MIT**（根 `LICENSE`）、本项目结果数据 **CC BY 4.0**
  （`LICENSES/DATA_LICENSE.txt`）、论文源文件与 PDF **CC BY 4.0**（`LICENSES/PAPER_LICENSE.txt`）；
  `CITATION.cff` 的 `license` 同步为 `MIT`，并注明三对象划分。
- **作者定稿**：**王平（Wang Ping），河北金融学院与数据科学学院，13088010056@163.com**；
  已同步 `AUTHORS.md`、`CITATION.cff`（含 `affiliation`/`email`）与 `paper/main.tex` 的 `\author{}`（三处一致）。
- **账本归档（本地完成，DOI 待登记）**：四份正式账本 + 两组大型索引（合计 **3.67 GB**）逐项校验；
  两组索引打包为**确定性 tar**（`mtime=0`、成员排序、无 uid/gid），真实 SHA-256/大小与三份成员的逐文件哈希
  已登记进 `data/manifests/external_artifacts.json`；`scripts/fetch_archived_data.py --verify-only`
  在本机返回 **0（6/6 verified）**。上传材料（Zenodo 元数据 + 步骤 + 逐文件清单）见工作区
  `OUTPUTS/data_archive_20260920/`；上传后把 DOI 回填清单与 `RELEASE_MANIFEST.json` 的 `doi.data` 槽位。
- **修正一处登记错字**：`EXCLUDED_ARTIFACTS.csv` 中 `ACTIVE_EVALUATION_INDEX_c89c90…` 的 SHA-256
  转录有误（`…dfdeccf86d…` → 实际 `…dfdecff86d…`），已按文件实际值修正（文件本身完整，首尾行均为合法 JSON）。
- **修正 H1 账本寻址**：两份 H1 账本的 `local_source` 由运行目录改为实际文件路径，此前导致
  `--verify-only` 把目录当文件并误报 `SIZE MISMATCH`。
- **本轮不推送**：仓库保持在本地就绪状态（tag `v1.0.0-paper` 可重建），全部校验在本地完成；
  是否公开与何时推送由作者决定。

### 2026-09-20 — 外部审计修复轮（发布阻断项闭环）
- 依据独立的 GitHub 发布包审计（裁决 `HOLD_PUBLIC_PUSH`，8 项 P0）完成修复，**科学结果未变**：
  H0/H1 canonical、P1–P3（0.5354 / 0.5330 / 0.0266，tail=0，Holm = 3/10001）与 Wilson 区间全部保留，未重跑任何 Monte Carlo；
- P1–P3 的 `--check` 改为**语义比较**（JSON 解析对象 + npz 按 key/dtype/shape/逐元素），跨平台不复因行尾或 ZIP 元数据失败；
  `.gitattributes` 区分字节封存区（`-text`）与文本区（LF），重规范化 133 个文件、零越界；
- 论文 CI 改为在 `paper/` 工作目录编译并启用**严格模式**（缺图件/缺表/未定义引用直接失败），正文表 1–5 改由
  `paper/scripts/make_tables.py` 生成、正文 `\input` 引用；图件修正 Figure 2 位移长度、Figure 4 零中心色尺与图例、
  Figure 5 场景映射，并解析可确定的 CJK 字体（`Noto Sans SC`，CI 用 `fonts-noto-cjk`）；
- 新增确定性的 `reproducibility/RELEASE_MANIFEST.json`；`SEED_MANIFEST.csv`/`FORMAL_MANIFEST.json` 的溯源字段改为
  `freeze:<freeze_id>`，使"重生成后工作区零差异"成立（发布 job 的 `git diff --exit-code` 现在通过）；
- 账本入口 `fetch_archived_data.py --verify-only` 在归档缺失时返回 **2**（不再静默成功）；README/RUNBOOK 明确
  Level 1 与 Level 2 的可验证范围；
- 发布标签：annotated tag **`v1.0.0-paper`**，与 `CITATION.cff` 的版本口径统一；库版本 `pyproject.toml` 仍为 0.1.0（冻结对象，不改）。
- 仍待作者决策（public 前置）：代码/数据/论文三项许可与作者名单（见 `LICENSE`、`AUTHORS.md`），以及账本归档 DOI。

### 2026-09-20 — 论文配套发布快照（R5-paper 阶段）
- 正式 H0/H1 运行已封存并保留（见 `artifacts/seals/`、`release/`；计数 280,000 / 51,200 evaluation 行）；
- 论文修订（R1）与图表重构（5 图 4 表）进行中；本快照含当前论文源码与 canonical 图表数据；
- 发布集说明：代码 + 冻结配置 + 治理与身份链 + 论文 + 小型证据；
  3.4 GB 原始账本与 6 个大索引不随仓库分发（出处与哈希见 `REPRODUCIBILITY.md`、`EXCLUDED_ARTIFACTS.csv`）。
