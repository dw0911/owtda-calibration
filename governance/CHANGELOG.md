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

## 2026-09-10 — B15c H1 alternative DGP + G3 blind smoke（SMOKE_ALT）：`OWTDA_CAL_R1_B15c_20260910_SMOKE_ALT`

- 新增 H1 alternative DGP（`src/owtda_cal/dgp.py`）：`CIRCLE_BASED_H1` 的
  `shape_change`（`τ=⌊T/2⌋` 前 `C(u)=(cos2πu,sin2πu)`、后 `F(u)=(sin2πu,sin4πu)`）与
  `mean_shift`（`+0.5·v·1(t>τ)`，`v=(cos2πV,sin2πV)`，`V∼U(0,1)`）；两变体共享 N-CIRCLE 的
  AR/copula latent 路径与连续观测噪声 `0.08η_t`，latent/noise stream 命名域为
  `{data_generation_id, master_replicate_id}`（排除 alternative/ρ/s/T/M）；
  新增 `shift_direction` 流（每次一个 `float64`，仅 mean-shift 消费）；
- 新增 `build_null_signature(rho, W, s, T, M)`（Plan §7）：H0 与 H1 共用同一 null 模型身份，
  H1 cell 将 effect 置零后精确回到对应 N-CIRCLE H0 的 `null_model_config_hash`；
- **F-B15c-1（修复 B15b 的 smoke 身份域/流合同违规）**：B15b 的 smoke runner 使用 **formal**
  身份函数（`cells.*` / `scope.logical_*`）与 formal 流 kind/字段
  （`null_*`、`{data_generation_id, DGP_family, master_replicate_id}`），违反 §16
  「smoke 使用完全独立的身份域，禁止借用 formal logical IDs」、§9.3「`stream_kind` 必须以
  `smoke_` 开头」与 §15.2 smoke 字段表。本批新增 `src/owtda_cal/smoke_ids.py`（§16 全部 12 个
  `smoke_*` ID 与流字段构造），`smoke.py` 全量改走 smoke 命名空间，并在
  `audit/run_smoke.py` 增加 **formal ID 泄漏检查**（§16 要求 validator 必须拒绝）；
  ledger 增加 `experiment_id` / `feature_sufficient_id` / `evaluation_id` / `scenario_id` 列；
  **B15b 的 S01 smoke 证据作废**；
- **smoke generation `S01` → `S02`**（§9.3 umbrella 规则：新增 DGP 必须整体提升并重跑两 phase）；
  phase root key 保持不变（generation 经流 payload 进入派生），
  `scope.SMOKE_GENERATIONS_SUPERSEDED = ("S01",)`；
- **§15.2 流表增行 `smoke_shift_direction`**（smoke 版 `shift_direction`，字段同其它 smoke 数据流）；
- 新增 `SYNTHETIC_CIRCLE_BASED_H1_V1` 数据组件（COMPONENT_REGISTRY 6 → 7 条）；
  `audit/validate_freeze.py` 的组件条目检查改为「与 `components.component_definitions()` 一致」
  （避免新增组件后留下过期 registry）；
- 新增 `audit/run_worker_sweep.py`（`w*` 确认）与 `audit/run_smoke.py --phase`
  （两 phase 盲 smoke + `identity_closure`）；
  `tests/test_h1_dgp.py`（36）/`tests/test_smoke_ids.py`（14）/`tests/test_smoke.py`（11 → 17）；
- **G3 blind smoke 实跑（8 workers，S02）**：SMOKE_NULL **896 / 3,584 / 73,600**
  （`t_0,32 = 842.03 s`）、SMOKE_ALT **256 / 1,024 / 49,152**（`t_1,32 = 272.52 s`）；
  两 phase 均 **0 未解释 error、0 缺字段、0 formal ID 泄漏、身份闭合**；无禁止聚合输出；
- **§9.4 完整判定 23/23 PASS**：`t_H0_hat = 22.842 h ≤ 192 h`、`t_H1_hat = 4.731 h ≤ 76.8 h`、
  `t_core_hat = 27.573 h ≤ 268.8 h`；总 peak RSS = **1.393 GiB ≤ 24 GiB**；swap 增量 = 0；
  `estimated_peak_disk = 386.1 MiB ≤ 0.8 × 455.6 GiB`；`open_runs = 0`；
- **`w*` 未确认（决策待定）**：worker 扫描（两 phase × workers{1,4,8,10,12}，replicates=8）显示
  **所有 worker 数下 evaluation-row payload 逐位一致**（`worker_consistency` 成立），但吞吐
  **w=12 最高**（H0 `+8.1%`、H1 `+6.3%` 相对 w=8，均超 §9.4 的 2% 并列阈值），
  故 §9.4 规则指向 `w*=12`，与冻结的 `COMPUTE_SPEC.w_star=8` 不符。
  由于 `w_star` 是 `compute_spec_hash` → `freeze_id` → SCOPE_DESIGN/全部合成身份的输入，
  **未作单方面修改**，需走 amendment + 重新冻结决策（见 B15c VALIDATION_REPORT §5）；
- 冻结科学内容不变：`freeze_id`、五类 spec hash、`SCOPE_DESIGN_NULL/ALT` 行与 hash、
  REAL 链 tip 不变；tag `v1.0-freeze-owtda-cal-r1` 仍指向 `e16222f`；
  变更的是 component 条目集合、smoke 规模/身份域与其派生的 component/run 身份。
- smoke 行仅作运行证据（`artifacts/smoke/<phase>/`），**永不进入论文**。

## 2026-09-10 — 审计提交（归档）：`OWTDA-CAL-R1-AUDIT-SUBMISSION-20260910`

- 归档包 `artifacts/archive/OWTDA-CAL-R1-AUDIT-SUBMISSION-20260910.zip`（313 对象；
  SHA256 见同名 `.zip.sha256` sidecar 与 `_incoming/OWTDA_CAL_R1_AUDIT_SUBMISSION_20260910/`），
  自包含且逐字节可验证（`package_manifest.json` + `SHA256SUMS.txt`，构建时自校验 0 mismatch）；
- 内容：被审计工作树（`repo/`，排除 `secrets/`、缓存与既往归档）、冻结源域 manifest 与复算
  `source_tree_hash`、git 状态、6 个 Gate 对象（JSON 权威 + 渲染 MD）、受理记录/审计请求/
  问题与待决断登记、被作废的 S01 smoke 证据、以及 B01–B15c 全部交付四件套（`batches/`）；
- Gate 判定：`G0-FREEZE-CHAIN-AND-IDENTITY` **PASS**、`G3-BLIND-SMOKE-BOTH-PHASES` **PASS**、
  `SECTION-9-4-COMPUTE-BUDGET` **PASS**、`H1-ALTERNATIVE-CONSTRUCT-CONTRACTS` **PASS**、
  `W-STAR-CONFIRMATION` **FAIL_UNCONFIRMED**（待裁定）、
  `SOURCE-REVISION-ADMISSIBILITY` **BLOCKED_PENDING_OPERATOR_ACTION**（待具名 commit）；
- 登记 **问题 8 项**（含 F-B15c-1 的定性与影响面、F-B15c-4 的 source_tree_hash 覆盖风险、
  w* 未确认、revision 未提交、wall 抖动与 w=10 swap 观测、REAL omission 状态）与
  **待决断 5 项**（D-1 w*、D-2 B15b 撤回、D-3 amendment 登记、D-4 smoke_ids 归属、D-5 具名 commit）；
- 新增 `scripts/build_audit_submission.py`：**刻意置于冻结源域（`src/`/`configs/`/`audit/`）之外**，
  使"打包已冻结状态"这一动作永远不会扰动它所打包的哈希；
- 新增 `scripts/export_audit_submission.py`：把密封包导出为单一可浏览文件夹
  （`package/` 为解压原文、外加密封包与其 SHA256 sidecar、`00_START_HERE.md` 交接说明与
  提交文档），并在导出后原地重新逐项校验（`EXPORT_VERIFY.json`）；交接说明
  `artifacts/archive/OWTDA-CAL-R1-AUDIT-SUBMISSION-20260910_HANDOVER.md` 按同一策略
  **不进入密封包**，以保证包体是纯证据对象；
- 冻结科学内容不变：`freeze_id`、五类 spec hash、`SCOPE_DESIGN_NULL/ALT`、REAL 链 tip、
  tag `v1.0-freeze-owtda-cal-r1` 均未移动；本条目属治理层归档记录，不进入 `source_tree_hash`。

## 2026-09-10/11 — 审计补件 R1：`OWTDA-CAL-R1-AUDIT-SUPPLEMENT-R1-20260910`

审计裁定（材料准入层）要求补件，原 B15c 包保持只读。本轮关闭 P0-1..P0-7：

- **P0-2 真实环境锁**：`pyproject.toml` 补齐实际直接依赖（`ripser`、证据工具 `psutil`）并
  生成 `uv.lock`；`scripts/frozen_env.py` 在**解释器启动前**设定四个 BLAS/线程变量为 `"1"`
  并留证（`environment/thread_env.json`，before/after import 均观测为 `"1"`）；
  `environment/` 收录版本、BLAS、`pip freeze`、`python -VV`、并在**仓库外全新目录**跑通
  `uv sync --frozen`（`environment_rebuild_test.json`）；`environment_lock_hash` 现覆盖
  `pyproject.toml`、`uv.lock`、版本/OS/CPU/BLAS/线程设置。旧环境（`ripser` 未声明、线程变量
  unset）下的时间/内存/预算结果**降为历史诊断**；
- **P0-3 `w*` 正式确认**：预登记协议 `configs/wstar/WSTAR_CONFIRMATION_PROTOCOL.json`
  先于测量入 git（`df17eb1c…`），两 phase 各 3 次配对、顺序固定 `8→12,12→8,8→12`、全长
  32-replicate、中位数裁决。结果：**12 组 payload 逐位一致**、error=0、RSS≤24 GiB；
  `SMOKE_ALT` **CONFIRMED**（w=12 比 w=8 快 12.7%），`SMOKE_NULL`
  **VOIDED_ACCEPTANCE_CONDITION_FAILED**（一次运行出现 4 MB swap 增量）。按协议
  「任一验收条件失败即作废且**不得重跑改善数字**」⇒ **不采纳新值**，冻结 `w* = 8` 维持，
  `COMPUTE_SPEC.w_star_source` 显式记录该判定；更换 w* 需新的预登记；
- **P0-4 严格 schema**：`configs/schema/` 七个对象（`scientific_row` / `_wire`、
  `feature_sufficient_row` / `_wire`、两个 result projection、`schemas_manifest`），
  discriminator = `row_type × phase × DGP_family × scenario_id × feature_id × method_id`
  （24 variants）；全部对象拒绝未知字段、required-null 必须显式写入、浮点仅走
  `f64:<16 hex>`；`audit/validate_schemas.py` **60 项 ALL_PASS**，golden row payload hash
  `3a9f2e8a…`，`tests/test_schemas.py` 35 项锁定 round-trip / golden / 拒绝语义；
- **P0-5 amendment/invalidation 链**：`AMENDMENT_REGISTRY.jsonl`（5 事件：环境锁修正、
  §15.2 `smoke_shift_direction` 增行、worker 确认规则、代次提升 S02→S03、w* 采纳判定）与
  `INVALIDATION_REGISTRY.jsonl`（S01 作废、S02 降为 pre-freeze historical evidence，另
  追加 v1.1 冻结标签被取代）均为 `prev_event_hash` 哈希链；
  `governance/reasons/` 收录全部 reason 对象；`B12_DISPOSITION.json` 显式处置：编号 B12
  从未使用（无交付、无 commit、无引用），无遗漏证据；
- **P0-6 sealed S03 smoke**：smoke generation 由 `S02` 提升为 `S03`（`S01`/`S02` 均登记
  superseded），两 phase 重跑并封 seal（`SMOKE_SEAL_SMOKE_NULL/ALT.json`，绑定 ledger
  content hash、`source_tree_hash`、`environment_lock_hash`、最终 `w*`、run component set、
  smoke generation、计数/零错误/终态）；新增 `RUN_REGISTRY.jsonl` / `STATE_REGISTRY.jsonl`
  与 `provenance_manifest.json`；`open_runs` 改为从注册表最新状态推导，**注册表缺失或为空
  一律 FAIL**（`MISSING_RUN_REGISTRY` / `EMPTY_RUN_REGISTRY`），禁止用空文件绕过；
  实测 SMOKE_NULL `955.83 s`（0 error）、SMOKE_ALT `275.50 s`（0 error）、`open_runs=[]`；
- **P0-7 原始测试证据**：`verification/`（`pytest_full.log`+`.xml`、`ruff_check.log`、
  `commands.jsonl`、`validation_exit_codes.json`、`validation_environment.json`），
  全部在冻结 venv 与冻结 commit 上重跑：**506 passed**、ruff **All checks passed**；
- **P0-1 Git 冻结身份**：`revision/`（`OWTDA-CAL-R1.bundle` 独立 verify、`git fsck --full`
  无错、`git_status_porcelain_v1.txt` 与 `git_stash_list.txt` **零字节**、
  `identity_check_*.json` `all_pass=true`、source manifest 可从冻结 commit 重算）；
  证据一律输出到**仓库外**，避免"生成干净证明又弄脏仓库"的循环；
- **顺序缺陷与修正（透明披露）**：第一次补充序列在 commit **之前**重建冻结，使
  `RUN_COMPONENT_SET.compute_git_commit` 指向的 revision 不含实际运行源码（与被驳回的 S02
  同因）。修正为「先提交源码 → 再重建 → 后运行」，并在新 revision 上重建与重跑；
  第一次冻结的 tag `v1.1` 保留不删除但由 `v1.2-freeze-owtda-cal-r1` 取代
  （登记为 `INV_V11_FREEZE_TAG`）；`v1.2` 亦在同一未闭合步骤内、于最终 lint-clean revision
  上重建一次（此前一次创建对应 revision 尚含一条未用 `noqa` 的 lint 发现）；
  **`v1.0-freeze-owtda-cal-r1` 始终未移动**；
- 新增工具：`audit/run_wstar_confirmation.py`、`audit/build_schemas.py`、
  `audit/validate_schemas.py`、`audit/build_governance_registries.py`、
  `audit/append_invalidation.py`、`audit/run_registry.py`、`audit/run_smoke_s03.py`、
  `audit/collect_git_identity.py`、`audit/collect_verification.py`、
  `audit/build_environment_evidence.py`、`scripts/frozen_env.py`、
  `scripts/run_supplement_sequence.py`（均置于冻结源域之外或仅审计侧）；
- 未闭合：`w*` 仍为 8 且确认作废（需新预登记）；`§9.4` 预算在新环境下按 S03 重算但**仍为
  PROVISIONAL**（正式 L2 未开始）；`PAMAP2 恰 23 个合格任务` 在缺原始数据时只能标记
  `UNVERIFIED_EXTERNAL_DATA_FACT`。

## 2026-09-11 — 补件后处置：fail-closed 冻结守卫、H1 复审包、`w*` 决定与并行度解耦提案

对应审计建议 A/B/C/D 的落地（证据标签 `v1.2-freeze-owtda-cal-r1`）：

- **D（fail-closed 冻结守卫，已生效）**：新增 `audit/repo_guard.py`；
  `audit/build_freeze.py` 与 `audit/build_run_admission.py` 在写出**任何字节之前**调用
  `assert_clean_frozen_scope`——若 `src/ configs/ audit/` 存在已修改、已暂存未提交或未跟踪
  的文件即**拒绝构建**；「无法证明干净」一律视为不干净（非 git 目录/取不到状态同样拒绝）。
  `SOURCE_TREE_PREFIXES` 改为由 `repo_guard.FROZEN_SCOPE_PATHS` 派生（单一事实来源，
  守卫与被哈希的范围永不漂移）。动机：同类**静默漏项**已发生两次——S02 的
  `compute_git_commit` 指向不含实际源码的 revision、F-B15c-4 的 `source_tree_hash` 漏掉未
  `git add` 的新模块。测试 `tests/test_repo_guard.py` 12 项（在临时仓库上验证拒绝语义，
  不依赖被运行时的仓库状态）；
- **C（H1 复审包，已生成）**：新增 `audit/build_h1_review_packet.py` →
  `governance/H1_CONSTRUCT_REVIEW_PACKET.{json,md}`，回答审计项
  `H1-ALTERNATIVE-CONSTRUCT-CONTRACTS = PENDING_CODE_REVIEW`。受审函数按**源码文本 SHA256**
  固定；8 条构造合同**全部 PASS**，含：§12.4 builder 阻塞门（`τ_true = τ + 1/2` 精确等于
  k=96 候选窗口中心，逐 H1 几何）、两映射的均值/协方差在 trapezoid 意义下**精确相同**
  （`0` 与 `½I₂`，机器精度而非 MC）、raw 序列与文档化组合**逐位相等**、RNG 消费形状
  `(), [13288], [12288,2]`、共享 latent/noise、8 个 H1 cell → 4 个 null signature；
  引用不存在的测试会自判 `MISSING_TEST`/FAIL；并显式列出**刻意不作的声明**
  （无二阶过程匹配、H1 不复用 H0 抽样、不含任何 L2 结论）。
  测试 +3：`test_tau_true_is_the_k96_candidate_centre`、
  `test_the_two_maps_share_mean_and_covariance`、
  `test_short_length_is_a_bitwise_prefix_of_the_long_length`。
  过程中修正了两处我自己先前的**过强表述**：跨 `T` 的 raw 序列**只在前段**一致（变点是
  cell 级属性，后段按设计不同）；骨架从 raw 反解只到 float64 舍入（`≈1e-16`），
  逐位相等只对「raw = skeleton + 0.08η」这一组合成立；
- **A（`w*` 处置，已定）**：冻结值**维持 `w* = 8`**、不采纳 12。理由：预登记协议含「无 swap
  增长」验收条件，`SMOKE_NULL` 因一次 4 MB swap 判 `VOIDED`，协议明禁重跑改善数字，
  采纳 12 等于推翻自身验收规则；且无任何 Gate 结论依赖该取值。记录见
  `governance/AMENDMENT_PROPOSAL_PARALLELISM_DECOUPLING.md` §1；
- **B（并行度解耦提案，未生效）**：提案把并行度从 `compute_spec_hash` 覆盖面移出，只冻结
  「线程变量=1 + 逐位不变性 + 资源验收」这一**契约**，实际 `workers_used` 每 run 记录
  （同上 §2）。**未改动任何身份**，需裁定；采纳应在正式 run 之前完成；
- 全量 **521 项测试通过**、ruff **All checks passed**；随后按「先提交源码 → 再重建 →
  后运行」的纪律重建冻结并重跑 S03。

## 待登记（未发生）

- **B 提案裁定**（并行度解耦：采纳则需在正式 run 前重建 + 新建 `v1.3`）；
- B15d：NULL/ALT phase 的 expected indexes（ID-only pass）与 G4 admission 收尾；
  正式 H0/H1 run 的 runner 与 phase seal 链；
- 后续批次：正式 H0/H1 运行、分析冻结、release。
