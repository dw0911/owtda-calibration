# BPI-Scan 从零重构：完整实验协议 v1.2-draft（冻结完整性纠错）

**协议日期：** 2026-09-03；v1.1 生效 2026-09-07；v1.2-draft 生效 2026-09-08  
**目标期刊：** 《山东大学学报（理学版）》“拓扑数据分析”专题  
**投稿截止：** 2026-10-31  
**计划投稿日：** 2026-10-25；2026-10-26 至 2026-10-31 仅作系统或格式故障缓冲  
**方法工作名：** BPI-Scan（Persistence-Intensity Scan with dependent multiplier calibration）  
**协议状态：** `METHOD_FREEZE_REOPENED_FOR_COMPLETENESS_CORRECTION`（E2 前置审计裁定：`E2_ADMISSION = NO_GO`；method-freeze 在技术上未成立——DMB 递归与 baseline common-support 属冻结后新增的 D 类组件。整改路线 R0–R4 完成前禁止任何正式科学 Monte Carlo；禁止核、带宽、中心化、candidate、eligibility、统计量或阈值二次调整。）  
**文献基准：** `BPI_Scan_Literature_Audit_20260830.md`、`BPI_Scan_Claim_Evidence_Matrix_20260830.md`、`BPI_Scan_Core_References_20260830.bib`

**冻结完整性纠错（修订事件 `AM-20260908-001`，2026-09-08）：** E2 前置审计（`BPI_E2_PRE_AUDIT_REPORT_20260908`）认定：既有 `v1.1.0-method-freeze-dmb-r1` freeze 对象不完整——完整 DMB 递归（`dmb_recursive.py`）、表示 common-support（DistHist/Moment series assembler）、标准 ledger/provenance、E2 runner 均在 freeze 与 E1-CONFIRM **之后**才实现；global-null recursion 产物从未执行 child nodes（`max_depth=1` 脚本常量）。按 §25.1“递归改变属 D 类 → 全部 CONFIRM 及下游失效”，既有 freeze 重新开启（`METHOD_FREEZE_REOPENED_FOR_COMPLETENESS_CORRECTION`），既有 E1 产物整体降为开发/历史诊断（`D-FREEZE-COMPLETENESS-20260908` 污染矩阵，`AFFECTED_RERUN_REQUIRED`）。**不改变**已冻结的科学方法定义（Bartlett 核、`b0=max(q0,ceil_cuberoot(M))`、外部 iid padding、全段均值、bridge、共同标量乘子、PCG64DXSM seed、资格、p 值 plus-one/`>=`/`≤0.05`）——本次纠错只把方法完整实现与证据基础设施纳入同一源码快照后**重做 freeze**（规格 §23 重放 R2/R3）。方法 ID 保持 `bpi_scan_dmb_bartlett_r1`。

### 0.0 冻结完整性纠错 — 证据/治理语义澄清（R0，2026-09-08，仅追加不删改）

以下澄清只改变**证据、治理与时间语义**，不改变任何科学 Gate 阈值或方法参数（`AM-20260908-001`）：

1. **方法冻结对象（重定义）**：一次 method-freeze 必须同时锁定并逐字节快照以下全部：核心方法代码（`dependent_multiplier.py`、`multipliers.py`、`bridge.py`、`dmb_recursive.py`、`naive.py`、`baselines.py` 的 series assembler、`scan.py`、`segmentation.py`、`windows.py`、`seeds.py`）、runner 脚本、tests、`configs/*.yaml`、`schema.json`、`requirements.lock`、DMB 绑定规格原件。任一对象冻结后才出现或改动，均属 D 类 → 该 freeze 不成立、需纠错后重做（本事件即首次执行）。
2. **递归是正式 E1/E2 的组成**：global-null recursion 与 E3 的“sequencewise FWER”必须由冻结递归器真实执行并保存每个被检验节点的 trace（a,b,n,b0,m_min,candidates,p,reject,c_hat,terminal_reason）。根拒绝恒等式（FWER=root-reject）只允许作为**派生检查**，不得替代递归执行证据。
3. **CONFIRM ledger 标准字段**（正式 CONFIRM 起强制）：除身份与结果字段外，必须包含 `seed_metric_bootstrap, data_sha256, environment_sha256, freeze_identity_sha256, attempt_id, retry_count, runtime_seconds` 及 node trace 引用；精确字段集由 `evidence_tables.TRIAL_FIELDS` 注册。缺列、未知列或 expected/actual outer 不闭合时，run 不可作为确认证据。
4. **时间语义**：`RUN_STARTED` 在**任何 payload 计算前**写入 `started_at_utc`；`finished_at_utc` 在结束时写入；全链 UTC。run 目录名时间戳 + event 时间共同构成先后证据；freeze 的“tag 时间”以 annotated tag object 的 commit/author 时间为准。
5. **Correction 与 seal**：Gate evaluator 修复只生成**新派生 Gate/correction 事件**（`CORRECTION_APPENDED`），禁止改写已 seal run 的 payload 后同 run ID re-seal；确需纠正 run 内容时走 `RUN_INVALIDATED` + 新 run。
6. **Overlap 配对身份**：任何“配对差”（如 O75−O0）必须在**同一 outer_id** 上定义。同一 replicate 的四个 overlap cells 共用 base data seed 与 `outer_id`，每个 cell/method 使用唯一 `trial_id`；不同 cell 若 data seed 不同则只能报告独立样本差。
7. **Smoke/formal 隔离**：DEV smoke 与正式 run 使用不同完整 namespace（如 `POWER/E2-SMOKE/DEV` vs `POWER/E2-H1/CONFIRM`），并分别落 outer manifest；formal 前机器验证 `intersection(outer_id)=∅` 且 `intersection(seed_data)=∅`。smoke 数值仅用于开发，禁止用于调参或 Gate 判定。
8. **G0-CONTRACT 固定分母**：正式冻结契约分母以**机器 test manifest** `configs/contract_manifest.json`（明确列出全部 pytest node id）为准；由 `scripts/01_e0_contracts.py` 读取并判定（0 skip/0 fail）。旧“75=40+35”字面分母废止（`AM-20260908-001`/审计 P0-02）；manifest 随源码快照冻结，改动属 D 类。
9. **D0 判定对象**：D0 通过除现有 ledger 外，必须保存 data seed 清单、每条序列原始输入 hash、production/reference candidate hash 与 equality、PPW 原始值与 `truncated=false` 字段，否则不得作为 freeze 准入。

---

## 0. 协议权威性与使用规则

### 0.1 单一权威来源

本文件是新项目实验设计的唯一人工可读权威来源。机器可读配置、代码默认值、测试和论文方法段必须由本文件派生。发生冲突时，按以下优先级裁决：

1. 已签名的协议修订记录；
2. 本文件；
3. 机器可读配置；
4. 实现代码；
5. README、日志和论文草稿。

代码与协议不一致时，代码结果不得进入论文。

### 0.2 与旧项目隔离

旧项目只承担两项功能：提供失败案例清单；提供需要重新建立的契约测试清单。新项目执行以下隔离规则：

- 新建独立仓库 `bpi-scan-rebuild`；
- 不复制旧项目的 `SRC/`、配置、缓存、预测、ledger、canonical 结果或图表；
- 旧压缩包和旧仓库不加入 `PYTHONPATH`；
- 新论文不得引用旧实验数字；
- 若后续人工迁移某段旧算法，必须先有独立规格和慢速参考实现，再通过逐值一致性测试，并在 `MIGRATION_LOG.md` 记录来源；
- 新仓库第一次正式 Monte Carlo 前生成源代码树 SHA256；旧结果与新结果在物理目录和命名空间上完全分离。

### 0.3 结果用途分层

| 层级 | 名称 | 可否调参 | 可否写入论文主结果 |
|---|---|---:|---:|
| L0 | 单元测试、微型确定性例 | 可修实现 | 仅作方法验证说明 |
| L1 | DEV 开发实验 | 允许一次协议修订 | 不可作为确认性结果 |
| L2 | CONFIRM 独立确认 | 禁止结果驱动修改 | 可以 |
| L3 | SENSITIVITY 预注册敏感性 | 禁止改变主配置 | 可以，标注敏感性 |
| L4 | REAL-VAL 真实数据确认 | 禁止回到开发网格 | 可以 |
| L5 | REAL-PRIVATE 密封评估 | 完全冻结 | 可以，属于最终证据 |

---

## 1. 研究定位与可检验问题

### 1.1 研究对象

给定有序时间序列

\[
X_t\in\mathbb R^p,\qquad t=0,\ldots,T-1,
\]

假设序列可由若干近似平稳状态拼接而成，未知变点为

\[
0<\tau_1<\cdots<\tau_K<T.
\]

本研究把局部时间片转换为点云，再由 Vietoris–Rips 持久同调得到持久图序列。目标是检测持久图期望测度的一阶密度，即局部持久强度发生变化的位置。

直接近邻包括早期拓扑变点检测、TADA 的重叠依赖分析及近期持久强度两样本检验；对应 BibTeX keys 为 `islambekov2020changepoints`、`chazal2024tada`、`han2026twosample`。

### 1.2 核心研究问题

- **RQ1（校准）：** 重叠时窗产生的共享样本依赖下，依赖高斯乘子 bootstrap（DMB）校准能否使拓扑最大扫描检验在预注册平稳原假设族中达到经验 size 等效区间？
- **RQ2（机制）：** 在原始观测独立时，naive permutation 的失校准是否随窗口重叠比例系统性增强？
- **RQ3（拓扑价值）：** 在均值和协方差匹配、环结构或有限尺度连通结构发生变化的备择中，持久强度表示能否提供可检测信号，并相对低阶矩特征产生增量功效？
- **RQ4（多变点）：** 经校准的区段最大扫描能否在未知变点数条件下保持合理的误报、检出和定位表现？
- **RQ5（外部适用性）：** 方法在 HASC 自然活动序列与 TSSB 构造型分割基准上的覆盖率、相对表现和计算边界如何？

### 1.3 允许的创新主张

若对应 Gate 通过，论文可以主张：

1. 提出面向重叠持久图序列的局部持久强度扫描流程；
2. 用冻结的 Bartlett 依赖高斯乘子 bootstrap 校准区段最大统计量，并以重叠诱导记忆下限与 PPW 候选保护量作为有限样本防护；
3. 在统一扫描壳中分离拓扑表示收益与依赖校准收益；
4. 系统报告节点 size、全局无变点序列误报、多变点功效、定位和数据适用覆盖率；
5. 给出方法在短序列、长依赖和真实基准上的失败边界。

以下表述永久禁用：

- 首次将 TDA 用于变点检测；
- 首次发现滑动窗口会产生依赖；
- 首次提出依赖数据的块重采样；
- 持久强度普遍优于标量、距离或其他分割方法；
- 依赖乘子 bootstrap 或任何校准在有限样本中精确控制 0.05，或称为 tuning-free；
- TSSB 代表完全自然的真实变点；
- 一个节点的 0.05 检验等同于部分原假设下的强 FWER 控制。

---

## 2. 统计目标、原假设与证据边界

### 2.1 持久图随机测度与强度

第 \(i\) 个时窗在同调维度 \(k\in\{0,1\}\) 上产生持久图 \(D_i^{(k)}\)。写成点测度：

\[
\mu_{D_i^{(k)}}=\sum_{u\in D_i^{(k)}}\delta_u.
\]

状态 \(r\) 下的期望持久测度及其密度定义为

\[
\Lambda_r^{(k)}(A)=\mathbb E_r\{\mu_D^{(k)}(A)\},\qquad
\lambda_r^{(k)}(z)=\frac{d\Lambda_r^{(k)}}{dz}(z).
\]

直观上，单张持久图类似一次星空快照；强度 \(\lambda_r\) 类似长期观测后得到的星体出现密度。单窗口核平滑图仍带有单次随机性，多个同状态窗口的平均才估计状态强度。

### 2.2 检验目标

对任一区段 \([a,b]\) 的派生特征过程 \(Z_a,\ldots,Z_b\)，节点原假设为

\[
H_{0,a:b}:\{Z_i\}_{i=a}^b\text{ 严格平稳、}\alpha\text{-mixing，且 }\mathbb E Z_i=\mu_{a:b}.
\]

工作假设进一步要求存在 \(\eta>0\)，使

\[
\mathbb E\lVert Z_0\rVert^{4+\eta}<\infty,
\qquad
\sum_{h=1}^{\infty}h^2\alpha(h)^{\eta/(4+\eta)}<\infty.
\]

该条件是有限维表面向量上采用依赖乘子 bootstrap（DMB）的保守充分条件。真实数据无法直接证明满足它，所以论文将其列为方法假设，并用候选保护量、资格检查（§6.3）和敏感性实验描述偏离风险。

单变点备择为

\[
H_{1,a:b}:\exists c\in\mathcal C_{a:b},\quad
\mathbb E Z_i=
\begin{cases}
\mu_L,&i\le c,\\
\mu_R,&i>c,
\end{cases}
\quad \mu_L\ne\mu_R.
\]

因此，主统计量针对持久表面的均值变化，也就是平滑后的持久强度变化。它没有覆盖持久图分布的全部高阶变化；两个分布可能具有相同强度，同时具有不同点数方差或点间相互作用。

### 2.3 误差定义

- **Nodewise size：** 对一条无变点区段执行一次最大扫描检验的拒绝概率；
- **Global-null sequencewise FWER：** 对一整条无变点序列运行完整递归后，至少报告一个变点的概率；
- **Partial-null strong FWER：** 部分区段含真实变点时，对所有真实无变化区段的联合误报概率。本研究不作理论控制承诺；
- **额外误报概率：** 含变点序列上 \(P(\widehat K>K)\)；
- **误报个数：** \(V=\max(\widehat K-K,0)\) 的分布与均值。

全局无变点时，递归算法只有根节点先被拒绝才会产生任何变点，所以 sequencewise FWER 与根节点拒绝事件相同。含真实变化时，递归选择会产生额外适应性，需通过多变点模拟单独评估。

### 2.4 方法冻结前必须完成的数学说明

方法章节至少完成以下三个结果，证明范围与引用边界必须逐项写明：

1. **强度联系：** 对固定核与权重，证明

\[
\mathbb E\{S_i^{(k)}(z)\}
=\int w(u)K_{h_k}(z-u)\lambda^{(k)}(u)\,du,
\]

即平均持久表面估计加权强度的核卷积；理论依据连接到 `chazaldivol2020density` 与 `wu2024intensity`；
2. **重叠依赖：** 在原始观测独立且窗口映射可测时，原始支持互不相交的窗口特征独立；支持发生交叠时通常不具交换性。给出 \(q_0\) 的保守上界并用 E1-OVERLAP 验证有限样本后果；
3. **Bootstrap 边界：** 对固定有限网格特征，在严格平稳、适当矩条件和混合条件下，依赖乘子（dependent multiplier/wild）框架要求带宽 \(b_n\to\infty\)、\(b_n/\sqrt n\to0\)。引用 `shao2010dependent`（依赖随机权重框架）、`bucher2016dependent` 与 `bucchiawendler2017`（Hilbert 空间值过程与变点最大统计量）。数据依赖网格、PPW 候选保护、递归选择和有限样本性能由预注册 Gate 与模拟验证，不延伸成未经证明的定理；`M^{1/3}` 属于预注册的确定性带宽选择，不作最优性宣称。

数学说明在 `docs/method_spec.md` 中完成，并由一个“假设—代码对象—实验”对照表连接到实现。若无法证明第一项恒等式或说明第三项适用条件，禁止进入 CONFIRM。

---

## 3. 数据到拓扑特征的冻结映射

### 3.1 预处理

所有规则均逐序列执行，不使用变点标签。

1. 将 `Inf/-Inf` 转为缺失值；
2. 全空通道删除；
3. 缺失率不超过 5%，且单个连续缺口不超过 25 个采样点：内部线性插值，首尾用最近有效值；
4. 其余含缺失通道删除；
5. 通道 IQR 小于 \(10^{-12}\) 时删除；
6. 每个剩余通道采用全序列 median/IQR 缩放：

\[
\widetilde X_{tj}=\frac{X_{tj}-\operatorname{median}_t(X_{tj})}
{\operatorname{IQR}_t(X_{tj})+10^{-12}}.
\]

对离线无监督变点问题，全序列无标签缩放属于固定特征映射。它会利用未来观测的边际尺度，因此论文明确限定为 offline 方法。

### 3.2 单变量延迟嵌入

单变量序列固定嵌入维数 \(d=3\)。给定原始窗口长度 \(W\) 和延迟 \(\delta\)，窗口内产生

\[
Y_j=(\widetilde X_j,\widetilde X_{j+\delta},\widetilde X_{j+2\delta}),
\qquad j=0,\ldots,W-1-2\delta.
\]

要求窗口内点数

\[
n_P=W-2\delta\ge24.
\]

合成主实验固定 \(\delta=2\)。TSSB 的 \(\delta\) 使用完整原始序列的样本自相关函数，取第一个 \(|\widehat\rho(h)|<e^{-1}\) 的滞后，并截断到

\[
1\le\delta\le\min\left(20,\left\lfloor\frac{W-24}{2}\right\rfloor\right).
\]

若上界小于 1，该序列在拓扑方法下不具备资格。

### 3.3 多变量窗口点云

多变量序列直接把窗口内的 \(p\) 维观测向量作为点云，不额外做时间延迟嵌入。这样可避免把“通道维度”和“延迟维度”混合成难以解释的参数。

### 3.4 窗口、步长和索引

原始窗口长度为 \(W\)，步长为 \(s\)。第 \(i\) 个窗口覆盖原始索引

\[
[is,\,is+W-1],\qquad i=0,\ldots,M-1,
\]

其中

\[
M=1+\left\lfloor\frac{T-W}{s}\right\rfloor.
\]

合成主配置固定

\[
W=64,\qquad s=16,\qquad M=192,
\]

故原始长度固定为

\[
T=W+s(M-1)=3120.
\]

候选 \(c\) 位于窗口 \(c\) 与 \(c+1\) 之间，映射到原始时间轴：

\[
\tau_{\mathrm{raw}}(c)=
\operatorname{round}_{\mathrm{half\,up}}
\left[(c+\tfrac12)s+\frac{W-1}{2}\right].
\]

这里的窗口定义保证延迟向量完全位于其原始窗口内部，所以无需再添加延迟偏移。所有代码采用 0-based 半开区间；所有表格面向读者时转换为 1-based，并在字段名中显式写出索引体系。

### 3.5 重叠记忆下限

相邻窗口共享原始观测。保守重叠记忆下限定义为

\[
q_0=\left\lfloor\frac Ws\right\rfloor+1.
\]

它类似相邻照片共享的像素跨度：原始观测即使独立，连续照片仍会因复用像素而相关。主配置下 \(q_0=5\)。

---

## 4. 持久同调与持久表面

### 4.1 持久同调配置

| 项目 | 主配置 |
|---|---|
| 复形 | Vietoris–Rips |
| 距离 | Euclidean |
| 系数域 | \(\mathbb F_2\) |
| 同调维度 | \(H_0,H_1\) |
| `maxdim` | 1 |
| 点云重复点 | 字典序排序后精确去重 |
| \(H_0\) essential class | 删除死亡时间为无穷的类 |
| 浮点 | float64 |
| 主实现 | Ripser |
| 交叉实现 | GUDHI，仅用于 E0 小样本一致性 |

输入点顺序理论上不应改变持久图。代码在所有降采样或抽样前执行字典序规范化，以阻断前缀选择带来的顺序依赖。

### 4.2 距离尺度

每个点云计算非零成对距离的中位数 \(a_i\)，整条序列的距离尺度为

\[
s_{\mathrm{dist}}=\operatorname{median}_{i=0}^{M-1}a_i.
\]

计算规则：

- 点云不超过 200 点时使用全部点对；
- 超过 200 点时，先字典序排序，再使用由 `series_id + config_hash` 派生的固定随机流抽取最多 4096 个无重复点对；
- 全部窗口均参与中位数聚合；
- \(s_{\mathrm{dist}}<10^{-12}\) 时序列标为退化；
- 持久图的 birth 和 persistence 坐标统一除以 \(s_{\mathrm{dist}}\)。

### 4.3 持久表面

把持久图坐标从 \((b,d)\) 转为 \((b,p=d-b)\)。第 \(i\) 个窗口、维度 \(k\) 的表面为

\[
S_i^{(k)}(z)=\sum_{u=(b,p)\in D_i^{(k)}}p^\gamma
\frac{1}{2\pi h_k^2}
\exp\left(-\frac{\lVert z-u\rVert_2^2}{2h_k^2}\right).
\]

主配置固定 \(\gamma=1\)。空持久图映射为全零表面。

### 4.4 带宽、截断和网格

对整条序列同一同调维度的有限持久点池执行：

1. 按 \((b,p)\) 字典序排序；
2. 超过 5000 点时用固定派生种子无放回抽取 5000 点；
3. 带宽 \(h_k\) 取抽样点两两距离中位数；
4. 下限：

\[
h_k\ge10^{-6}\max(C_{b,k},C_{p,k},1);
\]

5. \(C_{b,k}\) 与 \(C_{p,k}\) 分别为 birth 和 persistence 的 0.995 分位数；
6. 超过 cap 的坐标仅在表面计算时 Winsorize，原持久图保留；
7. 网格上界为

\[
B_{\max,k}=C_{b,k}+\max(0.05C_{b,k},3h_k),
\]

\[
P_{\max,k}=C_{p,k}+\max(0.05C_{p,k},3h_k);
\]

8. 主网格固定为 \(20\times20\)；
9. 每个向量元素乘以网格单元面积的平方根，使欧氏范数逼近连续 \(L_2\) 范数。

网格、cap、带宽和距离尺度均按整条序列计算一次，递归区段不得重估。记录每个 channel 的点数、空图率、clipping rate 和退化原因。clipping rate 超过 1% 时触发数值审计，结果在审计结束前不得进入 CONFIRM。

### 4.5 Channel 标准化与组合

对每个可用同调维度，令表面向量为 \(Z_i^{(k)}\)，全序列均值为 \(\bar Z^{(k)}\)，能量尺度为

\[
a_k=\left\{\frac1{M-1}\sum_{i=0}^{M-1}
\lVert Z_i^{(k)}-\bar Z^{(k)}\rVert_2^2\right\}^{1/2}.
\]

若 \(a_k<10^{-10}\)，该 channel 全局退化并被删除。其余 channel 标准化为 \(Z_i^{(k)}/a_k\)，再按 \(1/\sqrt K\) 拼接，\(K\) 为有效 channel 数。这使每个 channel 对总能量具有相同的一阶权重，同时保留 channel 内空间结构。

---

## 5. 最大扫描统计量

### 5.1 候选集合

PPW 只形成候选保护量，不决定校准带宽。在完整序列上计算
\(q_0=\lfloor W/s\rfloor+1\)，按
\[
\ell_{\mathrm{cand}}=\max\left(q_0,\left\lceil\widehat\ell_{\mathrm{PPW}}\right\rceil\right),
\qquad
m_{\min}=\max(2\ell_{\mathrm{cand}},20),
\]
并置候选两侧最小窗口数为 \(m_{\min}\)：

\[
\mathcal C^0_{a:b}=\{c:a+m_{\min}-1\le c\le b-m_{\min}\},
\]

删除距离既有检出点不超过 \(q_0\) 的候选后得 \(\mathcal C_{a:b}\)。候选排序固定为全局索引升序；`ell_candidate` 数值上等于旧路线 `ell_final`，语义改为 candidate guard，禁止传入 DMB 乘子生成器。

### 5.2 CUSUM 型局部强度差

对候选 \(c\)，定义

\[
C_{a:b}(c)=
\sqrt{\frac{n_Ln_R}{n_L+n_R}}
\left(\bar Z_{a:c}-\bar Z_{c+1:b}\right),
\]

其中 \(n_L=c-a+1\)、\(n_R=b-c\)。扫描分数为

\[
T_{a:b}(c)=\lVert C_{a:b}(c)\rVert_2^2,
\qquad
T^{\max}_{a:b}=\max_{c\in\mathcal C_{a:b}}T_{a:b}(c).
\]

平方根权重用于平衡左右样本量。缺少该权重时，极端候选会因均值方差较大而机械占优。

### 5.3 平台与并列规则

令

\[
\varepsilon_T=10^{-12}\max(1,|T^{\max}_{a:b}|).
\]

从全局最大位置向左右扩展，取得所有满足 \(T(c)\ge T^{\max}-\varepsilon_T\) 的连续平台；选取该平台 0-based 索引的 lower median。任何排序方式、线程数或浮点并列均必须返回相同位置。

---

## 6. 依赖校准：高斯 Bartlett 依赖乘子 bootstrap（DMB-R1）

本协议的主推断器自 v1.1（修订事件 `AM-20260907-003`）起为 dependent Gaussian multiplier bootstrap（方法 ID `bpi_scan_dmb_bartlett_r1`）。DMB 以相关随机权重作用于固定的窗口特征序列，用乘子部分和的桥接过程近似最大 CUSUM 统计量在原假设下的分布。本节为协议层冻结选择；逐字技术定义、伪代码、seed 串、RNG、状态码与 35 项契约见绑定规格 §5–§14。

### 6.1 主带宽（冻结规则）

主乘子带宽每条完整序列计算一次，全部递归节点复用：

\[
\operatorname{ceil\_cuberoot}(M)=\min\{j\in\mathbb N:j^3\ge M\},
\qquad
b_0=\max\{q_0,\operatorname{ceil\_cuberoot}(M)\}.
\]

实现必须用整数比较求 `ceil_cuberoot`，禁止依赖浮点 `M**(1/3)` 取整。主配置 \(W=64,s=16,M=192\) 时 \(q_0=5,\ \operatorname{ceil\_cuberoot}(192)=6,\ b_0=6\)。E1-OVERLAP 各 stride 的 \(b_0\)：stride 64/32/16/8 → \(q_0=2/3/5/9\)，\(b_0=6/6/6/9\)。`b0` 不受候选、标签、观测统计量、p 值或 PPW 影响；不设 `floor(M/8)` 硬 cap（资格不足的合法 abstain 见 §6.3）。

### 6.2 乘子随机过程

核固定为 Bartlett：\(\varphi(u)=(1-|u|)_+\)。对一个节点、一个 bootstrap replicate，生成相互独立的标准高斯创新 \(\varepsilon_0,\ldots,\varepsilon_{n+b_0-2}\sim N(0,1)\)，并以长度 \(b_0\) 的标准高斯移动平均构造

\[
\xi_i=\frac1{\sqrt{b_0}}\sum_{j=0}^{b_0-1}\varepsilon_{i-1+j},\qquad i=1,\ldots,n,
\]

给出 \(\mathrm E\xi_i=0\)、\(\mathrm{Var}(\xi_i)=1\)、\(\mathrm{Cov}(\xi_i,\xi_{i+h})=(1-|h|/b_0)_+\)，且协方差矩阵天然半正定，无需 Cholesky、特征裁剪或数值 jitter。

边界规则固定为 `external_iid_padding`：为节点外部生成足够独立创新使每个 \(\xi_i\) 恰好含 \(b_0\) 个创新。禁止 circular wrap、零/反射 padding、首尾缩短移动平均后重标定、从父节点乘子截取子序列、以及把不同 replicate 拼成连续过程。

对每个时点 \(i\)，同一个标量 \(\xi_i\) 同时乘该时点全部 \(D\) 个特征坐标（shared scalar multiplier）。禁止逐 channel、逐网格像素或逐坐标的独立乘子：那会破坏 \(\lVert CUSUM\rVert_2^2\) 的联合 null 几何。生成的 \(\xi\) 不做 replicate 内去均值、方差重标定、winsorize/clip/rank、antithetic 配对或按观测符号重排。

### 6.3 Eligibility 与 abstention

原 stationary-bootstrap 资格条件（`ell_final <= floor(M/8)`、至少八个期望物理块）随块重采样废止。DMB 支持下限为

\[
n_{\min,\mathrm{DMB}}=\max(8b_0,2m_{\min}+1).
\]

完整序列仅在以下全部条件满足时输出根节点 p 值：窗口特征至少一个 channel 有效；`ell_candidate` 有定义且有限；根候选集合非空；\(M\ge8b_0\)；\(M\ge2m_{\min}+1\)；全部输入、中间与乘子统计量有限；无技术异常。

根记录状态码：`SUCCESS`；`INELIGIBLE`（reason ∈ `INELIGIBLE_FEATURE_DEGENERATE` / `INELIGIBLE_PPWCAND_UNDEFINED` / `INELIGIBLE_NO_CANDIDATE` / `INELIGIBLE_DMB_SUPPORT` / `INELIGIBLE_TWO_SIDED_MARGIN`）；`ERROR`（`TECHNICAL_*`）。多条件同时失败时主 reason 优先级固定：feature → PPW-candidate → two-sided margin → DMB support → no candidate。合法 `INELIGIBLE` 属于方法 abstention；`ERROR` 属证据不完整；两者不合并为 missing，不得以新增 seed trial 替换。子节点不满足条件时以 `TERMINAL_TWO_SIDED_MARGIN` / `TERMINAL_DMB_SUPPORT` / `TERMINAL_NO_CANDIDATE` 正常终止并记入 recursion trace，不改变根 eligibility。

分母规则：合成校准同时报告 `N_generated`、`N_eligible`、`N_error`、`K_reject`；conditional size \(=K/N_{eligible}\)；unconditional rejection \(=K/N_{generated}\)；E2 端到端功效以 `N_generated` 为分母，合法 abstention 计未检出；真实数据 eligibility 以原始 manifest 全部序列为分母；技术失败不从真实数据分母删除，private 中存在未闭合技术失败时 Gate 保持阻断。

### 6.4 节点残差与桥接统计量

对节点 \([a,b]\) 用单一全段均值：

\[
\bar X=\frac1n\sum_{i=1}^n X_i,\qquad R_i=X_i-\bar X.
\]

残差中心化按递归节点重新计算；特征生成、网格、cap、KDE 带宽与 channel scale 沿用完整序列冻结值。第 \(r\) 个 replicate 定义部分和

\[
U_k^{*(r)}=\sum_{i=1}^k\xi_i^{(r)}R_i,\qquad U_n^{*(r)}=\sum_{i=1}^n\xi_i^{(r)}R_i,
\]

及 Brownian-bridge 校正

\[
G_k^{*(r)}=U_k^{*(r)}-\frac{k}{n}U_n^{*(r)},
\]

随后扫描分数

\[
C^{*(r)}_{a:b}(c)=\sqrt{\frac{n}{k(n-k)}}G_k^{*(r)},\qquad
T^{*(r)}_{a:b}(c)=\lVert C^{*(r)}_{a:b}(c)\rVert_2^2,
\]

\[
T^{\max,*(r)}_{a:b}=\max_{c\in\mathcal C_{a:b}}T^{*(r)}_{a:b}(c).
\]

同一候选集合用于观测统计量与全部 replicates；bootstrap 内不重估 PPW、`m_min`、候选、网格、cap、KDE 带宽或 channel scale。基于观测最大位置的分段中心化被禁止（优先保护 null size）。观测 \(T_{a:b}(c)\)、\(T^{\max}\) 与 `c_hat` 保持原定义（§5.2–§5.3）；实现必须证明均值差写法与部分和写法在冻结容差内一致（见规格 §7.4 与契约测试）。

### 6.5 p 值

主确认和真实数据使用 \(B=999\)；开发使用 \(B=199\)；次级功效、敏感性使用 \(B=499\)：

\[
p=\frac{1+\sum_{r=1}^{B}\mathbf 1\{T^{\max,*(r)}_{a:b}\ge T^{\max}_{a:b}\}}{B+1}.
\]

显著性水平固定 \(\alpha=0.05\)，比较符号固定为 `>=`，拒绝规则固定为 \(p\le0.05\)；因此 \(B=199/499/999\) 时超过或等于观测值的 replicate 数上限分别为 \(9/24/49\)。零残差节点 \(T^{\max}=0\) 且全部 \(T^{*}=0\) 依 `>=` 得 \(p=1\)。

### 6.6 Naive permutation 机制对照

Naive 对节点残差行做全排列（不保留相邻结构），其他候选、统计量、递归、\(B\)、指标、外层数据与 BPI-common-support eligibility 全部与 DMB 一致。它仅作为机制对照，不作推荐推断方法；其作用在于揭示忽略依赖时排列 p 值的失校准方向。

### 6.7 乘子随机性与 seed

每个节点、每个 replicate 的乘子流由独立派生 seed 生成。对完整 namespaced 字符串
`BPI-SCAN-V1|DMB-R1|segment|<experiment_id>|<cell_id>|<replicate_id>|<method_id>|<a>|<b>|<u>|multiplier`
取 SHA256 前 8 字节按 big-endian 解释为 uint64 作 `seed[a,b,u]`；以 `numpy.random.Generator(numpy.random.PCG64DXSM(seed))` 初始化并只调用一次 `rng.standard_normal(n+b0-1, dtype=float64)`。batch size、worker 数、resume 次数与队列实现不得改变乘子序列；同一 trial 的 DMB multiplier seed manifest 记入 ledger（`multiplier_seed_manifest_sha256`）。

### 6.8 第二次方法调整禁止

DMB-R1 失败后不得调整核、带宽常数、中心化、资格线或乘子分布后重试；可靠推断主线直接终止（失败路由见 §14.6、§21 与绑定规格 §18.4/§26）。

---

## 7. 多变点递归

### 7.1 算法

1. 把根区段 \([0,M-1]\) 放入队列；
2. 取队首区段；
3. 若区段不满足 DMB 支持条件（§6.3），标记为 terminal 并记录 reason；
4. 计算区段最大扫描统计量（观测定义不变，§5.2）与 DMB-R1 p 值（§6.4–§6.5）；
5. 若 \(p>0.05\)，标记为 terminal；
6. 若 \(p\le0.05\)，记录平台中位位置 \(\widehat c\)；
7. 将 \([a,\widehat c]\) 与 \([\widehat c+1,b]\) 按左后右顺序入队；
8. 子区段候选排除距任何已记录变点 \(q_0\) 以内的位置；
9. 队列为空后，将变点排序并映射回原始时间轴。

每个区段使用由自身全局端点 \((a,b)\) 派生的全新乘子流，父节点乘子不得复用（见 §6.7 与绑定规格 §8/§10）。FIFO 与固定左右顺序保证相同种子下随机流消费顺序完全确定；即使队列实现变化，同一节点（相同 \(a,b\)）的 DMB 结果不变，因为 seed 仅依赖全局端点而非入队次序。

### 7.2 递归显著性解释

每个被选择区段使用 \(\alpha=0.05\)。论文只对单节点 size 和 global-null sequencewise FWER 作确认性校准声明；部分原假设下的误报由 E3 模拟报告，不宣称强 FWER 理论保证。bootstrap replicate 的 argmax 不参与变点位置估计。

### 7.3 分辨率边界

方法能够分辨的最短区段由 DMB 支持下限

\[
n_{\min,\mathrm{test}}=\max(8b_0,2m_{\min}+1)
\]

决定（原 \(\max(8\ell,2m_{\min}+1)\) 规则废止，见 §6.3）。映射到原始样本尺度约为 \(s\,n_{\min,\mathrm{test}}\)。所有真实数据必须报告这一边界以及因此失去资格的序列比例。

---

## 8. 表示归因与外部算法基线

### 8.1 共享扫描壳的表示基线

以下方法共享窗口、候选、DMB-R1 校准壳（\(b_0\)、`ell_candidate`、`m_min`、eligibility）、递归和指标，唯一变化是窗口特征：

| 名称 | 窗口特征 | 科学作用 |
|---|---|---|
| BPI-Scan | \(H_0+H_1\) 持久表面 | 主方法 |
| BPI-H0 | 仅 \(H_0\) | 同调维度归因 |
| BPI-H1 | 仅 \(H_1\) | 同调维度归因 |
| TopoScalar-Scan | 每维有限点数、total persistence、max persistence | 检验强度表面的增量信息 |
| DistHist-Scan | 32-bin 窗口内成对距离直方图 | 检验 PH 相对一般几何信息的增量 |
| Moment-Scan | 均值、log 方差、通道相关、lag-1 自相关 | 检验相对低阶统计量的增量 |
| Landscape-Scan | 前 3 层 persistence landscape，固定 64 点 | 表征敏感性，仅 E4 |

DistHist 的全局 bin 上界取整条序列全部窗口距离的 0.995 分位数，超出者进入最后一格；每个直方图归一为总质量 1。Moment-Scan 对多变量窗口使用每通道均值、log 方差、lag-1 自相关和相关矩阵上三角；单变量使用均值、log 方差、偏度、超额峰度及 lag 1–3 自相关。零方差项按 0 处理并记录。

表示归因主分析采用 **BPI-common-support**：先由 BPI 特征一次性计算 \(b_0\)、\(\ell_{\mathrm{cand}}\)、\(m_{\min}\)、候选集合和 eligibility，随后全部共享壳表示（含 Moment、DistHist 的 BPI-common-support 版本）复用同一组值，且任一基线自估带宽的 operational 版本只可进入补充表。这样，方法差异只来自窗口表示；DMB 校准不属于表示增量。

### 8.2 完整算法基线

主真实数据比较包含：

1. PELT-RBF；
2. Kernel Change-Point Detection；
3. ClaSP；
4. changeforest；
5. E-Divisive；
6. S-CPD。

前五项必须本地运行。S-CPD 在 2026-09-10 前完成官方代码和依赖复现；若作者未公开可运行实现，则保存检索证据、环境错误和复现记录，正文只作 related work，不以自写近似实现冒充原方法。

完整算法的资源上限固定为：单序列 30 分钟、单方法整套数据 24 小时、单进程峰值内存 16 GB。超过上限记为 timeout/OOM，并进入失败率分母；不得静默排除。全分辨率结果是主比较。10 倍等间隔降采样只可作为补充的计算可行性分析，必须使用独立表格和方法名后缀 `-DS10`。

### 8.3 基线调参规则

HASC public-dev 是唯一带标签调参区：

- PELT-RBF：\(\mathrm{pen}=c\log T\)，\(c\in\{0.5,1,2,4,8\}\)；
- KernelCPD：相同 penalty 网格；
- ClaSP：窗口 \(W\in\{50,100,150\}\)，其余采用官方自动分段协议；
- changeforest：官方默认随机森林与二分分割；最小区段换算为主方法同一 raw-time 下限；
- E-Divisive：显著性 0.05，499 次置换，最小区段使用同一 raw-time 下限；
- S-CPD：官方默认参数，窗口在 \(\{50,100,150\}\) 中用 public-dev 选择。

每种方法分别选择 public-dev 上 subject-macro Covering 最大的配置。差异小于 0.005 时，依次选择运行时间更短、自由参数更少、窗口更小的配置。public-val 只运行一次，不参与再次选择。private 和 TSSB 禁止调参。

### 8.4 两类公平性

- **表示公平性：** 共享扫描壳方法使用完全相同的推断和递归代码；
- **算法公平性：** 完整算法保留其原生机制，同时共享原始数据、开发标签预算、最小区段尺度、评价指标和超时规则。

完整算法若天然使用不同时间分辨率，论文同时报告全数据结果和 BPI-eligible common-support 结果，不把降采样结果与全分辨率结果作直接非劣推断。

---

## 9. 随机数、确定性和并行

### 9.1 根种子

| 用途 | 64-bit 根种子 |
|---|---:|
| DEV | 14624430889863187540 |
| CONFIRM-A | 7652214086111030190 |
| CONFIRM-B | 10714481306926991779 |
| POWER | 6338124067242535181 |
| REAL-SPLIT | 8824389276957873083 |
| RESAMPLING | 4023015224203201134 |
| FIGURES | 4871402478146422143 |

这些整数由字符串 `BPI-SCAN-V1|CONTEXT` 的 SHA256 前 8 字节按 big-endian 解释得到。

### 9.2 Trial 级派生

每个随机流由下式独立派生：

\[
\operatorname{seed}(e,c,r,s)=
\operatorname{uint64}\left(
\operatorname{SHA256}[\texttt{BPI-SCAN-V1}|e|c|r|s]_{0:8}
\right),
\]

其中 \(e\) 为 experiment ID，\(c\) 为 cell ID，\(r\) 为 replicate ID，\(s\in\{\texttt{data,subsample,tie,metric_bootstrap}\}\)。四类非 DMB 流显式使用 `PCG64DXSM`；DMB 乘子使用独立 segment 派生。各流不得共享 seed。

**DMB 乘子 seed（v1.1，取代 `resample` 流的 stationary 语义）：** 对每个节点与 bootstrap replicate，seed 由规格 §6.7 字符串独立派生并仅初始化一次 `PCG64DXSM`。DMB-R1 使用新 namespace（`DMB-R1` segment），旧 `resample` 命名空间下无 DMB 乘子。数据 seeds 与派生规则保持原注册值，D 类重跑不得更换外层数据 seed。

### 9.3 并行规则

- Windows 使用 `spawn`，所有入口放在 `if __name__ == "__main__":` 下；
- 外层 trial 并行，单个 trial 内保持单线程；
- `OMP_NUM_THREADS=1`、`MKL_NUM_THREADS=1`、`OPENBLAS_NUM_THREADS=1`；
- worker 数只由 E0-COMPUTE 基准选择；候选为 \(\{1,4,8,12\}\)；
- 相同 trial 在不同 worker 数下输出必须逐字节一致，运行时间字段除外。

---

## 10. 新仓库结构

```text
bpi-scan-rebuild/
├─ README.md
├─ PROTOCOL.md
├─ CHANGELOG_PROTOCOL.md
├─ CLAIM_EVIDENCE_MATRIX.md
├─ pyproject.toml
├─ requirements.lock
├─ configs/
│  ├─ templates/base.template.yaml
│  ├─ resolved/e0_geometry.yaml
│  ├─ resolved/e0_compute.yaml
│  ├─ resolved/d0_applicability.yaml
│  ├─ resolved/e1_dev.yaml
│  ├─ resolved/e1_confirm.yaml
│  ├─ resolved/e1_overlap.yaml
│  ├─ resolved/e1_dependence.yaml
│  ├─ resolved/e2_smoke.yaml
│  ├─ resolved/e2_formal.yaml
│  ├─ synthetic.yaml
│  ├─ e1_calibration.yaml
│  ├─ e3_multiple_cp.yaml
│  ├─ e4_sensitivity.yaml
│  ├─ hasc.yaml
│  └─ tssb.yaml
├─ src/bpi_scan/
│  ├─ preprocessing.py
│  ├─ embedding.py
│  ├─ windows.py
│  ├─ persistence.py
│  ├─ surfaces.py
│  ├─ block_length.py            # PPW 仅作候选保护量（ell_candidate）
│  ├─ inference/
│  │  ├─ __init__.py
│  │  ├─ dependent_multiplier.py # DMB-R1 主推断器（v1.1）
│  │  ├─ multipliers.py          # Bartlett 乘子构造（external_iid_padding）
│  │  ├─ bridge.py               # 部分和与 Brownian-bridge 校正
│  │  └─ naive.py                # 机制对照全排列
│  ├─ stationary_bootstrap.py    # historical 套件；不再进入 DMB method-freeze 通过条件
│  ├─ scan.py
│  ├─ segmentation.py
│  ├─ synthetic.py
│  ├─ datasets.py
│  ├─ baselines.py
│  ├─ metrics.py
│  ├─ seeds.py
│  ├─ ledger.py
│  └─ provenance.py
├─ tests/
├─ scripts/
│  ├─ 00_preflight.py
│  ├─ 01_e0_contracts.py
│  ├─ 02_e0_compute.py
│  ├─ 10_e1_dev.py
│  ├─ 11_e1_confirm.py
│  ├─ 12_e1_overlap.py
│  ├─ 20_e2_power.py
│  ├─ 30_e3_multiple_cp.py
│  ├─ 40_e4_sensitivity.py
│  ├─ 50_hasc_manifest.py
│  ├─ 51_hasc_dev.py
│  ├─ 52_hasc_val.py
│  ├─ 53_hasc_private_predict.py
│  ├─ 54_hasc_private_evaluate.py
│  ├─ 60_tssb.py
│  ├─ 70_build_canonical.py
│  ├─ 71_build_tables.py
│  ├─ 72_build_figures.py
│  ├─ 80_audit_release.py
│  └─ 81_reproduce_smoke.py
├─ data/
│  ├─ raw/                 # gitignored
│  ├─ manifests/
│  └─ labels_private/      # 与预测进程隔离
├─ cache/                  # gitignored；只缓存真实数据 PH
├─ runs/                   # 每次运行不可覆盖
├─ artifacts/
│  ├─ canonical/
│  ├─ tables/
│  ├─ figures/
│  └─ seals/
└─ docs/
   ├─ method_spec.md
   ├─ resampling_spec.md
   ├─ metric_spec.md
   ├─ baseline_spec.md
   ├─ data_spec.md
   └─ audit_spec.md
```

---

## 11. 环境与预检

### 11.1 冻结环境

主机为 Windows 11 Pro、Intel i5-12600KF 10 核/16 线程、31.81 GB 内存、RTX 4070 SUPER、Python 3.12.10。标准 Ripser 路线主要使用 CPU；GPU 不进入主实验。

新建干净虚拟环境，不继承全局 186 个包。初始核心版本固定为：

```text
python==3.12.10
numpy==2.2.6
scipy==1.15.3
pandas==2.3.3
scikit-learn==1.7.2
statsmodels==0.15.0
ripser==0.6.15
persim==0.3.8
ruptures==1.1.10
changeforest==1.2.1
claspy==0.2.8
joblib==1.5.3
pytest==9.1.1
PyYAML==6.0.3
```

其余依赖安装后写入 `requirements.lock`，同时保存 `pip freeze`、Python build、操作系统、CPU、内存和 BLAS 信息。`arch` 仅作为 PPW 黄金值交叉验证的开发依赖，其实际版本同样进入 lock；正式运行调用项目内经过交叉验证的实现，避免运行环境隐式变化。

### 11.2 存储规则

- 开始正式实验前目标盘可用空间不得低于 25 GB；
- 低于 15 GB 自动停止新任务；
- 合成 trial 的 PH 和表面只在内存中存在，保存 ledger、聚合量及每格前 20 个审计样本；
- HASC/TSSB 的 PH 可持久缓存；
- 任何缓存必须以数据 hash、预处理 hash、窗口参数、Ripser 版本和代码 commit 共同寻址。

### 11.3 PRE-FLIGHT 输出

`00_preflight.py` 必须生成：

- `environment.json`；
- `package_lock_sha256.txt`；
- `hardware.json`；
- `data_manifest.csv`；
- `source_tree_sha256.txt`；
- `preflight_report.md`。

Gate G0-PREFLIGHT：所有核心包可导入、磁盘达标、BLAS 线程受控、随机种子重放一致、Git 工作区干净。任一项失败时不得进入 E0。

---

## 12. 实现顺序与契约测试

### 12.1 实现任务顺序

1. 建仓库、环境、配置 schema 和 provenance；
2. 实现 seed 派生和 append-only ledger；
3. 实现合成生成器及其统计不变量；
4. 实现预处理、窗口、延迟嵌入和索引映射；
5. 实现 Ripser 包装与 GUDHI 小样本交叉检查；
6. 实现距离尺度、持久表面、网格和 channel 组合；
7. 实现慢速候选扫描参考版；
8. 实现前缀和向量化扫描，并与参考版逐值核对；
9. 实现 PPW 候选保护量（`ell_candidate`）与 `arch` 黄金值交叉验证；
10. 实现 DMB-R1：`ceil_cuberoot`/主带宽、Bartlett 乘子构造、外部 padding、节点残差与桥接、动态分母与资格状态码（规格 §5–§9）；
11. 实现 naive permutation 机制对照；
12. 实现节点检验；
13. 实现确定性递归与 raw-time 映射；
14. 实现表示基线（BPI-common-support 复用 DMB `b0/ell_candidate/m_min/eligibility`）；
15. 实现指标；
16. 实现 HASC/TSSB loader 与 label firewall；
17. 实现完整算法基线；
18. 实现 canonical builder、表格、图形和 release audit。

任何后序模块不得在其前置测试未通过时启动正式结果计算。

### 12.2 冻结前必须通过的测试

#### A. 数据与索引

1. 半开区间窗口数量公式覆盖整除与非整除案例；
2. 单变量延迟向量只读取本窗口原始样本；
3. diagram boundary 到 raw time 的手算案例逐项相同；
4. 递归局部索引恢复为全局索引正确；
5. `round-half-up` 与 Python banker rounding 的反例测试；
6. 全局平移和正交旋转后距离矩阵相对误差小于 \(10^{-10}\)；
7. 固定时间窗口内的点顺序随机重排后，点云集合、持久图和表面不变；原始时间顺序不得重排。

#### B. 持久同调与表面

8. Ripser 与 GUDHI 在固定微型点云上的 persistence pair 数和距离误差达标；
9. \(H_0\) 无穷类删除；
10. 空 \(H_1\) 返回固定长度零向量；
11. 全局空 channel 被删除且组合权重重归一；
12. cap 与网格上界为不同字段；
13. 16/20/24 网格乘面积后 \(L_2\) 数值收敛；
14. 超 5000 持久点时的规范化抽样对输入顺序不敏感；
15. 任一特征参数变化均导致 cache miss。

#### C. 扫描与重采样（DMB）

16. 前缀和扫描与慢速参考实现最大绝对误差小于 \(10^{-10}\)；
17. 候选两侧长度恰好等于 \(m_{\min}\) 时可用；
18. 平台中位只在最大连续平台内返回；
19. `>=` tie 规则和加一 p 值公式正确；
20. data/sub-sample/tie 随机流互不相同；DMB multiplier 流在独立 namespace；
21. 相同 trial 在 1、4、8 worker 下科学输出哈希一致（multiplier 逐字节相同）。

> **DMB 专项契约（35 项，0 skip）按绑定规格 §14 执行**：A. 带宽与候选 6 项（`ceil_cuberoot`、`b0` 不变性、候选一致性）；B. 乘子过程 8 项（逐字节复现、seed 独立性、\(b=1\)、手算 MA、首中末边界、无 circular wrap、矩/协方差 Monte Carlo、PSD）；C. 向量与桥接 7 项（共同乘子坐标倍数、逐坐标乘子攻击失败、桥接端点为零、观测统计量两写法一致、慢双循环参考、\(R=0\)、删 bridge 攻击检出）；D. p 值/递归/资格 7 项（exceedance 界、`==`计入、`8b0` 边界、`m_min` 边界、seed 随端点、子节点不截父乘子、状态不混用）；E. 可复现/治理 7 项（worker 一致性、resume、env hash、common-support 一致、旧 stationary 输出拒绝、污染矩阵、seed/node/ledger/seal 反查）。

#### D. 递归和指标

22. 无合法候选区段正常终止；
23. 左右子区段覆盖父区段且无缺失、无重叠；
24. exclusion zone 不从特征数组物理删除观测；
25. tolerance matching 使用一对一最大基数、最小总距离匹配；
26. 反例 `true=[0]`、`pred=[1,1000]` 在 tol 内的 matched MAE 为 1，同时产生一个 false positive；
27. Covering 的方向固定为 `Covering(true, pred)`；
28. global-null 一次根拒绝后产生的变点计入 sequencewise FWER；
29. 同一预测文件重复评价逐字节相同。

#### E. 隔离和可复现性

30. private prediction 进程尝试打开 label 文件时测试必须失败；
31. dirty Git worktree 无法运行 CONFIRM 或 PRIVATE；
32. 缺少 config hash、data hash 或 commit 的 trial 无法进入 canonical；
33. 重复 `trial_id` 被拒绝；
34. 故意删除一行 ledger 后完整性检查失败；
35. 图表脚本出现硬编码结果数字时静态扫描失败；
36. 从空目录执行 smoke reproduction 可重建 E0 微型结果。

> 原 A–E 中的 stationary 专属契约（原第 19–22 项等）随主方法废止，保留在 **historical test suite** 执行但不作为 DMB method-freeze 通过条件。

Gate **G0-CONTRACT（v1.1）：原 40 项（historical 套件）+ DMB 新增 35 项 = 75 项全部通过，0 skip / 0 xfail**；允许 skip 的测试数量为 0。

---

## 13. E0：确定性正确性与计算基准

### 13.1 E0-GEOMETRY

固定微型点云：单点、两点、三角形、四边形、规则 32 点圆、两个相离小圆。检查：

- \(H_0\) finite death 数为唯一点数减一；
- 圆的主 \(H_1\) 类对旋转、平移和点顺序保持；
- 两圆在适当尺度出现两个长寿命 \(H_1\) 类；
- 加入 \(10^{-6}\) 级扰动后 bottleneck distance 满足稳定性数量级；
- Ripser/GUDHI 输出经排序后相符。

这些是表示层测试，不用于选择最终 DGP 难度。

### 13.2 E0-COMPUTE

对 \(W\in\{48,64,96\}\) 各生成 128 个代表点云，worker \(j\in\{1,4,8,12\}\) 各运行 3 次。记录：

- 冷启动时间；
- 单窗口 PH 中位数、P90、P99；
- 每秒窗口数；
- 峰值 RSS；
- 第三次相对第一次吞吐率；
- 表面、扫描和 499/999 bootstrap 的时间占比。

worker 选择规则：峰值 RSS 不超过 24 GB，第三次吞吐率不低于第一次的 90%；合格者中选吞吐最高者；吞吐差异不超过 5% 时选 worker 更少者。选择结果先封存在 `artifacts/freeze/compute_budget.json`，再由 `scripts/05_bind_compute_budget.py --apply` 逐个写入 `configs/resolved/*.yaml`；绑定后不得按实验结果调整。

### 13.3 E0-BLOCK-PILOT → D0-APPLICABILITY-PILOT（v1.1）

**历史记录：** 原块长适用性压力测试（R0/R2，stationary 语义）已执行并判 `FAIL_APPLICABILITY`（2026-09-07，run `…22f2a753`，见 `CHANGELOG_PROTOCOL.md` AM-20260907-002）。DMB-R1 带宽完全脱离 PPW 后，该旧 Gate（“alternative `ell` 中位数 ≤ null 两倍”等）标记 `SUPERSEDED_BY_DMB_R1`，其观测机制作为候选保护诊断保留。

**v1.1 新适用性门（D0-APPLICABILITY-PILOT，规格 §15）：** 复用已生成的多变量正确路由下 300 条 L1 数据（N-AR null 100 / E2-H1-MID 100 / C-MEAN-Δ1 100），保持原 data seeds、原始序列、特征与候选输入；不计算 p 值、拒绝率或功效，也不生成新 outer data。逐 trial 报告 \(M,W,s,q_0,\widehat\ell_{\mathrm{PPW}},\ell_{\mathrm{cand}},m_{\min},b_0,8b_0,2m_{\min}+1,n_{\mathrm{cand}},\text{root eligible},\text{reason}\)，含变化组另报真实变点是否位于候选。

通过须同时满足：300/300 无技术错误；三组各自根 eligibility ≥95/100；两个含变化组真实变点位于合法候选的比例 ≥95/100；全部 \(b_0\) 与冻结公式一致；候选集合一致性测试 100%；无人为截断。失败路由见规格 §15.4（代码错误修复后整批 300 重跑；无错误则 `DMB_R1_FAIL_APPLICABILITY` 终止主线）。

### 13.4 总预算路由

用 E0 实测时间外推本协议全部 outer trials：

- 预计 wall time 不超过 72 小时：执行完整矩阵；
- 预计 wall time 为 72–144 小时：E1 CONFIRM 和两个 E2 primary 数量保持，所有标记为 secondary 的外层 MC 减半；
- 预计 wall time 超过 144 小时：暂停，先优化缓存、前缀和和批处理；不得直接削减确认性样本量。

实际路由和公式保存于 `compute_budget.json`。GPU 不作为进入 Gate 的条件。

---

## 14. E1：校准与重叠机制

### 14.1 Null 生成器

所有 null 均无变点，主配置 \(W=64,s=16,M=192,T=3120\)。

| ID | 生成过程 | 具体参数 |
|---|---|---|
| N-IID | 单变量高斯白噪声 | \(X_t\sim N(0,1)\)，\(d=3,\delta=2\) |
| N-AR | 单变量 AR(1) | \(X_t=0.8X_{t-1}+\sqrt{1-0.8^2}\epsilon_t\)，平稳初始化 |
| N-VAR | 二变量 VAR(1) | \(A_0=\begin{psmallmatrix}0.72&0.16\\-0.08&0.68\end{psmallmatrix}\)，缩放到谱半径 0.8；创新 \(N(0,I_2)\)，burn-in 1000 |
| N-CIRCLE | 稳定环动力系统 | \(\theta_0\sim U(0,2\pi)\)，\(\theta_t=\theta_{t-1}+2\pi/32+\eta_t\pmod{2\pi}\)，\(\eta_t\sim N(0,0.03^2)\)；二维 AR(1) 测量噪声 \(\rho=0.6,\sigma=0.10\) |

### 14.2 E1-DEV（E1-DEV-DMB）

目的仅限发现实现错误与冻结前的 smoke 校准；数值不得进入论文 size 结论（规格 §16）。

- 4 个 null × stride \(s\in\{16,64\}\)；
- 每格 200 outer trials；合计 1600；
- 每 trial：`bpi_scan_dmb_bartlett_r1` 与 naive permutation，\(B=199\)；
- 外层 data seeds 保持原注册值；DMB multiplier seeds 用新 namespace（§6.7）；
- 禁止通过 DEV 调整 DMB 带宽、核、中心化、资格线或乘子分布。

DEV Gate（每格同时满足）：技术错误 0；`N_eligible/N_generated>=0.95`；eligible trials 上 DMB 经验拒绝率 ∈ [0.015,0.10]；全部 p 值 ∈ \(\{1/(B+1),...,1\}\)；seed/hash/common-support/ledger 审计通过。DEV 失败先 seal 并 code-line audit：确认 bug 允许在 method-freeze 前修复，受影响的 D0 与全部 DEV cell 整体重跑；未发现 bug 则记录 `DMB_R1_FAIL_DEV` 并停止推断主线。DEV 通过后生成 `METHOD_FREEZE_REPORT.md`，完成修订并标记 `v1.1.0-method-freeze-dmb-r1`。

### 14.3 E1-CONFIRM（E1-CONFIRM-DMB 主校准）

| 项目 | 冻结值 |
|---|---:|
| Cells | N-IID、N-AR、N-VAR、N-CIRCLE |
| 每格 outer trials | 2000（CONFIRM-A 1000 + CONFIRM-B 1000） |
| 每 trial bootstrap | 999 |
| 方法 | `bpi_scan_dmb_bartlett_r1`、`naive_permutation` |
| 名义水平 | 0.05 |
| 主区间 | 90% Wilson CI |
| 等效带 | [0.03, 0.07] |

已有外层数据逐 trial 复用原 data seed；不存在时按原注册 data seed 生成；禁止为 DMB 更换更有利的 null 数据。每个 cell 全量重算 DMB p 值与递归 trace。

Gate **G1-CALIBRATION-DMB**（每格）：`N_error=0`；`N_eligible/N_generated>=0.95`；在 eligible trials 上经验 Type-I 的 90% Wilson CI 完全位于 [0.03,0.07]；A/B 两批分别报告且差异判定同原规则。整数快捷条件 \(73\le K\le121\) **仅当该格 2000 条全部 eligible 时可用**；存在合法 abstention 时必须按实际 `N_eligible` 程序化计算 Wilson 区间，禁止继续用整数捷径。同时报告 `K/N_generated` 及其 Wilson 区间作为 end-to-end 拒绝量（不替代 conditional Gate）。

Naive 机制对照：naive 对节点残差行全排列，其他候选、统计量、B、数据与 BPI-common-support eligibility 与 DMB 一致；至少 N-IID、N-AR 两格的 95% Wilson 下界大于 0.10（\(N=2000\) 全 eligible 时自 \(K\ge227\) 满足）；动态分母按共同 eligible trials 计算。其余两格要求方向一致并完整报告。

### 14.4 E1-OVERLAP 因果隔离

仅使用 N-IID，保持 \(M=192\)，改变原始长度以匹配步长：

| Cell | \(s\) | 重叠率 \(1-s/W\) | Outer trials | \(B\) |
|---|---:|---:|---:|---:|
| O0 | 64 | 0% | 1000 | 499 |
| O50 | 32 | 50% | 1000 | 499 |
| O75 | 16 | 75% | 1000 | 499 |
| O875 | 8 | 87.5% | 1000 | 499 |

Gate G1-OVERLAP（DMB 版本，规格 §19.1）：

1. O0 naive 的 90% Wilson CI 位于 [0.03,0.07]（该格全部 1000 条 eligible 时才允许整数形式 \(39\le K\le56\)）；
2. O75 与 O875 naive 的 95% Wilson 下界均大于 0.10；
3. O75 减 O0 的配对拒绝率差异，其 one-sided 95% bootstrap 下界大于 0.05；
4. DMB 四格 conditional size 的 90% Wilson CI 位于 [0.025,0.075]（全 eligible 时 \(34\le K\le61\)）；
5. 每格 DMB eligibility ≥95%，技术错误为 0。

主推断器为 DMB-R1（各 stride 的 \(b_0\) 见 §6.1）。这组实验在原始数据独立条件下隔离重叠因素。AR/VAR 的非重叠窗口仍可能经底层过程保持相关，所以不能承担纯重叠因果识别。

### 14.5 E1-DEPENDENCE 诊断（DMB）

- N-AR、N-VAR；
- \(s\in\{64,32,16\}\)；
- 每格 500 outer trials；共 3000；
- \(B=499\)；
- 报告 \(q_0\)、\(b_0\)、\(\widehat\ell_{\mathrm{PPW}}\)、\(\ell_{\mathrm{cand}}\)、\(m_{\min}\)、candidate count、eligibility、conditional/unconditional size、p-value QQ 图，以及特征 pilot ACF（仅诊断）。

任一 DMB 格点的 95% Wilson 下界高于 0.08，先做 code-line audit；无 bug 时按 DMB-R1 终局失败处理（不得调整 \(b_0\) 后保留该 Gate）。

### 14.6 G1 失败路由与终局（DMB-R1）

1. 先冻结现有输出并运行 code-line audit；
2. 若确认实现 bug，修复后修改 patch 版本，四个 CONFIRM cell 使用全新派生 namespace 整体重跑；
3. 若未发现 bug：`FINAL_METHOD_FAILURE_DMB_R1`。随后固定执行：停止“可靠统计推断”主线；禁止 E2/G2 作为正式功效证据；禁止 HASC private 与 TSSB 正式预测；论文转方法诊断/负结果或停止本专题投稿；**禁止再改 Bartlett 核、\(M^{1/3}\) 常数、中心化、带宽或 eligibility 后重跑**（规格 §18.4）。

**已完成的 redesign 历史：** v1.0 曾允许一次方法级 redesign（把 stationary resampler 换为预注册的 DMB）。该 redesign 已于 2026-09-07 作为唯一路线签署生效（`AM-20260907-003`），本协议 v1.1 即其结果；从此不允许第二次方法级 redesign。

---

## 15. E2：单变点功效与拓扑归因

### 15.1 E2-H1：环到八字环

状态 A：

\[
f_A(\theta)=(\cos\theta,\sin\theta).
\]

状态 B：

\[
f_B(\theta)=(\sin\theta,\sin2\theta).
\]

当 \(\theta\sim U(0,2\pi)\) 时，两者均值为 0，协方差均为 \(I_2/2\)，但主要环结构分别对应一个环和两个环。相同低阶矩使该实验更接近“拓扑信息是否带来增量”的识别设计。

相位过程与 N-CIRCLE 相同，映射在 \(\tau=T/2\) 处切换。二维测量噪声为边际标准差 \(\sigma\)、AR 系数 \(\rho\) 的平稳 AR(1)，跨变点连续且不重置。

| 因素 | 水平 |
|---|---|
| \(\rho\) | 0、0.6、0.8 |
| \(\sigma\) | 0.05、0.10、0.20 |
| Cells | 9 |
| Primary | (0.6,0.10)、(0.8,0.20) |
| Primary outer trials | 各 1000 |
| 其余 outer trials | 各 400 |
| Bootstrap | 499 |

比较：BPI-Scan、BPI-H0、BPI-H1、TopoScalar、DistHist、Moment、ClaSP、changeforest。

### 15.2 E2-H0：矩匹配的有限尺度连通变化

状态 A：

\[
X\sim N(0,I_2).
\]

状态 B：

\[
X\sim\tfrac12N((-a,0),\operatorname{diag}(1-a^2,1))
+\tfrac12N((a,0),\operatorname{diag}(1-a^2,1)).
\]

两状态均值与协方差均相同。由于高斯分布具有全空间支撑，这里称为“有限尺度连通结构变化”，不宣称总体支撑发生严格拓扑改变。

- \(a\in\{0.70,0.85,0.95\}\)；
- 每格 500 outer trials；
- \(B=499\)；
- iid 时间顺序；
- 比较 BPI-H0、BPI-H1、BPI-Scan、DistHist、Moment、changeforest。

### 15.3 E2-CONVENTIONAL：传统变化对照

| ID | 变化 | 两个效应水平 |
|---|---|---|
| C-MEAN | \(N(0,1)\to N(\Delta,1)\) | \(\Delta=0.5,1.0\) |
| C-VAR | \(N(0,1)\to N(0,r^2)\) | \(r=1.5,2.0\) |
| C-AR | AR 系数变化 | 0.2→0.7、0.4→0.8 |

每格 300 outer trials，\(B=499\)。该实验用于展示低阶基线擅长的区域，不设置 BPI 优胜门槛。

### 15.4 单变点评价

真实变点 \(\tau\) 与预测点进行一对一匹配。主容差为

\[
\delta_{\mathrm{match}}=W/2,
\]

并报告 \(W/4\) 与 \(W\) 两个敏感性容差。

- 端到端功效（主定义，规格 §20.1）：\(\mathrm{power}_{\mathrm{e2e}}=\#\{\text{eligible 且拒绝且定位命中}\}/N_{\mathrm{generated}}\)，合法 abstention 与未拒绝均计未检出；
- conditional power（eligible trials 上，仅补充，不承担主结论）；
- Precision、Recall、F1：一对一匹配；
- matched MAE；
- normalized MAE：\(\mathrm{MAE}/W\)；
- exact-K rate；
- extra-FP probability；
- 运行时间分解。

### 15.5 Gate G2-TOPOLOGY

在两个 E2-H1 primary cells 上：

1. 中等 cell 的 BPI power 不低于 0.80；
2. 困难 cell 的 BPI power 不低于 0.65；
3. 至少一个 primary cell 中，BPI 相对 Moment 的 paired power difference 不低于 0.10，且 one-sided 95% bootstrap 下界大于 0；
4. BPI 相对 DistHist 的 paired power difference 在两格的 one-sided 95% 下界均大于 -0.05；
5. 中等 cell 中 BPI-H1 power 至少比 BPI-H0 高 0.10；
6. BPI 的 extra-FP probability 不超过 0.15。

结果路由：

- 六项全部通过：允许“拓扑特异增量功效”主张；
- 绝对功效通过，但第 3–5 项部分失败：继续项目，论文仅主张拓扑表示可用与依赖校准，不主张表示优越；
- 两个 primary 的 BPI power 均低于 0.60：停止当前持久强度统计量，避免用真实数据偶然结果挽救方法。

---

## 16. E3：多变点与递归误报

### 16.1 场景（DMB）

主配置扩展为 \(M=384\)，其他窗口参数不变。每节点按 DMB-R1 规则生成独立乘子（`b0` 由根序列固定；不得从父节点截取乘子）。

| ID | 状态序列 | 变点数 | Outer trials |
|---|---|---:|---:|
| M2-ALT | circle→figure-eight→circle | 2 | 500 |
| M3-ALT | circle→figure-eight→circle→figure-eight | 3 | 500 |
| M3-MIX | circle→figure-eight→均值移位 Gaussian→circle | 3 | 500 |
| MSEP-32 | 两个拓扑变点间隔 32 个窗口 | 2 | 500 |
| MSEP-48 | 间隔 48 个窗口 | 2 | 500 |
| MSEP-64 | 间隔 64 个窗口 | 2 | 500 |

所有场景 \(\rho=0.6,\sigma=0.10\)，\(B=499\)。真实变点位于合法候选内部；靠近边界的情况另作描述性失败测试，不进入 Gate。

精确位置按派生窗口边界定义：M2-ALT 位于 128、256；M3-ALT 与 M3-MIX 位于 96、192、288。MSEP-\(d\) 使用 circle→figure-eight→circle，两个边界为 \(192-d/2\) 与 \(192+d/2\)；本协议中的 \(d\in\{32,48,64\}\) 均为偶数。代码内部转换为 0-based candidate 时统一减 1。

### 16.2 全局无变点递归

E1-CONFIRM 四类 null 的全部 8000 条序列同时运行完整递归（推断器为 DMB-R1，每节点使用独立乘子流）。保存：

- 是否产生任意 CP；
- 预测 CP 个数；
- 递归深度；
- 被检验节点数；
- 每节点 p 值、区段端点与 terminal reason；
- conditional/unconditional sequencewise FWER（主 Gate 同 G1：eligible roots 上 90% Wilson [0.03,0.07]）。

### 16.3 Gate G3-MULTIPLE

1. 四个 null 的 global-null sequencewise FWER 满足与 G1 相同的 90% Wilson [0.03,0.07] 等效标准；
2. M2-ALT 的 macro F1 不低于 0.75；
3. M2-ALT 的 exact-K rate 不低于 0.60；
4. M2-ALT 的 median normalized localization error 不高于 0.50；
5. M2-ALT 的 extra-FP probability 不高于 0.20；
6. MSEP 场景的结果随间隔增大呈非下降趋势，允许相邻格点 Monte Carlo 波动不超过 0.05。

G3 失败只删除“可靠多变点扩展”主张；若 G1 和 G2 仍通过，论文可收缩为单变点校准方法，并把递归作为探索性扩展。

---

## 17. E4：敏感性与消融

### 17.1 基准 cell

- Null：N-AR；
- Alternative：E2-H1 的 \((\rho,\sigma)=(0.6,0.10)\)；
- 每个非主水平：null 300 + alternative 300 outer trials；
- \(B=499\)；
- 每次只改变一个因素。

### 17.2 预注册变化

| 因素 | 主值 | 非主水平 |
|---|---:|---|
| 原始窗口 \(W\) | 64 | 48、96 |
| 网格 | 20×20 | 16×16、24×24 |
| 权重 \(\gamma\) | 1 | 0、2 |
| 带宽 multiplier | 1 | 0.5、2 |
| DMB multiplier bandwidth | \(b_0\) | \(b_-=\max(q_0,\lfloor0.75b_0\rfloor)\)、\(b_+=\max(q_0,\lceil1.25b_0\rceil)\)；仅敏感性描述，不选择主带宽，不挽救 Gate（规格 §20.3） |
| channel | H0+H1 | H0、H1 |
| 单变量嵌入维数 | 3 | 2、4 |

共 14 个非主水平、8400 个 outer trials。若 E0 触发 72–144 小时预算路由，则每个 cell 从 300 降为 150，并在论文中标注精度变化。E4 只在主 DMB 方法且 G1/G2 完成后运行。

### 17.3 稳健性判据

核心数值因素为网格、\(\gamma\)、带宽和 DMB multiplier bandwidth，共 8 个非主水平。若至少 6 个同时满足：

- null 拒绝率点估计位于 [0.025,0.075]；
- alternative power 相对主配置下降不超过 0.10；

则可写“结论对邻近数值配置总体稳健”。窗口和嵌入维数属于观测尺度选择，其变化用于解释适用边界，不纳入该句主张。

---

## 18. HASC 自然活动数据协议

### 18.1 数据身份与清单（v1.1：BLOCKED_DATA_IDENTITY）

**状态：`BLOCKED_DATA_IDENTITY / NO_ANALYSIS_ALLOWED`**（修订事件 `AM-20260907-001`/`AM-20260907-003`）。"250 条、50 Hz、多变量、8 名受试者"自 v1.1 起被重定义为**未验证的历史派生子集目标规格**，而非已确认的官方语料身份；通过 **D0-HASC 门**（8 项验收，截止 2026-09-13T23:59Z，早于 method freeze）验收后（`D0 PASS`）才允许将 HASC 转入正式确认（此时冻结 `HASC_RAW_v1`/`HASC_DERIVED_v1`）。`50_hasc_manifest.py` 在读取标签前核验：数据来源、许可、文件 SHA256、官方 public/private 字段、subject、序列长度、通道、缺失率和标签格式。公开 hc2011 RealWorld/SampleData 等语料与目标身份不符，禁止直接替代（如需使用按 E 类变更另立数据集身份与 Gate）。D0 FAIL 时 HASC 撤下主外部验证，由 TSSB 承担（claim C14 相应收缩）。D0 验收细则见 `docs/data_spec.md` 与数据 manifest。

### 18.2 划分

- 官方 public：模型开发和一次确认；
- 官方 private：最终密封评估；
- public 内按 subject 分组，使用 `REAL-SPLIT` 根种子对 subject hash 排序；前一半 subject 为 public-dev，后一半为 public-val；
- private 保留官方划分。若 public 与 private 共享 subject，论文明确称为序列级外部留出，不作跨受试者泛化声明。

### 18.3 主方法开发网格

只在 public-dev 使用标签：

| 参数 | 水平 |
|---|---|
| \(W\) | 50、100、150 raw samples |
| \(s\) | \(\lceil W/4\rceil\) |
| bandwidth multiplier | 0.75、1.0、1.5 |
| \(\gamma\) | 1 |
| grid | 20×20 |
| \(B\) | dev 499；val/private 999 |

共 9 个 BPI 配置。按 subject-macro Covering 选择最大者；差异小于 0.005 时依次选择 runtime 更短、bandwidth 更接近 1、\(W\) 更小者。public-val 只运行胜出配置一次。

### 18.4 Eligibility（v1.1：DMB）

单序列满足以下全部条件才产生 BPI 推断（规格 §20.4；原 `ell_candidate<=floor(M/8)` 条件删除）：

1. 清洗后至少 2 个有效通道；
2. \(T\ge W\)；
3. \(M\ge\max(8b_0,2m_{\min}+1)\)（\(b_0=\max(q_0,\operatorname{ceil\_cuberoot}(M))\)）；
4. `ell_candidate` 可定义且有限（PPW candidate guard）；
5. 至少一个拓扑 channel 非退化；
6. 根候选集合非空；
7. 无数值错误。

private 主文准入：eligible 序列比例至少 80%，全部受试者均有 eligible 序列，且每名受试者的 eligibility 不低于 50%（以 D0 验收后冻结的受试者集为准）。技术失败不得从分母删除，未闭合技术失败时 Gate 阻断。未达标时，HASC 降为适用性补充表。

### 18.5 Private seal

1. public-dev 和 public-val 完成；
2. 所有主方法与基线参数写入 `benchmark_frozen.yaml`；
3. Git clean commit 并打 tag `v1.1.0-benchmark-freeze`；
4. `53_hasc_private_predict.py` 只加载无标签特征和 frozen config；
5. 输出每个方法的 prediction JSON、eligibility manifest、runtime 和 SHA256；
6. 预测文件写入后设为只读；
7. 独立 `54_hasc_private_evaluate.py` 才能加载标签；
8. 揭示结果后禁止调整参数、选择 comparator 或重写 eligibility；
9. 只有输出无关的评价 bug 可在原预测上重算；改变预测的 bug 使整个 private run 失效，并要求公开记录原因和新版本。

### 18.6 指标与推断单位

- 主指标：Covering；
- 次指标：0.5 s、1 s、2 s tolerance 下的 Precision/Recall/F1，matched MAE，\(\widehat K\)，runtime；
- 平均方式：先序列，再 subject macro；
- 配对区间：以 subject 为 cluster 的 10,000 次 bootstrap；
- 主表示 comparator：DistHist-Scan；
- 主算法 comparator：public-dev 上最优的完整非拓扑算法，名称在 private 前冻结。

Gate G4-HASC：eligibility 准入通过；BPI−DistHist 的 Covering one-sided 95% cluster-bootstrap 下界大于 -0.05。对专用算法只报告实际差异，不设置必须胜出的门槛。

---

## 19. TSSB 构造型基准协议

### 19.1 数据定位

TSSB 由 UCR/UEA 分类片段拼接产生，边界是构造标签。它用于测试跨形状分割能力和公开算法可比性，不承担自然过程外部有效性。

### 19.2 版本与参数

- 固定官方仓库 commit、75 条序列清单及 62 个 family；若固定 commit 的实际数量不同，以 manifest 为准并在方法冻结前修订；
- 每条序列使用 benchmark-provided window size \(W_{TSSB}\)，主窗口 \(W=\max(W_{TSSB},32)\)；
- \(d=3\)，\(\delta\) 按 §3.2 的无标签 ACF 规则；
- \(s=\lceil W/4\rceil\)；
- BPI 的 grid、\(\gamma\)、带宽 multiplier 与 DMB 主带宽规则（\(b_0=\max(q_0,\operatorname{ceil\_cuberoot}(M))\)）沿用冻结配置；eligibility 按规格 §20.4；
- 不在 TSSB 标签上调参；
- \(B=999\)。

使用 benchmark window 属公开先验，论文必须披露其可能包含任务设计信息。

### 19.3 指标

- 主指标：官方方向的 Covering；
- 次指标：F1@\(W/2\)、matched MAE/\(T\)、exact-K、runtime；
- 同时报告全部序列的 baseline 结果与 BPI common-support 配对结果；
- 置信区间以 family 为 cluster，10,000 次 bootstrap；
- 官方论文数值只作 sanity reference，正式表格使用本地同版本运行结果。

### 19.4 准入

若 BPI eligible 序列比例和 eligible family 比例均达到 80%，TSSB 可进入主文真实数据表；任何一个低于 80%，则进入补充材料的 applicability/common-support 表。阈值按字面执行，不因差一条序列而改变。

---

## 20. 评价指标的精确定义

### 20.1 Covering

真实分段集合为 \(G\)，预测分段集合为 \(S\)，序列长度为 \(T\)：

\[
\operatorname{Covering}(G,S)=
\frac1T\sum_{g\in G}|g|\max_{s\in S}
\frac{|g\cap s|}{|g\cup s|}.
\]

调用顺序永久固定为 `Covering(true, pred)`。

### 20.2 Tolerance matching

构建二分图：真实点与预测点距离不超过容差时连边。先最大化匹配数，再在最大基数匹配中最小化总绝对距离。由匹配计算 TP，未匹配预测为 FP，未匹配真实点为 FN。

### 20.3 Monte Carlo 区间

- size 与 power：Wilson interval；
- 主 size 等效：90% Wilson CI 与预注册等效带比较；
- 方法间 paired binary difference：trial 级 paired bootstrap 10,000 次；
- HASC：subject-cluster bootstrap 10,000 次；
- TSSB：family-cluster bootstrap 10,000 次；
- 多算法次级显著性检验：paired Wilcoxon，Holm 校正；
- 主结论以效应量和置信区间为核心，p 值只作辅助。

### 20.4 Monte Carlo 样本量理由

在 \(p=0.05\) 附近，\(N=2000\) 的标准误约为

\[
\sqrt{0.05(1-0.05)/2000}=0.00487,
\]

95% 正态近似半宽约 0.0095。该精度足以用 90% Wilson CI检验 [0.03,0.07] 的实用等效带。功效主格采用 \(N=1000\)，当 power 为 0.8 时 95% 半宽约 0.025。secondary 格用于趋势和边界描绘，使用 300–500 次并显式报告较宽区间。

任何 outer MC 运行均不得使用“观察到稳定后提前停止”。只有 E0 计算预算规则可以在开跑前降低 secondary 的固定样本量。

---

## 21. Gate 总表与论文路由

| Gate | 必要条件 | 失败后的固定处理 |
|---|---|---|
| G0-PREFLIGHT | 环境、磁盘、hash、Git、seed 全通过 | 修复后重跑，不产生科学结果 |
| G0-CONTRACT | 75/75 测试通过（原 40 historical + DMB 35），0 skip | 禁止进入 MC |
| D0-APPLICABILITY | 300/300 无技术错误；eligibility/cp 覆盖/`b0`/候选一致性全达标（规格 §15.3） | 有 bug 修复重跑；无 bug 则 `DMB_R1_FAIL_APPLICABILITY` 终止 |
| D0-HASC | 8 项数据身份验收（截止 2026-09-13） | HASC 撤主外部验证，TSSB 承担 |
| G1-CALIBRATION-DMB | 四格 eligible-trial 90% Wilson CI ∈ [0.03,0.07]（动态分母；全 eligible 时才等价 \(73\le K\le121\)） | audit；无 bug 则 `FINAL_METHOD_FAILURE_DMB_R1` 停止推断主线 |
| G1-OVERLAP | iid 非重叠校准、高重叠 naive 失控、差异下界达标、DMB 四格 conditional size ∈ [0.025,0.075] | 删除重叠机制主张 |
| G2-TOPOLOGY | 绝对功效、Moment 增量、DistHist 非劣、H1 归因 | 分级收缩；两主格均低于 0.60 时停止当前统计量 |
| G3-MULTIPLE | null FWER、F1、exact-K、定位、FP 达标 | 收缩为单变点方法 |
| G4-EXTERNAL | 至少一个外部数据集 ≥80% 准入；HASC 表示非劣若其入主文 | 无外部数据集准入时停止专题投稿 |
| G5-REPRO | 密封产物、独立重放、canonical、图表链全部通过 | 禁止投稿 |

最终投稿条件：G0、G1-CALIBRATION、G2 的最低可用路线、G4 至少一个主外部数据集、G5 必须通过。专用基线领先不会自动终止投稿，但摘要和结论不得含 SOTA 或普遍优越性表述。

---

## 22. Trial ledger、canonical 和审计

### 22.1 每 trial 必填字段

```text
protocol_version, experiment_id, cell_id, batch_id, replicate_id,
trial_id, method_id, status, retry_count,
git_commit, dirty, source_tree_sha256, config_sha256, data_sha256,
seed_data, seed_subsample, seed_tie,
method_family, calibration_engine,
T, p, W, s, d, delta, M, q0, ell_ppw, ell_candidate, m_min,
dmb_bandwidth, dmb_bandwidth_rule, dmb_kernel, dmb_construction,
dmb_boundary, dmb_centering, dmb_bridge, dmb_shared_multiplier, dmb_rng,
n_candidates_root, n_multiplier_spans_root, ell_candidate_over_M8,
multiplier_seed_manifest_sha256,
eligible, ineligible_reason, B, alpha,
test_stat, p_value, reject, K_true, K_hat,
predicted_cp_raw, true_cp_raw,
covering, precision, recall, f1, matched_mae, normalized_mae,
extra_fp, exact_k,
runtime_preprocess, runtime_ph, runtime_surface, runtime_scan,
runtime_resample, runtime_total, peak_rss_mb,
warning_code, exception_type, exception_message,
created_at_utc
```

列表字段采用规范 JSON 字符串；浮点保存为十进制文本和 float64 两种形式。`trial_id` 由 experiment/cell/replicate/method/config hash 产生，必须唯一。

### 22.2 失败与重试

- 同一 trial 最多自动重试 2 次；
- 重试必须使用完全相同种子和配置；
- 成功重试保留前两次失败记录；
- 任一确认性 cell 最终缺失率超过 0.5% 时整格失败；
- 不得只补跑“结果异常”的 trial；
- 输出目录按 UTC 时间和 run UUID 新建，永不覆盖。

### 22.3 Canonical 结果

唯一论文数值来源为：

```text
artifacts/canonical/canonical_results.parquet
artifacts/canonical/canonical_results.csv
```

`70_build_canonical.py` 只读取状态为 sealed、hash 匹配、行数满足配置的 ledger。每条汇总结果必须携带 source run、cell、方法、分母、缺失数、统计公式和代码 commit。

所有表格和图形只读取 canonical 文件。论文草稿禁止手工输入实验数字。每张表、图都生成 `.csv` 数据副本、`.json` provenance 和 SHA256。

### 22.4 Audit 检查

`80_audit_release.py` 至少检查：

- 预期 cell 与实际 cell 完全一致；
- 每格 outer trial 数、方法数和 \(B\) 正确；
- trial_id 与种子唯一；
- 无 dirty confirm/private run；
- 无旧项目路径或旧结果 hash；
- config 结构和 source hash 一致；
- private 预测时间早于标签评价时间；
- private comparator 在揭示前已冻结；
- eligibility 分母与 manifest 对齐；
- canonical 可追溯到 ledger；
- 表图无硬编码数值；
- BibTeX key 全部存在；
- 主张矩阵与 Gate 状态一致。

---

## 23. 变更控制和污染处理

### 23.1 变更等级

| 等级 | 例子 | 重跑范围 |
|---|---|---|
| A：展示 | 字体、颜色、文字修正 | 无科学重跑 |
| B：评价 | metric 实现修正，预测不变 | 重新评价全部受影响预测 |
| C：数值实现 | 排序、抽样、cap、带宽代码改变且可能改特征 | 受影响 cell 全量重跑 |
| D：方法 | 统计量、DMB 带宽/核/中心化/资格、resampler、窗口、候选、递归改变 | 全部 CONFIRM 及下游失效 |
| E：数据 | 数据版本、清洗、split 改变 | 该数据集全部失效 |

### 23.2 污染矩阵

每次代码修改运行静态 impact mapper，输出每个实验状态：

```text
UNAFFECTED
AFFECTED_RERUN_REQUIRED
SUPERSEDED
HISTORICAL_INVALID
BLOCKED_BY_UPSTREAM
```

任何“只有少量 p 值改变”的情况仍按 C 或 D 处理；变化幅度不参与裁决。

### 23.3 冻结标签

| Tag | 时点 |
|---|---|
| `v0.1.0-contracts` | E0 全部契约通过（historical 基线记录） |
| `v1.0.0-method-freeze` | **SUPERSEDED**（stationary 路线；被 DMB 取代，不并列作证据入口） |
| `v1.1.0-method-freeze-dmb-r1` | **项目唯一正式 method-freeze**：75/75 契约 + D0-APPLICABILITY + E1-DEV-DMB PASS、CONFIRM 前（规格 §17） |
| `v1.1.0-benchmark-freeze` | HASC private 前（D0-HASC PASS 后） |
| `v2.0.0-results-freeze` | canonical、表图、Gate 固定 |
| `v2.1.0-submission` | 论文和复现包最终版 |

---

## 24. 计算总量

### 24.1 外层 Monte Carlo 计划数

| 模块 | Trials |
|---|---:|
| D0-APPLICABILITY-PILOT（复用，不重生成） | 300 |
| E1-DEV-DMB | 1,600 |
| E1-CONFIRM-DMB | 8,000 |
| E1-OVERLAP（DMB） | 4,000 |
| E1-DEPENDENCE（DMB） | 3,000 |
| E2-H1 | 4,800 |
| E2-H0 | 1,500 |
| E2-CONVENTIONAL | 1,800 |
| E3-MULTIPLE | 3,000 |
| E4-SENSITIVITY | 8,400 |
| **总计（CONFIRM 科学 MC）** | **36,400** |

注：D0-APPLICABILITY-PILOT 复用既有 300 条 L1 数据（N-AR/E2-H1-MID/C-MEAN），不新增 outer MC；因此正式科学 Monte Carlo 总 outer = 36,400 不变。

E1-CONFIRM-DMB 的 8000 条同时供 global-null recursion 使用，不重复生成数据。完整预算路由只可削减 secondary：E1-DEPENDENCE、E2 非 primary、E2-CONVENTIONAL、E3 的非 M2-ALT cell、E4。E1-CONFIRM-DMB、E1-OVERLAP 和 E2 两个 primary 保持不变（规格 §23：E1-CONFIRM、private seal、canonical 审计与论文数字反查不得为追回日期减量）。

### 24.2 缓存策略

- 同一 trial 内所有表示共享点云和持久图；
- 同一 trial 的 BPI-H0/H1/combined 共享表面；
- DMB 与 naive 共享观测特征与候选；
- DMB 乘子序列不缓存（每次由 seed 重建，保证 worker/resume 确定性）；
- 真实数据 PH 永久缓存；
- 合成数据不跨 trial 落盘缓存，避免数百万小文件；
- 每格前 20 个 trial 保存完整中间状态，用于审计和独立重算。

---

## 25. 日历与逐日交付

| 日期 | 工作与退出条件 |
|---|---|
| 9/03 | 协议 v1.0 完成；冻结研究问题和文献边界 |
| 9/04 | 新仓库、环境、配置 schema、preflight |
| 9/05–9/07 | 数据/窗口/PH/表面实现与测试（本阶段实际完成：骨架/种子/DGP/窗口/嵌入/预处理） |
| 9/08–9/10 | DMB-R1 实现、扫描、PPW 候选保护、递归、指标 |
| 9/11–9/13 | 75 项契约测试（40 historical + 35 DMB）与 E0 geometry/compute |
| 9/13 | D0-APPLICABILITY-PILOT（300，无 p 值）；D0-HASC 数据身份门截止（23:59） |
| 9/14 | E1-DEV-DMB；code-line audit |
| 9/15 | `v1.1.0-method-freeze-dmb-r1`；开始写方法章节 |
| 9/16–9/20 | E1-CONFIRM-DMB 两批（8000，B=999） |
| 9/21–9/22 | E1-OVERLAP、E1-DEPENDENCE（DMB）、global-null recursion、G1 审计 |
| 9/23–9/27 | E2 单变点功效与归因（仅 G1 PASS 后） |
| 9/28–9/30 | E3 多变点 |
| 10/01–10/03 | E4 敏感性（仅主方法 + G1/G2 完成后） |
| 10/04 | HASC（D0 PASS 后）/TSSB 特征 manifest 冻结；D0-HASC 门已于 9/13 关闭 |

> v1.1 说明：本日历行首**全部旧日期作废**，改为以规格 §23 状态机（D-00..D-07）的依赖顺序为唯一执行序列（见上表 9/03 起的 DMB 行）。任何 Gate 的进入以前置 PASS 为准；不设压缩补偿（规格 §23）。
| 10/05–10/08 | HASC public-dev 网格与所有 baseline 调参 |
| 10/09 | HASC public-val 一次确认；冻结 comparator |
| 10/10 | `v1.1.0-benchmark-freeze` |
| 10/11 | HASC private 无标签预测 |
| 10/12 | HASC private 评价与 Gate G4 |
| 10/13–10/14 | TSSB 与 common-support |
| 10/15–10/17 | canonical、表格、图、统计区间 |
| 10/18–10/21 | 中文论文完整初稿与补充材料 |
| 10/22–10/23 | 独立复现、数字反查、主张审计 |
| 10/24 | `v2.0.0-results-freeze` 和投稿包检查 |
| **10/25** | **提交期刊系统** |
| 10/26–10/31 | 只处理系统、格式、文件上传故障 |

任何科学 Gate 延误超过 3 天时，优先删除 secondary 敏感性和 S-CPD 复现；确认性校准、HASC seal、canonical 审计和论文数字核对不可压缩。

---

## 26. 每阶段交付包

### P0：协议包

- `PROTOCOL.md`；
- claim-evidence matrix；
- BibTeX；
- protocol SHA256；
- 决策日志。

### P1：方法冻结前包（v1.1：DMB-R1）

- clean source snapshot；
- requirements lock（含 PCG64DXSM/NumPy 版本可追溯）；
- 75/75 测试报告（40 historical + 35 DMB，0 skip）；
- E0 geometry 与 compute 报告；
- D0-APPLICABILITY-PILOT 输出；
- E1-DEV-DMB ledger；
- METHOD_FREEZE_REPORT（记录 DMB 全部字段与废止路线）；
- tag `v1.1.0-method-freeze-dmb-r1`/commit/hash。

### P2：合成确认包

- E1–E4 configs；
- 全部 trial ledgers；
- 每格 20 个完整审计 trial；
- Gate 判定 JSON 和 Markdown；
- size/power/定位/FP 的原始汇总；
- contamination matrix。

### P3：真实数据包

- 数据 manifest 与 SHA256，不含受许可限制的原始数据；
- public-dev/val subject 划分；
- frozen benchmark config；
- private 无标签预测及 seal；
- private 评价；
- TSSB commit 和 family manifest；
- eligibility/common-support 表。

### P4：投稿复现包

- `canonical_results.csv/parquet`；
- 每张表图的数据和脚本；
- paper source 与 PDF；
- supplement；
- README 一键 smoke reproduction；
- 完整环境与 provenance；
- release audit 结果；
- zip 与 `.sha256`。

---

## 27. 论文实验部分映射

| 论文内容 | 唯一实验来源 |
|---|---|
| 重叠破坏 naive 的机制图 | E1-OVERLAP |
| 主校准表 | E1-CONFIRM-DMB |
| DMB 带宽、候选保护量与 p-value 诊断 | E1-DEPENDENCE |
| 拓扑特异功效图 | E2-H1、E2-H0 |
| 传统变化边界 | E2-CONVENTIONAL |
| 多变点与误报 | E3 |
| 参数稳健性 | E4 |
| 自然活动案例 | HASC private |
| 构造型公开基准 | TSSB |
| 计算复杂度 | E0-COMPUTE + real runtime |
| 局限性 | eligibility、长依赖、短序列、DistHist/专用基线差异 |

计划主图不超过 6 张：方法流程；重叠率—size；四类 null 校准；拓扑备择 power；多变点定位；HASC/TSSB 结果与 coverage。计划主表不超过 5 张：参数与 DGP；E1 校准；E2 功效；真实数据；消融/运行时间。其余进入补充材料。

---

## 28. 从现在开始的执行清单

以下步骤严格顺序执行：

1. 将本协议（v1.1）保存为新仓库 `PROTOCOL.md`；
2. 写入协议 SHA256，并维护 `CHANGELOG_PROTOCOL.md`；
3. 新建干净 Python 3.12.10 环境；
4. 初始化 Git，首次 commit 只含协议、文献、环境声明和空目录骨架；
5. 实现 preflight、seed、ledger、provenance；
6. 完成生成器、窗口、索引和 PH；
7. 完成表面、扫描、PPW 候选保护量与 DMB-R1（乘子/桥接/资格/seed）；
8. 完成递归、指标和 75 项测试（40 historical + 35 DMB，0 skip）；
9. 运行 E0 geometry/compute；
10. 执行 D0-APPLICABILITY-PILOT（300，不计算 p 值）；
11. 执行 E1-DEV-DMB；
12. 打 tag `v1.1.0-method-freeze-dmb-r1`（唯一正式 method-freeze）；
13. 此后才允许生成 CONFIRM 数据（E1-CONFIRM-DMB）；
14. 按 D-05→D-07（G1→overlap/dependence/recursion→E2→E3→E4）顺序运行，逐 Gate 审计；
15. D0-HASC 门 9/13 已关闭：PASS 后 real loader 与 baseline；FAIL 则 TSSB 承担主外部验证；
16. public-dev→public-val→benchmark freeze→private predict→private evaluate；
17. 构建 canonical；
18. 由 canonical 自动生成所有表图；
19. 执行 release audit 和空目录 smoke reproduction；
20. 主张矩阵按 Gate 结果降级或升级；
21. 2026-10-25 提交。

---

## 29. 最终冻结决定

本协议固定以下战略选择：

- 拓扑核心保留为 \(H_0/H_1\) 持久表面及局部强度差；
- 主推断器采用**高斯 Bartlett 依赖乘子 bootstrap（DMB-R1）**：主带宽 \(b_0=\max(q_0,\operatorname{ceil\_cuberoot}(M))\)，外部 iid padding、全段均值残差、Brownian-bridge 校正、共同标量乘子、per-node/per-replicate PCG64DXSM seed；PPW 仅形成候选保护量 `ell_candidate`，不再决定带宽或资格；资格由 \(M\ge\max(8b_0,2m_{\min}+1)\) 决定；
- 第二次方法级调整**禁止**：DMB-R1 科学失败（无实现 bug）时停止可靠推断主线；
- naive permutation 仅承担机制对照；
- 主要科学成功由校准、拓扑特异功效和至少一个外部数据集准入共同定义；
- 真实数据专用算法领先可以被如实接受；
- TSSB 的构造属性和 coverage 边界必须进入正文；
- 旧项目代码和数值不进入新证据链；
- 任何改变科学输出的修复都通过污染矩阵决定全量重跑范围；
- 提交前最后权威来源只有 sealed ledger、canonical 文件和与其一致的论文。

该设计把实验分成三条互相独立的证据链：**推断是否校准、拓扑表示何时有信息、完整算法在真实序列上能否使用**。三条链分别回答统计正确性、科学价值和应用边界，避免单一成功数字替代整篇论文的可信度。
