# FAILURE_POLICY — 失败与重跑策略

## 1. 总原则（fail-closed）

**无法证明正确即视为不正确。** 任何校验失败、身份不一致、字节不符或未解释异常，
一律阻断而不是降级放行；禁止"看起来没问题"式判断。

## 2. 正式 run 的失败处置

| 情形 | 处置 |
|---|---|
| 单次 trial/工作单元失败 | 终止该 run；保留 shard/attempt 证据（不删除）；用**同一** code/config/seed manifest 重跑该 run |
| 分片内容不一致（`commit_shard` 内容冲突） | 阻断并保留两侧字节；不得覆盖已提交分片 |
| 资源验收失败（RSS/swap/未解释 error） | 停止新任务派发；未结清 worker 标记 `UNRESOLVED`；不得伪报退出 |
| 冻结源域被修改（`src/ configs/ audit/` 有未提交改动） | `repo_guard` 在写出任何字节前拒绝构建/运行 |
| 结论与规格冲突 | 先停 run、再按失效范围表处置；**禁止现场调参续跑** |

## 3. 禁止事项

- 禁止静默跳过失败单元、换 seed 补齐、或只重跑"好看"的子集；
- 禁止覆盖/删除已封存对象（seal、ledger、registry、attempt 目录）；
- 禁止用空文件或占位值绕过"注册表缺失/为空即 FAIL"的检查；
- 禁止在预登记协议之外修改验收条件后重跑改善数字（历史先例：`w*` 确认作废、维持 `w* = 8`）。

## 4. 证据与再生成

- 失败证据（日志、stdout/stderr、退出码、环境快照）与成功证据同等保留；
- 再生成只允许发生在**新目录**（"输出目录必须不存在"），不得就地覆盖；
- 一切状态变更 append-only（`governance/CHANGELOG.md`、`*_REGISTRY.jsonl`、`reasons/`）。

## 5. 已知的披露项（本快照）

| 项 | 状态 |
|---|---|
| `validate_freeze.py` 的 `source_tree_hash` 单项不匹配 | 已解释（入库 `src/` 为 R4/R5 修复后较新版本）并登记，其余检查全 PASS |
| 表 1–5 原始生成器未保留 | 已披露；数据/输入/输入哈希齐备；随图表重构轮补入 |
| `H0_PRIMARY_CONTRASTS.json` 的旧 `p = 0` | 非法值，已由 `results/bootstrap/P1_P3_BOOTSTRAP_SUMMARY.json` 取代（原字节保留以维持哈希链） |
| M0 逐格范围口径 | 纸面 [4.72, 97.56] vs canonical 全行 [4.32, 99.96]，已登记待核对 |
