# OW-TDA-CAL-R1

重叠滑动窗口下拓扑扫描检验的交换性失效与校准边界
（Exchangeability Failure and Calibration Boundaries of Topological Scans with Overlapping Windows）

## 状态（2026-09-10）

- 项目级状态：`DRAFT`
- 文档状态：Plan v1.0 已定稿，**任何正式 Monte Carlo 开始前必须转为 `FROZEN`**
- 旧证据线 DMB-R1：已于 2026-09-09 终止（`NO_IMPLEMENTATION_DEFECT`），只读归档为 L1 先验证据

## 仓库布局

```
owtda-calibration/
├── README.md / CITATION.cff / LICENSE / pyproject.toml / uv.lock
├── src/owtda_cal/
├── tests/
├── configs/           # schema、smoke、confirm_null、confirm_h1、real
├── governance/        # Charter、PROTOCOL、METHOD_SPEC、SAP、DATA_SPEC、Claim Matrix、各 registry
├── scripts/           # 00_preflight 至 80_build_release
├── audit/             # validate_*、verify_*、attack_suite
├── artifacts/         # preflight/trials/ledgers/seals/summaries/tables/figures/audit
├── manuscript/
└── release/
```

权威计划：`OWTDA_CAL_R1_COMPLETE_PLAN_v1.0.md`（2026-09-09 定稿；
仓库内副本 SHA256 `dca49727def3d31d2f367d58dba157e782946b862c28d29dd8508a6a3cc19ab3`）。
权威布局与执行合同见 `governance/PROJECT_CHARTER.md`。

## 立即规则

- 正式 MC 前必须完成共同冻结（预计 2026-09-23）。
- 任何结果/对象身份变更走 append-only registry，禁止覆盖/删除已登记对象。
- 旧 DMB-R1 结果仅作 L1 历史证据，不与本代 L2/L3 结果拼接。
