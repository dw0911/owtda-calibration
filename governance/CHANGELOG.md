# OW-TDA-CAL-R1 Governance Changelog

> append-only 修订记录（治理层）。科学失效记录另走 INVALIDATION_REGISTRY；
> 本文件只记录治理/规格层变更。commit 列指本仓库提交。

## 2026-09-10 — B01 `OWTDA_CAL_R1_B01_20260910_SCAFFOLD`

- 初始化 `owtda-calibration` 仓库（commit `b11a92f` scaffold）。
- 提交 B01（commit `b1038b4`）：
  - `PROJECT_CHARTER.md`：project_id=owtda-cal-r1、四生存点、证据分级、状态机、批次纪律；
  - `CLAIM_MATRIX_v1.0.csv`：C1–C8，状态全 `UNTESTED`；
  - `manuscript/`：OUTLINE、WRITING_CONSTRAINTS、COLUMN_RECORD（投稿栏目待编辑部咨询）。
- 期刊官网核查：存在「专题征稿 | 拓扑数据分析」（2026-03-06）；详情待填（用户指示暂缓）。

## 2026-09-10 — B02 `OWTDA_CAL_R1_B02_20260910_PRIOR_EVIDENCE_AND_SPEC_SKELETON`

- **旧证据物化**：`external_prior_evidence/DMB_R1/` 收录 DMB-R1 终止归档 25 对象
  （zip SHA256 `38790d48…df933d`；23 内容对象逐字节核验通过）；
  `PRIOR_EVIDENCE_SUMMARY.md` 由 `governance/` 移入该目录（对齐计划 §2.1"旧材料只允许进入 external_prior_evidence"）；
  生成 `archive_manifest.json`（物化清单 + 校验记录）。Charter §5 同步更新。
- **规格骨架（均 draft）**：`PROTOCOL_v1.0.md`、`METHOD_SPEC_v1.0.md`、`SAP_v1.0.md`、`DATA_SPEC_v1.0.md`、
  `CHANGELOG.md`。开放项逐文件列出，冻结（9/23）前关闭。

## 2026-09-10 — B02 补记：计划基线入库

- `OWTDA_CAL_R1_COMPLETE_PLAN_v1.0.md`（2686 行，SHA256
  `dca49727def3d31d2f367d58dba157e782946b862c28d29dd8508a6a3cc19ab3`）复制入仓库根，
  作为本代唯一权威计划基线；README 与 `PROTOCOL_v1.0.md` 引用同步。

## 2026-09-10 — 治理修订：取消编辑部咨询环节（用户指令）

- 本轮不再开展编辑部咨询（原 Plan §23 排程 9/11 项取消）；
- `manuscript/COLUMN_RECORD_20260910.md` 改为"投稿准备期现场核验"基线；
- 风险登记：专题截止日仅用户口径 2026-10-31（未编辑部核验），投稿日 10-28 早于该口径，
  冲突处置见 COLUMN_RECORD §3.4/§4。

## 待登记（未发生）

- 协议正文定稿与 `protocol_content_hash` / `freeze_id` 计算（冻结批）；
- 后续批次（B07+）：scope/index、schema、smoke、PAMAP2 数据、攻击套件、冻结、正式运行等。
