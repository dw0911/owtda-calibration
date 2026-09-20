# OW-TDA-CAL-R1

**重叠滑动窗口下拓扑扫描检验的交换性失效与校准边界**
*Exchangeability Failure and Calibration Boundaries of Topological Scans with Overlapping Windows*

> 论文配套的**完整可复现仓库**：实现代码、冻结配置、治理与身份链、论文源码（LaTeX）、canonical 图表数据与封存证据。
> 目标期刊：《山东大学学报（理学版）》"拓扑数据分析"专题。
> **快照：2026-09-20（R5-paper 阶段）**——正式 H0/H1 已封存保留；论文修订（R1）与图表重构（5 图 4 表）进行中。

---

## 1. 研究概要

重叠滑动窗口会破坏"窗口级置换检验"所依赖的可交换性前提，进而使拓扑扫描（persistent-homology based scan）检验的校准失效。本代研究给出：

1. **精确反例**：原始样本 IID、窗口边际同分布时，重叠窗口特征仍可以不可交换（T2）；
2. **有限样本校准图谱**：fixed-M / fixed-T 双预算、28 个 H0 格 × 2,500 replicate、8 个 H1 格 × 1,600 replicate 的逐格 Type-I 与功效；
3. **表示选择性**：BPI 与 MOMENTS 在两类备择（单时点边际均值-协方差匹配的 shape-change 与 mean-shift）下的镜像功效差；
4. **可重放证据链**：身份 / 账本 / seal / 表图逐字节可复算（治理链 append-only）。

**主要结果（已封存）**

| 量 | 值 |
|---|---|
| H0：M0 朴素置换（BPI / MOMENTS） | 拒绝率 0.4267 / 0.5462（严重反保守） |
| H0：M1 DMB 依赖乘子（BPI / MOMENTS） | 0.0458 / 0.0506（接近名义 0.05） |
| P1 / P2 / P3（Holm） | 0.5354 / 0.5330 / 0.0266（阈值 0.10 / 0.10 / 0.01，全部 SUPPORTED） |
| H1 表示差 Δ(BPI−MOMENTS) | shape-change **+0.9380** [0.9297, 0.9461]；mean-shift **−0.9463** [−0.9534, −0.9384] |

## 2. 仓库内容

| 路径 | 内容 |
|---|---|
| `src/owtda_cal/` | 核心实现（DGP、特征 BPI/MOMENTS、扫描统计、校准器 M0/M1、身份/哈希/账本、正式流水线） |
| `tests/` | 契约与攻击式回归测试（含"故意破坏必须失败"用例） |
| `configs/` | schema 与各类运行配置（smoke / confirm_null / confirm_h1 / real） |
| `governance/` | 章程、协议与规格（PROTOCOL / METHOD_SPEC / SAP / DATA_SPEC）、registry、冻结与身份对象、append-only `CHANGELOG.md` |
| `scripts/` | 编排与证据工具（审计包构建/验证、正式 runner、序列执行、release 导出等） |
| `audit/` | 独立验证器（freeze/schema/admission 校验、攻击套件、资源采样、repo 守卫） |
| `artifacts/` | 封存证据与成稿数据：`seals/`、`preflight/`、`summaries/`、`tables/`、`figures/`、`audit/`、`archive/`、`smoke/` |
| `manuscript/` | 论文 LaTeX 工程（`main.tex` + `sections/` + `bibliography.bib` + `main.pdf` + 补充材料 CSV + 绘图脚本） |
| `release/` | 正式交付包：`analysis/`（canonical 汇总与分析脚本）、`certificate/`、`h0_run/`、`h1_run/`、`plan/`、`summary/` |
| `environment/` | 冻结环境记录（版本、BLAS、线程设置、pip freeze、重建测试） |
| `external_prior_evidence/` | 旧代 DMB-R1 终止归档（L1 历史证据；按治理要求隔离存放，不参与本代估计） |

> 不随仓库分发的大对象（3.2 GB 原始账本 + 6 个大型派生索引）及其 SHA256、再生成方式：
> 见 [`REPRODUCIBILITY.md`](REPRODUCIBILITY.md) 与 [`EXCLUDED_ARTIFACTS.csv`](EXCLUDED_ARTIFACTS.csv)。

## 3. 安装

```powershell
# Python 3.12；依赖以 pyproject.toml + uv.lock 锁定
uv sync --frozen
# 等价替代：
# python -m venv .venv
# .\.venv\Scripts\Activate.ps1
# pip install -e ".[test,dev]"
```

冻结运行环境约定（与正式结果一致）：`PYTHONDONTWRITEBYTECODE=1`、`OMP/OPENBLAS/MKL/NUMEXPR_NUM_THREADS=1`；
详见 `environment/` 与 `scripts/frozen_env.py`。

## 4. 快速验证

```powershell
python -m pytest tests -q                 # 回归测试
python -m ruff check src tests audit scripts configs   # 静态检查（代码与工具域）
python scripts/check_canonical.py         # canonical 序列化契约（递归）
python audit/validate_freeze.py           # 冻结对象与 registry 自洽性
python audit/validate_schemas.py          # 逐行 schema 合同
python scripts/verify_release_contracts.py --help   # 发布合同验证器
```

> 说明：`ruff check .` 会额外报出 3 个**交付/构建脚本**（`release/analysis/scripts/*`、`manuscript/scripts/make_figures.py`）
> 的 14 项风格提示——它们保留了交付时的紧凑风格，逻辑无问题，如实披露（见 `REPRODUCIBILITY.md` §4）。

## 5. 复现论文

三级复现路径（详见 [`REPRODUCIBILITY.md`](REPRODUCIBILITY.md)）：

1. **图表/表（轻量）**：由 `artifacts/summaries/` + `release/analysis/` 的 canonical 汇总重生成图与表；
2. **分析链**：由封存账本（本地，不随仓库分发）重算 canonical 汇总、bootstrap 与 Holm；
3. **全链重跑**：预检 → 冻结/准入 → H0/H1 运行与 seal → 分析 → 成稿（需要相应算力）。

数据流唯一（禁止硬编码数字）：

```text
sealed trial JSON → validated canonical ledger → canonical summaries
→ tables/figures → manuscript_values.json → manuscript consistency checker
```

## 6. 数据

真实数据（PAMAP2 Protocol）**不随本仓库分发**；出处、许可、文件清单与逐文件 SHA256 见
[`DATA_SOURCES.md`](DATA_SOURCES.md)。本代 REAL 线为 `REAL_OMITTED_BY_DATA_GATE`（正文条件章节），
复现合成主线**不需要**真实数据。

## 7. 证据链与治理

- 正式运行 seal（H0/NULL 与 H1/ALT 的 RUN + PHASE seal，H1 parent 精确指向 H0）位于 `artifacts/seals/`；
  计数：NULL 70,000 data units / 140,000 feature rows / 280,000 evaluation rows；ALT 12,800 / 25,600 / 51,200。
- 所有治理与证据变更 **append-only**（`governance/CHANGELOG.md`、`*_REGISTRY.jsonl`、`reasons/`）；已 seal 对象不可覆盖。
- **字节身份**：`.gitattributes` 设置 `* -text`；canonical 对象以 exact bytes 计算 SHA256，禁止 EOL 转换。

## 8. 引用与许可

- 引用：见 [`CITATION.cff`](CITATION.cff)（作者名单与最终标题将在稿件定稿时更新）。
- 许可：`LICENSE` 当前为占位（All rights reserved，until publication decision）——决策将在投稿前登记并替换。

## 9. 已知限制与未闭合项（如实披露）

1. **P1–P3 精确调整后 p 值**：真实 10,000 次 cluster-bootstrap draws 已入库
   （`governance/actual_primary_draws.json`，P1/P2/P3 各 10,000）；最终表仍待以正式工具重算后替换 `<0.05` 占位。
2. **图表重构**：当前图件正按审查规格重绘（5 图 4 表 + 补充材料）；本快照含重构前的已核验数据。
3. **T4（Ω=qΓ0 的过程极限）**：未闭合，正文按 proposition 处理（理论降级为精确反例 + 解析方差放大 + 系统校准图谱）。
4. **REAL/PAMAP2**：因数据闸门（23<24 合格任务）omission，正文为条件章节。
5. 历史过程稿、旧代项目与大型本地证据不随仓库分发；如需，见 `external_prior_evidence/` 与各章说明。
6. **表 1–5 的原始生成器脚本未随项目保留**（表数据、输入哈希与 canonical 输入均已入库；补充数据表可逐字节复现）——
   投稿前随图表重构一并重建，详见 `REPRODUCIBILITY.md` §3.5。
7. 在发布快照上运行 `audit/validate_freeze.py` 会报 1 项 `source_tree_hash` 不匹配（原因与影响见 `REPRODUCIBILITY.md` §4）。
