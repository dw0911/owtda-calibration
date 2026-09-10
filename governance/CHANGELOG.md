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

## 2026-09-10 — B14b 冻结收尾：`OWTDA_CAL_R1_B14b_20260910_REGISTRIES_AND_REAL_DISPOSITION`

- `SEED_REGISTRY_v1.0.json`：13 entries（smoke 两 phase、NULL data/M0/M1、ALT data/M0/M1、
  REAL_TASK_BUILD 两项、REAL_PREDICTION 两项、ANALYSIS bootstrap），按七元组 ASCII 排序；
  合成 root keys 明文入库（计划 §16.1 规定），`real_task` / `real_task_id_salt` 仅登记
  `secret_ref` + `root_key_commitment`（明文存于 git-ignored `secrets/REAL_TASK_SECRETS.local.json`）；
- `COMPONENT_REGISTRY_v1.json`：6 entries（2 data + 2 feature + 2 method），
  `config_hash` 用无 run 参数的生成器/特征/方法配置，`code_file_manifest_hash` 逐文件清单；
- `SECRET_COMMITMENT_REGISTRY_v1.0.json`：`entries=[]`、`reveal_events=[]`
  （REAL 在 task index 形成前即 omitted，不得铸造 salt）；
- `REAL_DISPOSITION.jsonl`：genesis + `REAL_OMITTED_BY_DATA_GATE`（stage `REAL_DATA_FROZEN`、
  `reason_code=TASK_GATE_MIN_TASKS_NOT_MET`、`task_index_seal_hash=null`、`truth_unsealed=false`），
  reason 对象 `REAL_DISPOSITION_REASON_71144c33….json`（8 受试者 / 23 任务 / 需 24）；
- `FREEZE_MANIFEST.json` 增记三类 registry snapshot hash 与 REAL 链 tip；
- `audit/validate_freeze.py` 扩展至 **33 项**（含 registry 主键/排序/快照重算、REAL 链重放与 truth 封闭）；
- 代码：`src/owtda_cal/components.py`、`src/owtda_cal/disposition.py`；测试 `tests/test_disposition.py`。

## 2026-09-10 — B15a run 身份层：`OWTDA_CAL_R1_B15a_20260910_RUN_ADMISSION`

- 新增 `src/owtda_cal/runs.py`：`RUN_COMPONENT_SET`（严格字段白名单、四类 refs 排序唯一）、
  `RUN_INPUT_BINDINGS`（JSONL 字节 + content hash）、三类 expected index（字段全 64-hex、主键唯一、
  排序、三层闭合）、`run_instance_id`、`RUN_SEAL` payload/hash、三个独立 domain 的 id-set hash；
- `scope.scope_design_rows` 支持 `SMOKE_NULL` / `SMOKE_ALT`（同格结构、128 replicates、独立 phase 身份）；
  NULL/ALT 既有行与 hash **不变**；
- 新增 `governance/SMOKE_CONFIG_v1.json`（128 reps/cell；3,584/1,024 smoke evaluations；不输出拒绝率）；
- 生成 `RUN_COMPONENT_SET_<hash>.json` 与 `RUN_INPUT_BINDINGS_<hash>.jsonl`：
  `SMOKE_NULL`（112 行 design / 9 bindings）、`SMOKE_ALT`（32 / 9）、`NULL`（112 / 8）；
  **ALT 的 component set 按设计延后**（`parent_phase_seal_hash` 必须是权威 H0 phase seal）；
- `FREEZE_MANIFEST.json` 增记 `smoke_config_hash` 与 `run_admission` 块，并刷新
  `source_tree_hash`（计划 §16.2 允许冻结时"另行绑定最终 source/component/environment manifests"）；
- 新增 `audit/build_run_admission.py`、`audit/validate_runs.py`（G4 前置，28 项 PASS）、
  `tests/test_runs.py`（27 项）。
- 冻结科学内容未变：`freeze_id`、五类 spec hash、三类 registry、`SCOPE_DESIGN_NULL/ALT`、REAL 链 tip 全部不变；
  tag `v1.0-freeze-owtda-cal-r1` 仍指向 `e16222f`。

## 2026-09-10 — B15b G3 blind smoke（SMOKE_NULL）：`OWTDA_CAL_R1_B15b_20260910_SMOKE_NULL`

- **B15a 数值修正（透明披露）**：smoke 的 replicates/cell 应为 **32**（计划 §9.3：H0 896 data units、
  3,584 rows、73,600 PH 窗口 = 128 master paths × 575），B15a 误写为 128 并据此生成过 smoke 对象；
  本批修正 `R0_SMOKE=32`、`SMOKE_CONFIG`（新增 data units / PH windows / `smoke_` 前缀 /
  `smoke_generation_id=S01`），并**删除**旧 smoke 的 SCOPE_DESIGN CSV 与 RUN_COMPONENT_SET/bindings 后重建；
- **component `code_files` 完整性修正**：原清单遗漏 resampler 的 `scan.py` 与 RNG/ID 依赖
  （`seeding.py`/`canonical.py`/`identity.py`/`hashing.py`），已补齐并重建 COMPONENT_REGISTRY 与
  RUN_COMPONENT_SET（`SMOKE_NULL=aad291fc…`、`SMOKE_ALT=4a31e21b…`、`NULL=7f021ed4…`）；
- 新增 `src/owtda_cal/smoke.py`（SMOKE_NULL runner；master×feature 粒度并行；PH 窗口逐 master 恰好
  计算一次 = 73,600；stream_kind 全部 `smoke_` 前缀）、`audit/run_smoke.py`、`audit/validate_admission.py`、
  `tests/test_smoke.py`（11 项）；`calibrate.py` 的 stream_kind 参数化（默认值不变）；
- **G3 smoke 实跑**（8 workers）：896 data units / 3,584 evaluation rows / 73,600 PH 窗口、
  **0 未解释 error**、0 缺字段、无禁止聚合输出；`t_0,32 = 1019.56 s`；
- **§9.4 三项 Gate（H0 部分）**：wall `t_H0_hat = 27.657 h ≤ 192 h` ✓；
  总 peak RSS（父+workers）= 1.486 GB ≤ 24 GiB ✓；run 期间 swap 增量 = 0 ✓；
  磁盘 `estimated_peak_disk = 230.4 MiB ≤ 0.8 × 455.6 GiB` ✓；`open_runs = 0` ✓；
- 冻结科学内容仍未变：`freeze_id`、五类 spec hash、`SCOPE_DESIGN_NULL/ALT`、REAL 链 tip 不变；
  变更的是 registry 的 `code_files` 清单与其派生的 component/run 身份（记录于本条目）。
- smoke 行仅作运行证据（`artifacts/smoke/SMOKE_NULL/`），**永不进入论文**。

## 待登记（未发生）

- B15c：SMOKE_ALT 实跑（H1 alternative DGP：§12.1 形状变化 / §12.2 mean shift）+ `t_1,32` +
  §9.4 完整判定（`t_H1/t_core`）+ `w*` 最终确认；
- 后续批次：正式 H0/H1 运行、分析冻结、release。
