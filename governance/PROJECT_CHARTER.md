# OW-TDA-CAL-R1 PROJECT CHARTER

> 版本：v1.0（B14a 共同冻结，2026-09-10）
> 状态：`PROTOCOL_FROZEN`（B14a 闭合后生效）
> 权威计划：`OWTDA_CAL_R1_COMPLETE_PLAN_v1.0.md`（2026-09-09 定稿，本代唯一计划基线）

---

## 1. 项目身份

| 项 | 值 |
|---|---|
| 项目名（中文） | 重叠滑动窗口下拓扑扫描检验的交换性失效与校准边界 |
| 项目名（英文） | Exchangeability Failure and Calibration Boundaries of Topological Scans with Overlapping Windows |
| 项目标识 | `OW-TDA-CAL-R1` |
| `project_id`（canonical ASCII） | `owtda-cal-r1` |
| `protocol_id` | 由 `PROTOCOL_v1.0.md` 正文内容哈希确定（协议定稿时登记；B01 未定稿） |
| `evidence_generation_id` 初代 | `G01` |
| 目标期刊 | 《山东大学学报（理学版）》"拓扑数据分析"专题 |
| 专题投稿截止 | 2026-10-31（编辑部未确认前以咨询为准） |
| 目标投稿日 | 2026-10-28 |
| 计划文档状态 | 方案定稿；冻结日 2026-09-23 |

`project_id` 与 DMB-R1（旧代 `bpi-scan` / 方法线 DMB-R1）完全不同，两代 ledger、
registry、seed、统计对象一律禁止混入。

## 2. 科学目标：四项生存点

1. **交换性失效的精确反例**（T2）：即使原样本 IID、窗口边际同分布，重叠窗口统计量也不必然可交换。
2. **窗口均值例的协方差错配**（T3/T4）：真实长期协方差与 naive permutation 保留的边际协方差严格错配（`Ω=qΓ0 ≠ Γ0`，`W=qs,q>1`）。
3. **全新种子下的 fixed-M / fixed-T 有限样本校准图谱**：28 个 H0 格 × 2,500 replicate、8 个 H1 格 × 1,600 replicate，冻结后一次完成。
4. **可从空环境重建的完整证据链**：身份/ledger/seal/表图逐字节可重放，R0–R4 复现分级。

任一校准器数值表现只改变论文结论，不决定实验合法性。代码、身份、数据、种子、
账本或"统计量—理论"对应出现错误时，实验进入阻断状态。

## 3. 本代明确排除（不得恢复）

- 递归切分 / 多变点 FWER 研究；
- 把旧 DMB-R1 ledger 并入正式估计；
- "persistence-intensity 普遍优于 scalar"主张；
- HASC / TSSB 作为本轮主要真实数据证据（本轮唯一真实数据 = PAMAP2 Protocol）；
- 正式结果出现后调整 DMB 带宽、核、候选区间、等价带或 MC 数；
- "首次发现滑动窗口产生依赖 / 首次研究依赖 TDA / 首次使用 block bootstrap 做 TDA 推断"类首创表述；
- 把审计流程包装成科学创新。

## 4. 证据分级（本代）

| 等级 | 内容 | 可进入论文主估计 |
|---|---|---|
| L0 | 单测、攻击测试、解析反例、blind smoke | 否 |
| L1 | DMB-R1 历史结果及任何已查看结果 | 否 |
| L2 | 本协议冻结后的正式合成实验 | 是 |
| L3 | 数据身份冻结后的 PAMAP2 分析 | 是（限说明性） |
| L4 | 独立环境重建与外部复核 | 增强可信度 |

表格与图片只读 L2/L3 sealed ledger；L1 只可在引言/补充材料说明动机，禁止与 L2 拼接计算。

## 5. 与 DMB-R1 的隔离

- DMB-R1 终止记录：`NO_IMPLEMENTATION_DEFECT`、R4 未达、归档 SHA256
  `38790d48a044bde41fd21bc31c18142b19e6decd2398cf1c3f3b8640f9df933d`。
- 旧材料只进 `external_prior_evidence/DMB_R1/`（B02 已物化完整 25 对象：
  23 内容对象逐字节核验 + `SHA256SUMS.txt` + `package_manifest.json` + `archive_manifest.json`；
  披露要点见该目录 `PRIOR_EVIDENCE_SUMMARY.md`）。
- 原 R1 的"统一恢复校准"主张不进入本代；R1 数字只属假设形成/历史开发证据（L1）。

## 6. 状态机与纪律

项目级：
```
DRAFT → THEORY_ALIGNED → SMOKE_VALIDATED → PROTOCOL_FROZEN
      → CORE_EVIDENCE_SEALED → ANALYSIS_FROZEN → RELEASED
```
其中 `CORE_EVIDENCE_SEALED := NULL_SEALED AND ALT_SEALED`。

phase 级（NULL/ALT/REAL 各自独立链，禁止用一个 CONFIRM_SEALED 代表三条证据线）：
```
NULL_INDEX_FROZEN → NULL_ADMITTED → NULL_RUNNING → NULL_SEALED
ALT_INDEX_FROZEN  → ALT_ADMITTED  → ALT_RUNNING  → ALT_SEALED
REAL_DATA_STAGED → REAL_DATA_FROZEN → REAL_TASK_BUILD_ADMITTED → REAL_TASKS_FROZEN
                 → REAL_PREDICTION_ADMITTED → REAL_PREDICTION_RUNNING → REAL_PREDICTION_SEALED
                 → REAL_LABELS_UNSEALED → REAL_EVALUATION_ADMITTED → REAL_EVALUATION_RUNNING
                 → REAL_EVALUATION_SEALED
```
REAL 数据/身份/task/隔离 Gate 失败分别从对应阶段进入 `REAL_OMITTED_BY_DATA_GATE`
（独立 append-only `REAL_DISPOSITION` chain，reason_code 必填）；`REAL_DEFERRED`
仅用于计算日程失败且 truth 保持封闭的情形。

通用纪律：
- 所有状态变更、失效、amend 一律 **append-only**，禁止覆盖、删除或静默改写已登记对象；
- 初次 full run 与局部重跑都必须从新的 `INDEX_FROZEN` 开始；
- `RUN_SEALED` 不可取消/改写；`INVALIDATED/SUPERSEDED` 作用于 logical slot 的 active binding；
- `DEADLINE_NO_GO` 只属 `schedule_disposition`，不充当科学/run 状态；
- blind smoke 不输出拒绝率汇总、不进入参数选择。

## 7. 实验设计快照（引用计划章节）

| 组件 | 规格 |
|---|---|
| 原序列 DGP | N-AR（延迟嵌入）、N-CIRCLE（copula，`Q=I2`）；`ρ∈{0,0.8}`；burn-in 1,000 |
| H0 双矩阵 | fixed-M（W64/M192, s∈{64,32,16,8}）× fixed-T（T=3120/W64, 同 s），28 唯一格 × 2,500 |
| H1 | 形状变化（circle→figure-eight）与 mean-shift 反向控制，均"单时点边际均值-协方差匹配"，8 格 × 1,600 |
| 特征 | BPI `BPI_FIXED20_H01_SIGMA005_GAMMA1_V1`（800 维）；MOMENTS `MOMENTS_MEAN_COV_FROB_V1`（2D→5D/3D→9D）；窗口局部固定参数，禁止全序列自适应 |
| 校准器 | M0 `M0_NAIVE_PERM_B999_V1`；M1 `M1_DMB_R1_TRI_EXTIID_B999_V1`；B=999，p=(1+exceed)/1000 |
| 真实数据 | PAMAP2 Protocol 9 受试者；W=100，s∈{100,50,25}；标签隔离评估 |
| 主假设 | P1/P2（M0 重叠失真 >0.10）、P3（M1 非重叠保守 >0.01）；整簇 bootstrap 10,000 + Holm；等价带 [0.035,0.065] |
| 规模 | 331,200 eval rows；330,868,800 内层重采样统计量；8,207,600 PH 窗口；575 唯一窗口起点复用 |

理论交付标准（T6）：2026-09-18 前未闭合 T4 即降级"精确反例 + 解析 VIF + 系统有限样本图谱"。

## 8. 治理：执行批次合同

每批四件套（方案方 → 本地执行方）：
`<BATCH_ID>_EXECUTION_GUIDE.md`、`<BATCH_ID>.patch`、
`<BATCH_ID>_VALIDATION_REPORT.md`、`<BATCH_ID>.patch.sha256`。

批次纪律（详见计划 §20.1）：
1. 回传 `git rev-parse HEAD`、`git status --porcelain=v1`、`git stash list`；
2. 仅当 status 与 stash 均空才创建批次分支；已有修改先形成具名 commit，禁止自动 stash；
3. 校验 patch SHA256 → `git apply --check` → apply；
4. 按手册执行定向/全套/攻击测试或 phase runner；
5. 回传新 HEAD、空工作区证明、测试摘要、Gate JSON 路径/hash、完整错误日志；
6. 方案方复审并书面签发下一批；上一批未闭合时禁止并行改动同一科学模块。

formal 阶段开始后，compute-freeze 列出的文件只读。发生错误先停止对应 run、保留
shard/attempt 证据，再按计划 §18.2 失效范围表处置，禁止现场调参续跑。

## 9. 关键日程（北京时间，引用计划 §23）

| 日期 | 里程碑 |
|---|---|
| 09-10 | 建仓、Charter、Claim Matrix、论文骨架（本批） |
| 09-12/13 | PAMAP2 hash 锁定；seed/salt commitments；`REAL_TASK_BUILD_ADMITTED` |
| 09-17/18 | `REAL_DATA_TASK_GATE` / task index 冻结或 omission；T2/T3；T4 审读或降级 |
| 09-19~22 | SCOPE_DESIGN/index/admission/分析器、93 项攻击、workers 基准、blind smoke |
| 09-23 | **共同冻结**（PROTOCOL_FROZEN；Git tag；REAL 隔离与日程 Gate） |
| 09-24 | NULL admission、ALT pre-admission、REAL admission/omission/deferred |
| 09-25~10-04 | H0 全 28 格运行（N-AR 9/25-29；N-CIRCLE 9/30-10/4） |
| 10-05/06 | H0 phase seal → ALT 正式 admission；锁 H0 主分析 |
| 10-06~10 | H1 运行与 seal；size-standardized analysis |
| 10-11/12 | PAMAP2 prediction →（seal 后）unseal truth → evaluation seal；科学 GO/NO-GO |
| 10-13~22 | 中文论文首稿 → clean-build → 独立审计 → 红队 → Analysis Freeze |
| 10-28 | 投稿（10-31 为紧急缓冲，不安排首次投稿） |

预设分流（不改变科学范围）：9/17 或 9/23 REAL Gate 失败 → REAL omission；
9/18 T4 未闭合 → 理论降级；9/22 计算 Gate 失败 → 停止赶投先做性能工程；
REAL 日程 Gate 单独失败 → `REAL_DEFERRED`、truth 保持封闭、合成主线继续。

## 10. 发布与签名登记

- release key（Ed25519/minisign）与公钥指纹：**TBD——G0（冻结）前必须闭合**；
  若 G0 前不能闭合，改用预先登记的机构不可变发布记录（见计划 §25）。
- 正式发布文件命名 `OWTDA-CAL-R1_release_202610xx.zip(.sha256/.attestation.json/.sig)`。

## 11. 许可证记录

- 当前 `LICENSE` 为占位（All rights reserved until publication decision）。
- 许可证决策将在稿件提交前登记于此节并替换 LICENSE 文件。

---

*本 Charter 随仓库 commit 提交；计划基线变更须经 amendment 并以 append-only 登记。*
