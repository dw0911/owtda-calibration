# 提案：把「证据装配工具」移出冻结源域，并让治理链只追加不重写

状态：**提案，未生效**（未改动任何身份）。拟定时间（UTC）：2026-09-11。
关联 amendment：`AM_PARALLELISM_DECOUPLING`（`v1.4-freeze-owtda-cal-r1`）。

## 1. 本轮暴露的第二个同类缺陷：治理链被「重写」而非「追加」

`audit/build_governance_registries.py` 的 `_write_chain` 每次**按内部清单重写**整条链
（每条事件带构建时刻的 `at_utc`，因此重写必然产生不同的事件字节）。后果：

- 由**其它工具**追加的事件会被静默丢弃。本轮实际发生过一次：
  `INV_V12_SOURCE_ANCHOR`（`inv1.2 → v1.3` 的来源锚点迁移）在随后的注册表重建中被抹掉，
  由补充序列的登记阶段重新追加后才恢复；
- 与 `freeze_id` 静默复用、`source_tree_hash` 静默漏项属于**同一缺陷类**：
  「无法从产物本身察觉的历史丢失」。

**建议修法（未实施）**：`_write_chain` 改为**保序保字节的追加器**——
1. 读取既有链，按 `change_id` 建立索引并**原样保留**既有事件（不改 `at_utc`、不重算哈希）；
2. 仅对**新增** `change_id` 追加事件，`expected_tip` 取当前 tip（CAS）；
3. 若某 `change_id` 已在链中但其内容与本次生成的不同（除 `at_utc` 外），**fail-closed 拒绝**
   （说明有人改了 reason 或事件语义），而不是悄悄重写。

配套测试：既有链 + 外部追加事件 + 重建 → 链长度不减、外部事件仍在；内容冲突 → 拒绝。

## 2. 根因：`source_tree_hash` 覆盖了「不影响结果的工具」

`SOURCE_TREE_PREFIXES = ("src/", "configs/", "audit/")`。其中 `src/`、`configs/` 决定**数值结果**
（DGP、特征、方法、分析、schema、参数），而 `audit/` 中的大部分文件只**装配证据**
（`collect_*`、`build_supplement`、`run_registry`、`build_governance_registries`、`validate_*`…）。

把它们全部纳入 `source_tree_hash` 的后果：任何工具改进都会移动「运行/来源锚点」，
从而（按本轮确立的纪律）**强制重跑编号 smoke 并新建标签**。本轮已因此付出一次
`v1.3 → v1.4` 迁移（为的是守卫与复审包这两个纯工具改动）。

**建议（未实施）**：
- `source_tree_hash` 只覆盖 `src/` 与 `configs/`（即「决定数值的工件」）；
- `audit/` 的证据装配工具改为由 **revision bundle + `revision/source_manifest.json`** 锚定
  （包内已提供 `SHA256SUMS.txt`、`git fsck`、bundle verify，内容锚定并不减弱）；
- 组件级 `code_files` 仍然只列决定该组件数值的文件（现状即是如此）。

**代价与边界**：这本身是一次 `source_tree_hash` 变更，必须在正式 run 之前完成
（与 B15d 的 identity 变更合并即可，不额外增加一次编号 smoke）；`freeze_id` 不受影响。
**风险**：审计方若要求「工具也进哈希」，则应维持现状——此时 `_write_chain` 的追加化（§1）
是必须的，否则工具每次改动都可能丢历史。

## 3. 需要裁定

| # | 决定 | 选项 |
|---|---|---|
| 1 | `_write_chain` 追加化 | 采纳（建议，与身份无关，可随时做）／维持重写 |
| 2 | `source_tree_hash` 覆盖面收窄到 `src/`+`configs/` | 采纳（建议，需在正式 run 前）／维持 `src/`+`configs/`+`audit/` |

在裁定之前，本文件仅为提案：仓库内**没有任何**关于上述两项的已应用改动，
当前冻结身份仍为 `v1.4-freeze-owtda-cal-r1` / `AM_PARALLELISM_DECOUPLING`。
