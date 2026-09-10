# ATTACK SUITE v1.0 — OW-TDA-CAL-R1

> 映射计划 §19 的 93 项攻击测试；状态口径：
> **COVERED** = 已有自动化测试直接覆盖（含正反例）；**PARTIAL** = 规则/机制级已覆盖、
> 缺少 run/ledger/release 集成；**DEFERRED** = 依赖尚未实现的 run/ledger/release 批次。
>
> 本文件由 B13 建立；每次批次闭合后更新状态。G2/G3 要求全 93 项达到 COVERED 或
> 由方案方书面登记的可接受替代（正式运行前必须清零 DEFERRED）。

## 覆盖统计（B13 时点）

| 状态 | 数量 |
|---|---|
| COVERED | 41 |
| PARTIAL | 20 |
| DEFERRED | 32 |
| 合计 | 93 |

自动化攻击测试：`tests/test_attacks.py`（跨模块，37 项）、`tests/test_parallel.py`（并行/RNG，9 项），
其余由各模块单测承载（下表"覆盖位置"）。

## 明细

| # | 攻击点（缩写） | 状态 | 覆盖位置 |
|---|---|---|---|
| 1 | 配置改一字节 → freeze 失效 | COVERED | test_attacks::test_01 |
| 2 | 源码未提交 → runner 拒绝 | DEFERRED | runner 批（B14+） |
| 3 | 非空 stash → freeze 拒绝 | DEFERRED | freeze 批（B14） |
| 4 | 缺字段/未知字段拒绝 | COVERED | test_attacks::test_04、test_rowschema、test_indexes |
| 5 | config/registry/ledger 的 W,s,T,M 不一致 | PARTIAL | test_indexes（结构级）；ledger 批补 |
| 6 | 混入旧代 ledger → 分析器拒绝 | DEFERRED | 分析器批 |
| 7 | 同 seed 同配置逐字段一致 | COVERED | test_attacks::test_07、test_dgp |
| 8 | workers=1 与 w* payload 一致 | COVERED | test_parallel、audit/compute_budget.py |
| 9 | 打乱提交顺序一致 | COVERED | test_parallel::test_submission_order |
| 10 | smoke/H0/H1/REAL seed 无交集 | COVERED | test_attacks::test_10 |
| 11 | 派生 seed 无碰撞 + intentional alias | COVERED | test_attacks::test_11 |
| 12 | 禁止全局 np.random.* | COVERED | test_parallel::TestNoGlobalNumpyRandom |
| 13 | 改 ρ/stride innovation hash 不变、resampling 按 data unit 变 | COVERED | test_attacks::test_13、test_dgp |
| 14 | M=⌊(T−W)/s⌋+1 | COVERED | test_cells、test_attacks::test_14_15_16 |
| 15 | fixed-M 反算 T=W+s(M−1) | COVERED | test_cells、test_attacks::test_14_15_16 |
| 16 | fixed-T 不自动改 T | COVERED | test_attacks::test_14_15_16 |
| 17 | s=W → overlap=0 | COVERED | test_attacks::test_17 |
| 18 | 末窗口与边界索引 | COVERED | test_cells::TestGeometry::test_raw_starts |
| 19 | window index→raw time 人工反例 | COVERED | test_attacks::test_19、test_scan::TestRawTime |
| 20 | 点云行置换不改 persistence | COVERED | test_attacks::test_20_21、test_ph |
| 21 | 乱序/重复/远端扰动不改 BPI | COVERED | test_attacks::test_20_21、test_pointcloud |
| 22 | circle/双环/单点/重复/共线结构 | COVERED | test_attacks::test_22、test_ph |
| 23 | 平移/旋转/缩放性质 | COVERED | test_attacks::test_23、test_moments |
| 24 | VR thresh / cap / grid 分离 | COVERED | test_attacks::test_24、test_bpi |
| 25 | 空图/零强度/无限 death | COVERED | test_attacks::test_25、test_bpi、test_ph |
| 26 | CUSUM 重放 ≤1e-12 | COVERED | test_attacks::test_26、test_scan::TestDoubleImplementation |
| 27 | observed 在 M0/M1 精确一致 | COVERED | test_attacks::test_27、test_calibrate |
| 28 | p 值全量重放 | PARTIAL | p 规则已测；ledger replay 工具待批 |
| 29 | p 值位于 0.001 网格 | COVERED | test_attacks::test_29_30、test_calibrate |
| 30 | exceed=49 拒绝 / 50 不拒绝 | COVERED | test_attacks::test_29_30 |
| 31 | DMB 经验协方差 = 三角核 | COVERED | test_attacks::test_31_33、test_calibrate::test_triangular_covariance |
| 32 | 无 circular wrap | COVERED | test_attacks::test_31_33 |
| 33 | padding 逐位复现 | COVERED | test_attacks::test_31_33（端点值） |
| 34 | resample exceed 精确 `>=` | COVERED | test_attacks::test_34 |
| 35 | candidate/exclusion/plateau 方法无关 | COVERED | test_attacks::test_35、test_scan |
| 36 | 删一条 trial → seal 失败 | DEFERRED | ledger/seal 批 |
| 37 | 复制一条 trial → seal 失败 | DEFERRED | ledger/seal 批 |
| 38 | 篡改 p 值 → replay 失败 | DEFERRED | replay 工具批 |
| 39 | ledger 行顺序不影响汇总 | DEFERRED | 分析器批 |
| 40 | figure 读未 sealed/多代 ledger 失败 | DEFERRED | 图表批 |
| 41 | canonical summary 与论文数字不一致失败 | DEFERRED | 图表/审计批 |
| 42 | release spec/index 漏项失败 | DEFERRED | release 批 |
| 43 | 零字节文件 UNEXPECTED_ZERO_BYTE / 白名单空对象合同 | DEFERRED | release 批 |
| 44 | ZIP 篡改 → SHA256 失败 | PARTIAL | external_prior_evidence 复核已实现；release ZIP 批补 |
| 45 | Win/Linux seed/ID/索引一致 + 浮点容差 | PARTIAL | 本机 golden 已冻结；Linux 重建（L4）批补 |
| 46 | 中止恢复后 ledger 一致、attempt 保留 | PARTIAL | test_shardio（CAS/attempts）；run 集成批补 |
| 47 | s=16 共享格一个 logical_cell_id | COVERED | test_attacks::test_47、test_scope |
| 48 | budget_membership 不改物理 hash | COVERED | test_attacks::test_48、test_cells |
| 49 | REAL prediction row 泄露字段 schema 拒绝 | COVERED | test_attacks::test_49、test_rowschema |
| 50 | 改 attempt 时间戳不改 scientific hash | PARTIAL | 设计分离（test_shardio）；run 批补 |
| 51 | H0/H1 行数偏离 280,000/51,200 → seal 失败 | DEFERRED | seal 批 |
| 52 | BPI/MOMENTS 的 M0/M1 逐 resample 相同 | COVERED | test_attacks::test_52 |
| 53 | H1 source-null 唯一指向匹配 N-CIRCLE H0 | PARTIAL | test_scope（source-null 生成）；H1 join 批补 |
| 54 | 主配置出现随机 Q → validator 拒绝 | DEFERRED | config validator 批 |
| 55 | *_ADMITTED 前消费正式 RNG 拒绝 | PARTIAL | test_registry（域隔离）；runner 批补 |
| 56 | 改 root key：该 family 变、其他不变 | COVERED | test_attacks::test_56 |
| 57 | 同 named fields、不同 stream_kind → seed 不同 | COVERED | test_attacks::test_57、test_seeding |
| 58 | canonical/HMAC/ID 跨平台 golden | PARTIAL | 本机 golden；Linux（L4）批补 |
| 59 | row_payload_hash 排除自身、NaN/Inf 拒绝 | COVERED | test_attacks::test_59、test_rowschema |
| 60 | 改 method generation 只变该 method evaluation/stream ID | COVERED | test_attacks::test_60 |
| 61 | PAMAP2 非递增/重复 grid/超残差/缺失 grid 攻击 | COVERED | test_pamap2_import |
| 62 | task builder 不能生成 A=B 或跨段任务 | COVERED | test_attacks::test_62_70、test_pamap2_tasks |
| 63 | REAL truth/prediction/evaluation 行数与 12:1 关系 | DEFERRED | REAL omitted；机制批（如 REAL 重启用） |
| 64 | 改 H1 noise/burn-in/Q/版本 → null_model_config_hash 变 + join 失败 | DEFERRED | H1 批 |
| 65 | generation 提升 → SUPERSEDED、active ledger 唯一行 | DEFERRED | ledger 批 |
| 66 | 白名单外 registry snapshot/source hash 混入 → seal 失败 | DEFERRED | seal 批 |
| 67 | bootstrap 循环顺序不变 | DEFERRED | 分析器批 |
| 68 | array native LE/C 与 BE hash view 同 hash | COVERED | test_attacks::test_68、test_hashing |
| 69 | 九 entries 顺序无关/单文件变/ZIP 不影响 | COVERED | test_attacks::test_69、test_realdata |
| 70 | bout/candidate 3000/500 边界、zero run 0/1、三轴 union | COVERED | test_attacks::test_62_70、test_pamap2_tasks |
| 71 | task_id 敏感性 | COVERED | test_attacks::test_71、test_pamap2_tasks |
| 72 | discriminated-union 三态逐格攻击 | COVERED | test_attacks::test_72、test_rowschema |
| 73 | reserved key / NFC collision / decimal 攻击 | COVERED | test_attacks::test_73、test_canonical、test_seeding |
| 74 | 双 schema/float 定向解码/byte round-trip/`f64:` 不误解码 | COVERED | test_attacks::test_74、test_rowschema |
| 75 | scientific row 含 post-run 字段拒绝、图无环 | PARTIAL | 未知字段拒绝已测；run 图批补 |
| 76 | expected indexes 重复/排序/BOM/CRLF/缺末行 LF/额外字段/自引用 | PARTIAL | 重复/排序/字段已测；字节级 writer 批补 |
| 77 | ORPHAN_FINAL 重算一致补唯一 commit、不一致阻断 | COVERED | test_attacks::test_77_91、test_shardio |
| 78 | RUN/PHASE seal 删改 feature ledger/ID set/content hash 失败 | PARTIAL | seal 构建与 ID-set hash 已测；ledger 集成批补 |
| 79 | 三层 binding generation 混入检查 | PARTIAL | test_registry/test_indexes；binding 批补 |
| 80 | NULL upstream 变化 → 旧 ALT seal 不可激活；REAL commitment 变化 → 下游不可激活 | DEFERRED | phase 链集成批 |
| 81 | ground-truth salt/truth byte/task ID 集/signal hash 变动 → precommit/unseal 失败 | PARTIAL | test_pamap2_tasks（敏感性）；unseal 批补 |
| 82 | REAL_LABELS_UNSEALED 后新增/替换 prediction 拒绝 | DEFERRED | REAL 状态机批 |
| 83 | scope CSV 行序/换行不改 hash、值/主键/evidence generation 改动会改 | PARTIAL | test_scope（行确定性）；CSV writer 批补 |
| 84 | candidate ID/mapping 出现在 prediction 路径任一处 → isolation Gate 失败 | DEFERRED | isolation 批 |
| 85 | PAMAP2 golden fixture 逐位（half-up/内插/bad-row/切段/除 g 顺序） | COVERED | test_attacks::test_85、test_pamap2_import |
| 86 | RNG stream API/次数/shape/dtype/consumption 顺序 golden | PARTIAL | shape/dtype/确定性已测；统一 consumption golden 批补 |
| 87 | 同 evaluation 跨 run attempt ID 不同；同 run 重复 attempt number 拒绝 | PARTIAL | test_shardio（单调分配）；跨 run ID 批补 |
| 88 | RUN_INPUT_BINDINGS 不一致 → admission 失败 | DEFERRED | admission 批 |
| 89 | ANALYSIS_INPUT_MANIFEST→…→ANALYSIS_SEAL 可 DAG 重放、回灌 derived ID 拒绝 | DEFERRED | 分析器批 |
| 90 | release payload 改变 → release_id 变；把 index/manifest/SHA/ZIP 加入 payload 拒绝 | DEFERRED | release 批 |
| 91 | shard commit 重复/冲突 CAS、漏 commit、ref 集合≠shard plan 阻断 RUN seal | PARTIAL | test_attacks::test_77_91（CAS/冲突）；seal 集合核对批补 |
| 92 | phase-state/validity/current-pointer tip 变化 → CAS 失败 | PARTIAL | test_chains（stale tip）；三链集成批补 |
| 93 | ZIP path traversal/casefold/symlink/duplicate member/额外 member/无效签名拒绝 | DEFERRED | release 批 |

## 后续闭合计划

| 批次 | 预期闭合编号 |
|---|---|
| B14 冻结 | 2、3、55（runner 拒绝路径）、44（release ZIP 前置） |
| 正式 run/ledger（H0/H1） | 5、36、37、38、39、46、50、51、65、66、78、87、91、92 |
| 分析器/图表 | 6、28、40、41、67、89 |
| REAL（若重启用） | 63、64、80、81、82、84 |
| release/打包 | 42、43、44、90、93 |
| 跨平台重建（L4） | 45、58 |

## B13 新增的攻击能力

1. **有序并行确定性**：`ordered_map`/`feature_matrix_parallel` 在任意 worker 数下逐位重现
   `workers=1` 结果，且提交顺序无关（§19 #8/#9）；
2. **全局 RNG 静态攻击**：`scan_for_global_numpy_random` 扫描 `src/` 与 `tests/`，禁止
   `np.random` 全局入口（允许 `Generator`/`PCG64DXSM`/`SeedSequence`/`default_rng`）（§19 #12）；
3. **规则级边界攻击**：`p_value`/`reject_from_exceed`/`resample_exceeds` 使 §19 #29/#30/#34
   成为可独立重放的规则断言；
4. **预算复核**：`audit/compute_budget.py` 输出 workers{1,4,8} 稳态吞吐、payload 一致性、
   peak RSS、F: 磁盘与 §9.4 wall 外推（证据 `artifacts/audit/compute_budget_RC.json`）。
