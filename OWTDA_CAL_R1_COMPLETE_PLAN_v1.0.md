# OW-TDA-CAL R1 完整研究与实验计划 v1.0

> 项目名称：重叠滑动窗口下拓扑扫描检验的交换性失效与校准边界  
> 英文名称：Exchangeability Failure and Calibration Boundaries of Topological Scans with Overlapping Windows  
> 项目标识：`OWTDA-CAL-R1`  
> 计划日期：2026-09-09  
> 文档状态：方案定稿，待本地实现核验与共同冻结；任何正式 Monte Carlo 开始前必须转为 `FROZEN`

---

## 0. 总裁定

本项目结束原 DMB-R1 的"通用可靠校准方法"叙事，建立全新的证据代际。新论文研究以下问题：

> 单条时间序列经重叠滑动窗口、点云构造、持续同调与有限维 persistence-intensity 映射后，普通置换所要求的交换性在哪些条件下失效或不再有保证；naive permutation 与冻结 DMB 规则的有限样本校准误差怎样随窗口重叠率、原序列依赖、数据预算及拓扑表征而变化。

论文的生存点固定为四项：

1. 交换性失效的精确反例；
2. 一个可解析的重叠窗口均值例中，真实长期协方差与置换边际协方差的理论错配；
3. 使用全新种子的 fixed-\(M\)/fixed-\(T\) 校准图谱；
4. 可从空环境重建的完整证据链。

任一校准器的数值表现只改变论文结论，不决定实验是否合法。代码、身份、数据、随机种子、账本或统计量—理论对应关系出现错误时，实验才进入阻断状态。

### 0.1 本轮明确排除

- 不研究递归切分和多变点 FWER；
- 不把旧 DMB-R1 ledger 合并进正式估计；
- 不恢复"persistence intensity 普遍优于 scalar"的主张；
- 不把 HASC 或 TSSB 作为本轮主要真实数据证据；
- 不在正式结果出现后调整 DMB 带宽、核、候选区间、等价带或 MC 数；
- 不宣称首次发现滑动窗口产生依赖、首次研究依赖 TDA、首次使用 block/bootstrap 进行 TDA 推断；
- 不把审计流程本身包装成科学创新。

---

## 1. 学术定位与可防守创新

### 1.1 与近邻工作的边界

1. Han、Kim 与 Kim 的 weighted persistence intensity 两样本检验以两组独立同分布 persistence diagrams 为前提；本项目研究单序列重叠窗口派生 diagrams 中交换性可能失效且不能直接沿用 IID 保证的情形。  
   <https://arxiv.org/html/2607.20893v1>
2. TADA 已研究依赖复杂序列中的拓扑异常检测；本项目聚焦最大扫描检验的 Type-I、p 值左尾与有限样本校准边界。  
   <https://jmlr.org/papers/v25/24-0853.html>
3. PL-CUSUM 已给出滑窗依赖继承界并使用 overlap-aware moving-block bootstrap；本项目限定为无需独立 Phase-I 校准池的离线单序列扫描。  
   <https://arxiv.org/html/2607.08635v2>
4. Romano 与 Tirlea 已证明普通置换在非交换时间序列中可能失效；本项目在窗口均值解析例中给出具体协方差错配，并为固定 persistence-intensity 管线提供有限样本图谱。  
   <https://arxiv.org/abs/2009.03170>
5. dependent multiplier bootstrap 已有一般经验过程理论；其渐近有效性不保证 \(M=192\) 等有限样本配置逐格接近 0.05。  
   <https://arxiv.org/abs/1306.3930>

### 1.3 允许使用的创新表述

在最终文献更新检索未发现完全同构工作时，论文可采用以下范围受限的表述：

> 本研究针对无需独立 Phase-I 样本的离线单序列拓扑最大扫描，系统考察重叠率、原序列依赖和采集预算共同作用下的有限样本校准边界。

只有 C2 或 C3 获支持时，结果段才可进一步写普通置换出现预注册幅度的反保守/失真；只有 C5 获支持时，才可写冻结 DMB-R1 在 IID 非重叠端存在实质保守性。两项不得互相替代。

---

## 2. 旧证据隔离与新证据代际

### 2.1 DMB-R1 终止记录

原证据线固定标记：

```text
DMB-R1-TERMINATED-20260909
```

旧材料只允许进入：

```text
external_prior_evidence/DMB_R1/
├── PRIOR_EVIDENCE_SUMMARY.md
├── archive_manifest.json
└── SHA256SUMS.txt
```

`PRIOR_EVIDENCE_SUMMARY.md` 必须披露：

- s16 下 naive Type-I 约为 0.74–0.83；
- s64 下 naive 约为 0.03–0.07；
- s16 下 DMB 约为 0.045–0.075；
- s64 下 DMB 约为 0.010–0.025；
- B5 code-line audit 未发现实现缺陷；
- 上述数字均属于假设形成和历史开发证据。

### 2.2 新证据等级

| 等级 | 内容 | 可进入论文主估计 |
|---|---|---:|
| L0 | 单测、攻击测试、解析反例、blind smoke | 否 |
| L1 | DMB-R1 历史结果及其他已查看结果 | 否 |
| L2 | 新协议冻结后的正式合成实验 | 是 |
| L3 | 数据身份冻结后的 PAMAP2 分析 | 是，限说明性结论 |
| L4 | 独立环境重建和外部复核 | 增强可信度 |

新论文表格和图片只读取 L2/L3 sealed ledger。L1 可在引言或补充材料中说明研究动机，不能与 L2 拼接计算。

### 2.3 项目级与运行级状态机

所有机器对象的 `phase` 只允许以下 ASCII 枚举：

```text
SMOKE_NULL
SMOKE_ALT
NULL
ALT
REAL_TASK_BUILD
REAL_PREDICTION
REAL_EVALUATION
ANALYSIS
```

正文中的"H0/H1"分别是科学含义，机器身份必须写 `NULL/ALT`；smoke 不得复用 formal phase 名。

本轮没有方法筛选，因此取消容易产生混代的 DEV→CONFIRM 选择链。项目级状态固定为：

```text
DRAFT
→ THEORY_ALIGNED
→ SMOKE_VALIDATED
→ PROTOCOL_FROZEN
→ CORE_EVIDENCE_SEALED
→ ANALYSIS_FROZEN
→ RELEASED
```

H0、H1 和真实数据各自拥有独立运行状态，禁止用一个 `CONFIRM_SEALED` 代表三条尚未同时闭合的证据线：

```text
NULL_INDEX_FROZEN → NULL_ADMITTED → NULL_RUNNING → NULL_SEALED
ALT_INDEX_FROZEN  → ALT_ADMITTED  → ALT_RUNNING  → ALT_SEALED
REAL_DATA_STAGED → REAL_DATA_FROZEN → REAL_TASK_BUILD_ADMITTED
                 → REAL_TASKS_FROZEN → REAL_PREDICTION_ADMITTED
                  → REAL_PREDICTION_RUNNING → REAL_PREDICTION_SEALED
                  → REAL_LABELS_UNSEALED → REAL_EVALUATION_ADMITTED
                  → REAL_EVALUATION_RUNNING → REAL_EVALUATION_SEALED
```

REAL 数据在身份、task 或 prediction-isolation Gate 未通过时，可分别从 `REAL_DATA_STAGED`、`REAL_DATA_FROZEN` 或 `REAL_TASKS_FROZEN` 进入专用终态 `REAL_OMITTED_BY_DATA_GATE`；该状态不阻断合成证据。进入终态必须记录唯一原因代码；数据身份失败不得降格为某个 subject 的不准入。定义

```text
CORE_EVIDENCE_SEALED := NULL_SEALED AND ALT_SEALED
```

真实数据省略或延期必须进入独立的 append-only `REAL_DISPOSITION` chain，不能只写一个自由文本状态。genesis 固定为 `H("real_disposition_genesis",project_id=...,protocol_id=...,freeze_id=...,evidence_generation_id=...)`。每个 event 删除自身 hash 后顶层恰含：

```text
schema_version, event_type="REAL_DISPOSITION",
project_id, protocol_id, freeze_id, evidence_generation_id,
disposition_status, disposition_stage,
reason_code, reason_object_hash,
task_index_seal_hash, truth_unsealed,
prev_real_disposition_event_hash
```

其中 `disposition_status` 只允许 `REAL_OMITTED_BY_DATA_GATE` 或 `REAL_DEFERRED`；`disposition_stage` 只允许 `REAL_DATA_STAGED,REAL_DATA_FROZEN,REAL_TASKS_FROZEN,REAL_PREDICTION_ADMISSION,REAL_PREDICTION_RUNNING`。`REAL_OMITTED_BY_DATA_GATE` 在 task index 形成前允许 `task_index_seal_hash=null`，形成后必须绑定唯一 current task-index seal；`REAL_DEFERRED` 必须绑定该 seal，且 `truth_unsealed=false`。`reason_code` 使用冻结枚举，`reason_object_hash` 必须解析到 strict 机器对象。`disposition_hash=SHA256(canonical_json(event_without_hash).encode("utf-8")+b"\n")`，它同时是该 event hash；writer 在项目级独占锁内 CAS 验证 `prev_real_disposition_event_hash` 等于当前 tip 后追加并 fsync。断链、分叉、循环、同一 tip 多 child 或字段组合不合法均阻断。分析 manifest 只能引用 reducer 得到的 current chain tip，且对象内 `disposition_hash` 必须与被引用 event bytes 重算值相同。

每个 phase 内的具体 `run_instance_id` 另走

```text
INDEX_FROZEN → ADMITTED → RUNNING → RUN_SEALED
```

初次 full run 和局部组件重跑都必须从新的 `INDEX_FROZEN` 开始。`RUN_SEALED` 只证明特定 run 的三类 expected indexes、shards 与字节内容完整，产生后不可取消或改写。`INVALIDATED/SUPERSEDED` 作用于 logical slot 的 active binding/validity registry；仍被其他未受影响 logical slots 引用的旧 run 保持可引用，引用数归零后才能另记为 archival-superseded。

phase 的 `*_SEALED` 是版本化事件 `{active_component_manifest_hash, active_data_index_hash, active_feature_index_hash, active_evaluation_index_hash, phase_seal_hash}`，每次新 active revision 都产生新事件；旧事件语义不得随"当前 manifest"漂移。`REAL_LABELS_UNSEALED` 后，同一 task/evidence generation 禁止新建或 supersede prediction。若此后发现 prediction 缺陷，进入 `REAL_INVALIDATED_POST_UNSEAL` 并省略真实结果；只有使用从未接触 truth 的全新隔离 executor 与新 evidence/task generation 才可重新开始。

每条状态变更 append-only。通用终止状态为 `ABORTED`、`INVALIDATED` 或 `SUPERSEDED`，且必须引用原因对象和受影响身份范围。`DEADLINE_NO_GO` 只属于日程处置字段 `schedule_disposition`，不充当科学项目或 run 状态。blind smoke 只检查运行时间、字段和错误，不输出拒绝率汇总，也不进入参数选择。

---

## 3. 研究对象、符号与主统计量

### 3.1 原始序列与滑动窗口

令严格平稳原序列为

\[
\{X_t:t\in\mathbb Z\},\qquad X_t\in\mathbb R^d.
\]

窗口长度为 \(W\)，步长为 \(s\)，第 \(i\) 个窗口为

\[
I_i=\{(i-1)s+1,\ldots,(i-1)s+W\},
\]

窗口数为

\[
M=\left\lfloor\frac{T-W}{s}\right\rfloor+1.
\]

重叠率和 IID 原序列下的几何依赖阶分别定义为

\[
r_{\mathrm{ov}}=1-\frac{s}{W},
\qquad
m_{\mathrm{ov}}=\left\lceil\frac Ws\right\rceil-1.
\]

### 3.2 拓扑特征

完整窗口局部映射写为

\[
Y_i=
\Phi\!\left[
\operatorname{PH}\!\left(\mathcal E(X_{I_i})\right)
\right]\in\mathbb R^p.
\]

- \(\mathcal E\)：二维数据直接使用窗口内观测行；单变量数据在每个窗口内部进行延迟嵌入；
- \(\operatorname{PH}\)：Vietoris–Rips 持续同调；
- \(\Phi\)：冻结的有限维 BPI/persistence-intensity 映射；
- 所有 cap、网格、核带宽、权重、降采样和随机数均为窗口局部规则。

禁止使用依赖整条序列的自适应 cap 或全序列标准化。该类操作类似根据全班答案重新划定每道题的分值，会把原本相隔很远的窗口人为连接起来，并破坏理论中的局部依赖边界。

### 3.3 主扫描统计量

候选集合固定为

\[
\mathcal K_M=
\left\{k:
\lceil0.15M\rceil
\le k\le
M-\lceil0.15M\rceil
\right\}.
\]

中心化 CUSUM 过程为

\[
U_M(k)=
\frac1{\sqrt M}
\left[
\sum_{i=1}^kY_i
-\frac{k}{M}\sum_{i=1}^MY_i
\right].
\]

主统计量为加权均值差的平方范数：

\[
T_M=
\max_{k\in\mathcal K_M}
\frac{\|U_M(k)\|_2^2}
{(k/M)(1-k/M)}.
\]

等价地，令 \(n_L=k,n_R=M-k\)，则候选 \(k\) 的统计量为

\[
T_M(k)=
\frac{n_Ln_R}{M}
\|\bar Y_{1:k}-\bar Y_{k+1:M}\|_2^2.
\]

BPI 的 cell-area 权重和 MOMENTS 的 Frobenius 权重直接编码在特征向量 \(Y_i\) 中，因此扫描器统一使用普通欧氏范数。候选集、exclusion、tie、退化处理和最大值位置规则对所有校准器完全相同。

候选 \(k\) 使用 1-based "左侧窗口数"语义，表示窗口 \(k\) 与 \(k+1\) 之间。若多个候选满足

\[
T_M(k)\ge T_M-64\epsilon_{64}\max(1,T_M),
\]

其中 \(\epsilon_{64}=2^{-52}\)。先找最长连续 plateau，并列时取最左 plateau，再取该段的 lower median 作为 \(\widehat k\)。该规则只选择位置；resampling exceed 仍使用 float64 精确 \(T_b^*\ge T_{obs}\)。

本轮只研究第一次全局扫描。递归检测会引入"第一次切分改变第二次样本空间"的选择效应，需要另一套 FWER 理论。

### 3.4 统计量—理论对齐 Gate

正式 MC 前必须满足：

1. 代码统计量可逐项写成上述有限维特征均值 CUSUM；
2. 两份独立实现对随机小样本的绝对误差 \(\le10^{-12}\)；
3. 候选端点、最大值 plateau、中位索引和 raw-time 映射具有手工反例测试；
4. permutation/multiplier 只改变校准过程，不改变 observed statistic；
5. 若代码实际属于退化核 U-statistic，正式 MC 暂停，Brownian-bridge 定理不得套用。

---

## 4. 理论工作包

### T1：窗口特征依赖继承

若原序列的 \(\beta\)-mixing 系数为 \(\beta_X(h)\)，证明或引用并适配：

\[
\widetilde\beta_X(\ell)=
\begin{cases}
1,&\ell\le0,\\
\beta_X(\ell),&\ell\ge1,
\end{cases}
\qquad
\beta_Y(h)\le\widetilde\beta_X(hs-W+1).
\]

等价地，重叠区 \(hs<W\) 只使用平凡上界 1；当 \(hs\ge W\) 时使用 \(\beta_X(hs-W+1)\)。不能把重叠区错误替换成一般并非最大值的 \(\beta_X(0)\)。当 \(X_t\) 为 IID 且 \(\Phi\circ\operatorname{PH}\circ\mathcal E\) 是第 5 节冻结的窗口局部固定映射时，\(Y_i\) 至多为 \(m_{\mathrm{ov}}\)-dependent。该结果作为理论起点，不列为首创贡献。

### T2：交换性失效的精确反例

令 \(1\le s<W\)、\(\sigma^2>0\)，并令

\[
X_t\overset{iid}{\sim}N(0,\sigma^2),
\qquad
Z_i=\frac1W\sum_{t\in I_i}X_t.
\]

则

\[
\operatorname{Cov}(Z_i,Z_{i+h})
=\frac{\sigma^2}{W^2}(W-hs)_+.
\]

当 \(s<W\) 且 \(M\ge3\) 时，严格有

\[
\operatorname{Cov}(Z_1,Z_2)
\ne
\operatorname{Cov}(Z_1,Z_3).
\]

高斯向量若可交换，其不同坐标对的协方差必须相同，因此置换 \(Z_2,Z_3\) 会改变联合分布。该反例精确说明：原始样本 IID 和窗口边际同分布均不足以推出窗口统计量可交换。

### T3：窗口均值的有限样本方差放大

定义

\[
A_{\mathrm{mean},M}
=1+2\sum_{h=1}^{\min(m_{\mathrm{ov}},M-1)}
\left(1-\frac hM\right)
\left(1-\frac{hs}{W}\right).
\]

当 \(W=qs\) 且 \(M\ge q\) 时，证明

\[
A_{\mathrm{mean},M}
=q-\frac{q^2-1}{3M}.
\]

所以 \(W=64,s=16,M=192\) 时：

\[
A_{\mathrm{mean},M}
=4-\frac{15}{576}
\approx3.974,
\qquad
M_{\mathrm{eff}}\approx48.3.
\]

192 个窗口在窗口均值信息量上接近 48 个独立窗口。这一数值是解析参照，不能用于解释 BPI Type-I 膨胀的精确幅度。

同一例在 \(M\to\infty\) 且 \(W=qs,q>1\) 时满足

\[
\Gamma_h=\Gamma_0(1-h/q),\quad h=1,\ldots,q-1,
\qquad
\Omega=\Gamma_0+2\sum_{h=1}^{q-1}\Gamma_h=q\Gamma_0.
\]

因此该标量窗口均值构造中真实长期方差与随机排列保留的边际方差严格不同。该结论是 C4 的直接支持范围；没有单独证据时不得写成固定 BPI 的协方差矩阵也必然满足相同倍数关系。

### T4：真实扫描与 naive permutation 的极限错配

渐近制度固定 \(W,s,p\)，令 \(M\to\infty\) 且 \(T=W+s(M-1)\)。定义

\[
\mu_\Phi=E(Y_0),
\qquad
\Gamma_h=\operatorname{Cov}(Y_0,Y_h),
\]

\[
\mathbb U_M(t)=\frac1{\sqrt M}
\left[
\sum_{i=1}^{\lfloor Mt\rfloor}Y_i
-\frac{\lfloor Mt\rfloor}{M}\sum_{i=1}^MY_i
\right],
\qquad 0\le t\le1.
\]

令 \(\pi\) 是独立于数据的均匀随机排列，并定义

\[
\mathbb U_M^\pi(t)=\frac1{\sqrt M}
\left[
\sum_{i=1}^{\lfloor Mt\rfloor}Y_{\pi(i)}
-\frac{\lfloor Mt\rfloor}{M}\sum_{i=1}^MY_i
\right].
\]

假定 \(Y_i\) 严格平稳，存在 \(\delta>0\) 使

\[
E\|Y_0\|^{2+\delta}<\infty,
\qquad
\sum_{h=1}^{\infty}
\beta_Y(h)^{\delta/(2+\delta)}<\infty
\]

及所引用函数型中心极限定理要求的其余可核验条件。随后证明：

\[
\mathbb U_M(\cdot)
\Rightarrow
\Omega_\Phi^{1/2}B_p^0(\cdot),
\]

其中

\[
\Omega_\Phi=
\Gamma_0+
\sum_{h\ge1}(\Gamma_h+\Gamma_h^\top).
\]

均匀随机排列的条件极限则由边际协方差控制：

\[
\mathbb U_M^\pi(\cdot)
\Rightarrow_{\mathbb P}
\Gamma_0^{1/2}B_p^0(\cdot).
\]

连续映射进一步给出

\[
T_M\Rightarrow
\sup_{t\in[0.15,0.85]}
\frac{\|\Omega_\Phi^{1/2}B_p^0(t)\|_2^2}{t(1-t)},
\]

而排列参考极限将 \(\Omega_\Phi\) 换为 \(\Gamma_0\)。真实分布包含窗口间的"合唱共振"，naive permutation 只保留每个窗口单独的音量。\(\Omega_\Phi\ne\Gamma_0\) 足以证明向量高斯过程的协方差错配；欧氏范数扫描的极限律由协方差矩阵的特征值决定。若两者的特征值多重集不同，则归一化平方范数过程的分布不同；最大值分布的严格差异仍需单独证明，或通过两种极限临界值律直接比较。全文不得把单纯的矩阵不等写成 \(T_M\) 极限分布必然不同的充分条件。

### T5：有限样本依赖放大诊断

定义有限样本长期协方差

\[
\Omega_{\Phi,M}
=\Gamma_0+
\sum_{h=1}^{M-1}\left(1-\frac hM\right)
(\Gamma_h+\Gamma_h^\top).
\]

当

\[
\operatorname{tr}(\Gamma_0)=E\|Y_0-\mu_\Phi\|_2^2>0
\]

时，主诊断量采用同一有限样本对象的 trace 比值：

\[
A^{\mathrm{tr}}_{\Phi,M}
=
\frac{
E\left\|M^{-1/2}
\sum_{i=1}^M(Y_i-\mu_\Phi)\right\|^2
}{E\|Y_i-\mu_\Phi\|^2}
=\frac{\operatorname{tr}(\Omega_{\Phi,M})}
{\operatorname{tr}(\Gamma_0)}.
\]

总体分母为 0 时记为 `UNDEFINED_DEGENERATE`。本轮不估计高维白化特征谱，避免在 \(p=800\)、\(R=2500\) 时引入 ridge 和 HAC 截断选择。`trace` 比值类似一个总信息重复率；最大扫描仍可能受少数方向支配，因此它只作机制诊断，不能单独决定 Type-I 的方向。

### T6：理论交付标准

主文至少包括 T2、T3、T4 和 T5 定义；T1 的完整证明可放补充材料。T4 必须由一名未参与实现的人逐行审读。若 2026-09-18 前无法闭合 T4，论文降级为"精确反例 + 解析 VIF + 系统有限样本图谱"，并删除渐近定理创新表述。正式 MC 可在统计量—理论对齐已经完成后继续。

---

## 5. 特征合同

旧实现会从整条派生序列联合估计距离尺度、核带宽、网格上界和通道标准化量。该做法会把相隔很远的窗口通过共享估计量连接起来，T1 的窗口局部依赖结论随即失去直接适用性。本轮重新定义固定参数版本，旧实现只保留为 L1 历史证据。

### 5.1 点云与持续同调

稳定标识：

```text
BPI_FIXED20_H01_SIGMA005_GAMMA1_V1
```

点云规则：

- 二维和三维序列直接把窗口内观测行作为点云；
- 单变量序列在每个窗口内部构造
  \[
  (x_t,x_{t+3},x_{t+6}),\qquad t=1,\ldots,W-6;
  \]
- 点云先拒绝 NaN/Inf、把 `-0.0` 规范为 `+0.0`，随后按 float64 字典序 `lexsort` 并按规范化位模式去重；
- `point_limit=128`；本轮最大窗口只有 100 点，若去重后仍超过 128 则视为配置错误，禁止随机降采样；
- 距离使用欧氏距离，Vietoris–Rips 复形，系数域 \(\mathbb F_2\)，计算 \(H_0,H_1\)，`maxdim=1`，不设数据驱动 `thresh`；
- 删除所有 infinite-death 类；少于 2 个唯一点时两个通道都返回固定零向量。

### 5.2 固定 persistence-intensity 映射

对有限 diagram 点 \((b,d)\)，令场景固定坐标尺度为 \(c\)，并定义

\[
u=\min(b/c,1),\qquad
v=\min((d-b)/c,1).
\]

尺度预先固定：

| 场景 | \(c\) |
|---|---:|
| N-AR 单变量延迟点云 | 6 |
| circle/figure-eight 合成点云 | 2.5 |
| PAMAP2 chest acceleration，单位 g | 6 g |

这里的 \(c\) 是 birth/lifetime 坐标 winsor cap；归一化网格上界固定为 1，与 VR 计算阈值分开。网格为 \(20\times20\)，步长 \(\Delta=1/20\)，中心

\[
g_r=(r+1/2)\Delta,\qquad r=0,\ldots,19.
\]

核宽 \(\sigma=0.05\)，权重 \(w(v)=v\)。每个同调通道的第 \((r,l)\) 个坐标为

\[
Z_{r,l}=\sqrt{\Delta^2}
\sum_{(u,v)}
v\frac{1}{2\pi\sigma^2}
\exp\!\left[-\frac{(g_r-u)^2+(g_l-v)^2}{2\sigma^2}\right].
\]

按 `H0` 后 `H1` 的顺序拼接两个 400 维向量，再除以 \(\sqrt2\)，得到固定 800 维 BPI。空通道保留为 400 维零向量。全流程不估计序列级 cap、距离尺度、核宽、网格、energy scale 或通道删除规则。

### 5.3 控制表征

稳定标识：

```text
MOMENTS_MEAN_COV_FROB_V1
```

对与 BPI 完全相同的窗口点云 \(P_1,\ldots,P_n\in\mathbb R^d\)，先除以固定坐标尺度 \(a\)：N-AR、circle 和 figure-eight 使用 \(a=1\)，PAMAP2 使用 \(a=6\text{ g}\)。令

\[
\bar P=\frac1n\sum_{j=1}^nP_j,
\qquad
S=\frac1n\sum_{j=1}^n(P_j-\bar P)(P_j-\bar P)^\top.
\]

协方差分母固定为 \(n\)，无 bias correction。特征依次写入 \(d\) 个均值、\(d\) 个对角协方差及按字典序排列的 \(\sqrt2S_{ab}\;(a<b)\)。所以二维产生 5 维，三维产生 9 维，欧氏距离恰对应

\[
\|\Delta\bar P\|_2^2+\|\Delta S\|_F^2.
\]

常数点云返回实际均值和零协方差。BPI 与 MOMENTS 是本轮仅有的两种表征，覆盖全部 H0、H1 和真实数据范围；不再运行 Betti curve 或 distance histogram。

---

## 6. 校准方法

### M0：naive permutation

稳定标识：

```text
M0_NAIVE_PERM_B999_V1
```

对每个 \(r=1,\ldots,999\) 独立生成 \(\{1,\ldots,M\}\) 的均匀随机排列 \(\pi_r\)，定义

\[
U_{M,r}^{\pi}(k)=\frac1{\sqrt M}
\left[
\sum_{i=1}^kY_{\pi_r(i)}
-\frac{k}{M}\sum_{i=1}^MY_{\pi_r(i)}
\right],
\]

并用第 3.3 节同一候选集和平方范数得到 \(T_{M,r}^{\pi}\)。

### M1：冻结 DMB-R1 规则

冻结规则为

\[
q_0=\lfloor W/s\rfloor+1,
\qquad
b_{R1}=\max\{q_0,\lceil M^{1/3}\rceil\}.
\]

\(\lceil M^{1/3}\rceil\) 用最小满足 \(j^3\ge M\) 的正整数 \(j\) 实现，禁止浮点立方根。

稳定标识固定为：

```text
M1_DMB_R1_TRI_EXTIID_B999_V1
```

令 \(\bar Y=M^{-1}\sum_iY_i\)、\(Z_i=Y_i-\bar Y\)。对每个 multiplier replicate 生成

\[
e_1,\ldots,e_{M+b-1}\overset{iid}{\sim}N(0,1),
\qquad
\xi_i=b^{-1/2}\sum_{j=0}^{b-1}e_{i+j}.
\]

每个 \(\xi_i\) 恰使用 \(b\) 个新息，不做 circular wrap、不截短边缘、也不对 \(\xi\) 再中心化。其协方差为

\[
\operatorname{Cov}(\xi_i,\xi_{i+h})
=\left(1-\frac{|h|}{b}\right)_+.
\]

DMB bridge 定义为

\[
U^*_{M,r}(k)=\frac1{\sqrt M}
\left[
\sum_{i=1}^k\xi_{r,i}Z_i
-\frac{k}{M}\sum_{i=1}^M\xi_{r,i}Z_i
\right],
\]

并用同一候选集和平方范数得到 \(T^*_{M,r}\)。这一定义逐项冻结；旧代码若与公式不同，G1 直接失败。

### 6.1 共同内层合同

M0、M1 与两种表征覆盖全部 28 个主 H0 格、8 个 H1 格和所有准入真实任务。每个方法固定：

\[
B=999,
\qquad
p=\frac{1+\sum_{b=1}^{999}
1(T_b^*\ge T_{obs})}{1000}.
\]

所以：

- p 值网格为 0.001；
- \(p\le0.05\iff\mathrm{exceed}\le49\)；
- tie 使用 \(\ge\)；
- p 值不可能为 0；
- 外层 MC 估计对象包含内层 \(B=999\) 的实际软件随机性。

同一数据单元内，BPI 与 MOMENTS 共享 M0 的排列索引；M1 共享同一标准正态新息张量。这样表征比较不会混入可避免的内层随机化差异。

---

## 7. Null 数据生成过程

两类 DGP 都使用 \(\rho\in\{0,0.8\}\)。每个 replicate 在两个 \(\rho\) 水平间共享基础创新，但保留不同的 `data_unit_id`。

所有 synthetic families 的最大正式前缀固定为 `T_master=12288`。stationary latent 初值位于 (t=-1000)，完整 latent innovation array 对应 (t=-999,ldots,12288)，所以 `L_latent=13288`，数组下标 `0..13287` 与该时间区间一一对应；`innovation_hash` 永远哈希完整 float64 `[13288]`。N-CIRCLE/H1 的 observation-noise master array 只对应正式观测 (t=1,ldots,12288)，故 `L_noise=12288`、shape `[12288,2]`。每个 physical cell 读取前 (T) 个正式观测，`base_series_id.raw_length=T`，`raw_series_hash` 只哈希该 cell 的 (X_1,ldots,X_T)。

### N-AR：Gaussian delay null

\[
X_t=\rho X_{t-1}+\sqrt{1-\rho^2}\,\varepsilon_t,
\qquad
\varepsilon_t\overset{iid}{\sim}N(0,1).
\]

- 抽取 \(X_{-1000}\sim N(0,1)\)，与后续创新独立；
- 依次递推并丢弃 \(X_{-999},\ldots,X_0\) 共 1,000 点，正式序列固定为 \(X_1,\ldots,X_T\)；
- 每个窗口内部使用 \(d=3,\tau=3\) 延迟嵌入；
- 不在整条序列上先嵌入再切窗。

### N-CIRCLE：固定边际几何、可控时序依赖

先生成

\[
G_t=\rho G_{t-1}+\sqrt{1-\rho^2}\,\varepsilon_t,
\qquad
U_t=\Phi_{\mathcal N}(G_t),
\]

其中抽取 \(G_{-1000}\sim N(0,1)\)，依次递推并丢弃 \(G_{-999},\ldots,G_0\) 共 1,000 点，正式 latent 序列固定为 \(G_1,\ldots,G_T\)；\(\Phi_{\mathcal N}\) 使用 `scipy.special.ndtr` 的 float64 实现。H1 latent process 使用完全相同的索引约定。再令

\[
X_t=
\begin{pmatrix}
\cos(2\pi U_t)\\
\sin(2\pi U_t)
\end{pmatrix}
+0.08\eta_t,
\qquad
\eta_t\sim N_2(0,I_2).
\]

\(\eta_t\) 与 \(G_t\) 的初值和创新独立，且在两个 \(\rho\) 格间共享同一 noise path。主实验固定旋转矩阵 \(Q=I_2\)，避免每条路径共享的随机旋转成为全局潜变量。任意 \(\rho\) 下 \(U_t\) 的单时点边际均为 \(U(0,1)\)；窗口内联合点云仍会随 \(\rho\) 改变，因此 \(\rho=0.8\) 只解释为原序列依赖的效应修饰条件。

H0 与 H1 只能调用同一个 `build_null_signature(rho,W,s,T,M)`：

```text
H("null_model_signature",
  null_family="N_CIRCLE",
  generator_version="N_CIRCLE_V1",
  latent_law="stationary_gaussian_ar1_then_scipy_ndtr_float64",
  initial_index=-1000,
  discarded_indices="-999..0",
  rho=<canonical decimal>,
  observation_noise="iid_N2_0_I2_times_0.08",
  rotation="I2",
  unit="dimensionless",
  W=..., stride=..., T=..., M=...)
```

`phase`、`scenario_id`、alternative 名称和任何 effect 参数均禁止进入 payload。N-CIRCLE H0 直接调用该函数生成 `null_model_config_hash`；它是 H1 size-standardization 的模型身份，不由自然语言 cell 名称代替。

---

## 8. 主 H0 双矩阵

### 8.1 Fixed-\(M\) 主矩阵

固定

\[
W=64,\qquad M=192.
\]

| stride \(s\) | 重叠率 | 原始长度 \(T=64+s(191)\) |
|---:|---:|---:|
| 64 | 0 | 12,288 |
| 32 | 0.50 | 6,176 |
| 16 | 0.75 | 3,120 |
| 8 | 0.875 | 1,592 |

因素：2 DGP × 2 \(\rho\) × 4 stride，共 16 格。

该矩阵固定扫描器看到的窗口数量，评估相同推断序列长度下的重叠变化。原始观测预算随 stride 改变，论文必须明确这一边界。

### 8.2 Fixed-\(T\) 主矩阵

固定

\[
T=3120,\qquad W=64.
\]

| stride \(s\) | 重叠率 | 窗口数 \(M\) |
|---:|---:|---:|
| 64 | 0 | 48 |
| 32 | 0.50 | 96 |
| 16 | 0.75 | 192 |
| 8 | 0.875 | 383 |

因素同上，共 16 格。\(s=16\) 与 Fixed-\(M\) 是同一个配置，只保留一份结果。因此主矩阵共有

\[
16+16-4=28
\]

个唯一格。

该矩阵固定采集预算，考察增加重叠窗口是否增加真实独立信息。改变 stride 无法同时保持 \(T\) 和 \(M\) 不变，两张矩阵共同出现才能区分两种预算视角。

### 8.3 共同随机数与计算复用

每个 DGP、replicate 先生成长度 12,288 的 master path。不同 \(\rho\) 使用相同基础创新；所有 cell 按协议读取相应前缀。

每条经 \(\rho\) 转换后的 master path 只计算下列 raw-window start 并集：

1. fixed-\(T\) stride 8 的 383 个 starts：0 至 3,056，步长 8；
2. fixed-\(M\) stride 32 在 3,072 至 6,112 的 96 个新增 starts；
3. fixed-\(M\) stride 64 在 6,144 至 12,224 的 96 个新增 starts。

所以每条 transformed master path 恰计算 575 个唯一窗口，其他 cell 只读取映射表。禁止机械计算长度 12,288 上的全部 stride-8 窗口。fixed-\(M\) 与 fixed-\(T\) 共同的 \((W,s,T,M)=(64,16,3120,192)\) 只有一个物理 cell，`budget_membership=["FIXED_M","FIXED_T"]`。

跨 stride、跨 \(\rho\) 的统计对比以同一 DGP 内的 `cluster_id` 为整簇单位，不把这些共享创新的结果当成独立样本。N-AR 与 N-CIRCLE 分层独立抽样，统计聚合时给予两个 DGP 相同权重。

---

## 9. 精确 Monte Carlo 规模

### 9.1 主 H0

每个唯一主格固定运行：

\[
R_0=2500.
\]

正式 H0 的 `replicate_id` 恰取整数 \(1,\ldots,2500\)，不允许 0-based 或缺号；同一 DGP 的相同 replicate ID 定义一个 master cluster。

在真实 Type-I 为 0.05 时：

\[
\operatorname{MCSE}
=\sqrt{\frac{0.05\times0.95}{2500}}
=0.00436,
\]

普通 95% 半宽约为

\[
1.96\times0.00436=0.00854.
\]

该规模能清楚地区分 0.01、0.05 和 0.07。这里的 2,500 是按 \(\pm0.009\) 精度目标反推并向上取整后的固定值，不能写成"至少 2,500"。

总量：

- 28 个唯一 cell × 2,500 = 70,000 个 cell-level 数据评价；
- 2 个 feature × 2 个 method，因此 H0 canonical ledger 固定为 280,000 行；
- 内层重采样统计量固定为 \(280000\times999=279720000\) 个；
- 按 2 DGP × 2 \(\rho\) × 2,500 replicate × 575 unique starts，H0 固定计算 5,750,000 个 PH 窗口；
- 所有方法共享同一数据和特征，禁止按方法重复生成 persistence diagrams。

### 9.2 H1

每个功效格固定：

\[
R_1=1600.
\]

正式 H1 的 `replicate_id` 恰取整数 \(1,\ldots,1600\)，不允许 0-based 或缺号；两种 alternative 的相同 replicate ID 属于同一 `CIRCLE_BASED_H1` master cluster。

当真实功效为 0.5 时，最坏情形普通 95% 半宽为

\[
1.96\sqrt{\frac{0.25}{1600}}=0.0245.
\]

两种 alternative × 2 个 \(\rho\) × 2 个 stride 构成 8 个 H1 cell：

- data units：\(8\times1600=12800\)；
- evaluation rows：\(12800\times2\text{ features}\times2\text{ methods}=51200\)；
- 内层重采样统计量：\(51200\times999=51148800\)；
- H1 的 stride-16 与 stride-64 虽共享部分 raw start，但 \(T\) 与变点位置不同，同一 start 未必对应同一输入数组；正式实现禁止跨 H1 `physical_cell_id` 复用 feature/PH cache。每格恰有 192 个窗口，故 PH 窗口总数为 \(8\times1600\times192=2457600\)。cache key 至少包含 `data_unit_id, window_start, W, feature_config_hash`，只允许同一 data unit 内两个 method 复用 feature。

正式合成核心总量固定为 331,200 evaluation rows、330,868,800 个内层重采样统计量和 8,207,600 个 PH 窗口。

### 9.3 Blind smoke

每个 H0/H1 物理格运行 32 个 smoke replicates，`replicate_id` 恰取 \(1,\ldots,32\)，并置于独立 smoke generation namespace；初代固定为 `smoke_generation_id=S01`，此后修订只能单调使用 `S02,S03,...`。它与 formal replicate ID 即使数值相同也没有身份或 seed 关系。只检查：

- 字段完整；
- 运行时间；
- 缓存一致；
- p 值网格；
- error/timeout；
- worker 候选配置的一致性。

H0 smoke 固定为 896 data units、3,584 evaluation rows 和 73,600 个 PH 窗口；H1 smoke 固定为 256 data units、1,024 evaluation rows 和 49,152 个 PH 窗口。在 smoke seal 前，evaluator 禁止输出 rejection rate、method ranking 或任何可用于调参的聚合结果。smoke 使用 `phase=SMOKE_NULL/SMOKE_ALT` 及当次已登记的 `smoke_generation_id`，并为每个 smoke phase 绑定唯一的 `stream_family=smoke` root entry；所有流的 `stream_kind` 必须以 `smoke_` 开头，formal root entries不得挂载到 smoke executor。`smoke_generation_id` 必须进入 smoke master/base/data/evaluation/run-component 身份。smoke 永不进入论文。

smoke 采用单一 umbrella generation：任一 DGP、feature、method、schema、RNG consumption、runner 或 smoke reference environment 的代码/配置变化，都必须把 `smoke_generation_id` 从 `S01` 整体提升并重跑两类 smoke；smoke 内不另设可独立替换的 component generations。这样相同 smoke generation、seed 和 ID 不会跨实现复用。

### 9.4 本机计算准入

已登记主机为 Windows 11、Intel i5-12600KF（10 核/16 线程）、31.81 GB RAM、RTX 4070 SUPER。`ripser` 在本计划中走 CPU，GPU 不计入吞吐预算。系统盘 C: 仅约 39.86 GB 可用，禁止承载正式 trial、临时 PH 或 release；正式工作卷固定为 F:，其可用容量必须在 preflight 实测。

正式参考环境固定为这台登记的 Windows 11 主机、冻结后的 Python lock、`float64`、冻结的 BLAS/线程变量与最终 (w^*)。全部正式 `exceed/reject` 裁决都在该环境产生；Linux/Docker 只承担独立重建与容差核对，不覆盖参考环境的离散裁决。freeze identity 必须记录操作系统 build、CPU、Python、NumPy/SciPy/ripser 版本、BLAS vendor、环境变量和 worker 数的哈希。

smoke 同时基准 `workers in {1,4,8,10,12}`，并固定：

```text
OMP_NUM_THREADS=1
MKL_NUM_THREADS=1
OPENBLAS_NUM_THREADS=1
NUMEXPR_NUM_THREADS=1
```

选择吞吐最高且满足以下条件的唯一 \(w^*\)：scientific payload 全部一致、总 peak RSS \(\le24\) GiB、无 swap、无未解释 error。若吞吐并列在 2% 内，取较小 worker 数。正式运行期间不得更换 \(w^*\)。

令完整 H0 smoke 和 H1 smoke 在 \(w^*\) 下的实测 wall time 分别为 \(t_{0,32}\)、\(t_{1,32}\)，则冻结前估计

\[
\widehat t_{H0}=1.25\frac{2500}{32}t_{0,32},
\qquad
\widehat t_{H1}=1.25\frac{1600}{32}t_{1,32},
\qquad
\widehat t_{core}=\widehat t_{H0}+\widehat t_{H1}.
\]

日历给 H0 运行预留 9月25日至10月4日的 240 小时、给 H1 运行预留 10月6日至9日的 96 小时；分别保留 20% seal/故障缓冲。准入必须同时满足

\[
\widehat t_{H0}\le192\text{ hours},
\qquad
\widehat t_{H1}\le76.8\text{ hours},
\qquad
\widehat t_{core}\le268.8\text{ hours}.
\]

任一分段 Gate 失败时，即使合计时间达标也不得 admission；计算较快的另一阶段不能借给依赖顺序尚未满足的阶段。H0 seal 只安排在其分段计算完成后，ALT 必须继续等待 authoritative H0 seal。

同理以 smoke 的持久化增量外推峰值磁盘并乘 1.25；要求 `estimated_peak_disk <= 0.8 * F_free_space`。运行期 PH 与 feature cache 只在单个 shard 内存活，写完科学结果即释放。若 wall、内存或磁盘任一不满足，先进行不改变浮点运算顺序和结果的性能修复并重跑 smoke；9月23日仍不满足时停止推进，不在正式结果出现后删格或减少 MC 数。

---

## 10. 主要估计量、假设与多重性

### 10.1 单格估计与分母

以下所有主要量都固定 `feature_id=BPI_FIXED20_H01_SIGMA005_GAMMA1_V1`。对 cell \(c\)、方法 \(j\)：

\[
\pi_{cj}=P(p_{cj}\le0.05),
\qquad
\widehat\pi_{cj}=K_{cj}/2500,
\qquad
\Delta_{cj}=\pi_{cj}-0.05.
\]

合成映射必须是 total function：零 diagram 或全常数特征固定返回 \(T_{obs}=0,p=1,reject=0\)。每格必须完整保留 2,500 个 trial；任何未解释 error、timeout、非有限值或数据依赖 ineligible 都使整格 `INVALIDATED`，不得采用 eligible-only 分母或新 seed 补位。

每格固定报告 \(K/2500\)、拒绝率、无连续性修正 Wilson 95% CI、Clopper–Pearson exact 95% CI（辅助）、\(\widehat F_p(u)-u\;[u\in\{0.01,0.025,0.05,0.10\}]\)、resampled 0.95 critical value 分布和运行诊断。无论拒绝数大小都同时计算两类区间；第 10.7 节的分类只读取 Wilson 区间，Clopper–Pearson 区间不改变标签。

Wilson 区间对 \(n=2500,\widehat p=K/n\) 固定为

\[
\frac{\widehat p+z^2/(2n)}{1+z^2/n}
\ \pm\ 
\frac{z}{1+z^2/n}
\sqrt{\frac{\widehat p(1-\widehat p)}n+\frac{z^2}{4n^2}},
\]

90%/95% 分别用 \(z=1.6448536269514722\) 与 \(1.959963984540054\)。Clopper–Pearson 95% 端点为 \([0,Q_{Beta}(0.975;1,n)]\) 当 \(K=0\)，\([Q_{Beta}(0.025;n,1),1]\) 当 \(K=n\)，其余为 \([Q_{Beta}(0.025;K,n-K+1),Q_{Beta}(0.975;K+1,n-K)]\)。实现固定使用冻结 SciPy beta quantile，并以 golden cases 锁定端点。

### 10.2 P1：Fixed-\(M\) 的两 DGP 等权平均重叠对比

只使用原始时间 IID 的 \(\rho=0\)，并对两个 DGP 等权：

\[
D_{OV}^{M}
=\frac12\sum_{g\in\{AR,CIRCLE\}}
\left[
\pi^{M}_{g,0,s=16,M0}
-\pi^{M}_{g,0,s=64,M0}
\right].
\]

检验

\[
H_0:D_{OV}^{M}\le0.10,
\qquad
H_1:D_{OV}^{M}>0.10.
\]

0.10 是实际意义阈值。\(\rho=0.8\) 不混入该因果口径，只作为原序列依赖的效应修饰分析。P1 只支持"两个注册 DGP 的等权平均效应"；AR 与 CIRCLE 的逐 DGP 差和 CI 同时报告，但本轮不以平均检验推出两个 DGP 各自均超过阈值或对所有 DGP 普遍成立。

### 10.3 P2：固定采集预算下两 DGP 等权平均的 stride/overlap 对比

\[
D_{ST}^{T}
=\frac12\sum_{g\in\{AR,CIRCLE\}}
\left[
\pi^{T}_{g,0,s=16,M0}
-\pi^{T}_{g,0,s=64,M0}
\right].
\]

检验 \(H_0:D_{ST}^{T}\le0.10\) 对 \(H_1:D_{ST}^{T}>0.10\)。Fixed-\(T\) 中 stride 同时改变窗口数量 \(M\)，因此结果只称"固定采集预算下、两个注册 DGP 等权平均的 stride/overlap 对比"。P1、P2 均成立时，才使用"在两个注册 DGP 的等权平均意义下，跨两种预算制度稳定出现实质失校准模式"。

### 10.4 P3：IID、非重叠端两个 DGP 等权平均的 DMB-R1 保守性

\[
D_{CONS}=0.05-
\frac12\sum_{g\in\{AR,CIRCLE\}}
\pi^M_{g,0,s=64,M1}.
\]

检验

\[
H_0:D_{CONS}\le0.01,
\qquad
H_1:D_{CONS}>0.01.
\]

只有两个注册 DGP 的等权平均保守幅度超过一个百分点且 Holm 校正后成立，才使用"等权平均意义下实质性保守"措辞；不得写成两个 DGP 都保守或全域保守。

### 10.5 效应修饰和控制表征

对 fixed-\(M\) 与 fixed-\(T\) 分别报告

\[
I_\rho=D_{\rho=0.8}-D_{\rho=0},
\]

其中每个 \(D_\rho\) 沿用 P1/P2 的两个 DGP 等权 stride 差。MOMENTS 对应的 P1–P3 量、完整四级 stride 曲线和 M0–M1 配对差都作为预注册次级估计，给出 95% CI，不进入主要假设家族，也不产生 `SUPPORTED` 标签。

### 10.6 分层整簇 bootstrap 与 Holm

对每个 DGP \(g\)，一次 bootstrap 抽样都从 \(r=1,\ldots,2500\) 中有放回抽取 2,500 个 `cluster_id`，并携带该 cluster 的全部 \(\rho\)、stride、预算成员和方法结果；两个 DGP 独立分层重抽。固定 \(B_A=10000\) 次。所有分析 bootstrap 的 `bootstrap_index` 从 1 开始：P1–P3 恰为 \(1,\ldots,10000\)，其余恰为 \(1,\ldots,2000\)；内层方法 `resample_index` 恰为 \(1,\ldots,999\)，均禁止 0-based 或缺号。

令 \(\widehat\theta\) 为 P1、P2 或 P3 的估计值，边界 \(\theta_0\) 分别为 0.10、0.10、0.01，\(\widehat\theta_b^*\) 为第 \(b\) 次整簇估计。三个单侧 p 值统一为

\[
p_{boot}=\frac{1+\sum_{b=1}^{10000}
1\{\widehat\theta_b^*-\widehat\theta
\ge \widehat\theta-\theta_0\}}
{10001}.
\]

95% basic bootstrap CI 为

\[
[2\widehat\theta-q_{0.975}(\widehat\theta^*),
 2\widehat\theta-q_{0.025}(\widehat\theta^*)].
\]

所有 bootstrap 分位数统一使用 nearest-rank：将该分析实际产生的 \(B_{boot}\) 个有限值 \(x_1^*,\ldots,x_{B_{boot}}^*\) 从小到大排列，

\[
q_\alpha=x^*_{(\lceil\alpha B_{boot}\rceil)}.
\]

其中 P1–P3 使用 \(B_{boot}=10000\)，\(A_\Phi\)、H1 和真实数据 bootstrap 使用 \(B_{boot}=2000\)；因此 2,000 次的 2.5%/97.5% 分位点分别取第 50/1,950 个顺序统计量。禁止沿用软件默认的线性插值分位数。上述 CI 是边际 95% basic CI，不称 Holm 同时区间。

P1–P3 的三个 \(p_{boot}\) 从小到大记为 \(p_{(1)},p_{(2)},p_{(3)}\)，Holm 调整值冻结为

\[
p^{Holm}_{(i)}=
\min\left\{1,\max_{j\le i}(4-j)p_{(j)}\right\},
\qquad i=1,2,3,
\]

再映射回原假设。对三个 bootstrap p 值应用 nominal 0.05 Holm step-down；若每个边际 p 值均为有效的 super-uniform p 值，Holm 在任意依赖下控制 FWER。本研究使用未学生化的非参数整簇 bootstrap p 值，因此只主张渐近/近似控制，不宣称有限样本精确 FWER。Holm-adjusted \(p\le0.05\) 仍作为本研究预注册的 Claim Matrix 操作性支持规则，CI 用于报告效应大小。单格热图不加显著性星号。所有分析 bootstrap 使用冻结的 `analysis_bootstrap_root_key`，不复用方法 RNG。

### 10.7 校准分类

预注册实用等价带：

\[
\mathcal E=[0.035,0.065].
\]

分类规则：

| 条件 | 标签 |
|---|---|
| 无连续性修正 90% Wilson CI 完整位于 \(\mathcal E\) | `POINTWISE_PRACTICALLY_CALIBRATED` |
| 无连续性修正 95% Wilson CI 上界低于 0.035 | `MATERIAL_CONSERVATISM` |
| 无连续性修正 95% Wilson CI 下界高于 0.065 | `MATERIAL_ANTI_CONSERVATISM` |
| 其他 | `BOUNDARY_OR_INDETERMINATE` |

等价带相当于工程公差；估计值与完整 CI 仍是主要结果。CI 覆盖 0.05 只能支持"未检出偏差"，不能自动转写为"校准良好"。

全部标签只对对应的单个 `cell × feature × method` 成立，不提供跨 28 格、两种表征或两种方法的同时保证；不得统计"通过格数"后再作显著性结论，也不得由若干 pointwise 标签写成"整个注册域校准良好"。全域主张需要另行预注册 simultaneous intervals 或 intersection–union Gate，本轮不作该主张。

---

## 11. 依赖放大指标的估计

对每个 H0 cell 估计

\[
A^{tr}_{\Phi,M}
=
\frac{
E\left\|M^{-1/2}\sum_{i=1}^M(Y_i-\mu_\Phi)\right\|^2
}{E\|Y_i-\mu_\Phi\|^2}.
\]

每个 replicate 只需保存两个可审计充分量：

\[
a_r=M^{-1}\sum_iY_{ri},
\qquad
q_r=M^{-1}\sum_i\|Y_{ri}\|_2^2.
\]

分子直接估计为

\[
\widehat{\operatorname{tr}(\Omega_{\Phi,M})}
=\frac{M}{R-1}\sum_{r=1}^R\|a_r-\bar a\|_2^2.
\]

令 \(\bar q=R^{-1}\sum_{r=1}^Rq_r\)。分母使用跨 replicate 的二阶 U-statistic 无偏估计 \(\|\mu_\Phi\|^2\)：

\[
\widehat D_U
=\bar q-
\frac{
\left\|\sum_{r=1}^R a_r\right\|_2^2
-\sum_{r=1}^R\|a_r\|_2^2
}{R(R-1)}.
\]

不同 replicate 独立，因此括号内的有序交叉内积平均无偏估计 \(\|\mu_\Phi\|_2^2\)。这避免了把两个折均值之间的平方差误加到分母而产生正偏差。最后

\[
\widehat A^{tr}_{\Phi,M}
=\widehat{\operatorname{tr}(\Omega_{\Phi,M})}/\widehat D_U.
\]

若原始 \(\widehat D_U\le10^{-12}\max(1,\bar q)\)，不启动该 cell 的 ratio bootstrap，点估计和 CI 均标记 `UNDEFINED_DEGENERATE`。否则从全部 \(R=2500\) 个 replicate 有放回整簇重抽 2,500 个，固定 2,000 次；每次都按重抽后的多重集重算分子与同一 \(\widehat D_U\) 公式。任何一次 bootstrap 分母未通过退化阈值，整项 CI 标记 `UNDEFINED_BOOTSTRAP_DEGENERACY`，不得删除该次后继续计算 percentile CI。全部 2,000 次均有效时，使用第 10.6 节冻结的 nearest-rank 分位数给出 percentile 95% CI。窗口均值实现必须恢复 T3 的解析值。BPI 的 \(A^{tr}_{\Phi,M}\) 只解释固定坐标系中的总方差重复；\(M/A\) 只称"信息量类比"，不能当成真实独立窗口数。

---

## 12. H1：构造效度、功效与定位实验

### 12.1 单时点边际均值—协方差匹配的形状/几何变化

定义

\[
C(u)=(\cos2\pi u,\sin2\pi u),
\qquad
F(u)=(\sin2\pi u,\sin4\pi u).
\]

两者满足

\[
E[C(U)]=E[F(U)]=0,
\qquad
\operatorname{Cov}[C(U)]
=\operatorname{Cov}[F(U)]
=\tfrac12I_2.
\]

变点前后分别为

\[
X_t=C(U_t)+0.08\eta_t,
\quad t\le\tau,
\]

\[
X_t=F(U_t)+0.08\eta_t,
\quad t>\tau.
\]

配置：

- \(W=64,M=192\)；
- \(s\in\{64,16\}\)；
- \(\rho\in\{0,0.8\}\)；
- \(\tau=\lfloor T/2\rfloor\)，即 (T=12288) 时 6,144、(T=3120) 时 1,560；两个配置的真实连续边界都与候选 \(k=96\) 的窗口中心中点精确对齐；
- 每格 \(R_1=1600\)。

共 4 格。\(U_t\) 使用与 N-CIRCLE 相同的单条连续 latent AR/copula path，\(\eta_t\) 也在变点两侧连续；主实验固定 \(Q=I_2\)。无噪声 skeleton 分别为圆与 figure-eight，骨架拓扑不同；加入非退化 Gaussian noise 后两侧观测分布的支持均为 \(\mathbb R^2\)，所以结果只称"潜在骨架不同的含噪形状/分布变化"，不称观测支持拓扑变化。两侧只保证每个时点的边际均值与协方差相同；当 \(\rho=0.8\) 时，滞后协方差结构无需相同，因此严禁称为"二阶随机过程匹配"。高阶边际分布、曲率和距离结构也会变化，全文禁止使用 `topology-only`。

两种 H1 alternative 的 `DGP_family` 均固定为 `CIRCLE_BASED_H1`，`scenario_id` 分别记录形状变化与 mean-shift；所以它们在相同 replicate 下共享 `master_replicate_id/cluster_id`，但因 `data_model_config_hash` 不同而拥有不同的 physical/data-unit 身份。

每个 H1 cell 先把形状/均值变化 effect 置零，再以自己的 \(\rho,W,s,T,M\) 调用第 7 节同一个 `build_null_signature`；禁止把实际 H1 DGP、phase、scenario 或 effect 参数传入。两种 alternative 由此精确回到对应 N-CIRCLE H0 的同一 `null_model_config_hash`。

### 12.2 Mean-shift 反向控制

\[
X_t=C(U_t)
+\delta v\,1(t>\tau)
+0.08\eta_t,
\qquad \delta=0.5,
\]

其中 \(v=(\cos2\pi V,\sin2\pi V)\)、\(V\sim U(0,1)\)，由独立的 `shift_direction` stream 生成并在该 replicate 的全部派生格共享。其余配置与第 12.1 节相同，共 4 格，每格 1,600。

持续同调基于窗口内部距离，纯平移对稳定段的 persistence diagram 不产生变化；MOMENTS 应当占优。该对照明确展示 TDA 的适用领域，禁止因为结果不利于 BPI 而删除。

### 12.3 功效报告

每个 cell 固定运行 BPI、MOMENTS × M0、M1，共 4 个 evaluation；两组 alternative 合计 51,200 行。每格同时报告：

1. nominal rejection power；
2. 对应 H0 的实际 Type-I；
3. size-standardized power；
4. raw-index MAE 与归一化 raw-index error；
5. 按 M0、M1 分别计算的 detection-and-localization joint success。

Size-standardized power 使用同一 \(\rho,s,W,T,M\) 的 N-CIRCLE H0 observed statistics，并按 feature 分别取经验 0.95 分位数：

\[
\widehat c_{0.95}
=T^{(\lceil0.95(R_0+1)\rceil)}.
\]

\[
\widehat{Power}_{adj}
=\frac1{R_1}\sum_{r=1}^{R_1}
1(T_r^{H1}>\widehat c_{0.95}).
\]

`source_null_logical_cell_id` 必须唯一指向 `null_model_config_hash` 完全相同的 H0 logical cell，并同时匹配 `feature_config_hash` 与 `feature_generation_id`；`source_null_phase_seal_hash` 必须指向实际供本次 size-standardization 使用的 NULL phase seal。报告某个方法的 nominal power/对应 Type-I 时还必须匹配 `method_config_hash` 与 `method_generation_id`。只核对 \(\rho,s,W,T,M\) 的 join 一律拒绝；NULL phase seal 改变时，ALT 分析必须新建 upstream binding 和 phase seal，不能静默换用另一版 H0。

两层 cluster bootstrap 固定 2,000 次。每个 bootstrap index 从 N-CIRCLE H0 的 2,500 个 master clusters 只抽一组 2,500 个索引，并把它同时应用到全部相关 \(\rho\)、stride 和 feature；再从 `CIRCLE_BASED_H1` 的 1,600 个 master clusters 只抽一组 1,600 个索引，同时应用到两种 alternative 的全部 \(\rho\)、stride 和 feature。H0 与 H1 两组索引由不同 `resample_role` 独立派生。随后重算 cell-feature 临界值、power 及每个 alternative 跨四格的等权平均差。M0 与 M1 的 observed statistic 完全相同，所以同一 cell-feature 的 size-standardized power 也完全相同，只报告一次；它用于比较 BPI 与 MOMENTS 的信号信息，不用于比较校准器。两种 feature 的平均 size-standardized power 差给出 percentile 95% CI，固定为次级估计，不设置结果支持门槛。对应 H0 cell 未获 `POINTWISE_PRACTICALLY_CALIBRATED` 标签的方法不得通过 nominal power 宣称更强；该判断读取 Wilson CI 分类，不能只看点估计是否落入等价带。反保守方法像把报警器阈值调低，命中更多异常的同时也制造更多误报。

### 12.4 定位

\[
\widehat\tau
=\left(\widehat k-\frac12\right)s+\frac{W+1}{2}.
\]

该式取第 \(\widehat k\) 与第 \(\widehat k+1\) 个窗口中心的中点，因为 CUSUM 候选 \(\widehat k\) 表示切分发生在这两个窗口之间。若使用第 \(\widehat k\) 个窗口中心，会产生约半个 stride 的系统偏移。该映射必须用手工构造的非重叠序列和重叠序列分别验证。

数据定义为 \(t\le\tau\) 属于变点前，因此真实连续边界固定为

\[
\tau_{true}=\tau+0.5.
\]

对本计划两组 H1 网格，\(k=96\) 时：非重叠配置给出 \((96-1/2)64+(64+1)/2=6144.5\)，重叠配置给出 \((96-1/2)16+(64+1)/2=1560.5\)，分别等于对应 \(\tau_{true}\)。任何 H1 builder 若不能通过这两个等式即阻断。

定位点及其无条件误差由 observed statistic 决定，可在 M0/M1 间只计算一次。固定同时报告采样点尺度的

\[
\operatorname{MAE}_{raw}
=E|\widehat\tau-\tau_{true}|,
\]

及无量纲的

\[
E\left(\frac{|\widehat\tau-\tau_{true}|}{T}\right),
\]

但联合成功率含方法特异的 p 值，必须对 \(j\in\{M0,M1\}\) 分别报告

\[
P\left(
p_j\le0.05,
|\widehat\tau-\tau_{true}|\le W/2
\right).
\]

漏检样本保留在每个方法的联合成功率分母中。条件于该方法已经拒绝的 MAE 同样按方法分别计算，只作补充，防止成功样本筛选造成过度乐观。手算测试固定包含 \((W,s,M,k,T,\tau)=(64,64,192,96,12288,6144)\) 与 \((64,16,192,96,3120,1560)\)，必须分别得到 \(6144.5\) 与 \(1560.5\)。

---

## 13. 真实数据：PAMAP2 说明性分析

### 13.1 数据身份

主真实案例固定为 UCI PAMAP2 Physical Activity Monitoring：

- DOI：<https://doi.org/10.24432/C5NW2H>
- 9 名受试者；
- 数据集总计 18 类活动；本分析只使用含 12 类协议活动的 `Protocol` 子集；
- 3 个 IMU；
- 100 Hz；
- 长连续多变量传感器序列。

官方数据页：  
<https://archive.ics.uci.edu/dataset/231/pamap2+physical+activity+monitoring>

HASC 因语料身份和公开复现条件尚未闭合，不进入本轮正式证据。TSSB 的 nonoverlap 适用覆盖较低，也不进入主稿；旧材料保留在 DMB-R1 历史归档。

### 13.2 固定数据选择

- 科学数据身份只覆盖从官方 `PAMAP2_Dataset.zip` 解出的、按 POSIX path 排序的 `Protocol/subject101.dat` 至 `Protocol/subject109.dat` 九个 recordings；`dataset_hash=H("pamap2_protocol_dataset",manifest_entries=<九个 {path,size,file_sha256}>)`。下载 ZIP 与官方独立小写 `readme.pdf` 各自记录 raw-file SHA256 和来源元数据，但不进入 `dataset_hash`；
- 纳入全部 9 名官方受试者；每行必须恰有 54 列。缺文件、坏行、非法 label 或文件解析失败都触发全数据集 `DATA_IDENTITY_FAIL`，不得把失败受试者临时排除后继续；
- 允许的非零 `activityID` 集合冻结为 \(\{1,2,3,4,5,6,7,12,13,16,17,24\}\)，另允许 transient label 0；任何其他值在 `Protocol` 文件中触发 `DATA_IDENTITY_FAIL`；
- 时间戳为官方第 1 列、activityID 为第 2 列、chest IMU 的 \(\pm16g\) 三轴加速度为 1-based 第 22–24 列；导入器同时校验列数和 README 语义；
- 1-based 第 25–27 列为 \(\pm6g\) 加速度，本分析明确禁用，防止通道误接；
- 每个 token 先按 binary64 解析：timestamp、activityID 必须有限；三个传感器 token 必须为有限数或字面 `NaN`，`+/-Inf`、拼写变体和其他 malformed token 全部失败；activityID 还须是精确整数；
- 每个文件的 timestamp 必须全局严格递增；任一 \(\Delta t\le0\) 直接触发 `DATA_IDENTITY_FAIL`，不通过重排或去重修复。先以相邻 timestamp 间隔 \(>0.5\) 秒切出 provisional clock segments；
- 每个 provisional clock segment 以首个 timestamp 为 \(t_0\)，用明确的 half-up 正值公式 \(j=\lfloor100(t-t_0)+0.5\rfloor\) 映射到整数网格，禁止调用语言默认 `round`。要求 \(|t-(t_0+j/100)|\le10^{-4}\) 秒且 \(j\) 严格递增；重复 grid index 或超容差触发 `DATA_TIMEBASE_FAIL`；
- 缺失 grid index 没有 activity label，不填成 0 且不插值；先在每个 provisional clock segment 内以缺失 grid row 切出 provisional grid-contiguous segments；
- 在 provisional grid-contiguous segment 内，对已有 grid row 的三轴传感器 NaN，先以原始 m/s² 值逐轴识别左右端点均有限、连续长度 \(r=1,\ldots,50\) 行的 run。端点为 \(x_0,x_1\) 时，第 \(k\) 个缺失值固定按 `delta=np.subtract(x1,x0,dtype=float64)`、`lam=np.divide(float64(k),float64(r+1))`、`prod=np.multiply(lam,delta,dtype=float64)`、`xk=np.add(x0,prod,dtype=float64)` 的四步顺序计算，每步舍入到 binary64，禁止 FMA contraction或代数改写；任一轴存在长度 \(>50\) 或无界 run 的行进入三轴统一 `bad_row = OR(axis_bad)`。删除全部 bad rows；final analysis segment 定义为剩余行中 grid index 连续的最大非空段，按时间顺序从 0 编号。activityID 永不插值，禁止首尾外推或各轴分别切段；长度 1 与 50 的插值 fixtures 固定输入 bytes、输出 bytes 和 digest；
- 插值和最终切段完成后，三个加速度通道统一除以标准重力 \(9.80665\) 一次，得到 `g` 单位；运算全程 binary64，不做结果驱动的全序列标准化。一个冻结 golden fixture 必须逐位验证"解析 → 网格 → 插值(m/s²) → 联合切段 → 除以 g"的顺序；
- BPI coordinate cap 固定为 6 g、归一化 birth/lifetime grid 上界为 1、`point_limit=128`、`global_empirical_winsor=false`；
- activity label=0 的 transient 段不作为活动状态；
- `REAL_DATA_CONFIG_v1.json` 固定上述路径、列、活动集、采样率、解析/网格/插值/单位规则；`TASK_BUILDER_CONFIG_v1.json` 固定第 13.3 节规则；`REAL_SCOPE_SPEC_v1.json` 固定第 13.4 节的 stride、feature 与 method。每个 config hash 都按第 15.3 节的 `config_hash` 合同计算，`real_scope_spec_id` 固定等于 `REAL_SCOPE_SPEC_v1.json` 的 config hash；
- 数据 ZIP、九个原文件、小写 `readme.pdf` 的 SHA256、下载时间、许可、字段映射、导入器版本和逐文件 timebase diagnostics 全部进入 `DATA_MANIFEST.json`，同时明确区分 `dataset_hash_inputs` 与仅作 provenance 的文件。

### 13.3 转移区间任务构造

在运行任何方法前，根据官方 activity labels 自动构造自然连续任务。task builder 可以读取标签，方法 runner 只能读取不含标签和构造字段的传感器片段；该设计称"标签隔离评估"，不称双盲。

1. `bout` 定义为同一 grid-contiguous analysis segment 内 `activityID` 相同且非零的最大连续行段；候选是 `A bout → 可选 zero run → B bout`，要求 `activity_A != activity_B` 且不得跨 clock/grid/NaN 断段；
2. A、B bout 各自精确要求行数 \(n_A,n_B\ge3000\)；
3. A/B 直接相邻时 zero run 数为 0；否则二者之间必须恰有一个最大连续 label-0 run，行数 \(1\le n_0\le500\)。因此统一为 \(0\le n_0\le500\)，不得含其他标签；
4. `subject_internal_id` 固定为文件干名 `subject101` 至 `subject109`；`relative_file_path` 固定为 POSIX path；`analysis_segment_id` 是该 subject 文件内按时间升序、从 0 开始的 final segment 编号；所有 grid start/end 都是含端点的整数；无 zero run 时 `zero_grid_start` 与 `zero_grid_end` 必须同时为 null。`candidate_identity` 恰含 `dataset_hash, relative_file_path, subject_internal_id, analysis_segment_id, activity_A, A_grid_start, A_grid_end, activity_B, B_grid_start, B_grid_end, zero_grid_start, zero_grid_end`，由 `task_candidate_id=H("real_task_candidate", candidate_identity=<object>)` 生成；
5. 对冻结的 candidate identity，分别以 `stream_kind=real_context_left/right` 按第 15.2 节 HMAC rejection mapping 直接产生 \(L_A,L_B\in\{20,\ldots,30\}\) 秒；counter 从 0 开始，仅在 64-bit 值落入 rejection tail 时递增，不实例化 PCG。若二者相等，将 \(L_B\) 在集合内循环加 1；
6. 精确提取 A bout 最后 \(100L_A\) 行、全部 \(n_0\) 行 transient 与 B bout 最前 \(100L_B\) 行，故 \(T=100L_A+n_0+100L_B\)。对 task array 的 \(i=0,\ldots,T-1\)，坐标只能机械生成为 `sample_index=i+1` 和 `relative_s=np.float64(i)/np.float64(100)`；不接收外部坐标文件或原 timestamp jitter。左右上下文不等长，方法无法从片段中心直接得知边界；
7. task 内 1-based 真值索引固定为 \(a=100L_A\)、\(b=100L_A+n_0+1\)；连续真值区间固定为
   \[
   [\tau_L,\tau_R]=[a+0.5,b-0.5].
   \]
   当 \(b=a+1\) 时区间退化为一个半整数边界；
8. 片段内不得含第三个非零活动状态，插值后传感器缺失比例必须为 0。逐任务原始 entrywise missing rate 冻结为"任务所提取行中、插值前 chest 三轴的 literal-NaN 数 / \((3T)\)"；另报 `rows_with_any_nan/T` 时必须使用该独立名称。两者逐任务进入 truth diagnostics，并以"先受试者内任务均值、再受试者等权平均"汇总；
9. 保留所有满足规则的转移，不按活动类别、任务数量或方法表现筛选；同一受试者的多个任务保持 subject cluster 身份；
10. task index 从 `task_index_generation_id="TI01"` 开始。片段信号在完成插值与单位变换后按 `object_kind="pamap2_chest_accel_task_v1"`、`dtype=">f8"`、`shape=[T,3]`、列顺序 `x,y,z`、行顺序为递增 grid index 计算第 15.4 节 `task_signal_hash`。`task_id` 的 HMAC payload 必须绑定 `task_candidate_id, task_index_generation_id, task_builder_config_hash, L_A, L_B, task_root_entry_hash, task_signal_hash`；
11. runner 输入目录固定为 `real_tasks/<task_index_generation_id>/<task_id>/`，只含 opaque task ID、上述 \(T\times3\) float64 signal、从 1 开始的 sample index 和从 0 开始的相对秒，不含 candidate ID、subject/file/原始 timestamp/activity/\(a,b,L_A,L_B\)。任务目录自身通过 schema 与 `task_signal_hash` 再核验；
12. `dataset_hash`、`real_task_root_key` commitment、`real_task_id_salt` commitment 与两个 real config hash 必须在首次 enumeration 前、最迟 9月13日提交；身份、importer tests、配置与隔离目录全部通过后先签发 `REAL_TASK_BUILD_ADMITTED`，此后 task builder 才可消费 `real_task_root_key`。上述身份、task-builder config 或 task index generation 随后任何变更都产生新的 generation 和新 task index。旧 task index 保留为 sealed artifact，其 active binding append-only 标记失效；禁止覆盖原目录；
13. 九名受试者都必须先通过数据身份与 timebase Gate。通过后定义 `subject_admitted := 该受试者至少有一个冻结任务`；唯一允许的 subject 非准入原因为 `NO_ELIGIBLE_TASK`。准入要求为至少 8 名受试者、至少 24 个任务且每名准入受试者至少 1 个任务；未满足时最迟在 9月17日进入终态 `REAL_OMITTED_BY_DATA_GATE`。

### 13.4 真实分析设置

- \(W=100\) 个采样点，即 1 秒；
- \(s\in\{100,50,25\}\)，对应重叠率 0、0.5、0.75；
- `BPI_FIXED20_H01_SIGMA005_GAMMA1_V1` 与 `MOMENTS_MEAN_COV_FROB_V1`（三维时为 9 维）；
- M0 与 M1；
- \(B=999\)；
- 若冻结任务数为 \(N_{task}\)，prediction scope 恰有 \(N_{task}\times3\times2\times2=12N_{task}\) 行；
- `REAL_PREDICTION_LEDGER` 含第 16 节要求的全部非真值身份、配置、seed/stream、observed statistic、exceed、p、decision 和 estimated boundary 字段；`estimated_change_raw_time` 必须为 null，sample-coordinate 与 relative-seconds 必须为值。schema 严禁 candidate ID、subject、file、activity、\(a,b\)、truth interval 和 localization error；
- prediction 执行环境禁止网络访问，且只挂载 sanitized task 目录、冻结方法配置、real M0/M1 keys 和输出目录；不得挂载 raw dataset、task-candidate mapping、真实标签、task root key 或 task ID salt。admission 保存 ACL、mount list 与 network-disabled attestation 的哈希；prediction log、expected index 和 shard plan 均不得出现 candidate ID；
- prediction image/环境使用 content-addressed digest 和完整 code/package/file allowlist，启动前枚举并拒绝未登记的本地 cache、额外卷、共享内存、环境变量与持久化用户目录；attestation 同时绑定 image digest、allowlist hash、process/command、mounts、ACL 和 network policy。该威胁模型只保证运行期不直接提供标签或构造字段；PAMAP2 是公开语料，信号可能被外部 record linkage 重新识别，因此全文只称 `direct-field label isolation`，不宣称抵抗公开数据匹配或达到密码学盲法；
- 隔离区中的 canonical ground-truth ledger 恰有 \(N_{task}\) 行且 `task_id` 唯一。每行恰含 `task_index_generation_id, task_index_seal_hash, task_id, subject_cluster_id, subject_internal_id, activity_A, activity_B, truth_sample_left, truth_sample_right, truth_relative_s_left, truth_relative_s_right, task_first_timestamp_s, task_signal_hash, original_entrywise_missing_rate, original_rowwise_missing_rate, truth_record_hash`；ground-truth runner 账户与路径对 prediction runner 均不可读；
- prediction ledger seal 后才允许 evaluation runner join truth。prediction→truth 是 `task_id` 上的多对一关系，每条 truth 恰匹配 12 条 predictions；prediction→evaluation 在 `evaluation_id` 上一对一且 ID 集完全相同。`REAL_EVALUATION_LEDGER` 引用 prediction-seal hash 与 truth-seal hash；prediction/evaluation 各恰有 \(12N_{task}\) 行，truth 恰有 \(N_{task}\) 行。

真实数据 seal DAG 固定如下：

以下四类 ledger 都用 UTF-8 无 BOM、每行 canonical JSON+单 LF、末行保留 LF，并直接对完整未压缩 bytes 求 SHA256。candidate rows 恰含 `task_candidate_id` 加第 13.3 节冻结的 12 个 candidate-identity 字段，按 `task_candidate_id` ASCII 排序；eligibility rows 恰含 `subject_internal_id,identity_gate_status,task_count,subject_admitted,nonadmission_reason`，按 subject ID 排序；task-record rows 恰含 `task_id,task_signal_hash,T`，按 task ID 排序；truth rows 恰含第 13.4 节列出的 truth 字段，按 task ID 排序。四者 schema 均拒绝未知字段。`candidate_manifest_content_hash`、`eligibility_table_hash`、`task_records_hash`、`ground_truth_content_hash` 分别是对应完整 bytes 的 SHA256；candidate content hash 只在 unseal 后公开。`truth_task_id_set_hash=H("truth_task_id_set",ids=<ASCII排序去重后的全部 task_id>)`。`truth_record_hash` 沿用第 15.4 节 row-hash算法，只从 logical truth row 删除自身字段后计算；candidate/task/eligibility 行不另设行 hash。

1. private candidate manifest 按 `task_candidate_id` 排序，恰列出全部满足第 13.3 节 1–9 条的 candidate identity；以独立 32-byte `candidate_manifest_salt` 生成 `candidate_manifest_salt_commitment=SHA256(salt)` 和 `candidate_manifest_commitment_hash=SHA256(b"owtda-candidate-manifest-commit-v1\x00"+salt+b"\x00"+canonical_candidate_jsonl)`。公开的 9-row eligibility table 固定每名 subject 的 identity-Gate 状态、task count、admission 与唯一原因代码，并计算 `eligibility_table_hash`；要求 candidate count、task count 和各 subject count 三方一致，且每个 candidate 恰生成一个 task；
2. 将每个 task 表示为 `{task_id,task_signal_hash,T}`，按 task ID 排序后计算 `task_records_hash`；`TASK_INDEX_SEAL` payload 恰含 `dataset_hash,real_data_config_hash,task_builder_config_hash,task_index_generation_id,task_root_entry_hash,real_task_id_salt_commitment,candidate_manifest_salt_commitment,candidate_manifest_commitment_hash,eligibility_table_hash,admitted_subject_count,candidate_count,task_count,task_records_hash`，其 canonical JSON+LF 生成 `task_index_seal_hash`。仅分别哈希 task-ID 集和 signal-hash 集的实现不合格；
3. truth logical/wire rows沿用第 15.4 节双 schema 与 float 编码，按 `task_id` 排序形成 `ground_truth_content_hash`；每行 `truth_record_hash` 只排除自身后计算；
4. 在 prediction admission 前用 CSPRNG 生成独立 32-byte `truth_commitment_salt`，公开 `truth_salt_commitment=SHA256(salt)` 以及 `ground_truth_commitment_hash=SHA256(b"owtda-ground-truth-commit-v1\x00"+salt+b"\x00"+canonical_truth_wire_jsonl)`，明文 salt 与 truth bytes 均隔离；
5. prediction phase seal 形成后，unseal runner 从冻结 raw data 与 importer/task-builder code 独立重枚举全部 candidates，再验证 truth/candidate 两个 salt commitments 与 commitments、重枚举结果逐 byte 相同、candidate↔task 一对一、eligibility counts、task-record 三元组、canonical truth bytes，以及每条 truth 的 `(task_id,task_signal_hash)` 配对；随后以 payload `task_index_seal_hash,ground_truth_commitment_hash,truth_salt_commitment,ground_truth_content_hash,truth_row_count,truth_task_id_set_hash,candidate_manifest_content_hash` 生成 `ground_truth_seal_hash=SHA256(canonical_json(payload).encode("utf-8")+b"\n")`；
6. 每条 REAL evaluation logical row保存 `prediction_row_payload_hash,truth_record_hash,prediction_phase_seal_hash,ground_truth_seal_hash`，再按普通规则计算自身新的 `row_payload_hash`；不得复制 prediction 原有 row hash 作为 evaluation row hash。

### 13.5 真实数据端点

- REAL runner 也是 total function：全部 \(12N_{task}\) 条 prediction 都必须 `eligibility=true`，零/常数特征按第 10.1 节返回固定结果；任何非有限值、error、timeout 或数据依赖 ineligible 都阻断 seal。运行完整性 coverage 固定为 1，不使用 eligible-only 或 common-support 分母；
- 对每个 `feature_id × method_id × task_id`，三个 stride pair \((100,50),(100,25),(50,25)\) 的 decision agreement 固定为 \(1\{R_{s_1}=R_{s_2}\}\)，all-three agreement 为 \(1\{R_{100}=R_{50}=R_{25}\}\)；active prediction 必须完整达到 \(12N_{task}\)，缺任一对应 prediction 时 REAL run 不能 seal，也不计算 agreement；
- 为防止"全部不拒绝"产生平凡的高 agreement，对每个 `feature × method × stride` 同时报告受试者等权边际决定率
  \[
  \widehat r_{fms}=\frac1H\sum_{h=1}^H\frac1{n_h}\sum_{q=1}^{n_h}R_{hqfms}.
  \]
  对每个有序 stride pair \((s_1,s_2)\) 报告
  \[
  d^{10}_{fm;s_1s_2}=\frac1H\sum_h\frac1{n_h}\sum_q1(R_{hqfm s_1}=1,R_{hqfm s_2}=0),
  \]
  \[
  d^{01}_{fm;s_1s_2}=\frac1H\sum_h\frac1{n_h}\sum_q1(R_{hqfm s_1}=0,R_{hqfm s_2}=1),
  \]
  并逐位验证 \(A_{fm;s_1s_2}=1-d^{10}-d^{01}\)；pair 顺序固定为上述列表的书写顺序；
- prediction ledger 同时保存 sample-coordinate 与相对秒估计，truth seal 保存相同坐标系的区间：
  \[
  \widehat t_{rel}=(\widehat\tau-1)/100,
  \qquad
  [t_{L,rel},t_{R,rel}]=[(a-0.5)/100,\ (b-1.5)/100];
  \]
- prediction seal 前不保存任务首行的原始 timestamp；unseal 后如需绝对时间，只在 evaluation ledger 中用 \(t_{abs}=t_1+t_{rel}\) 恢复；
- 到真实转移区间的秒制距离
  \[
  d_s(\widehat t_{rel},[t_{L,rel},t_{R,rel}])
  =\max\{t_{L,rel}-\widehat t_{rel},0,\widehat t_{rel}-t_{R,rel}\};
  \]
- \(d_s(\widehat t,[t_L,t_R])\le2\) 秒命中率；所有真实距离和阈值只使用 seconds 字段，sample-coordinate 只供重放；
- 定位端点明确拆成 `LOCATION_WITHIN_2S` 与方法特异的 `DETECTION_AND_LOCATION_WITHIN_2S`：
  \[
  L_{hfs}=\frac1{n_h}\sum_q1(d_{hqfs}\le2),\qquad
  J_{hfms}=\frac1{n_h}\sum_q1(R_{hqfms}=1,d_{hqfs}\le2).
  \]
  两者都报告，禁止用不含拒绝决定的 \(L\) 代替联合成功率 \(J\)；
- 冻结 `N_subject_admitted∈{8,9}`。estimand registry 的维度固定为：边际决定率 \(r\) 与联合端点 \(J\) 按 `feature × method × stride`；pair agreement 与 \(d^{10}/d^{01}\) 按 `feature × method × 3 ordered pairs`；all-three agreement 按 `feature × method`；位置命中 \(L\) 与 distance 按 `feature × stride`。计算 distance 前必须验证 M0/M1 的 observed statistic 与估计位置逐任务逐 feature×stride 精确相同，再去重为一条定位值；不满足即阻断；
- 每个二元端点先在准入受试者内取任务均值，再对准入受试者等权平均；距离先取受试者内中位数，再汇总受试者中位数与 IQR。受试者层中位数、Q1、Q3 使用第 10.6 节 nearest-rank 规则；
- 主文先列 9 名受试者的完整 eligibility 表；未准入者不进入均值、中位数、IQR、bootstrap 或 LOSO。随后报告每个预注册 estimand 的全部准入受试者值及 leave-one-admitted-subject-out 的最小值与最大值；
- 受试者 cluster bootstrap 固定 2,000 次：先按 `subject_cluster_id` ASCII 排序；每个 bootstrap index 使用 `plan_name="REAL_ALL_ENDPOINTS_V1"` 的 derived `bootstrap_plan_id`、`resample_role="REAL_SUBJECT"`、`stratum_id="ALL_ADMITTED_SUBJECTS_V1"` 的一个 RNG，恰调用一次 `rng.integers(0,N_subject,size=N_subject,dtype=np.int64,endpoint=False)` 有放回抽样，携带所抽受试者全部任务、stride、feature 和 method，再重算所有 endpoints。重复抽中的受试者作为带 multiplicity 的独立 bootstrap blocks，禁止按 ID 去重；95% CI 只作探索性不确定性描述。

真实案例只说明方法决定可能随重叠制度改变，不承担总体 Type-I 或 BPI superiority 结论。标签任务清点、身份核验和 `REAL_DATA_TASK_GATE` 必须在 9月17日前完成，完整标签隔离/ACL 攻击与 `REAL_ISOLATION_ADMISSION_GATE` 必须在 9月23日前完成；10月只运行已经冻结的任务。若数据下载 hash、字段身份、任务数量、标签隔离或 eligibility 任一失败，真实数据 run 进入 `REAL_OMITTED_BY_DATA_GATE`，合成主线继续。

---

## 14. Claim Matrix

| Claim | 层级 | 预注册支持规则 | 未支持时的固定写法 |
|---|---|---|---|
| C1：即使原始数据 IID，重叠窗口特征也未必可交换 | 主理论 | T2 精确反例成立 | 收缩到已证明的特定构造 |
| C2：naive 在 fixed-\(M\)、\(\rho=0\) 下的两个注册 DGP 等权平均重叠失真超过10个百分点 | 主实验 | P1 Holm-adjusted \(p\le0.05\) | 报告估计量与 CI，改称弱效应或未定 |
| C3：固定采集预算下两个注册 DGP 等权平均的 stride/overlap 对比超过10个百分点 | 主实验 | P2 Holm-adjusted \(p\le0.05\) | 仅当 C2 已支持时保留 fixed-\(M\) 结论；否则报告估计量与 CI 并称弱效应或未定 |
| C4：重叠窗口均值例中真实长期协方差与置换边际协方差发生错配 | 主理论 | T2/T3 给出 \(W=qs,q>1\) 时 \(\Omega=q\Gamma_0\ne\Gamma_0\)，T4 将两者映射到过程极限；最大统计量分布差异另按 T4 的特征谱条件陈述 | 仅保留交换性反例、解析方差放大与实证图谱，不外推到 BPI 协方差矩阵 |
| C5：DMB-R1 在 IID、非重叠端的两个注册 DGP 等权平均意义下存在实质保守性 | 次主张 | P3 Holm-adjusted \(p\le0.05\) | 明示 B5 未获独立复现 |
| C6：BPI 与 MOMENTS 在单时点边际均值—协方差匹配形状变化上的 size-standardized detection-power 差 | 次级描述 | 预注册 size-adjusted power 差及 95% CI | 原样报告持平或方向相反 |
| C7：mean-shift 反向控制 | 次级描述 | 预注册 size-adjusted power 差及 95% CI | 原样报告，不调整 \(\delta\) |
| C8：真实数据决定随 stride 改变 | 说明性 | subject-level 决定率、定向 discordance/agreement、定位与联合端点、LOSO 和探索性 CI 完整报告 | 报告稳定或无明显变化 |

Claim 状态只能为：

```text
UNTESTED
SUPPORTED
NOT_SUPPORTED
INCONCLUSIVE
DESCRIPTIVE_ONLY
INVALIDATED
SUPERSEDED
```

所有状态变更 append-only。

---

## 15. 随机数、trial 身份与并行合同

### 15.1 RNG

正式伪随机生成器固定为 `numpy.random.Generator(PCG64DXSM)`。每个 root key 是由操作系统 CSPRNG 生成的 32 bytes，并以 64 个 lowercase hex 字符（256 bit）登记；root key 自身不由 PCG 生成。下列名称是固定的 `stream_family` 枚举标签，而非可被覆盖的十二个全局单例槽位：

```text
smoke
null_data
null_M0
null_M1
h1_data
h1_M0
h1_M1
real_task
real_M0
real_M1
analysis_bootstrap
real_task_id_salt
```

`SEED_REGISTRY_v1.0.json` 采用 strict `entries[]` schema。每个 entry 恰含复合主键 `(project_id,protocol_id,freeze_id,evidence_generation_id,phase,stream_family,component_generation_id)`、二选一的 `root_key_hex` 或隔离 `secret_ref`、`root_key_commitment` 与 `root_entry_hash`；未知字段拒绝。entries 先验证复合主键唯一，再按该七元组 ASCII 排序。registry append-only，同一主键禁止覆盖；换 key 必须先提升对应 component generation 或全局 evidence generation。runner 只能从已签发的 `RUN_COMPONENT_SET` 解析一个精确 `root_entry_hash`，禁止按标签取"最新 key"。

用于封存明文而不驱动随机计算的 `candidate_manifest_salt` 与 `truth_commitment_salt` 进入独立的 `SECRET_COMMITMENT_REGISTRY_v1.0.json`。registry 恰含 immutable `entries[]` 与 append-only `reveal_events[]`。每个 entry 恰含 `(project_id,protocol_id,freeze_id,evidence_generation_id,task_index_generation_id,secret_kind)`、`secret_ref,secret_commitment,secret_entry_hash`；`secret_kind∈{CANDIDATE_MANIFEST_SALT,GROUND_TRUTH_SALT}`，`secret_entry_hash=H("secret_commitment_entry",project_id=...,protocol_id=...,freeze_id=...,evidence_generation_id=...,task_index_generation_id=...,secret_kind=...,secret_commitment=...)`。entries 先检查复合键唯一，再按该键 ASCII 排序。salt 为 CSPRNG 32 bytes；公开前只保存受控 `secret_ref` 和 SHA256 commitment，unseal 后追加 `{secret_entry_hash,revealed_salt_sha256,reveal_event_hash}`，禁止覆盖 entry 或历史 event。

除 `real_task_root_key` 与 `real_task_id_salt` 外，root key 在对应正式运行前写入受控 registry、提交 Git 并生成 SHA256 commitment。`real_task_root_key` 和 `real_task_id_salt` 只公开 commitment，明文与 ground truth 一同隔离；prediction seal 后才可 reveal。两者的 commitment 与 `dataset_hash` 最迟在 9月13日、首次 task enumeration 前提交。freeze/admission 校验器可读取普通 registry；在对应 `*_ADMITTED` 事件前，DGP、feature 或 resampler runner 禁止实例化或消费正式 RNG stream。

每类 root entry 的不可变键为 `(project_id, protocol_id, freeze_id, evidence_generation_id, phase, stream_family, component_generation_id)`。root family 与 generation 字段固定映射如下：

| `stream_family` | 唯一 `phase` | generation 字段 |
|---|---|---|
| `smoke` | `SMOKE_NULL` 或 `SMOKE_ALT`，每个 entry 只取其一 | 当次 umbrella `smoke_generation_id`；初代 `S01`，修订后单调 `S02,S03,...` |
| `null_data`,`null_M0`,`null_M1` | `NULL` | data 用 `data_generation_id`；M0/M1 用对应 `method_generation_id` |
| `h1_data`,`h1_M0`,`h1_M1` | `ALT` | data 用 `data_generation_id`；M0/M1 用对应 `method_generation_id` |
| `real_task`,`real_task_id_salt` | `REAL_TASK_BUILD` | `task_index_generation_id` |
| `real_M0`,`real_M1` | `REAL_PREDICTION` | 对应 `method_generation_id` |
| `analysis_bootstrap` | `ANALYSIS` | `analysis_generation_id=A01` |

若某个 resampler 在正式结果后被确认存在隔离缺陷，该方法提升 `method_generation_id` 并获得新的方法 root key；其余已证明隔离的 data/feature 结果按第 15.3 节保留。每个 entry 固定计算 `root_key_commitment=SHA256(bytes.fromhex(root_key_hex)).hexdigest()`，以及：

```text
root_entry_hash = H("root_entry",
    project_id=..., protocol_id=..., freeze_id=...,
    evidence_generation_id=..., phase=..., stream_family=...,
    component_generation_id=..., root_key_commitment=...)
```

`COMPONENT_REGISTRY_v1.json` 采用 strict `entries[]` schema。每项恰含 `project_id,protocol_id,freeze_id,evidence_generation_id,component_kind,stable_id,component_generation_id,config_hash,code_file_manifest_hash,component_registry_entry_hash`；复合主键 `(project_id,protocol_id,freeze_id,evidence_generation_id,component_kind,stable_id,component_generation_id)` 唯一，按该键 ASCII 排序且 append-only。同键不同 bytes 立即拒绝；配置或代码改变必须先提升 component generation。单项 hash 固定为 `H("component_registry_entry",project_id=...,protocol_id=...,freeze_id=...,evidence_generation_id=...,component_kind=...,stable_id=...,component_generation_id=...,config_hash=...,code_file_manifest_hash=...)`。

`code_file_manifest_hash` 只是第 15.4 节统一 `file_manifest_hash` 合同在代码角色上的字段名，entries 必须包含 `{path,size,file_sha256}`；禁止另建缺少 size 的代码清单算法。每次 admission 的 registry snapshot 从已验证且键唯一的 component、root 与 secret entries 取精确 ASCII 排序去重 hash list，`registry_snapshot_hash=H("registry_snapshot",entry_hashes=...)`；快照对象不可改写。

### 15.2 子 seed 派生

禁止依赖 worker 调度顺序、禁止 Python `hash()`、禁止含糊字符串拼接。身份与 seed payload 只允许 null、bool、integer、string、list 和 string-keyed object；配置实数必须从十进制文本/`Decimal` 生成 canonical decimal string，禁止 binary float、指数记法、前导 `+`、多余前导/尾随 0，`-0` 规范为 `"0"`（例如 0.8 只能写 `"0.8"`）。所有字符串先转 Unicode NFC；字段名和枚举限 ASCII。canonical JSON 固定为 UTF-8、键排序、无空白、`ensure_ascii=false`、`allow_nan=false`。

子 seed 必须真正由对应 root key 通过 HMAC 派生，并用 `stream_kind` 隔离组件：

```python
if {"domain", "stream_kind"} & set(named_fields):
    raise ValueError("reserved seed payload key")
# canonicalizer 还必须拒绝原键与 NFC 后键发生碰撞。
payload = canonical_json({
    "domain": "owtda-seed-v1",
    "stream_kind": stream_kind,
    **named_fields,
}).encode("utf-8")
digest = hmac.new(
    bytes.fromhex(root_key_hex), payload, hashlib.sha256
).digest()
seed_hex = digest[:16].hex()       # 恰好 32 个 lowercase hex，保留前导 0
seed = int(seed_hex, 16)
rng = np.random.Generator(np.random.PCG64DXSM(seed))
```

不同组件使用不同 `stream_kind`、root family 和 exact `named_fields`。下表中 `str` 指 NFC/ASCII 约束下的 canonical string，`int` 指 JSON integer；不得添加表外字段：

| `stream_kind` | root family | exact `named_fields` |
|---|---|---|
| `null_initial` | `null_data` | `{data_generation_id:str,DGP_family:str,master_replicate_id:str}` |
| `null_innovation` | `null_data` | `{data_generation_id:str,DGP_family:str,master_replicate_id:str}` |
| `null_observation_noise` | `null_data` | `{data_generation_id:str,DGP_family:str,master_replicate_id:str}` |
| `h1_initial` | `h1_data` | `{data_generation_id:str,master_replicate_id:str}` |
| `h1_innovation` | `h1_data` | `{data_generation_id:str,master_replicate_id:str}` |
| `h1_observation_noise` | `h1_data` | `{data_generation_id:str,master_replicate_id:str}` |
| `shift_direction` | `h1_data` | `{data_generation_id:str,master_replicate_id:str}` |
| `M0_permutation` | `null_M0` / `h1_M0` / `real_M0`，由 phase 唯一决定 | `{method_generation_id:str,data_unit_id:str,resample_index:int}` |
| `M1_gaussian_innovation` | `null_M1` / `h1_M1` / `real_M1`，由 phase 唯一决定 | `{method_generation_id:str,data_unit_id:str,resample_index:int}` |
| `analysis_bootstrap` | `analysis_bootstrap` | `{analysis_id:str,bootstrap_plan_id:str,bootstrap_index:int,resample_role:str,stratum_id:str}` |
| `real_context_left` / `real_context_right` | `real_task` | `{dataset_hash:str,task_candidate_id:str,task_index_generation_id:str,task_builder_config_hash:str,counter:int}` |
| `smoke_initial` / `smoke_innovation` / `smoke_observation_noise` | `smoke` | `{smoke_generation_id:str,phase:str,DGP_family:str,replicate_id:int}` |
| `smoke_M0_permutation` / `smoke_M1_gaussian_innovation` | `smoke` | `{smoke_generation_id:str,phase:str,smoke_data_unit_id:str,resample_index:int}` |

Formal null data keys明确排除 \(\rho,s,T,M\) 与 budget，以实现预注册的共同创新；H1 data keys 明确排除 alternative、\(\rho,s,T,M\)；method keys 明确排除 feature 与 worker。smoke keys 不得使用 formal `master_replicate_id/data_unit_id` 或 formal root families。

`null_initial` 与 `null_innovation` 即使 named fields 相同，也因 `stream_kind` 不同而不可能复用同一流；H1 同理。因此跨 \(\rho\)/stride 的共同创新真实存在，同一 data unit 的两个 feature 也共享完全相同的排列或 DMB 新息。

分析前先冻结 `ESTIMAND_SPEC_REGISTRY_v1.json`。顶层恰含 `{schema_version,entries}`，每项只含 `estimand_name,spec,estimand_spec_hash`，按名称 ASCII 排序且名称唯一；`estimand_spec_hash=H("estimand_spec",estimand_name=...,spec=<strict estimand spec>)`。registry 的 canonical JSON+LF 按单对象合同生成 `estimand_spec_registry_hash`，并严禁出现 `analysis_id` 或 `estimand_id`。该 registry 必须在计算 `analysis_spec_hash` 与 `freeze_id` 前生成；`ANALYSIS_SPEC_v1.0` 的 strict schema 恰绑定其 hash，同时冻结下表七个 bootstrap plans 的 plan name、resample role、stratum domain、cluster ordering 与抽样规模，并定义 `plan_spec_hash=H("bootstrap_plan_spec",plan_name=...,spec=<strict plan object>)`。formal admission 必须验证 registry bytes重算值、analysis spec内 hash与所属 freeze ID闭合；registry 任一 byte、estimand 集或 spec 改变都生成新 `analysis_spec_hash/freeze_id`。

随后生成 strict `ANALYSIS_INPUT_MANIFEST_<analysis_input_manifest_hash>.json`，顶层恰含 `schema_version,project_id,protocol_id,freeze_id,evidence_generation_id,analysis_generation_id,analysis_bootstrap_root_entry_hash,null_phase_seal_hash,alt_phase_seal_hash,real_analysis_input_ref,analysis_phase_state_heads_hash,analysis_validity_heads_hash,analysis_spec_hash,estimand_spec_registry_hash,analysis_code_file_manifest_hash,analysis_environment_lock_hash`。`analysis_phase_state_heads_hash=H("analysis_phase_state_heads",refs=<按 NULL,ALT,REAL_EVALUATION 固定 role 顺序的 {phase,phase_state_head_hash} list>)`；`analysis_validity_heads_hash` 用同一顺序对 `{phase,validity_registry_head_hash}` list 计算；REAL 未 INCLUDED 时两者都省略该 role。`real_analysis_input_ref` 是 discriminated union：`{status:"INCLUDED",real_evaluation_phase_seal_hash:<64hex>}` 或 `{status:"OMITTED"|"DEFERRED",disposition_hash:<64hex>}`，其余键 forbidden。content hash 沿用单对象合同，文件名中的 hash 必须与 bytes 重算值相同。

定义 `analysis_id=H("analysis",analysis_input_manifest_hash=...)` 后，另建两个 resolved indexes：`RESOLVED_ESTIMAND_INDEX_<analysis_id>.jsonl` 每行恰含 `{estimand_name,estimand_spec_hash,estimand_id}`，其中 `estimand_id=H("estimand",analysis_id=...,estimand_name=...,estimand_spec_hash=...)`；`RESOLVED_BOOTSTRAP_PLAN_INDEX_<analysis_id>.jsonl` 每行恰含 `{plan_name,plan_spec_hash,bootstrap_plan_id}`，其中 `bootstrap_plan_id=H("bootstrap_plan",analysis_id=...,plan_name=...,plan_spec_hash=...)`。两者分别按 name ASCII 验证唯一并排序，每行 canonical JSON+LF、末行保留 LF；`resolved_estimand_index_hash` 与 `resolved_bootstrap_plan_index_hash` 分别对 exact bytes 直接 SHA256。两个 index 的行集合必须分别与冻结 registry entries 和七个 plan specs 一一精确相等，所有 hashes/IDs 都从源对象重算。两者只进入 analysis seal，绝不回灌 input manifest 或 analysis ID，从图上消除自环。analysis root 变更必须提升 `analysis_generation_id` 并创建新不可变 root entry；任何输入 phase seal、分析 RNG 或分析实现变化都会生成新 analysis ID，旧分析保留归档。

分析 bootstrap 不允许一个 RNG 依次服务多个 plan 或 stratum。完整映射冻结为：

| `plan_name` | `resample_role` | `stratum_id` | 一组索引共同服务范围 |
|---|---|---|---|
| `P1_H0_PRIMARY_V1` | `H0_PRIMARY_P1` | `N_AR_MASTER`、`N_CIRCLE_MASTER` 各自独立 | P1 的全部 cell/feature/method派生量 |
| `P2_H0_PRIMARY_V1` | `H0_PRIMARY_P2` | 同上 | P2 全部派生量 |
| `P3_H0_PRIMARY_V1` | `H0_PRIMARY_P3` | 同上 | P3 全部派生量 |
| `H0_DIAGNOSTICS_ALL_V1` | `H0_DIAGNOSTIC` | 同上 | (A_\Phi)、effect modification与次级表征量 |
| `H1_NULL_QUANTILE_ALL_V1` | `NULL_QUANTILE` | `N_CIRCLE_MASTER` | 所有匹配 null 格和两种 feature |
| `H1_ALT_POWER_ALL_V1` | `ALT_POWER` | `CIRCLE_BASED_H1_MASTER` | 两种 alternative 的全部派生格与 feature |
| `REAL_ALL_ENDPOINTS_V1` | `REAL_SUBJECT` | `ALL_ADMITTED_SUBJECTS_V1` | 全部真实端点 |

每个表格单元的 seed payload 都恰为 `{analysis_id,bootstrap_plan_id,bootstrap_index,resample_role,stratum_id}`；其中 `bootstrap_plan_id` 必须从 plan name 在 resolved index 唯一解析。P1–P3 彼此使用不同 plan ID；H1 null 与 alt 也分离。REAL 一组 subject 索引联合服务全部端点。因此改变合法循环顺序不会改变抽样索引，也不会破坏共同随机数配对。

创建 analysis input manifest 与追加 `ANALYSIS_FROZEN` 前各做一次 CAS：authoritative NULL/ALT current phase-seal pointers 必须精确等于 manifest 所列 hashes，二者均不得 stale 或 `ACTIVATION_BLOCKED`，且 ALT 的 `source_null_phase_seal` ref 必须等于该 NULL seal；INCLUDED 时 REAL_EVALUATION 也须为唯一 current seal。适用 phase-state heads 与 validity heads 重新聚合后必须分别等于 `analysis_phase_state_heads_hash/analysis_validity_heads_hash`。`OMITTED` 只接受 current `REAL_DISPOSITION` chain tip 为 `REAL_OMITTED_BY_DATA_GATE`，`DEFERRED` 只接受 current tip 为 `REAL_DEFERRED`，且 manifest 的 `disposition_hash` 必须等于该 tip；DEFERRED 还要求 truth 尚未 unseal且没有 active REAL_EVALUATION seal。两次 CAS 都要核验 disposition tip 未改变。任一不符即废弃 pending analysis。

分析完成后生成 `ANALYSIS_SEAL_<analysis_id>.json`。其 payload 恰含 `analysis_id,analysis_input_manifest_hash,analysis_bootstrap_root_entry_hash,estimand_spec_registry_hash,resolved_estimand_index_hash,resolved_bootstrap_plan_index_hash,ordered_summary_artifact_refs`；summary ref 元素恰为 `{role,content_hash}`，role 顺序由冻结的 analysis spec 固定为 `CANONICAL_SUMMARY,CLAIM_MATRIX,TABLE_DATA_MANIFEST,FIGURE_DATA_MANIFEST,MANUSCRIPT_VALUES`，缺项、额外项、重复 role 均拒绝。五类 summary strict schema 可含 `analysis_id` 与 `analysis_input_manifest_hash`，严禁出现 `analysis_seal_hash`、`ANALYSIS_FROZEN` event hash、release ID/index/package hashes；这些下游引用只进入 state registry 或 release index。`analysis_seal_hash=SHA256(canonical_json(payload).encode("utf-8")+b"\n")`。状态机只有在该 seal、全部输入 phase seals、两个 resolved indexes 和 summary bytes 可重放一致时，才追加 `ANALYSIS_FROZEN` 事件 `{analysis_id,analysis_seal_hash}`；其后改动任何统计代码、输入、root 或 summary 均须创建新 `analysis_generation_id/analysis_id`，不能改写旧 seal。

analysis 状态也使用 append-only chain。每个 event 删除自身 hash 后恰含 `schema_version,event_type,analysis_id,analysis_seal_hash,superseded_analysis_state_event_hash,reason_object_hash,prev_event_hash`，其中 `event_type∈{ANALYSIS_FROZEN,INVALIDATED,SUPERSEDED}`，条件性 null/value 由 strict schema固定；`analysis_state_event_hash=SHA256(canonical_json(event_without_hash).encode("utf-8")+b"\n")`，新 `analysis_state_head_hash` 等于 chain tip。对 `event_type=ANALYSIS_FROZEN`，定义 `analysis_frozen_event_hash := analysis_state_event_hash`，release 只能使用这个精确 event hash。reducer 必须得到唯一且未被后续事件覆盖的 current `ANALYSIS_FROZEN`；否则发布阻断。

真实任务左右上下文的整数映射必须无 modulo bias。对区间大小 11，令 `limit = 2**64 - (2**64 % 11)`；从对应 HMAC digest 的前 8 bytes 读取 big-endian unsigned \(x\)，若 \(x\ge limit\) 则递增 payload 中的 `counter` 并重算，首个被接受的值映射为 \(20+(x\bmod11)\)。左右使用不同 `stream_kind`；相等时只按第 13.3 节对右值作确定性循环加一。

seed 只确定 PRNG 初态，以下 RNG consumption contract 同时冻结 API、调用次数、shape、dtype 和 C-order：

- M0 对每个 `(data_unit_id,resample_index)` 新建一个 Generator，恰调用一次 `rng.permutation(M)`，所得 `int64[M]` 直接作为排列；
- M1 对每个相同单位新建一个 Generator，恰调用一次 `rng.standard_normal(M+b-1,dtype=np.float64)`；padding 和卷积只做确定性变换；
- analysis bootstrap 对按预注册 cluster ID ASCII 排序后的 (N) 行，恰调用一次 `rng.integers(0,N,size=N,dtype=np.int64,endpoint=False)`；
- `shift_direction` 新建 Generator 后恰调用一次 `rng.random(dtype=np.float64)`，再令角度为 (2\pi V)；
- 每个 synthetic initial、innovation、observation-noise stream 均由独立 Generator 执行一次冻结在 DGP spec 中的 draw；N-AR initial shape `()`、innovation shape `[13288]`，N-CIRCLE/H1 latent initial shape `()`、latent innovation shape `[13288]`、observation noise shape `[12288,2]`，均为 float64 C-order。共享创新只复用已封存 draw bytes，不得重复消费同一 Generator。

每个 `stream_kind` 至少提供一个固定 root key/payload → `seed_hex` → 前 16 个输出值或完整短数组的 golden fixture；跨 Windows/Linux 必须逐 bit 相同。任何 NumPy 版本升级若改变 golden bytes，必须提升相应 component generation 并重新 admission。

### 15.3 主键

所有 ID 使用同一 canonical JSON 规则和以下唯一哈希函数，返回 64 个 lowercase hex 字符（256 bit）；禁止位置参数：

```python
def H(id_kind: str, **named_fields) -> str:
    if {"domain", "id_kind"} & set(named_fields):
        raise ValueError("reserved ID payload key")
    # canonicalizer 必须拒绝原键或 NFC 后键重复；不得后写覆盖前写。
    payload = canonical_json({
        "domain": "owtda-id-v1",
        "id_kind": id_kind,
        **named_fields,
    }).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()
```

所有配置对象使用严格 schema、拒绝未知字段，并统一计算：

```text
config_hash = H("config", config_kind=...,
    schema_version=..., config=<strict canonical object>)
```

其余规格类 hash 统一先以对应 strict schema 解析、拒绝未知字段，再计算 `H(<kind>,schema_version=...,spec=<strict canonical object>)`；`protocol_content_hash`、`scope_spec_hash`、`analysis_spec_hash`、`compute_spec_hash`、`release_spec_hash` 分别固定 `kind` 为 `protocol_content/scope_spec/analysis_spec/compute_spec/release_spec`。源码或文本文件集合只使用第 15.4 节的 `file_manifest_hash`。`source_tree_hash` 是被 Git 跟踪且参与正式计算的源码/配置文件之 `file_manifest_hash`；`environment_lock_hash` 是 `pyproject.toml`、`uv.lock`、Python/NumPy/SciPy/Ripser 版本、OS/architecture、BLAS vendor/thread settings 和协议列明环境变量所形成 exact environment files 的 `file_manifest_hash`。run 内多个配置的聚合身份固定为 `run_config_manifest_hash=H("run_config_manifest",config_hashes=<ASCII 排序去重 list>)`，ledger 禁止使用含义不清的裸 `config_hash`。

为避免 freeze/scope 循环，先创建不含任何 derived ID、freeze ID 或 evidence-specific logical ID 的 `SCOPE_SPEC_v1.json`：H0/H1 列出科学因子与固定重复数，REAL 只列 `replicate_source="TASK_INDEX_SEAL"` 及 stride/feature/method/必需关系，绝不预填尚未知的 \(N_{task}\)。计算 `scope_spec_hash` 后再计算：

```text
freeze_id = H("freeze", project_id=..., protocol_id=...,
    protocol_content_hash=..., scope_spec_hash=...,
    analysis_spec_hash=..., compute_spec_hash=...)
```

再用该 `freeze_id` 派生 logical IDs 和每 phase 不可变的 `SCOPE_DESIGN_<phase>_<scope_design_hash>.csv`。最终 `FREEZE_MANIFEST.json` 的文件 hash 只记录上述对象与生成物，绝不回灌 `freeze_id`。umbrella 证据代固定从 `evidence_generation_id="G01"` 开始；组件代分别登记 `data_generation_id`、每个 feature 的 `feature_generation_id` 和每个 method 的 `method_generation_id`。隔离的实现修复通过 component generation 和 append-only amendment 表达。固定主键为：

`freeze_id` 绑定的是科学/计算/分析规格内容，可在真实 task enumeration 前由已经定稿的 specs 预计算；9月23日正式冻结时必须重算得到同一值，并另行绑定最终 source/component/environment manifests。若期间任一被哈希的 spec 改变，旧 task index 随旧 freeze ID 保留归档并重新走 task-build admission，不能把新 freeze ID 写回旧任务。

`data_model_config_hash` 只覆盖生成器版本、分布/递推参数、burn-in、\(\rho\)、noise 与单位，不包含 \(W,s,T,M\)；窗口参数在 `physical_cell_id` 中单列。这样同一 transformed master path 可被多个 stride cell 复用，同时不同 \(\rho\) 的 raw series 身份仍然不同。

```text
experiment_id = H("experiment", project_id=..., protocol_id=...,
                  freeze_id=..., evidence_generation_id=...,
                  phase=..., scenario_id=...)

master_replicate_id = H("master_replicate", project_id=...,
    protocol_id=..., freeze_id=..., evidence_generation_id=...,
    phase=..., DGP_family=..., replicate_id=...)

cluster_id = H("cluster", phase=..., DGP_stratum=...,
               master_replicate_id=...)

physical_cell_id = H("synthetic_physical_cell", protocol_id=...,
    freeze_id=..., evidence_generation_id=..., phase=...,
    rho=..., W=..., stride=..., T=..., M=...,
    data_model_config_hash=...)

base_series_id = H("synthetic_base_series", master_replicate_id=...,
    data_generation_id=..., DGP_family=..., rho=...,
    raw_length=..., data_model_config_hash=...)

data_unit_id = H("synthetic_data_unit", base_series_id=...,
                 physical_cell_id=..., data_generation_id=...)

feature_sufficient_id = H("feature_sufficient", data_unit_id=...,
    feature_id=..., feature_generation_id=..., feature_config_hash=...)

resampling_stream_id = H("resampling_stream", data_unit_id=...,
    method_random_family=..., method_generation_id=...)

evaluation_id = H("evaluation", evidence_generation_id=...,
    data_unit_id=..., feature_sufficient_id=..., method_id=...,
    method_generation_id=..., method_config_hash=...)

attempt_id = H("attempt", run_instance_id=..., evaluation_id=...,
               attempt_number=...)
```

`attempt_number` 是从 1 开始的 JSON integer，按 `(run_instance_id,evaluation_id)` 在 append-only run registry 中原子单调分配；重复号或冲突事件立即阻断。同一 evaluation 在另一 run 或环境中重试会因 `run_instance_id` 不同而得到不同 attempt ID。

smoke 使用完全独立的身份域，禁止借用 formal logical IDs：

```text
smoke_master_replicate_id = H("smoke_master_replicate",
    project_id=..., protocol_id=..., freeze_id=...,
    evidence_generation_id=..., smoke_generation_id=...,
    phase=..., DGP_family=..., replicate_id=...)

smoke_physical_cell_id = H("smoke_physical_cell",
    project_id=..., protocol_id=..., freeze_id=...,
    evidence_generation_id=..., smoke_generation_id=..., phase=...,
    DGP_family=..., rho=..., W=..., stride=..., T=..., M=...,
    data_model_config_hash=...)

smoke_base_series_id = H("smoke_base_series",
    smoke_master_replicate_id=..., smoke_generation_id=..., rho=...,
    raw_length=..., data_model_config_hash=...)

smoke_data_unit_id = H("smoke_data_unit", smoke_base_series_id=...,
    smoke_physical_cell_id=..., smoke_generation_id=...)

smoke_feature_sufficient_id = H("smoke_feature_sufficient",
    smoke_generation_id=..., smoke_data_unit_id=...,
    feature_id=..., feature_config_hash=...)

smoke_resampling_stream_id = H("smoke_resampling_stream",
    smoke_generation_id=..., smoke_data_unit_id=...,
    method_random_family=...)

smoke_evaluation_id = H("smoke_evaluation", smoke_generation_id=...,
    smoke_data_unit_id=...,
    smoke_feature_sufficient_id=..., method_id=...,
    method_config_hash=...)

smoke_experiment_id = H("smoke_experiment",
    project_id=..., protocol_id=..., freeze_id=...,
    evidence_generation_id=..., smoke_generation_id=..., phase=...)

smoke_logical_cell_id = H("smoke_logical_cell",
    smoke_experiment_id=..., smoke_generation_id=...,
    DGP_family=..., scenario_id=..., rho=...,
    W=..., stride=..., T=..., M=...)

smoke_logical_data_key = H("smoke_logical_data",
    smoke_generation_id=..., smoke_logical_cell_id=...,
    smoke_master_replicate_id=...)

smoke_logical_feature_key = H("smoke_logical_feature",
    smoke_generation_id=..., smoke_logical_data_key=..., feature_id=...)

smoke_logical_evaluation_key = H("smoke_logical_evaluation",
    smoke_generation_id=..., smoke_logical_data_key=...,
    feature_id=..., method_id=...)
```

smoke ledger 的公共身份列分别写入这些值。对 `SMOKE_NULL/SMOKE_ALT`，scope/index 通用字段固定使用以下别名：`experiment_id := smoke_experiment_id`、`logical_cell_id := smoke_logical_cell_id`、`logical_data_key := smoke_logical_data_key`、`logical_feature_key := smoke_logical_feature_key`、`logical_evaluation_key := smoke_logical_evaluation_key`；expected/active indexes 中的 concrete IDs 分别使用 `smoke_data_unit_id/smoke_feature_sufficient_id/smoke_evaluation_id`。validator 必须拒绝任何 formal logical/concrete ID 混入 smoke。smoke 产物、roots、expected indexes 与 seals 均不得成为 formal phase 的 upstream input。

组件代之外再定义不随局部修复改变的逻辑键：

```text
logical_cell_id = H("logical_synthetic_cell",
    project_id=..., protocol_id=..., freeze_id=...,
    evidence_generation_id=..., phase=..., DGP_family=...,
    scenario_id=..., rho=..., W=..., stride=..., T=..., M=...)

logical_real_cell_id = H("logical_real_cell",
    project_id=..., protocol_id=..., freeze_id=...,
    evidence_generation_id=..., real_scope_spec_id=...,
    W=..., stride=...)

logical_data_key = H("logical_synthetic_data",
    logical_cell_id=..., master_replicate_id=...)

logical_real_data_key = H("logical_real_data",
    logical_real_cell_id=..., task_id=...)
```

这里的 `scenario_id` 仍禁止携带预算标签；logical keys 排除 component generation/config hash。REAL scientific schema 固定别名 `logical_cell_id := logical_real_cell_id`、`logical_data_key := logical_real_data_key`、`data_generation_id := task_index_generation_id`、`data_registry_entry_hash := task_builder_component_registry_entry_hash`、`data_root_entry_hash := real_task_root_entry_hash`；不得让各 runner 自选映射。随后

```text
logical_evaluation_key = H("logical_evaluation",
    logical_data_key=..., feature_id=..., method_id=...)

run_instance_id = H("run_instance", phase=...,
    evidence_generation_id=..., run_component_set_hash=...,
    expected_data_index_hash=..., expected_index_hash=...,
    expected_feature_index_hash=...,
    environment_lock_hash=...)
```

`logical_evaluation_key` 是 scope 的固定槽位，`evaluation_id` 是该槽位当前活动组件组合的具体实现。最终 release 对每个逻辑槽位必须恰好选择一个 active `evaluation_id`。

`design` 和 `scenario_id` 均不进入 `physical_cell_id`；`scenario_id` 只表示 DGP/alternative 科学场景，严禁携带 `FIXED_M/FIXED_T`，后两者只存于 `budget_membership`。DGP/alternative 身份已由 `data_model_config_hash` 覆盖。因此 H0 的共同 \((W,s,T,M)=(64,16,3120,192)\) 格不会因预算标签而重复。N-AR 与 N-CIRCLE 使用不同 `DGP_stratum`；H1 两种 alternative 共享同一 circle-based latent cluster。

REAL 身份另行固定为：

```text
real_base_series_id = H("real_base_series", evidence_generation_id=...,
    data_generation_id=..., dataset_hash=..., task_id=...,
    task_signal_hash=...)

real_physical_cell_id = H("real_physical_cell", protocol_id=...,
    freeze_id=..., evidence_generation_id=..., real_data_config_hash=...,
    W=..., stride=...)

real_data_unit_id = H("real_data_unit", real_base_series_id=...,
    real_physical_cell_id=..., T=..., M=..., data_generation_id=...)

real_prediction_cluster_id = H("real_prediction_cluster", task_id=...)

subject_cluster_id = H("real_subject_cluster",
    project_id=..., protocol_id=..., freeze_id=...,
    evidence_generation_id=..., dataset_hash=...,
    task_index_generation_id=..., subject_internal_id=...)
```

REAL scientific schema 将以上前三个值分别写入公共列 `base_series_id/physical_cell_id/data_unit_id`，并将 `real_prediction_cluster_id` 写入 prediction 的 `cluster_id`；前缀只表示计算公式的 `id_kind`。真实 `subject_cluster_id` 只在 truth unseal 后加入 evaluation ledger，统计分析只能使用后者。REAL 的 `feature_sufficient_id`、`resampling_stream_id` 和 `evaluation_id` 随后使用与合成数据相同的函数。opaque `task_id` 固定为 `HMAC-SHA256(key=real_task_id_salt, msg=canonical_json({"domain":"owtda-real-task-id-v1","task_candidate_id":...,"task_index_generation_id":...,"task_builder_config_hash":...,"L_A":...,"L_B":...,"task_root_entry_hash":...,"task_signal_hash":...})).hexdigest()`。

每次 admission 前生成不可变 `RUN_COMPONENT_SET_<hash>.json`。顶层 strict schema 恰含 `schema_version,project_id,protocol_id,freeze_id,evidence_generation_id,phase,scope_design_hash,parent_phase_seal_hash,binding_authority_phase_seal_hash,run_input_bindings_hash,run_input_bindings_row_count,run_input_bindings_empty_by_contract,ordered_upstream_artifact_refs,component_refs,root_refs,config_refs,code_manifest_refs,compute_git_commit,source_tree_hash,run_config_manifest_hash,registry_snapshot_hash,environment_lock_hash`。四类 refs 的 entry 分别固定为 `{role,stable_id,generation_id,hash}`；先按 `(role,stable_id,generation_id)` 检查唯一，再按该 tuple ASCII 排序，任何同 `(role,stable_id)` 多代、重复 hash、未知 role 或额外字段均拒绝。`ordered_upstream_artifact_refs` 使用第 16.2 节的固定 role 顺序。对象不含当前/下游 run seal、当前/下游 phase seal、run ID、expected/shard IDs、active indexes、路径、状态或时间。parent 与已存在的 typed upstream refs 属于输入，可合法进入；所有 scientific rows 必须逐字复制该对象绑定的四项 run-level provenance。canonical bytes 生成 `run_component_set_hash`，并为每种 phase 提供 golden bytes/hash。

失效范围按组件处理：data 缺陷提升 `data_generation_id` 并作废其全部下游；feature 缺陷只提升该 `feature_generation_id` 并作废该 feature 的全部 evaluation；resampler 缺陷只提升该 `method_generation_id`、换该 phase/method 的 root key 并作废该方法 evaluation。只有 scope、主要 estimand、科学协议发生改变，或无法证明组件隔离时，才提升全局 `evidence_generation_id` 并全量重建。单纯中断恢复保持全部 generation、ID 和 seed 不变。

`RUN_INPUT_BINDINGS_<run_input_bindings_hash>.jsonl` 只描述复用的 sealed scientific inputs，并采用 discriminated union：DATA 行恰为 `{input_kind:"DATA",logical_key,concrete_id,data_content_hash,source_run_seal_hash}`；FEATURE 行恰为 `{input_kind:"FEATURE_SUFFICIENT",logical_key,concrete_id,row_payload_hash,source_run_seal_hash}`。全表按 `(input_kind,logical_key)` ASCII 排序、主键唯一，字节合同同 expected indexes，`run_input_bindings_hash=SHA256(exact_uncompressed_jsonl_bytes)`。

令 `D_required/F_required` 为 evaluation expected index 所需的 logical data/feature keys，`D_produced/F_produced` 分别为本 run 的 `EXPECTED_DATA_INDEX/EXPECTED_FEATURE_INDEX` key 集；bindings 必须精确等于 `D_reuse=(D_required-D_produced)` 的 DATA 行与 `F_reuse=(F_required-F_produced)` 的 FEATURE 行之并集。任一缺项、额外项或 produced/reused 交集都拒绝。

`binding_authority_phase_seal_hash` 按 phase 与 revision 机械确定：存在 `parent_phase_seal_hash` 时必须与 parent 相同；初次 `REAL_EVALUATION` 的 parent 为 null，但该字段必须等于 typed upstream refs 中唯一的 `prediction_phase_seal_hash`；其余初次 producing phase 必须为 null。所有 binding 的 source run seal都必须从 binding-authority seal 的 active data/feature indexes 唯一解析，且 concrete ID/content或row hash逐项相等。初次 `REAL_EVALUATION` 是 join-only run：`D_produced=F_produced=∅`，其 DATA/FEATURE bindings 必须分别精确覆盖 prediction active indexes 中 evaluation 所需的 `D_required/F_required`，禁止直接从目录或任意历史 run 解析。只有 parent=null、binding authority=null 且本 run 生产全部所需 data/features 的初次 producing phase，bindings 才为 canonical empty JSONL。若同名目标已存在，只允许逐 byte 相同后复用，禁止覆盖。

合法零字节角色只允许显式列出的五类，并按 role 分别核验：初次 producing full run 的 empty `RUN_INPUT_BINDINGS` 必须满足 RCS 中 `row_count=0,run_input_bindings_hash=SHA256(b""),run_input_bindings_empty_by_contract=true`；feature-only、method-only 与 join-only run 的 empty `EXPECTED_DATA_INDEX`，method-only 与 join-only run 的 empty `EXPECTED_FEATURE_INDEX`，都必须由 admission 分别绑定 row count=0、对应空 ID-set hash、空内容 hash与 `empty_by_contract=true`；empty feature shard由 shard manifest 的对应 row count/set/content/flag 证明，merged empty feature ledger由 `RUN_SEAL.feature_empty_by_contract=true` 证明。初次 `REAL_EVALUATION` 必须使用上述 join-only 角色，evaluation expected index 仍为非空。上述 canonical 空文件都必须真实存在且恰为 0 bytes；其他零字节文件统一标记 `UNEXPECTED_ZERO_BYTE` 并阻断。

### 15.4 原子写入和恢复

运行期不产生几十万个散文件。每次 admission 必须先冻结 `EXPECTED_DATA_INDEX_<run_instance_id>.jsonl`、evaluation expected index、`EXPECTED_FEATURE_INDEX_<run_instance_id>.jsonl` 和 `SHARD_PLAN_<run_instance_id>.json`。shard plan 顶层恰为 `{schema_version,run_instance_id,expected_data_index_hash,expected_index_hash,expected_feature_index_hash,entries}`；每个 entry 恰为 `{row_type,row_id,shard_id,partition,bucket}`，`row_type∈{EVALUATION,FEATURE_SUFFICIENT}`，先按 `(row_type,row_id)` 验证唯一后 ASCII 排序。data units 由其 produced feature rows 证明，不单列 shard row。`partition` 的固定枚举/格式为 NULL 的 `DGP_stratum`、ALT 的 `alternative`、REAL 的常量 `REAL_TASK_RANK`；`bucket` 为非负 JSON integer。未知字段、expected ID 漏配/重配、同一 row 落入多个 shard 均拒绝。canonical bytes/hash 具有 phase-specific golden fixture。

shard plan 逐个把 `evaluation_id` 与 `feature_sufficient_id` 映射到唯一 `shard_id`，并把三个 expected-index hashes 与 `shard_plan_hash` 写入 admission。G01 初次 full run 的 H0 以 `(DGP_stratum, floor((replicate_id-1)/25))` 分区；每个 H0 shard 恰含 \(25\times14\text{ cells}\times2\text{ features}\times2\text{ methods}=1400\) evaluation rows。H1 以 `(alternative, floor((replicate_id-1)/25))` 分区，每 shard 400 evaluation rows；feature rows按其 data replicate落入相同分区。REAL 先按 opaque `task_id` 排序并编号 rank=0,…,\(N_{task}-1\)，以 `floor(rank/25)` 分区，同一 task 的 12 个 evaluations 与 6 个 feature rows 始终在一个 shard。`shard_id=H("shard",run_instance_id=...,phase=...,partition=...,bucket=...)`。局部组件重跑仍由上述确定性规则生成计划，三个 expected indexes 的 key 集共同定义 produced data/features/evaluations；其行数由对应 index精确决定。

所有非行级对象统一使用以下字节合同：数组先验证有限值、把 `-0.0` 规范为 `+0.0`，转换成协议指定 dtype 的 big-endian、C-contiguous bytes；`header_bytes=canonical_json({"domain":"owtda-array-v1","object_kind":...,"dtype":...,"shape":...,"axis_order":"C"}).encode("utf-8")`，dtype 使用 `>f8`/`>i8` 等显式代码。分隔符固定为单个 NUL byte `b"\x00"`，即 hex `00`；`array_hash = SHA256(header_bytes + b"\x00" + data_bytes).hexdigest()`。对象枚举与轴语义固定为：

| hash 字段 | `object_kind` | dtype/shape/轴顺序 |
|---|---|---|
| `innovation_hash` | `synthetic_latent_innovation_v1` | `>f8`, `[13288]`, time (t=-999,ldots,12288) |
| `raw_series_hash` | `synthetic_raw_series_v1` | `>f8`, `[T,d]`, time × coordinate |
| `task_signal_hash` | `pamap2_chest_accel_task_v1` | `>f8`, `[T,3]`, time × `x,y,z` |
| feature-matrix hash | `window_feature_matrix_v1` | `>f8`, `[M,p]`, window × frozen feature coordinate |
| sufficient-vector hash | `feature_sufficient_vector_v1` | `>f8`, `[p]`, frozen feature coordinate |

任何其他 `object_kind` 必须先改协议。每类至少一个 tiny-array golden fixture 固定 header hex、data hex 与最终 digest。原始文件 hash 直接对文件 bytes 求 SHA256；通用文件集合使用 `file_manifest_hash=H("file_manifest",manifest_entries=<按 POSIX relative path 排序的 {path,size,file_sha256} list>)`，PAMAP2 的科学 `dataset_hash` 只使用第 13.2 节九个 Protocol 文件。`expected_ID_set_hash=H("expected_id_set",ids=<排序、去重后的 64-hex ID list>)`。禁止使用平台原生 endian、pickle、`.npy` 头或 Parquet bytes 充当科学对象身份。

科学行分为 logical 与 wire 两层。内存中的 `scientific_row` 先由 `scientific_row.schema.json` 验证，科学实数字段类型为 number；计算 `row_payload_hash` 时先删除该字段，再由 schema 驱动的 `hash_view` 把每个有限 IEEE-754 binary64 转成字符串 `f64:` 加 8-byte big-endian 的 16 位 lowercase hex，`-0.0` 规范为 `+0.0`，NaN/Inf 拒绝。其他值沿用第 15.2 节 canonical JSON 类型规则：

```text
row_payload_hash = SHA256(
    canonical_json(hash_view(scientific_row_without_hash)).encode("utf-8")
).hexdigest()
```

将 hash 加回 logical row 后，`wire_row=hash_view(scientific_row_with_hash)`，并用独立的 `scientific_row_wire.schema.json` 验证，其中原 float 字段必须匹配 `^f64:[0-9a-f]{16}$`。编码/解码只依据 logical schema 标出的 float 路径，普通 string 即使以 `f64:` 开头也不得被反解为数字。每行固定为 `wire_line=canonical_json(wire_row).encode("utf-8")+b"\n"`；必须通过 `decode(encode(logical_row))` 科学值逐位相同以及 `encode(decode(wire_row))` bytes 相同的 round-trip Gate。

每个 shard 在与 final 同一卷、同一父目录的 `<run_instance_id>/<shard_id>.tmp/` staging directory 内写恰好三件：`evaluation.scientific.jsonl`、`feature.scientific.jsonl` 和 `shard_manifest.json`。前者按 `evaluation_id`、后者按 `feature_sufficient_id` 排序并连接各自 schema 的 `wire_line`，合法无 feature 时后者为零字节。两个 `shard_*_scientific_hash` 都只对原始 bytes 求 SHA256。

shard manifest 顶层恰含 `{schema_version,run_instance_id,shard_id,shard_plan_hash,evaluation,feature}`。两个 nested objects 都恰含 `{schema_hash,row_count,expected_id_set_hash,ordered_row_payload_refs,scientific_hash,empty_by_contract}`；ref 恰为 `{row_id,row_payload_hash}`，按 row ID ASCII 排序且唯一。evaluation 的 empty flag 固定 false；feature 只在本 shard expected feature set为空且 scientific bytes为 `b""` 时为 true。manifest 文件必须恰为这一不含自身 hash 的 strict object，以 canonical JSON+单 LF 保存；未知字段（包括 `shard_manifest_hash`）一律拒绝。`shard_manifest_hash=SHA256(exact_shard_manifest_file_bytes)`，该值只允许出现在 `SHARD_COMMITTED`、上游 ref 与以 hash 命名的路径中。由此每个 manifest hash 只对应一套合法文件 bytes。

writer 必须依次 fsync 三个文件与 staging directory，完成全部验证后用一次同卷 atomic directory rename 将整个目录改名为 `<shard_id>.final/`，再 fsync 父目录；final 路径已存在时禁止覆盖。随后构造 `SHARD_COMMITTED` payload，恰含 `schema_version,event_type="SHARD_COMMITTED",run_instance_id,shard_id,shard_plan_hash,shard_manifest_hash`，并计算 `shard_commit_hash=SHA256(canonical_json(payload).encode("utf-8")+b"\n")`。run registry 在 per-run exclusive lock 内以 `(run_instance_id,shard_id)` 执行 `append_if_absent` CAS：缺失时追加并 fsync；已存在且 hash相同视为幂等成功；已存在且不同立即阻断。运行时间、worker、日志和重试写入独立 append-only `attempts.jsonl`，不进入科学 hash。

中断恢复规则：

- 只有唯一 `SHARD_COMMITTED` 的 commit hash、两套 schema、row counts、ID sets、shard-plan、manifest 与文件 hashes 全部匹配时才安全跳过；仅有文件或可编辑 sidecar 不足以证明完成；
- 完整 `<shard_id>.final/` 三件套存在但没有 `SHARD_COMMITTED` 时标记 `ORPHAN_FINAL`：原目录保持只读，不覆盖或删除；用同一 IDs/seeds 重算到独立 staging directory 并逐 byte 比较三件套，完全相同才追加唯一 commit record，不同立即阻断并保留两份诊断；final 路径为普通文件、缺件目录或含额外文件时先隔离并阻断，禁止自动修补；同一 `(run_instance_id,shard_id)` 出现多个相互冲突的 commit records 也立即阻断；
- ID set 相同但 scientific hash 不同：立即阻断；
- 未 rename 的 staging shard：先记录诊断后删除整个 `.tmp/` staging directory，再以同一 ID、同一 seed 重算整 shard；
- timeout/error 只增加 attempt 记录，解决前不得 seal；
- 禁止生成替代 seed 补位。

RUN seal 时先把本 run 的 evaluation shards 合并为按 `evaluation_id` 排序的未压缩 canonical wire JSONL，并定义 `ledger_content_hash=SHA256(uncompressed_jsonl_bytes)`；feature-sufficient shards同样按 `feature_sufficient_id` 排序合并并计算 `feature_ledger_content_hash`。未产生新 feature 的 method-only run固定使用空字节 SHA256、row count=0 和空 ID-set hash。`gzip(mtime=0)` 只是传输文件，另记 file SHA256。

`ordered_shard_commit_refs` 的元素恰为 `{shard_id,shard_manifest_hash,shard_commit_hash}`；先拒绝重复 `shard_id`，再按 `shard_id` ASCII 排序，其 shard 集必须与 shard plan 精确相等。三个集合 hash 使用独立 domain：`data_unit_id_set_hash=H("data_unit_id_set",ids=<EXPECTED_DATA_INDEX 中 ASCII 排序去重 IDs>)`、`evaluation_id_set_hash=H("evaluation_id_set",ids=<ASCII 排序去重 IDs>)`、`feature_sufficient_id_set_hash=H("feature_sufficient_id_set",ids=<ASCII 排序去重 IDs>)`，空集合也按相同公式计算。每个 produced data unit 必须至少被本 run 一个 produced feature row以相同 `data_content_hash` 证明。

`RUN_SEAL` payload 恰含 `run_instance_id,run_component_set_hash,expected_data_index_hash,expected_index_hash,expected_feature_index_hash,shard_plan_hash,ordered_shard_commit_refs,produced_data_unit_count,data_unit_id_set_hash,ledger_content_hash,row_count,logical_key_count,evaluation_id_set_hash,feature_ledger_content_hash,feature_row_count,feature_sufficient_id_set_hash,feature_empty_by_contract`，不得含 seal自身 hash、status、时间或路径。`feature_empty_by_contract` 当且仅当 expected feature index、全部 feature shards与 merged feature ledger都为空时为 true；`run_seal_hash=SHA256(canonical_json(payload).encode("utf-8")+b"\n")`。active indexes必须引用 `run_seal_hash`，不能只引用 run ID；`ACTIVE_FEATURE_INDEX` 的每一行还必须能在该 seal绑定的 feature ledger中按 ID 与 row hash唯一定位。

Parquet 只作为派生查询格式，不称 canonical byte identity；每行必须通过 `evaluation_id + row_payload_hash` 与 JSONL 一一核对。release 分发合并 JSONL、派生 Parquet、shard manifests、run seal 和 attempts ledger。

---

## 16. Ledger 最小 schema

每条 scientific evaluation 必须包含以下字段；执行元数据进入独立 attempt ledger。

### 身份

```text
schema_version, row_type, project_id, protocol_id, freeze_id,
evidence_generation_id, data_generation_id,
feature_generation_id, method_generation_id,
phase, experiment_id, run_instance_id,
logical_cell_id, physical_cell_id, budget_membership, replicate_id,
master_replicate_id, cluster_id,
base_series_id, logical_data_key, data_unit_id,
data_content_hash,
logical_feature_key, logical_evaluation_key, evaluation_id,
feature_id, feature_config_hash, feature_sufficient_id,
method_id, method_config_hash,
compute_git_commit, source_tree_hash, run_config_manifest_hash,
data_registry_entry_hash, feature_registry_entry_hash,
method_registry_entry_hash, data_root_entry_hash,
resampling_root_entry_hash, registry_snapshot_hash,
run_component_set_hash, expected_index_hash, expected_feature_index_hash,
shard_plan_hash,
environment_lock_hash, row_payload_hash, scientific_result_hash
```

### 数据与窗口

```text
DGP_family, scenario_id, rho, DGP_parameters,
source_null_logical_cell_id, source_null_phase_seal_hash,
null_model_config_hash,
initial_state_seed, innovation_seed, observation_noise_seed,
shift_direction_seed,
innovation_hash, raw_series_hash, T, dimension,
W, stride, overlap_ratio,
M_expected, M_observed, m_overlap, dmb_q0,
true_boundary_synthetic
```

所有 uint128 子 seed 均以恰好 32 个 lowercase hex 字符落账，禁止以 Parquet signed integer 保存。`*_registry_entry_hash` 与 `*_root_entry_hash` 指向不可变单项对象；`registry_snapshot_hash` 只记录该 run 当时的完整快照，不要求不同 active component 的历史快照相同。

### 特征

```text
point_cloud_rule, homology_dimensions, coefficient_field,
coordinate_cap, grid_definition, kernel_sigma, persistence_weight,
point_limit, canonical_sort, infinite_death_rule,
feature_matrix_hash
```

evaluation row 的 `feature_matrix_hash` 必须逐字等于所引用 active feature-sufficient row 中的同名值；它用于便捷重放，科学内容仍以 `feature_sufficient_id` 和 feature ledger 为准。禁止再出现同义字段 `feature_hash`。`shift_direction_seed` 只在 mean-shift H1 为 required value，其他 synthetic rows 为 required null，REAL rows forbidden。

`FEATURE_SUFFICIENT_LEDGER` 每个 `data_unit_id × feature_id × feature_generation_id` 只写一行，保存 `feature_sufficient_id`、\(a_r\)、\(q_r\)、feature-matrix hash 和自身 row hash；evaluation rows 只引用该 ID，避免在两个方法行中复制 800 维向量。

该 ledger 使用独立的 `feature_sufficient_row.schema.json` 与 `feature_sufficient_row_wire.schema.json`，沿用第 15.4 节 float 编码、row hash 与 round-trip 合同。logical row 至少绑定 `project/protocol/freeze/evidence/data/feature generation`、`logical_data_key,logical_feature_key,data_unit_id,data_content_hash,feature_id,feature_sufficient_id,feature_config_hash,feature_matrix_hash,a_r,q_r,feature_result_hash` 和 `row_payload_hash`；wire rows 按 `feature_sufficient_id` 排序后形成 content hash。evaluation 引用的每个 `feature_sufficient_id` 都必须在 active feature ledger 恰有一行。

`data_content_hash` 是跨层唯一数据字节锚：synthetic 恰等于该行的 `raw_series_hash`，REAL 恰等于 `task_signal_hash`。evaluation row、feature-sufficient row 和 active data binding 都必须携带它；同一 `logical_data_key/data_unit_id` 下任何值不一致都阻断，不能仅凭派生 ID 推断原始 bytes 相同。

为区分科学结果与 run provenance，freeze 前生成 strict `scientific_result_projection.schema.json`。evaluation projection 必含 `evaluation_id,data_content_hash`、data/feature/method generation与 config identities、feature content identity、seeds、候选/统计量、observed/resampled结果、p/reject与定位结果；REAL evaluation 还保留 `prediction_row_payload_hash,truth_record_hash` 与所有评价端点。projection 明确排除 `run_instance_id,compute_git_commit,source_tree_hash,run_config_manifest_hash,registry_snapshot_hash,run_component_set_hash,expected_data_index_hash,expected_index_hash,expected_feature_index_hash,shard_plan_hash,environment_lock_hash,source_null_phase_seal_hash,prediction_phase_seal_hash,ground_truth_seal_hash,row_payload_hash,scientific_result_hash`。按第 15.4 节 hash-view canonical bytes 计算 `scientific_result_hash`。feature projection 恰含 `feature_sufficient_id,data_content_hash,feature_generation_id,feature_config_hash,feature_matrix_hash,a_r,q_r`，以同一规则计算 `feature_result_hash`。编码顺序固定为先计算并插入 result hash，再计算 `row_payload_hash`；后者只删除自身，必须覆盖已经插入的 result hash。两个 projection schemas 的字段集合、null/forbidden 规则与 golden hashes 都在 method-freeze 前固定。

### 推断

```text
candidate_first, candidate_last, candidate_count,
eligibility, ineligibility_reason,
bandwidth_b, kernel, padding_rule, B,
resampling_stream_id, observed_statistic,
exceed_count, p_value, alpha, reject,
estimated_change_index, estimated_change_raw_time,
localization_error_synthetic
```

### 执行

```text
attempt_id, evaluation_id, attempt_number, status,
start_time_utc, end_time_utc, runtime_seconds,
worker_id, hostname_digest, warning_codes, error_class,
stdout_hash, stderr_hash
```

真实数据严格拆成三层：prediction ledger 包含全部上述适用的身份、配置与推断字段，并额外写 `task_id, task_index_generation_id, task_builder_config_hash, task_signal_hash, estimated_change_sample_coord, estimated_change_relative_s`，其中 `estimated_change_raw_time` 必须为 null；candidate ID、subject、file、activity、真值和 localization error 均禁止出现。ground-truth seal 禁止出现方法结果；evaluation ledger 只在 prediction seal 后按第 13.4 节 join，增加 `subject_cluster_id`、subject/activity、truth sample/seconds interval、distance seconds，以及 `prediction_row_payload_hash,truth_record_hash,prediction_phase_seal_hash,ground_truth_seal_hash`。

### 16.1 Discriminated-union schema

正式实现必须提供 `scientific_row.schema.json`，以 `row_type × phase × DGP_family × feature_id × method_id` 为 discriminator；所有对象禁止未知字段。每种 schema 的字段要逐项标为 `required value`、`required null` 或 `forbidden`，不得在"省略字段"和"写 null"之间自行选择。最低条件矩阵固定为：

| 条件 | required value | required null | forbidden |
|---|---|---|---|
| H0/H1 synthetic | replicate/master/cluster、DGP/\(\rho\)、data streams/hash | REAL task/truth fields | subject/activity |
| H0 | observed/estimated index | synthetic true boundary、localization error、source-null ID | REAL truth fields |
| H1 | true boundary、localization、source-null ID/hash | REAL task fields | REAL truth fields |
| REAL prediction | task/data-unit identity、sample/relative-second estimate、method result | `estimated_change_raw_time`、replicate/master、DGP/\(\rho\)、synthetic seeds/boundary/localization、source-null ID | candidate ID、subject/file/activity/truth/distance |
| REAL evaluation | prediction fields与四个 join/seal hashes、subject/activity/truth/distance | synthetic-only fields | 方法重新计算字段 |
| N-AR | initial/innovation stream | observation-noise stream、null-model hash | circle latent fields |
| N-CIRCLE/H1 | initial/innovation/noise stream、适用 null-model hash | 无适用项时显式 null | 随机 \(Q\) |
| M0 | resampling stream、\(B\)、p/exceed | `bandwidth_b/kernel/padding_rule` | M1-only arrays |
| M1 | resampling stream、\(B\)、`bandwidth_b/kernel/padding_rule` | permutation-only fields | circular padding |
| BPI | PH/BPI 配置和 feature hash | MOMENTS-only 配置 | 自适应全序列配置 |
| MOMENTS | point-cloud/scale/moment 配置和 feature hash | PH/homology/kernel/grid fields | persistence-only arrays |

`SCOPE_DESIGN` 对 H0 与 REAL 的 `source_null_logical_cell_id` 强制为 null，对 H1 强制为 value；scientific row 中 `source_null_phase_seal_hash` 同样对 H0/REAL 为 null、对 H1 为 value。REAL prediction 中敏感字段属于 forbidden，不能用 null 占位。机器 schema 与本表冲突时，本表为科学意图、freeze 前必须修到一致，冲突未闭合则 G0 FAIL。

### 16.2 冻结范围、活动组件与精确行数

冻结前的 `SCOPE_SPEC_v1.json` 是无 derived ID 的科学范围真源；冻结后每个 phase 单独生成不可变 `SCOPE_DESIGN_<phase>_<scope_design_hash>.csv`。H0/H1 由它、`freeze_id` 和 `evidence_generation_id` 机械展开；REAL 还必须读取已封存 `task_index_seal_hash` 中的 \(N_{task}\) 作为唯一重复数来源。不得从目录重新计数。每个 CSV 是对应 phase/evidence generation 的逻辑计数真源，每行固定：

```text
phase, experiment_id, logical_cell_id, budget_membership,
feature_id, method_id, replicate_count,
expected_logical_evaluations, required,
source_null_logical_cell_id, null_model_config_hash
```

`SMOKE_NULL/SMOKE_ALT` 的 `experiment_id,logical_cell_id,source_null_logical_cell_id` 必须使用第 15.3 节的 smoke 专用逻辑域；其 logical data/feature/evaluation keys 也只用 smoke 专用公式。formal phase 使用 formal 逻辑域。任何跨域 ID、缺少当前 `smoke_generation_id` 的 smoke key，或把 `S01` 硬编码为永久 generation 的对象都拒绝。

计算身份时先按 strict schema 把 CSV 解析成 row objects，要求主键 `(phase,logical_cell_id,feature_id,method_id)` 唯一，将 `budget_membership` 规范为已排序无重复 list，并强制每行 `expected_logical_evaluations == replicate_count`。随后按上述主键排序并计算：

```text
scope_design_hash = H("scope_design", project_id=..., protocol_id=...,
    freeze_id=..., evidence_generation_id=..., phase=...,
    scope_upstream_hashes=...,
    rows=<sorted strict rows>)
```

`SMOKE_NULL/SMOKE_ALT/NULL/ALT` 的 `scope_upstream_hashes` 强制为 `[]`；`REAL_PREDICTION/REAL_EVALUATION` 强制为 `[task_index_seal_hash]`。CSV 文件名中的 phase/hash、对象内 phase 与重算 hash 必须三方一致；文件自身另记 file SHA256，行顺序或换行格式不得影响 `scope_design_hash`。run admission、`RUN_COMPONENT_SET` 与 `PHASE_SEAL` 都必须绑定本 phase 的该 hash。

active binding 正规化为三层，禁止在 `(phase,feature,method)` 条目中重复选择 data generation：

1. `ACTIVE_DATA_INDEX_<active_revision_id>.jsonl`：每个 `logical_data_key` 唯一映射到 `data_unit_id,data_content_hash,data_generation_id,data_registry_entry_hash,data_root_entry_hash,source_run_seal_hash`；
2. `ACTIVE_FEATURE_INDEX_<active_revision_id>.jsonl`：令 `logical_feature_key=H("logical_feature",logical_data_key=...,feature_id=...)`，每个 key 唯一映射到 `feature_sufficient_id, feature_generation_id, feature_registry_entry_hash, feature_row_payload_hash, source_run_seal_hash`；
3. `ACTIVE_EVALUATION_INDEX_<active_revision_id>.jsonl`：每个 `logical_evaluation_key` 唯一映射到 `evaluation_id, method_generation_id, method_registry_entry_hash, resampling_root_entry_hash, source_run_seal_hash`。

首次 `REAL_EVALUATION` 是跨 phase 的纯 join revision：其 ACTIVE DATA/FEATURE indexes 必须从 typed upstream 所绑定的 current `REAL_PREDICTION` phase seal 逐 byte 继承，行内 `source_run_seal_hash` 继续指向原 prediction run seals；ACTIVE EVALUATION index 才引用本 phase 的 join-only run seal。evaluation builder 只把已 sealed prediction rows与已 sealed truth rows连接，禁止重算 data、feature、observed statistic或 p 值。

validity registry 是按 phase 分离的 append-only hash chain。首个 head 固定为 `validity_genesis_hash=H("validity_genesis",project_id=...,protocol_id=...,freeze_id=...,evidence_generation_id=...,phase=...)`。此后每个 `INVALIDATE` event 在删除自身 `event_hash` 后恰含 `schema_version,event_type,project_id,protocol_id,freeze_id,evidence_generation_id,phase,logical_kind,logical_key,expected_current_concrete_id,expected_current_source_run_seal_hash,reason_code,reason_object_hash,prev_event_hash`；`event_type="INVALIDATE"`，`logical_kind∈{DATA,FEATURE,EVALUATION}`。`event_hash=SHA256(canonical_json(event_without_event_hash).encode("utf-8")+b"\n")`，且 `prev_event_hash` 必须等于写入瞬间该 phase 的 chain tip；新 head 就是新 `event_hash`。事件写入还须 CAS 验证 expected concrete ID/source seal 与当前 active binding 一致，禁止对历史 binding 补写"当前失效"。

初版 `parent_phase_seal_hash=null` 时，通常三个 replacement sets 分别等于完整 scope 的全部 data/feature/evaluation logical keys。唯一例外是首次 `REAL_EVALUATION`：data/feature replacement sets 固定为空，evaluation replacement set等于完整 evaluation scope；data/feature active bindings按上一段从 prediction authority seal继承。后续 revision 必须从拟绑定 validity head 沿 `prev_event_hash` 反向遍历并恰好到达 parent phase seal 所绑定 head；未到达、断链、分叉或循环均拒绝。只读取这段新增事件，并对仍命中 parent active binding 的 event 计算 data→feature→evaluation 依赖闭包；三个 replacement hashes 分别按 `H("data_replacement_key_set",keys=<ASCII排序去重64hex list>)`、`H("feature_replacement_key_set",keys=<...>)`、`H("evaluation_replacement_key_set",keys=<...>)` 计算。`REAL_EVALUATION` validity chain 禁止产生 DATA/FEATURE invalidation；prediction/data/feature 在 truth unseal 后发现缺陷时走 `REAL_INVALIDATED_POST_UNSEAL`。没有新命中事件时三个 delta 必须为空，禁止创建仅为换行的 revision。

`replacement_source_run_seal_hashes` 必须精确等于本 revision 三个非空 replacement sets 所引用、由本 phase 实际 produced 的 source-run seals 的 ASCII 排序去重集，不能只做包含检查。每个此类 source run seal 的 phase、evidence generation、scope、parent binding 与本 revision 必须一致；各 run expected outputs 两两不重叠，其并集须恰覆盖相应 delta，且 component generation 等于本 revision 选择值。首次 `REAL_EVALUATION` 继承的 DATA/FEATURE bindings不属于 replacement，故不进入该字段；它们必须逐项来自 `binding_authority_phase_seal_hash=prediction_phase_seal_hash`，并通过该 prediction phase seal 的 active indexes、source run seals及内容 hash重放。任何其他跨 phase source seal均拒绝。

构建器先在临时路径计算三层 exact bytes/hashes，再构造不含 `active_revision_id` 的 strict component manifest。其顶层恰含 `schema_version,phase,evidence_generation_id,parent_phase_seal_hash,validity_registry_head_hash,data_replacement_key_set_hash,feature_replacement_key_set_hash,evaluation_replacement_key_set_hash,replacement_source_run_seal_hashes,active_data_index_hash,active_feature_index_hash,active_evaluation_index_hash,selected_component_refs,selected_root_refs,selected_config_refs,selected_code_manifest_refs,isolation_proof_refs`。各 refs 元素使用 `{role,stable_id,generation_id,hash}`，按 `(role,stable_id,generation_id)` ASCII 排序且唯一；同一 `(role,stable_id)` 多代、任何 superset、未知字段均拒绝。manifest 只允许选择 active indexes 实际引用的恰当 entries。按单对象合同得到 `active_component_manifest_hash` 后再计算：

```text
active_revision_id = H("active_revision", phase=...,
    evidence_generation_id=..., parent_phase_seal_hash=...,
    validity_registry_head_hash=...,
    active_component_manifest_hash=...,
    active_data_index_hash=..., active_feature_index_hash=...,
    active_evaluation_index_hash=...)
```

三个 indexes 与 manifest 都以同一 `<active_revision_id>` 命名；manifest bytes 中不回填该 ID。每类对象具有 golden bytes/hash。若目标已存在，只允许逐 byte 相同后复用，严禁覆盖。

`EXPECTED_DATA_INDEX_<run_instance_id>.jsonl`、`EXPECTED_INDEX_<run_instance_id>.jsonl` 与 `EXPECTED_FEATURE_INDEX_<run_instance_id>.jsonl` 分别描述该 run 要产生的 data units、evaluations 与 feature sufficients；三者的排序 bytes hashes 和 `SHARD_PLAN_<run_instance_id>.json` hash 一同写入 admission。phase assembler 必须验证每条 active evaluation 所引用的 data/feature ID 与前两层 binding 精确相同。

每条 active data binding 还必须在其 `source_run_seal_hash` 所封存的 feature ledger 中至少找到一个同 `logical_data_key/data_unit_id/data_content_hash` 的 row；其两个预注册 feature bindings必须全部可定位。phase assembler 还要验证同一 logical data 下的全部 active feature/evaluation rows 都逐字等于 data index 的 `data_content_hash`。这样 data index 不能凭空指向未被 sealed scientific row 证明或内容不一致的数据单元。

`EXPECTED_DATA_INDEX` 每行恰含 `logical_data_key,data_unit_id`，两列分别唯一；`EXPECTED_FEATURE_INDEX` 每行恰含 `logical_data_key,logical_feature_key,data_unit_id,feature_sufficient_id`，`logical_feature_key/feature_sufficient_id` 分别唯一；`EXPECTED_INDEX` 每行恰含 `logical_data_key,logical_feature_key,logical_evaluation_key,data_unit_id,feature_sufficient_id,evaluation_id`，`logical_evaluation_key/evaluation_id` 分别唯一。同一 logical data 或 feature 在三表中必须始终指向同一 concrete ID。每行全部字段均为 64-hex，并必须按第 15.3 节公式重算闭合。三个 indexes 分别按 `logical_data_key/logical_feature_key/logical_evaluation_key` ASCII 升序排列；feature-only/method-only/join-only run允许 data index为零行，method-only/join-only run允许 feature index为零行。所有 expected/active JSONL 都用 UTF-8 无 BOM、每行 canonical JSON、单个 LF，末行也有 LF，且分别按其 logical primary key 排序；content hash 对未压缩 exact bytes 求 SHA256。内容禁止出现 run ID、文件名或自身 hash。`SHARD_PLAN` 是按 `(row_type,row_id)` 排序的 strict entries object；`RUN_COMPONENT_SET`、shard plan、active component manifest 及其他单对象 manifest 都按 `SHA256(canonical_json(object_without_own_hash).encode("utf-8")+b"\n")` 计算 content hash。每种 wire object 都有 golden fixture。

固定计数：

| phase | data units | evaluation rows |
|---|---:|---:|
| H0 smoke | 896 | 3,584 |
| H1 smoke | 256 | 1,024 |
| H0 formal | 70,000 | 280,000 |
| H1 formal | 12,800 | 51,200 |
| REAL prediction | \(3N_{task}\) stride-units | \(12N_{task}\) |
| REAL evaluation | 与 prediction 在 evaluation ID 上一对一 | \(12N_{task}\) |

H0/H1 formal 的 feature-sufficient rows 分别固定为 140,000 和 25,600。REAL 的 eligibility table 恰 9 行、ground truth 恰 \(N_{task}\) 行、logical real cells 恰 3 行、scope design 恰 12 行、data units 恰 \(3N_{task}\)、feature-sufficient rows 恰 \(6N_{task}\)、prediction/evaluation 各恰 \(12N_{task}\)。`expected_logical_evaluations` 必须直接求和得到对应数；seal checker 禁止现场从目录或自然语言重新推断范围。

phase assembler 从 source run seals 复制已验证的 exact `wire_line`，禁止解码后重序列化；evaluation 按 `evaluation_id` ASCII、feature 按 `feature_sufficient_id` ASCII 排序后直接连接，末行保留单 LF，分别生成 `active_ledger_content_hash` 与 `active_feature_ledger_content_hash`。

同一 formal phase 的全部 active source runs 必须绑定 `COMPUTE_FREEZE` 指定的同一 `compute_git_commit,source_tree_hash,run_config_manifest_hash,environment_lock_hash`，除非已按缺陷路由提升相关 component generation并形成新 active revision。相同 `evaluation_id` 若曾在多个 sealed runs 中出现，必须具有相同 `scientific_result_hash`；相同 `feature_sufficient_id` 必须具有相同 `feature_result_hash`。完整 wire row 只由 `(source_run_seal_hash,row_id)` 唯一定位，允许 run/upstream provenance 随合法新 run 改变。科学结果 hash 冲突时记 `IDENTITY_CONTENT_CONFLICT` 并阻断，禁止结果后挑选其中一份。

`RUN_SEAL` 只在本 run 的 expected indexes/shard plan 范围内核验局部计数。`PHASE_SEAL` 才组装 active logical evaluation/feature ledgers，并对 H0/H1 应用完整的 280,000/51,200 evaluation 计数、140,000/25,600 feature-row 计数、每个 logical key 恰一行以及三层 binding 一致性。phase seal payload 恰含 `phase,evidence_generation_id,scope_design_hash,parent_phase_seal_hash,validity_registry_head_hash,data_replacement_key_set_hash,feature_replacement_key_set_hash,evaluation_replacement_key_set_hash,replacement_source_run_seal_hashes,active_component_manifest_hash,active_data_index_hash,active_feature_index_hash,active_evaluation_index_hash,active_ledger_content_hash,active_feature_ledger_content_hash,active_feature_row_count,logical_key_count,evaluation_id_set_hash,feature_sufficient_id_set_hash,ordered_source_run_seal_hashes,ordered_upstream_artifact_refs`；`ordered_source_run_seal_hashes` 必须精确等于三层 active indexes 行内全部 source-run seal 的 ASCII 排序去重集，故首次 REAL_EVALUATION 合法包含 prediction source seals与本 phase join source seals；`replacement_source_run_seal_hashes` 仍只含本 revision produced delta来源。两个 ID-set hash 采用第 15.4 节彼此独立的 domain。`phase_seal_hash=SHA256(canonical_json(payload).encode("utf-8")+b"\n")`，不得含自身、status、时间或路径。初版 `parent_phase_seal_hash=null` 时各 replacement set 按本节前述一般规则或 REAL_EVALUATION 唯一例外生成；后续 revision 的非 replacement rows 必须与 parent index 逐 byte相同。

每个 phase 另有 append-only phase-state chain，genesis 由 `H("phase_state_genesis",project_id=...,protocol_id=...,freeze_id=...,evidence_generation_id=...,phase=...)` 固定。激活 event 删除自身 hash 后恰含 `schema_version,event_type="PHASE_ACTIVATED",project_id,protocol_id,freeze_id,evidence_generation_id,phase,expected_parent_phase_seal_hash,expected_validity_registry_head_hash,new_active_revision_id,new_phase_seal_hash,prev_phase_state_event_hash`；`phase_state_event_hash=SHA256(canonical_json(event_without_hash).encode("utf-8")+b"\n")`，新 head 等于该 hash。writer 在同一 exclusive phase lock 内同时 CAS 验证 current phase pointer、validity tip 和 phase-state tip，append+fsync event 后释放锁；可编辑 current pointer只作缓存并由 event-chain reducer重建。崩溃发生在 event fsync 前则无激活，发生在其后则 reducer恢复新 pointer。初版 expected parent为 null；断链、分叉、循环或同一 tip 的多个 child全部阻断。

typed upstream refs 的顺序与内容冻结为：NULL `[]`；ALT `[{role:"source_null_phase_seal",hash:...}]`；REAL prediction `[{role:"task_index_seal",hash:...},{role:"ground_truth_commitment",hash:...}]`；REAL evaluation `[{role:"prediction_phase_seal",hash:...},{role:"ground_truth_seal",hash:...}]`。相同 refs 同时进入该 phase 的 `RUN_COMPONENT_SET`，因此上游证据变更会机械改变 run/phase 身份。

局部修复时固定执行：先在 append-only validity registry 标记受影响 logical bindings，并将该 phase 置为 `ACTIVATION_BLOCKED`；随后创建新 component generation/root entry 和 `RUN_COMPONENT_SET` → expected indexes → `run_instance_id` → shard plan → admission/run/`RUN_SEAL`。只有新 run seal 已存在后，才生成引用它的三层 ACTIVE index revision 与 component manifest，组装新 `PHASE_SEAL`，最后用 compare-and-swap 原子激活；CAS 同时要求 registry 当前 phase seal 精确等于 `parent_phase_seal_hash`，且当前 validity-registry head 精确等于 seal 所绑定的 `validity_registry_head_hash`。任一不符都放弃激活，并基于最新 parent/head 重建。pending indexes 永远不能成为 active；运行期间旧 phase seal保持不可变，但标为 stale 且禁止分析读取。最终合并器按已激活 indexes 对每个逻辑槽位选且只选一个 sealed row；旧 run/phase seals保留只读，旧行不得进入新的 canonical active ledger。

---

## 17. Integrity Gates

### G0：项目身份

- DMB-R1 终止记录存在且可验证；
- 新 `project_id/protocol_id` 与旧代不同；
- 工作区干净；
- `git stash list` 为空；
- 所有配置、schema、统计分析脚本已 tracked；
- source、protocol、component registry/root entry、environment hash 完整；
- `COMPUTE_FREEZE.json` 单独列出 DGP、window、feature、method、runner 及配置文件；后续仅修改表图代码不会改变已经 sealed 的 compute identity。

### G1：理论和实现对齐

- CUSUM 数学式与代码误差 \(\le10^{-12}\)；
- window count、fixed-\(M\)/fixed-\(T\) 公式通过；
- multivariate direct-point-cloud 路由通过；
- window-local delay embedding 通过；
- analytic window-mean covariance 和 VIF 通过；
- BPI 没有整序列自适应步骤。

### G2：确定性与攻击测试

- workers=1 与最终 \(w^*\) 的 scientific payload 一致；
- 顺序打乱后一致；
- 对唯一 `(root_entry_hash, canonical payload)` 无派生 seed 碰撞；协议要求跨 feature/\(\rho\)/stride 共用的同一 payload 视为 intentional alias 并须产生同一 stream；
- 点云行顺序攻击后 BPI 一致；
- p 值可重放；
- DMB multiplier covariance 与理论一致；
- 方法共享 observed statistic 和候选集；
- 中断恢复与一次完成一致；
- logical/wire 两层 schema、float round-trip、reserved-key/NFC-collision 与 array golden digests 全部通过；
- PAMAP2 sanitized task 目录、opaque ID、mount/ACL/network isolation 攻击全部通过。

### G3：blind smoke

- H0/H1 分别恰有 3,584/1,024 个 smoke evaluation；
- evaluator 未暴露科学汇总；
- 0 未解释 error；
- §9.4 的 wall、RAM、F: 磁盘三项均 PASS；
- admission 前 formal runner 没有实例化或消费正式随机流。

### G4：正式运行准入

- H0、H1 分别生成 phase admission；REAL prediction admission 要求 `REAL_DATA_TASK_GATE`、`REAL_ISOLATION_ADMISSION_GATE` 与 `REAL_COMPUTE_SCHEDULE_GATE` 三者都 PASS。前两者失败进入 `REAL_OMITTED_BY_DATA_GATE`；计算日程 Gate 失败则保持 truth 封闭并记 `REAL_DEFERRED`，不签发 admission；
- 协议、方法、分析计划、图表规格共同冻结；
- Git tag、environment lock、`RUN_COMPONENT_SET` 与其白名单 component/root entries 一致；
- `SCOPE_SPEC_v1.json`、本 phase 的 `SCOPE_DESIGN_<phase>_<scope_design_hash>.csv`、`RUN_INPUT_BINDINGS_<run_input_bindings_hash>.jsonl`、`RUN_COMPONENT_SET`、对应 run instance 的 data/evaluation/feature expected indexes 与 shard plan 已生成并相互闭合；
- 对当前 phase 适用的前置 Gate 均为 PASS；
- `open_runs=0`。

### G5：结果 seal

- 每个 `RUN_SEAL` 只核验自身三类 expected indexes、shard plan、committed shards、局部行数与未压缩 ledger content hash；
- 每个版本化 `PHASE_SEAL` 核验 active 三层 indexes、全部 source run seals 和 active ledger；H0/H1 active evaluations 分别为 280,000/51,200；REAL 路径启用时 truth 为 \(N_{task}\)、prediction/evaluation 各为 \(12N_{task}\)，不得合并计成一个含糊总数；
- feature-sufficient rows 分别为 140,000/25,600；
- 0 缺失主键；
- 0 重复 evaluation；
- 0 身份冲突；
- 每个 logical data/feature/evaluation key 在相应 active index 恰有一个 binding，evaluation 引用的 data/feature identity 必须与前两层相同；所有 superseded bindings 均被排除；
- 0 未解释 error；
- 每个 p 值满足 \((1+exceed)/1000\)；
- `reject ⇔ p≤0.05 ⇔ exceed≤49`；
- physical cell、budget membership 和 scope 计数与冻结配置完全一致；
- row/shard scientific hash 与 attempt metadata 已分离；
- `ledger_content_hash`、run seal hash 和 phase seal hash 均按第 15.4/16.2 节重放一致；
- `open_runs=0`。

### G6：分析与发布

- 表图只读取 sealed ledger；
- `ANALYSIS_INPUT_MANIFEST`、`ESTIMAND_SPEC_REGISTRY`、resolved estimand/bootstrap-plan indexes 与 `ANALYSIS_SEAL` 的身份图无环，hash 全部可重放；
- `ANALYSIS_FROZEN` 事件精确绑定当前 `analysis_id/analysis_seal_hash`，release index 必须绑定同一 analysis seal；
- manuscript 数字可从 canonical summary 重建；
- 真实数据标签在 prediction seal 后才打开；
- 标签打开后，同一 task/evidence generation 没有新增、替换或 supersede prediction；
- freeze 前的 `RELEASE_SPEC_v1.0.yaml` 定义路径模式和必需性，结果后生成的 `RELEASE_INDEX_<release_id>.json` 是打包唯一真源；
- 除第 15.3 节显式登记的 `empty_by_contract=true` 角色外，无零字节、缺失文件和未经 active manifest 授权的 umbrella/component generation；
- 从空环境重建主表图；
- ZIP 外部 SHA256 sidecar 验证通过。
- release attestation、签名与 pre-registered public-key fingerprint 验证通过。

---

## 18. 科学结果分类与 failure routes

### 18.1 结果分类

以下现象均属于合法科学结果，不触发工程终止：

- naive 未呈单调趋势；
- DMB-R1 未复现 s64 保守；
- BPI 与 MOMENTS 持平；
- BPI 在 mean shift 中落后；
- 某些 overlap cell 接近 0.05；
- 真实数据没有显著方法差异。

它们只更新 Claim Matrix。

### 18.2 缺陷处理

| 事件 | 固定动作 |
|---|---|
| DGP 实现错误 | 提升 `data_generation_id`，作废其全部下游，使用新 data root key 重跑 |
| 扫描统计量、candidate、plateau 或公共 evaluator 实现错误 | 直接提升全局 `evidence_generation_id`、更换全部正式 root keys，并重建所有已启用 formal phases、三层 active indexes 与 phase seals；final release 只允许一个 umbrella generation，不保留其他 Gxx phase 拼接 |
| BPI 实现改变 | 提升该 `feature_generation_id`，作废该特征下全部方法结果；其他 feature 仅在隔离证明通过时保留 |
| 某个 resampler 改变 | 提升该 `method_generation_id`、换该方法 root key，只作废该方法结果；保留有隔离证明的 data/feature/其他方法 |
| 绘图或汇总错误且 ledger 正确 | 只重建下游产物 |
| 计算中断 | 同 ID、同 seed 恢复 |
| 正式 CI 过宽 | 标记 `INCONCLUSIVE`，禁止追加 MC 追求通过 |
| 数据 coverage 低 | 按预注册规则降级或省略，禁止下调准入线 |
| 理论证明无法闭合 | 收缩理论主张，不篡改实验结果 |
| 正式结果后希望调带宽 | 新建 `OWTDA-CAL-R2`，新协议和新 seed |

### 18.3 稿件科学 GO/NO-GO

- C1 理论反例必须成立；
- T3 解析式与独立数值实现一致；
- C2 或 C3 至少一项按 Holm 规则得到 L2 支持；
- 28 格 H0 与 8 格 H1 全部 seal；
- 论文主张与近邻文献仍有明确差异。

如上述条件不满足，完整负结果继续归档。该判断不触发参数调整。

---

## 19. 必须完成的攻击测试

### 身份与配置

1. 改动配置一个字节，旧 freeze 必须失效；
2. 源码未提交时 runner 必须拒绝；
3. 非空 stash 时 freeze 必须拒绝；
4. 缺少字段或出现未知字段必须拒绝；
5. config、method registry 和 ledger 的 \(W,s,T,M\) 不一致时拒绝；
6. 混入旧代 ledger 时分析器拒绝。

### RNG 与并行

7. 同 seed、同配置逐字段一致；
8. workers=1 与冻结的 \(w^*\) scientific payload 一致；
9. 随机打乱任务提交顺序后一致；
10. smoke、H0、H1、真实分析 seed 无交集；
11. 对唯一 `(root_entry_hash, canonical payload)` 的派生 seed 0 碰撞；intentional alias 去重后审计，且别名必须逐项匹配协议；
12. 禁止直接调用全局 `np.random.*`；
13. 改变 \(\rho\)/stride 后 innovation hash 保持相同，resampling stream 按 data unit 正确变化。

### 窗口与特征

14. \(M=\lfloor(T-W)/s\rfloor+1\)；
15. fixed-\(M\) 反算 \(T=W+s(M-1)\)；
16. fixed-\(T\) 不允许自动改变 \(T\)；
17. \(s=W\) 时 overlap=0、\(m_{ov}=0\)；
18. 最后一个完整窗口和边界索引正确；
19. window index→raw time 使用人工反例验证；
20. 点云行置换不改变 persistence；
21. 输入行乱序、重复行和远端无关窗口扰动不改变目标窗口的 BPI；
22. circle、figure-eight、单点、重复点、共线点产生预期结构；
23. 平移、旋转和缩放性质符合方法定义；
24. VR `thresh`、coordinate cap 与 grid bound 分开；
25. 空图、零强度和无限 death 按协议处理。

### 推断

26. CUSUM 公式重放误差 \(\le10^{-12}\)；
27. observed statistic 在 M0、M1 间精确一致；
28. p 值全量重放；
29. p 值位于 0.001 网格；
30. exceed=49 拒绝、exceed=50 不拒绝；
31. DMB 经验协方差与三角核理论值一致；
32. 无 circular wrap；
33. padding 逐位复现；
34. resample exceed 使用 reference environment 的 float64 精确 `>=`；
35. candidate/exclusion/plateau 对所有方法相同。

### Ledger 与发布

36. 删除一条 trial，seal 失败；
37. 复制一条 trial，seal 失败；
38. 篡改 p 值，replay 失败；
39. ledger 行顺序改变不影响汇总；
40. figure 读取未 sealed 或多代 ledger 时失败；
41. canonical summary 与论文数字不一致时失败；
42. release spec 或结果期 release index 漏项时失败；
43. 非白名单零字节文件触发 `UNEXPECTED_ZERO_BYTE`；白名单空对象逐 role 满足第 15.3–15.4 节各自的 count/set/content/flag 合同时才通过；
44. ZIP 篡改后 SHA256 失败；
45. Windows/Linux 的 seed、ID 和整数索引精确一致；浮点量按冻结容差比较，靠近判断边界的样本回到 formal reference environment 裁决；
46. 人为中止并恢复后的 scientific ledger 与一次完成一致，attempt ledger 保留不同执行记录；
47. fixed-\(M\)/fixed-\(T\) 共同的 s=16 配置只产生一个 `logical_cell_id` 和一个 active `physical_cell_id`；
48. 修改 `budget_membership` 不改变物理数据 hash；
49. REAL prediction row 出现 subject、activity 或 truth 字段时 schema 拒绝；
50. 修改 attempt 时间戳不改变 row/shard scientific hash；
51. H0/H1 行数偏离 280,000/51,200 时 seal 失败；
52. BPI 与 MOMENTS 的 M0 排列索引、M1 Gaussian 新息逐 resample 相同；
53. H1 的 `source_null_logical_cell_id` 必须唯一指向 `null_model_config_hash` 与 feature/method 身份均匹配的 N-CIRCLE H0；
54. 主 N-CIRCLE/H1 配置中出现随机 \(Q\) 时 config validator 拒绝；
55. `*_ADMITTED` 前 formal runner 尝试消费正式 RNG stream 时拒绝；
56. 改变任一 root key 后该 family 全部派生 seed 改变，其他 family 不变；
57. named fields 相同但 `stream_kind` 不同的初值/创新 seed 必须不同；
58. canonical JSON、HMAC 和全部 ID 具有跨 Windows/Linux 的 golden fixtures；
59. `row_payload_hash` 计算排除自身，NaN/Inf 和非 canonical float 被拒绝；
60. 修改一个 method generation 只使该方法 evaluation/stream ID 改变，data/feature ID 保持不变；
61. PAMAP2 的非递增 timestamp、重复 grid index、超残差和缺失 grid row 攻击分别触发冻结动作；
62. task builder 无法生成 `activity_A=activity_B` 或跨 analysis segment 的任务；
63. REAL truth 恰有 \(N_{task}\) 行、prediction/evaluation 各恰有 \(12N_{task}\) 行，prediction→truth 每 task 12:1 且 prediction→evaluation 按 evaluation ID 一对一；
64. 修改 H1 noise、burn-in、\(Q\) 或生成器版本后 `null_model_config_hash` 改变且 source-null join 失败；
65. 局部 method/feature generation 提升后旧 logical binding 进入 `SUPERSEDED`，旧 run seal 保持不可变，active ledger 对每个 logical key 仍恰有一行；
66. active component 白名单外的 registry snapshot、source hash 或 generation 混入时 seal 失败；
67. 任意调换 DGP stratum、H0/H1 layer 或 estimand 循环顺序后 bootstrap 抽样索引和结果不变；
68. 同一数组的 native little-endian/C-order 表示与规范 big-endian hash view 得到同一 `array_hash`，shape/axis/dtype 任一改变则 hash 改变；
69. 九个 Protocol manifest entries 的输入顺序打乱不改变 `dataset_hash`，其中任一文件 byte/relative path 改动则改变；ZIP 或 `readme.pdf` 单独 provenance hash 改动不改变 scientific dataset hash；
70. PAMAP2 bout/candidate builder 的 3,000/500 行边界、零个/一个 zero run 和三轴 bad-row union 具有正反例；
71. 改变 \(L_A,L_B\)、task-builder generation/config、task root commitment 或 signal 任一项都改变 `task_id`；
72. discriminated-union schema 对 required value/null/forbidden 逐格攻击，省略键、用 null 冒充 value、泄露 REAL truth 或给 M0 填 M1 字段均拒绝；
73. seed/ID payload 注入 reserved key 或制造 Unicode NFC key collision 时拒绝；canonical decimal 的指数、前导 `+`、多余 0 和 `-0` 攻击均拒绝；
74. logical-row 与 wire-row 双 schema、float path 定向解码和双向 byte round-trip 通过；普通字符串 `f64:...` 不被误解码；
75. scientific row 含 active-index hash、run-seal hash 或其他 post-run 字段时拒绝，run→ledger→seal 图保持无环；
76. data/evaluation/feature expected indexes 的重复 logical/concrete ID、错误排序、BOM、CRLF、缺末行 LF、额外字段或自引用字段均使 admission 失败；
77. `ORPHAN_FINAL` 重算一致时只补唯一 commit，不一致或冲突 commit records 时阻断且不覆盖原件；
78. RUN/PHASE seal 中删改 feature ledger 一行、feature ID set 或 feature content hash时失败；
79. 在 BPI/MOMENTS 或 M0/M1 active entries 中混入不同 data generation，以及在两种 method 间混入不同 feature generation 时，三层 binding 检查失败；
80. 改变 NULL upstream phase seal 后，旧 ALT seal 不再可激活；改变 task-index/truth commitment 或 prediction/truth seal 后，旧 REAL 下游 seal 不再可激活；
81. ground-truth salt、任一 truth byte、task ID 集或 task signal hash 变动时 precommit/unseal 验证失败；evaluation row 的 prediction/truth lineage 可逐行重放；
82. `REAL_LABELS_UNSEALED` 后同一 task/evidence generation 的新增或替换 prediction 被状态机拒绝；
83. scope CSV 行序/换行变化不改变 `scope_design_hash`，但 strict row 值、主键或 evidence generation 改动会改变；
84. candidate ID 或 task-candidate mapping 出现在 REAL prediction input、expected index、shard plan、ledger 或 log 的任一处时 isolation Gate 失败；
85. PAMAP2 golden fixture 逐位验证 half-up 网格、m/s² 内插、三轴 bad-row union、最终切段和除以 g 的固定顺序。
86. 每个 RNG stream 的 API、调用次数、shape、dtype 或 consumption 顺序任一改变，golden fixture 失败；
87. 同一 evaluation 在不同 run 的 `attempt_number=1` 得到不同 attempt ID，同一 run 内重复 attempt number 被拒绝；
88. `RUN_INPUT_BINDINGS` 文件名 hash、bytes、parent active indexes 或 reused/produced 集合任一不一致时 admission 失败；
89. `ANALYSIS_INPUT_MANIFEST → analysis_id → 两个 RESOLVED indexes → ANALYSIS_SEAL` 可按有向无环图重放，任何回灌 derived ID 的 registry 被拒绝；
90. release payload 路径/byte 或 analysis seal 改变会改变 `release_id`；把 release index、package manifest、SHA 或 ZIP 加入 release-ID payload 时 schema 拒绝。
91. shard commit 的重复/冲突 CAS、漏 commit、manifest/commit ref 集合不等于 shard plan 时均阻断 RUN seal；
92. phase-state/validity/current-pointer 任一 tip 在组装或分析冻结期间变化时 CAS 失败；
93. ZIP path traversal、casefold collision、symlink、duplicate member、额外 member 与无效 release attestation signature 全部被拒绝。

浮点数组默认测试容差：

```python
np.allclose(a, b, rtol=1e-10, atol=1e-12)
```

p 值、exceed、reject、索引和 seed 在 formal reference environment 内必须精确相同。最大统计量 plateau 容差冻结为

\[
\tau_{plateau}=64\epsilon_{64}\max(1,|T_{max}|).
\]

最大 plateau 定义为所有满足 \(T(k)\ge T_{max}-\tau_{plateau}\) 的最大连续候选段；并列段取最左段，段内取 lower median。跨平台边界审计标记条件为 \(|T_b-T_{obs}|\le128\epsilon_{64}\max(1,|T_b|,|T_{obs}|)\)，该标记只触发参考环境重放，不自行改变 exceed 规则。

---

## 20. 仓库结构与脚本职责

```text
owtda-calibration/
├── README.md
├── CITATION.cff
├── LICENSE
├── pyproject.toml
├── uv.lock
├── src/owtda_cal/
├── tests/
├── configs/
│   ├── schema/
│   ├── smoke/
│   ├── confirm_null/
│   ├── confirm_h1/
│   └── real/
├── governance/
│   ├── PROJECT_CHARTER.md
│   ├── PRIOR_EVIDENCE_SUMMARY.md
│   ├── PROTOCOL_v1.0.md
│   ├── METHOD_SPEC_v1.0.md
│   ├── SAP_v1.0.md
│   ├── DATA_SPEC_v1.0.md
│   ├── CLAIM_MATRIX_v1.0.csv
│   ├── METHOD_REGISTRY_v1.0.yaml
│   ├── COMPONENT_REGISTRY_v1.json
│   ├── SEED_REGISTRY_v1.0.json
│   ├── SECRET_COMMITMENT_REGISTRY_v1.0.json
│   ├── ESTIMAND_SPEC_REGISTRY_v1.json
│   ├── SCOPE_SPEC_v1.json
│   ├── SCOPE_DESIGN_<phase>_<scope_design_hash>.csv
│   ├── ACTIVE_DATA_INDEX_<active_revision_id>.jsonl
│   ├── ACTIVE_FEATURE_INDEX_<active_revision_id>.jsonl
│   ├── ACTIVE_EVALUATION_INDEX_<active_revision_id>.jsonl
│   ├── ACTIVE_COMPONENT_MANIFEST_<active_revision_id>.json
│   ├── RUN_INPUT_BINDINGS_<run_input_bindings_hash>.jsonl
│   ├── RUN_COMPONENT_SET_<run_component_set_hash>.json
│   ├── EXPECTED_DATA_INDEX_<run_instance_id>.jsonl
│   ├── EXPECTED_INDEX_<run_instance_id>.jsonl
│   ├── EXPECTED_FEATURE_INDEX_<run_instance_id>.jsonl
│   ├── SHARD_PLAN_<run_instance_id>.json
│   ├── ANALYSIS_INPUT_MANIFEST_<analysis_input_manifest_hash>.json
│   ├── RESOLVED_ESTIMAND_INDEX_<analysis_id>.jsonl
│   ├── RESOLVED_BOOTSTRAP_PLAN_INDEX_<analysis_id>.jsonl
│   ├── ANALYSIS_SEAL_<analysis_id>.json
│   ├── RELEASE_SPEC_v1.0.yaml
│   ├── AMENDMENT_REGISTRY.jsonl
│   ├── INVALIDATION_REGISTRY.jsonl
│   ├── RUN_REGISTRY.jsonl
│   └── STATE_REGISTRY.jsonl
├── scripts/
│   ├── 00_preflight.py
│   ├── 01_import_pamap2.py
│   ├── 02_build_real_tasks.py
│   ├── 03_export_method_spec.py
│   ├── 04_build_scope_design.py
│   ├── 05_run_blind_smoke.py
│   ├── 06_build_freeze.py
│   ├── 07_admit_phase.py
│   ├── 10_run_null_shards.py
│   ├── 20_seal_null.py
│   ├── 30_run_h1_shards.py
│   ├── 31_seal_h1.py
│   ├── 40_run_real_predictions.py
│   ├── 41_seal_real_predictions.py
│   ├── 42_unseal_real_labels.py
│   ├── 43_build_real_evaluation.py
│   ├── 50_build_analysis.py
│   ├── 60_build_tables.py
│   ├── 61_build_figures.py
│   ├── 70_validate_release.py
│   └── 80_build_release.py
├── audit/
│   ├── validate_identity.py
│   ├── validate_transitions.py
│   ├── validate_ledgers.py
│   ├── replay_pvalues.py
│   ├── verify_rng.py
│   ├── verify_scope_counts.py
│   ├── verify_truth_isolation.py
│   ├── verify_figures.py
│   ├── verify_manuscript_values.py
│   └── attack_suite.py
├── artifacts/
│   ├── preflight/
│   ├── trials/
│   ├── ledgers/
│   ├── seals/
│   ├── summaries/
│   ├── tables/
│   ├── figures/
│   └── audit/
├── manuscript/
└── release/
```

发布构建器先按 `RELEASE_SPEC_v1.0.yaml` 解析最终路径，再生成 `RELEASE_INDEX_<release_id>.json`。打包器只读取结果期 index，禁止递归扫描目录猜测交付内容。

### 20.1 对话式交付与本地执行合同

每一批都使用固定四件套：

```text
<BATCH_ID>_EXECUTION_GUIDE.md
<BATCH_ID>.patch
<BATCH_ID>_VALIDATION_REPORT.md
<BATCH_ID>.patch.sha256
```

方案方负责计划、算法、补丁、测试、审计脚本和结果判读；本地执行方负责在登记主机上应用补丁、运行测试与大计算，并原样回传证据。每批顺序固定：

1. 本地回传 `git rev-parse HEAD`、`git status --porcelain=v1`、`git stash list`；
2. 只有 status 和 stash 都为空才创建批次分支；已有修改先形成具名 commit，禁止自动 stash；
3. 校验 patch SHA256，执行 `git apply --check` 后再 apply；
4. 按手册运行定向测试、全套测试、攻击测试或 phase runner；
5. 回传新的 HEAD、空工作区证明、测试摘要、Gate JSON 路径/hash 和完整错误日志；
6. 方案方完成复审并书面签发下一批，禁止在上一批未闭合时并行修改同一科学模块。

formal phase 开始后，compute-freeze 列出的文件只读。发生错误时先停止对应 run、保留 shard/attempt 证据，再按第 18.2 节确定失效范围；本地不得现场改参数后续跑。

---

## 21. 图表和表格计划

### 主图

1. **图1**：raw series → overlapping windows → persistence diagrams → BPI → scan 的机制图；
2. **图2**：窗口均值解析 \(A_{mean,M}\) 与 overlap 的关系；
3. **图3**：Fixed-\(M\) Type-I heatmap；
4. **图4**：Fixed-\(T\) Type-I heatmap；
5. **图5**：p 值 ECDF 左尾与 empirical 0.95 critical value 对比；
6. **图6**：\(A^{tr}_{\Phi,M}\) 与 Type-I 的联合图；
7. **图7**：单时点边际均值—协方差匹配形状变化与 mean-shift 的 size-standardized power；
8. **图8**：PAMAP2 转移区间示例及 stride-dependent decisions。

### 主表

1. **表1**：DGP、预算制度、stride、\(T\)、\(M\)、overlap、方法；
2. **表2**：主 H0 拒绝率与 Wilson CI；
3. **表3**：P1–P3 对比、basic bootstrap CI、Holm-adjusted p；
4. **表4**：校准分类与 eligibility；
5. **表5**：功效、对应 size、size-adjusted power、定位；
6. **表6**：PAMAP2 subject-level 完整结果。

所有图输出 PDF、SVG、PNG 和 `.meta.json`。元数据必须包括输入 ledger hash、脚本 hash、环境 hash 和生成时间。

数据流唯一：

```text
sealed trial JSON
→ validated canonical ledger
→ canonical summaries
→ tables/figures
→ manuscript_values.json
→ manuscript consistency checker
```

禁止手工在画图或 LaTeX/Word 脚本中硬编码结果数字。

---

## 22. 论文结构

1. **引言**：TDA 变点背景、IID 检验与重叠派生对象之间的缺口、三项贡献；
2. **拓扑窗口扫描框架**：窗口、点云、PH、BPI、CUSUM；
3. **交换性与校准理论**：T1–T5；
4. **实验协议**：DGP、双预算、方法、MC 精度、审计；
5. **有限样本校准边界**：Type-I、p 值尾部、critical values、依赖放大；
6. **构造效度、功效与定位**：单时点边际均值—协方差匹配形状变化与 mean-shift；
7. **PAMAP2 说明性案例**；
8. **讨论**：适用边界、DMB-R1 的局限、未来 stride-equivariant 方法；
9. **结论**；
10. **补充材料**：完整证明、全部次级格、配置、seed、旧证据披露和重现说明。

禁止使用的措辞：

- 所有重叠窗口必然失去交换性；
- 重叠必然导致 Type-I 膨胀；
- 拓扑映射制造了时间依赖；
- \(A_\Phi\) 单独决定多维扫描 Type-I；
- DMB 普遍恢复名义水平；
- B5 已证明 \(b=6\) 是唯一原因；
- WPI 的 IID 保证可直接用于当前扫描；
- BPI 在真实数据上普遍优于标量方法。
- 固定参数 BPI 与旧自适应 BPI 属于同一个数值方法。

---

## 23. 日期排程

日期按北京时间执行。

| 日期 | 工作 | 必须交付 |
|---|---|---|
| 9月9日 | 关闭 DMB-R1，定稿本计划 | 终止记录、Prior Evidence、Plan v1.0 |
| 9月10日 | 建新仓库、Charter、Claim Matrix 和论文骨架 | 干净项目身份 |
| 9月11日 | 更新文献检索 | 文献矩阵 |
| 9月12日 | 下载 PAMAP2、固定 raw hash；检查 F: 容量 | DATA_MANIFEST RC、host preflight |
| 9月13日 | 提交 dataset hash、task root/salt commitments；实现 timestamp/字段/缺失导入器；签发 task-build admission | seed commitments、importer tests、`REAL_TASK_BUILD_ADMITTED` |
| 9月14日 | 使用已承诺 task root 运行首次 label-only enumeration | task index RC、初步 Data Gate |
| 9月15日 | 实现 fixed-\(M\)/fixed-\(T\)、DGP、575-start 映射和固定 BPI/MOMENTS | feature/window/DGP tests |
| 9月16日 | 实现 M0、M1、独立慢速参考和 p-value replay | resampler tests |
| 9月17日 | 完成 `REAL_DATA_TASK_GATE` 并冻结 task index，或进入 REAL omission 终态；完成 T2/T3 | task/truth commitments 或 omission record、Theory draft 1 |
| 9月18日 | 完成 T4 证明审读或触发理论降级 | Theory Freeze memo |
| 9月19日 | 完成 SCOPE_DESIGN、active-component/index builder、分析器、CI、Holm 和整簇 bootstrap | scope/identity/evaluator tests |
| 9月20日 | 全套攻击测试；完成 REAL schema/opaque-ID/ACL/mount/network 攻击；基准 workers=1/4/8/10/12 | attack report、REAL isolation evidence、首版 runtime budget |
| 9月21日 | 完成 H0/H1 32-replicate blind smoke，并按冻结任务数完成 REAL smoke/runtime 外推 | 4,608-row synthetic smoke seal、`REAL_COMPUTE_SCHEDULE_GATE` 报告、无科学汇总 |
| 9月22日 | 只修复实现/性能问题并重跑受影响 smoke | amendment 或 `NO_CHANGE`、最终预算 |
| 9月23日 | 协议、方法、scope、seed、compute 和分析共同冻结；裁定 REAL isolation 与 compute-schedule Gates | freeze manifest、Git tag、两个 REAL gates |
| 9月24日 | 签发 NULL admission 与 ALT 配置预检；REAL 三个 Gate 都 PASS 时签发 prediction admission，否则按原因写 omission/deferred | NULL admission、ALT pre-admission、REAL admission/omission/deferred record |
| 9月25–29日 | 按 N-AR × replicate bundles 运行全部14个物理格 | 原子 shards、每日完整性报告 |
| 9月30–10月4日 | 按 N-CIRCLE × replicate bundles 运行全部14个物理格 | 原子 shards、每日完整性报告 |
| 10月5日 | H0 phase seal；用其 hash 完成 ALT upstream binding 并签发正式 ALT admission | null phase seal、ALT admission |
| 10月6日 | 锁定 H0 主分析并生成图2–图6 | canonical null summaries |
| 10月6–9日 | 运行两组 H1 的全部固定 bundles | H1 shards |
| 10月10日 | H1 ledger seal 与 size-standardized analysis | power/localization summaries |
| 10月11日 | 对已冻结 PAMAP2 tasks 运行 label-isolated predictions；未完整 seal 时保持 truth 封闭 | prediction phase seal 或 `REAL_DEFERRED` |
| 10月12日 | 仅在 prediction 已 seal 时 unseal truth，验证 truth seal、签发 evaluation admission并构建 evaluation phase seal；科学 GO/NO-GO | truth/evaluation seals 或延期记录、最终 Claim Matrix 草案 |

`REAL_COMPUTE_SCHEDULE_GATE` 在 task index 冻结后按实际 \(N_{task}\) 独立外推 wall time、peak RAM 与 peak disk，并要求全部 prediction 可在 10月11日结束前完成。若不满足，调整日历或计算资源，禁止抽取任务子集；截至 admission 日仍不满足时不签发 REAL prediction admission，truth 保持封闭，写 `schedule_disposition=REAL_DEFERRED`，不得误记为 data omission。若截至 10月12日 prediction phase seal 仍未形成，采用同一 disposition；真实案例不进入正文，合成证据继续。

---

## 24. 范围与日历失败规则

本计划已经删除额外 \(\rho\)、额外几何、Betti、DistHist 和新带宽探针，因此没有可在结果后继续削减的模拟外圈。以下核心整体冻结：

- T2/T3 及按 9月18日规则保留或降级的 T4；
- BPI 与 MOMENTS；
- M0 与 M1；
- 28 个 H0 格 × 2,500；
- 8 个 H1 格 × 1,600；
- Fixed-\(M\)/Fixed-\(T\)、新 seed、完整 ledger 和主表图。

冻结前只允许四条预设分流：

1. 9月17日 `REAL_DATA_TASK_GATE` 或 9月23日 `REAL_ISOLATION_ADMISSION_GATE` 失败：PAMAP2 进入 `REAL_OMITTED_BY_DATA_GATE`；
2. 9月18日 T4 未闭合：按 T6 降级理论措辞；
3. 9月22日计算 Gate 失败：停止推进，先完成性能工程或迁移计算资源。
4. REAL 专属 compute-schedule Gate 失败而合成 Gate 通过：只将 REAL 记为 `REAL_DEFERRED` 并保持 truth 封闭，合成主线继续。

9月23日冻结后，延误不改变科学范围。若 10月8日仍未 seal H0，或 10月12日仍未 seal H1，`schedule_disposition` 自动写为 `DEADLINE_NO_GO`；科学 run 状态保持原值，研究继续完成，但不为追赶截止日期删格、减 MC、换方法或省略不利结果。

---

## 25. 发布包

文件名固定：

```text
OWTDA-CAL-R1_release_202610xx.zip
OWTDA-CAL-R1_release_202610xx.zip.sha256
OWTDA-CAL-R1_release_202610xx.attestation.json
OWTDA-CAL-R1_release_202610xx.attestation.sig
```

至少包括：

### A. 身份

- `PROJECT_IDENTITY.json`
- `GIT_REFS.json`：formal-compute、analysis-freeze 与 pre-index `release_source_commit/tag`
- `RELEASE_SPEC_v1.0.yaml`
- `RELEASE_INDEX_<release_id>.json`
- `ACTIVE_COMPONENT_MANIFEST_<active_revision_id>.json`
- `ANALYSIS_SEAL_<analysis_id>.json`
- active/superseded run-instance map
- `package_manifest.json`
- `SHA256SUMS.txt`

### B. 设计

- Project Charter
- Protocol
- Method Spec
- SAP
- Data Spec
- Claim Matrix
- Prior Evidence Summary
- Amendment/Invalidation Registry
- `SCOPE_SPEC_v1.json`、各 phase 的 `SCOPE_DESIGN_<phase>_<scope_design_hash>.csv`、三层 active indexes，以及所有 active `RUN_INPUT_BINDINGS_<run_input_bindings_hash>.jsonl`、`RUN_COMPONENT_SET`、data/evaluation/feature expected indexes 与 `SHARD_PLAN_<run_instance_id>.json`

### C. 环境与代码

- `pyproject.toml`
- lockfile
- Dockerfile 或等价环境说明
- source、tests、configs、runner、audit、table/figure scripts

### D. 运行证据

- preflight
- seed/root-entry registry snapshots、secret commitment/reveal registry 与 commitments
- run registry
- canonical JSONL.gz identity ledgers 与经逐行 hash 核对的派生 Parquet ledgers
- shard manifests、attempt ledger、logs、seals
- attack report、p-value replay、transition validation

### E. 数据

- DGP 规格
- PAMAP2 下载和许可说明
- raw checksums
- importer
- task/eligibility manifest
- 原始 PAMAP2 默认不随包重分发，复现者按官方 DOI 获取并核对 hash

### F. 结果与论文

- canonical summaries
- `ANALYSIS_INPUT_MANIFEST_<analysis_input_manifest_hash>.json`、`ESTIMAND_SPEC_REGISTRY_v1.json`、`RESOLVED_ESTIMAND_INDEX_<analysis_id>.jsonl` 与 `RESOLVED_BOOTSTRAP_PLAN_INDEX_<analysis_id>.jsonl`
- machine-readable tables
- PDF/SVG/PNG figures及元数据
- manuscript values
- Word/PDF 稿件
- supplement
- known limitations

### G. 复现入口

```text
REPRODUCE.md
validate_release.py
reproduce_tables.py
reproduce_figures.py
run_smoke.py
run_full_synthetic.py
```

复现级别：

| 等级 | 内容 |
|---|---|
| R0 | 校验身份和全部 hash |
| R1 | 从 sealed ledger 重建表图 |
| R2 | 运行 blind smoke |
| R3 | 重跑完整合成实验 |
| R4 | 合法取得 PAMAP2 后重跑真实分析 |

release 的身份边界固定为：先创建 pre-index `release_source_commit/tag`，其 tree 明确排除 `GIT_REFS.json`、release index、package manifest、SHA、ZIP、sidecar 与 attestation；commit/tag 固定后才生成 strict canonical `GIT_REFS.json` 并记录 formal-compute、analysis-freeze 与该 pre-index source refs。`GIT_REFS.json` 随其他普通文件进入 release `payload_entries`，但永不回灌 source commit/tag，由此消除 commit-ID 自环。随后解析冻结的 release spec 得到 `payload_entries`，每项恰为 `{path,size,file_sha256}`，POSIX relative path 唯一并按 path ASCII 排序；该集合明确排除 release index 自身、`package_manifest.json`、`SHA256SUMS.txt`、ZIP、sidecar 与 attestation。

所有 release paths 必须是 NFC、ASCII-portable relative paths；禁止绝对路径、反斜杠、控制字符、空段、`.`/`..` 段、尾随点/空格和 Windows reserved basename，并拒绝 ASCII-casefold 后碰撞。源文件和 ZIP members 只能是 regular files；禁止 symlink、hardlink、device、显式 directory entry 与重复 member。ZIP central-directory member 名集合必须精确等于 `SHA256SUMS.txt` 的 path 集再加唯一 `SHA256SUMS.txt`；validator 先检查 central directory，再流式读取每个 member 的未压缩 bytes核对 size/SHA，禁止先解压到文件系统。随后计算：

```text
release_id = H("release", project_id=..., protocol_id=...,
    freeze_id=..., evidence_generation_id=...,
    release_spec_hash=...,
    analysis_id=..., analysis_seal_hash=...,
    analysis_frozen_event_hash=..., analysis_state_head_hash=...,
    payload_entries=...)
```

再生成 `RELEASE_INDEX_<release_id>.json`；其 strict 顶层恰含 `{schema_version,release_id,project_id,protocol_id,freeze_id,evidence_generation_id,release_spec_hash,analysis_id,analysis_seal_hash,analysis_frozen_event_hash,analysis_state_head_hash,payload_entries}`，unknown field 拒绝，entries 与 release-ID 输入逐项同 byte 语义。validator 从对象字段重算 release ID，并要求重算值、对象值与文件名值三者相同；index bytes、文件名和下游 packaging objects 都不进入 `release_id`。

发布顺序固定：先冻结上述 payload；再生成 release index；再生成 canonical JSON+LF 的 `package_manifest.json`，其顶层恰含 `{schema_version,release_id,entries}`，entries 必须精确等于 release index 的 `payload_entries` 加该 index 自身的 `{path,size,file_sha256}`，按 path ASCII 排序且唯一，排除 manifest 自身和 `SHA256SUMS.txt`。最后生成 `SHA256SUMS.txt`：按 POSIX path ASCII 排序，每行严格为 `<64 lowercase hex><两个空格><path><LF>`，行集合精确等于 `package_manifest.entries` 加 `package_manifest.json`，每个 path 恰一行，禁止 BOM/CRLF。ZIP 内容恰为这些文件再加 `SHA256SUMS.txt`；生成前后都重算全部 size/hash。任何工具不得建立自引用或 manifest/SHA 互相递归哈希。

ZIP 完成验证、准备追加 `RELEASED` 事件前，必须 CAS 检查 authoritative analysis-state head 与 current `(analysis_id,analysis_seal_hash,analysis_frozen_event_hash)` 仍等于 release index；任何改变都废弃 pending package并重建。

ZIP 形成后另生成包外 strict `RELEASE_ATTESTATION_<release_id>.json`，恰含 `schema_version,release_id,release_index_file_sha256,package_manifest_file_sha256,sha256sums_file_sha256,zip_filename,zip_sha256`，不得回灌 payload 或 ZIP。项目初始化时生成独立 Ed25519/minisign release key并把 public-key fingerprint写入 Project Charter；用它生成 `.attestation.sig`，再以签名 annotated Git tag指向只含 attestation/signature的 post-package commit。私钥不得进入仓库或 release。若签名基础设施在 G0 前不能闭合，必须改用预先登记的机构不可变发布记录，不能只依赖可被一起替换的 ZIP 与 sidecar。

---

## 26. 最终验收清单

- [ ] DMB-R1 已打终止标签并只读归档；
- [ ] 旧结果明确标记为 L1；
- [ ] 新项目 ID、协议、方法和 seed 与旧代完全分离；
- [ ] 主统计量确认为有限维 mean-CUSUM；
- [ ] T2/T3 证明和数值反例一致；
- [ ] T4 已证明或按规则降级；
- [ ] 固定 BPI/MOMENTS 的全部显式参数与实现已 hash；
- [ ] 无全序列自适应特征步骤；
- [ ] 28 个 H0 格、8 个 H1 格和 280,000/51,200 个逻辑槽位已在 SCOPE_DESIGN 冻结；
- [ ] \(B=999\) 和 p 值公式已冻结；
- [ ] 工作区和 stash 均为空；
- [ ] attack suite 全通过；
- [ ] smoke evaluator 未泄露科学汇总；
- [ ] formal runner 在 admission 前没有消费正式 RNG stream；
- [ ] seed registry 复合键、root entry 与每类 RNG consumption golden fixtures 全部通过；
- [ ] \(w^*\)、RAM、F: 容量和 268.8 小时 wall Gate 全通过；
- [ ] ledger 100% 完整、唯一、可重放；
- [ ] 科学失败没有被误记成运行失败；
- [ ] 所有失效记录 append-only；
- [ ] 表图全部由 sealed ledger 程序化生成；
- [ ] analysis input、resolved estimand index 与 analysis seal 闭合且 `ANALYSIS_FROZEN` 已登记；
- [ ] 功效同时报告对应 size 和 size-adjusted power；
- [ ] PAMAP2 identity、task index、prediction/truth/evaluation 三层 seal 闭合，或按规则省略；
- [ ] manuscript consistency checker 通过；
- [ ] release spec 已冻结，结果期 release index 是打包唯一真源；
- [ ] `release_id` 绑定 exact payload entries 与最终 analysis seal，且所有控制文件无自引用；
- [ ] release 无意外零字节、缺失和未经 active manifest 授权的代际文件；合法空对象均有 `empty_by_contract` 证明；
- [ ] 空环境完成 R0、R1、R2；
- [ ] ZIP 外部 SHA256 sidecar 验证通过；
- [ ] release attestation、签名和预登记 public key 验证通过；
- [ ] `open_runs=0`；
- [ ] Claim Matrix 每项具有最终状态；
- [ ] 主张未超出证据范围。

---

## 27. 后续研究线，禁止混入本轮

本轮结束后另立 `OWTDA-CAL-R2`，研究 stride-equivariant DMB。候选尺度可以从

\[
b(s)\approx
\left\lceil\frac{W+L_{raw}}s\right\rceil,
\]

出发，但 Bartlett taper 会再次衰减样本自协方差，因此该式只能进入开发阶段，必须先推导目标协方差再预注册确认。R2 可用同一乘子路径联合校准"候选位置 × 预注册窗口尺度"的最大统计量。另一条路线是在原始时间轴做 block bootstrap，每次重新生成窗口、点云、持续图和扫描量，同时对块拼接缝采用删窗或 taper。

R2 必须拥有新协议、新方法 ID、新 seed 和独立确认数据。本轮结果只能用于提出 R2 假设，不能充当 R2 的确认数据。

---

## 28. 一句话执行口径

> 先证明并冻结"窗口如何改变依赖"，随后用新数据完整绘制方法在哪些区域反保守、近名义或保守；任何不利数值都保留，任何数值实现变化都按依赖矩阵作废受影响证据。
