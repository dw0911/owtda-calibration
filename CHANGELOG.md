# Changelog

> 本仓库的**权威变更记录**是治理层的 append-only 链：**`governance/CHANGELOG.md`**
> （逐批次记录 B01…、冻结标签 v1.0→v1.5、缺陷与修正、审计裁决等，含时间与依据）。
> 本文件仅作为 GitHub 惯例入口，不复制其内容以避免双份维护。

## 公开发布快照

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
