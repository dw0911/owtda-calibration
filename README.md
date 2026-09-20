# Finite-Sample Calibration Boundaries of Topological Windowed Scanning

**OW-TDA-CAL-R1** · *Exchangeability Failure and Calibration Boundaries of
Topological Scans with Overlapping Windows*

> 论文配套的**可复现仓库**：代码、冻结配置、论文源文件、规范化汇总结果与图表生成脚本。
> 发布快照：**v1.1.1-paper**。
>
> **复现方式**
> - **Level 1（秒级）**：`verify_release.py --level quick` 核验代码、canonical 结果、正文表 1–5 与图件、论文 PDF 的全部数值与血缘。
> - **Level 2（账本级重做，可选）**：由正式账本（四份 ledger，约 3.2 GB，**不随仓库分发**）重做分析。
>   账本哈希登记在 `data/manifests/`；账本就位时 `fetch_archived_data.py --verify-only` 返回 0，否则返回 2。
>   **复现论文的合成实验不需要账本。**
> - **Level 3（从头重跑，主路径）**：`scripts/reproduce.py` 用代码 + 冻结种子从零重跑 H0/H1 Monte Carlo，
>   产出科学账本后与 canonical 对账，**零外部数据依赖**。
> - **许可**：代码 MIT；结果数据与论文源文件 CC BY 4.0（见 `LICENSE`、`LICENSES/`）。

## Overview

重叠滑动窗口会使"窗口级置换检验"失去可交换性前提，从而让拓扑扫描检验的校准失效。本仓库给出：
算法实现（BPI / MOMENTS 两种表示、扫描统计量、M0 朴素置换与 M1 依赖乘子两种校准器）、
冻结实验协议、一次正式 H0/H1 运行，以及从 canonical 汇总重建全部图表与论文的脚本。

## Scientific question

在重叠窗口、双预算（fixed-M 与 fixed-T）设计下：**朴素置换校准的有限样本 Type-I 边界在哪里？**
**依赖乘子（DMB）能把边界收回到什么程度？** 以及**不同拓扑表示（BPI vs MOMENTS）对两类备择的功效选择性如何？**

## Main findings

| 量 | 结果 |
|---|---|
| H0 逐格（28 唯一格 × 2,500 replicate） | M0 朴素置换**严重反保守**（BPI 0.4267、MOMENTS 0.5462 的合并拒绝率）；M1 明显降低极端反保守性，但逐格拒绝率仍为 0.0020–0.1412，**未达到统一的逐格名义校准**（合并拒绝率 0.0458 / 0.0506 仅作描述性汇总） |
| P1 / P2 / P3（10,000 次 cluster bootstrap + Holm） | **0.5354 / 0.5330 / 0.0266**（阈值 0.10 / 0.10 / 0.01，全部 SUPPORTED；tail = 0 → p = 1/10001，Holm = 3/10001） |
| H1 表示差 Δ(BPI − MOMENTS)（8 格 × 1,600 replicate） | shape change **+0.9380** [0.9297, 0.9461]；mean shift **−0.9463** [−0.9534, −0.9384]（镜像） |
| 交换性失效 | 精确反例 + 解析方差放大（理论节 T1–T5；T4 按 proposition 降级披露） |

**冻结规模**：`R₀ = 2500`（H0）、`R₁ = 1600`（H1）、`B = 999`；
H0 共 **280,000** evaluation、H1 共 **51,200**，合计 **331,200**（数据单元 82,800 / 特征行 165,600）。

## Repository structure

```text
src/owtda_cal/        核心实现（DGP、窗口/点云/PH、BPI/MOMENTS、扫描、M0/M1、身份与账本、正式流水线）
configs/              schema + 各 phase 配置；configs/formal/ 为冻结设计的可读快照
scripts/              规范入口（reproduce / verify_release / analyse_h0 / analyse_h1 /
                      bootstrap_primary_contrasts / build_tables / build_figures /
                      fetch_archived_data / build_release_manifest）
tests/                契约与攻击式回归
results/canonical/    **正文数值的单一真源**（canonical 汇总 + 主张—证据映射）
results/bootstrap/    P1–P3 真实 draws（npz）+ 推断摘要 + 元数据
artifacts/figures|tables/  图与表（脚本生成；每项附 meta.json：输入/输出哈希、脚本哈希、稿件引用）
governance/           冻结对象（FREEZE_MANIFEST、SEED_REGISTRY 与冻结设计登记；复现输入）
paper/                论文 LaTeX 工程（main.tex + sections + bib + main.pdf）+ 补充材料；
                      paper/scripts/make_tables.py 由 canonical 源生成正文表 1、3、4、5
                      （表 2 效应修饰表在正文手写），正文以 \input{../artifacts/tables/TableX.tex} 引用
release/analysis/scripts/  Level-2 的 H1 账本级重分析脚本（reanalyse_h1 / review_delivery）
reproducibility/      RUNBOOK / ENVIRONMENT / COMPUTE_REQUIREMENTS / DATA_AVAILABILITY /
                      FAILURE_POLICY / VALIDATION_SUMMARY / FORMAL_MANIFEST / RELEASE_MANIFEST /
                      SEED_MANIFEST / EXPECTED_OUTPUTS / ARTIFACT_INDEX / SHA256SUMS
data/                 manifests（正式账本 + 外部归档 + 校验和）、sample、external（占位）
docs/                 method_overview / result_definitions / faq
examples/             最小可用示例（复现单格 H0 / 单格 H1 / 窗口几何演示）
```

> 本仓库只包含复现论文所需的内容；审计/治理过程件与封存证据已剔除，见
> [`EXCLUDED_ARTIFACTS.csv`](EXCLUDED_ARTIFACTS.csv)。

## Quick start

```powershell
git clone <repo> && cd owtda-calibration
uv sync --frozen                                   # 按 uv.lock 建环境
python scripts/verify_release.py --level quick     # 最快：秒级验证全部论文数值与血缘
```

**完整复现（三层）**

```powershell
# Level 1 快速完整性验证（秒级，零外部数据）
python scripts/verify_release.py --level quick

# Level 2 由正式记录重做分析（分钟级，可选；需账本，见 §Data and large-file archive）
python scripts/fetch_archived_data.py --verify-only --report-only   # 查看归档状态
python scripts/fetch_archived_data.py --verify-only                 # 账本就位后必须返回 0
python scripts/analyse_h0.py --from-ledger data/external/H0_NULL_evaluation.scientific.jsonl
python scripts/bootstrap_primary_contrasts.py
python scripts/build_tables.py && python scripts/build_figures.py
python scripts/verify_release.py --level analysis

# Level 3 从头重跑（小时级；代码 + 冻结种子，零外部数据）
python scripts/reproduce.py --phase NULL --workers 8 --out ./repro   # H0：280,000 行
python scripts/reproduce.py --phase ALT  --workers 8 --out ./repro   # H1：51,200 行
python scripts/analyse_h0.py --from-ledger ./repro/H0_NULL_evaluation.scientific.jsonl
# 冒烟规模（几分钟）：--replicate-limit 32
```

## Reproduction levels

见 [`reproducibility/RUNBOOK.md`](reproducibility/RUNBOOK.md)：Level 1（秒级完整性）→ Level 2（账本 → 分析链）→
Level 3（全量重跑）。每层的命令、输入、预期产物与失败策略（fail-closed）在 RUNBOOK 与
[`reproducibility/FAILURE_POLICY.md`](reproducibility/FAILURE_POLICY.md) 中给出。

## Expected outputs

| 层级 | 预期 |
|---|---|
| Level 1 | `verify_release --level quick` 全部 PASS（H0 112/28、H1 16、P1–P3 合法性、图表血缘、SHA256SUMS） |
| Level 2 | 与 `results/bootstrap/P1_P3_BOOTSTRAP_SUMMARY.json`、`results/canonical/*` 一致（表 CSV 逐字节；图 PNG 逐字节）；**需先取得外部归档**，未闭合时 `fetch_archived_data.py --verify-only` 返回 2 |
| Level 3 | H0 280,000 / H1 51,200 evaluation 行，逐格与 canonical 汇总在容差内一致 |
| 论文 | `paper/main.pdf`（XeLaTeX；24 页，严格模式编译，0 未定义引用、0 缺图占位） |

机器可读清单：[`reproducibility/EXPECTED_OUTPUTS.json`](reproducibility/EXPECTED_OUTPUTS.json)、
图形/表格血缘：[`reproducibility/ARTIFACT_INDEX.csv`](reproducibility/ARTIFACT_INDEX.csv)。

## Table and figure generation

正文表 1、3、4、5 与全部图件均由 canonical 源生成，正文引用生成物；表 2（效应修饰）在正文手写、数值已核对：

| 产物 | 生成器 | 校验命令 | 说明 |
|---|---|---|---|
| `artifacts/tables/Table{1,3,4,5}_*.{tex,csv,json,json.meta.json}` | `paper/scripts/make_tables.py`（别名入口 `scripts/build_tables.py`） | `python scripts/build_tables.py --check` | 缺表、数值差异、多余未提交产物都会使校验返回非零 |
| `artifacts/figures/Figure*.{pdf,svg,png,meta.json}` | `paper/scripts/make_figures.py`（别名入口 `scripts/build_figures.py`） | `python scripts/build_figures.py --check` | 校验输入哈希、**当前生成脚本哈希**、输出哈希与稿件引用（**只核对哈希，不重绘图件**） |

- 图内标签为中文，需要**可确定获得**的 CJK 字体：Windows/macOS 使用系统字体，Debian/Ubuntu 使用
  `fonts-noto-cjk`（本机解析到 `Noto Sans SC`）。缺字体时 `make_figures.py` 默认**报错退出**，
  不会静默产出缺字方框；CI 用 `--check-fonts` 断言字体存在。
- `matplotlib` 是图件生成路径的依赖，通过锁定环境（`uv sync --frozen`）获得；`pyproject.toml`
  与 `uv.lock` 属 R1 冻结对象（字节由 `governance/FREEZE_MANIFEST.json` 钉住），本代不做修改，
  依赖因此显式记录在本文与 `reproducibility/ENVIRONMENT.md`。
- 同一 matplotlib 版本下重生成逐字节稳定：PNG/SVG 稳定（SVG 的时间戳元数据被剥离），
  PDF 抑制创建/修改时间。
- 论文编译的工作目录是 `paper/`。CI 与发布构建使用**严格模式**（`touch paper/STRICT.tex`）：
  缺图件、缺表或未定义引用都会直接失败，而不是渲染"图件缺失"占位框。

## Data and large-file archive

- **合成数据**：由代码 + 冻结种子生成，无需外部数据；
- **真实数据（PAMAP2）**：不随仓库分发，出处/许可/逐文件 SHA-256 见 [`DATA_SOURCES.md`](DATA_SOURCES.md)（本代 REAL 线为 `REAL_OMITTED_BY_DATA_GATE`）；
- **正式账本（约 3.2 GB）与大型派生索引**：**不随仓库分发**，哈希登记在
  [`data/manifests/external_artifacts.json`](data/manifests/external_artifacts.json)
  （大小 + SHA-256；索引含成员逐文件哈希），供核对一份副本的完整性
  （`scripts/fetch_archived_data.py --verify-only`，依赖缺失时返回 2）。**复现论文的合成实验不需要账本**——
  从头重跑用 `scripts/reproduce.py`。

## Computational requirements

见 [`reproducibility/COMPUTE_REQUIREMENTS.md`](reproducibility/COMPUTE_REQUIREMENTS.md)：
Level 3 约 **28 h**（8 workers，冻结预算外推）；峰值 RSS **1.4 GiB**、swap 增量 0、峰值磁盘约 0.4 GiB（账本 3.2 GB）；
**不需要 GPU**；Level 1/2 任意现代 CPU（分级实测：quick 秒级、回归约 77 s、编译约 1 min）。

## Paper and supplementary material

- 论文源文件与编译产物：[`paper/`](paper/)（`main.tex` + `sections/` + `bibliography.bib` + `main.pdf`）；
- 补充材料：`paper/supplement/supplement.pdf`（S1–S5：完整 112 行 H0、16 行 H1、分析规格、16×4 热图、代码与数据可用性）；
- 论文方法/理论/协议的权威定义：`paper/sections/02_method.tex`、`03_theory.tex`、`04_protocol.tex`
  与 `governance/{METHOD_SPEC,PROTOCOL,SAP,DATA_SPEC}_v1.0.md`。

## Citation

引用方式见 [`CITATION.cff`](CITATION.cff)（GitHub 会显示 "Cite this repository"）。
**软件 release 与论文请同时引用**。

作者：**王平（Wang Ping），河北金融学院与数据科学学院**（`AUTHORS.md`）。
`preferred-citation` 将在论文见刊后补入 `CITATION.cff`。

## License

本仓库分三部分许可：

| 对象 | 许可 | 文件 |
|---|---|---|
| 代码（`src/`、`scripts/`、`tests/`、`paper/scripts/`、`configs/`） | **MIT** | [`LICENSE`](LICENSE) |
| 本项目自行产生的结果数据（`results/`、`artifacts/`、清单与归档账本） | **CC BY 4.0** | [`LICENSES/DATA_LICENSE.txt`](LICENSES/DATA_LICENSE.txt) |
| 论文源文件与 PDF（`paper/`） | **CC BY 4.0** | [`LICENSES/PAPER_LICENSE.txt`](LICENSES/PAPER_LICENSE.txt) |
| 第三方组件与数据 | 见 [`THIRD_PARTY_NOTICES.md`](THIRD_PARTY_NOTICES.md)（PAMAP2 为 CC BY 4.0，**不重新分发**） | — |

转载/再分发时请按 CC BY 4.0 保留署名（`AUTHORS.md` 与 `CITATION.cff` 给出了署名信息）。

## Contact and issue reporting

- 缺陷与复现报告：使用仓库的 issue 模板（`Bug report` / `Reproducibility report`），
  请附 `git rev-parse HEAD`、环境与本机输出；
- 贡献路径与硬性约束（不得改 `pyproject.toml`/`uv.lock` 与已封存对象）见 [`CONTRIBUTING.md`](CONTRIBUTING.md)。

---

**说明**：

- 正文表 1、3、4、5 由 `paper/scripts/make_tables.py` 从 canonical 源生成，正文 `\input` 生成结果；表 2（效应修饰）在正文手写，其 8 个数值已与 canonical 逐格拒绝率核对一致；
- 图件生成依赖 `matplotlib`（锁定环境提供）；
- `H0_PRIMARY_CONTRASTS.json` 中历史 `p = 0` 值仅作字节保留，现行有效值见 `results/bootstrap/`。
