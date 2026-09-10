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

## 2026-09-10 — REAL 线：Data Gate FAIL → omission RC（计划 §24 分流 1）

- 九受试者全 analysis segments 枚举（B11b2/B11b3）：准入 8 受试者、候选 **23 < 24**，
  `subject109` 无候选（`NO_ELIGIBLE_TASK`）→ `REAL_DATA_TASK_GATE` = FAIL；
- 判定为**数据事实**（非实现缺陷），按计划 §24 分流 1：`configs/real/REAL_DISPOSITION_RC.json`
  记 `REAL_OMITTED_BY_DATA_GATE`（stage `REAL_DATA_FROZEN`，reason `TASK_GATE_MIN_TASKS_NOT_MET`）；
- 未下调准入线、未放宽 3000/500 阈值；合成主线不受影响；
- 正式 `REAL_DISPOSITION` append-only 链事件与冻结 reason_code 枚举在 B14 冻结批写入。

## 2026-09-10 — B14a 共同冻结：`OWTDA_CAL_R1_B14a_20260910_COMMON_FREEZE`

- 治理文档升 `FROZEN`：PROTOCOL / METHOD_SPEC / SAP / DATA_SPEC / PROJECT_CHARTER（此后只读，
  变更走 `AMENDMENT_REGISTRY.jsonl`）；
- 冻结对象落库：`SCOPE_SPEC_v1.json`、`PROTOCOL_CONTENT_v1.json`、`ESTIMAND_SPEC_REGISTRY_v1.json`、
  `ANALYSIS_SPEC_v1.0.json`、`COMPUTE_SPEC_v1.json`、`COMPUTE_FREEZE.json`；
- `freeze_id = 7cb4f85e31394b23f6c9d6bcaa9ce6a7fc7b824b2b5c8fb6b600c9181979322d`
  （`evidence_generation_id=G01`，由 protocol/scope/analysis/compute 四个 spec hash 派生）；
- `SCOPE_DESIGN_NULL_*.csv`（112 行）与 `SCOPE_DESIGN_ALT_*.csv`（32 行）由 `freeze_id` 派生；
- `FREEZE_MANIFEST.json` 记录全部对象 hash 与 source/environment manifests（不回灌 `freeze_id`，无环）；
- Git tag `v1.0-freeze-owtda-cal-r1`；
- 校验：`audit/validate_freeze.py` 全 PASS；pytest 362 passed；ruff clean。

## 待登记（未发生）

- B14b：SEED / COMPONENT / SECRET_COMMITMENT registries（root key commitments 与 secret refs）、
  正式 `REAL_DISPOSITION` append-only 链事件（`REAL_OMITTED_BY_DATA_GATE`）；
- 后续批次：blind smoke（G3）、正式 H0/H1 运行、分析冻结、release。
