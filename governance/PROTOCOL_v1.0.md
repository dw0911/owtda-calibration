# PROTOCOL v1.0（FROZEN）— OW-TDA-CAL-R1

> 状态：**FROZEN**（B14a 共同冻结，2026-09-10；此后只读）；
> 此后变更一律走 `AMENDMENT_REGISTRY.jsonl`（append-only）。
> 权威基线：`../OWTDA_CAL_R1_COMPLETE_PLAN_v1.0.md`（2026-09-09 定稿；
> 仓库内副本 SHA256 `dca49727def3d31d2f367d58dba157e782946b862c28d29dd8508a6a3cc19ab3`）。
> 本文件是基线计划的治理投影；与基线冲突时以基线为准直到冻结（冻结后以本文件链为准）。

## 1. 研究对象与主统计量（基线 §3）

- 原序列 `{X_t}`（`R^d`）、窗口 `W`、步长 `s`、窗口数 `M=floor((T-W)/s)+1`；
  重叠率 `r_ov=1-s/W`，几何依赖阶 `m_ov=ceil(W/s)-1`。
- 窗口局部特征 `Y_i=Φ[PH(E(X_{I_i}))]`；**所有 cap/网格/核宽/权重/去重均为窗口局部规则**，
  禁止整序列自适应 cap 与全序列标准化（基线 §3.2 强约束）。
- 扫描统计量：候选集 `K_M={k: ceil(0.15M) ≤ k ≤ M-ceil(0.15M)}`，
  加权均值差平方范数 `T_M(k)=(n_L n_R/M)||Ybar_1:k - Ybar_{k+1:M}||^2`，
  位置规则 = 最长 plateau → 最左段 → lower median；resample exceed 仍按 float64 精确 `>=`（基线 §3.3）。
- 本轮只研究**第一次全局扫描**（无递归切分）。

## 2. 证据分级与隔离（基线 §2）

- L0（测试/攻击/解析反例/blind smoke）、L1（DMB-R1 历史，见
  `external_prior_evidence/DMB_R1/`）、L2（冻结后正式合成）、L3（PAMAP2）、L4（独立重建）。
- 论文表格与图片只读 L2/L3 sealed ledger。DMB-R1 已终止
  （`NO_IMPLEMENTATION_DEFECT`，归档 SHA256 `38790d48…df933d`），禁止并账。

## 3. 状态机（基线 §2.3）

- 项目级：`DRAFT → THEORY_ALIGNED → SMOKE_VALIDATED → PROTOCOL_FROZEN → CORE_EVIDENCE_SEALED → ANALYSIS_FROZEN → RELEASED`
  （`CORE_EVIDENCE_SEALED := NULL_SEALED AND ALT_SEALED`）。
- NULL/ALT/REAL 各自独立状态链；REAL 经 `REAL_DISPOSITION` chain 进入
  `REAL_OMITTED_BY_DATA_GATE` / `REAL_DEFERRED`（独立 reason_code，append-only）。
- 机器 phase 枚举只允许 `SMOKE_NULL/SMOKE_ALT/NULL/ALT/REAL_*/ANALYSIS`；
  smoke 不得复用 formal phase 名。`DEADLINE_NO_GO` 仅属 `schedule_disposition`。

## 4. Integrity Gates（基线 §17，摘要）

| Gate | 内容 | 关键对象 |
|---|---|---|
| G0 | 项目身份：DMB-R1 终止可验证、新 project_id 与旧代不同、工作区/stash 干净、配置/schema/脚本 tracked、COMPUTE_FREEZE 完整 | `PROJECT_CHARTER`、`external_prior_evidence/DMB_R1/` |
| G1 | 理论与实现对齐：CUSUM 误差 ≤1e-12、窗口计数、575-start、延迟嵌入、解析 VIF、BPI 无全局自适应 | METHOD_SPEC |
| G2 | 确定性与攻击：workers 一致性、seed 无碰撞、schema/bytes golden | audit suite |
| G3 | blind smoke：H0 3,584 / H1 1,024 行、无科学汇总泄露、wall/RAM/磁盘三项 PASS | smoke seals |
| G4 | 正式运行准入：admission、freeze、RUN_COMPONENT_SET/expected indexes/shard plan 闭合、前置 Gate PASS、open_runs=0 | admission 对象 |
| G5 | 结果 seal：RUN/PHASE seal 计数（H0 280,000 / H1 51,200 / feature 140,000/25,600）、0 缺失/重复/冲突、p 值公式重放 | seals |
| G6 | 分析与发布：表图只读 sealed ledger、analysis seal、无自引用、release 校验 | release index |

## 5. 内容与身份合同（基线 §15）

- RNG：`numpy.random.Generator(PCG64DXSM)`；root key = CSPRNG 32 bytes；HMAC 子 seed 派生
  （payload 含 `domain:"owtda-seed-v1"`、`stream_kind`、`named_fields`）。
- ID：`H(id_kind, **named_fields)`（payload 含 `domain:"owtda-id-v1"`），全部 64 hex，禁止位置参数。
- canonical JSON：UTF-8、键排序、无空白、`ensure_ascii=false`、`allow_nan=false`、单 LF；
  配置实数从 Decimal/canonical decimal 文本进入 payload。
- array/row 字节合同：big-endian `>f8`、header+`b"\x00"`+data 的 SHA256；row 双层 schema、
  `f64:` 8-byte BE hex 的 float hash view；round-trip Gate（基线 §15.4）。
- freeze_id = `H("freeze", project_id, protocol_id, protocol_content_hash, scope_spec_hash,
  analysis_spec_hash, compute_spec_hash)`；`protocol_content_hash` 的输入正文即本文件与
  各 `METHOD_SPEC/SAP/DATA_SPEC` 冻结版（hash 在冻结批登记，不在此预填）。

## 6. 变更与失效纪律

- 所有变更 append-only：AMENDMENT_REGISTRY / INVALIDATION_REGISTRY / STATE_REGISTRY（jsonl）。
- 缺陷失效范围（基线 §18.2）：DGP→data generation；公共 evaluator→evidence generation 全重建；
  feature→该 feature generation；resampler→该 method generation；绘图→仅下游产物。
- 结果后禁止调带宽/删格/减 MC；CI 过宽标 `INCONCLUSIVE`；新假设进 OWTDA-CAL-R2。

## 7. 开放项（冻结前关闭）

- [ ] protocol_content_hash / freeze_id 在共同冻结批计算；
- [ ] COMPUTE_FREEZE.json（基线 §17 G0）列出 DGP/window/feature/method/runner/config 文件白名单；
- [ ] AMENDMENT_REGISTRY / INVALIDATION_REGISTRY / STATE_REGISTRY 初始登记机制落地；
- [ ] 编辑部咨询结果并入 §1.4 投稿适配（征稿详情暂缓填写）。
