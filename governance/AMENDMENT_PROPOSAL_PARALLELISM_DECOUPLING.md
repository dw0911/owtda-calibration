# 关于 `w*` 的处置决定与并行度解耦提案

状态：**第 1 部分已生效；第 2 部分为提案，尚未生效、未改动任何身份。**
拟定时间（UTC）：2026-09-11；对应冻结 amendment 标签 `v1.2-freeze-owtda-cal-r1`。

## 第 1 部分 — `w*` 处置（已生效，无需进一步动作）

**决定：冻结值维持 `w* = 8`，不采纳扫描/确认中测得更快的 12。**

依据（均可复核）：

1. 预登记协议 `configs/wstar/WSTAR_CONFIRMATION_PROTOCOL.json`
   （`protocol_sha256 = df17eb1c…`）在任何测量之前入 git，验收条件含「无 swap 增长」；
2. 执行结果（`wstar/worker_confirmation_RC.json`，12 次全长 32-replicate 配对）：
   `SMOKE_ALT = CONFIRMED`，`SMOKE_NULL = VOIDED_ACCEPTANCE_CONDITION_FAILED`
   （一次运行出现 4 MB swap 增量）；
3. 协议明文规定：任一验收条件失败即**作废**，且**不得重跑以改善数字**；
4. 因此采纳 12 等于推翻自己预登记的验收规则——治理质量上严格劣于维持 8。

**没有任何 Gate 结论依赖该取值**（两 phase 的 wall 预算均有约 9 倍余量）。
`COMPUTE_SPEC.w_star_source` 已显式记录该判定；`AM_WSTAR_ADOPTION` 已登记。

> 若日后确实需要更快的并行度，须走第 2 部分（结构性），而不是重跑已作废的确认。

## 第 2 部分 — 提案：把并行度从科学身份中解耦（**未生效**）

### 2.1 问题

`COMPUTE_SPEC.w_star` 进入 `compute_spec_hash`，后者进入 `freeze_id`，`freeze_id`
进入 `SCOPE_DESIGN_*` 行哈希与全部合成 cell/run 身份
（`audit/build_freeze.py`：`_compute_spec()` → `freeze.compute_spec_hash()` → `scope.freeze_id()`）。

与此同时，**同一份 `COMPUTE_SPEC` 里写着 `worker_consistency = "bitwise_identical_payload"`**：
并行度已被证明不改变任何一个 evaluation row 的字节。于是：

- 一个**已被证明与结果无关的操作参数**，被冻结成了科学身份；
- 任何换机器/换核数的操作动作，都会强制重新冻结并重派生全部身份；
- R1 已经为此付出过代价：一次确认作废、两次 tag 处置（`v1.1` → `v1.2`）。

### 2.2 提案

把「并行度」从 `compute_spec_hash` 的覆盖面中移出，拆成两部分：

| 冻结进 `compute_spec_hash`（契约） | 每 run 记录（操作参数） |
|---|---|
| 线程环境锁：四个 BLAS/OMP 变量必须为 `1`（解释器启动前设定） | `workers_used`（写入 `RUN_COMPONENT_SET`） |
| 并行度不变性要求：任一允许的 `w` 必须产生**逐位相同**的 payload | `1 ≤ w ≤ cpu_count` |
| 资源验收：peak RSS ≤ 24 GiB、swap 增量 = 0 | 实测 wall / RSS / swap（运行证据，不改变身份） |

即：`compute_spec` 只冻结**必须成立的性质**，不冻结满足它的具体取值。

### 2.3 改变面与代价

- `governance/COMPUTE_SPEC_v1.json` 结构变更 → `compute_spec_hash` 变更 →
  `freeze_id` 变更 → `SCOPE_DESIGN_NULL/ALT` 行哈希与全部合成身份变更；
- 因此**必须在正式 run 之前做**：现在做的代价 ≈ 一次重建 + 一次 S03 重跑（约 25 分钟）；
  正式 run 之后再做，代价是作废已产出的 phase seal 与全部 L2 证据；
- `v1.0` tag 不移动；本提案若被采纳，应新建 `v1.3-freeze-owtda-cal-r1`（或经裁定复用并登记）。

### 2.4 采纳后必须保持的严格性（不得放松）

1. 全尺度两 phase 盲 smoke 上，候选 `w` 与参考 `w` 的 evaluation row payload **逐位一致**
   （R1 已在 32-replicate 全长上观测到该性质：`wstar/worker_confirmation_raw.jsonl`）；
2. 资源验收（RSS/swap）在候选 `w` 下逐次通过；
3. `workers_used` 必须出现在 `RUN_COMPONENT_SET` 与 run 证据中，使每次正式 run 的实际并行度
   可被独立复核；
4. 参考环境锁与 §9.4 预算公式不变（预算按实测 `t_32` 与所选 `w` 计算）。

### 2.5 备选方案与被否理由

| 方案 | 结论 |
|---|---|
| 维持 `w* = 8`，不解耦（现状） | 可接受，但下次换机器/换核会**再次**强制重新冻结 |
| 保留 `w*` 在身份内，另立协议把 12 测成 CONFIRMED | **否决**：等于重跑已作废的验收以改善数字，违反代理协议自身规则 |
| 提案（解耦） | **建议采纳**：一次性消除该类churn，且不放松任何验收条件 |

### 2.6 需要谁裁定

`compute_spec_hash` 的覆盖面属于冻结身份契约，**需审计方（或项目负责人）裁定**。
在裁定之前：本文件仅为提案，**仓库内没有任何已应用的身份改动**，
`w* = 8` 与 `v1.2` 仍为唯一有效冻结身份。
